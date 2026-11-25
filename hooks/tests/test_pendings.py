#!/usr/bin/env python3
"""
test_pendings.py — Sub-entrega A (REQ neb-pendings-sqlite).

Cubre el CRUD + ciclo de vida de pendings.py contra DBs TEMPORALES (tempfile):
  create / add_note / archive / revive (máquina de estados reversible e idempotente)
  enums en INGLES ('open'/'obsolete', 'no-longer-applies'/'resolved-otherwise')
  validación de entradas inválidas (type, obsolete_cause)
  resolve_session_context para pending type='session'
  on_work_archived (auto-obsolescencia reversible vía SAVEPOINT)
  archive / on_work_archived borran las sugerencias (curated=0) del pendiente que vuelve obsoleto
  base sin migrar: cada verbo del CLI que abre la base responde el JSON de base-sin-migrar

Framework: unittest (stdlib), NO pytest. NUNCA toca ~/.claude/*.db.
"""

import io
import os
import sys
import json
import sqlite3
import tempfile
import unittest
from unittest import mock

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
        wid = con.execute("INSERT INTO work (mode, created_at, updated_at) VALUES ('req',?,?)",
                          (_db_shared.now_iso(), _db_shared.now_iso())).lastrowid
        linked_open = pendings.create(con, "task", "ligado abierto", work_ref=wid)
        linked_obs  = pendings.create(con, "task", "ligado ya obsoleto", work_ref=wid)
        pendings.archive(con, linked_obs, "no-longer-applies")    # ya obsoleto antes del cierre
        unlinked    = pendings.create(con, "task", "no ligado")   # work_ref NULL
        con.commit()
        pendings.on_work_archived(con, wid)
        con.commit()
        self.assertEqual(con.execute("SELECT status, obsolete_cause FROM pending WHERE id=?", (linked_open,)).fetchone(),
                         ("obsolete", "resolved-otherwise"))
        # el que ya estaba obsoleto conserva su causa original (no-op del SAVEPOINT)
        self.assertEqual(con.execute("SELECT obsolete_cause FROM pending WHERE id=?", (linked_obs,)).fetchone()[0],
                         "no-longer-applies")
        # el no-ligado sigue abierto
        self.assertEqual(con.execute("SELECT status FROM pending WHERE id=?", (unlinked,)).fetchone()[0], "open")
        con.close()

    def _con_with_suggestions(self, n=2, work_ref=None):
        """Base con un tema curable y n pendientes con sugerencias del matching (curated=0) más una
        fila curada en el primero."""
        con = _fresh_con()
        tid = con.execute("INSERT INTO topic (slug, name, keywords, status) "
                          "VALUES ('seguridad','Seguridad','token, seguridad','active')").lastrowid
        otro = con.execute("INSERT INTO topic (slug, name, keywords, status) "
                           "VALUES ('tooling','Tooling','hook','active')").lastrowid
        pids = [pendings.create(con, "task", f"token expuesto {i} con un hook", work_ref=work_ref)
                for i in range(n)]
        for pid in pids:
            pendings.classify(con, pid, manage_tx=False)
        con.execute("UPDATE pending_topic SET curated=1 WHERE pending_id=? AND topic_id=?", (pids[0], otro))
        con.commit()
        self.assertTrue(all(self._suggestions(con, pid) > 0 for pid in pids[1:]))
        return con, pids, tid

    @staticmethod
    def _suggestions(con, pid):
        return con.execute("SELECT count(*) FROM pending_topic WHERE pending_id=? AND curated=0",
                           (pid,)).fetchone()[0]

    def test_archive_drops_suggestions_keeps_curated(self):
        con, pids, _tid = self._con_with_suggestions()
        self.assertEqual(pendings.archive(con, pids[0], "no-longer-applies"), 1)
        self.assertEqual(pendings.archive(con, pids[1], "resolved-otherwise"), 1)
        con.commit()
        for pid in pids:
            self.assertEqual(self._suggestions(con, pid), 0)
        self.assertEqual(con.execute("SELECT count(*) FROM pending_topic WHERE pending_id=? AND curated=1",
                                     (pids[0],)).fetchone()[0], 1)        # lo curado se conserva
        con.close()

    def test_on_work_archived_drops_suggestions_inside_its_savepoint(self):
        con, pids, _tid = self._con_with_suggestions(n=3)
        wid = con.execute("INSERT INTO work (mode, created_at, updated_at) VALUES ('req',?,?)",
                          (_db_shared.now_iso(), _db_shared.now_iso())).lastrowid
        con.execute("UPDATE pending SET work_ref=? WHERE id IN (?,?)", (wid, pids[0], pids[1]))
        con.commit()
        pendings.on_work_archived(con, wid)
        con.commit()
        self.assertEqual([self._suggestions(con, p) for p in pids[:2]], [0, 0])
        self.assertGreater(self._suggestions(con, pids[2]), 0)              # no ligado: intacto
        # falla sembrada: un error dentro del SAVEPOINT revierte también el borrado de sugerencias
        pendings.revive(con, pids[1]); pendings.classify(con, pids[1], manage_tx=False); con.commit()
        before = self._suggestions(con, pids[1])
        real_drop = pendings._drop_suggestions

        def drop_then_fail(c, pid):
            real_drop(c, pid)
            raise sqlite3.OperationalError("falla sembrada")
        with mock.patch.object(pendings, "_drop_suggestions", drop_then_fail):
            with self.assertRaises(sqlite3.OperationalError):
                pendings.on_work_archived(con, wid)
        con.commit()
        self.assertEqual(self._suggestions(con, pids[1]), before)
        self.assertEqual(con.execute("SELECT status FROM pending WHERE id=?", (pids[1],)).fetchone()[0], "open")
        con.close()

    def test_resolve_session_context(self):
        con = _fresh_con()
        payload = json.dumps({"summary": "exploración X"}, ensure_ascii=False)
        wid = con.execute("INSERT INTO work (mode, payload_json, transcript_path, created_at, updated_at) "
                          "VALUES ('exploratory',?,?,?,?)",
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


class TestResolvePendingRef(unittest.TestCase):
    """resolve_pending_ref: cita canónica por id (rowid) vs cita robusta por [slug].
    El #NNN del markdown histórico NO es clave (colisiona / reasignado en la migración)."""

    def _seed(self):
        con = _fresh_con()
        con.row_factory = __import__("sqlite3").Row
        # context_origin con prefijo "NN." histórico + tag [slug], como tras la migración
        pendings.create(con, "task", "153. [uma-pem-ppk-desfasados] regenerar pem desde ppk")
        pendings.create(con, "task", "30. [site-monitor] rotar keys PEM a forced-command")
        pendings.create(con, "task", "31. [site-monitor] drop tablas diagnostics_bak")
        con.commit()
        return con

    def test_resolve_by_id_plain_and_prefixed(self):
        con = self._seed()
        for ref in ("1", "#1", "PD-1", "pd-1"):
            kind, rows = pendings.resolve_pending_ref(con, ref)
            self.assertEqual(kind, "id")
            self.assertEqual([r["id"] for r in rows], [1])
        con.close()

    def test_resolve_by_exact_slug(self):
        con = self._seed()
        kind, rows = pendings.resolve_pending_ref(con, "uma-pem-ppk-desfasados")
        self.assertEqual(kind, "slug-exact")
        self.assertEqual([r["id"] for r in rows], [1])
        # también acepta el slug con corchetes
        kind2, rows2 = pendings.resolve_pending_ref(con, "[uma-pem-ppk-desfasados]")
        self.assertEqual([r["id"] for r in rows2], [1])
        con.close()

    def test_resolve_ambiguous_slug_returns_all(self):
        con = self._seed()
        kind, rows = pendings.resolve_pending_ref(con, "site-monitor")
        self.assertEqual(kind, "slug-exact")
        self.assertEqual(sorted(r["id"] for r in rows), [2, 3])
        con.close()

    def test_resolve_not_found(self):
        con = self._seed()
        kind, rows = pendings.resolve_pending_ref(con, "no-existe-xyz")
        self.assertEqual(rows, [])
        kind2, rows2 = pendings.resolve_pending_ref(con, "9999")
        self.assertEqual((kind2, rows2), ("id", []))
        con.close()

    def test_old_markdown_number_does_not_resolve_to_item(self):
        # el "153." vive solo como texto en context_origin; show 153 (id) no devuelve ese item
        con = self._seed()
        _, rows = pendings.resolve_pending_ref(con, "153")
        self.assertEqual(rows, [])  # no hay rowid 153
        con.close()


class TestBaseSinMigrar(unittest.TestCase):
    """HOME y USERPROFILE temporales con solo la bitácora de nombre anterior (poblada): cada verbo del CLI
    que abre la base responde el JSON de base-sin-migrar con la migración guiada y el comando del migrador,
    y no crea neb.db.
    write-compas no abre la base (escribe compas.md), así que no entra."""

    # Argumentos válidos para que cada verbo llegue a abrir la base.
    VERBOS = (
        ["create", "task", "algo"], ["note", "1", "texto"], ["archive", "1", "no-longer-applies"],
        ["revive", "1"], ["show", "1"], ["list"], ["triage"], ["rank", "criterio"], ["infer-objectives"],
        ["remember-session", "1"], ["curate", "1", "--band", "alta"], ["backfill-slugs"],
    )

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-test-sinmigrar-")
        self.base = os.path.join(self.home, ".claude")
        os.makedirs(self.base)
        self.legacy = os.path.join(self.base, _db_shared.LEGACY_DB_NAME)
        _db_shared._connect(self.legacy, SCHEMA).close()
        self.nuevo = _db_shared.resolve_db_path(self.home)

    def _cli(self, argv):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home}), \
                mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
            pendings.cli_main(list(argv))
        return json.loads(out.getvalue())

    def _esperado(self):
        # Con el mismo HOME que ve el CLI: así el comando no lleva --home (ese home es el de ~).
        with mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home}):
            err = _db_shared.unmigrated_legacy(self.home)
        self.assertIsNotNone(err)
        self.assertIn("migrate-neb-db.py", err.comando)
        self.assertIn(self.legacy, err.detalle)
        self.assertEqual(list(err.to_dict()), ["ok", "motivo", "detalle", "accion", "comando"])
        return err.to_dict()

    def _huella(self, path):
        with open(path, "rb") as fh:
            return fh.read(), os.path.getmtime(path)

    def test_cada_verbo_responde_base_sin_migrar_sin_crear_neb_db(self):
        esperado = self._esperado()
        antes = self._huella(self.legacy)
        for argv in self.VERBOS:
            with self.subTest(verbo=argv[0]):
                self.assertEqual(self._cli(argv), esperado)
        self.assertFalse(os.path.exists(self.nuevo))
        self.assertEqual(self._huella(self.legacy), antes)

    def test_neb_db_no_vacio_sin_work_pide_moverlo_y_no_se_toca(self):
        c = sqlite3.connect(self.nuevo)
        c.execute("CREATE TABLE otra (x)")
        c.commit()
        c.close()
        antes = self._huella(self.nuevo)
        esperado = self._esperado()
        self.assertIn(f"mueve fuera de {self.base} el neb.db que hay ahí ({os.path.getsize(self.nuevo)} bytes)",
                      esperado["detalle"])
        for argv in self.VERBOS:
            with self.subTest(verbo=argv[0]):
                self.assertEqual(self._cli(argv), esperado)
        self.assertEqual(self._huella(self.nuevo), antes)


if __name__ == "__main__":
    unittest.main()
