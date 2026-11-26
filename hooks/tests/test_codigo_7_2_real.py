#!/usr/bin/env python3
"""
test_codigo_7_2_real.py — el código REAL de neb 7.2.0 (commit 9e31583) sobre una base que este código llevó a la
versión 3 (eje proyecto), sin simularlo con los pasos de este árbol.

Extrae `hooks/` de 9e31583 con `git archive` a una carpeta temporal y corre ahí, como procesos aparte y con un
home temporal, la captura (`hooks/lib/logbook.py`), `pendings.py triage` y `pendings.py curate --cliente`:
  • ninguno responde base-incompatible: la mínima compatible del paso 3 es 2 (desde 7.4.0);
  • la captura escribe; el triage responde y solo escribe sugerencias curated=0; curate --cliente es error
    legible y no escribe; ninguno crea una raíz 'cliente' ni archiva la raíz 'proyecto';
  • un triage posterior de este código borra las sugerencias de 7.2.0 sobre raíces de eje y no toca lo curado.
También con la fila del paso 3 como la dejó 7.3.0 (min_code 3): tras la reparación del arranque, 7.2.0 opera.
Desde 8.0.0 los dos códigos comparten la base solo con NEB_DATA = ~/.claude (la carpeta de datos es la de 7.x; sin
ella, 8.0.0 muda la base y deja la testigo): así corre aquí este código.

La base testigo (8.0.0, _relocate.write_witness) con el código REAL de 6.48.0 (95c48b3), 7.2.0 (9e31583) y 7.6.0
(fd91e4d), extraído igual: la captura, `logbook.py list`, `pendings.py list` y `triage`, y, si el árbol los trae,
`neb-migrate.py status`, `apply`, `apply --guiados` y `al-iniciar`. Ninguno crea tablas, escribe filas ni cambia
schema_step: la testigo sigue siéndolo, con el mismo tamaño y sin -wal/-shm tras la sonda de escritura de
is_witness; list y triage responden base-incompatible; la captura no escribe; en ~/.claude no aparece nada más que
el candado de 7.5–7.6; la base de la carpeta de datos no se toca.

Se salta (por commit) si no hay git o el clon no trae el commit.
  py -m unittest hooks.tests.test_codigo_7_2_real
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(NEB, "hooks", "lib"))

import _entorno     # noqa: E402 — quita NEB_DATA del entorno heredado
import _db_shared   # noqa: E402
import _migrations  # noqa: E402
import _relocate    # noqa: E402

COMMIT_7_2 = "9e31583"
COMMITS_TESTIGO = (("6.48.0", "95c48b3"), ("7.2.0", COMMIT_7_2), ("7.6.0", "fd91e4d"))
SCHEMA = os.path.join(NEB, "hooks", "logbook-schema.sql")
CLEAN = ("NEB_HOME", "NEB_HOOKS", "NEB_LOGBOOK_DB", "CLAUDE_CONFIG_DIR", "NEB_WORKSPACE", _entorno.DATA_ENV)
TREE_PATHS = ("hooks", "bootstrap", "migrations", "commands", "VERSION", ".claude-plugin")


def _extract(commit, dest, paths=("hooks",)):
    """Las rutas de `paths` que el commit trae, en dest; False si no hay git, el commit o hooks/lib/pendings.py."""
    try:
        present = [p for p in paths if subprocess.run(["git", "-C", NEB, "cat-file", "-e", f"{commit}:{p}"],
                                                      capture_output=True, timeout=60).returncode == 0]
        if not present:
            return False
        r = subprocess.run(["git", "-C", NEB, "archive", "--format=zip", commit] + present,
                           capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    if r.returncode != 0 or not r.stdout:
        return False
    with zipfile.ZipFile(io.BytesIO(r.stdout)) as z:
        z.extractall(dest)
    return os.path.isfile(os.path.join(dest, "hooks", "lib", "pendings.py"))


def _extract_7_2(dest):
    """hooks/ de 9e31583 en dest; False si no hay git o el commit."""
    return _extract(COMMIT_7_2, dest)


_TREE = None


def setUpModule():
    global _TREE
    d = tempfile.mkdtemp(prefix="neb-test-arbol-72-")
    if not _extract_7_2(d):
        shutil.rmtree(d, True)
        raise unittest.SkipTest(f"sin git o sin el commit {COMMIT_7_2}")
    _TREE = d


def tearDownModule():
    if _TREE:
        shutil.rmtree(_TREE, True)


class TestCodigo72RealSobreLaBaseMigrada(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-test-72real-")
        self.addCleanup(shutil.rmtree, self.home, True)
        os.makedirs(os.path.join(self.home, ".claude"))
        self.db = os.path.join(self.home, ".claude", "neb.db")
        self.env = {k: v for k, v in os.environ.items() if k not in CLEAN}
        self.env.update(HOME=self.home, USERPROFILE=self.home, PYTHONIOENCODING="utf-8")
        # Este código, con la carpeta de datos en ~/.claude: la misma base que lee 7.2.0 (8.0.0 no muda nada así).
        self.env_este = dict(self.env, **{_entorno.DATA_ENV: os.path.join(self.home, ".claude")})
        # Base como la deja 7.2.x (versión 2) con el eje curado, migrada después por este código (versión 3).
        with contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(self.db, SCHEMA, steps=_migrations.STEPS[:2]).close()
        con = sqlite3.connect(self.db)
        con.executescript("""
            INSERT INTO topic (id, slug, name, keywords) VALUES (33, 'cliente', 'Cliente', 'cliente proyecto');
            INSERT INTO topic (id, slug, name, keywords, parent_id) VALUES (40, 'alpha', 'Alpha', 'alpha', 33);
            INSERT INTO topic (id, slug, name, keywords) VALUES (34, 'topico', 'Tópico', 'topico');
            INSERT INTO topic (id, slug, name, keywords, parent_id)
                VALUES (50, 'seguridad', 'Seguridad', 'seguridad', 34);
            INSERT INTO pending (id, type, context_origin, status, created_at)
                VALUES (1, 'task', '[alpha] seguridad de alpha', 'open', '2026-11-01T00:00:00Z');
            INSERT INTO pending_topic (pending_id, topic_id, priority_band, is_primary, curated)
                VALUES (1, 40, 'high', 0, 1), (1, 50, 'high', 1, 1);
            INSERT INTO pending (id, type, context_origin, status, created_at)
                VALUES (2, 'task', 'el cliente y el proyecto piden seguridad en alpha', 'open',
                        '2026-11-02T00:00:00Z');
        """)
        con.commit()
        con.close()
        with contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(self.db, SCHEMA).close()            # este código: paso 3
        self.assertEqual(self.read(lambda c: _migrations.read_version(c)), (3, 2))

    def read(self, fn):
        con = sqlite3.connect(self.db)
        try:
            return fn(con)
        finally:
            con.close()

    def roots(self):
        return self.read(lambda c: sorted(c.execute(
            "SELECT slug, status FROM topic WHERE parent_id IS NULL AND slug IN ('cliente','proyecto','topico')")))

    def curated(self):
        return self.read(lambda c: sorted(c.execute(
            "SELECT pending_id, topic_id, priority_band, is_primary FROM pending_topic WHERE curated = 1")))

    def root_suggestions(self):
        return self.read(lambda c: sorted(c.execute(
            "SELECT pt.pending_id, t.slug FROM pending_topic pt JOIN topic t ON t.id = pt.topic_id "
            "WHERE pt.curated = 0 AND t.parent_id IS NULL AND t.slug IN ('cliente','proyecto','topico')")))

    def run72(self, *args):
        r = subprocess.run([sys.executable, *args], env=self.env, capture_output=True, timeout=120,
                           cwd=self.home)
        out = r.stdout.decode("utf-8", errors="replace")
        self.assertNotIn("base-incompatible", out)
        self.assertNotIn("paso-bloqueado", out)
        return r.returncode, out

    def pendings72(self, *args):
        return self.run72(os.path.join(_TREE, "hooks", "lib", "pendings.py"), *args)

    def test_critico_captura_triage_y_curate_reales_de_7_2(self):
        roots, curated = self.roots(), self.curated()
        # captura
        cwd = os.path.join(self.home, "repo")
        os.makedirs(cwd)
        t = os.path.join(self.home, "S72.jsonl")
        with open(t, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "message": {"content": "tema de 7.2"}}) + "\n")
        rc, _out = self.run72(os.path.join(_TREE, "hooks", "lib", "logbook.py"),
                              "S72", cwd, t, "Stop", _TREE, self.home)
        self.assertEqual(rc, 0)
        self.assertIsNotNone(self.read(lambda c: c.execute(
            "SELECT 1 FROM work WHERE claude_session_id = 'S72'").fetchone()), "la captura de 7.2.0 escribe")
        # triage
        rc, out = self.pendings72("triage")
        self.assertEqual(rc, 0, out)
        self.assertIsInstance(json.loads(out), dict)
        self.assertEqual(self.roots(), roots, "no crea 'cliente' ni archiva 'proyecto'")
        self.assertEqual(self.curated(), curated, "no toca lo curado")
        self.assertIn((2, "proyecto"), self.root_suggestions(), "7.2.0 sugiere la raíz 'proyecto' (no la excluye)")
        # curate --cliente: error legible, sin escribir
        before = self.read(lambda c: sorted(c.execute("SELECT * FROM pending_topic")))
        rc, out = self.pendings72("curate", "2", "--cliente", "alpha", "--topico", "seguridad")
        res = json.loads(out)
        self.assertFalse(res.get("ok"), res)
        self.assertIn("cliente", res.get("error", ""))
        self.assertEqual(self.read(lambda c: sorted(c.execute("SELECT * FROM pending_topic"))), before)
        self.assertEqual(self.read(lambda c: _migrations.read_version(c)), (3, 2))
        # un triage de este código borra las sugerencias de 7.2.0 sobre raíces y no toca lo curado
        r = subprocess.run([sys.executable, os.path.join(NEB, "hooks", "lib", "pendings.py"), "triage"],
                           env=self.env_este, capture_output=True, timeout=120, cwd=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.root_suggestions(), [])
        self.assertEqual(self.curated(), curated)
        self.assertEqual(self.roots(), roots)

    def test_critico_con_la_fila_de_7_3_0_opera_tras_la_reparacion_del_arranque(self):
        """7.2.0 lee MAX(min_code) tal cual: con la fila que dejó 7.3.0 (min_code 3) responde base-incompatible;
        el arranque de este código la baja y 7.2.0 vuelve a operar."""
        con = sqlite3.connect(self.db)
        con.execute("UPDATE schema_step SET min_code = 3 WHERE step = 3")
        con.commit()
        con.close()
        r = subprocess.run([sys.executable, os.path.join(_TREE, "hooks", "lib", "pendings.py"), "triage"],
                           env=self.env, capture_output=True, timeout=120, cwd=self.home)
        self.assertIn("base-incompatible", r.stdout.decode("utf-8", errors="replace"))
        spec = importlib.util.spec_from_file_location(
            "neb_bootstrap_context_72real", os.path.join(NEB, "bootstrap", "neb-bootstrap-context.py"))
        nb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nb)
        with mock.patch.dict(os.environ, {_entorno.DATA_ENV: os.path.join(self.home, ".claude")}):
            self.assertTrue(nb._relax_axis_step(os.path.join(NEB, "bootstrap"), home=self.home))
        rc, out = self.pendings72("triage")
        self.assertEqual(rc, 0, out)


class TestCodigoViejoSobreLaTestigo(unittest.TestCase):
    """La base testigo que 8.0.0:mover-base deja en ~/.claude/neb.db, con el código real de las versiones cuyas
    sesiones pueden seguir abiertas (el plugin viejo o el clon de NEB_HOME): ninguno la usa ni la convierte en una
    base vacía divergente."""

    trees = {}

    @classmethod
    def setUpClass(cls):
        for version, commit in COMMITS_TESTIGO:
            d = tempfile.mkdtemp(prefix="neb-test-arbol-%s-" % version)
            if _extract(commit, d, TREE_PATHS):
                cls.trees[version] = d
            else:
                shutil.rmtree(d, True)

    @classmethod
    def tearDownClass(cls):
        for d in cls.trees.values():
            shutil.rmtree(d, True)

    def _home(self):
        home = _entorno.home_temporal(self, claude=True, neb=True)
        witness = _db_shared.legacy_db_path(home)
        _relocate.write_witness(witness, "8.0.0")
        db = _db_shared.resolve_db_path(home)                  # la base mudada, con datos
        with mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}), \
                contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(db, SCHEMA).close()
        con = sqlite3.connect(db)
        con.execute("INSERT INTO pending (context_origin, created_at) VALUES ('dato de la base mudada', 'a')")
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
        return home, witness, db

    @staticmethod
    def _witness_state(path):
        con = sqlite3.connect(path)
        try:
            tables = sorted(r[0] for r in con.execute("SELECT name FROM sqlite_master"))
            rows = list(con.execute("SELECT step, min_code, title FROM schema_step"))
        finally:
            con.close()
        return tables, rows

    @staticmethod
    def _sha(path):
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    def _commands(self, tree, home):
        cwd = os.path.join(home, "repo")
        os.makedirs(cwd, exist_ok=True)
        t = os.path.join(home, "S.jsonl")
        with open(t, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "message": {"content": "tema de una sesión vieja"}}) + "\n")
        lib = os.path.join(tree, "hooks", "lib")
        cmds = [("captura", [os.path.join(lib, "logbook.py"), "S1", cwd, t, "Stop", tree, home]),
                ("logbook list", [os.path.join(lib, "logbook.py"), "list"]),
                ("pendings list", [os.path.join(lib, "pendings.py"), "list"]),
                ("pendings triage", [os.path.join(lib, "pendings.py"), "triage"])]
        nm = os.path.join(tree, "bootstrap", "neb-migrate.py")
        if os.path.isfile(nm):
            cmds += [("status", [nm, "status", "--json"]), ("apply", [nm, "apply"]),
                     ("apply --guiados", [nm, "apply", "--guiados"]), ("al-iniciar", [nm, "al-iniciar"])]
        return cwd, cmds

    def test_critico_el_codigo_viejo_no_crea_tablas_ni_escribe_en_la_testigo(self):
        if not self.trees:
            self.skipTest("sin git o sin los commits de 6.48.0, 7.2.0 y 7.6.0")
        for version, tree in sorted(self.trees.items()):
            with self.subTest(version=version):
                home, witness, db = self._home()
                size = os.path.getsize(witness)
                row = (_relocate.WITNESS_STEP, _relocate.WITNESS_STEP, _relocate.WITNESS_TITLE)
                expected = (["schema_step"], [row])
                db_sha = self._sha(db)
                env = {k: v for k, v in os.environ.items() if k not in CLEAN}
                env.update(HOME=home, USERPROFILE=home, PYTHONIOENCODING="utf-8")
                cwd, cmds = self._commands(tree, home)
                for name, cmd in cmds:
                    r = subprocess.run([sys.executable] + cmd, env=env, capture_output=True, timeout=120, cwd=cwd)
                    out = r.stdout.decode("utf-8", errors="replace")
                    err = r.stderr.decode("utf-8", errors="replace")
                    self.assertNotIn("Traceback", err, (version, name))
                    if name in ("logbook list", "pendings list", "pendings triage"):
                        self.assertIn("base-incompatible", out, (version, name))
                    self.assertTrue(_relocate.is_witness(witness), (version, name, "dejó de ser la testigo"))
                    self.assertEqual(self._witness_state(witness), expected, (version, name))
                    self.assertEqual(os.path.getsize(witness), size, (version, name, "la testigo creció"))
                    extra = sorted(set(os.listdir(os.path.dirname(witness))) - {"neb.db", ".neb-migrate.lock"})
                    self.assertEqual(extra, [], (version, name, "residuos en ~/.claude tras la sonda de escritura"))
                    self.assertEqual(self._sha(db), db_sha, (version, name, "tocó la base de la carpeta de datos"))


if __name__ == "__main__":
    unittest.main()
