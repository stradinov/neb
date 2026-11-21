#!/usr/bin/env python3
"""
test_logbook_sync_regression.py — regresión del flujo del hook logbook-sync sobre la base única.

Gate crítico: la captura escribe en la base que resuelve resolve_db_path (siempre <home>/.claude/neb.db),
más:
  T2 resolvedor único: un neb.db vacío o sin tabla work no cambia la ruta ni cuenta como base usable; la
     guarda de la base sin migrar la prueba test_logbook_migracion_team.py
  T-concurrencia (dos escritores con busy_timeout)
  T-gancho (on_work_archived reusa la conexión y es reversible)

Framework: unittest (stdlib), NO pytest. TODAS las DBs son temporales (tempfile); nunca se toca ~/.claude.

  py -m unittest tests.test_logbook_sync_regression
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
        logbook._upsert_req(con, "host/o/repo", "mi-req", "maq", "En progreso",
                            "main", "abc1234", "/repo", "draft md", '{"plan":""}',
                            "sess-1", "/tmp/t.jsonl")
        con.commit(); con.close()
        # relee con un nuevo connect resuelto (regresión: el path resuelto persiste)
        con2 = _db_shared._connect(_db_shared.resolve_db_path(home), SCHEMA)
        row = con2.execute("SELECT req_slug, req_state, origin_machine FROM work WHERE project=?",
                           ("host/o/repo",)).fetchone()
        self.assertEqual(row, ("mi-req", "En progreso", "maq"))
        con2.close()

    # ----------------------------------------------------------------- T2 resolvedor único
    def test_neb_db_vacio_no_cambia_la_ruta(self):
        home = _fresh_home()
        newp = os.path.join(home, ".claude", "neb.db")
        open(newp, "w").close()                              # neb.db de 0 bytes (connect accidental)
        self.assertEqual(_db_shared.resolve_db_path(home), newp)
        self.assertFalse(_db_shared._is_usable_db(newp))

    def test_neb_db_without_work_table_is_not_usable(self):
        home = _fresh_home()
        newp = os.path.join(home, ".claude", "neb.db")
        c = sqlite3.connect(newp); c.execute("CREATE TABLE foo(x)"); c.commit(); c.close()
        self.assertFalse(_db_shared._is_usable_db(newp))   # sin tabla 'work'

    def test_fresh_install_targets_neb_db(self):
        home = _fresh_home()  # ni neb.db ni la base anterior existen
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
        wid = con.execute("INSERT INTO work (mode, created_at, updated_at) VALUES ('exploratory',?,?)",
                          (_db_shared.now_iso(), _db_shared.now_iso())).lastrowid
        pid = pendings.create(con, "task", "algo ligado al work", work_ref=wid)
        con.commit()
        pendings.on_work_archived(con, wid)                 # SAVEPOINT propio, sin commit
        con.commit()
        r = con.execute("SELECT status, obsolete_cause FROM pending WHERE id=?", (pid,)).fetchone()
        self.assertEqual(r, ("obsolete", "resolved-otherwise"))
        # reversible
        pendings.revive(con, pid); con.commit()
        self.assertEqual(con.execute("SELECT status FROM pending WHERE id=?", (pid,)).fetchone()[0], "open")
        con.close()


if __name__ == "__main__":
    unittest.main()
