#!/usr/bin/env python3
"""
test_logbook_migracion_retiro.py — retiro de la subida de transcripts, del corpus local y de la búsqueda.

Cubre lo que el retiro deja en su lugar:
  • La migración de _db_shared borra transcript_fts, transcript_local y transcript_cursor en una sola
    transacción, siembra session_sync.read_byte y nunca hace que _connect devuelva None (módulo FTS5
    ausente, candado de escritura tomado por otra conexión, base que ya no tiene las tablas).
  • El lector solo-cursor de la captura (_read_new_chunk) entrega el tramo nuevo del .jsonl sin guardar texto.
  • `search` sigue en el diccionario de verbos retirados: responde su JSON sin tocar ni crear la base.

Invariantes: DBs y homes temporales (tempfile); nunca ~/.claude; ningún test hace red.
Framework: unittest (stdlib).
  py -m unittest hooks.tests.test_logbook_migracion_retiro
"""

import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
NEB_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, LIB)

import _db_shared
import logbook

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
RETIRADAS = ("transcript_fts", "transcript_local", "transcript_cursor")
MARCA = "texto-unico-de-la-conversacion-7f3a"
LINE = json.dumps({"type": "user", "message": {"content": MARCA}}).encode() + b"\n"

# DDL CONGELADO de las tablas retiradas y del session_sync previo a read_byte (neb ≤ 6.40). No se deriva del
# .sql vivo: ahí ya no existen.
LEGACY_SESSION_SYNC = """
CREATE TABLE session_sync (
  session_id TEXT PRIMARY KEY, work_id INTEGER REFERENCES work(id) ON DELETE SET NULL, transcript_path TEXT,
  synced_byte INTEGER NOT NULL DEFAULT 0, transcript_error TEXT, transcript_error_at TEXT,
  updated_at TEXT NOT NULL, root_cwd TEXT
);
"""
LEGACY_TRANSCRIPT_TABLES = """
CREATE TABLE transcript_cursor (
  session_id TEXT NOT NULL, work_id INTEGER NOT NULL REFERENCES work(id) ON DELETE CASCADE,
  synced_byte INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, PRIMARY KEY (session_id, work_id)
);
CREATE TABLE transcript_local (
  id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, work_id INTEGER NULL, byte_from INTEGER NOT NULL,
  byte_to INTEGER NOT NULL, text_plain TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX uq_transcript_local ON transcript_local(session_id, byte_from, byte_to);
CREATE INDEX idx_transcript_local_session ON transcript_local(session_id);
"""


def _fts5():
    m = sqlite3.connect(":memory:")
    try:
        m.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        m.close()


def _tables(path):
    c = sqlite3.connect(path)
    try:
        return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        c.close()


def _count(path, table):
    c = sqlite3.connect(path)
    try:
        return c.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        c.close()


def _legacy_db(with_fts=False):
    """Base como la deja neb ≤ 6.40: session_sync sin read_byte, las tablas retiradas con datos y relevo vivo.
    El resto del esquema sale del esquema inicial (el de 6.45.0: trae event, que el paso de base 2 borra)."""
    d = tempfile.mkdtemp(prefix="neb-test-retiro-")
    path = os.path.join(d, "neb.db")
    raw = sqlite3.connect(path)
    raw.executescript(LEGACY_SESSION_SYNC + LEGACY_TRANSCRIPT_TABLES)
    with open(SCHEMA, encoding="utf-8") as fh:
        raw.executescript(fh.read())                  # work, event, pendings… (session_sync queda la vieja)
    for i in (1, 2):
        raw.execute("INSERT INTO work (mode, project, req_slug, created_at, updated_at, claude_session_id) "
                    "VALUES ('req','p',?, 't','t', ?)", (f"r{i}", f"S{i}"))
        raw.execute("INSERT INTO event (work_id, ts, dev, action) VALUES (?, 't', 'dev', 'publish')", (i,))
    rows = (("S1", 0, 120), ("S1", 120, 500),        # MAX(byte_to) por sesión: S1 500, S2 300, S3 40
            ("S2", 0, 300),
            ("S3", 0, 40))
    for sid, a, b in rows:
        raw.execute("INSERT INTO transcript_local (session_id, work_id, byte_from, byte_to, text_plain, created_at) "
                    "VALUES (?, NULL, ?, ?, ?, 't')", (sid, a, b, MARCA))
    raw.execute("INSERT INTO transcript_cursor VALUES ('S1', 1, 500, 't')")
    for sid in ("S1", "S2", "S3", "S4"):             # S4: registrada, sin corpus
        raw.execute("INSERT INTO session_sync (session_id, synced_byte, updated_at) VALUES (?, 0, 't')", (sid,))
    if with_fts:
        raw.execute("CREATE VIRTUAL TABLE transcript_fts USING fts5(session_id UNINDEXED, text_plain)")
        raw.execute("INSERT INTO transcript_fts (session_id, text_plain) SELECT session_id, text_plain FROM transcript_local")
    raw.commit()
    raw.close()
    return path


def _connect_quiet(path):
    err = io.StringIO()
    with mock.patch.object(sys, "stderr", err):
        con = _db_shared._connect(path, SCHEMA)
    return con, err.getvalue()


class TestMigracion(unittest.TestCase):

    def test_critico_borra_las_tablas_siembra_read_byte_y_conserva_el_relevo(self):
        fts = _fts5()
        path = _legacy_db(with_fts=fts)
        if fts:
            self.assertTrue(any(t.startswith("transcript_fts_") for t in _tables(path)))   # tablas sombra
        antes = {t: _count(path, t) for t in ("work", "session_sync")}
        con, err = _connect_quiet(path)
        self.assertIsNotNone(con, err)
        con.close()
        quedan = _tables(path)
        self.assertEqual([t for t in quedan if t.startswith("transcript")], [], quedan)
        self.assertEqual({t: _count(path, t) for t in ("work", "session_sync")}, antes)
        self.assertNotIn("event", quedan)
        c = sqlite3.connect(path)
        cursores = dict(c.execute("SELECT session_id, read_byte FROM session_sync"))
        c.close()
        self.assertEqual(cursores, {"S1": 500, "S2": 300, "S3": 40, "S4": 0})
        con2, err2 = _connect_quiet(path)                                    # segundo _connect: limpio y sin aviso
        self.assertIsNotNone(con2)
        con2.close()
        self.assertEqual(err2, "")

    def test_no_baja_un_cursor_mayor_y_crea_la_fila_de_las_sesiones_sin_registro(self):
        path = _legacy_db()
        c = sqlite3.connect(path)
        c.execute("ALTER TABLE session_sync ADD COLUMN read_byte INTEGER NOT NULL DEFAULT 0")
        c.execute("UPDATE session_sync SET read_byte=900 WHERE session_id='S2'")
        c.execute("DELETE FROM session_sync WHERE session_id='S3'")
        c.commit()
        c.close()
        con, err = _connect_quiet(path)
        self.assertIsNotNone(con, err)
        got = {r[0]: (r[1], r[2]) for r in con.execute("SELECT session_id, read_byte, transcript_path FROM session_sync")}
        con.close()
        self.assertEqual(got["S2"], (900, None))
        self.assertEqual(got["S3"], (40, None))                             # fila mínima con su cursor

    def test_modulo_ausente_no_tumba_la_conexion_y_avisa(self):
        path = _legacy_db()
        c = sqlite3.connect(path)
        c.execute("PRAGMA writable_schema=ON")
        c.execute("INSERT INTO sqlite_master (type, name, tbl_name, rootpage, sql) VALUES "
                  "('table', 'transcript_fts', 'transcript_fts', 0, "
                  "'CREATE VIRTUAL TABLE transcript_fts USING modulo_que_no_existe(x)')")
        c.execute("PRAGMA writable_schema=OFF")
        c.commit()
        c.close()
        con, err = _connect_quiet(path)
        self.assertIsNotNone(con, err)
        self.assertIn("[logbook] aviso", err)
        self.assertEqual(con.execute("SELECT count(*) FROM work").fetchone()[0], 2)   # la conexión sirve
        # Solo se queda el índice cuyo módulo falta: las tablas con el texto y el cursor de subida se van.
        self.assertTrue(_db_shared._table_exists(con, "transcript_fts"))
        self.assertFalse(_db_shared._table_exists(con, "transcript_local"))
        self.assertFalse(_db_shared._table_exists(con, "transcript_cursor"))
        # La siembra va en su propia transacción: queda aunque un DROP falle.
        self.assertEqual(con.execute("SELECT read_byte FROM session_sync WHERE session_id='S1'").fetchone()[0], 500)
        con.close()
        con2, _ = _connect_quiet(path)                                      # se reintenta y sigue sirviendo
        self.assertIsNotNone(con2)
        con2.close()

    def test_candado_tomado_conexion_devuelta_y_limpieza_en_la_siguiente(self):
        path = _legacy_db()
        con0, _ = _connect_quiet(path)                                      # migra columnas y borra
        con0.close()
        # Base ya migrada en columnas: se reponen las tablas retiradas (cliente anterior en la misma máquina).
        c = sqlite3.connect(path)
        c.executescript(LEGACY_TRANSCRIPT_TABLES)
        c.execute("INSERT INTO transcript_local (session_id, work_id, byte_from, byte_to, text_plain, created_at) "
                  "VALUES ('S9', NULL, 0, 77, 'x', 't')")
        c.commit()
        c.close()
        locker = sqlite3.connect(path, isolation_level=None, timeout=0.1)
        self.addCleanup(locker.close)
        locker.execute("BEGIN IMMEDIATE")
        locker.execute("UPDATE work SET origin_machine='otra' WHERE id=1")
        con, err = _connect_quiet(path)
        self.assertIsNotNone(con, err)
        self.assertIn("[logbook] aviso", err)
        self.assertTrue(_db_shared._table_exists(con, "transcript_local"))
        self.assertFalse(con.in_transaction)
        self.assertEqual(con.execute("SELECT count(*) FROM work").fetchone()[0], 2)
        con.close()
        locker.execute("COMMIT")
        con2, err2 = _connect_quiet(path)
        self.assertIsNotNone(con2, err2)
        self.assertFalse(any(_db_shared._table_exists(con2, t) for t in RETIRADAS))
        self.assertEqual(con2.execute("SELECT read_byte FROM session_sync WHERE session_id='S9'").fetchone()[0], 77)
        con2.close()

    def test_critico_sin_siembra_el_lector_toma_el_cursor_de_transcript_local(self):
        # La siembra no llegó a correr (candado) y transcript_local sigue en la base: el lector de la captura
        # no relee la sesión desde el byte 0.
        path = _legacy_db()
        c = sqlite3.connect(path)
        c.execute("ALTER TABLE session_sync ADD COLUMN read_byte INTEGER NOT NULL DEFAULT 0")   # sin sembrar
        c.commit()
        d = os.path.dirname(path)
        jsonl = os.path.join(d, "S1.jsonl")
        with open(jsonl, "wb") as f:
            f.write(b"x" * 500 + LINE)                                      # 500 ya leídos por 6.40 + 1 línea nueva
        self.assertEqual(logbook._read_new_chunk(c, "S1", jsonl), LINE.decode())
        self.assertEqual(c.execute("SELECT read_byte FROM session_sync WHERE session_id='S1'").fetchone()[0],
                         500 + len(LINE))
        with open(jsonl, "wb") as f:
            f.write(b"x" * 500)                                             # sin nada nuevo tras el cursor heredado
        c.execute("UPDATE session_sync SET read_byte=0 WHERE session_id='S1'")
        self.assertIsNone(logbook._read_new_chunk(c, "S1", jsonl))
        c.close()

    def test_base_sin_las_tablas_no_pide_candado_ni_avisa(self):
        d = tempfile.mkdtemp(prefix="neb-test-retiro-")
        path = os.path.join(d, "neb.db")
        _db_shared._connect(path, SCHEMA).close()                          # base nueva: ya sin las tablas
        locker = sqlite3.connect(path, isolation_level=None, timeout=0.1)
        self.addCleanup(locker.close)
        locker.execute("BEGIN IMMEDIATE")
        locker.execute("INSERT INTO work (mode, created_at, updated_at) VALUES ('exploratory', 't', 't')")
        t0 = time.monotonic()
        con, err = _connect_quiet(path)
        elapsed = time.monotonic() - t0
        self.assertIsNotNone(con, err)
        con.close()
        self.assertEqual(err, "")
        self.assertLess(elapsed, 3.0)                                       # no esperó el busy_timeout de 5 s


class TestSearchRetirado(unittest.TestCase):

    DETALLE = ("se retiró en neb 6.41.0: la bitácora no guarda texto de sesiones. Para retomar un REQ usa su "
               "Change MD, su ## Relevo, el plan aprobado y la rama.")

    def _run(self, home, args):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("NEB_") and k not in ("PYTHONUTF8", "CLAUDE_PLUGIN_ROOT")}
        env.update(HOME=home, USERPROFILE=home, NEB_HOME=NEB_ROOT, PYTHONIOENCODING="cp1252")
        return subprocess.run([sys.executable, os.path.join(LIB, "logbook.py"), "search"] + args,
                              capture_output=True, env=env, timeout=60)

    def test_critico_search_con_1_y_con_6_o_mas_argumentos_responde_el_retiro_sin_tocar_la_base(self):
        home = tempfile.mkdtemp(prefix="neb-test-search-")
        os.makedirs(os.path.join(home, ".claude"))
        db = _db_shared.resolve_db_path(home)
        _db_shared._connect(db, SCHEMA).close()
        antes = {t: _count(db, t) for t in ("work", "session_sync")}
        for args in (["algo"], ["a", "b", "c", "d", "e"], ["a", "b", "Stop", "d", "e"],
                     ["a", "b", "c", "d", "e", "f"], []):
            r = self._run(home, args)
            self.assertEqual(r.returncode, 0, args)
            self.assertEqual(json.loads(r.stdout.decode("utf-8")),
                             {"ok": False, "motivo": "verbo-retirado", "verbo": "search", "detalle": self.DETALLE},
                             args)
            self.assertEqual({t: _count(db, t) for t in ("work", "session_sync")}, antes, args)

    def test_search_no_crea_la_base(self):
        home = tempfile.mkdtemp(prefix="neb-test-search-")
        os.makedirs(os.path.join(home, ".claude"))
        r = self._run(home, ["a", "b", "Stop", "d", "e"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(os.listdir(os.path.join(home, ".claude")), [])

    def test_search_vive_en_el_diccionario_de_retirados(self):
        self.assertEqual(logbook._RETIRED_VERBS["search"], {"detalle": self.DETALLE})
        self.assertNotIn("search", logbook.CLI_CMDS)


class TestLectorSoloCursor(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="neb-test-lector-")
        self.db = os.path.join(self.d, "neb.db")
        self.con = _db_shared._connect(self.db, SCHEMA)
        self.addCleanup(self.con.close)
        self.t = os.path.join(self.d, "S.jsonl")

    def _write(self, data, mode="wb"):
        with open(self.t, mode) as fh:
            fh.write(data)

    def test_critico_primero_todo_luego_solo_lo_nuevo_y_ningun_texto_guardado(self):
        self._write(LINE * 3)
        logbook._register_session(self.con, "S", self.t)
        self.assertEqual(logbook._read_new_chunk(self.con, "S", self.t), (LINE * 3).decode())
        self.con.commit()
        self.assertIsNone(logbook._read_new_chunk(self.con, "S", self.t))  # sin crecimiento
        self._write(b'{"type":"assistant"}\n', "ab")
        self.assertEqual(logbook._read_new_chunk(self.con, "S", self.t), '{"type":"assistant"}\n')
        self.con.commit()
        self.assertEqual(self.con.execute("SELECT read_byte FROM session_sync WHERE session_id='S'").fetchone()[0],
                         os.path.getsize(self.t))
        for (table,) in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for row in self.con.execute(f"SELECT * FROM {table}"):
                self.assertFalse(any(isinstance(v, str) and MARCA in v for v in row), table)

    def test_sin_jsonl_devuelve_none_y_no_escribe(self):
        self.assertIsNone(logbook._read_new_chunk(self.con, "S", os.path.join(self.d, "no-existe.jsonl")))
        self.assertIsNone(logbook._read_new_chunk(self.con, "S", None))
        self.assertEqual(self.con.execute("SELECT count(*) FROM session_sync").fetchone()[0], 0)

    def test_sin_fila_de_sesion_la_crea_con_el_cursor(self):
        self._write(LINE)
        self.assertEqual(logbook._read_new_chunk(self.con, "N", self.t), LINE.decode())
        self.assertEqual(tuple(self.con.execute("SELECT transcript_path, read_byte FROM session_sync "
                                                "WHERE session_id='N'").fetchone()), (self.t, len(LINE)))

    def test_captura_real_pasa_al_req_vinculado_solo_el_tramo_nuevo(self):
        home = os.path.join(self.d, "home")
        os.makedirs(os.path.join(home, ".claude"))
        cwd = os.path.join(self.d, "cwd")
        os.makedirs(cwd)
        self._write(LINE * 2)
        vistos = []
        argv = ["logbook.py", "S", cwd, self.t, "Stop", NEB_ROOT, home]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(logbook, "_after_capture", lambda con, sid, chunk, ev: vistos.append(chunk)):
            logbook.main()
            self._write(LINE, "ab")
            logbook.main()
            logbook.main()
        self.assertEqual(vistos, [(LINE * 2).decode(), LINE.decode(), None])


if __name__ == "__main__":
    unittest.main()
