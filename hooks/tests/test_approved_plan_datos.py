#!/usr/bin/env python3
"""test_approved_plan_datos.py — lugar de caída de los planes aprobados en la carpeta de datos (8.0.0).

Cubre hooks/lib/approved_plan.py y hooks/save-approved-plan.sh:
  • approved_plan.save escribe en <datos>/approved-plans/ (~/.neb sin NEB_DATA; NEB_DATA absoluta si la hay),
    nunca en ~/.claude/approved-plans/, y crea la carpeta.
  • una carpeta de datos que es enlace (symlink o junction) no se escribe: ValueError, que el dispatcher
    deja en stderr y sale 0.
  • el .sh (entrada de settings con clon) resuelve la misma ruta vía neb_paths; sin bash o jq se salta.

El slug, el encabezado y el extremo a extremo del dispatcher viven en test_neb_hook.py.

Framework: unittest (stdlib). HOME temporal; _entorno quita NEB_DATA: nunca toca ~/.claude ni ~/.neb reales.
  py -m unittest discover -s hooks/tests -p test_approved_plan_datos.py
"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from datetime import datetime
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HOOKS_DIR, "lib"))

import _entorno  # noqa: E402
import approved_plan  # noqa: E402
from test_neb_root import BASH  # noqa: E402 — bash como lo resuelve Claude Code (Git Bash en Windows)

EVENT = {"session_id": "sid-1", "cwd": "/w/demo", "tool_input": {"plan": "# Plan de prueba\n\nPaso 1"}}
NOW = datetime(2026, 11, 25, 9, 30, 0)
NAME = "20261125-093000-demo-plan-de-prueba.md"


def _link_dir(target, link):
    """Enlace de carpeta: symlink o, en Windows sin ese privilegio, junction. False si no se pudo."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    try:
        import _winapi
        _winapi.CreateJunction(target, link)
        return True
    except (ImportError, AttributeError, OSError):
        return False


class TestSaveEnCarpetaDeDatos(unittest.TestCase):

    def setUp(self):
        self.home = _entorno.home_temporal(self)

    def test_save_va_a_la_carpeta_de_datos(self):
        path = approved_plan.save(EVENT, self.home, now=NOW)
        self.assertEqual(path, os.path.join(self.home, ".neb", "approved-plans", NAME))
        self.assertTrue(os.path.isfile(path))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude")))

    def test_save_respeta_neb_data_absoluta(self):
        datos = os.path.join(self.home, "otra", "datos")
        with mock.patch.dict(os.environ, {"NEB_DATA": datos}):
            path = approved_plan.save(EVENT, self.home, now=NOW)
        self.assertEqual(path, os.path.join(datos, "approved-plans", NAME))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".neb")))

    def test_save_rechaza_carpeta_de_datos_enlazada(self):
        # ensure_dir revisa la carpeta final: aquí <datos>/approved-plans es el enlace.
        target = os.path.join(self.home, "destino")
        os.makedirs(target)
        os.makedirs(os.path.join(self.home, ".neb"))
        if not _link_dir(target, os.path.join(self.home, ".neb", "approved-plans")):
            self.skipTest("sin permiso para crear enlaces")
        with self.assertRaises(ValueError):
            approved_plan.save(EVENT, self.home, now=NOW)
        self.assertEqual(os.listdir(target), [])


@unittest.skipUnless(BASH and shutil.which("jq"), "requiere bash (Git Bash en Windows) y jq")
class TestScriptBash(unittest.TestCase):
    """save-approved-plan.sh, la entrada de settings con clon: misma ruta que approved_plan.save."""

    def setUp(self):
        self.home = _entorno.home_temporal(self)

    def _run(self, **extra):
        env = _entorno.env_con_home(self.home, **extra)
        # Barras normales: el bash de Git trata la barra invertida de una ruta de Windows como escape.
        script = os.path.join(HOOKS_DIR, "save-approved-plan.sh").replace("\\", "/")
        return subprocess.run([BASH, script],
                              input=json.dumps(EVENT).encode("utf-8"), env=env, capture_output=True,
                              timeout=60)

    def _planes(self, folder):
        return os.listdir(folder) if os.path.isdir(folder) else []

    def test_sh_va_a_la_carpeta_de_datos(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        files = self._planes(os.path.join(self.home, ".neb", "approved-plans"))
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith("-demo-plan-de-prueba.md"))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude")))

    def test_sh_respeta_neb_data(self):
        datos = os.path.join(self.home, "datos")
        r = self._run(NEB_DATA=datos)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self._planes(os.path.join(datos, "approved-plans"))), 1)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".neb")))


if __name__ == "__main__":
    unittest.main()
