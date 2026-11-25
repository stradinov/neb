#!/usr/bin/env python3
"""
test_pendings_recommend.py — Sub-entrega C (REQ neb-pendings-sqlite): recomendador + priorización.

Cubre contra DBs TEMPORALES (tempfile) + compas.md temporal (home= bajo el tmp):
  • normalize: minúsculas + sin acentos (reusa la de B; aquí solo se consume)
  • jerarquía prompt > compas > intrínsecas (T2/T3)
  • compas = fuente única de pesos -> banda alta (T3)
  • sin roadmap (7.3.0): un criterio con 'roadmap' es texto libre como cualquier otro (T4)
  • prioridad POR TEMA: el mismo pending difiere en dos temas (T5)
  • sin compas -> infer_objectives propone, NO inventa pesos ni escribe (T6)
  • sentinel sin-clasificar -> source unclassified, banda baja, score 0 (T7)
  • enums en INGLES consistentes en DB (T8)
  • señal intrínseca: un pending que BLOQUEA a otro sube de prioridad (T9)
  • parse_compas defensivo + traducción band_to_db (extra)
  • lote: triage parsea compas.md UNA vez por llamada y sus consultas no crecen con los pendientes (extra)

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
    objectives = [(name, weight, [topics][, {proyecto: bonus}]), ...]."""
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
        _write_compas(self.home, [("Deuda", 40, ["alpha"])])   # compas daría 40
        r = P.recommend_priority(self.con, 1, prompt_criterion="urgente alpha", home=self.home)
        self.assertEqual(r["source"], "prompt")

    # T3 — compas es fuente única de pesos: tema con peso alto -> banda alta
    def test_compas_single_source_of_weights(self):
        _seed_pending(self.con, pid=2, status="open", topic="alpha")
        _write_compas(self.home, [("Tienda", 90, ["alpha"])])
        r = P.recommend_priority(self.con, 2, home=self.home)
        self.assertEqual(r["source"], "compas")
        self.assertEqual(r["band"], "alta")
        self.assertGreaterEqual(r["score"], 67)

    # T4 — sin roadmap (7.3.0): la palabra 'roadmap' en el criterio ya no busca un repo roadmap ni
    # afina por iniciativas; puntúa por tokens como cualquier criterio de texto libre.
    def test_roadmap_word_is_plain_criterion(self):
        _seed_pending(self.con, pid=3, status="open", topic="catalogo")
        _seed_pending(self.con, pid=30, status="open", topic="pedidos")
        self.assertFalse(hasattr(P, "_roadmap_fine_order"))
        self.assertFalse(hasattr(P, "_detect_roadmap_project"))
        r = P.rank_by_external_criterion(self.con, [3, 30], "roadmap pedidos")
        self.assertEqual(r["order"], [30, 3])
        self.assertEqual(r["scores"], {30: 50.0, 3: 0.0})       # 1 de 2 tokens ('pedidos'), 'roadmap' no matchea
        self.assertIn("match de tokens", r["rationale"])

    # T5 — prioridad por tema: el mismo pending difiere en dos temas
    def test_priority_per_topic(self):
        _seed_pending(self.con, pid=4, status="open", topics=["alpha", "neb"])
        _write_compas(self.home, [("Tienda", 90, ["alpha"]),
                                  ("Deuda", 30, ["neb"])])
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
        _write_compas(self.home, [("A", 40, ["alpha"]),
                                  ("B", 80, ["alpha"])])
        c = P.parse_compas(self.home)
        self.assertEqual(c["topic_weight"]["alpha"], 80)



class TriageBatchTests(unittest.TestCase):
    """Eficiencia de `triage` (7.3.0): compas.md se parsea una vez por llamada (no por pendiente) y,
    con el delta de classify vacío, el número de sentencias SQL no depende de cuántos pendientes hay
    (sin N+1 en pending_topic, banda curada, sugerencias ni señales intrínsecas)."""

    def setUp(self):
        import _db_shared
        self._db_shared = _db_shared
        self.home = tempfile.mkdtemp(prefix="neb-recommend-batch-")
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        P.write_compas(self.home, [("Seg", 70, ["seguridad"], {"alpha": 10})])

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def _db(self, n):
        path = os.path.join(self.home, ".claude", f"neb-{n}.db")
        con = self._db_shared._connect(path, SCHEMA)
        roots = {}
        for axis in P.AXIS_ROOTS:
            roots[axis] = con.execute("INSERT INTO topic (slug, name, keywords, status) VALUES (?,?,'','active')",
                                      (axis, axis)).lastrowid
        con.execute("INSERT INTO topic (slug, name, keywords, status, parent_id) VALUES "
                    "('alpha','Alpha','alpha','active',?)", (roots["proyecto"],))
        con.execute("INSERT INTO topic (slug, name, keywords, status, parent_id) VALUES "
                    "('seguridad','Seguridad','token, seguridad','active',?)", (roots["topico"],))
        for i in range(n):
            pid = P.create(con, "task", f"token expuesto en alpha {i}")
            if i % 3 == 0:
                P.curate(con, pid, proyecto="alpha", topico="seguridad", band="media")
        con.commit(); con.close()
        return path

    def _triage(self, path, trace=None):
        def _con():
            con = self._db_shared._connect(path, SCHEMA)
            if trace is not None:
                con.set_trace_callback(trace.append)
            return con
        from unittest import mock
        import contextlib, io, json
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home}), \
                mock.patch.object(P, "_db_for_cli", _con), contextlib.redirect_stdout(buf):
            P.cli_triage([])
        return json.loads(buf.getvalue())

    def test_compas_parsed_once_per_triage(self):
        from unittest import mock
        path = self._db(12)
        calls = []
        real = P.parse_compas

        def counting(*a, **kw):
            calls.append(a)
            return real(*a, **kw)
        with mock.patch.object(P, "parse_compas", counting):
            out = self._triage(path)
        self.assertEqual(len(out["items"]), 12)
        self.assertEqual(len(calls), 1)
        curated = [it for it in out["items"] if it["curated"]]
        self.assertTrue(curated and all(it["source"] == "curated" for it in curated))
        self.assertTrue(any(it["source"] == "compas" for it in out["items"] if not it["curated"]))

    def test_statement_count_does_not_grow_with_pendings(self):
        counts = {}
        for n in (4, 40):
            path = self._db(n)
            self._triage(path)                      # 1er pase: classify del delta (crece con n, es escritura)
            trace = []
            out = self._triage(path, trace)         # 2º pase: delta vacío -> solo lectura por lotes
            self.assertEqual(out["classified"], 0)
            counts[n] = len(trace)
        self.assertEqual(counts[4], counts[40], counts)


if __name__ == "__main__":
    unittest.main()
