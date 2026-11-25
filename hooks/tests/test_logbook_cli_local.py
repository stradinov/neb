#!/usr/bin/env python3
"""
test_logbook_cli_local.py — verbos locales de `/logbook`: list, show, rename y archive (neb 7.0.0).

  • list: works activos, sin columnas de equipo.
  • show: lista explícita de columnas (_SHOW_COLS); sobre una base que aún tiene las columnas retiradas
    (el paso de base 2 se detuvo, p. ej. con SQLite < 3.35.5) no las muestra, y ya no trae eventos. Esa
    base sigue operando con los pasos vigentes: desde 7.4.0 el paso 3 tiene espera (7.3.0 la bloqueaba).
  • rename: solo works `req`.
  • archive: archiva el work y, por pendings.on_work_archived, deja obsoletos sus pendientes abiertos.

Invariantes: DBs temporales (tempfile); nunca ~/.claude. _db_for_cli se reemplaza por una conexión nueva a
la base de la prueba en cada llamada (los verbos la cierran).
Framework: unittest (stdlib).
  py -m unittest tests.test_logbook_cli_local
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
LIB = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared
import _migrations
import logbook
import pendings

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
RETIRED_WORK = ("owner", "lock_state", "takeover_by", "locked_at", "payload_version", "origin_dev", "dirty",
                "synced_at", "remote_id", "conflict", "last_error", "last_error_at", "transcript_error",
                "transcript_error_at")
SHOW_COLS = ["id", "mode", "project", "req_slug", "req_state", "branch", "head_commit", "repo_path", "change_md",
             "payload_json", "origin_machine", "claude_session_id", "claude_session_name", "transcript_path",
             "created_at", "updated_at", "archived_at"]


class _Cli(unittest.TestCase):

    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(prefix="neb-test-cli-local-"), "neb.db")
        self.con = self._connect()
        self.addCleanup(self.con.close)

    def _connect(self):
        return _db_shared._connect(self.path, SCHEMA)

    def _cli(self, *args):
        buf = io.StringIO()
        with mock.patch.object(logbook, "_db_for_cli", self._connect), mock.patch.object(sys, "stdout", buf):
            logbook.cli_main(list(args))
        return buf.getvalue()

    def _req(self, slug, session="s"):
        wid = logbook._upsert_req(self.con, "host/o/repo", slug, "maq", "En progreso", "main", "abc", "C:\\repo",
                                  "changes/x.md", '{"plan":"p"}', session, "C:\\t\\s.jsonl")
        self.con.commit()
        return wid


class TestList(_Cli):

    def test_activos_mas_reciente_primero_sin_columnas_de_equipo(self):
        a = self._req("uno")
        b = logbook._upsert_exploratory(self.con, "E", "maq", "resumen", None, None, "C:\\c", None)
        c = self._req("archivado")
        self.con.execute("UPDATE work SET updated_at='2026-01-01' WHERE id=?", (a,))
        self.con.execute("UPDATE work SET updated_at='2026-01-02' WHERE id=?", (b,))
        self.con.execute("UPDATE work SET archived_at='t' WHERE id=?", (c,))
        self.con.commit()
        out = json.loads(self._cli("list"))
        self.assertEqual([w["id"] for w in out], [b, a])
        self.assertEqual(out[1], {"id": a, "mode": "req", "project": "host/o/repo", "req_slug": "uno",
                                  "req_state": "En progreso", "updated_at": "2026-01-01"})
        self.assertEqual(out[0]["project"], "")

    def test_sin_conexion_responde_lista_vacia(self):
        buf = io.StringIO()
        with mock.patch.object(logbook, "_db_for_cli", lambda: None), mock.patch.object(sys, "stdout", buf):
            logbook.cli_main(["list"])
        self.assertEqual(buf.getvalue().strip(), "[]")


class TestShow(_Cli):

    def test_columnas_explicitas_sin_eventos(self):
        wid = self._req("uno")
        out = json.loads(self._cli("show", str(wid)))
        self.assertEqual(list(out), SHOW_COLS)
        self.assertEqual((out["req_slug"], out["origin_machine"], out["archived_at"]), ("uno", "maq", None))

    def _legacy_base(self):
        path = os.path.join(tempfile.mkdtemp(prefix="neb-test-show-"), "neb.db")
        raw = sqlite3.connect(path)
        with open(SCHEMA, encoding="utf-8") as fh:            # esquema inicial = el de 6.45.0
            raw.executescript(fh.read())
        raw.execute("INSERT INTO work (id, mode, project, req_slug, owner, lock_state, dirty, remote_id, "
                    "created_at, updated_at) VALUES (7, 'req', 'p', 's', 'dev', 'owned', 1, 99, 't', 't')")
        raw.execute("INSERT INTO event (work_id, ts, dev, action) VALUES (7, 't', 'dev', 'publish')")
        raw.commit()
        raw.close()
        return path

    def test_paso_2_detenido_no_bloquea_la_base_desde_7_4_0(self):
        # Desde 7.4.0 el paso 3 tiene `espera`: con el paso 2 detenido, los pasos vigentes siguen operando la
        # base en la versión 1 (7.3.0 respondía paso-bloqueado). `show` responde el work, sin las columnas retiradas.
        self.path = self._legacy_base()
        with mock.patch.object(_migrations, "SQLITE_VERSION", (3, 34, 1)), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            out = json.loads(self._cli("show", "7"))
        self.assertEqual(list(out), SHOW_COLS, out)
        self.assertEqual((out["id"], out["req_slug"]), (7, "s"))
        c = sqlite3.connect(self.path)
        try:
            self.assertEqual(_migrations.read_version(c), (1, 1))
            self.assertTrue(set(RETIRED_WORK) <= {r[1] for r in c.execute("PRAGMA table_info(work)")})
        finally:
            c.close()

    def test_critico_base_con_las_columnas_retiradas_no_las_muestra(self):
        # Con solo los pasos 1 y 2 (como hasta 7.2.x) un paso 2 detenido deja operar la base: `show` no
        # expone las columnas retiradas aunque sigan en la tabla.
        self.path = self._legacy_base()
        path = self.path
        with mock.patch.object(_migrations, "SQLITE_VERSION", (3, 34, 1)),                 mock.patch.object(_migrations, "STEPS", tuple(s for s in _migrations.STEPS if s.n <= 2)):
            out = json.loads(self._cli("show", "7"))
        c = sqlite3.connect(path)
        cols = {r[1] for r in c.execute("PRAGMA table_info(work)")}
        c.close()
        self.assertTrue(set(RETIRED_WORK) <= cols)
        self.assertEqual(list(out), SHOW_COLS)
        self.assertNotIn("events", out)

    def test_no_encontrado_y_uso(self):
        self.assertEqual(self._cli("show", "999").strip(), "work 999 no encontrado")
        self.assertEqual(self._cli("show").strip(), "uso: show <id>")


class TestRename(_Cli):

    def test_renombra_solo_works_req(self):
        wid = self._req("viejo")
        eid = logbook._upsert_exploratory(self.con, "E", "maq", "", None, None, "C:\\c", None)
        self.con.commit()
        self.assertEqual(self._cli("rename", str(wid), "nuevo").strip(), f"rename OK (work {wid} → nuevo).")
        self._cli("rename", str(eid), "otro")
        c = self._connect()
        rows = dict(c.execute("SELECT id, req_slug FROM work"))
        c.close()
        self.assertEqual(rows, {wid: "nuevo", eid: None})

    def test_uso(self):
        self.assertEqual(self._cli("rename", "1").strip(), "uso: rename <id> <new_req_slug>")


class TestArchive(_Cli):

    def test_critico_archiva_el_work_y_deja_obsoleto_su_pendiente_abierto(self):
        wid = self._req("cerrar")
        otro = self._req("sigue")
        pid = pendings.create(self.con, "task", "ligado al REQ", work_ref=wid)
        libre = pendings.create(self.con, "task", "de otro REQ", work_ref=otro)
        self.con.commit()
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err):
            out = self._cli("archive", str(wid))
        self.assertEqual(out.strip(), f"archive OK (work {wid}).")
        self.assertEqual(err.getvalue(), "")
        c = self._connect()
        self.addCleanup(c.close)
        self.assertIsNotNone(c.execute("SELECT archived_at FROM work WHERE id=?", (wid,)).fetchone()[0])
        self.assertIsNone(c.execute("SELECT archived_at FROM work WHERE id=?", (otro,)).fetchone()[0])
        self.assertEqual(c.execute("SELECT status, obsolete_cause FROM pending WHERE id=?", (pid,)).fetchone(),
                         ("obsolete", "resolved-otherwise"))
        self.assertEqual(c.execute("SELECT note FROM pending_note WHERE pending_id=?", (pid,)).fetchall(),
                         [(f"[auto] work {wid} archivado -> obsoleto (resolved-otherwise)",)])
        self.assertEqual(c.execute("SELECT status FROM pending WHERE id=?", (libre,)).fetchone()[0], "open")

    def test_uso(self):
        self.assertEqual(self._cli("archive").strip(), "uso: archivar <id>")


class TestBaseSinMigrar(unittest.TestCase):

    def test_cada_verbo_local_responde_base_sin_migrar(self):
        err = _db_shared.UnmigratedDb("detalle de prueba", 'py "migrate-neb-db.py"')

        def _raise():
            raise err
        for args in (["list"], ["show", "1"], ["rename", "1", "x"], ["archive", "1"], ["trace", "x"]):
            with self.subTest(args=args):
                buf = io.StringIO()
                with mock.patch.object(logbook, "_db_for_cli", _raise), mock.patch.object(sys, "stdout", buf):
                    logbook.cli_main(args)
                self.assertEqual(json.loads(buf.getvalue()),
                                 {"ok": False, "motivo": "base-sin-migrar", "detalle": "detalle de prueba",
                                  "accion": err.accion, "comando": 'py "migrate-neb-db.py"'})


if __name__ == "__main__":
    unittest.main()
