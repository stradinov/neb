#!/usr/bin/env python3
"""
test_logbook_session_sync.py — registro de sesión (session_sync) y candado del sync.

session_sync guarda una fila por sesión: ruta del .jsonl, cwd con el que arrancó (opt-in de los works
exploratorios) y cursor de lectura del .jsonl. El sync registra las sesiones que un work apunta y no tienen
fila (backfill) y corre de a uno (candado).

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


# 6.14.2: el drenaje filtra por opt-in (marcador en el CLAUDE.md del repo o del dir donde arrancó la
# sesión). Estos tests no prueban eso: aquí todo dir cuenta como marcado. El opt-in se prueba en
# test_logbook_cli_and_drain.py. Sin _maybe_spawn_sync: una captura no lanza un sync real.
_OPTIN_PATCHES = (mock.patch.object(logbook, "_is_shared", lambda cwd: True),
                  mock.patch.object(logbook, "_maybe_spawn_sync", lambda *a, **k: None))


def setUpModule():
    for p in _OPTIN_PATCHES:
        p.start()


def tearDownModule():
    for p in _OPTIN_PATCHES:
        p.stop()


SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
GUIDE  = os.path.join(HERE, "..", "..")                  # NEB_HOME de esta copia: hooks/logbook-schema.sql
FAKE_ENV = {"NEB_LOGBOOK_ENDPOINT": "http://central.invalid", "NEB_LOGBOOK_TOKEN": "tok-de-prueba-0123456789"}
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
            "SELECT session_id, transcript_path, root_cwd FROM session_sync ORDER BY session_id")]
    finally:
        o.close()


class _Central:
    """Central falso: publica works (remote_id = 1000 + número de publicación). Otra ruta falla la prueba."""

    def __init__(self):
        self.publishes = []

    def __call__(self, endpoint, token, path, method="GET", payload=None):
        if path == "/work/publish":
            self.publishes.append(payload)
            return 200, {"remote_id": 1000 + len(self.publishes)}
        raise AssertionError("ruta inesperada " + path)


def _sync(home, central):
    with mock.patch.dict(os.environ, FAKE_ENV), mock.patch.object(logbook, "_http", central):
        logbook.sync_main([GUIDE, home])


class TestRegistro(unittest.TestCase):

    def test_registra_ruta_y_cwd_raiz_una_sola_vez(self):
        con = _db(_home())
        logbook._register_session(con, "S", "/t1", "C:\\repo"); con.commit()
        logbook._register_session(con, "S", "/t2", "C:\\otro"); con.commit()   # otra captura tras un `cd`
        s = _sess(con, "S")
        self.assertEqual((s["transcript_path"], s["root_cwd"], s["work_id"]), ("/t2", "C:\\repo", None))

    def test_completa_el_cwd_raiz_si_faltaba(self):
        con = _db(_home())
        logbook._register_session(con, "S", "/t", None); con.commit()        # .jsonl sin cwd legible aún
        logbook._register_session(con, "S", "/t", "C:\\repo"); con.commit()
        self.assertEqual(_sess(con, "S")["root_cwd"], "C:\\repo")


class TestBackfill(unittest.TestCase):

    def test_critico_registra_las_sesiones_apuntadas_por_un_work_e_idempotente(self):
        """[crítico] Casos: apuntada por un work con ruta · por un work con transcript_path NULL · por dos works
        (gana la ruta del más reciente) · ya registrada (no se toca)."""
        con = _db(_home())
        w = {}
        for slug in ("w1", "w2", "w3a", "w3b", "w4"):
            w[slug] = logbook._upsert_req(con, "p", slug, "dev", "m", "x", None, None, "/r", "", "{}", None, None)
        con.execute("UPDATE work SET claude_session_id='s1', transcript_path='/x/s1.jsonl' WHERE id=?", (w["w1"],))
        con.execute("UPDATE work SET claude_session_id='s2', transcript_path=NULL WHERE id=?", (w["w2"],))
        con.execute("UPDATE work SET claude_session_id='s3', transcript_path='/x/viejo.jsonl', updated_at='2026-01-01' "
                    "WHERE id=?", (w["w3a"],))
        con.execute("UPDATE work SET claude_session_id='s3', transcript_path='/x/s3.jsonl', updated_at='2026-02-01' "
                    "WHERE id=?", (w["w3b"],))
        con.execute("UPDATE work SET claude_session_id='s4', transcript_path='/x/w4.jsonl' WHERE id=?", (w["w4"],))
        logbook._register_session(con, "s4", "/x/s4.jsonl", "C:\\repo")                  # captura primero
        con.commit()
        logbook._backfill_sessions(con, None)
        got = {r[0]: (r[1], r[2]) for r in _snapshot(con)}
        self.assertEqual(got, {"s1": ("/x/s1.jsonl", None), "s2": (None, None), "s3": ("/x/s3.jsonl", None),
                               "s4": ("/x/s4.jsonl", "C:\\repo")})
        before = _snapshot(con)
        logbook._backfill_sessions(con, None)
        self.assertEqual(_snapshot(con), before)

    def test_si_el_backfill_falla_no_deja_transaccion_ni_lee_disco(self):
        con = _db(_home())
        logbook._upsert_req(con, "p", "r", "dev", "m", "x", None, None, "/r", "", "{}", "S", "/t"); con.commit()

        class _Locked:
            def __init__(self, c): self._c = c
            def executemany(self, *a): raise sqlite3.OperationalError("database is locked")
            def __getattr__(self, n): return getattr(self._c, n)
        with mock.patch.object(logbook, "_fill_root_cwd") as fill:
            logbook._backfill_sessions(_Locked(con), None)
        fill.assert_not_called()
        self.assertFalse(con.in_transaction)
        self.assertIsNone(_sess(con, "S"))

    def test_ruta_guardada_inexistente_el_cwd_raiz_se_lee_del_jsonl_hallado_por_nombre(self):
        home = _home()
        con = _db(home)
        logbook._upsert_exploratory(con, "M", "dev", "m", "s", None, None, "/c", "C:\\vieja\\M.jsonl"); con.commit()
        first = json.dumps({"type": "user", "cwd": "C:\\repo\\algo", "message": {"content": "x"}}).encode() + b"\n"
        _jsonl(os.path.join(home, ".claude", "projects", "otro-dir", "M.jsonl"), first)
        logbook._backfill_sessions(con, logbook._JsonlIndex(home))
        self.assertEqual(_sess(con, "M")["root_cwd"], "C:\\repo\\algo")


class TestCandado(unittest.TestCase):

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
        logbook._upsert_exploratory(con, "R", "dev", "m", "s", None, None, "/c", None)
        logbook._register_session(con, "R", None, "/c"); con.commit()
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

    def test_el_dueno_refresca_el_candado_antes_de_cada_publicacion(self):
        home = _home()
        con = _db(home)
        logbook._upsert_exploratory(con, "L", "dev", "m", "s", None, None, "/c", None)
        logbook._register_session(con, "L", None, "/c"); con.commit()
        lock = logbook._acquire_sync_lock(home)
        self.addCleanup(logbook._release_sync_lock, lock)
        viejo = time.time() - 3600
        os.utime(lock, (viejo, viejo))
        central = _Central()
        with mock.patch.object(logbook, "_http", central):
            logbook._drain_works(con, "http://x", "tok")
        self.assertEqual(len(central.publishes), 1)
        self.assertGreater(os.path.getmtime(lock), viejo + 3000)


if __name__ == "__main__":
    unittest.main()
