#!/usr/bin/env python3
"""
test_logbook_req_state_enum.py — el cliente publica `req_state` normalizado al ENUM
(REQ neb-logbook-req-state-enum-en-publish).

El central declara `req_state` como ENUM del requerimiento (VARCHAR(64), modo estricto); la memoria
redacta el `Estado:` como ENUM + prosa. Solo el PAYLOAD del publish se normaliza: la bitácora local
conserva el texto, y la prosa viaja en `payload_json.req_state_note`.

Invariantes: DBs temporales; ningún test hace red (logbook._http siempre reemplazado); las aserciones
sobre la fila local leen con una conexión distinta a la que escribió.
  py -m unittest hooks.tests.test_logbook_req_state_enum
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import _db_shared
import logbook

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
ENUM = ("En progreso", "En validación", "Listo para aprobación", "Cerrado")

# Prosa SINTÉTICA con la forma real que toma el campo (ENUM + nota larga con markdown, guiones y paréntesis).
PROSA = " — Ola 1 LIVE y sincronizado; **fase 2 confirmada** (QA oficial); resto con código sembrado pero " \
        "**estado sin verificar**; pendiente: confirmación en storefront (gate Parte C) " + "x" * 120


def _fresh_db():
    d = tempfile.mkdtemp(prefix="neb-test-enum-")
    path = os.path.join(d, "neb.db")
    con = _db_shared._connect(path, SCHEMA)
    con.row_factory = sqlite3.Row
    return con, path


def _add_req(con, slug, state, payload='{"plan":"p","next_steps":"n"}'):
    logbook._upsert_req(con, "host/o/repo", slug, "dev", "maq", state, "main", "abc1234", "/repo",
                        "draft md", payload, "sess-" + slug, "/tmp/" + slug + ".jsonl")
    con.commit()
    return con.execute("SELECT id FROM work WHERE req_slug=?", (slug,)).fetchone()[0]


def _row(con, wid):
    path = con.execute("PRAGMA database_list").fetchone()[2]
    other = sqlite3.connect(path, timeout=1.0)
    other.row_factory = sqlite3.Row
    try:
        return other.execute("SELECT * FROM work WHERE id=?", (wid,)).fetchone()
    finally:
        other.close()


class TestNormalizeReqState(unittest.TestCase):

    def test_valores_canonicos_exactos_sin_nota(self):
        for s in ENUM:
            self.assertEqual(logbook._normalize_req_state(s), (s, None), s)

    def test_mayusculas_y_acentos_no_importan(self):
        self.assertEqual(logbook._normalize_req_state("en validacion"), ("En validación", None))
        self.assertEqual(logbook._normalize_req_state("LISTO PARA APROBACIÓN"), ("Listo para aprobación", None))
        self.assertEqual(logbook._normalize_req_state("EN PROGRESO"), ("En progreso", None))

    def test_envoltorio_markdown(self):
        self.assertEqual(logbook._normalize_req_state("**En progreso**"), ("En progreso", None))
        self.assertEqual(logbook._normalize_req_state("`Cerrado`"), ("Cerrado", None))

    def test_prosa_despues_del_enum_va_a_la_nota(self):
        raw = "En progreso" + PROSA
        enum, note = logbook._normalize_req_state(raw)
        self.assertEqual(enum, "En progreso")
        self.assertEqual(note, raw)                          # la nota es el texto ORIGINAL completo

    def test_sufijo_bloqueado_se_conserva_en_dos_formas(self):
        enum, note = logbook._normalize_req_state("En progreso (bloqueado por X)")
        self.assertEqual(enum, "En progreso (bloqueado)")
        self.assertEqual(note, "En progreso (bloqueado por X)")
        enum, _ = logbook._normalize_req_state("En validación — algo (Bloqueado: espera)")
        self.assertEqual(enum, "En validación (bloqueado)")

    def test_alias_documentado(self):
        enum, note = logbook._normalize_req_state("Listo para producción — deploy hecho")
        self.assertEqual(enum, "Listo para aprobación")
        self.assertIsNotNone(note)

    def test_sin_prefijo_del_enum_publica_null_y_conserva_la_nota(self):
        raw = "QA validada + mergeado a master + DEPLOYADO (pendiente: confirmación)"
        self.assertEqual(logbook._normalize_req_state(raw), (None, raw))

    def test_frontera_de_palabra(self):
        self.assertEqual(logbook._normalize_req_state("en progresos")[0], None)   # no es el ENUM
        self.assertEqual(logbook._normalize_req_state("Cerrado.")[0], "Cerrado")
        self.assertEqual(logbook._normalize_req_state("Cerrado (cancelado)")[0], "Cerrado")

    def test_vacio_o_none(self):
        for raw in ("", "   ", None):
            self.assertEqual(logbook._normalize_req_state(raw), (None, None), repr(raw))

    def test_todo_lo_publicado_cabe_en_64(self):
        casos = list(ENUM) + [s + PROSA for s in ENUM] + [s + " (bloqueado por " + "y" * 300 + ")" for s in ENUM] \
                + ["Listo para producción" + PROSA, "x" * 500, "**" + ENUM[2] + "**" + PROSA]
        for raw in casos:
            enum, _ = logbook._normalize_req_state(raw)
            self.assertTrue(enum is None or len(enum) <= 64, raw[:40])


class TestPayloadJsonWithNote(unittest.TestCase):

    def test_agrega_la_nota_sin_perder_claves(self):
        out = json.loads(logbook._payload_json_with_note('{"plan":"p","files":"f"}', "nota"))
        self.assertEqual(out, {"plan": "p", "files": "f", "req_state_note": "nota"})

    def test_sin_nota_manda_tal_cual(self):
        self.assertEqual(logbook._payload_json_with_note('{"plan":"p"}', None), '{"plan":"p"}')

    def test_json_invalido_o_no_objeto_manda_tal_cual(self):
        self.assertEqual(logbook._payload_json_with_note("no es json", "nota"), "no es json")
        self.assertEqual(logbook._payload_json_with_note("[1,2]", "nota"), "[1,2]")

    def test_vacio_o_none_se_convierte_en_objeto_con_la_nota(self):
        """Sin payload local la nota no se pierde: viaja en un objeto nuevo."""
        for empty in ("", None):
            self.assertEqual(json.loads(logbook._payload_json_with_note(empty, "nota")), {"req_state_note": "nota"})


class TestDrainWorksPublicaNormalizado(unittest.TestCase):

    def _capturar(self, con):
        calls = []

        def fake(endpoint, token, path, method="GET", payload=None):
            calls.append(payload)
            return 200, {"remote_id": 100 + len(calls)}
        with mock.patch.object(logbook, "_http", fake):
            logbook._drain_works(con, "http://x", "tok")
        return calls

    def test_payload_normalizado_y_fila_local_intacta(self):
        con, _ = _fresh_db()
        raw = "En validación" + PROSA
        wid = _add_req(con, "a", raw)
        (payload,) = self._capturar(con)
        self.assertEqual(payload["req_state"], "En validación")
        self.assertEqual(json.loads(payload["payload_json"])["req_state_note"], raw)
        self.assertEqual(json.loads(payload["payload_json"])["plan"], "p")   # el resto del payload sigue
        r = _row(con, wid)
        self.assertEqual(r["req_state"], raw)                                # la bitácora local conserva la prosa
        self.assertNotIn("req_state_note", r["payload_json"])                # y su payload_json no se toca
        self.assertEqual((r["dirty"], r["remote_id"]), (0, 101))

    def test_sin_prosa_no_hay_nota(self):
        con, _ = _fresh_db()
        _add_req(con, "a", "Cerrado")
        (payload,) = self._capturar(con)
        self.assertEqual(payload["req_state"], "Cerrado")
        self.assertNotIn("req_state_note", json.loads(payload["payload_json"]))

    def test_sin_prefijo_publica_null_con_nota(self):
        con, _ = _fresh_db()
        raw = "QA validada + mergeado + DEPLOYADO (pendiente confirmación)"
        _add_req(con, "a", raw)
        (payload,) = self._capturar(con)
        self.assertIsNone(payload["req_state"])
        self.assertEqual(json.loads(payload["payload_json"])["req_state_note"], raw)

    def test_payload_json_local_invalido_no_impide_publicar(self):
        con, _ = _fresh_db()
        wid = _add_req(con, "a", "En progreso" + PROSA, payload="{esto no es json")
        (payload,) = self._capturar(con)
        self.assertEqual(payload["req_state"], "En progreso")
        self.assertEqual(payload["payload_json"], "{esto no es json")
        self.assertEqual(_row(con, wid)["dirty"], 0)

    def test_exploratory_sin_estado_sigue_igual(self):
        con, _ = _fresh_db()
        logbook._upsert_exploratory(con, "s-x", "dev", "maq", "resumen", "main", "h", "/c", "/t.jsonl"); con.commit()
        (payload,) = self._capturar(con)
        self.assertIsNone(payload["req_state"])
        self.assertNotIn("req_state_note", json.loads(payload["payload_json"]))

    def test_e2e_un_central_que_rechaza_mas_de_64_ahora_acepta(self):
        """El caso real: antes del REQ, este central respondía 500 en cada sync para estos works."""
        con, _ = _fresh_db()
        ids = [_add_req(con, s, e + PROSA) for s, e in zip("abcd", ENUM)]
        ids.append(_add_req(con, "e", "QA validada + sin prefijo" + PROSA))

        def central(endpoint, token, path, method="GET", payload=None):
            rs = payload.get("req_state")
            if rs is not None and len(rs) > 64:
                return 500, {"error": "server_error", "detail": "(1406, \"Data too long for column 'req_state'\")"}
            return 200, {"remote_id": 500}
        with mock.patch.object(logbook, "_http", central):
            logbook._drain_works(con, "http://x", "tok")
        for wid in ids:
            r = _row(con, wid)
            self.assertEqual((r["dirty"], r["last_error"]), (0, None), wid)


if __name__ == "__main__":
    unittest.main()
