#!/usr/bin/env python3
"""test_transcript_local.py — SR-1 (programa preservación-de-conocimiento).

Persistencia local del corpus + búsqueda local:
  T1  _index_local persiste el text_plain (sin tool_result) en transcript_local.
  T2  idempotencia: re-indexar el mismo .jsonl (sin crecer) no duplica.
  T3  incremental: al crecer el .jsonl, sólo se añade el tramo nuevo (cursor = MAX(byte_to)).
  T4  _search_local encuentra un término del corpus (FTS5 o fallback LIKE).

Framework: unittest (stdlib). DBs y .jsonl temporales; nunca toca ~/.claude.
  py -m unittest hooks.tests.test_transcript_local
"""
import os
import sys
import json
import sqlite3
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared
import logbook

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")


def _write_jsonl(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        for obj in lines:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


BASE_LINES = [
    {"type": "user", "message": {"content": "necesito revisar el proceso de importacion nocturno del catalogo"}},
    {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "el proceso NOCTURNO usa el contador ALPHA_COUNTER para el modo MAESTRO vs REPLICA"},
        {"type": "tool_use", "name": "Bash", "input": {"command": "run-import --dry"}},
    ]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "content": "TOKEN_SECRETO=abc123 y otra salida de herramienta"},
    ]}},
]


class TestTranscriptLocal(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-test-sr1-")
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        self.db = _db_shared.resolve_db_path(self.home)
        self.con = _db_shared._connect(self.db, SCHEMA)
        self.con.row_factory = sqlite3.Row
        self.jsonl = os.path.join(self.home, "sess1.jsonl")

    def tearDown(self):
        try:
            self.con.close()
        except Exception:
            pass

    def _count(self):
        return self.con.execute(
            "SELECT COUNT(*) FROM transcript_local WHERE session_id='sess1'").fetchone()[0]

    def test_index_extracts_text_plain_without_tool_result(self):  # T1
        _write_jsonl(self.jsonl, BASE_LINES)
        logbook._index_local(self.con, "sess1", None, self.jsonl)
        self.con.commit()
        txt = self.con.execute(
            "SELECT text_plain FROM transcript_local WHERE session_id='sess1'").fetchone()[0]
        self.assertIn("ALPHA_COUNTER", txt)                  # conversación capturada
        self.assertIn("necesito revisar el proceso", txt)
        self.assertNotIn("TOKEN_SECRETO", txt)               # tool_result excluido
        self.assertNotIn("run-import", txt)                  # tool_use excluido

    def test_idempotent_when_not_grown(self):                # T2
        _write_jsonl(self.jsonl, BASE_LINES)
        logbook._index_local(self.con, "sess1", None, self.jsonl); self.con.commit()
        logbook._index_local(self.con, "sess1", None, self.jsonl); self.con.commit()
        self.assertEqual(self._count(), 1)                   # no duplica

    def test_incremental_appends_only_new(self):             # T3
        _write_jsonl(self.jsonl, BASE_LINES)
        logbook._index_local(self.con, "sess1", None, self.jsonl); self.con.commit()
        first_end = self.con.execute(
            "SELECT byte_to FROM transcript_local WHERE session_id='sess1'").fetchone()[0]
        # crece el .jsonl con un turno nuevo
        with open(self.jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "el fix ordena la jerarquia real por campo_agrupador"}]}},
                ensure_ascii=False) + "\n")
        logbook._index_local(self.con, "sess1", None, self.jsonl); self.con.commit()
        rows = self.con.execute(
            "SELECT byte_from, byte_to, text_plain FROM transcript_local "
            "WHERE session_id='sess1' ORDER BY byte_from").fetchall()
        self.assertEqual(len(rows), 2)                       # tramo nuevo añadido
        self.assertEqual(rows[1]["byte_from"], first_end)    # arranca donde terminó el anterior
        self.assertIn("campo_agrupador", rows[1]["text_plain"])
        self.assertNotIn("campo_agrupador", rows[0]["text_plain"])  # no re-captura lo viejo

    def test_search_local_finds_term(self):                  # T4
        _write_jsonl(self.jsonl, BASE_LINES)
        logbook._index_local(self.con, "sess1", None, self.jsonl); self.con.commit()
        results = logbook._search_local(self.con, "ALPHA_COUNTER")
        self.assertTrue(any(sid == "sess1" for sid, _ in results))
        # término inexistente no matchea
        self.assertEqual(logbook._search_local(self.con, "terminoinventadoxyz"), [])


if __name__ == "__main__":
    unittest.main()
