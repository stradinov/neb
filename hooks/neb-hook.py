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
    "logbook-sync":         ("Stop", "SessionEnd", "PreCompact"),
    "notify-on-stop":       ("Stop",),
    "notify-on-permission": ("Notification",),
    "preprocess-prompt":    ("UserPromptSubmit",),
}
# Hooks retirados → versión y qué los reemplaza (el arranque avisa si siguen en las variables).
RETIRED = {
    "usage-tracker": "6.29.0; el uso se mide al cerrar con `/neb-usage`",
    "ops-capture": "6.41.0; sin reemplazo en el núcleo: el conocimiento operativo se registra a mano desde la sesión",
}
ENV_VARS = ("NEB_HOOKS", "NEB_PROJECT_HOOKS")
IS_WINDOWS = os.name == "nt"


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


def dispatch(hook, payload, event, home):
    py = sys.executable
    if hook == "logbook-sync":
        args = [event.get(k) or "" for k in ("session_id", "cwd", "transcript_path", "hook_event_name")]
        if all(args):
            _run(hook, [py, os.path.join(LIB, "logbook.py")] + args + [ROOT, home], payload,
                 stderr=subprocess.DEVNULL)
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
