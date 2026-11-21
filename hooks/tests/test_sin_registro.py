# -*- coding: utf-8 -*-
"""El sustituto de winreg de las pruebas (_sin_registro.py) llega a este proceso y a sus subprocesos, y el oráculo
reprueba sin él: si se pierde el PYTHONPATH o el sitecustomize, una prueba consultaría el registro real de Windows."""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sin_registro  # noqa: E402,F401

PROBE = ("import sys, winreg; "
         "sys.exit(0 if getattr(winreg.OpenKey, '__module__', '') == '_sin_registro' else 3)")


class TestSinRegistro(unittest.TestCase):

    def test_en_este_proceso(self):
        import winreg
        self.assertEqual(winreg.OpenKey.__module__, "_sin_registro")

    def test_critico_en_un_subproceso(self):
        r = subprocess.run([sys.executable, "-c", PROBE], env=dict(os.environ), timeout=60)
        self.assertEqual(r.returncode, 0)

    @unittest.skipUnless(sys.platform == "win32", "winreg real solo en Windows")
    def test_el_oraculo_reprueba_sin_el_sustituto(self):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        r = subprocess.run([sys.executable, "-c", PROBE], env=env, timeout=60)
        self.assertEqual(r.returncode, 3)


if __name__ == "__main__":
    unittest.main()
