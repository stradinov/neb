#!/usr/bin/env python3
"""test_check_references.py — archivo de una cita de sección (bootstrap/check-references.py).

  • la ruta .md suelta justo después de un paréntesis de apertura se atribuye a la cita
  • el título se busca en el archivo atribuido: si falta, el roto nombra ese archivo
  • una ruta no localizable sale como aviso y no cuenta
  • una «§» a la que nada le atribuye archivo se verifica contra el propio archivo
  • el enlace y la ruta en código en línea, dentro de un paréntesis, se atribuyen igual que antes

Framework: unittest (stdlib). Un repo git temporal por clase, con una copia del script en
bootstrap/ que hace de raíz de neb; del repo real solo lee el script.
  py -m unittest discover -s hooks/tests -p test_check_references.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
SCRIPT = os.path.join(NEB, "bootstrap", "check-references.py")

FILES = {
    "a.md": "# A\n\n## Propio\n",
    "b.md": "# B\n\n## Destino\n",
    "sub/c.md": "# C\n\n## Tema\n",
}


class CheckReferencesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="neb-refs-")
        os.makedirs(os.path.join(cls.root, "bootstrap"))
        cls.script = os.path.join(cls.root, "bootstrap", "check-references.py")
        shutil.copy(SCRIPT, cls.script)
        for rel, text in FILES.items():
            cls.write(rel, text)
        subprocess.run(["git", "init", "-q", cls.root], check=True, capture_output=True)
        subprocess.run(["git", "-C", cls.root, "add", "-A"], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def write(cls, rel, text):
        p = os.path.join(cls.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def check(self, line):
        """Pone <line> al final de a.md y devuelve (rc, filas de a.md sin su posición)."""
        self.write("a.md", FILES["a.md"] + "\n" + line + "\n")
        r = subprocess.run([sys.executable, self.script, "--no-overlay"], capture_output=True)
        rows = [l.split("\t") for l in r.stdout.decode("utf-8").splitlines()]
        return r.returncode, [row[1:] for row in rows if row[0].startswith("neb:a.md:")]

    # ── ruta suelta tras un paréntesis de apertura ────────────────────────────
    def test_ruta_tras_parentesis_se_atribuye(self):
        cases = (
            'Ver el mapa (b.md § "Destino") antes de editar.',
            'Ver el mapa (sub/c.md § "Tema") antes de editar.',
            'Ver el mapa (b.md) § "Destino" antes de editar.',
            'Ver el mapa (b.md, § "Destino") antes de editar.',
        )
        for line in cases:
            with self.subTest(line=line):
                self.assertEqual(self.check(line), (0, []))

    def test_titulo_ausente_sale_roto_contra_el_archivo_nombrado(self):
        cases = (
            ('Ver el mapa (b.md § "No existe") antes de editar.', "No existe"),
            ('Ver el mapa (b.md) § "Propio" antes de editar.', "Propio"),
        )
        for line, title in cases:
            with self.subTest(line=line):
                self.assertEqual(self.check(line), (1, [["seccion", "b.md", title]]))

    def test_ruta_no_localizable_tras_parentesis_es_aviso(self):
        rc, rows = self.check('Ver el mapa (otro/falta.md § "Tema") antes de editar.')
        self.assertEqual((rc, rows), (0, [["aviso", "otro/falta.md", "Tema"]]))

    # ── sin falsos positivos ──────────────────────────────────────────────────
    def test_cita_sin_archivo_atribuido_va_contra_el_propio_archivo(self):
        self.assertEqual(self.check('El detalle (ver b.md) está más abajo, en § "Propio".'), (0, []))
        cases = (
            'El detalle (ver b.md) está más abajo, en § "Destino".',
            'Cumple § "Destino", «con un inciso», de [b](b.md).',
            'Cumple § "Destino" (b.md).',
        )
        for line in cases:
            with self.subTest(line=line):
                rc, rows = self.check(line)
                self.assertEqual((rc, len(rows), rows[0][0], rows[0][2]), (1, 1, "seccion", "Destino"))
                self.assertTrue(rows[0][1].startswith("(mismo archivo)"))

    def test_enlace_y_codigo_en_linea_tras_parentesis_no_cambian(self):
        cases = (
            'Ver el mapa ([b](b.md) § "Destino") antes de editar.',
            'Ver el mapa (`b.md` § "Destino") antes de editar.',
            'Ver el mapa ([b](b.md)) y, aparte, § "Propio".',
        )
        for line in cases:
            with self.subTest(line=line):
                self.assertEqual(self.check(line), (0, []))
        rc, rows = self.check('Ver el mapa ([b](b.md) § "No existe") antes de editar.')
        self.assertEqual((rc, rows), (1, [["seccion", "b.md", "No existe"]]))

    def test_enlace_roto_seguido_de_cita_da_un_solo_roto(self):
        rc, rows = self.check('Ver [b](falta.md) § "Destino" antes de editar.')
        self.assertEqual((rc, rows), (1, [["enlace", "falta.md", ""]]))


if __name__ == "__main__":
    unittest.main()
