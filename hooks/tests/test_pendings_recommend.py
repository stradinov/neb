#!/usr/bin/env python3
"""
test_pendings_recommend.py — Sub-entrega C (REQ neb-pendings-sqlite): recomendador + priorización.

Cubre contra DBs TEMPORALES (tempfile) + compas.md temporal (home= bajo el tmp) +
roadmap mock temporal (NEB_ROADMAP_DIR):
  • normalize: minúsculas + sin acentos (reusa la de B; aquí solo se consume)
  • jerarquía prompt > compas > intrínsecas (T2/T3)
  • compas = fuente única de pesos -> banda alta (T3)
  • orden fino por roadmap REAL con tokens acentuados 'catálogo, pedidos' (T4 — CIERRA HUECO #5)
  • prioridad POR TEMA: el mismo pending difiere en dos temas (T5)
  • sin compas -> infer_objectives propone, NO inventa pesos ni escribe (T6)
  • sentinel sin-clasificar -> source unclassified, banda baja, score 0 (T7)
  • enums en INGLES consistentes en DB (T8)
  • señal intrínseca: un pending que BLOQUEA a otro sube de prioridad (T9)
  • parse_compas defensivo + traducción band_to_db (extra)

Framework: unittest (stdlib), NO pytest. NUNCA toca ~/.claude/*.db ni ~/.claude/compas.md.
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import pendings as P  # noqa: E402

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")


# --------------------------------------------------------------------------- helpers

def _open_seeded_db(home):
    """Conexión a una DB temporal bajo <home>/.claude con el schema A (6 tablas) + FK ON."""
    db = os.path.join(home, ".claude", "neb.db")
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())
    return con


def _ensure_topic(con, slug, status="active"):
    """Crea/asegura un topic por slug (status INGLES) y devuelve su id."""
    con.execute(
        "INSERT OR IGNORE INTO topic (slug, name, description, keywords, status) "
        "VALUES (?,?,?,?,?)", (slug, slug, "", slug, status))
    return con.execute("SELECT id FROM topic WHERE slug=?", (slug,)).fetchone()[0]


def _seed_pending(con, pid, status="open", topic=None, topics=None, is_primary_first=True):
    """Inserta un pending (status INGLES 'open') con id explícito + filas pending_topic.
    topic= un slug | topics= lista de slugs (priority_band se deja NULL: C lo recomienda)."""
    con.execute(
        "INSERT INTO pending (id, type, context_origin, status, created_at) "
        "VALUES (?, 'task', ?, ?, ?)", (pid, f"ctx-{pid}", status, P.now_iso()))
    slugs = topics if topics is not None else ([topic] if topic else [])
    for i, slug in enumerate(slugs):
        tid = _ensure_topic(con, slug)
        con.execute(
            "INSERT INTO pending_topic (pending_id, topic_id, is_primary) VALUES (?,?,?)",
            (pid, tid, 1 if (i == 0 and is_primary_first) else 0))
    con.commit()


def _write_compas(home, objectives):
    """Materializa compas.md vía el writer del módulo (mismo formato que parse_compas espera).
    objectives = [(name, weight, [topics], roadmap_or_None), ...]."""
    return P.write_compas(home, objectives)


# --------------------------------------------------------------------------- base

class RecommendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-recommend-")
        self.home = self.tmp
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        self.con = _open_seeded_db(self.home)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # T1 — normalize: minúsculas + sin acentos (reusa la de B; NO hace strip ni tokeniza)
    def test_normalize_diacritics(self):
        self.assertEqual(P.normalize("Catálogo"), "catalogo")
        self.assertEqual(P.normalize("Analítica"), "analitica")
        self.assertEqual(P.normalize("PEDIDOS"), "pedidos")
        # el trim/tokenización lo hace el caller sobre el CSV (parse_compas split + normalize por token)
        self.assertEqual(P.normalize(" Pedidos ").strip(), "pedidos")

    # T2 — jerarquía: prompt manda sobre compas
    def test_prompt_overrides_compas(self):
        _seed_pending(self.con, pid=1, status="open", topic="alpha")
        _write_compas(self.home, [("Deuda", 40, ["alpha"], None)])   # compas daría 40
        r = P.recommend_priority(self.con, 1, prompt_criterion="urgente alpha", home=self.home)
        self.assertEqual(r["source"], "prompt")

    # T3 — compas es fuente única de pesos: tema con peso alto -> banda alta
    def test_compas_single_source_of_weights(self):
        _seed_pending(self.con, pid=2, status="open", topic="alpha")
        _write_compas(self.home, [("Clientes", 90, ["alpha"], None)])
        r = P.recommend_priority(self.con, 2, home=self.home)
        self.assertEqual(r["source"], "compas")
        self.assertEqual(r["band"], "alta")
        self.assertGreaterEqual(r["score"], 67)

    # T4 — orden fino por roadmap REAL (tokens reales 'catalogo','pedidos') — CIERRA HUECO #5
    def test_roadmap_fine_order_real_tokens(self):
        _seed_pending(self.con, pid=3, status="open", topic="catalogo")   # tema sin acento en DB
        rmdir = os.path.join(self.tmp, "roadmap", "alpha")
        os.makedirs(os.path.join(rmdir, "initiatives", "INIT-001-x"), exist_ok=True)
        # frontmatter REAL: subsystems con acentos 'catálogo, pedidos', priority alta
        with open(os.path.join(rmdir, "initiatives", "INIT-001-x", "initiative.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\nid: INIT-001\npriority: alta\nstatus: En análisis\n"
                    "subsystems: [catálogo, pedidos]\n---\n# x\n")
        os.environ["NEB_ROADMAP_DIR"] = os.path.join(self.tmp, "roadmap")
        try:
            _write_compas(self.home, [("Roadmap alpha", 60, ["catalogo"], "alpha")])
            r = P.recommend_priority(self.con, 3, home=self.home)
            # base 60 (compas) + bonus 'alta' (15) por match catálogo<->catalogo vía normalize/token
            self.assertEqual(r["source"], "compas")
            self.assertGreater(r["score"], 60)        # el roadmap afinó al alza
        finally:
            del os.environ["NEB_ROADMAP_DIR"]

    # T4b — fallback a la tabla maestra de roadmap.md (sin initiatives/)
    def test_roadmap_fine_order_master_table(self):
        _seed_pending(self.con, pid=30, status="open", topic="pedidos")
        rmdir = os.path.join(self.tmp, "roadmap", "alpha")
        os.makedirs(rmdir, exist_ok=True)
        with open(os.path.join(rmdir, "roadmap.md"), "w", encoding="utf-8") as f:
            f.write(
                "## Tabla maestra\n\n"
                "| ID | Nombre | Prioridad | Estado | Owner | status-since | Subsistemas |\n"
                "|---|---|---|---|---|---|---|\n"
                "| INIT-001 | Pedido por catálogo | alta | En análisis | business | 2026-06-12 | catálogo, pedidos |\n")
        os.environ["NEB_ROADMAP_DIR"] = os.path.join(self.tmp, "roadmap")
        try:
            _write_compas(self.home, [("Roadmap alpha", 60, ["pedidos"], "alpha")])
            r = P.recommend_priority(self.con, 30, home=self.home)
            self.assertGreater(r["score"], 60)
        finally:
            del os.environ["NEB_ROADMAP_DIR"]

    # T5 — prioridad por tema: el mismo pending difiere en dos temas
    def test_priority_per_topic(self):
        _seed_pending(self.con, pid=4, status="open", topics=["alpha", "neb"])
        _write_compas(self.home, [("Clientes", 90, ["alpha"], None),
                                  ("Deuda", 30, ["neb"], None)])
        r = P.recommend_priority(self.con, 4, home=self.home)
        self.assertIn("alpha", r["by_topic"])
        self.assertIn("neb", r["by_topic"])
        self.assertGreater(r["by_topic"]["alpha"]["score"], r["by_topic"]["neb"]["score"])

    # T6 — sin compas -> infer_objectives propone, NO inventa pesos ni escribe
    def test_infer_when_no_compas(self):
        _seed_pending(self.con, pid=5, status="open", topic="alpha")
        self.assertFalse(P.parse_compas(self.home)["exists"])
        out = P.infer_objectives(self.con, home=self.home)
        self.assertTrue(out["proposed"])                      # propone algo
        self.assertIn("alpha", [t for o in out["proposed"] for t in o["topics"]])
        # y NO escribió compas.md por su cuenta:
        self.assertFalse(os.path.isfile(os.path.join(self.home, ".claude", "compas.md")))

    # T7 — sentinel sin-clasificar -> source unclassified, banda baja, score 0
    def test_unclassified_sentinel(self):
        _seed_pending(self.con, pid=6, status="open", topic=P.SENTINEL_SLUG)
        r = P.recommend_priority(self.con, 6, home=self.home)
        self.assertEqual(r["source"], "unclassified")
        self.assertEqual(r["band"], "baja")
        self.assertEqual(r["score"], 0)

    # T8 — enums en INGLES consistentes (guarda contra regresión activo/active)
    def test_enums_english(self):
        _seed_pending(self.con, pid=7, status="open", topic="alpha")
        row = self.con.execute("SELECT status FROM pending WHERE id=7").fetchone()
        self.assertEqual(row[0], "open")              # nunca 'activo'/'abierto' en DB
        trow = self.con.execute("SELECT status FROM topic WHERE slug='alpha'").fetchone()
        self.assertEqual(trow[0], "active")           # nunca 'activo' en DB

    # T9 — señal intrínseca: pending que BLOQUEA a otro sube de prioridad
    def test_intrinsic_blocks_raises(self):
        _seed_pending(self.con, pid=8, status="open", topic="neb")
        _seed_pending(self.con, pid=9, status="open", topic="neb")
        self.con.execute("INSERT INTO pending_link (a,b,relation) VALUES (8,9,'blocks')")
        self.con.commit()
        base = P.recommend_priority(self.con, 9, home=self.home)["score"]
        blk  = P.recommend_priority(self.con, 8, home=self.home)["score"]
        self.assertGreater(blk, base)

    # extra — parse_compas defensivo: ausente -> exists False
    def test_parse_compas_absent(self):
        self.assertFalse(P.parse_compas(self.home)["exists"])
        self.assertEqual(P.parse_compas(self.home)["topic_weight"], {})

    # extra — traducción de bandas a persistencia INGLES
    def test_band_to_db_english(self):
        self.assertEqual(P.band_to_db("alta"), "high")
        self.assertEqual(P.band_to_db("media"), "medium")
        self.assertEqual(P.band_to_db("baja"), "low")

    # extra — parse_compas: un tema en >1 objetivo gana el mayor peso
    def test_parse_compas_max_weight(self):
        _write_compas(self.home, [("A", 40, ["alpha"], None),
                                  ("B", 80, ["alpha"], None)])
        c = P.parse_compas(self.home)
        self.assertEqual(c["topic_weight"]["alpha"], 80)


if __name__ == "__main__":
    unittest.main()
