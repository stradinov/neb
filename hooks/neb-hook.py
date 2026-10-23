#!/usr/bin/env python3
"""neb-hook.py — dispatcher de los hooks opcionales de Neb registrados por el plugin.

`hooks/hooks.json` registra una entrada por hook con un gate en el shell, que solo arranca Python
si el hook está activado:

  case ",$NEB_HOOKS,$NEB_PROJECT_HOOKS," in *,<hook>,*) python ".../hooks/neb-hook.py" <hook> || python3 … ;; esac

`NEB_HOOKS` es la lista personal (env de `~/.claude/settings.json` o de `settings.local.json`) y
`NEB_PROJECT_HOOKS` la del proyecto (env de su `.claude/settings.json` versionado); cuenta la unión.

Este script lee una vez el JSON del evento (stdin) y corre el hook con el código de su propio árbol:
la versión instalada del plugin, o el clon con `--plugin-dir`. No usa NEB_HOME.

Defensivo: ante cualquier falla, exit 0 — un hook no bloquea la sesión.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIB = os.path.join(HERE, "lib")
sys.path.insert(0, LIB)

try:
    from subsession import is_internal_subsession
except ImportError:
    def is_internal_subsession(env=None):
        env = os.environ if env is None else env
        return (env.get("NEB_INTERNAL_SUBSESSION") == "1"
                or env.get("CLAUDE_PREPROCESS_RECURSION") == "1")

# Hook → evento(s) donde hooks/hooks.json lo registra. test_hooks_json.py verifica que coincidan.
HOOKS = {
    "save-approved-plan":   ("PostToolUse",),
    "usage-tracker":        ("Stop",),
    "logbook-sync":         ("Stop", "SessionEnd", "PreCompact"),
    "notify-on-stop":       ("Stop",),
    "notify-on-permission": ("Notification",),
    "ops-capture":          ("SessionEnd",),
    "preprocess-prompt":    ("UserPromptSubmit",),
}
ENV_VARS = ("NEB_HOOKS", "NEB_PROJECT_HOOKS")
IS_WINDOWS = os.name == "nt"

# Windows: sin ventana de consola (ops-capture lanza `claude -p`), grupo propio y fuera del job del
# proceso padre, para sobrevivir al presupuesto de 1.5 s de SessionEnd.
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_NO_WINDOW = 0x08000000
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def _tokens(env, var):
    return [t for t in env.get(var, "").split(",") if t != ""]


def enabled_hooks(env=None):
    """Hooks activados: unión de NEB_HOOKS y NEB_PROJECT_HOOKS (mismo criterio que el gate del shell)."""
    env = os.environ if env is None else env
    return {t for var in ENV_VARS for t in _tokens(env, var) if t in HOOKS}


def invalid_tokens(env=None):
    """[(variable, valor)] que el gate no reconoce: nombres desconocidos o con espacios."""
    env = os.environ if env is None else env
    return [(var, t) for var in ENV_VARS for t in _tokens(env, var) if t not in HOOKS]


def _child_env():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"   # en Windows el stdio por defecto es cp1252
    return env


def _log(msg):
    # Con exit 0, Claude Code muestra el stderr de un hook solo en modo verbose: rastro sin ruido.
    try:
        sys.stderr.write("[neb-hook] %s\n" % msg)
    except (OSError, ValueError):
        pass


def _run(hook, argv, payload, stdout=subprocess.DEVNULL, stderr=None, timeout=None):
    try:
        subprocess.run(argv, input=payload, stdout=stdout, stderr=stderr,
                       env=_child_env(), timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        _log("%s: %r" % (hook, e))


def _spawn_detached(hook, argv, payload):
    """Lanza `argv` con `payload` por stdin y no lo espera. El hijo sobrevive al proceso del hook."""
    kwargs = dict(stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  env=_child_env())
    if IS_WINDOWS:
        flags = _CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP
        attempts = [flags | _CREATE_BREAKAWAY_FROM_JOB, flags]   # sin breakaway si el job no lo permite
    else:
        kwargs["start_new_session"] = True
        attempts = [0]
    for flags in attempts:
        try:
            if IS_WINDOWS:
                kwargs["creationflags"] = flags
            proc = subprocess.Popen(argv, **kwargs)
        except OSError as e:
            _log("%s (flags %#x): %r" % (hook, flags, e))
            continue
        try:
            proc.stdin.write(payload)
            proc.stdin.close()
        except OSError:
            pass
        return proc
    return None


def _encoded_project_dir(event):
    """Nombre del directorio del proyecto en ~/.claude/projects: el padre de transcript_path, que es
    exacto (Claude Code convierte también `.`), o la codificación del cwd de usage-tracker.sh."""
    parts = re.split(r"[/\\]", event.get("transcript_path") or "")
    if len(parts) >= 3 and parts[-3] == "projects" and parts[-2]:
        return parts[-2]
    cwd = event.get("cwd") or ""
    return cwd.replace(":", "-").replace("/", "-").replace("\\", "-")


def dispatch(hook, payload, event, home):
    py = sys.executable
    if hook == "logbook-sync":
        sid, cwd = event.get("session_id") or "", event.get("cwd") or ""
        if sid and cwd:
            _run(hook, [py, os.path.join(LIB, "logbook.py"), sid, cwd, event.get("transcript_path") or "",
                  event.get("hook_event_name") or "", ROOT, home], payload, stderr=subprocess.DEVNULL)
    elif hook == "usage-tracker":
        sid, cwd = event.get("session_id") or "", event.get("cwd") or ""
        if sid and cwd:
            _run(hook, [py, os.path.join(LIB, "usage-tracker.py"), sid, _encoded_project_dir(event), ROOT, home],
                 payload, stderr=subprocess.DEVNULL)
    elif hook == "save-approved-plan":
        import approved_plan
        approved_plan.save(event, home)
    elif hook in ("notify-on-stop", "notify-on-permission"):
        if IS_WINDOWS:
            argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    os.path.join(HERE, hook + ".ps1")]
        else:
            argv = ["bash", os.path.join(HERE, hook + ".sh")]
        # Salida a DEVNULL: el .sh deja la reproducción en segundo plano (`& disown`) con los
        # descriptores heredados, y con un pipe el dispatcher la esperaría.
        _run(hook, argv, payload, stderr=subprocess.DEVNULL, timeout=9)
    elif hook == "ops-capture":
        _spawn_detached(hook, [py, os.path.join(HERE, "ops-capture.py")], payload)
    elif hook == "preprocess-prompt":
        # El stdout del hijo es el del hook: su JSON es el contexto que inyecta UserPromptSubmit.
        _run(hook, [py, os.path.join(HERE, "preprocess-prompt.py")], payload, stdout=None, timeout=33)


def main(argv):
    if len(argv) < 2 or is_internal_subsession():
        return
    hook = argv[1]
    if hook not in enabled_hooks():
        return
    payload = sys.stdin.buffer.read()
    try:
        event = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return
    if not isinstance(event, dict):
        return
    dispatch(hook, payload, event, os.path.expanduser("~"))


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception as e:  # noqa: BLE001 — defensivo, nunca romper la sesión
        _log("%s: %r" % (sys.argv[1:2], e))
    sys.exit(0)
