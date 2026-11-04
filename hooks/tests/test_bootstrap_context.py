#!/usr/bin/env python3
"""test_bootstrap_context.py — el arranque en partes (bootstrap/neb-bootstrap-context.py, PD-742).

La plataforma topa cada salida de hook en 10,000 caracteres (supuesto R1); el arranque sale en partes de
LIMIT unidades UTF-16 o menos, una por entrada de hooks/hooks.json:
  • split_parts: sin pérdida, cada parte con su cabecera dentro de LIMIT, sin cortar un bloque de código,
    corte duro de una línea larga, caracteres fuera del BMP, desbordamiento con lugar para el aviso
  • el script como lo corre el hook: --part k reconstruye la salida completa con la misma huella y sin CR;
    parte fuera de rango, `neb: skip` y la subsesión interna no emiten nada; el aviso va en la última
  • --check-size (gate 6 del pre-push): pasa sobre el repo y falla con un núcleo inflado
  • main() dentro del proceso, con un stdout sin `.buffer`

Framework: unittest (stdlib). Árboles y workspaces temporales; nunca toca ~/.claude.
  py -m unittest discover -s hooks/tests -p test_bootstrap_context.py
"""
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
SCRIPT = os.path.join(NEB, "bootstrap", "neb-bootstrap-context.py")

_spec = importlib.util.spec_from_file_location("neb_bootstrap_context", SCRIPT)
nb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nb)

HEADER_RE = re.compile(r"^# Arranque de Neb — parte (\d+) de (\d+) · huella ([0-9a-f]{8})\n\n")
CLEAN = ("NEB_HOME", "CLAUDE_PLUGIN_ROOT", "NEB_WORKSPACE", "NEB_HOOKS", "NEB_PROJECT_HOOKS",
         "NEB_INTERNAL_SUBSESSION", "CLAUDE_PREPROCESS_RECURSION", "CLAUDE_PROJECT_DIR")


def u16(s):
    return len(s.encode("utf-16-le")) // 2


def seccion(titulo, subsecciones, largo):
    parrafo = ("Relleno con acentos: canción, año, pingüino. " * (largo // 40 + 1))[:largo]
    return "# %s\n\n" % titulo + "".join("## Sub %d\n\n%s\n\n" % (i, parrafo) for i in range(subsecciones))


class TestSplit(unittest.TestCase):

    def assertPartes(self, text, parts, rest=""):
        self.assertEqual("".join(parts) + rest, text)
        header = u16(nb.HEADER % (99, 99, "f" * 8))
        for p in parts:
            self.assertLessEqual(header + u16(p), nb.LIMIT)

    def test_sin_perdida_y_dentro_del_limite(self):
        text = "".join(seccion("S%d" % i, 5, 1500) for i in range(6))
        parts, rest = nb.split_parts(text)
        self.assertEqual(rest, "")
        self.assertGreater(len(parts), 1)
        self.assertPartes(text, parts)

    def test_corta_en_secciones_cuando_caben(self):
        text = "".join(seccion("S%d" % i, 2, 1500) for i in range(8))
        parts, _ = nb.split_parts(text)
        for p in parts:
            self.assertTrue(p.startswith("# S"), p[:20])

    def test_no_corta_dentro_de_un_bloque_de_codigo(self):
        codigo = "```bash\n" + "".join("# comentario %d\necho %d\n" % (i, i) for i in range(120)) + "```\n"
        text = seccion("A", 3, 2000) + codigo + "\n" + seccion("B", 3, 2000)
        start = text.index("```bash")
        end = text.index("```\n", start + 3) + 4
        parts, _ = nb.split_parts(text)
        self.assertPartes(text, parts)
        pos = 0
        for p in parts[:-1]:
            pos += len(p)
            self.assertFalse(start < pos < end, "corte dentro del bloque de código en %d" % pos)

    def test_corte_duro_de_una_linea_larga(self):
        text = "# Larga\n\n" + "a" * 25000 + "\n"
        parts, _ = nb.split_parts(text)
        self.assertGreaterEqual(len(parts), 3)
        self.assertPartes(text, parts)

    def test_fuera_del_bmp_cuenta_doble(self):
        text = "# Emoji\n\n" + "\U0001F6A8" * 6000 + "\n"
        self.assertEqual(u16("\U0001F6A8"), 2)
        parts, _ = nb.split_parts(text)
        self.assertGreaterEqual(len(parts), 2)
        self.assertPartes(text, parts)

    def test_desbordamiento_deja_lugar_al_aviso(self):
        text = "".join("# S%d\n\n%s\n\n" % (i, "x" * 8000) for i in range(15))
        parts, rest = nb.split_parts(text)
        self.assertEqual(len(parts), nb.MAX_PARTS)
        self.assertTrue(rest)
        self.assertPartes(text, parts, rest)
        self.assertLessEqual(u16(parts[-1]), nb._body_budget() - nb.NOTICE_RESERVE)


class TestPartesDelArranque(unittest.TestCase):
    """El script como lo corre cada entrada de hooks/hooks.json."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _run(self, *args, **env):
        e = {k: v for k, v in os.environ.items() if k not in CLEAN}
        e["NEB_HOME"] = NEB
        e.update(env)
        r = subprocess.run([sys.executable, SCRIPT] + [str(a) for a in args], env=e,
                           capture_output=True, timeout=60)
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8")

    def _out(self, *args, **env):
        rc, out, err = self._run(*args, **env)
        self.assertEqual(rc, 0, err)
        return out

    def _partes(self, **env):
        return [self._out("--part", k, **env) for k in range(1, nb.MAX_PARTS + 1)]

    def test_las_partes_reconstruyen_el_arranque(self):
        full = self._out()
        outs = self._partes()
        llenas = [o for o in outs if o]
        self.assertTrue(all(outs[:len(llenas)]), "las partes con contenido van primero")
        self.assertGreater(len(llenas), 1)
        cuerpos, n, huellas = [], set(), set()
        for k, o in enumerate(llenas, 1):
            m = HEADER_RE.match(o)
            self.assertIsNotNone(m, o[:80])
            self.assertEqual(int(m.group(1)), k)
            n.add(int(m.group(2)))
            huellas.add(m.group(3))
            self.assertNotIn("\r", o)
            self.assertLessEqual(u16(o), nb.LIMIT)
            cuerpos.append(o[m.end():])
        self.assertEqual(n, {len(llenas)})
        self.assertEqual(huellas, {nb.fingerprint(full)})
        self.assertEqual("".join(cuerpos), full)

    def test_parte_fuera_de_rango_no_emite(self):
        for arg in (nb.MAX_PARTS + 1, 0, "x"):
            self.assertEqual(self._out("--part", arg), "")

    def test_neb_skip_y_subsesion_no_emiten(self):
        with open(os.path.join(self.tmp, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# Proyecto\n\n<!-- neb: skip -->\n")
        self.assertEqual(self._partes(CLAUDE_PROJECT_DIR=self.tmp), [""] * nb.MAX_PARTS)
        self.assertEqual(self._out("--part", 1, NEB_INTERNAL_SUBSESSION="1"), "")

    def test_desbordamiento_avisa_en_la_ultima(self):
        ov = os.path.join(self.tmp, "ws", "ov")
        os.makedirs(os.path.join(ov, "overlays"))
        open(os.path.join(ov, "overlays", "detect-profile.local.sh"), "w").close()
        with open(os.path.join(ov, "startup.md"), "w", encoding="utf-8") as f:
            f.write("".join("# Extensión %d\n\n%s\n\n" % (i, "y" * 8000) for i in range(15)))
        ws = os.path.join(self.tmp, "ws")
        ultima = self._out("--part", nb.MAX_PARTS, NEB_WORKSPACE=ws)
        self.assertIn("**Aviso de Neb (entorno):** el arranque no cupo en %d partes" % nb.MAX_PARTS, ultima)
        self.assertIn("overlay del adoptante", ultima)
        self.assertLessEqual(u16(ultima), nb.LIMIT)
        self.assertEqual(self._out("--part", nb.MAX_PARTS + 1, NEB_WORKSPACE=ws), "")

    def test_check_size_pasa_sobre_el_repo(self):
        rc, out, err = self._run("--check-size", "--root", NEB)
        self.assertEqual(rc, 0, err)
        self.assertIn("arranque del núcleo", out)

    def test_check_size_falla_con_un_nucleo_inflado(self):
        os.makedirs(os.path.join(self.tmp, "general"))
        with open(os.path.join(self.tmp, "general", "startup.md"), "w", encoding="utf-8") as f:
            f.write("# Arranque\n\n" + "".join(seccion("S%d" % i, 4, 2000) for i in range(10)))
        rc, _, err = self._run("--check-size", "--root", self.tmp)
        self.assertEqual(rc, 1)
        self.assertIn("tope %d de %d" % (nb.NUCLEUS_MAX_PARTS, nb.MAX_PARTS), err)

    def test_check_size_sin_raiz_falla(self):
        rc, _, err = self._run("--check-size")
        self.assertEqual(rc, 1)
        self.assertIn("uso:", err)


class TestMainEnProceso(unittest.TestCase):
    """test_subsession.py llama a main() con un io.StringIO, que no tiene `.buffer`."""

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in CLEAN}
        for k in CLEAN:
            os.environ.pop(k, None)
        os.environ["NEB_HOME"] = NEB

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _main(self, argv=None):
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            nb.main(argv)
        finally:
            sys.stdout = old
        return buf.getvalue()

    def test_sin_argumentos_y_con_parte(self):
        self.assertIn("Arranque de Neb (inyectado por el plugin)", self._main())
        self.assertIsNotNone(HEADER_RE.match(self._main(["--part", "1"])))


if __name__ == "__main__":
    unittest.main()
