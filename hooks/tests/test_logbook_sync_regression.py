#!/usr/bin/env python3
"""
test_logbook_sync_regression.py — Sub-entrega A (REQ neb-pendings-sqlite).

Gate crítico (fila 2 del change MD): regresión del flujo logbook-sync con la DB
resuelta por resolve_db_path (rename lógico neb-logbook.db → neb.db), más:
  T2/T3 anti-shadowing en Windows (neb.db vacío / sin tabla 'work' no oculta legacy poblado)
  T3 dual-mode legado (máquina del equipo sin migrar)
  T-concurrencia (dos escritores con busy_timeout)
  T-gancho (on_work_archived reusa conexión y es reversible)

Framework: unittest (stdlib), NO pytest. TODAS las DBs son temporales (tempfile);
NUNCA se toca ~/.claude/neb-logbook.db ni ~/.claude/neb.db.

Comando de gate:
  py -m unittest discover -s hooks/tests -p "test_*.py"
  py -m unittest hooks.tests.test_logbook_sync_regression
"""

import os
import sys
import sqlite3
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared
import pendings
import logbook

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")


def _fresh_home():
    d = tempfile.mkdtemp(prefix="neb-test-")
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    return d


class TestLogbookRegression(unittest.TestCase):

    # ----------------------------------------------------------------- T1 [crítico]
    def test_capture_then_read_via_resolver(self):
        home = _fresh_home()
        db = _db_shared.resolve_db_path(home)               # → .../.claude/neb.db (no existe aún)
        con = _db_shared._connect(db, SCHEMA)
        self.assertIsNotNone(con)
        # simula captura de un work 'req' (firma real de _upsert_req)
        logbook._upsert_req(con, "host/o/repo", "mi-req", "dev", "maq", "En progreso",
                            "main", "abc1234", "/repo", "draft md", '{"plan":""}',
                            "sess-1", "/tmp/t.jsonl")
        con.commit(); con.close()
        # relee con un nuevo connect resuelto (regresión: el path resuelto persiste)
        con2 = _db_shared._connect(_db_shared.resolve_db_path(home), SCHEMA)
        row = con2.execute("SELECT req_slug, req_state FROM work WHERE project=?",
                           ("host/o/repo",)).fetchone()
        self.assertEqual(row[0], "mi-req")
        self.assertEqual(row[1], "En progreso")
        # el evento 'publish' se emitió
        n = con2.execute("SELECT count(*) FROM event WHERE action='publish'").fetchone()[0]
        self.assertEqual(n, 1)
        con2.close()

    # ----------------------------------------------------------------- T2 anti-shadowing
    def test_anti_shadowing_empty_neb_db(self):
        home = _fresh_home()
        legacy = os.path.join(home, ".claude", "neb-logbook.db")
        newp   = os.path.join(home, ".claude", "neb.db")
        # poblar legacy con schema + un work
        con = _db_shared._connect(legacy, SCHEMA)
        logbook._upsert_exploratory(con, "s-leg", "dev", "maq", "resumen", "main", "h", "/c", "/t.jsonl")
        con.commit(); con.close()
        # crear neb.db VACÍO (tamaño 0) — simula connect accidental
        open(newp, "w").close()
        self.assertEqual(os.path.getsize(newp), 0)
        # el resolver debe IGNORAR el neb.db vacío y caer a legacy
        self.assertEqual(_db_shared.resolve_db_path(home), legacy)
        self.assertFalse(_db_shared._is_usable_db(newp))
        self.assertTrue(_db_shared._is_usable_db(legacy))

    def test_neb_db_without_work_table_is_not_usable(self):
        home = _fresh_home()
        newp = os.path.join(home, ".claude", "neb.db")
        c = sqlite3.connect(newp); c.execute("CREATE TABLE foo(x)"); c.commit(); c.close()
        self.assertFalse(_db_shared._is_usable_db(newp))   # sin tabla 'work'

    # ----------------------------------------------------------------- T3 dual-mode legado
    def test_dual_mode_legacy_only(self):
        home = _fresh_home()
        legacy = os.path.join(home, ".claude", "neb-logbook.db")
        con = _db_shared._connect(legacy, SCHEMA); con.commit(); con.close()
        self.assertTrue(os.path.isfile(legacy))
        self.assertEqual(_db_shared.resolve_db_path(home), legacy)

    def test_fresh_install_targets_neb_db(self):
        home = _fresh_home()  # ni neb.db ni legacy existen
        self.assertTrue(_db_shared.resolve_db_path(home).endswith("neb.db"))

    # ----------------------------------------------------------------- T-concurrencia
    def test_two_writers_busy_timeout(self):
        home = _fresh_home()
        db = _db_shared.resolve_db_path(home)
        _db_shared._connect(db, SCHEMA).close()   # crea schema
        errors = []

        def writer(tag):
            try:
                con = _db_shared._connect(db, SCHEMA)
                _db_shared.begin_immediate(con)        # fija isolation_level=None + BEGIN IMMEDIATE
                con.execute("INSERT INTO pending (type, context_origin, status, created_at) "
                            "VALUES ('task', ?, 'open', ?)", (f"ctx-{tag}", _db_shared.now_iso()))
                time.sleep(0.2)                        # mantiene el lock para forzar espera del otro
                con.execute("COMMIT"); con.close()
            except Exception as e:
                errors.append((tag, str(e)))

        t1 = threading.Thread(target=writer, args=("A",))
        t2 = threading.Thread(target=writer, args=("B",))
        t1.start(); t2.start(); t1.join(); t2.join()
        self.assertEqual(errors, [], f"errores de concurrencia: {errors}")
        con = _db_shared._connect(db, SCHEMA)
        self.assertEqual(con.execute("SELECT count(*) FROM pending").fetchone()[0], 2)
        con.close()

    # ----------------------------------------------------------------- T-gancho
    def test_on_work_archived_auto_obsolete(self):
        home = _fresh_home()
        con = _db_shared._connect(_db_shared.resolve_db_path(home), SCHEMA)
        wid = con.execute("INSERT INTO work (mode, owner, lock_state, created_at, updated_at) "
                          "VALUES ('exploratory','dev','owned',?,?)",
                          (_db_shared.now_iso(), _db_shared.now_iso())).lastrowid
        pid = pendings.create(con, "task", "algo ligado al work", work_ref=wid)
        con.commit()
        pendings.on_work_archived(con, wid, "dev", "maq")   # SAVEPOINT propio, sin commit
        con.commit()
        r = con.execute("SELECT status, obsolete_cause FROM pending WHERE id=?", (pid,)).fetchone()
        self.assertEqual(r, ("obsolete", "resolved-otherwise"))
        # reversible
        pendings.revive(con, pid); con.commit()
        self.assertEqual(con.execute("SELECT status FROM pending WHERE id=?", (pid,)).fetchone()[0], "open")
        con.close()


if __name__ == "__main__":
    unittest.main()
