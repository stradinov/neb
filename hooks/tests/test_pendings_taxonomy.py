#!/usr/bin/env python3
"""
test_pendings_taxonomy.py — REQ pendings-taxonomia-cliente-topico.

Cubre contra DBs TEMPORALES (tempfile; NUNCA ~/.claude/*.db) y ejemplos GENÉRICOS (alpha/beta):
  • migración: DB legacy (forma 6.6.0, DDL inline) recibe pending.slug, pending_topic.curated y el
    índice único parcial uq_pending_slug; idempotente; filas y bandas intactas; solo DDL (sin backfill);
    parcial se completa; DB solo-logbook y conexión envuelta (mock de PRAGMA) no rompen; el .sql vivo
    trae las columnas y las migraciones coinciden con él.
  • backfill_slugs: tag inicial único -> slug (3 formatos); repetido / ocupado / sin tag -> NULL; idempotente.
  • resolve_pending_ref: columna slug > tag exacto > substring.
  • classify/reclassify: no tocan lo curado; escriben curated=0; nunca sugieren raíces; el delta incluye
    a los que quedaron solo sobre temas archivados.
  • triage_pass: grupos SOLO por pending_link entre open; suggested/unclassified disjuntos.
  • compas v2: `Clientes:` (bonus por cliente), v1 sin la línea, write_compas round-trip; peso por eje.
  • recommend_priority: banda curada > compas; curado sin banda -> compas.
  • curate: reemplazo por eje, is_primary solo en tópico, banda EN, slug único, raíz rechazada,
    related -> link; cli_curate emite JSON ok/error por stdout.
  • seed-pendings-taxonomy.py: dry-run no escribe; apply (raíces, reuso, archivo, curaduría, slugs,
    links, backfill, respaldo verificado); invariante de bandas; idempotente; no pisa curaduría posterior
    salvo --force; colisión de slug reportada; rollback restaura las 4 tablas.

Framework: unittest (stdlib), NO pytest.
"""

import contextlib
import importlib.util
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

import _db_shared  # noqa: E402
import pendings    # noqa: E402

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
_SEED_PATH = os.path.join(HERE, "..", "..", "bootstrap", "seed-pendings-taxonomy.py")
_spec = importlib.util.spec_from_file_location("seed_pendings_taxonomy", _SEED_PATH)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)

# DDL CONGELADO de las tablas de pendings en 6.6.0 (sin slug / curated / uq_pending_slug) + work completo.
LEGACY_DDL = """
CREATE TABLE work (
  id INTEGER PRIMARY KEY, mode TEXT NOT NULL DEFAULT 'req', project TEXT, req_slug TEXT, owner TEXT,
  lock_state TEXT NOT NULL DEFAULT 'owned', takeover_by TEXT, locked_at TEXT, req_state TEXT, branch TEXT,
  head_commit TEXT, repo_path TEXT, change_md TEXT, payload_json TEXT,
  payload_version INTEGER NOT NULL DEFAULT 0, origin_dev TEXT, origin_machine TEXT, claude_session_id TEXT,
  claude_session_name TEXT, transcript_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  archived_at TEXT, dirty INTEGER NOT NULL DEFAULT 1, synced_at TEXT, remote_id INTEGER,
  conflict INTEGER NOT NULL DEFAULT 0, last_error TEXT, last_error_at TEXT, transcript_error TEXT,
  transcript_error_at TEXT
);
CREATE TABLE pending (
  id INTEGER PRIMARY KEY, type TEXT NOT NULL DEFAULT 'task', context_origin TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open', obsolete_cause TEXT, work_ref INTEGER, session_ref INTEGER,
  created_at TEXT NOT NULL, last_reviewed_at TEXT, archived_at TEXT
);
CREATE TABLE pending_note (id INTEGER PRIMARY KEY, pending_id INTEGER NOT NULL, note TEXT NOT NULL, ts TEXT NOT NULL);
CREATE TABLE pending_link (a INTEGER NOT NULL, b INTEGER NOT NULL, relation TEXT NOT NULL, PRIMARY KEY (a, b, relation));
CREATE TABLE topic (
  id INTEGER PRIMARY KEY, slug TEXT NOT NULL, name TEXT NOT NULL, description TEXT, keywords TEXT,
  status TEXT NOT NULL DEFAULT 'active', parent_id INTEGER
);
CREATE UNIQUE INDEX uq_topic_slug ON topic(slug);
CREATE TABLE topic_link (topic_a INTEGER NOT NULL, topic_b INTEGER NOT NULL, relation TEXT NOT NULL, PRIMARY KEY (topic_a, topic_b, relation));
CREATE TABLE pending_topic (
  pending_id INTEGER NOT NULL, topic_id INTEGER NOT NULL, priority_band TEXT, priority_score REAL,
  is_primary INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (pending_id, topic_id)
);
"""


# --------------------------------------------------------------------------- helpers

def _fresh_home():
    d = tempfile.mkdtemp(prefix="neb-tax-")
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    return d


def _connect_fresh(home):
    path = _db_shared.resolve_db_path(home)
    con = _db_shared._connect(path, SCHEMA)
    con.execute("PRAGMA foreign_keys=ON")
    return con, path


def _topic(con, slug, name=None, keywords="", status="active", parent=None):
    cur = con.execute(
        "INSERT INTO topic (slug, name, description, keywords, status, parent_id) VALUES (?,?,?,?,?,?)",
        (slug, name or slug, "", keywords, status, parent))
    con.commit()
    return cur.lastrowid


def _axes(con):
    """Raíces + hijos genéricos. cliente: alpha, beta · topico: seguridad, tooling."""
    ids = {}
    for axis in pendings.AXIS_ROOTS:
        ids[axis] = _topic(con, axis, axis.capitalize(), "")
    ids["alpha"] = _topic(con, "alpha", "Alpha", "alpha", parent=ids["cliente"])
    ids["beta"] = _topic(con, "beta", "Beta", "beta", parent=ids["cliente"])
    ids["seguridad"] = _topic(con, "seguridad", "Seguridad", "seguridad, token, credenciales", parent=ids["topico"])
    ids["tooling"] = _topic(con, "tooling", "Tooling", "tooling, hook, script", parent=ids["topico"])
    return ids


def _pending(con, ctx, status="open", slug=None):
    cur = con.execute(
        "INSERT INTO pending (type, context_origin, status, created_at, slug, archived_at) "
        "VALUES ('task', ?, ?, ?, ?, ?)",
        (ctx, status, pendings.now_iso(), slug, (pendings.now_iso() if status == "obsolete" else None)))
    con.commit()
    return cur.lastrowid


def _pt(con, pid, tid, band=None, score=None, primary=0, curated=0):
    con.execute(
        "INSERT INTO pending_topic (pending_id, topic_id, priority_band, priority_score, is_primary, curated) "
        "VALUES (?,?,?,?,?,?)", (pid, tid, band, score, primary, curated))
    con.commit()


def _rows(con, pid):
    return {r[0]: r[1:] for r in con.execute(
        "SELECT t.slug, pt.priority_band, pt.priority_score, pt.is_primary, pt.curated "
        "FROM pending_topic pt JOIN topic t ON t.id = pt.topic_id WHERE pt.pending_id=?", (pid,))}


def _index_names(con):
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}


# =========================================================================== migración

class TestMigration(unittest.TestCase):

    def _legacy(self):
        d = tempfile.mkdtemp(prefix="neb-tax-legacy-")
        path = os.path.join(d, "neb.db")
        c = sqlite3.connect(path)
        c.executescript(LEGACY_DDL)
        c.execute("INSERT INTO work (mode, created_at, updated_at) VALUES ('exploratory','t','t')")
        c.execute("INSERT INTO pending (context_origin, created_at) VALUES ('[alpha-uno] cosa uno','t')")
        c.execute("INSERT INTO topic (slug, name, keywords) VALUES ('alpha','Alpha','alpha')")
        c.execute("INSERT INTO pending_topic (pending_id, topic_id, priority_band, priority_score, is_primary) "
                  "VALUES (1, 1, 'high', 95.0, 1)")
        c.commit(); c.close()
        return path

    def test_legacy_db_gets_columns_index_and_keeps_rows(self):
        path = self._legacy()
        for _ in range(2):                                   # dos veces: idempotente
            con = _db_shared._connect(path, SCHEMA)
            self.assertIsNotNone(con)
            self.assertIn("slug", {r[1] for r in con.execute("PRAGMA table_info(pending)")})
            self.assertIn("curated", {r[1] for r in con.execute("PRAGMA table_info(pending_topic)")})
            self.assertIn("uq_pending_slug", _index_names(con))
            self.assertEqual(con.execute("SELECT count(*) FROM pending").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT priority_band, priority_score, curated FROM pending_topic").fetchone(),
                             ("high", 95.0, 0))
            # SOLO DDL: la migración no hace backfill aunque el tag sea único
            self.assertIsNone(con.execute("SELECT slug FROM pending WHERE id=1").fetchone()[0])
            con.close()

    def test_partial_migration_completes(self):
        path = self._legacy()
        c = sqlite3.connect(path); c.execute("ALTER TABLE pending ADD COLUMN slug TEXT"); c.commit(); c.close()
        con = _db_shared._connect(path, SCHEMA)
        self.assertIn("curated", {r[1] for r in con.execute("PRAGMA table_info(pending_topic)")})
        self.assertIn("uq_pending_slug", _index_names(con))
        con.close()

    def test_logbook_only_db_and_wrapped_connection_do_not_break(self):
        """Espejo de TestMigrate.test_el_perdedor_de_la_carrera (test_logbook_sync_errors): una DB con
        SOLO `work` y una conexión que falsea CUALQUIER PRAGMA table_info no deben hacer que _migrate
        intente tocar `pending` (guard por sqlite_master, que el mock delega a la conexión real)."""
        d = tempfile.mkdtemp(prefix="neb-tax-onlywork-")
        path = os.path.join(d, "neb.db")
        real = sqlite3.connect(path)
        real.executescript(LEGACY_DDL.split("CREATE TABLE pending (")[0])   # solo work
        real.commit()
        _db_shared._migrate(real)                             # DB solo-logbook: no lanza

        class _StaleView:
            def __init__(self, con): self._con = con
            def execute(self, sql, *a):
                if sql.startswith("PRAGMA table_info"):
                    class _R:
                        def fetchall(_s): return [(0, "id"), (1, "mode")]
                    return _R()
                return self._con.execute(sql, *a)
            def __getattr__(self, n): return getattr(self._con, n)

        _db_shared._migrate(_StaleView(real))                 # no debe lanzar 'no such table: pending'
        real.close()

    def test_schema_sql_and_migrations_in_sync(self):
        m = sqlite3.connect(":memory:")
        with open(SCHEMA, encoding="utf-8") as fh:
            m.executescript(fh.read())
        pcols = {r[1] for r in m.execute("PRAGMA table_info(pending)")}
        tcols = {r[1] for r in m.execute("PRAGMA table_info(pending_topic)")}
        self.assertTrue({n for n, _ in _db_shared._PENDING_MIGRATIONS} <= pcols)
        self.assertTrue({n for n, _ in _db_shared._PENDING_TOPIC_MIGRATIONS} <= tcols)
        # el índice NO vive en el .sql (ver comentario ahí); lo crea _migrate en una DB fresca también
        self.assertNotIn("uq_pending_slug", _index_names(m))
        con, _ = _connect_fresh(_fresh_home())
        self.assertIn("uq_pending_slug", _index_names(con))
        con.close()

    def test_unique_slug_index_enforced(self):
        con, _ = _connect_fresh(_fresh_home())
        _pending(con, "a", slug="x")
        _pending(con, "b", slug=None)
        _pending(con, "c", slug=None)                         # varios NULL conviven
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute("UPDATE pending SET slug='x' WHERE id=2")
        con.close()

    def test_duplicate_slugs_do_not_brick_connect(self):
        """Slugs duplicados pre-existentes (solo por escritura cruda): el índice no se crea, se avisa
        por stderr y la conexión sigue usable — el hook no muere por esto."""
        path = self._legacy()
        c = sqlite3.connect(path)
        c.execute("ALTER TABLE pending ADD COLUMN slug TEXT")
        c.execute("INSERT INTO pending (context_origin, created_at, slug) VALUES ('dos','t','dup')")
        c.execute("INSERT INTO pending (context_origin, created_at, slug) VALUES ('tres','t','dup')")
        c.commit(); c.close()
        for _ in range(2):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                con = _db_shared._connect(path, SCHEMA)
            self.assertIsNotNone(con)
            self.assertNotIn("uq_pending_slug", _index_names(con))
            self.assertIn("uq_pending_slug no creado", err.getvalue())
            self.assertEqual(con.execute("SELECT count(*) FROM pending").fetchone()[0], 3)
            con.close()


# =========================================================================== backfill + resolve

class TestBackfill(unittest.TestCase):
    def test_backfill_only_unique_free_tags_three_formats(self):
        con, _ = _connect_fresh(_fresh_home())
        p1 = _pending(con, "[alpha-uno] cosa")
        p2 = _pending(con, "12. **[alpha-dos]** cosa migrada")
        p3 = _pending(con, "[dup] c"); p4 = _pending(con, "[dup] d")
        p5 = _pending(con, "sin tag")
        _pending(con, "otro pendiente con slug", slug="alpha-tres")
        p7 = _pending(con, "[alpha-tres] tag ocupado por otro slug")
        p8 = _pending(con, "**[alpha-cuatro]** sin numero")
        n = pendings.backfill_slugs(con); con.commit()
        self.assertEqual(n, 3)
        got = dict(con.execute("SELECT id, slug FROM pending"))
        self.assertEqual(got[p1], "alpha-uno"); self.assertEqual(got[p2], "alpha-dos")
        self.assertEqual(got[p8], "alpha-cuatro")
        for p in (p3, p4, p5, p7):
            self.assertIsNone(got[p])
        self.assertEqual(pendings.backfill_slugs(con), 0)     # idempotente
        con.close()

    def test_dry_run_counts_without_writing_even_on_unmigrated_db(self):
        con, _ = _connect_fresh(_fresh_home())
        _pending(con, "[alpha-uno] a"); _pending(con, "[alpha-dos] b"); _pending(con, "[dup] c"); _pending(con, "[dup] d")
        self.assertEqual(pendings.backfill_slugs(con, dry_run=True), 2)
        self.assertEqual(pendings.backfill_slugs(con, dry_run=True, skip_ids={1}, reserved={"alpha-dos"}), 0)
        self.assertEqual(con.execute("SELECT count(*) FROM pending WHERE slug IS NOT NULL").fetchone()[0], 0)
        con.close()
        # DB sin migrar (sin columna slug): el conteo funciona; escribir lanza
        raw = sqlite3.connect(":memory:")
        raw.executescript(LEGACY_DDL)
        raw.execute("INSERT INTO pending (context_origin, created_at) VALUES ('[beta-uno] x','t')")
        self.assertEqual(pendings.backfill_slugs(raw, dry_run=True), 1)
        with self.assertRaises(RuntimeError):
            pendings.backfill_slugs(raw)
        raw.close()


class TestResolve(unittest.TestCase):
    def test_column_then_tag_then_loose(self):
        con, _ = _connect_fresh(_fresh_home())
        con.row_factory = sqlite3.Row
        a = _pending(con, "sin tag pero con slug", slug="x")
        _pending(con, "[x] tag viejo de OTRO pendiente")          # no debe ganar sobre la columna
        b = _pending(con, "[y] solo tag")
        c = _pending(con, "texto con la palabra zeta dentro")
        kind, rows = pendings.resolve_pending_ref(con, "x")
        self.assertEqual((kind, [r["id"] for r in rows]), ("slug", [a]))
        kind, rows = pendings.resolve_pending_ref(con, "[x]")
        self.assertEqual((kind, [r["id"] for r in rows]), ("slug", [a]))
        kind, rows = pendings.resolve_pending_ref(con, "y")
        self.assertEqual((kind, [r["id"] for r in rows]), ("slug-exact", [b]))
        kind, rows = pendings.resolve_pending_ref(con, "zeta")
        self.assertEqual((kind, [r["id"] for r in rows]), ("slug-loose", [c]))
        con.close()


# =========================================================================== classify / reclassify / triage

class TestClassifyCurated(unittest.TestCase):
    def setUp(self):
        self.con, _ = _connect_fresh(_fresh_home())
        self.ids = _axes(self.con)

    def tearDown(self):
        self.con.close()

    def test_curated_pending_is_untouched_and_returned(self):
        pid = _pending(self.con, "token de alpha expuesto, tooling roto")
        pendings.curate(self.con, pid, cliente="alpha", topico="seguridad", band="alta"); self.con.commit()
        before = _rows(self.con, pid)
        reviewed = self.con.execute("SELECT last_reviewed_at FROM pending WHERE id=?", (pid,)).fetchone()[0]
        out = pendings.classify(self.con, pid)
        self.assertEqual(set(out), {self.ids["alpha"], self.ids["seguridad"]})
        self.assertEqual(_rows(self.con, pid), before)
        self.assertEqual(self.con.execute("SELECT last_reviewed_at FROM pending WHERE id=?", (pid,)).fetchone()[0], reviewed)
        self.assertNotIn(pid, pendings.reclassify(self.con))

    def test_uncurated_gets_suggestions_curated_0_and_never_roots(self):
        pid = _pending(self.con, "el cliente pide rotar el token; el topico es otro")
        out = pendings.classify(self.con, pid)
        rows = _rows(self.con, pid)
        self.assertIn(self.ids["seguridad"], out)
        self.assertTrue(all(r[3] == 0 for r in rows.values()))          # curated=0
        self.assertNotIn("cliente", rows); self.assertNotIn("topico", rows)   # raíces jamás
        # replace=True solo borra lo suyo: una fila curada sobre otro tema sobrevive
        _pt(self.con, pid, self.ids["alpha"], curated=1)
        pendings.classify(self.con, _pending(self.con, "otro"))       # no afecta a pid
        pendings.curate(self.con, pid, band="media"); self.con.commit()  # solo banda sobre lo curado
        self.assertEqual(_rows(self.con, pid)["alpha"][3], 1)

    def test_roots_only_text_falls_to_sentinel(self):
        pid = _pending(self.con, "cliente topico cliente")
        out = pendings.classify(self.con, pid)
        sent = self.con.execute("SELECT id FROM topic WHERE slug=?", (pendings.SENTINEL_SLUG,)).fetchone()[0]
        self.assertEqual(out, [sent])

    def test_curated_only_on_archived_topics_returns_to_curation_flow(self):
        """Curado = fila curated=1 sobre tema ACTIVO. Si el catálogo archiva ambos temas de un
        pendiente, deja de contar como curado: triage lo devuelve a suggested/unclassified y
        reclassify vuelve a sugerir (el skill lo verá en el paso 3)."""
        pid = _pending(self.con, "token expuesto en alpha")
        pendings.curate(self.con, pid, cliente="alpha", topico="tooling", band="alta"); self.con.commit()
        self.assertNotIn(pid, pendings.triage_pass(self.con)["suggested"] + pendings.triage_pass(self.con)["unclassified"])
        self.con.execute("UPDATE topic SET status='archived' WHERE slug IN ('alpha','tooling')"); self.con.commit()
        self.assertEqual(pendings._curated_topic_ids(self.con, pid), [])
        out = pendings.triage_pass(self.con)
        self.assertIn(pid, out["suggested"] + out["unclassified"])   # de vuelta al flujo
        self.assertIn(self.ids["seguridad"], pendings.classify(self.con, pid))   # y se re-sugiere
        self.assertEqual(_rows(self.con, pid)["tooling"][3], 1)      # el historial curado se conserva

    def test_reclassify_includes_rows_only_on_archived_topics(self):
        old = _topic(self.con, "old-req", "Old", "old", status="archived")
        pid = _pending(self.con, "credenciales en claro")
        _pt(self.con, pid, old, band="low", score=1.0, primary=1)
        self.con.execute("UPDATE pending SET last_reviewed_at='2026-01-01' WHERE id=?", (pid,)); self.con.commit()
        res = pendings.reclassify(self.con)
        self.assertIn(pid, res)                                        # sin sugerencia vigente -> entra al delta
        self.assertIn(self.ids["seguridad"], res[pid])
        self.assertIn("old-req", _rows(self.con, pid))                 # la fila histórica se conserva


class TestTriageSets(unittest.TestCase):
    def test_disjoint_sets_and_link_groups_between_open_only(self):
        con, _ = _connect_fresh(_fresh_home())
        ids = _axes(con)
        p1 = _pending(con, "curado")
        pendings.curate(con, p1, cliente="alpha", topico="tooling", band="baja"); con.commit()
        p2 = _pending(con, "token expuesto")                           # sugerencia: seguridad
        p3 = _pending(con, "nada que matchee")                         # sentinel
        p4 = _pending(con, "obsoleto vinculado", status="obsolete")
        p5 = _pending(con, "credenciales sin vinculo")                 # comparte tema con p2, sin link
        for a, b in ((p2, p1), (p4, p1)):
            con.execute("INSERT INTO pending_link (a, b, relation) VALUES (?,?,'related')", (a, b))
        con.commit()
        out = pendings.triage_pass(con)
        self.assertEqual(out["groups"], [[p1, p2]])                    # p4 obsoleto fuera; p5 sin link fuera
        self.assertEqual(out["suggested"], sorted([p2, p5]))
        self.assertEqual(out["unclassified"], [p3])
        self.assertFalse(set(out["suggested"]) & set(out["unclassified"]))
        self.assertEqual(set(out["suggested"]) | set(out["unclassified"]), {p2, p3, p5})
        con.close()

    def test_cli_triage_exposes_catalog_and_rejects_unknown_filter(self):
        home = _fresh_home()
        con, db = _connect_fresh(home)
        _axes(con); con.close()

        def _con():
            return _db_shared._connect(db, SCHEMA)
        buf = io.StringIO()
        with mock.patch.object(pendings, "_db_for_cli", _con), contextlib.redirect_stdout(buf):
            pendings.cli_triage([])
        out = json.loads(buf.getvalue())
        self.assertEqual(out["catalog"], {"cliente": ["alpha", "beta"], "topico": ["seguridad", "tooling"]})
        buf = io.StringIO()
        with mock.patch.object(pendings, "_db_for_cli", _con), contextlib.redirect_stdout(buf):
            pendings.cli_triage(["--cliente", "nope"])
        err = json.loads(buf.getvalue())
        self.assertFalse(err["ok"]); self.assertIn("nope", err["error"]); self.assertIn("catalog", err)


# =========================================================================== compas v2 + recomendador

class TestCompasV2(unittest.TestCase):
    def setUp(self):
        self.home = _fresh_home()
        self.con, _ = _connect_fresh(self.home)
        self.ids = _axes(self.con)

    def tearDown(self):
        self.con.close()

    def test_write_and_parse_v2_and_v1(self):
        path = pendings.write_compas(self.home, [("Seg", 60, ["seguridad"], None, {"alpha": 15})])
        txt = open(path, encoding="utf-8").read()
        self.assertIn("version: 2", txt); self.assertIn("- **Clientes:** alpha=+15", txt)
        c = pendings.parse_compas(self.home)
        self.assertEqual(c["topic_weight"], {"seguridad": 60}); self.assertEqual(c["client_bonus"], {"alpha": 15})
        pendings.write_compas(self.home, [("Seg", 60, ["seguridad"], None)])   # sin 5º elemento = v1
        c = pendings.parse_compas(self.home)
        self.assertEqual(c["client_bonus"], {}); self.assertEqual(c["topic_weight"], {"seguridad": 60})
        self.assertEqual(pendings.parse_compas(_fresh_home())["client_bonus"], {})   # ausente

    def test_parse_all_temas_of_an_objective_and_empty_temas_line(self):
        """Regresión (bug previo a 6.7.0): solo el primer tema de cada objetivo ponderaba (los demás
        quedaban con espacio inicial) y una línea `Temas:` vacía capturaba la línea siguiente."""
        pendings.write_compas(self.home, [("Varios", 70, ["seguridad", "tooling", "memoria"], None),
                                          ("Solo clientes", 0, [], None, {"beta": 10})])
        c = pendings.parse_compas(self.home)
        self.assertEqual(c["topic_weight"], {"seguridad": 70, "tooling": 70, "memoria": 70})
        self.assertEqual(c["client_bonus"], {"beta": 10})
        self.assertEqual(c["objectives"][1]["topics"], [])          # nada de '- **roadmap:** —' como tema

    def test_weight_by_topico_plus_client_bonus_axis_aware(self):
        pendings.write_compas(self.home, [("Seg", 60, ["seguridad", "alpha"], None, {"alpha": 15})])
        pid = _pending(self.con, "x")
        pendings.curate(self.con, pid, cliente="alpha", topico="seguridad"); self.con.commit()  # curado SIN banda
        r = pendings.recommend_priority(self.con, pid, home=self.home)
        self.assertEqual(r["source"], "compas")
        self.assertGreaterEqual(r["score"], 75)                        # 60 + 15 (+ intrínsecas)
        self.assertLess(r["score"], 95)                                # 'alpha' en Temas NO cuenta como peso
        self.assertIn("bonus por cliente +15", r["rationale"])
        only_client = _pending(self.con, "y")
        pendings.curate(self.con, only_client, cliente="alpha"); self.con.commit()
        r2 = pendings.recommend_priority(self.con, only_client, home=self.home)
        self.assertEqual(r2["source"], "compas")                       # bonus 15 > 0 -> compas
        self.assertLess(r2["score"], 34)                               # sin peso de tópico: baja

    def test_curated_band_wins_over_compas(self):
        pendings.write_compas(self.home, [("Todo", 10, ["seguridad", "tooling"], None)])
        pid = _pending(self.con, "urgente crítico bloqueante")         # señales intrínsecas fuertes
        pendings.curate(self.con, pid, cliente="beta", topico="tooling", band="alta"); self.con.commit()
        r = pendings.recommend_priority(self.con, pid, home=self.home)
        self.assertEqual((r["source"], r["band"], r["score"]), ("curated", "alta", 80.0))
        self.assertEqual(set(r["by_topic"]), {"beta", "tooling"})
        # el prompt sigue mandando sobre la banda curada
        self.assertEqual(pendings.recommend_priority(self.con, pid, prompt_criterion="tooling", home=self.home)["source"],
                         "prompt")

    def test_infer_objectives_skips_cliente_axis_and_archived(self):
        old = _topic(self.con, "old-req", "Old", "old", status="archived")
        legacy = _topic(self.con, "gamma", "Gamma", "gamma")           # sin raíz: se propone
        pid = _pending(self.con, "z")
        pendings.curate(self.con, pid, cliente="alpha", topico="seguridad"); self.con.commit()
        _pt(self.con, pid, old); _pt(self.con, pid, legacy)
        proposed = {t for o in pendings.infer_objectives(self.con, home=self.home)["proposed"] for t in o["topics"]}
        self.assertEqual(proposed, {"seguridad", "gamma"})


# =========================================================================== curate + CLI

class TestCurate(unittest.TestCase):
    def setUp(self):
        self.home = _fresh_home()
        self.con, self.db = _connect_fresh(self.home)
        self.ids = _axes(self.con)

    def tearDown(self):
        self.con.close()

    def test_replace_per_axis_primary_band_slug_related(self):
        pid = _pending(self.con, "p")
        other = _pending(self.con, "q", slug="q-slug")
        pendings.classify(self.con, _pending(self.con, "token"))      # ruido ajeno, no afecta
        out = pendings.curate(self.con, pid, cliente="alpha", topico="seguridad", band="media",
                              slug="p-slug", related=["q-slug"])
        pendings.curate(self.con, pid, cliente="beta")                 # reemplaza el eje cliente
        self.con.commit()
        rows = _rows(self.con, pid)
        self.assertEqual(set(rows), {"beta", "seguridad"})             # exactamente una fila por eje
        self.assertEqual(rows["seguridad"][2], 1); self.assertEqual(rows["beta"][2], 0)   # is_primary solo tópico
        self.assertEqual(rows["beta"][0], "medium"); self.assertEqual(rows["beta"][3], 1)  # banda EN heredada, curated
        self.assertEqual(out["links_added"], 1)
        self.assertEqual(self.con.execute("SELECT a, b, relation FROM pending_link").fetchall(),
                         [(pid, other, "related")])
        self.assertEqual(self.con.execute("SELECT slug FROM pending WHERE id=?", (pid,)).fetchone()[0], "p-slug")

    def test_errors_are_value_errors(self):
        pid = _pending(self.con, "p"); _pending(self.con, "q", slug="taken")
        with self.assertRaises(ValueError): pendings.curate(self.con, pid, cliente="cliente")     # raíz
        with self.assertRaises(ValueError): pendings.curate(self.con, pid, topico="alpha")       # eje cruzado
        with self.assertRaises(ValueError): pendings.curate(self.con, pid, slug="taken")         # colisión
        with self.assertRaises(ValueError): pendings.curate(self.con, pid, slug="Bad Slug")      # formato
        with self.assertRaises(ValueError): pendings.curate(self.con, pid, band="urgente")       # banda

    def test_band_with_single_axis_applies_to_all_curated_rows(self):
        pid = _pending(self.con, "p")
        pendings.curate(self.con, pid, cliente="alpha", topico="seguridad", band="alta")
        out = pendings.curate(self.con, pid, cliente="beta", band="baja"); self.con.commit()
        self.assertEqual(out["band"], "baja")
        self.assertEqual(pendings._curated_band(self.con, pid), ("low", 20.0))
        rows = _rows(self.con, pid)
        self.assertEqual((rows["beta"][0], rows["seguridad"][0]), ("low", "low"))
        self.assertEqual(pendings.recommend_priority(self.con, pid, home=self.home)["band"], "baja")

    def test_band_only_on_uncurated_pending_raises_and_keeps_suggestions(self):
        pid = _pending(self.con, "token expuesto")
        pendings.classify(self.con, pid)                              # sugerencia: seguridad
        before = _rows(self.con, pid)
        with self.assertRaises(ValueError):
            pendings.curate(self.con, pid, band="alta")
        self.assertEqual(_rows(self.con, pid), before)                # la sugerencia sigue

    def test_cli_curate_rejects_loose_citation_and_rolls_back_partial_writes(self):
        pid = _pending(self.con, "texto con la palabra zeta dentro")
        _pending(self.con, "q", slug="q-slug")
        self.con.close()

        def _con():
            return _db_shared._connect(self.db, SCHEMA)
        buf = io.StringIO()
        with mock.patch.object(pendings, "_db_for_cli", _con), contextlib.redirect_stdout(buf):
            pendings.cli_curate(["zeta", "--cliente", "alpha"])       # substring: NO cura
        err = json.loads(buf.getvalue())
        self.assertFalse(err["ok"]); self.assertIn("no exacta", err["error"])
        buf = io.StringIO()
        with mock.patch.object(pendings, "_db_for_cli", _con), contextlib.redirect_stdout(buf):
            pendings.cli_curate([str(pid), "--cliente", "alpha", "--topico", "tooling", "--slug", "p-x",
                                 "--relacionado", "no-existe"])       # falla al final -> nada persiste
        err = json.loads(buf.getvalue())
        self.assertFalse(err["ok"]); self.assertIn("no encontrado", err["error"])
        self.con = _con()
        self.assertEqual(_rows(self.con, pid), {})
        self.assertIsNone(self.con.execute("SELECT slug FROM pending WHERE id=?", (pid,)).fetchone()[0])
        self.assertEqual(self.con.execute("SELECT count(*) FROM pending_link").fetchone()[0], 0)

    def test_cli_curate_prints_json_ok_and_error(self):
        pid = _pending(self.con, "p")
        self.con.close()

        def _con():
            return _db_shared._connect(self.db, SCHEMA)
        buf = io.StringIO()
        with mock.patch.object(pendings, "_db_for_cli", _con), contextlib.redirect_stdout(buf):
            pendings.cli_curate([str(pid), "--cliente", "alpha", "--topico", "tooling", "--band", "alta", "--slug", "p-uno"])
        ok = json.loads(buf.getvalue())
        self.assertTrue(ok["ok"]); self.assertEqual((ok["cliente"], ok["topico"], ok["band"], ok["slug"]),
                                                    ("alpha", "tooling", "alta", "p-uno"))
        buf = io.StringIO()
        with mock.patch.object(pendings, "_db_for_cli", _con), contextlib.redirect_stdout(buf):
            pendings.cli_curate(["p-uno", "--topico", "no-existe"])
        err = json.loads(buf.getvalue())
        self.assertFalse(err["ok"]); self.assertIn("no-existe", err["error"])
        self.con = _con()
        self.assertEqual(_rows(self.con, pid)["tooling"][3], 1)        # el error no tocó lo curado


# =========================================================================== seed

class TestSeed(unittest.TestCase):
    """Fixture genérica: DB con temas viejos (alpha reusable, old-req a archivar), pendientes en varios
    estados y un dataset + catálogo mínimos. Todo en tempfile."""

    def setUp(self):
        self.home = _fresh_home()
        self.con, self.db = _connect_fresh(self.home)
        old_alpha = _topic(self.con, "alpha", "Alpha", "alpha")           # se reusa como cliente
        old_req = _topic(self.con, "old-req", "Old req", "old, req")     # se archiva
        self.p1 = _pending(self.con, "[alpha-viejo] cosa uno")
        _pt(self.con, self.p1, old_req, band="high", score=95.0, primary=1)
        _pt(self.con, self.p1, old_alpha, band="low", score=1.0)         # ruido FTS sobre tema reusado
        self.p2 = _pending(self.con, "[beta-dos] cosa dos")
        _pt(self.con, self.p2, old_req, band="medium", score=42.0, primary=1)   # score del pase != mapa
        self.p3 = _pending(self.con, "otra sin tag")
        self.p4 = _pending(self.con, "[obs] obsoleto", status="obsolete")
        _pt(self.con, self.p4, old_req, band="low", score=20.0, primary=1)
        self.p6 = _pending(self.con, "ya curado antes")
        self.p7 = _pending(self.con, "[delta-siete] fuera del dataset")
        self.p8 = _pending(self.con, "colision de slug")
        self.p9 = _pending(self.con, "prioridad desconocida y slug invalido")
        self.con.execute("UPDATE pending SET last_reviewed_at='2026-01-01' WHERE id=?", (self.p1,))
        self.con.execute("INSERT INTO topic_link (topic_a, topic_b, relation) VALUES (?,?,'related')", (old_alpha, old_req))
        self.con.commit()
        self.con.close()
        self.catalog = os.path.join(self.home, "taxonomy.json")
        json.dump({"cliente": [{"slug": "alpha", "name": "Alpha", "keywords": "alpha"},
                               {"slug": "beta", "name": "Beta", "keywords": "beta"}],
                   "topico": [{"slug": "seguridad", "name": "Seguridad", "keywords": "token"},
                              {"slug": "tooling", "name": "Tooling", "keywords": "hook"}]},
                  open(self.catalog, "w", encoding="utf-8"))
        self.dataset = os.path.join(self.home, "triage.json")
        json.dump({"items": [
            {"id": self.p1, "slug": "alpha-uno-nuevo", "cliente": "alpha", "topico": "seguridad", "grupo": "g1", "prioridad": "P0", "veredicto_final": "vigente"},
            {"id": self.p2, "slug": "beta-dos", "cliente": "beta", "topico": "tooling", "grupo": "g1", "prioridad": "P2", "veredicto_final": "requiere_verificacion"},
            {"id": self.p3, "slug": "gamma-tres", "cliente": "alpha", "topico": "tooling", "grupo": None, "prioridad": "P3", "veredicto_final": "vigente"},
            {"id": self.p4, "slug": "obs-cuatro", "cliente": "alpha", "topico": "tooling", "grupo": "g1", "prioridad": "P1", "veredicto_final": "vigente"},
            {"id": 9999, "slug": "no-existe", "cliente": "alpha", "topico": "tooling", "grupo": None, "prioridad": "P3", "veredicto_final": "vigente"},
            {"id": self.p6, "slug": "seis", "cliente": "alpha", "topico": "tooling", "grupo": None, "prioridad": "P3", "veredicto_final": "vigente"},
            {"id": self.p8, "slug": "beta-dos", "cliente": "beta", "topico": "seguridad", "grupo": None, "prioridad": "P3", "veredicto_final": "vigente"},
            {"id": self.p9, "slug": "Bad Slug", "cliente": "alpha", "topico": "tooling", "grupo": None, "prioridad": "P9", "veredicto_final": "vigente"},
        ]}, open(self.dataset, "w", encoding="utf-8"))

    def _pre_curate_p6(self):
        """p6 curado ANTES del seed (curaduría posterior al pase que el seed NO debe pisar)."""
        con = _db_shared._connect(self.db, SCHEMA)
        # las raíces aún no existen: se crean con el catálogo para poder curar p6 "antes"
        for axis in pendings.AXIS_ROOTS:
            con.execute("INSERT OR IGNORE INTO topic (slug, name, description, keywords, status) VALUES (?,?,?,?, 'active')",
                        (axis, axis, "", ""))
        root = con.execute("SELECT id FROM topic WHERE slug='topico'").fetchone()[0]
        con.execute("INSERT OR IGNORE INTO topic (slug, name, description, keywords, status, parent_id) "
                    "VALUES ('seguridad','Seguridad','', 'token', 'active', ?)", (root,))
        pendings.curate(con, self.p6, topico="seguridad", band="alta"); con.commit(); con.close()

    def _run(self, apply=True, force=False):
        return self._run_on(self.db, apply=apply, force=force)

    def _run_on(self, db, apply=True, force=False):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = seed.run(db, self.catalog, self.dataset, apply=apply, force=force, backup_dir=self.home)
        return res, buf.getvalue()

    def test_dry_run_writes_nothing(self):
        con = _db_shared._connect(self.db, SCHEMA); before = seed.digest(con); con.close()
        res, out = self._run(apply=False)
        self.assertIn("DRY-RUN", out)
        con = _db_shared._connect(self.db, SCHEMA); self.assertEqual(seed.digest(con), before); con.close()
        self.assertFalse([f for f in os.listdir(self.home) if ".bak-pre-taxonomy-" in f])
        plan = res["plan"]
        self.assertEqual(set(plan["curate"]), {self.p1, self.p2, self.p3, self.p6, self.p8, self.p9})
        self.assertEqual(plan["skipped"]["obsolete"], [self.p4]); self.assertEqual(plan["skipped"]["missing"], [9999])
        self.assertEqual(plan["topics_reparent"], ["alpha"]); self.assertEqual(plan["topics_archive"], ["old-req"])
        self.assertEqual(plan["slugs_collide"], [(self.p8, "beta-dos", self.p2)])
        self.assertEqual(plan["slugs_invalid"], [(self.p9, "Bad Slug")]); self.assertEqual(plan["sin_banda"], [self.p9])
        # backfill: p7 (open, fuera del dataset) y p4 (obsoleto con tag único) — los obsoletos también
        self.assertEqual((plan["groups"], plan["links_new"], plan["backfill"]), (1, 1, 2))

    def test_dry_run_on_unmigrated_db_estimates_backfill(self):
        d = tempfile.mkdtemp(prefix="neb-tax-seedlegacy-")
        legacy = os.path.join(d, "neb.db")
        c = sqlite3.connect(legacy); c.executescript(LEGACY_DDL)
        c.execute("INSERT INTO work (mode, created_at, updated_at) VALUES ('exploratory','t','t')")
        # id 50: fuera de los ids del dataset (los del dataset se saltan como 'missing' en esta DB)
        c.execute("INSERT INTO pending (id, context_origin, created_at) VALUES (50, '[gamma-uno] fuera','t')")
        c.commit(); c.close()
        res, out = self._run_on(legacy, apply=False)
        self.assertFalse(res["plan"]["migrated"]); self.assertEqual(res["plan"]["backfill"], 1)
        self.assertIn("DB sin migrar", out)

    def test_missing_db_path_is_an_error_not_a_new_db(self):
        ghost = os.path.join(self.home, "typo.db")
        with self.assertRaises(RuntimeError):
            seed.run(ghost, self.catalog, self.dataset, apply=False)
        with self.assertRaises(RuntimeError):
            seed.rollback(ghost, self.dataset)
        self.assertFalse(os.path.exists(ghost))

    def test_apply_seeds_everything_with_verified_backup(self):
        self._pre_curate_p6()
        con = _db_shared._connect(self.db, SCHEMA)
        pre_digest = seed.digest(con)
        pre_band = {pid: con.execute("SELECT priority_band FROM pending_topic WHERE pending_id=? AND is_primary=1",
                                     (pid,)).fetchone()[0] for pid in (self.p1, self.p2)}
        alpha_id = con.execute("SELECT id FROM topic WHERE slug='alpha'").fetchone()[0]
        con.close()
        res, out = self._run(apply=True)
        self.assertTrue(res["changed"]); self.assertTrue(os.path.isfile(res["backup"]))
        bak = sqlite3.connect(res["backup"])
        self.assertEqual(bak.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(seed.digest(bak), pre_digest)                    # el respaldo es el estado pre-seed
        bak.close()
        con = _db_shared._connect(self.db, SCHEMA)
        t = {r[0]: r[1:] for r in con.execute("SELECT slug, status, parent_id, id FROM topic")}
        self.assertEqual(t["alpha"][2], alpha_id)                          # reusado: mismo id
        self.assertEqual(t["alpha"][1], t["cliente"][2]); self.assertEqual(t["seguridad"][1], t["topico"][2])
        self.assertEqual(t["old-req"][0], "archived"); self.assertEqual(t["beta"][0], "active")
        r1 = _rows(con, self.p1)
        self.assertEqual(r1["seguridad"], ("high", 95.0, 1, 1)); self.assertEqual(r1["alpha"], ("high", 95.0, 0, 1))
        self.assertEqual(r1["old-req"], ("high", 95.0, 1, 0))             # historial sobre tema archivado intacto
        self.assertEqual(_rows(con, self.p2)["tooling"], ("medium", 42.0, 1, 1))   # score HEREDADO del pase
        for pid in (self.p1, self.p2):                                     # invariante de bandas
            self.assertEqual(con.execute(
                "SELECT pt.priority_band FROM pending_topic pt JOIN topic t ON t.id=pt.topic_id JOIN topic r ON r.id=t.parent_id "
                "WHERE pt.pending_id=? AND pt.curated=1 AND r.slug='topico'", (pid,)).fetchone()[0], pre_band[pid])
        r9 = _rows(con, self.p9)
        self.assertEqual((r9["tooling"][0], r9["tooling"][3]), (None, 1))    # prioridad desconocida: curado SIN banda
        self.assertIsNone(con.execute("SELECT slug FROM pending WHERE id=?", (self.p9,)).fetchone()[0])
        self.assertEqual(pendings.recommend_priority(con, self.p9, home=self.home)["source"], "intrinsic")
        slugs = dict(con.execute("SELECT id, slug FROM pending"))
        self.assertEqual((slugs[self.p1], slugs[self.p2], slugs[self.p3], slugs[self.p7], slugs[self.p8]),
                         ("alpha-uno-nuevo", "beta-dos", "gamma-tres", "delta-siete", None))
        self.assertEqual(slugs[self.p4], "obs")                            # backfill también sobre obsoletos
        self.assertEqual(res["counts"]["backfilled"], 2)
        self.assertEqual(con.execute("SELECT a, b, relation FROM pending_link").fetchall(),
                         [(self.p2, self.p1, "related")])                 # estrella hacia el menor id; p4 obsoleto fuera
        self.assertEqual(_rows(con, self.p6)["seguridad"][:2], ("high", 80.0))   # curaduría previa NO pisada
        self.assertEqual(_rows(con, self.p4), {"old-req": ("low", 20.0, 1, 0)})  # obsoleto intacto
        self.assertEqual(res["counts"]["curated"], 5); self.assertEqual(res["counts"]["slugs_collided"], 1)
        self.assertEqual((res["counts"]["slugs_invalid"], res["counts"]["sin_banda"]), (1, 1))
        tp = pendings.triage_pass(con)
        self.assertEqual(tp["groups"], [[self.p1, self.p2]]); self.assertIn(self.p7, tp["unclassified"])
        con.close()

    def test_second_run_is_idempotent_and_force_recurates(self):
        self._pre_curate_p6()
        self._run(apply=True)
        con = _db_shared._connect(self.db, SCHEMA); d1 = seed.digest(con); con.close()
        res2, _ = self._run(apply=True)
        self.assertFalse(res2["changed"]); self.assertEqual(res2["counts"]["curated"], 0)
        self.assertEqual(res2["plan"]["backfill"], 0)                        # el estimado también converge
        con = _db_shared._connect(self.db, SCHEMA); self.assertEqual(seed.digest(con), d1)
        pendings.curate(con, self.p1, cliente="beta"); con.commit(); con.close()   # curaduría posterior
        self._run(apply=True)
        con = _db_shared._connect(self.db, SCHEMA)
        self.assertIn("beta", _rows(con, self.p1)); self.assertNotIn("alpha", _rows(con, self.p1))
        con.close()
        self._run(apply=True, force=True)
        con = _db_shared._connect(self.db, SCHEMA)
        self.assertIn("alpha", _rows(con, self.p1)); self.assertNotIn("beta", _rows(con, self.p1))
        con.close()

    def test_rollback_restores_seeded_tables_including_topic_link_and_last_reviewed(self):
        con = _db_shared._connect(self.db, SCHEMA); before = seed.digest(con)
        n_work = con.execute("SELECT count(*) FROM work").fetchone()[0]; con.close()
        res, _ = self._run(apply=True)
        con = _db_shared._connect(self.db, SCHEMA)
        self.assertNotEqual(con.execute("SELECT last_reviewed_at FROM pending WHERE id=?", (self.p1,)).fetchone()[0], "2026-01-01")
        con.close()
        counts = seed.rollback(self.db, res["backup"])
        self.assertGreater(counts["pending_topic"], 0); self.assertEqual(counts["topic_link"], 1)
        con = _db_shared._connect(self.db, SCHEMA)
        self.assertEqual(seed.digest(con), before)                            # incluye topic_link y last_reviewed_at
        self.assertEqual(con.execute("SELECT last_reviewed_at FROM pending WHERE id=?", (self.p1,)).fetchone()[0], "2026-01-01")
        self.assertEqual(con.execute("SELECT count(*) FROM work").fetchone()[0], n_work)
        con.close()

    def test_rollback_from_pre_migration_backup(self):
        """Respaldo tomado ANTES de que la DB tenga slug/curated (el caso real: primer comando del
        turno del merge): el rollback restaura las tablas y deja slug NULL / curated 0."""
        d = tempfile.mkdtemp(prefix="neb-tax-premig-")
        legacy = os.path.join(d, "neb.db")
        c = sqlite3.connect(legacy); c.executescript(LEGACY_DDL)
        c.execute("INSERT INTO work (mode, created_at, updated_at) VALUES ('exploratory','t','t')")
        c.execute("INSERT INTO topic (slug, name, keywords) VALUES ('alpha','Alpha','alpha')")
        c.execute("INSERT INTO pending (context_origin, created_at) VALUES ('[alpha-viejo] cosa uno','t')")
        c.execute("INSERT INTO pending_topic (pending_id, topic_id, priority_band, priority_score, is_primary) VALUES (1,1,'high',95.0,1)")
        c.commit(); c.close()
        bak = seed.backup_db(legacy, os.path.join(d, "pre-migracion.bak"))   # plano, sin migrar
        pre = sqlite3.connect(bak); pre_digest = seed.digest(pre)
        self.assertNotIn("slug", {r[1] for r in pre.execute("PRAGMA table_info(pending)")}); pre.close()
        res, _ = self._run_on(legacy, apply=True)                            # migra + siembra
        con = _db_shared._connect(legacy, SCHEMA)
        self.assertIsNotNone(con.execute("SELECT slug FROM pending WHERE id=1").fetchone()[0]); con.close()
        seed.rollback(legacy, bak)
        con = _db_shared._connect(legacy, SCHEMA)
        self.assertEqual(seed.digest(con), pre_digest)
        self.assertIsNone(con.execute("SELECT slug FROM pending WHERE id=1").fetchone()[0])
        self.assertEqual(con.execute("SELECT curated FROM pending_topic WHERE pending_id=1").fetchone()[0], 0)
        con.close()

    def test_archived_catalog_topic_is_skipped_without_force_and_reactivated_with_force(self):
        con = _db_shared._connect(self.db, SCHEMA)
        con.execute("UPDATE topic SET status='archived' WHERE slug='alpha'"); con.commit(); con.close()
        res, out = self._run(apply=True)                                      # sin --force: no revienta
        plan = res["plan"]
        self.assertEqual(plan["topics_reactivate"], ["alpha"])
        self.assertEqual(set(plan["skipped"]["axis_archived"]), {self.p1, self.p3, self.p6, self.p9})
        self.assertEqual(set(plan["curate"]), {self.p2, self.p8})
        self.assertIn("eje archivado (usa --force) 4", out)
        con = _db_shared._connect(self.db, SCHEMA)
        self.assertEqual(con.execute("SELECT status FROM topic WHERE slug='alpha'").fetchone()[0], "archived")
        self.assertEqual(_rows(con, self.p1), {"old-req": ("high", 95.0, 1, 0), "alpha": ("low", 1.0, 0, 0)})
        con.close()
        res2, _ = self._run(apply=True, force=True)
        con = _db_shared._connect(self.db, SCHEMA)
        self.assertEqual(con.execute("SELECT status FROM topic WHERE slug='alpha'").fetchone()[0], "active")
        self.assertEqual(_rows(con, self.p1)["alpha"][3], 1)
        self.assertIn(self.p1, res2["plan"]["curate"])
        con.close()


if __name__ == "__main__":
    unittest.main()
