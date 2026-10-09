#!/usr/bin/env python3
"""
test_logbook_session_sync.py — cursor de subida POR SESIÓN (neb 6.12).

Antes de 6.12 el drenaje subía solo la sesión que cada work apuntaba en ese momento: una sesión que otra
pisaba en los works REQ antes de un sync perdía su cola para siempre. Ahora cada sesión tiene su fila en
session_sync, sube una sola vez y el sync va de a uno.

Invariantes de esta suite:
  • TODAS las DBs y homes son temporales (tempfile); NUNCA se toca ~/.claude.
  • NINGÚN test hace red: logbook._http se reemplaza siempre.
  • El entorno no hereda el endpoint/token reales (mock.patch.dict).

Framework: unittest (stdlib), NO pytest.
  py -m unittest hooks.tests.test_logbook_session_sync
"""

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared
import logbook

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
GUIDE  = os.path.join(HERE, "..", "..")                  # NEB_HOME de esta copia: hooks/logbook-schema.sql
FAKE_ENV = {"NEB_LOGBOOK_ENDPOINT": "http://central.invalid", "NEB_LOGBOOK_TOKEN": "tok-de-prueba-0123456789"}
NO_CENTRAL = {"NEB_LOGBOOK_ENDPOINT": "", "NEB_LOGBOOK_TOKEN": ""}
LINE = b'{"type":"user","message":{"content":"hola"}}\n'


def _home():
    h = tempfile.mkdtemp(prefix="neb-test-sesion-")
    os.makedirs(os.path.join(h, ".claude", "projects"))
    return h


def _jsonl(path, data=LINE * 3):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def _db(home):
    con = _db_shared._connect(_db_shared.resolve_db_path(home), SCHEMA)
    con.row_factory = sqlite3.Row
    return con


def _other(con):
    path = con.execute("PRAGMA database_list").fetchone()[2]
    o = sqlite3.connect(path, timeout=1.0)
    o.row_factory = sqlite3.Row
    return o


def _sess(con, sid):
    o = _other(con)
    try:
        return o.execute("SELECT * FROM session_sync WHERE session_id=?", (sid,)).fetchone()
    finally:
        o.close()


def _snapshot(con):
    o = _other(con)
    try:
        return [tuple(r) for r in o.execute(
            "SELECT session_id, work_id, transcript_path, synced_byte, transcript_error FROM session_sync "
            "ORDER BY session_id")]
    finally:
        o.close()


class _Central:
    """Central falso: publica works (remote_id = 1000 + id local de la llamada) y registra cada transcript."""

    def __init__(self, transcript_codes=None):
        self.transcripts = []
        self.publishes = []
        self._codes = list(transcript_codes or [])

    def __call__(self, endpoint, token, path, method="GET", payload=None, body=None, timeout=5):
        if payload is None and body is not None:
            payload = json.loads(body)
            payload["_body_len"] = len(body)
        if path == "/work/publish":
            self.publishes.append(payload)
            return 200, {"remote_id": 1000 + len(self.publishes)}
        if path == "/transcript":
            self.transcripts.append(payload)
            code = self._codes.pop(0) if self._codes else 200
            return code, ({} if code == 200 else {"error": "server_error"})
        raise AssertionError("ruta inesperada " + path)


def _capturar(home, cwd, sid, transcript, reqs):
    """Captura REAL (logbook.main) de la sesión `sid` en `cwd`, con `reqs` como REQ activos (el último
    escrito queda con mtime mayor). Sin central en el entorno: la captura no lanza sync."""
    mem = os.path.join(home, ".claude", "projects", _db_shared.encode_cwd(cwd), "memory")
    os.makedirs(mem, exist_ok=True)
    for i, name in enumerate(reqs):
        f = os.path.join(mem, f"active_p_{name}.md")
        if not os.path.exists(f):
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(f"- **Nombre:** {name}\n- **Path del proyecto:** {cwd}\n- **Estado:** En progreso\n")
            os.utime(f, (time.time() - 100 + i, time.time() - 100 + i))
    argv = ["logbook.py", sid, cwd, transcript, "Stop", GUIDE, home]
    with mock.patch.dict(os.environ, NO_CENTRAL), mock.patch.object(sys, "argv", argv):
        logbook.main()


def _sync(home, central):
    with mock.patch.dict(os.environ, FAKE_ENV), mock.patch.object(logbook, "_http", central):
        logbook.sync_main([GUIDE, home])


class TestPisado(unittest.TestCase):

    def test_critico_dos_sesiones_en_los_mismos_req_suben_ambas_una_vez(self):
        """[crítico] El defecto de PD-451: A captura en 2 REQ, B captura los mismos 2 REQ sin sync entre medio.
        Antes: solo subía B (2 veces, una por REQ) y A perdía su cola. Ahora: A y B, un POST cada una."""
        home, cwd = _home(), tempfile.mkdtemp(prefix="neb-cwd-")
        ta = _jsonl(os.path.join(home, ".claude", "projects", "x", "A.jsonl"), LINE * 4)
        tb = _jsonl(os.path.join(home, ".claude", "projects", "x", "B.jsonl"), LINE * 7)
        _capturar(home, cwd, "A", ta, ["r1", "r2"])
        _capturar(home, cwd, "B", tb, ["r1", "r2"])
        central = _Central()
        _sync(home, central)
        got = sorted((t["session_id"], t["byte_from"], t["byte_to"]) for t in central.transcripts)
        self.assertEqual(got, [("A", 0, os.path.getsize(ta)), ("B", 0, os.path.getsize(tb))])
        con = _db(home)
        self.assertEqual(_sess(con, "A")["synced_byte"], os.path.getsize(ta))
        self.assertEqual(_sess(con, "B")["synced_byte"], os.path.getsize(tb))
        # un segundo sync no reenvía nada
        central2 = _Central()
        _sync(home, central2)
        self.assertEqual(central2.transcripts, [])

    def test_la_sesion_se_atribuye_al_req_de_mtime_mas_reciente(self):
        home, cwd = _home(), tempfile.mkdtemp(prefix="neb-cwd-")
        t = _jsonl(os.path.join(home, ".claude", "projects", "x", "S.jsonl"))
        _capturar(home, cwd, "S", t, ["viejo", "nuevo"])          # 'nuevo' se escribe después: mtime mayor
        con = _db(home)
        wid = _sess(con, "S")["work_id"]
        self.assertEqual(con.execute("SELECT req_slug FROM work WHERE id=?", (wid,)).fetchone()[0], "nuevo")


class TestAtribucion(unittest.TestCase):

    def _works(self, con):
        a = logbook._upsert_req(con, "p", "a", "dev", "m", "x", None, None, "/r", "", "{}", "S", "/t")
        b = logbook._upsert_req(con, "p", "b", "dev", "m", "x", None, None, "/r", "", "{}", "S", "/t")
        con.commit()
        return a, b

    def test_prefiere_un_work_publicado(self):
        con = _db(_home())
        a, b = self._works(con)
        con.execute("UPDATE work SET remote_id=5 WHERE id=?", (b,))
        logbook._register_session(con, "S", "/t", [a, b]); con.commit()
        self.assertEqual(_sess(con, "S")["work_id"], b)

    def test_atribucion_fija_salvo_que_el_work_no_sea_publicable(self):
        con = _db(_home())
        a, b = self._works(con)
        con.execute("UPDATE work SET remote_id=5 WHERE id IN (?,?)", (a, b))
        logbook._register_session(con, "S", "/t", [a, b]); con.commit()
        logbook._register_session(con, "S", "/t2", [b, a]); con.commit()      # otra captura, otro orden
        self.assertEqual((_sess(con, "S")["work_id"], _sess(con, "S")["transcript_path"]), (a, "/t2"))

    def test_reasigna_si_el_work_quedo_en_conflicto(self):
        """Un relevo que terminó en 409 deja el work con remote_id y conflict=1: la sesión pasa a uno sano."""
        con = _db(_home())
        a, b = self._works(con)
        con.execute("UPDATE work SET remote_id=5 WHERE id IN (?,?)", (a, b))
        logbook._register_session(con, "S", "/t", [a, b]); con.commit()
        self.assertEqual(_sess(con, "S")["work_id"], a)
        con.execute("UPDATE work SET conflict=1 WHERE id=?", (a,)); con.commit()
        logbook._register_session(con, "S", "/t", [a, b]); con.commit()
        self.assertEqual(_sess(con, "S")["work_id"], b)

    def test_no_reasigna_a_uno_peor(self):
        """En conflicto pero publicado sigue siendo mejor que uno sin remote_id (este no puede recibir nada)."""
        con = _db(_home())
        a, b = self._works(con)
        con.execute("UPDATE work SET remote_id=5, conflict=1 WHERE id=?", (a,))
        logbook._register_session(con, "S", "/t", [a]); con.commit()
        logbook._register_session(con, "S", "/t", [b]); con.commit()          # b no tiene remote_id
        self.assertEqual(_sess(con, "S")["work_id"], a)

    def test_reasigna_si_el_work_quedo_sin_publicar(self):
        """El work de un 409 al nacer nunca recibe remote_id: la sesión no puede quedar atada a él."""
        con = _db(_home())
        a, b = self._works(con)
        con.execute("UPDATE work SET conflict=1 WHERE id=?", (a,))
        logbook._register_session(con, "S", "/t", [a]); con.commit()
        self.assertEqual(_sess(con, "S")["work_id"], a)
        con.execute("UPDATE work SET remote_id=9 WHERE id=?", (b,)); con.commit()
        logbook._register_session(con, "S", "/t", [a, b]); con.commit()
        self.assertEqual(_sess(con, "S")["work_id"], b)


class TestBackfill(unittest.TestCase):

    def test_critico_estado_heredado_sin_bajar_ningun_cursor_e_idempotente(self):
        """[crítico] Casos: solo pares · apuntada + pares · apuntada sin pares · work con transcript_path NULL
        (cuarentena heredada) · fila creada por la captura ANTES del backfill y pares escritos después."""
        home = _home()
        con = _db(home)
        w = {}
        for slug in ("w1", "w2", "w3", "w39", "w4", "w5", "w6"):
            w[slug] = logbook._upsert_req(con, "p", slug, "dev", "m", "x", None, None, "/r", "", "{}", None, None)
        con.execute("UPDATE work SET claude_session_id=NULL, transcript_path=NULL")
        con.execute("UPDATE work SET remote_id=id+100")
        cur = "INSERT INTO transcript_cursor (session_id, work_id, synced_byte, updated_at) VALUES (?,?,?,'t')"
        con.execute(cur, ("s1", w["w1"], 100)); con.execute(cur, ("s1", w["w2"], 300))      # solo pares
        con.execute("UPDATE work SET claude_session_id='s2', transcript_path='/x/s2.jsonl' WHERE id=?", (w["w3"],))
        con.execute("UPDATE work SET claude_session_id='s3', transcript_path=NULL WHERE id=?", (w["w39"],))
        con.execute("UPDATE work SET claude_session_id='s4', transcript_path='/x/s4.jsonl' WHERE id=?", (w["w4"],))
        con.execute(cur, ("s4", w["w5"], 500))                                              # apuntada + pares
        logbook._register_session(con, "s5", "/x/s5.jsonl", [w["w6"]])                       # captura primero...
        con.execute(cur, ("s5", w["w6"], 700))                                              # ...par después
        con.commit()
        logbook._backfill_sessions(con, None)
        got = {r[0]: (r[1], r[2], r[3]) for r in _snapshot(con)}
        self.assertEqual(got["s1"], (w["w2"], None, 300))
        self.assertEqual(got["s2"], (w["w3"], "/x/s2.jsonl", 0))
        self.assertEqual(got["s3"], (w["w39"], None, 0))
        self.assertEqual(got["s4"], (w["w4"], "/x/s4.jsonl", 500))
        self.assertEqual(got["s5"], (w["w6"], "/x/s5.jsonl", 700))
        before = _snapshot(con)
        logbook._backfill_sessions(con, None)
        self.assertEqual(_snapshot(con), before)

    def test_critico_una_fila_por_encima_de_sus_pares_no_baja(self):
        """[crítico] El MAX es hacia arriba: si 6.12 ya subió más de lo que dicen los pares heredados (el caso
        normal tras unos syncs), el backfill no lo regresa."""
        con = _db(_home())
        w = logbook._upsert_req(con, "p", "r", "dev", "m", "x", None, None, "/r", "", "{}", "S", "/t")
        con.execute("INSERT INTO transcript_cursor (session_id, work_id, synced_byte, updated_at) VALUES ('S',?,100,'t')", (w,))
        logbook._register_session(con, "S", "/t", [w])
        con.execute("UPDATE session_sync SET synced_byte=900 WHERE session_id='S'"); con.commit()
        logbook._backfill_sessions(con, None)
        self.assertEqual(_sess(con, "S")["synced_byte"], 900)

    def test_si_el_backfill_falla_no_adopta(self):
        """Con el backfill a medias, una sesión que solo tiene pares parecería huérfana y se re-enviaría desde 0."""
        con = _db(_home())
        with mock.patch.object(logbook, "_cursor_seed", side_effect=sqlite3.OperationalError("database is locked")), \
             mock.patch.object(logbook, "_adopt_orphans") as adopt:
            w = logbook._upsert_req(con, "p", "r", "dev", "m", "x", None, None, "/r", "", "{}", "S", "/t"); con.commit()
            logbook._backfill_sessions(con, None)
        adopt.assert_not_called()
        self.assertFalse(con.in_transaction)

    def test_una_sesion_con_pares_heredados_no_es_huerfana(self):
        home = _home()
        con = _db(home)
        w = logbook._upsert_req(con, "p", "r", "dev", "m", "x", None, None, "/r", "", "{}", None, None)
        con.execute("UPDATE work SET claude_session_id=NULL")
        con.execute("INSERT INTO transcript_cursor (session_id, work_id, synced_byte, updated_at) VALUES ('P',?,5,'t')", (w,))
        con.execute("INSERT INTO transcript_local (session_id, work_id, byte_from, byte_to, text_plain, created_at) "
                    "VALUES ('P', NULL, 0, 10, 'x', 't')")
        con.commit()
        _jsonl(os.path.join(home, ".claude", "projects", "d", "P.jsonl"))
        logbook._adopt_orphans(con, logbook._JsonlIndex(home))
        self.assertEqual(con.execute("SELECT count(*) FROM work WHERE mode='exploratory'").fetchone()[0], 0)

    def test_limpia_el_transcript_error_heredado_del_work(self):
        con = _db(_home())
        wid = logbook._upsert_req(con, "p", "r", "dev", "m", "x", None, None, "/r", "", "{}", "S", "/t")
        con.execute("UPDATE work SET transcript_error='transcript 500 viejo', transcript_error_at='t'"); con.commit()
        logbook._backfill_sessions(con, None)
        r = _other(con).execute("SELECT transcript_error, transcript_error_at FROM work WHERE id=?", (wid,)).fetchone()
        self.assertEqual(tuple(r), (None, None))


class TestDrenajeDiario(unittest.TestCase):

    def test_critico_sesion_nueva_sube_entera_y_luego_solo_deltas(self):
        """[crítico] Sin regresión del flujo de todos los días: 1 POST [0, size) con el remote_id correcto,
        y después solo lo que creció."""
        home, cwd = _home(), tempfile.mkdtemp(prefix="neb-cwd-")
        t = _jsonl(os.path.join(home, ".claude", "projects", "x", "E.jsonl"))
        _capturar(home, cwd, "E", t, [])                            # sin REQ: exploratorio
        c1 = _Central()
        _sync(home, c1)
        (p1,) = c1.transcripts
        self.assertEqual((p1["byte_from"], p1["byte_to"], p1["work_id"]), (0, os.path.getsize(t), 1001))
        size1 = os.path.getsize(t)
        with open(t, "ab") as fh:
            fh.write(LINE * 2)
        _capturar(home, cwd, "E", t, [])
        c2 = _Central()
        _sync(home, c2)
        (p2,) = c2.transcripts
        self.assertEqual((p2["byte_from"], p2["byte_to"], p2["work_id"]), (size1, os.path.getsize(t), 1001))


class TestAdopcionYRuta(unittest.TestCase):

    def _huerfana(self, home, sid, con, con_archivo=True):
        con.execute("INSERT INTO transcript_local (session_id, work_id, byte_from, byte_to, text_plain, created_at) "
                    "VALUES (?, NULL, 0, 10, 'x', 't')", (sid,))
        con.commit()
        if con_archivo:
            first = json.dumps({"type": "user", "cwd": "C:\\repo\\algo",
                                "message": {"content": "Planear un dashboard"}}).encode() + b"\n"
            return _jsonl(os.path.join(home, ".claude", "projects", "C--repo-algo", sid + ".jsonl"), first + LINE)
        return None

    def test_huerfana_se_adopta_se_publica_y_sube_en_un_sync(self):
        home = _home()
        con = _db(home)
        t = self._huerfana(home, "H", con)
        central = _Central()
        _sync(home, central)
        work = _other(con).execute("SELECT * FROM work WHERE claude_session_id='H'").fetchone()
        self.assertEqual(work["mode"], "exploratory")
        self.assertEqual(work["repo_path"], "C:\\repo\\algo")
        self.assertTrue(json.loads(work["payload_json"])["adopted"])
        self.assertIsNotNone(work["remote_id"])
        (p,) = central.transcripts
        self.assertEqual((p["session_id"], p["byte_to"], p["work_id"]), ("H", os.path.getsize(t), work["remote_id"]))

    def test_sin_jsonl_no_se_adopta(self):
        home = _home()
        con = _db(home)
        self._huerfana(home, "SIN", con, con_archivo=False)
        _sync(home, _Central())
        self.assertIsNone(_other(con).execute("SELECT id FROM work WHERE claude_session_id='SIN'").fetchone())
        self.assertIsNone(_sess(con, "SIN"))

    def test_adopcion_idempotente_y_carrera_de_unicidad(self):
        home = _home()
        con = _db(home)
        self._huerfana(home, "H", con)
        idx = logbook._JsonlIndex(home)
        logbook._adopt_orphans(con, idx)
        logbook._adopt_orphans(con, idx)
        self.assertEqual(con.execute("SELECT count(*) FROM work WHERE claude_session_id='H'").fetchone()[0], 1)
        self._huerfana(home, "H2", con)
        with mock.patch.object(logbook, "_upsert_exploratory", side_effect=sqlite3.IntegrityError("uq")):
            logbook._adopt_orphans(con, idx)                     # otro proceso ganó: no debe lanzar
        self.assertFalse(con.in_transaction)

    def test_ruta_guardada_inexistente_se_busca_por_nombre_y_se_corrige(self):
        home = _home()
        con = _db(home)
        wid = logbook._upsert_exploratory(con, "M", "dev", "m", "s", None, None, "/c", "C:\\vieja\\M.jsonl")
        con.execute("UPDATE work SET remote_id=7, dirty=0 WHERE id=?", (wid,))
        logbook._register_session(con, "M", "C:\\vieja\\M.jsonl", [wid]); con.commit()
        real = _jsonl(os.path.join(home, ".claude", "projects", "otro-dir", "M.jsonl"))
        central = _Central()
        _sync(home, central)
        (p,) = central.transcripts
        self.assertEqual((p["session_id"], p["byte_to"]), ("M", os.path.getsize(real)))
        self.assertEqual(_sess(con, "M")["transcript_path"], real)


def _body_len(sid, remote_id, start, data):
    """Largo del cuerpo serializado que manda _drain_transcripts (mismo armado y json.dumps por defecto)."""
    content = data.decode("utf-8", errors="replace")
    return len(json.dumps({"session_id": sid, "work_id": remote_id, "byte_from": start, "byte_to": start + len(data),
                           "content": content, "text_plain": logbook._extract_text_plain(content)}).encode("utf-8"))


# Fixture no-ASCII y densa en comillas: el JSON la escapa (\uXXXX, \") y el cuerpo pesa más que los bytes crudos.
DENSA = (json.dumps({"type": "user", "message": {"content": 'año "ñandú" → ✓ ' * 20}}, ensure_ascii=False)
         + "\n").encode("utf-8")


class TestTopeYPresupuesto(unittest.TestCase):

    def _sesion(self, con, d, sid, data):
        wid = logbook._upsert_exploratory(con, sid, "dev", "m", "s", None, None, "/c", os.path.join(d, sid + ".jsonl"))
        con.execute("UPDATE work SET remote_id=?, dirty=0 WHERE id=?", (500 + wid, wid))
        p = _jsonl(os.path.join(d, sid + ".jsonl"), data)
        logbook._register_session(con, sid, p, [wid]); con.commit()
        return 500 + wid, p

    def test_el_cuerpo_serializado_pesa_mas_que_los_bytes_crudos(self):
        self.assertGreater(_body_len("S", 1, 0, DENSA * 3), len(DENSA * 3) * 1.3)

    def test_borde_del_tope_en_bytes_serializados(self):
        for delta, sube in ((0, True), (-1, False)):
            home = _home()
            con = _db(home)
            rid, p = self._sesion(con, home, "T", DENSA * 3)
            tope = _body_len("T", rid, 0, DENSA * 3) + delta
            central = _Central()
            with mock.patch.object(logbook, "_http", central), \
                 mock.patch.object(logbook, "_TRANSCRIPT_BODY_MAX", tope), \
                 mock.patch.object(logbook, "_TRANSCRIPT_SYNC_BUDGET", 10 * tope):
                logbook._drain_transcripts(con, "http://x", "tok")
            self.assertEqual(len(central.transcripts), 1 if sube else 0, delta)
            s = _sess(con, "T")
            if sube:
                self.assertEqual(central.transcripts[0]["_body_len"], tope)
                self.assertIsNone(s["transcript_error"])
            else:
                self.assertEqual(s["transcript_error"], logbook._TRANSCRIPT_TOO_BIG)
                self.assertEqual(s["synced_byte"], 0)

    def test_texto_del_tope_fijo_conserva_desde_cuando(self):
        home = _home()
        con = _db(home)
        self._sesion(con, home, "G", LINE * 50)
        with mock.patch.object(logbook, "_TRANSCRIPT_BODY_MAX", 100), mock.patch.object(logbook, "_http", _Central()):
            logbook._drain_transcripts(con, "http://x", "tok")
            con.execute("UPDATE session_sync SET transcript_error_at='2026-01-01'"); con.commit()
            with open(_sess(con, "G")["transcript_path"], "ab") as fh:
                fh.write(LINE)                                  # crece: el pendiente cambia, el texto no
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertEqual(_sess(con, "G")["transcript_error_at"], "2026-01-01")

    def test_presupuesto_por_sync(self):
        home = _home()
        con = _db(home)
        ids = [self._sesion(con, home, f"P{i}", LINE * 10) for i in range(6)]
        un_cuerpo = _body_len("P0", ids[0][0], 0, LINE * 10)
        central = _Central()
        with mock.patch.object(logbook, "_http", central), \
             mock.patch.object(logbook, "_TRANSCRIPT_SYNC_BUDGET", 5 * un_cuerpo + 5):
            logbook._drain_transcripts(con, "http://x", "tok")
            self.assertEqual(len(central.transcripts), 5)
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertEqual(len(central.transcripts), 6)
        self.assertEqual(len({t["session_id"] for t in central.transcripts}), 6)

    def test_con_el_presupuesto_agotado_igual_marca_las_que_exceden_el_tope(self):
        home = _home()
        con = _db(home)
        rid, _ = self._sesion(con, home, "CHICA", LINE * 10)
        self._sesion(con, home, "ENORME", LINE * 400)
        un_cuerpo = _body_len("CHICA", rid, 0, LINE * 10)
        central = _Central()
        with mock.patch.object(logbook, "_http", central), \
             mock.patch.object(logbook, "_TRANSCRIPT_BODY_MAX", 4 * un_cuerpo), \
             mock.patch.object(logbook, "_TRANSCRIPT_SYNC_BUDGET", un_cuerpo - 1):   # ni la chica cabe
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertEqual(central.transcripts, [])
        self.assertEqual(_sess(con, "ENORME")["transcript_error"], logbook._TRANSCRIPT_TOO_BIG)
        self.assertIsNone(_sess(con, "CHICA")["transcript_error"])

    def test_central_caido_corta_los_envios_del_sync(self):
        home = _home()
        con = _db(home)
        for sid in ("A1", "A2", "A3"):
            self._sesion(con, home, sid, LINE * 3)
        calls = []

        def http(endpoint, token, path, method="GET", payload=None, body=None, timeout=5):
            calls.append(path)
            return None, {"error": "TimeoutError", "detail": "timed out"}
        with mock.patch.object(logbook, "_http", http):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertEqual(len(calls), 1)                          # el primero falla sin respuesta: se corta
        self.assertIsNotNone(_sess(con, "A1")["transcript_error"])

    def test_un_500_no_corta_a_las_demas(self):
        """Un 500 puede venir del contenido de una sesión: las demás siguen."""
        home = _home()
        con = _db(home)
        for sid in ("B1", "B2"):
            self._sesion(con, home, sid, LINE * 3)
        central = _Central(transcript_codes=[500, 200])
        with mock.patch.object(logbook, "_http", central):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertEqual(len(central.transcripts), 2)

    def test_menor_pendiente_primero(self):
        home = _home()
        con = _db(home)
        self._sesion(con, home, "GRANDE", LINE * 40)
        self._sesion(con, home, "CHICA", LINE * 2)
        central = _Central()
        with mock.patch.object(logbook, "_http", central):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertEqual([t["session_id"] for t in central.transcripts], ["CHICA", "GRANDE"])


class TestCandadoYMonotonia(unittest.TestCase):

    def test_con_el_candado_tomado_el_sync_sale_sin_red(self):
        home = _home()
        _db(home).close()
        lock = os.path.join(os.path.dirname(_db_shared.resolve_db_path(home)), logbook._SYNC_LOCK_NAME)
        open(lock, "w").close()
        with mock.patch.dict(os.environ, FAKE_ENV), \
             mock.patch.object(logbook, "_http", side_effect=AssertionError("no debe hacer red")):
            logbook.sync_main([GUIDE, home])
        self.assertTrue(os.path.exists(lock))                   # no es suyo: no lo borra

    def test_candado_rancio_se_toma_y_se_libera(self):
        home = _home()
        con = _db(home)
        wid = logbook._upsert_exploratory(con, "R", "dev", "m", "s", None, None, "/c", None); con.commit()
        lock = os.path.join(os.path.dirname(_db_shared.resolve_db_path(home)), logbook._SYNC_LOCK_NAME)
        open(lock, "w").close()
        viejo = time.time() - logbook._SYNC_LOCK_STALE_S - 5
        os.utime(lock, (viejo, viejo))
        central = _Central()
        _sync(home, central)
        self.assertEqual(len(central.publishes), 1)             # el sync corrió
        self.assertFalse(os.path.exists(lock))                   # y soltó el candado

    def test_solo_libera_el_candado_propio(self):
        home = _home()
        lock = os.path.join(home, logbook._SYNC_LOCK_NAME)
        with open(lock, "w") as fh:
            fh.write("999999 2026-01-01T00:00:00+00:00\n")       # otro proceso lo tomó por rancio
        logbook._release_sync_lock(lock)
        self.assertTrue(os.path.exists(lock))
        os.remove(lock)
        mine = logbook._acquire_sync_lock(home)
        self.assertEqual(mine, lock)
        logbook._release_sync_lock(mine)
        self.assertFalse(os.path.exists(lock))

    def test_el_dueno_refresca_el_candado_antes_de_cada_envio(self):
        home = _home()
        con = _db(home)
        wid = logbook._upsert_exploratory(con, "L", "dev", "m", "s", None, None, "/c", None)
        con.execute("UPDATE work SET remote_id=3, dirty=0 WHERE id=?", (wid,))
        logbook._register_session(con, "L", _jsonl(os.path.join(home, "L.jsonl")), [wid]); con.commit()
        lock = logbook._acquire_sync_lock(home)
        self.addCleanup(logbook._release_sync_lock, lock)
        viejo = time.time() - 3600
        os.utime(lock, (viejo, viejo))
        with mock.patch.object(logbook, "_http", _Central()):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertGreater(os.path.getmtime(lock), viejo + 3000)

    def test_un_200_tardio_no_baja_el_cursor(self):
        home = _home()
        con = _db(home)
        wid = logbook._upsert_exploratory(con, "C", "dev", "m", "s", None, None, "/c", None)
        con.execute("UPDATE work SET remote_id=3, dirty=0 WHERE id=?", (wid,))
        p = _jsonl(os.path.join(home, "C.jsonl"), LINE * 3)
        logbook._register_session(con, "C", p, [wid]); con.commit()

        def http(endpoint, token, path, method="GET", payload=None, body=None, timeout=5):
            con.execute("UPDATE session_sync SET synced_byte=999999 WHERE session_id='C'"); con.commit()   # otro ganó
            con.execute("INSERT INTO transcript_cursor (session_id, work_id, synced_byte, updated_at) "
                        "VALUES ('C', ?, 999999, 't')", (wid,)); con.commit()
            return 200, {}
        with mock.patch.object(logbook, "_http", http):
            logbook._drain_transcripts(con, "http://x", "tok")
        self.assertEqual(_sess(con, "C")["synced_byte"], 999999)
        o = _other(con)
        self.assertEqual(o.execute("SELECT synced_byte FROM transcript_cursor WHERE session_id='C'").fetchone()[0], 999999)
        o.close()


class TestSyncStatusSesiones(unittest.TestCase):

    def test_huerfana_sin_jsonl_aparece_como_perdida(self):
        home = _home()
        con = _db(home)
        con.execute("INSERT INTO transcript_local (session_id, work_id, byte_from, byte_to, text_plain, created_at) "
                    "VALUES ('PERDIDA', NULL, 0, 400, 'x', 't')"); con.commit()
        (s,) = logbook._sync_status_sessions(con, logbook._JsonlIndex(home))
        self.assertEqual((s["session_id"], s["status"], s["pending_bytes"]), ("PERDIDA", "jsonl-ausente", 400))

    def test_sin_central_solo_lista_fallos(self):
        """Un dev local-only: nada sube nunca, así que «esperando» o «pérdida» serían falsos."""
        home = _home()
        con = _db(home)
        w = logbook._upsert_req(con, "p", "r", "dev", "m", "x", None, None, "/r", "", "{}", "S", None)
        logbook._register_session(con, "ESPERA", _jsonl(os.path.join(home, "E.jsonl")), [w])
        logbook._register_session(con, "FALLA", None, [w])
        con.execute("UPDATE session_sync SET transcript_error='transcript 500' WHERE session_id='FALLA'")
        con.execute("INSERT INTO transcript_local (session_id, work_id, byte_from, byte_to, text_plain, created_at) "
                    "VALUES ('HUERFANA', NULL, 0, 400, 'x', 't')"); con.commit()
        got = [s["session_id"] for s in logbook._sync_status_sessions(con, logbook._JsonlIndex(home), central=False)]
        self.assertEqual(got, ["FALLA"])


class TestRollback(unittest.TestCase):

    def test_critico_un_200_escribe_tambien_el_cursor_heredado(self):
        """[crítico] Volver a un cliente 6.11 (que lee transcript_cursor) no debe re-enviar lo ya subido."""
        home = _home()
        con = _db(home)
        a = logbook._upsert_req(con, "p", "a", "dev", "m", "x", None, None, "/r", "", "{}", "S", None)
        con.execute("UPDATE work SET remote_id=40, dirty=0 WHERE id=?", (a,))
        p = _jsonl(os.path.join(home, "S.jsonl"), LINE * 5)
        logbook._register_session(con, "S", p, [a]); con.commit()
        with mock.patch.object(logbook, "_http", _Central()):
            logbook._drain_transcripts(con, "http://x", "tok")
        o = _other(con)
        self.assertEqual(tuple(o.execute("SELECT work_id, synced_byte FROM transcript_cursor WHERE session_id='S'")
                               .fetchone()), (a, os.path.getsize(p)))
        o.close()


if __name__ == "__main__":
    unittest.main()
