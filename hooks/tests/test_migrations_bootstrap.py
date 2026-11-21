#!/usr/bin/env python3
"""
test_migrations_bootstrap.py — aviso del arranque de base incompatible o paso detenido (6.48.0).

Cubre _db_notice / _env_notices de bootstrap/neb-bootstrap-context.py:
  • sin aviso con la base al día, ni con plugin y clon de versiones distintas si los dos la entienden (M7);
  • aviso por árbol que ya no puede operar la base (el propio y el clon de NEB_HOME, leído como texto;
    un clon sin _migrations.py cuenta como 1);
  • aviso de paso detenido con el motivo del precheck propio;
  • solo lectura: sin base no la crea;
  • dos corridas con el aviso presente dan el mismo texto; un cambio de estado entre corridas, otro;
  • tope DB_NOTICE_MAX.

Homes temporales; nunca ~/.claude.
  py -m unittest discover -s hooks/tests -p test_migrations_bootstrap.py
"""

import contextlib
import importlib.util
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sin_registro  # noqa: E402,F401 — sin el registro real de Windows
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(NEB, "hooks", "lib"))

import _db_shared

_spec = importlib.util.spec_from_file_location("neb_bootstrap_context_mig",
                                               os.path.join(NEB, "bootstrap", "neb-bootstrap-context.py"))
nb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nb)

BOOTSTRAP_DIR = os.path.join(NEB, "bootstrap")


def u16(s):
    return len(s.encode("utf-16-le")) // 2


class TestAvisoBase(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-test-boot-")
        self.addCleanup(shutil.rmtree, self.home, True)
        os.makedirs(os.path.join(self.home, ".claude"))
        self.db = os.path.join(self.home, ".claude", "neb.db")
        self.clone = tempfile.mkdtemp(prefix="neb-test-clon-")
        self.addCleanup(shutil.rmtree, self.clone, True)
        os.makedirs(os.path.join(self.clone, "hooks", "lib"))

    def make_db(self, rows=()):
        with contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(self.db).close()
        con = sqlite3.connect(self.db)
        for step, min_code in rows:
            con.execute("INSERT INTO schema_step VALUES (?, ?, 'prueba', 'x', 'x', NULL)", (step, min_code))
        con.commit()
        con.close()

    def clone_version(self, v):
        with open(os.path.join(self.clone, "hooks", "lib", "_migrations.py"), "w", encoding="utf-8") as fh:
            fh.write("SCHEMA_VERSION = %d\n" % v)

    def notice(self, neb_home=None):
        return nb._db_notice(BOOTSTRAP_DIR, neb_home, home=self.home)

    def test_sin_base_no_avisa_ni_la_crea(self):
        self.assertIsNone(self.notice())
        self.assertFalse(os.path.exists(self.db))

    def test_base_al_dia_sin_aviso(self):
        self.make_db()
        self.clone_version(_db_shared._migrations.SCHEMA_VERSION)
        self.assertIsNone(self.notice(self.clone))

    def test_versiones_distintas_que_entienden_la_base_sin_aviso(self):
        self.make_db([(3, 2)])                        # base más nueva, mínima 2: plugin (2) y clon (2) la operan
        self.clone_version(2)
        self.assertIsNone(self.notice(self.clone))

    def test_aviso_por_cada_arbol_que_no_opera_la_base(self):
        self.make_db([(3, 3)])                        # mínima 3: el propio (2) y un clon sin el archivo (1) no
        n = self.notice(self.clone)
        self.assertIsNotNone(n)
        self.assertIn(NEB, n)
        self.assertIn(self.clone, n)
        self.assertIn("base-incompatible", n)                       # el propio conoce la regla
        self.assertIn("anterior a 6.48.0", n)                       # el clon sin _migrations.py no

    def test_clon_al_dia_no_aparece(self):
        self.make_db([(3, 3)])
        self.clone_version(3)
        n = self.notice(self.clone)
        self.assertIn(NEB, n)
        self.assertNotIn(self.clone, n)

    def test_paso_detenido_con_el_motivo_del_precheck(self):
        self.make_db()
        real = nb._load_module

        def patched(path, name):
            mod = real(path, name)
            if name == "neb_migrations_own":
                mod.STEPS = mod.STEPS + (mod.Step(3, "paso de prueba", lambda c: None, espera=True,
                                                  precheck=lambda c: "vista v_mia"),)
            return mod
        with mock.patch.object(nb, "_load_module", patched):
            n = self.notice()
        self.assertIn("paso de base 3", n)
        self.assertIn("vista v_mia", n)
        self.assertIn("neb-migrate.py", n)

    def test_base_atras_sin_motivo_no_avisa(self):
        self.make_db()
        real = nb._load_module

        def patched(path, name):
            mod = real(path, name)
            if name == "neb_migrations_own":
                mod.STEPS = mod.STEPS + (mod.Step(3, "paso de prueba", lambda c: None),)
            return mod
        with mock.patch.object(nb, "_load_module", patched):
            self.assertIsNone(self.notice())

    def test_mismo_texto_en_dos_corridas_y_otro_si_el_estado_cambia(self):
        self.make_db([(3, 3)])
        with mock.patch.object(os.path, "expanduser", lambda p: self.home if p == "~" else p):
            a = nb._env_notices(BOOTSTRAP_DIR, self.clone)
            b = nb._env_notices(BOOTSTRAP_DIR, self.clone)
            self.assertEqual(a, b)
            self.assertTrue(any("base-incompatible" in x for x in a))
            con = sqlite3.connect(self.db)
            con.execute("INSERT INTO schema_step VALUES (4, 4, 'otro', 'x', 'x', NULL)")
            con.commit()
            con.close()
            c = nb._env_notices(BOOTSTRAP_DIR, self.clone)
        self.assertNotEqual(a, c)

    def test_tope_del_aviso(self):
        self.make_db([(3, 3)])
        largo = os.path.join(self.clone, *(["x" * 200] * 4))   # no se crea: un árbol ausente cuenta como 1
        n = self.notice(largo)
        self.assertIn("…", n)
        self.assertLessEqual(u16(nb.ENV_NOTICE % n), nb.DB_NOTICE_MAX)

    def test_arbol_sin_migrations_no_rompe_el_arranque(self):
        viejo = tempfile.mkdtemp(prefix="neb-test-viejo-")
        self.addCleanup(shutil.rmtree, viejo, True)
        os.makedirs(os.path.join(viejo, "bootstrap"))
        self.make_db([(3, 3)])
        self.assertIsNone(nb._db_notice(os.path.join(viejo, "bootstrap"), None, home=self.home))


if __name__ == "__main__":
    unittest.main()
