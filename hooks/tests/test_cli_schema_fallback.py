#!/usr/bin/env python3
"""test_cli_schema_fallback.py — CLI de pendings y logbook sin NEB_HOME (6.14.3).

Con solo el plugin, NEB_HOME no existe: `_db_for_cli` toma el esquema del árbol del propio módulo,
que es el de su misma versión. Antes caía a ~/.claude/neb, que bajo el plugin no existe, y con una
base nueva el CLI fallaba con «no such table».

Framework: unittest (stdlib). Home temporal; nunca toca ~/.claude.
  py -m unittest discover -s hooks/tests -p test_cli_schema_fallback.py
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import logbook
import pendings


def _tables(con):
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


class TestCliSchemaSinNebHome(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        os.makedirs(os.path.join(self.home, ".claude"))
        env = {k: v for k, v in os.environ.items() if k != "NEB_HOME"}
        env.update(HOME=self.home, USERPROFILE=self.home)   # expanduser: HOME (POSIX) / USERPROFILE (Windows)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _assert_schema(self, mod, table):
        con = mod._db_for_cli()
        self.assertIsNotNone(con)
        try:
            self.assertIn(table, _tables(con))
        finally:
            con.close()

    def test_pendings_base_nueva_sin_neb_home(self):
        self._assert_schema(pendings, "pending")

    def test_logbook_base_nueva_sin_neb_home(self):
        self._assert_schema(logbook, "work")


class TestEsquemaConElModulo(unittest.TestCase):
    """6.48.0: con NEB_HOME apuntando a otro árbol (con otro esquema), el CLI usa el esquema de su módulo; y
    ante una base incompatible cada verbo responde el JSON base-incompatible (nunca vacío)."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        os.makedirs(os.path.join(self.home, ".claude"))
        self.other = tempfile.mkdtemp(prefix="neb-test-otro-arbol-")
        self.addCleanup(shutil.rmtree, self.other, True)
        os.makedirs(os.path.join(self.other, "hooks"))
        with open(os.path.join(self.other, "hooks", "logbook-schema.sql"), "w", encoding="utf-8") as fh:
            fh.write("CREATE TABLE IF NOT EXISTS tabla_del_otro_arbol (x);\n")
        env = {k: v for k, v in os.environ.items() if not k.startswith("NEB_LOGBOOK_")}
        env.update(HOME=self.home, USERPROFILE=self.home, NEB_HOME=self.other)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cli_usa_el_esquema_de_su_modulo_con_neb_home_ajeno(self):
        for mod, table in ((pendings, "pending"), (logbook, "work")):
            con = mod._db_for_cli()
            try:
                t = _tables(con)
                self.assertIn(table, t)
                self.assertNotIn("tabla_del_otro_arbol", t)
            finally:
                con.close()

    def _mark_incompatible(self):
        con = pendings._db_for_cli()
        con.execute("INSERT INTO schema_step VALUES (9, 9, 'futuro', '9.0.0', 'x', NULL)")
        con.commit()
        con.close()

    def _run(self, fn, argv):
        import contextlib
        import io
        import json
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            fn(argv)
        return json.loads(out.getvalue())

    def test_base_incompatible_responde_json_en_cada_cli(self):
        self._mark_incompatible()
        for fn, argv in ((pendings.cli_main, ["list"]), (pendings.cli_main, ["show", "1"]),
                         (logbook.cli_main, ["list"]), (logbook.cli_main, ["show", "1"]),
                         (logbook.cli_main, ["trace", "x"])):
            r = self._run(fn, argv)
            self.assertEqual(r.get("ok"), False, (argv, r))
            self.assertEqual(r.get("motivo"), "base-incompatible", (argv, r))
            self.assertTrue(r.get("accion"))

    def test_scripts_de_bootstrap_salen_con_1_y_el_motivo(self):
        import subprocess
        self._mark_incompatible()
        db = os.path.join(self.home, ".claude", "neb.db")
        md = os.path.join(self.home, "pendings.md")
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("## alpha\n\n- **alpha-uno** — algo pendiente.\n")
        bak = os.path.join(self.home, "neb.db.bak-pre-taxonomy-x")
        shutil.copy(db, bak)
        boot = os.path.join(HERE, "..", "..", "bootstrap")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        for script, args in (("migrate-pendings-md.py", ["--from", md, "--db", db, "--apply"]),
                             ("seed-pendings-taxonomy.py", ["--db", db, "--rollback", bak])):
            con = sqlite3.connect(db)
            before = con.execute("SELECT count(*) FROM pending").fetchone()[0]
            con.close()
            r = subprocess.run([sys.executable, os.path.join(boot, script)] + args, env=env,
                               capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(r.returncode, 1, (script, r.stdout, r.stderr))
            self.assertIn("base-incompatible", r.stderr, script)
            con = sqlite3.connect(db)
            self.assertEqual(con.execute("SELECT count(*) FROM pending").fetchone()[0], before, script)
            con.close()

    def test_captura_no_escribe_en_base_incompatible(self):
        self._mark_incompatible()
        db = os.path.join(self.home, ".claude", "neb.db")

        def content():
            # Lee a través de SQLite: lo que esté en el -wal también cuenta.
            con = sqlite3.connect(db)
            try:
                tables = [r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                return {t: con.execute(f'SELECT * FROM "{t}" ORDER BY 1').fetchall() for t in tables}
            finally:
                con.close()
        before = content()
        import contextlib
        import io
        transcript = os.path.join(self.home, "sesion-1.jsonl")
        with open(transcript, "w", encoding="utf-8") as fh:
            fh.write('{"type": "user", "message": {"content": "hola"}}\n')
        argv = ["logbook.py", "sesion-1", self.home, transcript, "Stop", self.other, self.home]
        err = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(err):
            logbook.main()
        self.assertIn("base-incompatible", err.getvalue())
        self.assertEqual(content(), before)


if __name__ == "__main__":
    unittest.main()
