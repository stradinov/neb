#!/usr/bin/env python3
"""
preprocess-prompt.py — UserPromptSubmit hook: corrige ortografía y prepara eco + confirmación.

Stdin: JSON con campos prompt, session_id, cwd, permission_mode (Claude Code).
Stdout: JSON con hookSpecificOutput.additionalContext (preámbulo para Claude principal) o vacío.
Salida: exit 0 siempre — hook defensivo, errores a stderr.

Lineamiento: tooling/prompt-preprocessing.md.
"""

import json
import os
import re
import shutil
import subprocess
import sys

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

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS = {
    "mode": "off",  # arranca inerte; el dev lo enciende con /preprocess full|fast o preprocess.json (REQ v5.4.0)
    "model": "claude-haiku-4-5-20251001",
    "prefix": "$$",
}

VALID_MODES = ("full", "fast", "off")

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


def load_config(home):
    """Lee ~/.claude/preprocess.json; cualquier campo ausente cae al default."""
    cfg_path = os.path.join(home, ".claude", "preprocess.json")
    cfg = dict(DEFAULTS)
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        if isinstance(user_cfg, dict):
            for k in DEFAULTS:
                if k in user_cfg and isinstance(user_cfg[k], str):
                    cfg[k] = user_cfg[k]
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as e:
        log(f"config ilegible, usando defaults: {e}")
    return cfg


def read_session_mode(home, session_id):
    """Lee ~/.claude/preprocess-state/<session_id>.json si existe."""
    if not session_id:
        return None
    state_path = os.path.join(
        home, ".claude", "preprocess-state", f"{session_id}.json"
    )
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        mode = data.get("mode")
        return mode if mode in VALID_MODES else None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def resolve_mode(prompt, cfg, home, session_id):
    """Aplica precedencia: prefijo > sesión > env > archivo personal > default."""
    prefix = cfg.get("prefix") or "$$"

    if prompt.startswith(prefix):
        rest = prompt[len(prefix):]
        if rest == "" or rest[0].isspace() or rest[0].isalnum():
            return "off", prompt[len(prefix):].lstrip()

    session_mode = read_session_mode(home, session_id)
    if session_mode:
        return session_mode, prompt

    env_mode = os.environ.get("CLAUDE_PREPROCESS_MODE")
    if env_mode in VALID_MODES:
        return env_mode, prompt

    return cfg.get("mode", "off"), prompt


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
    try:
        main()
    except Exception as e:
        log(f"excepción no manejada: {e}")
    sys.exit(0)
