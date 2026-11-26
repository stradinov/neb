#!/usr/bin/env python3
"""
test_migration_7_4_0.py — la migración guiada de neb 7.4.0 (migrations/7.4.0.py) y su punta a punta con el
paso de base 3, que desde 7.4.0 resuelve solo el choque de slug.

Cubre, con el árbol real y homes temporales:
  • la migración carga con su paso (compas-tema-proyecto), que corre solo y deja respaldo;
  • punta a punta con `apply --guiados`: base en la versión 2 con raíz 'cliente' y un tema 'proyecto' citado en
    «- **Temas:**» de compas.md; el paso de base 3 mueve el tema a 'proyecto-<id>' y la raíz toma 'proyecto', y
    el paso guiado cambia la cita en compas.md (respaldo con los bytes originales); el peso del objetivo vuelve a
    caer sobre el tema movido (parse_compas); la segunda corrida no lo marca; nada de esto pide al dev;
  • no se marca sin tema movido, sin compas.md o sin la cita; las demás líneas y los fines de línea se conservan;
  • compas.md de solo lectura: se reescribe y conserva la protección; falla sembrada al reemplazar: el original
    queda intacto, con su protección y sin respaldo ni temporal.

Disposición de 8.0.0: la base, compas.md y los respaldos en la carpeta de datos del home temporal (<home>/.neb,
sin NEB_DATA: _entorno); con la de 7.x (en ~/.claude), la cubre test_migration_8_0_0.py. Nunca toca ~/.claude,
~/.neb, neb.db ni compas.md reales.
  py -m unittest hooks.tests.test_migration_7_4_0
"""

import contextlib
import glob
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _sin_registro  # noqa: E402,F401 — sin el registro real de Windows
import _entorno  # noqa: E402,F401 — quita NEB_DATA: la carpeta de datos es la del home temporal

NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(NEB, "hooks", "lib"))

import _db_shared  # noqa: E402
import _guided  # noqa: E402
import _machine  # noqa: E402
import _migrations  # noqa: E402
import pendings  # noqa: E402

V = "7.4.0"
SCHEMA = os.path.join(NEB, "hooks", "logbook-schema.sql")

COMPAS = ("---\r\nversion: 3\r\n---\r\n\r\n"
          "## Objetivo: Proyecto estrella\r\n- **Peso:** 80\r\n- **Temas:** seguridad, proyecto , deuda\r\n"
          "- **Proyectos:** alpha=+10\r\n\r\n"
          "## Objetivo: Otro\r\n- **Peso:** 20\r\n- **Temas:** deuda\r\n"
          "Una línea de prosa que dice proyecto no se toca.\r\n")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nm = _load("neb_migrate_740_test", os.path.join(NEB, "bootstrap", "neb-migrate.py"))


def _migration():
    migrations, errors = _guided.load(NEB)
    bad = [e for e in errors if e[0] == V + ".py"]
    if bad:
        raise AssertionError(f"7.4.0.py no carga: {bad}")
    for m in migrations:
        if m.version == V:
            return m
    raise AssertionError("no se encontró la migración 7.4.0")


def _step(step_id="compas-tema-proyecto"):
    return {s.id: s for s in _migration().steps}[step_id]


class FakeUserEnv:
    kind = "windows"

    def present_user(self, name):
        return False

    def present_machine(self, name):
        return False


class Base(unittest.TestCase):

    def setUp(self):
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        self.home = tempfile.mkdtemp(prefix="neb-test-740-")
        self.addCleanup(self._rmtree)
        os.environ.update(HOME=self.home, USERPROFILE=self.home)
        self.claude = os.path.join(self.home, ".claude")
        os.makedirs(self.claude)
        self.data = os.path.join(self.home, ".neb")      # carpeta de datos (8.0.0)
        os.makedirs(self.data)
        self.db = os.path.join(self.data, "neb.db")
        self.compas = os.path.join(self.data, "compas.md")
        self.backups = os.path.join(self.data, "backups")
        self.env = FakeUserEnv()
        p = mock.patch.object(_machine, "default_user_env", lambda: self.env)
        p.start()
        self.addCleanup(p.stop)

    def _rmtree(self):
        for root, _dirs, files in os.walk(self.home):
            for f in files:
                try:
                    os.chmod(os.path.join(root, f), stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
        shutil.rmtree(self.home, True)

    def ctx(self):
        return _machine.Ctx(self.home, db_path=self.db, user_env=self.env)

    def v2_db_con_choque(self):
        """Base en la versión 2 (como la deja 7.2.x) con la raíz 'cliente' y un tema 'proyecto' (id 51)."""
        with contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(self.db, SCHEMA, steps=_migrations.STEPS[:2]).close()
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO topic (id, slug, name) VALUES (33, 'cliente', 'Cliente')")
        con.execute("INSERT INTO topic (id, slug, name, parent_id) VALUES (40, 'alpha', 'Alpha', 33)")
        con.execute("INSERT INTO topic (id, slug, name) VALUES (34, 'topico', 'Tópico')")
        con.execute("INSERT INTO topic (id, slug, name, parent_id) VALUES (51, 'proyecto', 'Proyecto', 34)")
        con.commit()
        con.close()

    def migrar_base(self):
        with contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(self.db, SCHEMA).close()

    def write_compas(self, text):
        with open(self.compas, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def read_bytes(self, path):
        with open(path, "rb") as fh:
            return fh.read()

    def compas_backups(self):
        return sorted(glob.glob(os.path.join(self.backups, "compas.pre-7.4.0.*.md")))


class TestCarga(unittest.TestCase):

    def test_carga_con_su_paso(self):
        steps = {s.id: s for s in _migration().steps}
        self.assertEqual(set(steps), {"compas-tema-proyecto"})
        s = steps["compas-tema-proyecto"]
        self.assertTrue(s.respaldo)
        self.assertFalse(s.exclusivo)
        self.assertTrue(os.path.isfile(_migration().prompt or ""), "falta migrations/7.4.0.md")


class TestCompasTemaProyecto(Base):

    def apply(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.apply(self.home, (), False, True)
        return rc, json.loads(out.getvalue())

    def test_critico_punta_a_punta_mueve_el_tema_y_cambia_la_cita(self):
        self.v2_db_con_choque()
        self.write_compas(COMPAS)
        original = self.read_bytes(self.compas)
        rc, out = self.apply()
        g = out["guiados"]
        self.assertIn(f"{V}:compas-tema-proyecto", {r["id"] for r in g["aplicados"]}, out)
        self.assertEqual([r for r in g["pendientes"] if r["id"].startswith(V)], [])
        con = sqlite3.connect(self.db)
        try:
            topics = dict(con.execute("SELECT id, slug FROM topic"))
            v, _f = _migrations.read_version(con)
        finally:
            con.close()
        self.assertEqual(v, 3)
        self.assertEqual((topics[33], topics[51]), ("proyecto", "proyecto-51"))
        new = self.read_bytes(self.compas).decode("utf-8")
        self.assertIn("- **Temas:** seguridad, proyecto-51 , deuda\r\n", new)
        self.assertIn("Una línea de prosa que dice proyecto no se toca.\r\n", new)
        self.assertEqual(new.replace("proyecto-51 ", "proyecto "), original.decode("utf-8"))
        self.assertEqual([self.read_bytes(p) for p in self.compas_backups()], [original])
        weights = pendings.parse_compas(self.home)["topic_weight"]
        self.assertEqual(weights.get("proyecto-51"), 80, "el peso vuelve a caer sobre el tema movido")
        self.assertNotIn("proyecto", weights)
        self.assertFalse(_step().detectar(self.ctx()), "la segunda corrida no lo marca")

    def test_sin_tema_movido_no_se_marca(self):
        with contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(self.db, SCHEMA).close()
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO topic (id, slug, name) VALUES (10, 'proyecto', 'Proyecto')")
        con.execute("INSERT INTO topic (id, slug, name) VALUES (11, 'proyecto-9', 'De otro id')")
        con.commit()
        con.close()
        self.write_compas(COMPAS)
        self.assertFalse(_step().detectar(self.ctx()))

    def test_sin_compas_o_sin_la_cita_no_se_marca(self):
        self.v2_db_con_choque()
        self.migrar_base()
        self.assertFalse(_step().detectar(self.ctx()), "sin compas.md")
        self.write_compas(COMPAS.replace("proyecto , ", ""))
        self.assertFalse(_step().detectar(self.ctx()), "sin la cita")
        self.write_compas(COMPAS)
        self.assertTrue(_step().detectar(self.ctx()))

    def test_solo_lectura_se_reescribe_y_conserva_la_proteccion(self):
        self.v2_db_con_choque()
        self.migrar_base()
        self.write_compas(COMPAS)
        os.chmod(self.compas, stat.S_IREAD)
        r = _guided.run(self.ctx(), _step())
        self.assertNotIn(r.get("estado"), ("fallo", "pendiente", "manual"), r)
        self.assertIn("proyecto-51", self.read_bytes(self.compas).decode("utf-8"))
        self.assertFalse(os.access(self.compas, os.W_OK))
        self.assertEqual([f for f in os.listdir(self.data) if ".tmp-" in f], [])

    def test_falla_sembrada_al_reemplazar_deja_el_original(self):
        self.v2_db_con_choque()
        self.migrar_base()
        self.write_compas(COMPAS)
        os.chmod(self.compas, stat.S_IREAD)
        original = self.read_bytes(self.compas)
        with mock.patch("os.replace", side_effect=PermissionError(13, "valor-que-no-sale")):
            r = _guided.run(self.ctx(), _step())
        self.assertEqual(r["estado"], "fallo", r)
        self.assertNotIn("valor-que-no-sale", r["detalle"])
        self.assertEqual(self.read_bytes(self.compas), original)
        self.assertFalse(os.access(self.compas, os.W_OK))
        self.assertEqual(self.compas_backups(), [])
        self.assertEqual([f for f in os.listdir(self.data) if ".tmp-" in f], [])
        self.assertTrue(_step().detectar(self.ctx()), "sigue pendiente")


if __name__ == "__main__":
    unittest.main()
