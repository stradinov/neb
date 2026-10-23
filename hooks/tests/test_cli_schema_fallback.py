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


if __name__ == "__main__":
    unittest.main()
