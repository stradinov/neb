#!/usr/bin/env python3
"""
preprocess-prompt.py — UserPromptSubmit hook: corrige ortografía y prepara eco + confirmación.

Stdin: JSON con campos prompt, session_id, cwd, permission_mode (Claude Code).
Stdout: JSON con hookSpecificOutput.additionalContext (preámbulo para Claude principal) o vacío.
Salida: exit 0 siempre — hook defensivo, errores a stderr.

Dónde lee (desde 8.0.0, rutas de hooks/lib/neb_paths.py):
    <datos>/config.json, sección `preprocess`         modo, modelo y prefijo persistentes
    <datos>/state/preprocess/<session_id>.json        modo de la sesión, que escribe /preprocess

CLI (la usa commands/preprocess.md; no es parte del hook):
    preprocess-prompt.py --set-session-mode <session_id> <full|fast|off>
        escribe atómicamente el modo de la sesión, borra los estados de más de 7 días de esa carpeta e
        imprime la ruta escrita. Salida 0; 2 si el session_id, el modo o la carpeta no sirven.

Lineamiento: tooling/prompt-preprocessing.md.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

# Helper de subsesión interna (hooks/lib/subsession.py). Fallback inline si el
# import falla — el hook nunca debe romperse por esto.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
try:
    from subsession import is_internal_subsession, mark_internal_subsession
except ImportError:
    def is_internal_subsession(env=None):
        env = os.environ if env is None else env
        return (env.get("NEB_INTERNAL_SUBSESSION") == "1"
                or env.get("CLAUDE_PREPROCESS_RECURSION") == "1")

    def mark_internal_subsession(env):
        env["NEB_INTERNAL_SUBSESSION"] = "1"
        env["CLAUDE_PREPROCESS_RECURSION"] = "1"
        return env

# Resolvedor de la carpeta de datos y de config.json (hooks/lib/neb_paths.py, 8.0.0). Vive en el mismo
# árbol; si aun así no importa, el hook sigue con los valores por omisión y sin estado por sesión.
try:
    import neb_paths
except ImportError:
    neb_paths = None

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS = {
    "mode": "off",  # arranca inerte; el dev lo enciende con /preprocess full|fast o config.json (REQ v5.4.0)
    "model": "claude-haiku-4-5-20251001",
    "prefix": "$$",
}

VALID_MODES = ("full", "fast", "off")

# session_id que se acepta como nombre de archivo de estado. Claude Code usa UUID (36 caracteres); el tope
# deja margen sin admitir separadores, `..` ni nombres que el sistema de archivos rechace.
SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
STATE_NAME = "preprocess"
LEGACY_STATE_DIR = "preprocess-state"  # ~/.claude/preprocess-state/, antes de 8.0.0
STATE_MAX_AGE = 7 * 24 * 3600  # segundos; un estado más viejo es de una sesión que ya terminó

SKIP_REGEX = re.compile(
    r"^(hola|hi|hello|si|sí|yes|no|ok|okay|gracias|thanks|listo|"
    r"continúa|continua|continue|sigue|dale|va|oui|salut)\s*[.!?]*$",
    re.IGNORECASE,
)

CODE_KEYWORDS = re.compile(
    r"^(function|const|let|var|def|class|return|import|from|if|else|for|while|"
    r"SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|public|private|async|await)\b"
)

CODE_TOKENS = re.compile(r"[{};=]|:=|->|=>")
STACK_TRACE = re.compile(
    r"(at\s+\S+\s+\([^)]+:\d+\)|File\s+\"[^\"]+\",\s+line\s+\d+)"
)
SUBPROCESS_TIMEOUT = 30


def log(msg):
    print(f"[preprocess-prompt] {msg}", file=sys.stderr)


def load_config(home=None, env=None):
    """Sección `preprocess` de la config de Neb (neb_paths: <datos>/config.json leído en utf-8-sig o, sin
    él, el `~/.claude/preprocess.json` de antes de 8.0.0). Campo ausente, vacío o de otro tipo y modo
    desconocido caen al default. Nunca levanta."""
    cfg = dict(DEFAULTS)
    if neb_paths is None:
        log("hooks/lib/neb_paths.py no importó; usando defaults")
        return cfg
    try:
        user_cfg = neb_paths.section("preprocess", home, env)
    except Exception as e:  # defensivo: el hook nunca se rompe por la config
        log(f"config ilegible, usando defaults: {e}")
        return cfg
    if isinstance(user_cfg, dict):
        for k in DEFAULTS:
            value = user_cfg.get(k)
            if isinstance(value, str) and value:
                cfg[k] = value
    if cfg["mode"] not in VALID_MODES:
        # Un modo mal escrito en config.json no enciende el hook: sin esta guarda caía en la rama `fast`.
        log(f"modo desconocido en config.json: {cfg['mode']!r}; usando {DEFAULTS['mode']!r}")
        cfg["mode"] = DEFAULTS["mode"]
    return cfg


def valid_session_id(session_id):
    """True si `session_id` sirve como nombre de archivo de estado (ver SESSION_ID_RE)."""
    return isinstance(session_id, str) and SESSION_ID_RE.fullmatch(session_id) is not None


def session_state_path(session_id, home=None, env=None):
    """<datos>/state/preprocess/<session_id>.json, o None si el session_id no sirve o falta neb_paths."""
    if neb_paths is None or not valid_session_id(session_id):
        return None
    return os.path.join(neb_paths.state_dir(STATE_NAME, home, env), f"{session_id}.json")


def _legacy_state_path(session_id, home=None):
    """~/.claude/preprocess-state/<session_id>.json (antes de 8.0.0)."""
    return os.path.join(neb_paths.legacy_dir(home), LEGACY_STATE_DIR, f"{session_id}.json")


def _read_state_mode(path):
    """(existe, modo válido o None). Ilegible, otro tipo o modo desconocido → (True, None)."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        return False, None
    except (ValueError, OSError):
        return True, None
    mode = data.get("mode") if isinstance(data, dict) else None
    return True, (mode if mode in VALID_MODES else None)


def read_session_mode(home, session_id, env=None):
    """Modo fijado con /preprocess para esta sesión, o None (sin estado, session_id inválido, ilegible)."""
    path = session_state_path(session_id, home, env)
    if path is None:
        return None
    exists, mode = _read_state_mode(path)
    if exists:
        return mode
    # Residuo de transición (sale en 9.0.0): una sesión abierta antes de actualizar a 8.0.0 pudo fijar su
    # modo en la ruta vieja con el /preprocess anterior. Solo se lee si el archivo nuevo no existe.
    return _read_state_mode(_legacy_state_path(session_id, home))[1]


def resolve_mode(prompt, cfg, home, session_id, env=None):
    """Aplica precedencia: prefijo > sesión > env > config.json > default."""
    env = os.environ if env is None else env
    prefix = cfg.get("prefix") or "$$"

    if prompt.startswith(prefix):
        rest = prompt[len(prefix):]
        if rest == "" or rest[0].isspace() or rest[0].isalnum():
            return "off", prompt[len(prefix):].lstrip()

    session_mode = read_session_mode(home, session_id, env)
    if session_mode:
        return session_mode, prompt

    env_mode = env.get("CLAUDE_PREPROCESS_MODE")
    if env_mode in VALID_MODES:
        return env_mode, prompt

    mode = cfg.get("mode", "off")
    return (mode if mode in VALID_MODES else DEFAULTS["mode"]), prompt


# --------------------------------------------------------------------------- estado por sesión (CLI)

def _is_link(path):
    """Symlink o junction (Windows). Misma regla que neb_paths: no se escribe ni se borra a través de uno."""
    try:
        if os.path.islink(path):
            return True
        st = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _state_folder(home=None, env=None):
    """Crea <datos>, <datos>/state y <datos>/state/preprocess (0700) comprobando en cada nivel que no sea
    un enlace (ensure_dir solo revisa la carpeta que recibe). ValueError si alguno lo es."""
    data = neb_paths.ensure_data_dir(home, env)
    neb_paths.ensure_dir(os.path.join(data, "state"))
    return neb_paths.ensure_dir(neb_paths.state_dir(STATE_NAME, home, env))


def purge_old_states(folder, now=None, max_age=STATE_MAX_AGE, keep=None):
    """Borra de `folder` los `<session_id>.json` (nombre válido) con mtime de hace más de `max_age`.
    No sigue enlaces ni toca otros archivos; `keep` es un nombre que no se borra. Devuelve los borrados.
    Oportunista: un error en un archivo lo deja y sigue."""
    now = time.time() if now is None else now
    removed = []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return removed
    for entry in entries:
        name = entry.name
        if name == keep or not name.endswith(".json") or not valid_session_id(name[:-5]):
            continue
        try:
            if _is_link(entry.path) or not entry.is_file(follow_symlinks=False):
                continue
            if now - entry.stat(follow_symlinks=False).st_mtime <= max_age:
                continue
            os.remove(entry.path)
            removed.append(name)
        except OSError:
            continue
    return removed


def set_session_mode(session_id, mode, home=None, env=None, now=None):
    """Escribe atómicamente {"mode": <modo>} en el estado de la sesión y purga los estados viejos.
    Devuelve la ruta. ValueError si el modo o el session_id no sirven, o si hay un enlace en el camino."""
    if mode not in VALID_MODES:
        raise ValueError(f"modo inválido: {mode!r}; usa {'|'.join(VALID_MODES)}")
    if not valid_session_id(session_id):
        raise ValueError("session_id inválido: solo letras, dígitos, '_' y '-' (hasta 128)")
    if neb_paths is None:
        raise ValueError("hooks/lib/neb_paths.py no importó")
    folder = _state_folder(home, env)
    path = session_state_path(session_id, home, env)
    if _is_link(path):
        raise ValueError(f"{path} es un enlace: Neb no escribe a través de enlaces")
    # Temporal con punto inicial y sufijo .tmp: la purga no lo confunde con un estado.
    fd, tmp = tempfile.mkstemp(prefix=f".{session_id}.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"mode": mode}, f)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    purge_old_states(folder, now=now, keep=os.path.basename(path))
    return path


def cli(argv):
    """`--set-session-mode <session_id> <modo>`: salida 0 con la ruta escrita; 2 con el error en stderr."""
    if len(argv) != 3 or argv[0] != "--set-session-mode":
        print("uso: preprocess-prompt.py --set-session-mode <session_id> <full|fast|off>", file=sys.stderr)
        return 2
    try:
        print(set_session_mode(argv[1], argv[2]))
    except (ValueError, OSError) as e:
        print(f"preprocess-prompt: {e}", file=sys.stderr)
        return 2
    return 0


def is_trivial(prompt):
    """Filtros de skip sin llamar a Haiku: slash command, muy corto, saludo."""
    stripped = prompt.lstrip()
    if stripped.startswith("/"):
        return True
    if len(prompt.strip()) < 12:
        return True
    if SKIP_REGEX.match(prompt.strip()):
        return True
    return False


def is_pure_payload(prompt):
    """Capa A — heurística conservadora para skipear payloads puros."""
    stripped = prompt.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        return True

    lines = [ln for ln in prompt.splitlines() if ln.strip()]
    if not lines:
        return False

    code_lines = 0
    prose_lines = 0
    stack_lines = 0

    for line in lines:
        if STACK_TRACE.search(line):
            stack_lines += 1
            continue
        is_code = (
            CODE_KEYWORDS.match(line.strip())
            or CODE_TOKENS.search(line)
            or (line.startswith("  ") or line.startswith("\t"))
        )
        words = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúñÑüÜ]{4,}", line)
        if is_code:
            code_lines += 1
        if len(words) >= 3:
            prose_lines += 1

    if stack_lines == len(lines):
        return True
    if prose_lines == 0 and (code_lines / len(lines)) > 0.80:
        return True
    return False


SYSTEM_PROMPT = """Eres un corrector de prompts para un dev trabajando en consola.

Aplica la taxonomía documentada en `tooling/redaccion-es.md` (recurso de referencia del repo) con este perfil:
- variedad: auto-detectada según idioma del prompt.
- estrictez: estandar.
- registro: informal.
- dominio: tecnico_software (tolera anglicismos asentados: deploy, retry, webhook, queue, endpoint).
- intervencion.modo: corregir_obligatorios.
- intervencion.preservar_voz_autor: true.
- intervencion.excepciones: [citas_textuales, codigo, nombres_propios, identificadores, paths, URLs, contenido entre backticks o fences].
- salida.formato: texto_corregido_unico.
- salida.nivel_detalle_explicaciones: ninguno.

Detecta el idioma del texto. Identifica partes conversacionales vs código / log / JSON / stack trace / contenido pegado de tercero. Aplica correcciones SOLO en la parte conversacional, en el mismo idioma detectado.

Aplica las secciones 1, 2, 3, 6, 7 de la taxonomía (ortografía literal, acentual con énfasis en tildes diacríticas con impacto semántico, puntual, sintaxis, semántica clara — pleonasmos, impropiedad léxica obvia, falsos amigos comunes).

NO apliques secciones 4 (tipografía), 9 (pragmática/estilo), 10 (cohesión textual), 11 (formato y convenciones) — invasivas en prompts cortos.

NO cambies el significado. NO traduzcas. NO marques ambigüedades de jerga organizacional (terminología corta en mayúsculas que parezca un código interno se preserva tal cual). NO agregues comentarios ni explicaciones.

Si el texto completo NO es petición conversacional (solo código, log, o contenido pegado), devuélvelo idéntico al original.

Devuelve únicamente el texto resultante."""


def find_claude_cli():
    """Localiza el binario claude en PATH. Devuelve None si no está."""
    for name in ("claude", "claude.cmd", "claude.exe"):
        path = shutil.which(name)
        if path:
            return path
    return None


def correct_with_haiku(prompt, model):
    """Capa B — invoca claude -p con Haiku para corrección selectiva."""
    cli = find_claude_cli()
    if not cli:
        log("claude CLI no encontrado en PATH")
        return None
    env = mark_internal_subsession(os.environ.copy())
    try:
        proc = subprocess.run(
            [cli, "-p", "--model", model, "--system-prompt", SYSTEM_PROMPT, prompt],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except subprocess.TimeoutExpired:
        log(f"timeout {SUBPROCESS_TIMEOUT}s al corregir; pasando raw")
        return None
    except OSError as e:
        log(f"falla al invocar claude: {e}")
        return None

    if proc.returncode != 0:
        log(f"claude -p exit {proc.returncode}; stderr: {proc.stderr.strip()[:200]}")
        return None

    corrected = proc.stdout.strip()
    if not corrected:
        return None
    return corrected


def build_preamble(mode, original, corrected):
    """Capa C — preámbulo inyectado a Claude principal."""
    if mode == "full":
        return (
            "[PROMPT PRE-PROCESADO — modo full]\n"
            f"Original: {original}\n"
            f"Corregido: {corrected}\n\n"
            "Antes de actuar:\n"
            "1. Muestra al dev eco breve en el idioma del prompt (1–2 líneas) de lo que entendiste.\n"
            "2. Para escrituras o comandos con efecto, aplica el gate de autorización de la metodología: "
            "pide OK donde el gate lo exige y procede sin pedirlo donde el gate ya exime (artefactos que "
            "Neb genera —registros, pendings, planes—, cambios `.md`-only, autonomías declaradas por "
            "proyecto). No endurezcas el gate \"por las dudas\".\n"
            "3. Si el dev solo conversa o pregunta, omite el paso de confirmación y responde directo.\n"
            "4. Si detectas que el prompt NO es una petición conversacional sino contenido pegado "
            "para análisis (código, log, email, fragmento de doc), omite eco y confirmación; "
            "interpreta directamente el contenido. Las partes de código del prompt se preservaron "
            "intactas en la versión corregida; trátalas como contexto del análisis."
        )
    return (
        "[PROMPT PRE-PROCESADO — modo fast]\n"
        f"Original: {original}\n"
        f"Corregido: {corrected}\n\n"
        "Muestra al dev eco breve en el idioma del prompt (1 línea) y procede directo. Sin esperar confirmación.\n"
        "Si el prompt es contenido pegado, omite eco e interpreta directamente."
    )


def emit(additional_context):
    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": additional_context,
        }
    }
    print(json.dumps(out, ensure_ascii=False))


def main():
    if is_internal_subsession():
        return

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    prompt = payload.get("prompt", "")
    session_id = payload.get("session_id", "")
    if not prompt:
        return

    home = os.path.expanduser("~")
    cfg = load_config(home)
    mode, effective_prompt = resolve_mode(prompt, cfg, home, session_id)

    if mode == "off":
        return
    if is_trivial(effective_prompt):
        return
    if is_pure_payload(effective_prompt):
        return

    corrected = correct_with_haiku(effective_prompt, cfg.get("model", DEFAULTS["model"]))
    if corrected is None:
        return

    emit(build_preamble(mode, effective_prompt, corrected))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--set-session-mode"]:
        sys.exit(cli(sys.argv[1:]))
    try:
        main()
    except Exception as e:
        log(f"excepción no manejada: {e}")
    sys.exit(0)
