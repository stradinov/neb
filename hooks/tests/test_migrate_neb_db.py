#!/usr/bin/env python3
"""
test_migrate_neb_db.py — BLOQUEANTE 3 (REQ neb-pendings-sqlite): el migrador one-shot
NO debe ignorar el resultado de wal_checkpoint(TRUNCATE).

Cubre contra DIRECTORIOS HOME TEMPORALES (tempfile); NUNCA toca ~/.claude/*.db:
  • happy-path: neb-logbook.db -> neb.db, backups creados, destino usable
  • checkpoint busy (fila (1, ...)) -> ABORT sin tocar el destino (neb.db NO se crea) ni el legacy
  • rollback: si el destino no resulta usable tras os.replace, se restaura el legacy BORRADO
    por os.replace desde su backup .bak-<stamp>
  • idempotencia: ya migrado -> 0 sin tocar nada

Carga migrate-neb-db.py vía importlib (nombre con guiones, no importable normal).

Framework: unittest (stdlib), NO pytest.
"""

import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared  # noqa: E402

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
_MIGRATE_PATH = os.path.join(HERE, "..", "..", "bootstrap", "migrate-neb-db.py")


def _load_migrate():
    spec = importlib.util.spec_from_file_location("migrate_neb_db", _MIGRATE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load_migrate()


def _seed_legacy(home):
    """Crea <home>/.claude/neb-logbook.db poblado (una fila en work) y devuelve su path."""
    os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
    legacy = os.path.join(home, ".claude", _db_shared.LEGACY_DB_NAME)
    con = _db_shared._connect(legacy, SCHEMA)
    con.execute("INSERT INTO work (mode, owner, lock_state, created_at, updated_at) "
                "VALUES ('exploratory','dev','owned',?,?)",
                (_db_shared.now_iso(), _db_shared.now_iso()))
    con.commit(); con.close()
    return legacy


class _BusyCheckpointConn:
    """Envoltura de una conexión sqlite3 que finge un wal_checkpoint(TRUNCATE) BUSY:
    devuelve (1, -1, -1) para esa PRAGMA; delega todo lo demás a la conexión real."""

    def __init__(self, real):
        self._real = real

    def execute(self, sql, *a, **k):
        if "wal_checkpoint" in sql.lower():
            return _BusyCursor()
        return self._real.execute(sql, *a, **k)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _BusyCursor:
    def fetchone(self):
        return (1, -1, -1)   # busy=1 -> el migrador debe abortar


class TestMigrateCheckpoint(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-migrate-")

    def test_happy_path_renames_and_backs_up(self):
        legacy = _seed_legacy(self.home)
        target = os.path.join(self.home, ".claude", _db_shared.NEB_DB_NAME)
        rc = M.migrate(self.home, dry_run=False)
        self.assertEqual(rc, 0)
        self.assertTrue(_db_shared._is_usable_db(target))   # neb.db usable
        self.assertFalse(os.path.isfile(legacy))            # legacy consumido por os.replace
        # se creó al menos el backup del .db principal
        baks = [f for f in os.listdir(os.path.join(self.home, ".claude"))
                if f.startswith(_db_shared.LEGACY_DB_NAME) and ".bak-" in f]
        self.assertTrue(baks, "esperaba al menos un backup .bak-<stamp>")

    def test_checkpoint_busy_aborts_without_touching_destination(self):
        legacy = _seed_legacy(self.home)
        target = os.path.join(self.home, ".claude", _db_shared.NEB_DB_NAME)

        real_connect = sqlite3.connect

        def fake_connect(path, *a, **k):
            # Tras el fix TOCTOU, el abort-check (BEGIN IMMEDIATE) y el checkpoint reusan la
            # MISMA conexión. La envolvemos: BEGIN IMMEDIATE/ROLLBACK delegan al real (funcionan);
            # solo wal_checkpoint(TRUNCATE) finge BUSY -> el migrador debe abortar.
            return _BusyCheckpointConn(real_connect(path, *a, **k))

        with mock.patch.object(M.sqlite3, "connect", fake_connect):
            rc = M.migrate(self.home, dry_run=False)
        self.assertEqual(rc, 1)                              # abortó
        self.assertTrue(os.path.isfile(legacy))             # legacy intacto
        self.assertFalse(_db_shared._is_usable_db(target))  # destino NO creado/usable
        self.assertFalse(os.path.isfile(target))            # neb.db no debe existir

    def test_rollback_restores_legacy_deleted_by_os_replace(self):
        legacy = _seed_legacy(self.home)
        target = os.path.join(self.home, ".claude", _db_shared.NEB_DB_NAME)

        # Forzar que la verificación final (_is_usable_db del destino, paso 8) falle -> rollback.
        # En ese punto os.replace YA movió/borró el legacy; el rollback debe restaurarlo del backup.
        # Distinguimos paso 8 de la idempotencia/anti-colisión (paso 2/3): allí el legacy AÚN
        # existe; en el paso 8 el legacy ya NO existe (os.replace lo consumió).
        real_is_usable = M._is_usable_db

        def fake_is_usable(path):
            if os.path.basename(path) == _db_shared.NEB_DB_NAME and not os.path.isfile(legacy):
                return False     # paso 8: destino "no usable" -> dispara rollback
            return real_is_usable(path)

        with mock.patch.object(M, "_is_usable_db", fake_is_usable):
            rc = M.migrate(self.home, dry_run=False)
        self.assertEqual(rc, 1)                          # reportó fallo
        self.assertTrue(os.path.isfile(legacy),
                        "el rollback debe restaurar el legacy borrado por os.replace")
        self.assertTrue(real_is_usable(legacy))          # y restaurado usable (desde el backup)
        self.assertFalse(os.path.isfile(target))         # destino removido en el rollback

    def test_idempotent_already_migrated(self):
        # ya migrado: existe neb.db usable y NO hay legacy -> nada que hacer
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        target = os.path.join(self.home, ".claude", _db_shared.NEB_DB_NAME)
        _db_shared._connect(target, SCHEMA).close()
        # poblar para que sea usable
        con = _db_shared._connect(target, SCHEMA)
        con.execute("INSERT INTO work (mode, owner, lock_state, created_at, updated_at) "
                    "VALUES ('exploratory','d','owned',?,?)",
                    (_db_shared.now_iso(), _db_shared.now_iso()))
        con.commit(); con.close()
        self.assertEqual(M.migrate(self.home, dry_run=False), 0)


if __name__ == "__main__":
    unittest.main()
