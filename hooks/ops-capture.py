#!/usr/bin/env python3
"""ops-capture.py — SessionEnd hook: captura conocimiento operativo a un inbox.

Stdin: JSON con session_id, cwd, transcript_path, hook_event_name (Claude Code).
Flujo:
  1. guard de subsesión interna (no capturar la subsesión Haiku del corrector);
  2. leer el transcript de la sesión;
  3. GATE barato (helper): extraer fragmentos operativos — si no hay, salir sin costo;
  4. invocar un subagente vía `claude -p` que extrae DELTAS propuestos;
  5. escribir un `*.inbox.md` al inbox efímero (NEB_OPS_INBOX_DIR, default ~/.claude/ops-inbox/).

NO toca la fuente de verdad: la aplicación de los deltas es gated por el comando
`/ops-review` del overlay. Defensivo: exit 0 siempre — errores a stderr.

Opt-in por proyecto (settings.json). Mecanismo genérico; el overlay especializa el
prompt de detección (NEB_OPS_CAPTURE_PROMPT_FILE) y el vocabulario (NEB_OPS_SIGNALS_EXTRA).
Lineamiento: hooks/README.md §ops-capture. Pieza 2a de la metodología.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys

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

import ops_inbox  # noqa: E402  (mismo dir lib/, ya en sys.path)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
SUBPROCESS_TIMEOUT = 120

GENERIC_PROMPT = """Eres un asistente que extrae CONOCIMIENTO OPERATIVO de una sesión de dev para que no se pierda.

Te paso fragmentos de la sesión que mencionan operación de infraestructura (accesos a servidores, scripts, comandos de base de datos, despliegues, reglas). Detecta HALLAZGOS OPERATIVOS nuevos o cambiados que valga la pena persistir en una fuente de verdad, y emítelos como DELTAS.

Por cada hallazgo, un bloque markdown:

## Delta N
- destino: proyectos-activos-ambientes.md | skill onibex-ops/scripts-map.md | profile deployment-scripts | (sugerir)
- tipo: acceso | script | regla | gotcha
- resumen: <una línea>
- propuesta: <qué anotar en la fuente de verdad>
- actual: <valor anterior si se infiere, o "(nuevo)">
- evidencia: <comando o archivo de la sesión que lo respalda>
- confianza: confirmado | hipotesis

Reglas estrictas:
- NUNCA incluyas secretos (contraseñas, llaves privadas, tokens). Si un acceso cambió, describe el HECHO ("la llave de X ahora es Y.pem") sin volcar el secreto.
- Si algo es suposición no confirmada en la sesión, marca confianza: hipotesis. No inventes: solo lo respaldado por los fragmentos.
- Si no hay ningún hallazgo digno de persistir, responde EXACTAMENTE: SIN HALLAZGOS"""

NO_FINDINGS = "SIN HALLAZGOS"


def log(msg):
    print(f"[ops-capture] {msg}", file=sys.stderr)


def find_claude_cli():
    for name in ("claude", "claude.cmd", "claude.exe"):
        path = shutil.which(name)
        if path:
            return path
    return None


def load_prompt():
    """Prompt de detección: genérico, o el del overlay si `NEB_OPS_CAPTURE_PROMPT_FILE`."""
    path = os.environ.get("NEB_OPS_CAPTURE_PROMPT_FILE")
    if path:
        try:
            with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
                text = f.read().strip()
            if text:
                return text
        except OSError as e:
            log(f"prompt override ilegible ({path}): {e}; usando genérico")
    return GENERIC_PROMPT


def run_capture(excerpts, model):
    """Invoca `claude -p` con los fragmentos operativos. Devuelve el texto o None."""
    cli = find_claude_cli()
    if not cli:
        log("claude CLI no encontrado en PATH; skip")
        return None
    env = mark_internal_subsession(os.environ.copy())
    user_input = "Fragmentos operativos de la sesión:\n\n" + "\n".join(excerpts)
    try:
        proc = subprocess.run(
            [cli, "-p", "--model", model, "--system-prompt", load_prompt(), user_input],
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
            encoding="utf-8", errors="replace", env=env,
        )
    except subprocess.TimeoutExpired:
        log(f"timeout {SUBPROCESS_TIMEOUT}s; skip")
        return None
    except OSError as e:
        log(f"falla al invocar claude: {e}")
        return None
    if proc.returncode != 0:
        log(f"claude -p exit {proc.returncode}; stderr: {proc.stderr.strip()[:200]}")
        return None
    out = proc.stdout.strip()
    return out or None


def main():
    if is_internal_subsession():
        return
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    transcript_path = payload.get("transcript_path", "")
    cwd = payload.get("cwd", "")
    session_id = payload.get("session_id", "")
    if not transcript_path:
        return

    # Gate en streaming con ventana: no materializa el transcript (puede pesar MB)
    # y conserva inicio + final si hay muchos hits (ver ops_inbox).
    excerpts = ops_inbox.extract_operational_excerpts_from_file(transcript_path)
    if not excerpts:
        return  # gate: sin transcript legible o sin actividad operativa

    model = os.environ.get("NEB_OPS_CAPTURE_MODEL", DEFAULT_MODEL)
    result = run_capture(excerpts, model)
    if not result or result.strip() == NO_FINDINGS:
        return

    home = os.path.expanduser("~")
    project = os.path.basename(cwd.rstrip("/\\")) or "session"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    inbox_dir = ops_inbox.resolve_inbox_dir(home=home)
    filename = ops_inbox.inbox_filename(project, session_id, stamp)
    header = f"# ops-capture — {project} — {session_id} — {stamp}\n\n"
    try:
        path = ops_inbox.write_inbox(inbox_dir, filename, header + result + "\n")
        log(f"inbox escrito: {path}")
    except OSError as e:
        log(f"no se pudo escribir inbox: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — defensivo, nunca romper el cierre
        log(f"excepción no manejada: {e}")
    sys.exit(0)
