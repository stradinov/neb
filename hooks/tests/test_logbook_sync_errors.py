#!/usr/bin/env python3
"""
test_logbook_sync_errors.py — fallos de sync VISIBLES (REQ neb-logbook-sync-errores-visibles).

Un rechazo del central que no sea 200 ya no es mudo: se persiste por canal en work.last_error
(publish) / work.transcript_error (transcript) sin cortar el reintento (salvo el 409), y el verbo
local `sync-status` lo expone.

Invariantes de esta suite:
  • TODAS las DBs son temporales (tempfile); NUNCA se toca ~/.claude/neb-logbook.db ni ~/.claude/neb.db.
  • NINGÚN test hace red: logbook._http se reemplaza siempre; donde no debe invocarse, el reemplazo falla.
  • El entorno del test no hereda el endpoint/token reales (mock.patch.dict).

Framework: unittest (stdlib), NO pytest.
  py -m unittest hooks.tests.test_logbook_sync_errors
"""

import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared
import logbook

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
NEW_COLS = ("last_error", "last_error_at", "transcript_error", "transcript_error_at")
FAKE_ENV = {"NEB_LOGBOOK_ENDPOINT": "http://central.invalid", "NEB_LOGBOOK_TOKEN": "tok-de-prueba-0123456789"}

# DDL CONGELADO del esquema previo a este REQ (sin `conflict` ni las 4 columnas nuevas): una DB "vieja" real.
# No se deriva del .sql vivo a propósito: así el test detecta fallos del camino schema -> _migrate sobre una
# DB existente, que una DB recién creada con el esquema nuevo nunca ejercita.
LEGACY_WORK_DDL = """
CREATE TABLE work (
  id INTEGER PRIMARY KEY, mode TEXT NOT NULL DEFAULT 'req', project TEXT, req_slug TEXT, owner TEXT,
  lock_state TEXT NOT NULL DEFAULT 'owned', takeover_by TEXT, locked_at TEXT, req_state TEXT, branch TEXT,
  head_commit TEXT, repo_path TEXT, change_md TEXT, payload_json TEXT,
  payload_version INTEGER NOT NULL DEFAULT 0, origin_dev TEXT, origin_machine TEXT, claude_session_id TEXT,
  claude_session_name TEXT, transcript_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  archived_at TEXT, dirty INTEGER NOT NULL DEFAULT 1, synced_at TEXT, remote_id INTEGER
);
"""


def _fresh_db():
    d = tempfile.mkdtemp(prefix="neb-test-syncerr-")
    path = os.path.join(d, "neb.db")
    con = _db_shared._connect(path, SCHEMA)
    con.row_factory = sqlite3.Row
    return con, path, d


def _add_req(con, slug, state="En progreso"):
    logbook._upsert_req(con, "host/o/repo", slug, "dev", "maq", state, "main", "abc1234", "/repo",
                        "draft md", '{"plan":""}', "sess-" + slug, "/tmp/" + slug + ".jsonl")
    con.commit()
    return con.execute("SELECT id FROM work WHERE req_slug=?", (slug,)).fetchone()[0]


def _row(con, wid):
    """Lee con una conexión NUEVA, no con la que escribió: así un UPDATE sin commit (que la conexión
    escritora vería igual) no pasa la prueba. Quitar un con.commit() en el código debe romper tests."""
    path = con.execute("PRAGMA database_list").fetchone()[2]
    other = sqlite3.connect(path, timeout=1.0)
    other.row_factory = sqlite3.Row
    try:
        return other.execute("SELECT * FROM work WHERE id=?", (wid,)).fetchone()
    finally:
        other.close()


def _http_seq(responses, calls=None):
    """_http falso: devuelve `responses` en orden (la última se repite). Registra (path, payload)."""
    state = {"i": 0}

    def fake(endpoint, token, path, method="GET", payload=None):
        if calls is not None:
            calls.append((path, payload))
        r = responses[min(state["i"], len(responses) - 1)]
        state["i"] += 1
        return r
    return fake


def _http_forbidden(*_a, **_k):
    raise AssertionError("este camino NO debe hacer red")


class _FailingWrites:
    """Proxy de conexión: lanza 'database is locked' en los UPDATE que REGISTRAN un fallo de publish
    (SET last_error=?), y delega todo lo demás. El 200 usa 'last_error=NULL', que no coincide."""

    def __init__(self, con):
        self._con = con
        self.failed = 0

    def execute(self, sql, *a):
        if "SET last_error=?" in sql:
            self.failed += 1
            raise sqlite3.OperationalError("database is locked")
        return self._con.execute(sql, *a)

    def __getattr__(self, name):
        return getattr(self._con, name)


class TestDrainWorks(unittest.TestCase):

    def test_200_publica_y_limpia_error_previo(self):
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        con.execute("UPDATE work SET last_error='publish 500 viejo', last_error_at='2026-01-01T00:00:00+00:00' WHERE id=?", (wid,))
        con.commit()
        with mock.patch.object(logbook, "_http", _http_seq([(200, {"remote_id": 77})])):
            logbook._drain_works(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertEqual((r["dirty"], r["remote_id"], r["conflict"]), (0, 77, 0))
        self.assertIsNone(r["last_error"]); self.assertIsNone(r["last_error_at"])
        self.assertIsNotNone(r["synced_at"])

    def test_409_corta_reintento_y_deja_motivo(self):
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        with mock.patch.object(logbook, "_http", _http_seq([(409, {"error": "conflict", "detail": "owner distinto"})])):
            logbook._drain_works(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertEqual((r["dirty"], r["conflict"]), (0, 1))
        self.assertEqual(r["last_error"], "publish 409 conflict: owner distinto")
        self.assertIsNotNone(r["last_error_at"])

    def test_500_conserva_dirty_y_registra_codigo_y_detail(self):
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        resp = {"error": "server_error", "detail": "(1406, \"Data too long for column 'req_state' at row 1\")"}
        with mock.patch.object(logbook, "_http", _http_seq([(500, resp)])):
            logbook._drain_works(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertEqual(r["dirty"], 1)                      # la decisión: seguir reintentando
        self.assertEqual(r["conflict"], 0)
        self.assertIn("publish 500 server_error", r["last_error"])
        self.assertIn("1406", r["last_error"])
        self.assertIsNotNone(r["last_error_at"])

    def test_4xx_distinto_de_409_conserva_dirty(self):
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        with mock.patch.object(logbook, "_http", _http_seq([(422, {"error": "invalid"})])):
            logbook._drain_works(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertEqual(r["dirty"], 1)
        self.assertEqual(r["last_error"], "publish 422 invalid")

    def test_sin_respuesta_conserva_el_motivo(self):
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        with mock.patch.object(logbook, "_http", _http_seq([(None, {"error": "TimeoutError", "detail": "timed out"})])):
            logbook._drain_works(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertEqual(r["dirty"], 1)
        self.assertEqual(r["last_error"], "publish sin respuesta HTTP TimeoutError: timed out")

    def test_502_con_cuerpo_html_no_produce_texto_vacio(self):
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        with mock.patch.object(logbook, "_http", _http_seq([(502, {})])):
            logbook._drain_works(con, "http://x", "tok")
        self.assertEqual(_row(con, wid)["last_error"], "publish 502 (sin cuerpo JSON)")

    def test_respuesta_que_no_es_dict_no_lanza(self):
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        with mock.patch.object(logbook, "_http", _http_seq([(500, ["no", "soy", "dict"])])):
            logbook._drain_works(con, "http://x", "tok")             # no debe lanzar
        self.assertEqual(_row(con, wid)["last_error"], "publish 500 (sin cuerpo JSON)")
        with mock.patch.object(logbook, "_http", _http_seq([(200, ["tampoco"])])):
            logbook._drain_works(con, "http://x", "tok")             # 200 con cuerpo raro: tampoco lanza
        self.assertEqual(_row(con, wid)["dirty"], 1)                 # ...pero NO cuenta como publicado

    def test_200_sin_remote_id_no_cuenta_como_publicado(self):
        """Un 200 con cuerpo vacío o JSON ajeno (proxy, portal cautivo) daba dirty=0 sin remote_id: el work salía
        de sync-status y del drenaje de transcripts sin haberse publicado. Además debe conservar el remote_id previo."""
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        con.execute("UPDATE work SET remote_id=77 WHERE id=?", (wid,)); con.commit()
        for body in ({}, {"status": "ok"}, [], "ok", {"remote_id": None}):
            with mock.patch.object(logbook, "_http", _http_seq([(200, body)])):
                logbook._drain_works(con, "http://x", "tok")
            r = _row(con, wid)
            self.assertEqual((r["dirty"], r["remote_id"]), (1, 77), body)
            self.assertEqual(r["last_error"], "publish 200-sin-remote_id (sin cuerpo JSON)")
        with mock.patch.object(logbook, "_http", _http_seq([(200, {"remote_id": 78})])):
            logbook._drain_works(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertEqual((r["dirty"], r["remote_id"], r["last_error"]), (0, 78, None))

    def test_200_tardio_no_pisa_la_version_nueva(self):
        """Carrera real: el POST de la versión v0 está en vuelo, un Stop captura v1 (que el central rechaza) y otro
        sync registra el 500. Cuando llega el 200 tardío de v0 NO debe bajar dirty ni borrar el error de v1."""
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")

        def fake(endpoint, token, path, method="GET", payload=None):
            # mientras v0 viaja: nueva captura (v1, prosa larga) + otro sync la registra como rechazada
            _add_req(con, "a", state="En progreso " + "x" * 120)
            con.execute("UPDATE work SET last_error='publish 500 server_error: (1406, ...)', "
                        "last_error_at='2026-01-01T00:00:00+00:00' WHERE id=?", (wid,)); con.commit()
            return 200, {"remote_id": 5}
        with mock.patch.object(logbook, "_http", fake):
            logbook._drain_works(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertEqual(r["dirty"], 1)                              # v1 sigue pendiente
        self.assertEqual(r["last_error"], "publish 500 server_error: (1406, ...)")
        self.assertEqual(r["remote_id"], 5)                          # pero el remote_id del 200 sí se conserva
        self.assertIsNotNone(r["synced_at"])

    def test_200_tras_409_baja_conflict_y_limpia_el_motivo(self):
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        con.execute("UPDATE work SET conflict=1, last_error='publish 409 conflict', last_error_at='t' WHERE id=?", (wid,))
        con.commit()
        with mock.patch.object(logbook, "_http", _http_seq([(200, {"remote_id": 1})])):
            logbook._drain_works(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertEqual((r["dirty"], r["conflict"], r["last_error"]), (0, 0, None))

    def test_409_repetido_conserva_desde_cuando(self):
        """Ruta caliente de '*_at = desde cuándo': cada Stop vuelve a poner dirty=1 y el sync repite el 409."""
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        resp = {"error": "conflict", "detail": "owner distinto"}
        with mock.patch.object(logbook, "_http", _http_seq([(409, resp)])):
            logbook._drain_works(con, "http://x", "tok")
        con.execute("UPDATE work SET last_error_at='2026-01-01T00:00:00+00:00' WHERE id=?", (wid,)); con.commit()
        _add_req(con, "a")                                           # el Stop siguiente re-ensucia (dirty=1)
        self.assertEqual(_row(con, wid)["dirty"], 1)
        with mock.patch.object(logbook, "_http", _http_seq([(409, resp)])):
            logbook._drain_works(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertEqual((r["dirty"], r["conflict"]), (0, 1))
        self.assertEqual(r["last_error_at"], "2026-01-01T00:00:00+00:00")   # mismo texto ⇒ se conserva
        _add_req(con, "a")
        with mock.patch.object(logbook, "_http", _http_seq([(409, {"error": "conflict", "detail": "otro"})])):
            logbook._drain_works(con, "http://x", "tok")
        self.assertNotEqual(_row(con, wid)["last_error_at"], "2026-01-01T00:00:00+00:00")   # otro texto ⇒ cambia

    def test_detail_que_no_es_str_no_tumba_el_drenaje(self):
        con, _, _ = _fresh_db()
        bad = _add_req(con, "a"); good = _add_req(con, "b")
        with mock.patch.object(logbook, "_http", _http_seq([(422, {"error": "invalid", "detail": ["campo", {"x": 1}]}),
                                                            (200, {"remote_id": 2})])):
            logbook._drain_works(con, "http://x", "tok")
        self.assertEqual(_row(con, bad)["dirty"], 1)
        self.assertTrue(_row(con, bad)["last_error"].startswith("publish 422 invalid"))
        self.assertEqual(_row(con, good)["dirty"], 0)

    def test_token_enmascarado_en_los_tres_sitios_de_llamada(self):
        tok = "SECRETO-XYZ-0123456789"
        for code in (409, 500):
            con, _, d = _fresh_db()
            wid = _add_req(con, "a")
            with mock.patch.object(logbook, "_http", _http_seq([(code, {"error": "e", "detail": "eco " + tok})])):
                logbook._drain_works(con, "http://x", tok)
            self.assertNotIn(tok, _row(con, wid)["last_error"], code)
        con, _, d = _fresh_db()
        wid = _add_req(con, "t")
        p = os.path.join(d, "t.jsonl"); open(p, "wb").write(b'{"type":"user"}\n')
        con.execute("UPDATE work SET remote_id=50, transcript_path=?, dirty=0 WHERE id=?", (p, wid)); con.commit()
        with mock.patch.object(logbook, "_http", _http_seq([(413, {"error": "e", "detail": "eco " + tok})])):
            logbook._drain_transcripts(con, "http://x", tok)
        self.assertNotIn(tok, _row(con, wid)["transcript_error"])
        # frontera del truncado: el token pegado al corte de 500 no debe dejar ni un prefijo
        text = logbook._sync_error_text("publish", 500, {"error": "e", "detail": "x" * 470 + tok}, tok)
        self.assertNotIn(tok[:8], text)

    def test_secuencia_500_500_200_se_recupera_sola(self):
        """La razón de no cortar el reintento: al arreglarse el central, el work se re-publica sin intervención.
        Y mientras falla, last_error_at NO se reescribe: responde 'desde cuándo', no 'último reintento'."""
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        resp = {"error": "server_error", "detail": "boom"}
        with mock.patch.object(logbook, "_http", _http_seq([(500, resp)])):
            logbook._drain_works(con, "http://x", "tok")
        first_at = _row(con, wid)["last_error_at"]
        con.execute("UPDATE work SET last_error_at='2026-01-01T00:00:00+00:00' WHERE id=?", (wid,)); con.commit()
        with mock.patch.object(logbook, "_http", _http_seq([(500, resp)])):
            logbook._drain_works(con, "http://x", "tok")
        self.assertIsNotNone(first_at)
        self.assertEqual(_row(con, wid)["last_error_at"], "2026-01-01T00:00:00+00:00")   # mismo texto => intacto
        with mock.patch.object(logbook, "_http", _http_seq([(200, {"remote_id": 9})])):
            logbook._drain_works(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertEqual((r["dirty"], r["remote_id"]), (0, 9))
        self.assertIsNone(r["last_error"])

    def test_registrar_el_error_nunca_tumba_el_drenaje(self):
        """Regresión que el plan original habría introducido: si el UPDATE del error falla (DB bloqueada),
        los works sanos que vienen después deben publicarse igual."""
        con, _, _ = _fresh_db()
        bad = _add_req(con, "envenenado")
        good = _add_req(con, "sano")
        proxy = _FailingWrites(con)
        with mock.patch.object(logbook, "_http", _http_seq([(500, {"error": "server_error"}), (200, {"remote_id": 5})])):
            logbook._drain_works(proxy, "http://x", "tok")           # no debe lanzar
        self.assertEqual(proxy.failed, 1)
        self.assertEqual(_row(con, good)["dirty"], 0)                # el sano se publicó
        self.assertEqual(_row(con, good)["remote_id"], 5)
        self.assertEqual(_row(con, bad)["dirty"], 1)
        self.assertFalse(con.in_transaction)                         # rollback hecho: no queda tx colgada

    def test_no_registra_si_otro_sync_ya_publico_durante_el_post(self):
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")

        def fake(endpoint, token, path, method="GET", payload=None):
            con.execute("UPDATE work SET dirty=0 WHERE id=?", (wid,)); con.commit()     # otro sync ganó
            return 500, {"error": "server_error"}
        with mock.patch.object(logbook, "_http", fake):
            logbook._drain_works(con, "http://x", "tok")
        self.assertIsNone(_row(con, wid)["last_error"])              # fallo rancio: no se pega

    def test_el_payload_no_lleva_columnas_locales(self):
        con, _, _ = _fresh_db()
        _add_req(con, "a")
        calls = []
        with mock.patch.object(logbook, "_http", _http_seq([(200, {"remote_id": 1})], calls)):
            logbook._drain_works(con, "http://x", "tok")
        path, payload = calls[0]
        self.assertEqual(path, "/work/publish")
        for local_only in NEW_COLS + ("dirty", "conflict", "synced_at", "remote_id", "id"):
            self.assertNotIn(local_only, payload)

    def test_el_token_nunca_queda_persistido(self):
        con, _, _ = _fresh_db()
        wid = _add_req(con, "a")
        with mock.patch.object(logbook, "_http", _http_seq([(500, {"error": "e", "detail": "eco del header SECRETO-XYZ"})])):
            logbook._drain_works(con, "http://x", "SECRETO-XYZ")
        self.assertNotIn("SECRETO-XYZ", _row(con, wid)["last_error"])
        self.assertIn("***", _row(con, wid)["last_error"])

    def test_texto_truncado_a_500(self):
        text = logbook._sync_error_text("publish", 500, {"error": "e", "detail": "x" * 5000})
        self.assertEqual(len(text), 500)
        self.assertTrue(text.startswith("publish 500 e: "))


class TestDrainTranscripts(unittest.TestCase):

    def _work_con_transcript(self, con, d, contenido=b'{"type":"user"}\n'):
        wid = _add_req(con, "t")
        p = os.path.join(d, "t.jsonl")
        with open(p, "wb") as fh:
            fh.write(contenido)
        con.execute("UPDATE work SET remote_id=50, transcript_path=?, dirty=0 WHERE id=?", (p, wid)); con.commit()
        return wid, p

    def test_no_200_no_avanza_cursor_y_registra_en_su_par(self):
        con, _, d = _fresh_db()
        wid, _p = self._work_con_transcript(con, d)
        with mock.patch.object(logbook, "_http", _http_seq([(None, {"error": "TimeoutError", "detail": "timed out"})])):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertEqual(con.execute("SELECT count(*) FROM transcript_cursor").fetchone()[0], 0)
        r = _row(con, wid)
        self.assertEqual(r["transcript_error"], "transcript sin respuesta HTTP TimeoutError: timed out")
        self.assertIsNotNone(r["transcript_error_at"])
        self.assertIsNone(r["last_error"])                          # no toca el par de publish

    def test_publish_500_y_transcript_caido_no_se_pisan(self):
        """El caso que un solo par de columnas corrompía: ambos drenajes tocan la misma fila en un sync."""
        con, _, d = _fresh_db()
        wid, _p = self._work_con_transcript(con, d)
        con.execute("UPDATE work SET dirty=1 WHERE id=?", (wid,)); con.commit()

        def fake(endpoint, token, path, method="GET", payload=None):
            if path == "/work/publish":
                return 500, {"error": "server_error", "detail": "causa raiz"}
            return None, {"error": "URLError", "detail": "caido"}
        with mock.patch.object(logbook, "_http", fake):
            logbook._drain_works(con, "http://x", "tok")
            logbook._drain_transcripts(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertEqual(r["last_error"], "publish 500 server_error: causa raiz")
        self.assertEqual(r["transcript_error"], "transcript sin respuesta HTTP URLError: caido")

    def test_200_avanza_cursor_y_limpia_solo_su_par(self):
        con, _, d = _fresh_db()
        wid, p = self._work_con_transcript(con, d)
        con.execute("UPDATE work SET transcript_error='transcript 500 x', transcript_error_at='t', "
                    "last_error='publish 500 y', last_error_at='t' WHERE id=?", (wid,)); con.commit()
        with mock.patch.object(logbook, "_http", _http_seq([(200, {})])):
            logbook._drain_transcripts(con, "http://x", "tok")
        r = _row(con, wid)
        self.assertIsNone(r["transcript_error"]); self.assertIsNone(r["transcript_error_at"])
        self.assertEqual(r["last_error"], "publish 500 y")           # el par de publish queda intacto
        self.assertEqual(con.execute("SELECT synced_byte FROM transcript_cursor").fetchone()[0], os.path.getsize(p))

    def test_archivo_ausente_limpia_el_fallo(self):
        con, _, d = _fresh_db()
        wid, p = self._work_con_transcript(con, d)
        con.execute("UPDATE work SET transcript_error='transcript 500 x', transcript_error_at='t' WHERE id=?", (wid,))
        con.commit()
        os.remove(p)
        with mock.patch.object(logbook, "_http", _http_forbidden):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertIsNone(_row(con, wid)["transcript_error"])

    def test_al_dia_limpia_el_fallo_sin_hacer_red(self):
        con, _, d = _fresh_db()
        wid, p = self._work_con_transcript(con, d)
        con.execute("INSERT INTO transcript_cursor (session_id, work_id, synced_byte, updated_at) VALUES (?,?,?,?)",
                    ("sess-t", wid, os.path.getsize(p), "t"))
        con.execute("UPDATE work SET transcript_error='transcript 500 x', transcript_error_at='t' WHERE id=?", (wid,))
        con.commit()
        with mock.patch.object(logbook, "_http", _http_forbidden):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertIsNone(_row(con, wid)["transcript_error"])

    def test_mismo_fallo_de_transcript_conserva_desde_cuando(self):
        con, _, d = _fresh_db()
        wid, p = self._work_con_transcript(con, d)
        with mock.patch.object(logbook, "_http", _http_seq([(413, {"error": "too_large"})])):
            logbook._drain_transcripts(con, "http://x", "tok")
        con.execute("UPDATE work SET transcript_error_at='2026-01-01T00:00:00+00:00' WHERE id=?", (wid,)); con.commit()
        with open(p, "ab") as fh:
            fh.write(b'{"type":"user"}\n')                            # el archivo crece (sesión viva)
        with mock.patch.object(logbook, "_http", _http_seq([(413, {"error": "too_large"})])):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertEqual(_row(con, wid)["transcript_error_at"], "2026-01-01T00:00:00+00:00")

    def test_transcript_200_limpia_aunque_el_snapshot_no_viera_el_error(self):
        """Carrera: otro sync registra el fallo DESPUÉS de que este leyó su snapshot (prev=None) y ANTES de su 200.
        La limpieza del 200 no debe depender del snapshot: va en la misma transacción del cursor."""
        con, _, d = _fresh_db()
        wid, p = self._work_con_transcript(con, d)

        def fake(endpoint, token, path, method="GET", payload=None):
            con.execute("UPDATE work SET transcript_error='transcript 500 x', transcript_error_at='t' WHERE id=?", (wid,))
            con.commit()
            return 200, {}
        with mock.patch.object(logbook, "_http", fake):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertIsNone(_row(con, wid)["transcript_error"])

    def test_no_registra_si_el_cursor_avanzo_durante_el_post(self):
        con, _, d = _fresh_db()
        wid, p = self._work_con_transcript(con, d)

        def fake(endpoint, token, path, method="GET", payload=None):
            con.execute("INSERT INTO transcript_cursor (session_id, work_id, synced_byte, updated_at) VALUES (?,?,?,?)",
                        ("sess-t", wid, os.path.getsize(p), "t")); con.commit()      # otro sync lo subió
            return None, {"error": "TimeoutError"}
        with mock.patch.object(logbook, "_http", fake):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertIsNone(_row(con, wid)["transcript_error"])

    def test_fila_sana_no_genera_escrituras(self):
        """Limpieza CONDICIONAL: un work al día y sin fallo previo no debe emitir UPDATE (evita ~200 commits/sync)."""
        con, _, d = _fresh_db()
        wid, p = self._work_con_transcript(con, d)
        con.execute("INSERT INTO transcript_cursor (session_id, work_id, synced_byte, updated_at) VALUES (?,?,?,?)",
                    ("sess-t", wid, os.path.getsize(p), "t")); con.commit()
        before = con.total_changes
        with mock.patch.object(logbook, "_http", _http_forbidden):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertEqual(con.total_changes, before)


class TestMigrate(unittest.TestCase):

    def _legacy_db(self, extra_cols=()):
        d = tempfile.mkdtemp(prefix="neb-test-legacy-")
        path = os.path.join(d, "neb-logbook.db")
        c = sqlite3.connect(path)
        c.executescript(LEGACY_WORK_DDL)
        for col in extra_cols:
            c.execute(f"ALTER TABLE work ADD COLUMN {col} TEXT")
        c.execute("INSERT INTO work (mode, project, req_slug, created_at, updated_at) VALUES ('req','p','s','t','t')")
        c.commit(); c.close()
        return path

    def _cols(self, con):
        return [r[1] for r in con.execute("PRAGMA table_info(work)").fetchall()]

    def test_db_legacy_recibe_todas_las_columnas_y_es_idempotente(self):
        path = self._legacy_db()
        for _ in range(2):                                   # dos veces: idempotente
            con = _db_shared._connect(path, SCHEMA)
            self.assertIsNotNone(con)
            cols = self._cols(con)
            for c in ("conflict",) + NEW_COLS:
                self.assertIn(c, cols)
            self.assertEqual(con.execute("SELECT count(*) FROM work").fetchone()[0], 1)   # sin pérdida de filas
            con.close()

    def test_migracion_parcial_se_completa(self):
        path = self._legacy_db(extra_cols=("last_error",))   # un proceso murió a media migración
        con = _db_shared._connect(path, SCHEMA)
        self.assertIsNotNone(con)
        for c in ("conflict",) + NEW_COLS:
            self.assertIn(c, self._cols(con))
        con.close()

    def test_el_perdedor_de_la_carrera_no_pierde_la_conexion(self):
        """Dos procesos ven que la columna falta; el segundo ALTER da 'duplicate column name'. Se tolera."""
        path = self._legacy_db()
        real = sqlite3.connect(path)
        for _name, ddl in _db_shared._WORK_MIGRATIONS:
            real.execute(ddl)                                # el 'otro proceso' ya migró
        real.commit()

        class _StaleView:                                    # este proceso aún ve el table_info viejo
            def __init__(self, con): self._con = con
            def execute(self, sql, *a):
                if sql.startswith("PRAGMA table_info"):
                    class _R:
                        def fetchall(_s): return [(0, "id"), (1, "mode")]
                    return _R()
                return self._con.execute(sql, *a)
            def __getattr__(self, n): return getattr(self._con, n)

        _db_shared._migrate(_StaleView(real))                # no debe lanzar
        real.close()

    def test_otros_errores_si_se_propagan(self):
        """'database is locked' NO se traga: _connect debe devolver None (invariante: conexión = esquema completo)."""
        class _Locked:
            def execute(self, sql, *a):
                if sql.startswith("PRAGMA table_info"):
                    class _R:
                        def fetchall(_s): return [(0, "id")]
                    return _R()
                raise sqlite3.OperationalError("database is locked")
            def commit(self): pass
        with self.assertRaises(sqlite3.OperationalError):
            _db_shared._migrate(_Locked())

    def test_el_sql_vivo_parsea_y_trae_las_columnas(self):
        """Red de seguridad del archivo de mayor radio de explosión: una coma mal puesta en el .sql deja
        _connect en None para captura, sync, /logbook y pendings, en silencio."""
        m = sqlite3.connect(":memory:")
        with open(SCHEMA, encoding="utf-8") as fh:
            m.executescript(fh.read())
        cols = [r[1] for r in m.execute("PRAGMA table_info(work)").fetchall()]
        for c in ("conflict",) + NEW_COLS:
            self.assertIn(c, cols)
        self.assertEqual(sorted(n for n, _ in _db_shared._WORK_MIGRATIONS), sorted(("conflict",) + NEW_COLS))


class TestSyncStatus(unittest.TestCase):

    def _db(self):
        con, _path, _d = _fresh_db()
        ok = _add_req(con, "publicado")
        con.execute("UPDATE work SET dirty=0, remote_id=1 WHERE id=?", (ok,))
        pend = _add_req(con, "pendiente")                                     # dirty=1, sin error
        err = _add_req(con, "rechazado")
        con.execute("UPDATE work SET last_error='publish 500 x', last_error_at='t' WHERE id=?", (err,))
        conf = _add_req(con, "conflicto-viejo")                               # conflict=1 y dirty=0: heredado
        con.execute("UPDATE work SET dirty=0, conflict=1 WHERE id=?", (conf,))
        tx = _add_req(con, "transcript-roto")
        con.execute("UPDATE work SET dirty=0, remote_id=2, transcript_error='transcript 413', "
                    "transcript_error_at='t' WHERE id=?", (tx,))
        con.commit()
        return con, {"ok": ok, "pend": pend, "err": err, "conf": conf, "tx": tx}

    def test_filas_con_central(self):
        con, ids = self._db()
        rows = logbook._sync_status_rows(con, central=True)
        got = {r["local_id"] for r in rows}
        self.assertEqual(got, {ids["pend"], ids["err"], ids["conf"], ids["tx"]})   # el publicado sano NO aparece
        for r in rows:
            self.assertNotIn("id", r)                          # nunca `id`: con central los ids son remotos
            self.assertIn("remote_id", r)

    def test_sin_central_no_lista_los_dirty_sin_fallo(self):
        con, ids = self._db()
        got = {r["local_id"] for r in logbook._sync_status_rows(con, central=False)}
        self.assertEqual(got, {ids["err"], ids["conf"], ids["tx"]})

    def test_verbo_registrado_en_el_dispatcher(self):
        self.assertIn("sync-status", logbook.CLI_CMDS)         # si falta, cae a captura y sale mudo con rc=0

    def _run_cli(self, con, env):
        buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict", write_through=True)
        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch.object(logbook, "_db_for_cli", lambda: con), \
             mock.patch.object(logbook, "_http", _http_forbidden), \
             mock.patch.object(sys, "stdout", buf):
            logbook.cli_main(["sync-status"])
        return buf.buffer.getvalue()

    def test_cli_es_local_no_hace_red_y_reporta_precondiciones(self):
        con, ids = self._db()
        out = json.loads(self._run_cli(con, FAKE_ENV).decode("ascii"))     # ASCII puro
        self.assertEqual(out["scope"], "local")
        self.assertTrue(out["endpoint_set"]); self.assertTrue(out["token_set"])
        self.assertEqual(out["attention"], 3)                  # err + conf + tx (el pendiente sin fallo no cuenta)
        self.assertEqual({w["local_id"] for w in out["works"]}, {ids["pend"], ids["err"], ids["conf"], ids["tx"]})
        self.assertNotIn(FAKE_ENV["NEB_LOGBOOK_TOKEN"], json.dumps(out))   # booleanos, nunca el valor

    def test_cli_avisa_si_hay_endpoint_pero_falta_el_token(self):
        con, ids = self._db()
        env = {"NEB_LOGBOOK_ENDPOINT": "http://central.invalid", "NEB_LOGBOOK_TOKEN": ""}
        out = json.loads(self._run_cli(con, env).decode("ascii"))
        self.assertFalse(out["token_set"])
        self.assertTrue(any("NEB_LOGBOOK_TOKEN" in n for n in out["notes"]))
        self.assertIn(ids["pend"], {w["local_id"] for w in out["works"]})   # los dirty SÍ se listan: no se publican

    def test_cli_sin_endpoint_no_lista_los_dirty_y_trae_la_nota(self):
        con, ids = self._db()
        env = {"NEB_LOGBOOK_ENDPOINT": "", "NEB_LOGBOOK_TOKEN": ""}
        out = json.loads(self._run_cli(con, env).decode("ascii"))
        self.assertFalse(out["endpoint_set"])
        self.assertEqual({w["local_id"] for w in out["works"]}, {ids["err"], ids["conf"], ids["tx"]})
        self.assertTrue(any("Sin central" in n for n in out["notes"]))

    def test_cli_sin_db_imprime_json_con_error_no_vacio(self):
        buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict", write_through=True)
        with mock.patch.dict(os.environ, FAKE_ENV), mock.patch.object(logbook, "_db_for_cli", lambda: None), \
             mock.patch.object(logbook, "_http", _http_forbidden), mock.patch.object(sys, "stdout", buf):
            logbook.cli_main(["sync-status"])
        out = json.loads(buf.buffer.getvalue().decode("ascii"))
        self.assertIn("error", out)

    def test_cli_excepcion_tras_abrir_la_db_sale_por_stdout(self):
        """Si algo revienta después de abrir la DB, la salida NO puede quedar vacía con rc=0 (el skill lo leería
        como 'nada que avisar'): el error va en JSON por stdout."""
        con, _ids = self._db()
        buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict", write_through=True)
        with mock.patch.dict(os.environ, FAKE_ENV), mock.patch.object(logbook, "_db_for_cli", lambda: con), \
             mock.patch.object(logbook, "_sync_status_rows", side_effect=RuntimeError("no such table: work")), \
             mock.patch.object(sys, "stdout", buf):
            logbook.cli_main(["sync-status"])
        out = json.loads(buf.buffer.getvalue().decode("ascii"))
        self.assertIn("no such table", out["error"])

    def test_fila_completa_de_sync_status(self):
        """Aserción de fila completa: los índices del SELECT y las claves del dict no pueden cruzarse."""
        con, _p, _d = _fresh_db()
        wid = _add_req(con, "r")
        con.execute("UPDATE work SET dirty=1, conflict=0, remote_id=9, synced_at='S', last_error='LE', last_error_at='LEA', "
                    "transcript_error='TE', transcript_error_at='TEA', updated_at='U' WHERE id=?", (wid,)); con.commit()
        row = logbook._sync_status_rows(con, central=True)[0]
        self.assertEqual({k: row[k] for k in ("local_id", "mode", "project", "req_slug", "dirty", "conflict", "remote_id",
                                              "synced_at", "last_error", "last_error_at", "transcript_error",
                                              "transcript_error_at", "updated_at", "archived_at")},
                         {"local_id": wid, "mode": "req", "project": "host/o/repo", "req_slug": "r", "dirty": 1,
                          "conflict": 0, "remote_id": 9, "synced_at": "S", "last_error": "LE", "last_error_at": "LEA",
                          "transcript_error": "TE", "transcript_error_at": "TEA", "updated_at": "U", "archived_at": None})

    def test_cli_no_queda_vacio_con_caracteres_fuera_de_cp1252(self):
        """En un pipe cp1252 de Windows, ensure_ascii=False + '↔' daba 0 bytes con rc=0: 'nada atascado'."""
        con, ids = self._db()
        con.execute("UPDATE work SET last_error=? WHERE id=?", ("publish 500 a ↔ b", ids["err"])); con.commit()
        raw = self._run_cli(con, FAKE_ENV)
        self.assertGreater(len(raw), 0)
        out = json.loads(raw.decode("ascii"))
        self.assertIn("↔", [w for w in out["works"] if w["local_id"] == ids["err"]][0]["last_error"])

    def test_pendiente_de_transcript_calculado_al_vuelo(self):
        con, _path, d = _fresh_db()
        wid = _add_req(con, "t")
        p = os.path.join(d, "t.jsonl")
        with open(p, "wb") as fh:
            fh.write(b"x" * 1000)
        con.execute("UPDATE work SET dirty=0, remote_id=3, transcript_path=?, transcript_error='transcript 413', "
                    "transcript_error_at='t' WHERE id=?", (p, wid))
        con.execute("INSERT INTO transcript_cursor (session_id, work_id, synced_byte, updated_at) VALUES (?,?,?,?)",
                    ("sess-t", wid, 400, "t")); con.commit()
        row = logbook._sync_status_rows(con, central=True)[0]
        self.assertEqual(row["transcript_pending_bytes"], 600)


class TestCandadoReal(unittest.TestCase):
    """Otra conexión (una 'captura' de otra sesión) toma el candado de escritura y ESCRIBE mientras el sync
    intenta registrar/limpiar. Con un candado real, no con un proxy que lanza antes de tocar SQLite."""

    def _db(self, transcripts=False, slugs="ABC"):
        con, path, d = _fresh_db()
        for slug in slugs:
            t = os.path.join(d, slug + ".jsonl")
            with open(t, "wb") as fh:
                fh.write(b'{"type":"user"}\n' * 5)
            _add_req(con, slug)
            con.execute("UPDATE work SET transcript_path=? WHERE req_slug=?", (t, slug))
        if transcripts:
            con.execute("UPDATE work SET dirty=0, remote_id=id+100")
        con.commit()
        con.execute("PRAGMA busy_timeout=150")           # no esperar 5 s por caso: el mecanismo es el mismo
        return con, path

    def _http_con_locker(self, path, respuestas):
        """En el 1er POST otra conexión toma el candado y ESCRIBE (BEGIN IMMEDIATE + UPDATE); lo confirma en el 3º."""
        locker = sqlite3.connect(path, timeout=0.05, isolation_level=None)
        self.addCleanup(locker.close)
        n = {"i": 0}

        def http(ep, tok, p, method="GET", payload=None):
            i = n["i"]; n["i"] += 1
            if i == 0:
                locker.execute("BEGIN IMMEDIATE")
                # escribe SIN simular una captura (no toca updated_at/payload_version: eso dispararía el guard de versión)
                locker.execute("UPDATE work SET origin_machine='locked' WHERE req_slug='C'")
            if i == 2:
                locker.execute("COMMIT")
            return respuestas[min(i, len(respuestas) - 1)]
        return http

    def test_publicar_y_registrar_bajo_candado_no_tumban_el_drenaje(self):
        """A recibe 200 CON el candado tomado (su UPDATE choca), B recibe 500 bajo candado, C se publica tras liberarlo.
        Ni la rama 200 ni el registro del fallo pueden abortar el lote."""
        con, path = self._db()
        with mock.patch.object(logbook, "_http", self._http_con_locker(path, [(200, {"remote_id": 7}), (500, {"error": "server_error"}), (200, {"remote_id": 9})])):
            logbook._drain_works(con, "http://x", "tok")     # no debe lanzar
        self.assertFalse(con.in_transaction)                 # rollback real: nada colgado
        rows = {r["req_slug"]: r for r in [_row(con, i) for i in (1, 2, 3)]}
        self.assertEqual(rows["A"]["dirty"], 1)              # su 200 no pudo confirmarse: se reintentará
        self.assertEqual(rows["B"]["dirty"], 1)
        self.assertEqual(rows["C"]["dirty"], 0)              # el último, tras liberar el candado, se publicó
        self.assertEqual(rows["C"]["remote_id"], 9)

    def test_transcripts_bajo_candado_no_tumban_el_drenaje(self):
        """Con el candado tomado desde antes del drenaje: A está AL DÍA con un fallo previo (limpieza sin red),
        B recibe 500 (registro), C recibe 200 (el INSERT del cursor choca). D se publica tras liberarlo.
        Ninguna de las tres ramas puede abortar el lote."""
        con, path = self._db(transcripts=True, slugs="ABCD")
        con.execute("UPDATE work SET transcript_error='transcript 500 viejo', transcript_error_at='t'")
        ta = con.execute("SELECT transcript_path FROM work WHERE req_slug='A'").fetchone()[0]
        con.execute("INSERT INTO transcript_cursor (session_id, work_id, synced_byte, updated_at) VALUES ('sess-A', 1, ?, 't')",
                    (os.path.getsize(ta),))                  # A al día ⇒ entra al continue que limpia
        con.commit()
        locker = sqlite3.connect(path, timeout=0.05, isolation_level=None)
        self.addCleanup(locker.close)
        locker.execute("BEGIN IMMEDIATE"); locker.execute("UPDATE work SET origin_machine='locked' WHERE req_slug='D'")
        n = {"i": 0}

        def http(ep, tok, p, method="GET", payload=None):
            i = n["i"]; n["i"] += 1                          # i=0 → B, i=1 → C, i=2 → D
            if i == 2:
                locker.execute("COMMIT")                     # se libera antes del POST de D
            return [(500, {"error": "server_error"}), (200, {}), (200, {})][min(i, 2)]
        with mock.patch.object(logbook, "_http", http):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertFalse(con.in_transaction)
        cursores = {r[0] for r in con.execute("SELECT session_id FROM transcript_cursor")}
        self.assertEqual(cursores, {"sess-A", "sess-D"})    # C chocó con el candado: se reintentará
        self.assertIsNone(_row(con, 4)["transcript_error"])
        # y un drenaje posterior sobre la MISMA conexión sigue funcionando (no quedó tx colgada)
        with mock.patch.object(logbook, "_http", _http_seq([(200, {})])):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertIsNone(_row(con, 1)["transcript_error"])  # ahora sí, sin candado, A quedó limpio
        self.assertEqual(con.execute("SELECT count(*) FROM transcript_cursor").fetchone()[0], 4)


class TestSyncMainSobreDbMigrada(unittest.TestCase):

    def test_e2e_sobre_db_legacy_migrada(self):
        """sync_main completo (ambos drenajes) sobre una DB creada con el DDL VIEJO: la migración corre en el
        _connect del propio sync y el resultado se lee con otra conexión."""
        home = tempfile.mkdtemp(prefix="neb-test-syncmain-")
        os.makedirs(os.path.join(home, ".claude"))
        path = os.path.join(home, ".claude", "neb-logbook.db")
        c = sqlite3.connect(path); c.executescript(LEGACY_WORK_DDL)
        c.execute("CREATE TABLE IF NOT EXISTS transcript_cursor (session_id TEXT NOT NULL, work_id INTEGER NOT NULL, "
                  "synced_byte INTEGER NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (session_id, work_id))")
        t = os.path.join(home, "t.jsonl")
        with open(t, "wb") as fh:
            fh.write(b'{"type":"user"}\n' * 3)
        c.execute("INSERT INTO work (mode, project, req_slug, req_state, created_at, updated_at, dirty) "
                  "VALUES ('req','p','malo','x'*1, 't','t',1)")
        c.execute("INSERT INTO work (mode, project, req_slug, created_at, updated_at, dirty, remote_id, "
                  "claude_session_id, transcript_path) VALUES ('req','p','publicado','t','t',0,44,'s-pub',?)", (t,))
        c.commit(); c.close()
        guide = os.path.join(HERE, "..", "..")                          # NEB_HOME de la copia: hooks/logbook-schema.sql

        def fake(endpoint, token, path_, method="GET", payload=None):
            if path_ == "/work/publish":
                return 500, {"error": "server_error", "detail": "boom"}
            return 200, {}
        with mock.patch.dict(os.environ, FAKE_ENV), mock.patch.object(logbook, "_http", fake):
            logbook.sync_main([guide, home])
        other = sqlite3.connect(path); other.row_factory = sqlite3.Row
        self.assertFalse(other.execute("PRAGMA table_info(work)").fetchall() == [])
        malo = other.execute("SELECT dirty, last_error FROM work WHERE req_slug='malo'").fetchone()
        self.assertEqual(malo["dirty"], 1)
        self.assertEqual(malo["last_error"], "publish 500 server_error: boom")
        cur = other.execute("SELECT synced_byte FROM transcript_cursor WHERE session_id='s-pub'").fetchone()
        self.assertEqual(cur["synced_byte"], os.path.getsize(t))         # la 2ª mitad de sync_main también corrió
        rows = logbook._sync_status_rows(other, central=False)
        self.assertEqual([r["req_slug"] for r in rows], ["malo"])
        other.close()


class TestSyncMainYHttp(unittest.TestCase):

    def test_http_url_sin_esquema_no_lanza(self):
        import urllib.request
        with mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("no debe llegar a la red")):
            code, resp = logbook._http("central.invalid", "tok", "/work")
        self.assertIsNone(code)
        self.assertEqual(resp["error"], "ValueError")

    def test_http_respuesta_truncada_no_lanza(self):
        import http.client
        import urllib.request
        with mock.patch.object(urllib.request, "urlopen", side_effect=http.client.IncompleteRead(b"abc")):
            code, resp = logbook._http("http://central.invalid", "tok", "/work")
        self.assertIsNone(code)
        self.assertEqual(resp["error"], "IncompleteRead")

    def test_http_enmascara_un_token_con_salto_de_linea(self):
        """Un token pegado con CRLF hace que http.client lo eche en el ValueError ANTES de conectar."""
        tok = "tok-FALSO-0123456789abcdef"
        code, resp = logbook._http("http://127.0.0.1:9", tok + "\r\n", "/work")
        self.assertIsNone(code)
        self.assertNotIn(tok, resp["detail"])

    def test_central_hace_strip_del_token(self):
        with mock.patch.dict(os.environ, {"NEB_LOGBOOK_ENDPOINT": "http://central.invalid", "NEB_LOGBOOK_TOKEN": " t \r\n"}):
            self.assertEqual(logbook._central()[1], "t")

    def test_sync_manual_sin_central_avisa_en_vez_de_salir_mudo(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"NEB_LOGBOOK_ENDPOINT": "", "NEB_LOGBOOK_TOKEN": ""}, clear=False), \
             mock.patch.object(logbook, "_connect", side_effect=AssertionError("no debe abrir la DB")), \
             mock.patch.object(sys, "stderr", err):
            logbook.sync_main(["", tempfile.mkdtemp()])
        self.assertIn("central no configurado", err.getvalue())

    def test_http_conserva_el_motivo_cuando_no_hay_codigo(self):
        import urllib.error
        import urllib.request
        with mock.patch.object(urllib.request, "urlopen", side_effect=urllib.error.URLError("getaddrinfo failed")):
            code, resp = logbook._http("http://central.invalid", "tok", "/work")
        self.assertIsNone(code)
        self.assertEqual(resp["error"], "URLError")
        self.assertIn("getaddrinfo failed", resp["detail"])
        self.assertNotIn("tok", resp["detail"])


if __name__ == "__main__":
    unittest.main()
