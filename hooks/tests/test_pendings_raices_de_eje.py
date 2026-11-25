#!/usr/bin/env python3
"""
test_pendings_raices_de_eje.py — pendientes con la base antes del paso 3 y sugerencias sobre raíces de eje (7.4.0).

Cubre hooks/lib/pendings.py contra bases TEMPORALES (tempfile; nunca ~/.claude) con ejemplos genéricos:
  • Base que no pasó el paso de base 3 (eje proyecto): paso 2 detenido por un SQLite anterior a 3.35.5
    (simulado), así que la base sigue en la versión 1 con la raíz 'cliente'. Desde 7.4.0 el paso 3 tiene
    `espera` y pendings opera degradado: triage, curate, rank e infer-objectives responden sin excepción; el
    catálogo del eje proyecto queda vacío, los hijos de 'cliente' cuentan como temas sin eje, la raíz 'cliente'
    nunca se sugiere, `curate --proyecto` es error legible sin escribir y no aparece una raíz 'proyecto'.
  • Sugerencias (curated=0) sobre una raíz de eje, como las deja el código 7.2.x de una sesión abierta (no
    excluye la raíz 'proyecto' de sus candidatos): las lecturas las ignoran (también sobre una raíz 'cliente';
    un tema 'cliente' que no es raíz sí cuenta) y reclassify/triage las borran, nunca una fila curated=1.

Framework: unittest (stdlib).
  py -m unittest discover -s hooks/tests -p test_pendings_raices_de_eje.py
"""

import contextlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import _db_shared   # noqa: E402
import _migrations  # noqa: E402
import pendings     # noqa: E402

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")


def _home():
    d = tempfile.mkdtemp(prefix="neb-test-raices-")
    os.makedirs(os.path.join(d, ".claude"))
    return d


def _topic(con, slug, name, keywords="", parent=None):
    return con.execute("INSERT INTO topic (slug, name, description, keywords, status, parent_id) "
                       "VALUES (?,?,'',?, 'active', ?)", (slug, name, keywords, parent)).lastrowid


def _pending(con, ctx, reviewed=None):
    return con.execute("INSERT INTO pending (type, context_origin, status, created_at, last_reviewed_at) "
                       "VALUES ('task', ?, 'open', ?, ?)", (ctx, pendings.now_iso(), reviewed)).lastrowid


def _pt(con, pid, tid, curated=0, primary=0, band=None, score=None):
    con.execute("INSERT INTO pending_topic (pending_id, topic_id, priority_band, priority_score, is_primary, curated) "
                "VALUES (?,?,?,?,?,?)", (pid, tid, band, score, primary, curated))


def _rows(con, pid):
    return {r[0]: r[1] for r in con.execute(
        "SELECT t.slug, pt.curated FROM pending_topic pt JOIN topic t ON t.id = pt.topic_id "
        "WHERE pt.pending_id=?", (pid,))}


# =========================================================================== base antes del paso 3

class TestBaseSinPaso3(unittest.TestCase):
    """Paso 2 detenido (SQLite 3.34.0 simulado en toda la prueba): la base queda en la versión 1 con la raíz
    'cliente' y el paso 3 pendiente. 7.3.0 respondía paso-bloqueado a todo; 7.4.0 opera degradado."""

    def setUp(self):
        p = mock.patch.object(_migrations, "SQLITE_VERSION", (3, 34, 0))
        p.start()
        self.addCleanup(p.stop)
        self.home = _home()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.db = _db_shared.resolve_db_path(self.home)
        with contextlib.redirect_stderr(io.StringIO()):
            con = _db_shared._connect(self.db, SCHEMA)
        self.assertIsNotNone(con)
        cli = _topic(con, "cliente", "Cliente", "cliente")
        top = _topic(con, "topico", "Tópico")
        self.alpha = _topic(con, "alpha", "Alpha", "alpha", parent=cli)
        _topic(con, "beta", "Beta", "beta", parent=cli)
        seg = _topic(con, "seguridad", "Seguridad", "token, credenciales", parent=top)
        _topic(con, "tooling", "Tooling", "hook, script", parent=top)
        self.p1 = _pending(con, "curado en alpha")
        _pt(con, self.p1, self.alpha, curated=1, band="high", score=80.0)
        _pt(con, self.p1, seg, curated=1, primary=1, band="high", score=80.0)
        self.p2 = _pending(con, "token de alpha que pidio el cliente")
        self.p3 = _pending(con, "el hook del script falla")
        con.commit()
        con.close()
        self.assertEqual(self._version(), (1, 1))

    def _version(self):
        con = sqlite3.connect(self.db)
        try:
            return _migrations.read_version(con)
        finally:
            con.close()

    def _cli(self, *argv):
        def _con():
            return _db_shared._connect(self.db, SCHEMA)
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home}), \
                mock.patch.object(pendings, "_db_for_cli", _con), contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            pendings.cli_main(list(argv))
        return buf.getvalue()

    def _con(self):
        return sqlite3.connect(self.db)

    def test_critico_triage_opera_degradado_sin_sugerir_la_raiz_cliente(self):
        out = json.loads(self._cli("triage"))
        self.assertNotIn("motivo", out, out)
        self.assertEqual(out["catalog"], {"proyecto": [], "topico": ["seguridad", "tooling"]})
        items = {i["id"]: i for i in out["items"]}
        self.assertEqual((items[self.p1]["proyecto"], items[self.p1]["topico"], items[self.p1]["curated"],
                          items[self.p1]["source"]), (None, "seguridad", True, "curated"))
        sug = items[self.p2]["suggestions"]
        self.assertIn("seguridad", sug)
        self.assertIn("alpha", sug, "un hijo de 'cliente' cuenta como tema sin eje")
        self.assertNotIn("cliente", sug)
        self.assertIsNone(items[self.p2]["suggested_proyecto"])
        self.assertEqual(items[self.p3]["suggested_topico"], "tooling")
        con = self._con()
        try:
            self.assertEqual(con.execute(
                "SELECT count(*) FROM pending_topic pt JOIN topic t ON t.id = pt.topic_id "
                "WHERE t.parent_id IS NULL AND t.slug IN ('cliente','proyecto','topico')").fetchone()[0], 0,
                "ninguna fila sobre una raíz")
            self.assertIsNone(con.execute("SELECT 1 FROM topic WHERE slug='proyecto'").fetchone())
            self.assertEqual(con.execute("SELECT parent_id FROM topic WHERE slug='cliente'").fetchone(), (None,))
        finally:
            con.close()
        self.assertEqual(self._version(), (1, 1))

    def test_curate_proyecto_es_error_legible_y_topico_si_cura(self):
        con = self._con()
        before = _rows(con, self.p3)
        con.close()
        out = json.loads(self._cli("curate", str(self.p3), "--proyecto", "alpha"))
        self.assertFalse(out["ok"])
        self.assertIn("proyecto desconocido", out["error"])
        con = self._con()
        self.assertEqual(_rows(con, self.p3), before, "sin escrituras")
        con.close()
        out = json.loads(self._cli("curate", str(self.p3), "--topico", "tooling", "--band", "media"))
        self.assertTrue(out["ok"], out)
        self.assertEqual((out["proyecto"], out["topico"], out["band"]), (None, "tooling", "media"))
        out = json.loads(self._cli("curate", str(self.p3), "--topico", "cliente"))
        self.assertFalse(out["ok"], "la raíz 'cliente' no es curable")

    def test_rank_e_infer_objectives_responden(self):
        self._cli("triage")
        out = json.loads(self._cli("rank", "token alpha"))
        self.assertEqual(set(out["order"]), {self.p1, self.p2, self.p3})
        out = json.loads(self._cli("infer-objectives"))
        proposed = {t for o in out["proposed"] for t in o["topics"]}
        self.assertTrue(proposed, out)
        self.assertFalse(proposed & {"cliente", "alpha", "beta", "proyecto", "topico"},
                         "ni raíces ni hijos de 'cliente' (proyectos) como objetivos")
        self.assertIn("seguridad", proposed)


# =========================================================================== sugerencias sobre raíces

class TestSugerenciasSobreRaices(unittest.TestCase):
    """Filas curated=0 sobre una raíz de eje sembradas a mano, como las deja 7.2.x."""

    def setUp(self):
        self.home = _home()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.con = _db_shared._connect(_db_shared.resolve_db_path(self.home), SCHEMA)
        self.addCleanup(self.con.close)
        c = self.con
        self.proy = _topic(c, "proyecto", "Proyecto")
        top = _topic(c, "topico", "Tópico")
        self.cli = _topic(c, "cliente", "Cliente", "cliente")           # raíz vieja (p. ej. una base a medias)
        _topic(c, "alpha", "Alpha", "alpha", parent=self.proy)
        self.seg = _topic(c, "seguridad", "Seguridad", "token", parent=top)
        # p: sugerencia válida + sugerencia sobre la raíz 'proyecto' (no entra al delta de reclassify)
        self.p = _pending(c, "token expuesto", reviewed="2026-01-01")
        _pt(c, self.p, self.seg, primary=1, score=1.0)
        _pt(c, self.p, self.proy, score=5.0)
        _pt(c, self.p, self.cli, score=4.0)
        # q: una fila curated=1 sobre la raíz (anómala): nunca se borra
        self.q = _pending(c, "curado raro", reviewed="2026-01-01")
        _pt(c, self.q, self.seg, curated=1, primary=1, band="low", score=20.0)
        _pt(c, self.q, self.proy, curated=1)
        c.commit()

    def _root_suggestions(self):
        return self.con.execute(
            "SELECT pending_id, topic_id FROM pending_topic WHERE curated=0 AND topic_id IN (?,?) "
            "ORDER BY 1, 2", (self.proy, self.cli)).fetchall()

    def test_critico_las_lecturas_ignoran_las_sugerencias_sobre_raices(self):
        ax = pendings.pending_axes(self.con, self.p)
        self.assertEqual(ax["suggestions"], ["seguridad"])
        self.assertEqual(ax["suggested_topico"], "seguridad")
        self.assertIsNone(ax["suggested_proyecto"])
        eff = [t[0] for t in pendings._effective_topics(self.con, self.p)]
        self.assertEqual(eff, ["seguridad"])
        rec = pendings.recommend_priority(self.con, self.p, home=self.home)
        self.assertEqual(set(rec["by_topic"]), {"seguridad"})
        proposed = {t for o in pendings.infer_objectives(self.con, home=self.home)["proposed"] for t in o["topics"]}
        self.assertFalse(proposed & {"proyecto", "cliente"})

    def test_critico_triage_borra_las_sugerencias_sobre_raices_y_no_lo_curado(self):
        self.assertEqual(len(self._root_suggestions()), 2)
        pendings._with_write_tx(self.con, pendings.triage_pass)
        self.assertEqual(self._root_suggestions(), [])
        self.assertEqual(_rows(self.con, self.p), {"seguridad": 0}, "la sugerencia válida se queda")
        self.assertEqual(_rows(self.con, self.q), {"seguridad": 1, "proyecto": 1}, "curated=1 nunca se borra")

    def test_reclassify_en_modo_cli_las_borra_en_su_propia_transaccion(self):
        pendings.reclassify(self.con)
        self.assertFalse(self.con.in_transaction)
        self.assertEqual(self._root_suggestions(), [])
        self.assertEqual(_rows(self.con, self.q)["proyecto"], 1)

    def test_tema_cliente_que_no_es_raiz_si_cuenta(self):
        """'cliente' solo es raíz de eje sin padre: un tema 'cliente' que cuelga de un eje es un tema más."""
        self.con.execute("DELETE FROM pending_topic WHERE topic_id=?", (self.cli,))
        self.con.execute("UPDATE topic SET parent_id=? WHERE id=?", (self.proy, self.cli))
        r = _pending(self.con, "aviso", reviewed="2026-01-01")
        _pt(self.con, r, self.cli, score=1.0)
        self.con.commit()
        self.assertEqual(pendings.pending_axes(self.con, r)["suggested_proyecto"], "cliente")
        pendings._with_write_tx(self.con, pendings.triage_pass)
        self.assertEqual(_rows(self.con, r), {"cliente": 0})


if __name__ == "__main__":
    unittest.main()
