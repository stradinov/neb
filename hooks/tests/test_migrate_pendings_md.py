#!/usr/bin/env python3
"""
test_migrate_pendings_md.py — migrador del pendings.md → neb.db (REQ neb-pendings-sqlite).

Cubre bootstrap/migrate-pendings-md.py contra un pendings.md de MUESTRA en tempfile y DBs
TEMPORALES:
  • parser: secciones→topics, ítems numerados, sub-ítems (a)/(b), líneas no clasificadas.
  • regla de estado: ACTIVOS migran; CERRADO/DESCARTADO/RESUELTO/✅-cabecera se OMITEN;
    sub-ítems ACTIVOS de un ítem CERRADO SÍ migran.
  • plan (dry-run): conteos de pendings/topics/links sin tocar DB.
  • --apply: crea pending/topic/pending_link; idempotente (re-correr no duplica).
  • relación 'depends' cuando el sub-ítem es prerequisito/bloqueante; 'related' si no.

Ejemplos GENÉRICOS (alpha/beta), NUNCA clientes reales. Framework: unittest (stdlib).
NUNCA toca ~/.claude/*.db ni ~/.claude/pendings.md.
"""

import os
import sys
import importlib.util
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared          # noqa: E402
import pendings            # noqa: E402

# El script vive en bootstrap/ con guiones en el nombre → carga por path (no importable por nombre).
_MIG_PATH = os.path.join(HERE, "..", "..", "bootstrap", "migrate-pendings-md.py")
_spec = importlib.util.spec_from_file_location("migrate_pendings_md", _MIG_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")


# pendings.md de muestra: 2 secciones, ítems activos y cerrados, sub-ítems mixtos.
SAMPLE_MD = """\
# Pendientes del dev

## alpha — primer tema — 2026-01-01

> Una línea de quote que el parser no debe clasificar como ítem.

1. **[alpha-uno] Hacer la cosa uno — En progreso.** Descripción autocontenida del ítem uno.
    - **(a) Sub-tarea activa relacionada.** Detalle del sub-ítem a.
    - **(b) CERRADO 2026-01-02.** Este sub-ítem ya está cerrado y se omite.

2. ✅ **[alpha-dos] CERRADO 2026-01-02.** Ítem cerrado de cabecera; se omite el padre.
    - **(a) Prerequisito que bloquea el cierre — En cola.** Este sub-ítem es prerequisito del padre.

## beta — segundo tema

3. **[beta-uno] Otra tarea — En validación.** Cuerpo del ítem tres, sin sub-ítems.

4. **[beta-dos] DESCARTADO 2026-01-03.** Ítem descartado, sin sub-ítems activos.
"""


def _fresh_db():
    d = tempfile.mkdtemp(prefix="neb-migtest-")
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    return _db_shared.resolve_db_path(d)


def _write_sample(text=SAMPLE_MD):
    fd, path = tempfile.mkstemp(prefix="pendings-", suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class TestParser(unittest.TestCase):

    def test_topics_detected(self):
        parsed = mig.parse(SAMPLE_MD)
        self.assertEqual(parsed["topics"], ["alpha", "beta"])

    def test_items_and_subitems_counted(self):
        parsed = mig.parse(SAMPLE_MD)
        # 4 ítems numerados, con sub-ítems anidados en los dos primeros
        items = [u for u in parsed["units"] if u["item"] is not None]
        self.assertEqual(len(items), 4)
        # ítem 1 → 2 sub-ítems; ítem 2 → 1 sub-ítem
        by_title = {u["item"].title: u for u in items}
        self.assertEqual(len(by_title["alpha-uno"]["subitems"]), 2)
        self.assertEqual(len(by_title["alpha-dos"]["subitems"]), 1)

    def test_quote_line_goes_unparsed(self):
        parsed = mig.parse(SAMPLE_MD)
        self.assertTrue(any("quote" in u for u in parsed["unparsed"]))

    def test_subitem_label_captured(self):
        parsed = mig.parse(SAMPLE_MD)
        by_title = {u["item"].title: u for u in parsed["units"] if u["item"]}
        labels = [s.label for s in by_title["alpha-uno"]["subitems"]]
        self.assertEqual(labels, ["a", "b"])


class TestStateHeuristic(unittest.TestCase):

    def test_active_vs_closed_headers(self):
        self.assertTrue(mig._is_closed_header("2. ✅ **[x] CERRADO 2026-01-02.**"))
        self.assertTrue(mig._is_closed_header("4. **[x] DESCARTADO 2026-01-03.**"))
        self.assertTrue(mig._is_closed_header("- **(b) RESUELTO.** ya"))
        self.assertFalse(mig._is_closed_header("1. **[x] Hacer la cosa — En progreso.**"))
        self.assertFalse(mig._is_closed_header("3. **[x] Otra — En validación.**"))

    def test_inline_check_does_not_close(self):
        # un ✅ a mitad de cuerpo NO cierra el ítem (marca un sub-paso hecho)
        self.assertFalse(mig._is_closed_header(
            "1. **[x] En progreso** con un ✅ paso hecho pero el ítem sigue abierto"))


class TestPlan(unittest.TestCase):

    def test_plan_counts(self):
        parsed = mig.parse(SAMPLE_MD)
        plan = mig.build_plan(parsed)
        # activos: alpha-uno (item), alpha-uno(a) (sub), alpha-dos(a) (sub), beta-uno (item) = 4
        self.assertEqual(len(plan.pendings), 4)
        titles = sorted(p["title"] for p in plan.pendings)
        self.assertEqual(len(titles), 4)
        self.assertIn("alpha-uno", titles)
        self.assertIn("beta-uno", titles)
        # omitidos: alpha-uno(b), alpha-dos (item), beta-dos (item) = 3
        self.assertEqual(len(plan.omitted), 3)

    def test_links_relation(self):
        parsed = mig.parse(SAMPLE_MD)
        plan = mig.build_plan(parsed)
        # alpha-uno(a) → alpha-uno : related ; alpha-dos(a) tiene padre CERRADO → sin link en el plan.
        # build_plan solo liga sub-ítems activos a su ítem padre cuando el padre existe en el plan.
        parent_links = [lk for lk in plan.links if lk["parent_title"] == "alpha-uno"]
        self.assertEqual(len(parent_links), 1)
        self.assertEqual(parent_links[0]["relation"], "related")
        # el sub-ítem de alpha-dos (cerrado) no produce link en el plan (padre no está en pendings)
        self.assertEqual([lk for lk in plan.links if lk["parent_title"] == "alpha-dos"], [])

    def test_depends_detection(self):
        md = ("## g — t\n\n"
              "1. **[p] Padre — En progreso.** cuerpo.\n"
              "    - **(a) Prerequisito que bloquea al padre — En cola.** depende.\n")
        plan = mig.build_plan(mig.parse(md))
        deps = [lk for lk in plan.links if lk["relation"] == "depends"]
        self.assertEqual(len(deps), 1)


class TestApply(unittest.TestCase):

    def test_apply_creates_rows(self):
        db = _fresh_db()
        src = _write_sample()
        plan, counts = mig.run(src, db, do_apply=True)
        self.assertIsNotNone(counts)
        self.assertEqual(counts["pendings_created"], 4)

        con = _db_shared._connect(db, SCHEMA)
        # 4 pendings open
        self.assertEqual(con.execute(
            "SELECT count(*) FROM pending WHERE status='open'").fetchone()[0], 4)
        # topics: alpha, beta, sentinel (sin-clasificar)
        slugs = {r[0] for r in con.execute("SELECT slug FROM topic").fetchall()}
        self.assertIn("alpha", slugs)
        self.assertIn("beta", slugs)
        self.assertIn(pendings.SENTINEL_SLUG, slugs)
        # al menos 1 link (sub-ítem activo de ítem activo)
        self.assertGreaterEqual(con.execute("SELECT count(*) FROM pending_link").fetchone()[0], 1)
        # cada pending activo asociado a algún topic
        self.assertEqual(con.execute(
            "SELECT count(DISTINCT pending_id) FROM pending_topic").fetchone()[0], 4)
        con.close()
        os.remove(src)

    def test_apply_is_idempotent(self):
        db = _fresh_db()
        src = _write_sample()
        mig.run(src, db, do_apply=True)
        _, counts2 = mig.run(src, db, do_apply=True)   # segunda corrida
        self.assertEqual(counts2["pendings_created"], 0)
        self.assertEqual(counts2["pendings_reused"], 4)

        con = _db_shared._connect(db, SCHEMA)
        # sigue habiendo exactamente 4 pendings (no se duplicaron)
        self.assertEqual(con.execute("SELECT count(*) FROM pending").fetchone()[0], 4)
        # tampoco se duplicaron links
        self.assertEqual(con.execute("SELECT count(*) FROM pending_link").fetchone()[0],
                         con.execute("SELECT count(DISTINCT a||'-'||b||'-'||relation) "
                                     "FROM pending_link").fetchone()[0])
        con.close()
        os.remove(src)

    def test_context_origin_is_full_text(self):
        db = _fresh_db()
        src = _write_sample()
        mig.run(src, db, do_apply=True)
        con = _db_shared._connect(db, SCHEMA)
        rows = [r[0] for r in con.execute("SELECT context_origin FROM pending").fetchall()]
        # el context_origin del ítem activo conserva su descripción completa
        self.assertTrue(any("Descripción autocontenida del ítem uno" in r for r in rows))
        con.close()
        os.remove(src)


class TestDryRunNoWrite(unittest.TestCase):

    def test_dry_run_does_not_open_db(self):
        src = _write_sample()
        # db_path inexistente: en dry-run NO debe intentar abrirlo/crearlo
        bogus_db = os.path.join(tempfile.mkdtemp(prefix="neb-nodb-"), "does-not-exist.db")
        plan, counts = mig.run(src, bogus_db, do_apply=False)
        self.assertIsNotNone(plan)
        self.assertIsNone(counts)
        self.assertFalse(os.path.exists(bogus_db))   # no se creó
        os.remove(src)


if __name__ == "__main__":
    unittest.main()
