#!/usr/bin/env python3
"""test_hooks_json.py — hooks/hooks.json del plugin contra el dispatcher (6.15.0).

  • cada entrada de un hook opcional usa el mismo nombre en el gate y en el argumento de neb-hook.py,
    y está en el evento que declara neb-hook.py (HOOKS); no falta ninguna
  • el placeholder va entre comillas y la cadena de intérpretes es `python … || python3 …`
  • timeouts: notify-* 10 s, preprocess-prompt 35 s (su `claude -p` interno es de 30 s)
  • el SessionStart no cambia
  • el gate en un shell real: unión de NEB_HOOKS y NEB_PROJECT_HOOKS, sin falsos positivos por
    prefijo, stdin íntegro hasta el script

Framework: unittest (stdlib).
  py -m unittest discover -s hooks/tests -p test_hooks_json.py
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
HOOKS_JSON = os.path.join(HOOKS_DIR, "hooks.json")

_spec = importlib.util.spec_from_file_location("neb_hook", os.path.join(HOOKS_DIR, "neb-hook.py"))
nh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nh)

GATE_RE = re.compile(
    r'^case ",\$NEB_HOOKS,\$NEB_PROJECT_HOOKS," in \*,(?P<gate>[a-z-]+),\*\) '
    r'python "\$\{CLAUDE_PLUGIN_ROOT\}/hooks/neb-hook\.py" (?P<a1>[a-z-]+) \|\| '
    r'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/hooks/neb-hook\.py" (?P<a2>[a-z-]+) ;; esac$')
BOOTSTRAP = ('python "${CLAUDE_PLUGIN_ROOT}/bootstrap/neb-bootstrap-context.py" || '
             'python3 "${CLAUDE_PLUGIN_ROOT}/bootstrap/neb-bootstrap-context.py"')

sys.path.insert(0, HERE)
from test_neb_root import BASH  # noqa: E402 — bash como lo resuelve Claude Code (Git Bash en Windows)


def _load():
    with open(HOOKS_JSON, encoding="utf-8") as f:
        return json.load(f)["hooks"]


def _optional_entries(hooks):
    """[(evento, matcher, hook_dict)] de las entradas que llaman a neb-hook.py."""
    out = []
    for event, groups in hooks.items():
        for g in groups:
            for h in g["hooks"]:
                if "neb-hook.py" in h.get("command", ""):
                    out.append((event, g.get("matcher"), h))
    return out


class TestEstructura(unittest.TestCase):

    def setUp(self):
        self.hooks = _load()
        self.entries = _optional_entries(self.hooks)

    def test_gate_y_argumento_coinciden(self):
        for event, _, h in self.entries:
            m = GATE_RE.match(h["command"])
            self.assertIsNotNone(m, h["command"])
            self.assertEqual({m.group("gate"), m.group("a1"), m.group("a2")}, {m.group("gate")}, h["command"])
            self.assertEqual(h["type"], "command")
            self.assertNotIn("shell", h)

    def test_mapa_completo_contra_el_dispatcher(self):
        got = {(GATE_RE.match(h["command"]).group("gate"), event) for event, _, h in self.entries}
        want = {(hook, event) for hook, events in nh.HOOKS.items() for event in events}
        self.assertEqual(got, want)

    def test_save_approved_plan_solo_en_exit_plan_mode(self):
        for event, matcher, h in self.entries:
            if event == "PostToolUse":
                self.assertEqual(matcher, "ExitPlanMode")

    def test_timeouts(self):
        want = {"notify-on-stop": 10, "notify-on-permission": 10, "preprocess-prompt": 35}
        for _, _, h in self.entries:
            gate = GATE_RE.match(h["command"]).group("gate")
            self.assertEqual(h.get("timeout"), want.get(gate), gate)

    def test_session_start_sin_cambios(self):
        ss = self.hooks["SessionStart"]
        self.assertEqual([g["matcher"] for g in ss], ["startup", "compact"])
        for g in ss:
            self.assertEqual([h["command"] for h in g["hooks"]], [BOOTSTRAP])


STUB = """import os, sys
data = sys.stdin.buffer.read()
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "calls.txt"), "ab") as f:
    f.write(sys.argv[1].encode() + b"|" + data + b"\\n")
"""


@unittest.skipUnless(BASH, "requiere bash (Git Bash en Windows)")
class TestGateEnShell(unittest.TestCase):
    """El comando de hooks.json tal como lo corre Claude Code: placeholder sustituido (con `/`),
    shell POSIX, JSON por stdin. neb-hook.py es un stub que registra cada llamada."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="neb-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "hooks"))
        with open(os.path.join(self.root, "hooks", "neb-hook.py"), "w", encoding="utf-8") as f:
            f.write(STUB)
        self.cmd = {GATE_RE.match(h["command"]).group("gate"): h["command"]
                    for _, _, h in _optional_entries(_load())}

    def _calls(self):
        try:
            with open(os.path.join(self.root, "calls.txt"), "rb") as f:
                return f.read().decode("utf-8").splitlines()
        except FileNotFoundError:
            return []

    def _run(self, hook, payload, **env):
        command = self.cmd[hook].replace("${CLAUDE_PLUGIN_ROOT}", self.root.replace("\\", "/"))
        e = {k: v for k, v in os.environ.items() if k not in ("NEB_HOOKS", "NEB_PROJECT_HOOKS")}
        e.update(env)
        r = subprocess.run([BASH, "-c", command], input=payload.encode("utf-8"), env=e,
                           capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_activado_por_usuario(self):
        self._run("logbook-sync", '{"a": "ñ→"}', NEB_HOOKS="notify-on-stop,logbook-sync")
        self.assertEqual(self._calls(), ['logbook-sync|{"a": "ñ→"}'])

    def test_activado_por_proyecto(self):
        self._run("usage-tracker", "{}", NEB_HOOKS="notify-on-stop", NEB_PROJECT_HOOKS="usage-tracker")
        self.assertEqual(self._calls(), ["usage-tracker|{}"])

    def test_apagado(self):
        self._run("logbook-sync", "{}")
        self._run("logbook-sync", "{}", NEB_HOOKS="", NEB_PROJECT_HOOKS="")
        self.assertEqual(self._calls(), [])

    def test_sin_falsos_positivos(self):
        self._run("notify-on-stop", "{}", NEB_HOOKS="notify,notify-on-stop-x,on-stop")
        self._run("logbook-sync", "{}", NEB_HOOKS="logbook-sync ", NEB_PROJECT_HOOKS=" logbook-sync")
        self.assertEqual(self._calls(), [])


if __name__ == "__main__":
    unittest.main()
