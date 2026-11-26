#!/usr/bin/env python3
"""
test_setup_workspace.py — `_is_workspace` de bootstrap/setup-workspace.sh (7.0.1).

  • un dir con corchetes (p. ej. un usuario dev[1]) es ruta, no patrón: x[1] no debe leerse como x1, ni
    para dar por workspace un dir que no lo es ni para no ver el marker propio.

Corre solo la función, extraída del script: nunca el script entero (escribe variables de entorno).
Temporales; nunca ~/.claude ni el registro.
  py -m unittest discover -s hooks/tests -p test_setup_workspace.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import _entorno  # noqa: E402,F401 — quita NEB_DATA: la carpeta de datos es la del home temporal

from test_neb_root import BASH  # noqa: E402 — bash como lo resuelve Claude Code (Git Bash en Windows)

SCRIPT = os.path.join(NEB, "bootstrap", "setup-workspace.sh")
MARKER = os.path.join("ws", "overlays", "detect-profile.local.sh")


def is_workspace_fn():
    with open(SCRIPT, encoding="utf-8") as fh:
        m = re.search(r"^_is_workspace\(\) \{\n.*?^\}\n", fh.read(), re.S | re.M)
    assert m, "no se encontró _is_workspace en setup-workspace.sh"
    return m.group(0)


@unittest.skipUnless(BASH, "sin bash")
class TestIsWorkspaceConCorchetes(unittest.TestCase):

    def setUp(self):
        base = tempfile.mkdtemp(prefix="neb-test-ws-")
        self.addCleanup(shutil.rmtree, base, True)
        self.own, self.decoy = os.path.join(base, "x[1]"), os.path.join(base, "x1")
        os.makedirs(self.own)
        self.plant(self.decoy)
        self.env = dict(os.environ, HOME=base, USERPROFILE=base)

    @staticmethod
    def plant(root):
        path = os.path.join(root, MARKER)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("")

    def rc(self, d):
        # La ruta va por el entorno: en Windows, el runtime de MSYS expande los comodines de los argumentos
        # que recibe bash.exe de un proceso que no es MSYS, y x[1] llegaría ya convertido en x1.
        script = is_workspace_fn() + '_is_workspace "$NEB_TEST_DIR"\n'
        env = dict(self.env, NEB_TEST_DIR=d.replace("\\", "/"))
        return subprocess.run([BASH, "-c", script], env=env, capture_output=True, timeout=30).returncode

    def test_no_toma_el_marker_de_otra_carpeta(self):
        self.assertEqual(self.rc(self.own), 1)

    def test_ve_el_marker_propio(self):
        shutil.rmtree(self.decoy)               # sin señuelo: leída como patrón, x[1] no ve la carpeta x[1]
        self.plant(self.own)
        self.assertEqual(self.rc(self.own), 0)


if __name__ == "__main__":
    unittest.main()
