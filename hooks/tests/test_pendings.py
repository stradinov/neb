#!/usr/bin/env python3
"""
test_pendings.py — Sub-entrega A (REQ neb-pendings-sqlite).

Cubre el CRUD + ciclo de vida de pendings.py contra DBs TEMPORALES (tempfile):
  create / add_note / archive / revive (máquina de estados reversible e idempotente)
  enums en INGLES ('open'/'obsolete', 'no-longer-applies'/'resolved-otherwise')
  validación de entradas inválidas (type, obsolete_cause)
  resolve_session_context para pending type='session'
  on_work_archived (auto-obsolescencia reversible vía SAVEPOINT)

Framework: unittest (stdlib), NO pytest. NUNCA toca ~/.claude/*.db.
"""

import os
import sys
import json
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared
import pendings

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")


def _fresh_con():
    d = tempfile.mkdtemp(prefix="neb-test-")
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    return _db_shared._connect(_db_shared.resolve_db_path(d), SCHEMA)


class TestPendingsCrud(unittest.TestCase):

    def test_create_returns_autoincrement_id(self):
        con = _fresh_con()
        p1 = pendings.create(con, "task", "primer pendiente")
        p2 = pendings.create(con, "task", "segundo pendiente")
        con.commit()
        self.assertEqual((p1, p2), (1, 2))
        r = con.execute("SELECT type, context_origin, status, obsolete_cause, archived_at "
                        "FROM pending WHERE id=?", (p1,)).fetchone()
        self.assertEqual(r, ("task", "primer pendiente", "open", None, None))
        con.close()

    def test_create_invalid_type_raises(self):
        con = _fresh_con()
        with self.assertRaises(ValueError):
            pendings.create(con, "bogus", "x")
        con.close()

    def test_add_note_does_not_touch_context_origin(self):
        con = _fresh_con()
        pid = pendings.create(con, "task", "origen inmutable")
        pendings.add_note(con, pid, "evolución 1")
        pendings.add_note(con, pid, "evolución 2")
        con.commit()
        self.assertEqual(con.execute("SELECT context_origin FROM pending WHERE id=?", (pid,)).fetchone()[0],
                         "origen inmutable")
        self.assertEqual(con.execute("SELECT count(*) FROM pending_note WHERE pending_id=?", (pid,)).fetchone()[0], 2)
        con.close()

    def test_archive_revive_cycle_english_enums(self):
        con = _fresh_con()
        pid = pendings.create(con, "task", "ctx")
        n = pendings.archive(con, pid, "no-longer-applies")
        self.assertEqual(n, 1)
        r = con.execute("SELECT status, obsolete_cause FROM pending WHERE id=?", (pid,)).fetchone()
        self.assertEqual(r, ("obsolete", "no-longer-applies"))
        # idempotente: re-archivar es no-op (ya estaba obsolete)
        self.assertEqual(pendings.archive(con, pid, "resolved-otherwise"), 0)
        # revive limpia causa + archived_at
        self.assertEqual(pendings.revive(con, pid), 1)
        r = con.execute("SELECT status, obsolete_cause, archived_at FROM pending WHERE id=?", (pid,)).fetchone()
        self.assertEqual(r, ("open", None, None))
        # revive de un open es no-op
        self.assertEqual(pendings.revive(con, pid), 0)
        # cada transición deja nota
        self.assertGreaterEqual(con.execute("SELECT count(*) FROM pending_note WHERE pending_id=?", (pid,)).fetchone()[0], 2)
        con.commit(); con.close()

    def test_archive_invalid_cause_raises(self):
        con = _fresh_con()
        pid = pendings.create(con, "task", "ctx")
        with self.assertRaises(ValueError):
            pendings.archive(con, pid, "resuelto-de-otra-forma")  # español/invalido
        con.close()

    def test_archive_nonexistent_is_noop(self):
        con = _fresh_con()
        self.assertEqual(pendings.archive(con, 999, "resolved-otherwise"), 0)
        con.close()

    def test_on_work_archived_only_affects_open_linked(self):
        con = _fresh_con()
        wid = con.execute("INSERT INTO work (mode, owner, lock_state, created_at, updated_at) "
                          "VALUES ('req','dev','owned',?,?)",
                          (_db_shared.now_iso(), _db_shared.now_iso())).lastrowid
        linked_open = pendings.create(con, "task", "ligado abierto", work_ref=wid)
        linked_obs  = pendings.create(con, "task", "ligado ya obsoleto", work_ref=wid)
        pendings.archive(con, linked_obs, "no-longer-applies")    # ya obsoleto antes del cierre
        unlinked    = pendings.create(con, "task", "no ligado")   # work_ref NULL
        con.commit()
        pendings.on_work_archived(con, wid, "dev", "maq")
        con.commit()
        self.assertEqual(con.execute("SELECT status, obsolete_cause FROM pending WHERE id=?", (linked_open,)).fetchone(),
                         ("obsolete", "resolved-otherwise"))
        # el que ya estaba obsoleto conserva su causa original (no-op del SAVEPOINT)
        self.assertEqual(con.execute("SELECT obsolete_cause FROM pending WHERE id=?", (linked_obs,)).fetchone()[0],
                         "no-longer-applies")
        # el no-ligado sigue abierto
        self.assertEqual(con.execute("SELECT status FROM pending WHERE id=?", (unlinked,)).fetchone()[0], "open")
        con.close()

    def test_resolve_session_context(self):
        con = _fresh_con()
        payload = json.dumps({"summary": "exploración X"}, ensure_ascii=False)
        wid = con.execute("INSERT INTO work (mode, owner, lock_state, payload_json, transcript_path, "
                          "created_at, updated_at) VALUES ('exploratory','dev','owned',?,?,?,?)",
                          (payload, "/tmp/sess.jsonl", _db_shared.now_iso(), _db_shared.now_iso())).lastrowid
        pid = pendings.create(con, "session", "sesión pausada", session_ref=wid)
        con.commit()
        ctx = pendings.resolve_session_context(con, pid)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["work_id"], wid)
        self.assertEqual(ctx["summary"], "exploración X")
        self.assertIn("sess.jsonl", ctx["transcript_path"])
        con.close()

    def test_resolve_session_context_none_for_task(self):
        con = _fresh_con()
        pid = pendings.create(con, "task", "no es sesión")
        con.commit()
        self.assertIsNone(pendings.resolve_session_context(con, pid))
        con.close()

    def test_with_write_tx_commits(self):
        con = _fresh_con()
        con.close()  # cerrar el de schema; abrir uno limpio para el wrapper
        d = tempfile.mkdtemp(prefix="neb-test-")
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        db = _db_shared.resolve_db_path(d)
        c = _db_shared._connect(db, SCHEMA)
        pid = pendings._with_write_tx(c, lambda x: pendings.create(x, "task", "via wrapper"))
        c.close()
        # releer en conexión nueva: el COMMIT del wrapper persistió
        c2 = _db_shared._connect(db, SCHEMA)
        self.assertEqual(c2.execute("SELECT context_origin FROM pending WHERE id=?", (pid,)).fetchone()[0],
                         "via wrapper")
        c2.close()


if __name__ == "__main__":
    unittest.main()
