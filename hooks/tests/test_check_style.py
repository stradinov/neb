#!/usr/bin/env python3
"""test_check_style.py — linter de forma única (bootstrap/check-style.py).

  • cada regla (V1, V2, V3, C1, C2) dispara con su forma vetada y calla con la canónica
  • los bloques cercados y el código en línea no cuentan (así se documenta una forma vetada)
  • exclusiones: CHANGELOG.md, changelog.d/, research fechado y directorios ocultos
  • salida y códigos de retorno: 0 limpio, 1 con hallazgos, 2 raíz inexistente
  • el repo real sale limpio

Framework: unittest (stdlib). Árboles temporales; del repo real solo lee.
  py -m unittest discover -s hooks/tests -p test_check_style.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
SCRIPT = os.path.join(NEB, "bootstrap", "check-style.py")


class CheckStyleTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="neb-style-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def run_lint(self, root=None):
        r = subprocess.run([sys.executable, SCRIPT, "--root", root or self.root], capture_output=True)
        out = r.stdout.decode("utf-8")
        return r.returncode, [l.split("\t") for l in out.splitlines()], r.stderr.decode("utf-8")

    def rules(self, text, rel="a.md"):
        self.write(rel, text)
        rc, rows, _ = self.run_lint()
        return rc, [row[1] for row in rows]

    # ── reglas ────────────────────────────────────────────────────────────────
    def test_cada_regla_dispara_con_su_forma_vetada(self):
        cases = (
            ("V1", "El change MD registra el REQ.\n"),
            ("V1", "Dos change MDs.\n"),
            ("V2", "El gate de F4 corre antes.\n"),
            ("V2", "Revisores en F3/F4.\n"),
            ("V3", "Es la single source of truth.\n"),
            ("V3", "Es la Single Source Of Truth.\n"),
            ("C1", 'Ver §"Contexto".\n'),
            ("C1", "Ver § Contexto.\n"),
            ("C1", "Ver §Contexto.\n"),
            ("C1", "Ver § 5.\n"),
            ("C1", "Ver § «Contexto».\n"),
            ("C2", 'Ver [plan](plan.md) "Contexto".\n'),
            ("C2", "Ver [plan](plan.md) «Contexto».\n"),
        )
        for rule, text in cases:
            with self.subTest(text=text):
                rc, found = self.rules(text)
                self.assertEqual(rc, 1)
                self.assertIn(rule, found)

    def test_la_forma_canonica_no_dispara(self):
        text = ('El Change MD registra el REQ en Fase 4; `vocabulary.md` es la fuente única.\n'
                'Ver [plan](plan.md) § "Contexto" y § "Alcance". Una «§» sin archivo cita al propio.\n'
                'La tabla [§ "Estados"](#estados) y el enlace [con título](plan.md "título") pasan.\n'
                "Un exchange MD5 no es una variante, ni PDF1 ni F10 ni v1.F2.\n")
        rc, found = self.rules(text)
        self.assertEqual((rc, found), (0, []))

    def test_dos_formas_en_la_misma_linea_dan_dos_hallazgos(self):
        self.write("a.md", "El change MD en F4, ver § Contexto.\n")
        rc, rows, _ = self.run_lint()
        self.assertEqual(rc, 1)
        self.assertEqual(sorted(r[1] for r in rows), ["C1", "V1", "V2"])
        self.assertEqual({r[0] for r in rows}, {"a.md:1"})
        self.assertEqual({r[1]: r[3] for r in rows}["V1"], "Change MD")

    # ── código y bloques cercados ─────────────────────────────────────────────
    def test_codigo_en_linea_y_bloques_cercados_no_cuentan(self):
        text = ("Vetadas: `change MD`, `F4`, `single source of truth`, `§ X`; la tecla `F5` recarga.\n"
                "```\nchange MD, F4, § X, [t](a.md) \"X\"\n```\n"
                "~~~\nsingle source of truth\n~~~\n")
        rc, found = self.rules(text)
        self.assertEqual((rc, found), (0, []))

    def test_tras_cerrar_el_bloque_vuelve_a_contar(self):
        rc, found = self.rules("```\nchange MD\n```\nEl change MD.\n")
        self.assertEqual((rc, found), (1, ["V1"]))

    # ── alcance ───────────────────────────────────────────────────────────────
    def test_exclusiones(self):
        bad = "El change MD.\n"
        for rel in ("CHANGELOG.md", "changelog.d/1.0.0.md", "research/2026-01-02-tema.md",
                    ".claude/personal.md", "personal/dev.md", "notas.txt", "node_modules/x/README.md"):
            self.write(rel, bad)
        rc, rows, _ = self.run_lint()
        self.assertEqual((rc, rows), (0, []))

    def test_incluye_plantillas_research_readme_y_subcarpetas(self):
        bad = "El change MD.\n"
        for rel in ("templates/change.md.template", "research/README.md", "process/sub/x.md",
                    "docs/CHANGELOG.md"):
            self.write(rel, bad)
        rc, rows, err = self.run_lint()
        self.assertEqual(rc, 1)
        self.assertEqual(sorted(r[0] for r in rows),
                         ["docs/CHANGELOG.md:1", "process/sub/x.md:1", "research/README.md:1",
                          "templates/change.md.template:1"])
        self.assertIn("hallazgos: 4", err)

    def test_raiz_inexistente_es_error_de_uso(self):
        rc, _, err = self.run_lint(os.path.join(self.root, "no-existe"))
        self.assertEqual(rc, 2)
        self.assertIn("no es un directorio", err)

    def test_archivo_no_utf8_se_reporta(self):
        p = os.path.join(self.root, "a.md")
        with open(p, "wb") as f:
            f.write(b"caf\xe9\n")
        rc, rows, _ = self.run_lint()
        self.assertEqual(rc, 1)
        self.assertEqual(rows[0][1], "utf8")

    # ── el repo real ──────────────────────────────────────────────────────────
    def test_el_repo_real_sale_limpio(self):
        rc, rows, err = self.run_lint(NEB)
        self.assertEqual(rc, 0, "\n".join("\t".join(r) for r in rows[:20]) + "\n" + err)


if __name__ == "__main__":
    unittest.main()
