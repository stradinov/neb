#!/usr/bin/env python3
"""
test_logbook_session_sync.py — registro de sesión (tabla session_sync).

session_sync guarda una fila por sesión: ruta del .jsonl y cursor de lectura (read_byte). Cada captura
refresca la ruta sin duplicar la fila ni bajar el cursor. El cursor lo prueba en detalle
test_logbook_migracion_retiro.py (TestLectorSoloCursor).

Invariantes: DBs y homes temporales (tempfile); nunca ~/.claude.
Framework: unittest (stdlib), NO pytest.
  py -m unittest tests.test_logbook_session_sync
"""

import os
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared
import logbook

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")


def _db():
    path = os.path.join(tempfile.mkdtemp(prefix="neb-test-sesion-"), "neb.db")
    return _db_shared._connect(path, SCHEMA), path


def _sess(path, sid):
    """Lee con una conexión nueva: un registro sin commit no pasa la prueba."""
    o = sqlite3.connect(path)
    try:
        o.row_factory = sqlite3.Row
        return [dict(r) for r in o.execute("SELECT * FROM session_sync WHERE session_id=?", (sid,))]
    finally:
        o.close()


class TestRegistro(unittest.TestCase):

    def test_registra_la_ruta_la_refresca_y_no_baja_el_cursor(self):
        con, path = _db()
        self.addCleanup(con.close)
        logbook._register_session(con, "S", "/t1"); con.commit()
        con.execute("UPDATE session_sync SET read_byte=40 WHERE session_id='S'"); con.commit()
        logbook._register_session(con, "S", "/t2"); con.commit()           # otra captura, el .jsonl se movió
        rows = _sess(path, "S")
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), {"session_id", "transcript_path", "updated_at", "read_byte"})
        self.assertEqual((rows[0]["transcript_path"], rows[0]["read_byte"]), ("/t2", 40))


if __name__ == "__main__":
    unittest.main()
