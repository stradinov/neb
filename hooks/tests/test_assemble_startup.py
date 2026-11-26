#!/usr/bin/env python3
"""test_assemble_startup.py — enlaces del arranque (bootstrap/assemble-startup.py y su uso en el hook).

  • assemble sin rel_root: enlaces relativos a .md reescritos a paths absolutos (comportamiento de siempre)
  • assemble con rel_root: relativos a la raíz, también desde un archivo importado de otra carpeta; conserva
    el ancla; un destino fuera de la raíz conserva su path absoluto; URLs, anclas y no-.md no se tocan
  • CLI: --relative-to <raíz>; sin valor, uso y exit 1
  • el hook (neb-bootstrap-context.py): el núcleo sale con enlaces relativos y la intro anuncia la raíz con un
    ejemplo de ruta completa; el overlay del adoptante conserva enlaces absolutos (supuesto R34)

Framework: unittest (stdlib). Árboles temporales, sin NEB_DATA (_entorno).
  py -m unittest discover -s hooks/tests -p test_assemble_startup.py
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sin_registro  # noqa: E402,F401 — sin el registro real de Windows
import _entorno  # noqa: E402,F401 — quita NEB_DATA: la carpeta de datos es la del home temporal

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
ASM = os.path.join(NEB, "bootstrap", "assemble-startup.py")
HOOK = os.path.join(NEB, "bootstrap", "neb-bootstrap-context.py")

_spec = importlib.util.spec_from_file_location("neb_assemble_startup_t", ASM)
asm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(asm)

CLEAN = ("NEB_HOME", "CLAUDE_PLUGIN_ROOT", "NEB_WORKSPACE", "NEB_HOOKS", "NEB_PROJECT_HOOKS",
         "NEB_INTERNAL_SUBSESSION", "CLAUDE_PREPROCESS_RECURSION", "CLAUDE_PROJECT_DIR",
         "CLAUDE_CODE_PLUGIN_CACHE_DIR")


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _posix(*parts):
    return os.path.normpath(os.path.join(*parts)).replace("\\", "/")


class _Arbol(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="neb-test-asm-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "neb")
        self.startup = os.path.join(self.root, "general", "startup.md")
        _write(self.startup,
               "# Arranque\n\n@communication.md\n@../process/fases.md\n")
        _write(os.path.join(self.root, "general", "communication.md"),
               "Ver [correo](correspondence.md) § \"Idioma\" y [gate](../process/gate.md#piso).\n"
               "Fuera: [otro](../../afuera/nota.md). Web: [g](https://example.com/a.md). Ancla: [a](#aqui). "
               "Imagen: [i](logo.png).\n")
        _write(os.path.join(self.root, "process", "fases.md"),
               "Detalle en [ejecución](execution.md) y [inicio](../general/startup.md).\n")


class TestEnsamblador(_Arbol):
    def test_sin_raiz_los_enlaces_salen_absolutos(self):
        out = asm.assemble(self.startup, 0, frozenset())
        self.assertIn("[correo](%s)" % _posix(self.root, "general", "correspondence.md"), out)
        self.assertIn("[gate](%s#piso)" % _posix(self.root, "process", "gate.md"), out)
        self.assertIn("[ejecución](%s)" % _posix(self.root, "process", "execution.md"), out)

    def test_con_raiz_los_enlaces_salen_relativos_a_ella(self):
        out = asm.assemble(self.startup, 0, frozenset(), self.root)
        self.assertIn("[correo](general/correspondence.md)", out)
        self.assertIn("[gate](process/gate.md#piso)", out)
        # Desde un archivo importado de otra carpeta, relativo a la raíz y no al archivo.
        self.assertIn("[ejecución](process/execution.md)", out)
        self.assertIn("[inicio](general/startup.md)", out)
        self.assertNotIn(self.root.replace("\\", "/"), out)

    def test_fuera_de_la_raiz_conserva_el_path_absoluto(self):
        out = asm.assemble(self.startup, 0, frozenset(), self.root)
        self.assertIn("[otro](%s)" % _posix(self.tmp, "afuera", "nota.md"), out)

    def test_urls_anclas_y_otros_archivos_no_se_tocan(self):
        for raiz in (None, self.root):
            out = asm.assemble(self.startup, 0, frozenset(), raiz)
            self.assertIn("[g](https://example.com/a.md)", out)
            self.assertIn("[a](#aqui)", out)
            self.assertIn("[i](logo.png)", out)

    def test_cli_relative_to(self):
        r = subprocess.run([sys.executable, ASM, "--relative-to", self.root, self.startup],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[correo](general/correspondence.md)", r.stdout)
        r = subprocess.run([sys.executable, ASM, self.startup], capture_output=True, text=True, encoding="utf-8")
        self.assertIn("[correo](%s)" % _posix(self.root, "general", "correspondence.md"), r.stdout)

    def test_cli_relative_to_sin_valor_es_uso(self):
        r = subprocess.run([sys.executable, ASM, "--relative-to"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Uso:", r.stderr)


class TestHook(_Arbol):
    """El hook real sobre un núcleo y un overlay mínimos."""

    def _out(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in CLEAN}
        home = tempfile.mkdtemp(prefix="neb-test-home-")
        self.addCleanup(shutil.rmtree, home, True)
        env.update({"HOME": home, "USERPROFILE": home, "NEB_HOME": self.root, "PYTHONIOENCODING": "utf-8"})
        env.update(extra)
        r = subprocess.run([sys.executable, HOOK], capture_output=True, env=env, cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        return r.stdout.decode("utf-8")

    def test_el_nucleo_sale_relativo_y_la_intro_anuncia_la_raiz(self):
        out = self._out()
        self.assertIn("[correo](general/correspondence.md)", out)
        self.assertIn("[ejecución](process/execution.md)", out)
        intro = out.split("# Arranque\n", 1)[0]
        self.assertIn("NEB_HOME (`%s`)" % self.root, intro)
        self.assertIn("relativos a esa raíz", intro)
        self.assertIn("`%s`" % os.path.join(self.root, "process", "delivery.md"), intro)
        # La raíz solo va en la intro: ningún enlace del núcleo la repite.
        self.assertNotIn("](%s/" % self.root.replace("\\", "/"), out)

    def test_el_overlay_conserva_enlaces_absolutos(self):
        ws = os.path.join(self.tmp, "ws")
        ov = os.path.join(ws, "acme")
        _write(os.path.join(ov, "overlays", "detect-profile.local.sh"), "")
        _write(os.path.join(ov, "startup.md"), "Lee [addendum](process/vc.local.md) antes de integrar.\n")
        out = self._out(NEB_WORKSPACE=ws)
        self.assertIn("[addendum](%s)" % _posix(ov, "process", "vc.local.md"), out)
        self.assertIn("[correo](general/correspondence.md)", out)


if __name__ == "__main__":
    unittest.main()
