#!/usr/bin/env python3
"""
test_pendings_classify.py — Sub-entrega B (REQ neb-pendings-sqlite): temas y matching.

Cubre contra DBs TEMPORALES (tempfile):
  • sentinel 'sin-clasificar' (status='active' INGLES, idempotente)
  • classify por ruta FTS5 y por ruta LIKE (simulando FTS5 ausente con monkeypatch)
  • classify con match -> pending_topic; sin match -> sentinel
  • LIKE sin falso positivo de substring ('expedido' no matchea 'pedido')
  • normalización (acentos/idempotencia) con tokens reales del roadmap (catalogo, pedidos)
  • prioridad por tema: mismo pending con banda distinta en dos temas
  • reclassify solo toca el delta (last_reviewed_at)
  • triage_pass agrupa por topic compartido, NO O(N²) (sentinel no forma grupo gigante)
  • enums en INGLES de forma consistente (topic 'archived' nunca matchea)

Framework: unittest (stdlib), NO pytest. NUNCA toca ~/.claude/*.db.
"""

import contextlib
import io
import json
import os
import sys
import sqlite3
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared  # noqa: E402
import pendings  # noqa: E402

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")


def _new_topic(con, slug, name, keywords, status="active", parent_id=None):
    """Siembra un topic con status en INGLES ('active'). keywords = CSV de tokens."""
    cur = con.execute(
        "INSERT INTO topic (slug, name, description, keywords, status, parent_id) "
        "VALUES (?,?,?,?,?,?)", (slug, name, "", keywords, status, parent_id))
    con.commit()
    return cur.lastrowid


def _new_pending(con, context_origin, ptype="task", status="open"):
    """Siembra un pending con status en INGLES ('open')."""
    cur = con.execute(
        "INSERT INTO pending (type, context_origin, status, created_at) "
        "VALUES (?,?,?,?)", (ptype, context_origin, status, pendings.now_iso()))
    con.commit()
    return cur.lastrowid


class _Base(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.con = sqlite3.connect(self.db)
        with open(SCHEMA, encoding="utf-8") as f:
            self.con.executescript(f.read())   # incluye las 6 tablas de A (sin FTS5)

    def tearDown(self):
        self.con.close()
        for ext in ("", "-wal", "-shm"):
            try:
                os.remove(self.db + ext)
            except OSError:
                pass


# --------------------------------------------------------------------------- T1 sentinel

class TestSentinel(_Base):
    def test_sentinel_active_and_idempotent(self):
        a = pendings._ensure_sentinel(self.con)
        b = pendings._ensure_sentinel(self.con)
        self.assertEqual(a, b)  # mismo id, no duplica
        st = self.con.execute("SELECT status FROM topic WHERE id=?", (a,)).fetchone()[0]
        self.assertEqual(st, "active")  # INGLES, no 'activo'
        n = self.con.execute("SELECT count(*) FROM topic WHERE slug=?",
                             (pendings.SENTINEL_SLUG,)).fetchone()[0]
        self.assertEqual(n, 1)


# --------------------------------------------------------------------------- T2 ruta FTS5

class TestClassifyFTS(_Base):
    def setUp(self):
        super().setUp()
        if not pendings._fts5_available(self.con):
            self.skipTest("FTS5 no compilado en este Python")

    def test_classify_matches_topic_fts(self):
        tid = _new_topic(self.con, "catalogo", "Catálogo", "catalogo, pedidos")
        pid = _new_pending(self.con, "El cliente pide PEDIDO por catálogo en alpha")
        assigned = pendings.classify(self.con, pid)
        self.assertIn(tid, assigned)
        # debe haber tomado la ruta FTS
        self.assertTrue(pendings._ensure_fts(self.con))
        # is_primary marcado en el de mayor score
        prim = self.con.execute(
            "SELECT topic_id FROM pending_topic WHERE pending_id=? AND is_primary=1",
            (pid,)).fetchone()[0]
        self.assertEqual(prim, tid)


# --------------------------------------------------------------------------- T3 ruta LIKE (fallback)

class TestClassifyLike(_Base):
    def test_classify_matches_topic_like(self):
        orig = pendings._fts5_available
        pendings._fts5_available = lambda con: False   # fuerza ruta LIKE
        try:
            tid = _new_topic(self.con, "catalogo", "Catálogo", "catalogo, pedidos")
            pid = _new_pending(self.con, "Pedido por catalogo sin acentos")
            assigned = pendings.classify(self.con, pid)
            self.assertIn(tid, assigned)
            self.assertFalse(pendings._ensure_fts(self.con))  # confirma ruta LIKE
        finally:
            pendings._fts5_available = orig

    def test_like_no_false_positive_substring(self):
        # 'expedido' NO debe matchear el token 'pedido' por substring
        orig = pendings._fts5_available
        pendings._fts5_available = lambda con: False
        try:
            _new_topic(self.con, "logistica", "Logística", "pedido")
            pid = _new_pending(self.con, "paquete expedido a tiempo")
            assigned = pendings.classify(self.con, pid)
            sent = self.con.execute("SELECT id FROM topic WHERE slug=?",
                                    (pendings.SENTINEL_SLUG,)).fetchone()[0]
            self.assertEqual(assigned, [sent])  # cae al sentinel, no falso positivo
        finally:
            pendings._fts5_available = orig


# --------------------------------------------------------------------------- T4 normalización

class TestNormalization(_Base):
    def test_roadmap_tokens_match_with_accents_and_spaces(self):
        # roadmap real alpha: 'catalogo, pedidos' (con acentos/espacios en el origen)
        tid = _new_topic(self.con, "alpha-catalogo", "Catálogo alpha", "catálogo, pedidos")
        pid = _new_pending(self.con, "Revisar el CATÁLOGO de Pedidos en alpha")
        assigned = pendings.classify(self.con, pid)
        self.assertIn(tid, assigned)

    def test_normalize_idempotent_and_diacritics(self):
        self.assertEqual(pendings.normalize("Catálogo"), "catalogo")
        self.assertEqual(pendings.normalize(pendings.normalize("PÉDIDOS")), "pedidos")
        self.assertEqual(pendings.normalize(None), "")


# --------------------------------------------------------------------------- T5 sin match -> sentinel

class TestNoMatch(_Base):
    def test_no_match_falls_to_sentinel(self):
        _new_topic(self.con, "catalogo", "Catálogo", "catalogo, pedidos")
        pid = _new_pending(self.con, "Configurar el backup nocturno del servidor de correo")
        assigned = pendings.classify(self.con, pid)
        sent = self.con.execute("SELECT id FROM topic WHERE slug=?",
                                (pendings.SENTINEL_SLUG,)).fetchone()[0]
        self.assertEqual(assigned, [sent])


# --------------------------------------------------------------------------- T6 prioridad por tema

class TestPriorityPerTopic(_Base):
    def test_distinct_band_per_topic(self):
        t_strong = _new_topic(self.con, "t1", "Pagos", "pago, factura, cobro")   # 3 tokens
        t_weak   = _new_topic(self.con, "t2", "Reporte", "reporte")              # 1 token
        pid = _new_pending(self.con, "Reporte de pago factura y cobro pendiente")
        pendings.classify(self.con, pid)
        bands = dict(self.con.execute(
            "SELECT topic_id, priority_band FROM pending_topic WHERE pending_id=?", (pid,)))
        self.assertEqual(bands[t_strong], "high")    # >=3 tokens
        self.assertEqual(bands[t_weak], "low")       # 1 token
        self.assertNotEqual(bands[t_strong], bands[t_weak])


# --------------------------------------------------------------------------- T7 reclassify delta

class TestReclassifyDelta(_Base):
    def test_reclassify_only_unreviewed(self):
        _new_topic(self.con, "catalogo", "Catálogo", "catalogo, pedidos")
        p1 = _new_pending(self.con, "catalogo nuevo")
        pendings.classify(self.con, p1)   # p1 queda con last_reviewed_at != NULL
        p2 = _new_pending(self.con, "pedidos atrasados")  # nunca revisado
        res = pendings.reclassify(self.con)  # since=None -> solo NULL
        self.assertIn(p2, res)
        self.assertNotIn(p1, res)

    def test_reclassify_after_editing_keywords(self):
        # tema sin keyword que matchee -> pending cae al sentinel
        t = _new_topic(self.con, "infra", "Infra", "ssh")
        pid = _new_pending(self.con, "rotar credenciales del backup")
        pendings.classify(self.con, pid)
        sent = self.con.execute("SELECT id FROM topic WHERE slug=?",
                                (pendings.SENTINEL_SLUG,)).fetchone()[0]
        self.assertEqual([r[0] for r in self.con.execute(
            "SELECT topic_id FROM pending_topic WHERE pending_id=?", (pid,))], [sent])
        # editar keywords del tema para que ahora matchee 'backup' + 'credenciales'
        self.con.execute("UPDATE topic SET keywords=? WHERE id=?",
                         ("backup, credenciales", t))
        self.con.commit()
        # re-clasificar este pending (replace=True) -> ahora apunta al tema, no al sentinel
        pendings.classify(self.con, pid)
        topics_now = [r[0] for r in self.con.execute(
            "SELECT topic_id FROM pending_topic WHERE pending_id=?", (pid,))]
        self.assertIn(t, topics_now)
        self.assertNotIn(sent, topics_now)


# --------------------------------------------------------------------------- T8 triage_pass agrupa (NO O(N²))

class TestTriageGrouping(_Base):
    def test_groups_by_shared_topic_and_sentinel_excluded(self):
        _new_topic(self.con, "catalogo", "Catálogo", "catalogo, pedidos")
        pa = _new_pending(self.con, "catalogo roto")
        pb = _new_pending(self.con, "pedidos del catalogo")
        # 3 pendings sin match -> todos al sentinel; NO deben formar grupo entre sí
        s1 = _new_pending(self.con, "backup correo")
        s2 = _new_pending(self.con, "rotar llaves ssh")
        s3 = _new_pending(self.con, "actualizar firmware router")
        out = pendings.triage_pass(self.con)
        # pa y pb comparten topic -> un grupo
        self.assertTrue(any(set(g) == {pa, pb} for g in out["groups"]))
        # los del sentinel van a unclassified, NO a groups
        self.assertEqual(set(out["unclassified"]), {s1, s2, s3})
        for g in out["groups"]:
            self.assertFalse({s1, s2, s3} & set(g))  # sentinel nunca agrupa


# --------------------------------------------------------------------------- T9 enums INGLES consistentes

class TestEnumsEnglish(_Base):
    def test_classify_queries_use_active_english(self):
        # un topic 'archived' NO debe matchear nunca
        _new_topic(self.con, "viejo", "Viejo", "catalogo", status="archived")
        ok = _new_topic(self.con, "vigente", "Vigente", "catalogo", status="active")
        pid = _new_pending(self.con, "catalogo pendiente")
        assigned = pendings.classify(self.con, pid)
        self.assertIn(ok, assigned)
        self.assertNotIn(self.con.execute(
            "SELECT id FROM topic WHERE slug='viejo'").fetchone()[0], assigned)


# --------------------------------------------------------------------------- BLOQUEANTE 1: /pendings triage vivo
# Antes de la corrección, la cadena cli_triage -> _with_write_tx -> triage_pass -> reclassify
# -> classify anidaba un segundo BEGIN IMMEDIATE ('cannot start a transaction within a
# transaction') y reventaba en el ROLLBACK ('cannot rollback - no transaction is active').

class TestTriageEndToEnd(unittest.TestCase):
    """Ruta REAL del verbo CLI 'triage' contra una DB temporal (NUNCA ~/.claude)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-triage-")
        os.makedirs(os.path.join(self.tmp, ".claude"), exist_ok=True)
        self.db = _db_shared.resolve_db_path(self.tmp)
        # siembra: 2 pendings que comparten tema + 1 sin clasificar
        con = _db_shared._connect(self.db, SCHEMA)
        _new_topic(con, "catalogo", "Catálogo", "catalogo, pedidos")
        _new_pending(con, "catalogo roto en alpha")
        _new_pending(con, "pedidos atrasados del catalogo")
        _new_pending(con, "rotar llaves ssh del bastion")
        con.close()

    def tearDown(self):
        for ext in ("", "-wal", "-shm"):
            try:
                os.remove(self.db + ext)
            except OSError:
                pass

    def test_cli_triage_runs_and_emits_useful_output(self):
        # cli_triage abre su propia conexión vía _db_for_cli: la apuntamos al tempfile.
        def _temp_con():
            return _db_shared._connect(self.db, SCHEMA)

        buf = io.StringIO()
        with mock.patch.object(pendings, "_db_for_cli", _temp_con), \
                contextlib.redirect_stdout(buf):
            pendings.cli_triage([])           # NO debe lanzar (antes: OperationalError en ROLLBACK)
        out = json.loads(buf.getvalue())      # salida útil = JSON parseable
        self.assertGreaterEqual(out["classified"], 2)            # los 2 con tema fueron clasificados
        # los dos del mismo tema forman un grupo
        self.assertTrue(any(len(g) == 2 for g in out["groups"]),
                        f"esperaba un grupo de 2; groups={out['groups']}")
        # el ssh cae a sin-clasificar (sentinel)
        self.assertEqual(len(out["unclassified"]), 1)
        # cada item trae banda/score (presentación) — salida útil para el skill
        self.assertTrue(all("band" in it and "score" in it for it in out["items"]))
        # y la clasificación PERSISTIÓ (el COMMIT del _with_write_tx funcionó)
        con = _db_shared._connect(self.db, SCHEMA)
        self.assertGreaterEqual(
            con.execute("SELECT count(*) FROM pending_topic").fetchone()[0], 3)
        con.close()


class TestWriteTxLockedRetryRollback(unittest.TestCase):
    """BLOQUEANTE 1 (ii): cuando BEGIN IMMEDIATE da 'locked', NO debe reventar el ROLLBACK
    (defensivo: no hay transacción que revertir). El retry debe correr y, si el lock cede,
    completar; el caso terminal (sigue locked) propaga el OperationalError de BEGIN, NO el
    'cannot rollback - no transaction is active'."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-lock-")
        os.makedirs(os.path.join(self.tmp, ".claude"), exist_ok=True)
        self.db = _db_shared.resolve_db_path(self.tmp)
        _db_shared._connect(self.db, SCHEMA).close()

    def tearDown(self):
        for ext in ("", "-wal", "-shm"):
            try:
                os.remove(self.db + ext)
            except OSError:
                pass

    def test_locked_on_begin_immediate_then_succeeds_on_retry(self):
        con = _db_shared._connect(self.db, SCHEMA)
        # primer BEGIN IMMEDIATE falla 'locked' (sin transacción abierta); segundo pasa.
        real_begin = _db_shared.begin_immediate
        calls = {"n": 0}

        def flaky_begin(c):
            calls["n"] += 1
            if calls["n"] == 1:
                raise sqlite3.OperationalError("database is locked")
            return real_begin(c)

        with mock.patch.object(_db_shared, "begin_immediate", flaky_begin):
            # _with_write_tx (alias de _db_shared.with_write_tx) NO debe lanzar el error de ROLLBACK
            pid = pendings._with_write_tx(
                con, lambda c: pendings.create(c, "task", "creado tras reintento"))
        self.assertEqual(calls["n"], 2)   # hubo exactamente un reintento
        self.assertEqual(
            con.execute("SELECT context_origin FROM pending WHERE id=?", (pid,)).fetchone()[0],
            "creado tras reintento")
        con.close()

    def test_persistently_locked_propagates_begin_error_not_rollback_error(self):
        con = _db_shared._connect(self.db, SCHEMA)

        def always_locked(c):
            raise sqlite3.OperationalError("database is locked")

        with mock.patch.object(_db_shared, "begin_immediate", always_locked):
            with self.assertRaises(sqlite3.OperationalError) as ctx:
                pendings._with_write_tx(con, lambda c: pendings.create(c, "task", "x"), retries=2)
        # el error propagado es el de BEGIN (locked), NO el 'no transaction is active' del ROLLBACK
        self.assertIn("locked", str(ctx.exception).lower())
        self.assertNotIn("no transaction is active", str(ctx.exception).lower())
        con.close()


# --------------------------------------------------------------------------- BLOQUEANTE 2: sin triggers FTS
# Sin los 6 triggers persistentes, NINGUNA escritura cruda en pending/topic toca FTS5 → el
# camino de pérdida de datos (escritura del logbook acoplada a un FTS5 que falla) queda cerrado.

class TestNoFtsTriggers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-noftstrig-")
        os.makedirs(os.path.join(self.tmp, ".claude"), exist_ok=True)
        self.db = _db_shared.resolve_db_path(self.tmp)

    def tearDown(self):
        for ext in ("", "-wal", "-shm"):
            try:
                os.remove(self.db + ext)
            except OSError:
                pass

    def test_no_persistent_fts_triggers_on_pending_or_topic(self):
        con = _db_shared._connect(self.db, SCHEMA)
        pendings._ensure_fts(con)   # crea neb_fts (sin triggers)
        trigs = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'neb_fts_%'").fetchall()]
        self.assertEqual(trigs, [], f"no debe quedar ningún trigger FTS persistente; halló {trigs}")
        con.close()

    def test_raw_insert_from_connection_without_ensure_fts_does_not_error(self):
        # Conexión A: SÍ llama _ensure_fts (crea neb_fts y la deja poblada/sincronizada).
        ca = _db_shared._connect(self.db, SCHEMA)
        _new_pending(ca, "pendiente sembrado via A")
        self.assertTrue(pendings._ensure_fts(ca))
        ca.commit(); ca.close()
        # Conexión B: NUNCA llama _ensure_fts. Una inserción cruda en pending (como la del hook
        # de captura del logbook) NO debe disparar FTS5 ni fallar — antes, un trigger AFTER INSERT
        # la acoplaba a FTS5 y podía perder la escritura silenciosamente.
        cb = _db_shared._connect(self.db, SCHEMA)
        cb.execute("INSERT INTO pending (type, context_origin, status, created_at) "
                   "VALUES ('task', 'escritura cruda sin FTS', 'open', ?)", (pendings.now_iso(),))
        cb.commit()
        self.assertEqual(cb.execute("SELECT count(*) FROM pending").fetchone()[0], 2)
        cb.close()


if __name__ == "__main__":
    unittest.main()
