#!/usr/bin/env python3
"""
test_respaldos_a_medias.py — copias de respaldo cortadas a medias (7.5.0).

Desde 7.5.0 la entrada de migración de SessionStart (`neb-migrate.py al-iniciar`) corre pasos al iniciar la sesión,
y la plataforma la mata si pasa su timeout (supuesto R31): una copia que se estaba escribiendo queda a medias, a
veces con su -journal. Cubre:
  • prune_backups (_migrations.py) borra también el -journal de las copias que poda;
  • _borrar_copias_anteriores (migrations/7.3.0.py, vacuum-neb-db) borra también el -journal de las que poda;
  • `restore` sobre una copia ilegible responde respaldo-ilegible con su motivo, sin lanzar;
  • la poda de neb.pre-restore.* dentro de `restore` borra también su -journal;
  • un VACUUM matado a media corrida: una conexión de solo lectura falla mientras quede el diario caliente, y
    la siguiente conexión de escritura lo revierte con la base íntegra; con la base real del home, la siguiente
    `al-iniciar` la deja legible e íntegra;
  • `restore` sobre una copia cortada de verdad (VACUUM matado sobre la copia, con su -journal) responde sin
    lanzar: restaura una copia íntegra o responde respaldo-ilegible.

Homes temporales; nunca ~/.claude.
  py -m unittest discover -s hooks/tests -p test_respaldos_a_medias.py
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sin_registro  # noqa: E402,F401 — sin el registro real de Windows
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(NEB, "hooks", "lib"))

import _db_shared   # noqa: E402
import _machine     # noqa: E402
import _migrations  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nm = _load("neb_migrate_respaldos_test", os.path.join(NEB, "bootstrap", "neb-migrate.py"))


class Base(unittest.TestCase):

    def setUp(self):
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        # al-iniciar corre las migraciones reales del árbol: nada del entorno del dev (config, proyecto, subsesión).
        for k in ("CLAUDE_CONFIG_DIR", "CLAUDE_PROJECT_DIR", "NEB_HOME", "NEB_INTERNAL_SUBSESSION",
                  "CLAUDE_PREPROCESS_RECURSION"):
            os.environ.pop(k, None)
        self.home = tempfile.mkdtemp(prefix="neb-test-medias-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.claude = os.path.join(self.home, ".claude")
        os.makedirs(self.claude)
        self.db = os.path.join(self.claude, "neb.db")
        with contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(self.db).close()
        self.backups = os.path.join(self.claude, "neb-backups")
        os.makedirs(self.backups, exist_ok=True)

    def write(self, name, data=b"x"):
        path = os.path.join(self.backups, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path


class TestPodas(Base):

    def test_prune_backups_borra_el_journal(self):
        viejo = self.write("neb.pre-paso-2.20260101T000000Z.db")
        self.write("neb.pre-paso-2.20260101T000000Z.db-journal")
        nuevo = self.write("neb.pre-paso-2.20260202T000000Z.db")
        _migrations.prune_backups(self.db, "neb.pre-paso-2.*.db", nuevo)
        self.assertEqual(sorted(os.listdir(self.backups)), [os.path.basename(nuevo)])
        self.assertFalse(os.path.exists(viejo))

    def test_vacuum_poda_el_journal_de_la_copia_anterior(self):
        mig = _load("neb_migration_7_3_0_medias", os.path.join(NEB, "migrations", "7.3.0.py"))
        self.write("neb.pre-vacuum.20260101T000000Z.db")
        self.write("neb.pre-vacuum.20260101T000000Z.db-journal")
        otro = self.write("neb.pre-paso-2.20260101T000000Z.db-journal")       # de otro paso: no se toca
        keep = self.write("neb.pre-vacuum.20260202T000000Z.db")
        borradas, fallidas = mig._borrar_copias_anteriores(_machine.Ctx(self.home, db_path=self.db), keep)
        self.assertEqual((borradas, fallidas), (1, 0))
        self.assertEqual(sorted(os.listdir(self.backups)), sorted([os.path.basename(keep), os.path.basename(otro)]))


class TestRestore(Base):

    def test_la_poda_de_restore_borra_el_journal(self):
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE IF NOT EXISTS _x (a)")
        con.commit()
        con.close()
        good = os.path.join(self.backups, "neb.pre-paso-2.20260101T000000Z.db")
        src = sqlite3.connect(self.db)
        dst = sqlite3.connect(good)
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")
        dst.close()
        src.close()
        viejo = self.write("neb.pre-restore.20250101T000000Z.db")
        self.write("neb.pre-restore.20250101T000000Z.db-journal")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.restore(self.home, good)
        self.assertEqual(rc, 0, out.getvalue())
        self.assertFalse(os.path.exists(viejo))
        self.assertFalse(os.path.exists(viejo + "-journal"))

    def test_restore_de_una_copia_ilegible_responde_sin_lanzar(self):
        bad = self.write("neb.pre-paso-2.20260101T000000Z.db", b"SQLite format 3\x00" + b"\x01" * 300)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.restore(self.home, bad)
        res = json.loads(out.getvalue())
        self.assertEqual((rc, res["ok"], res["motivo"]), (1, False, "respaldo-ilegible"))


VAC = textwrap.dedent('''
    import sqlite3, sys
    con = sqlite3.connect(sys.argv[1], isolation_level=None)
    con.execute("PRAGMA journal_mode=DELETE")
    print("empieza", flush=True)
    con.execute("VACUUM")
    print("terminó", flush=True)
''')


class TestVacuumMatado(Base):
    """Lo que el diseño de al-iniciar da por hecho (plan del REQ, § 2): el diario caliente de un VACUUM matado hace
    fallar a una conexión de solo lectura hasta que una de escritura lo revierte, y la base queda íntegra."""

    def make_big(self, path):
        con = sqlite3.connect(path)
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, x TEXT)")
        con.executemany("INSERT INTO t (x) VALUES (?)", ((os.urandom(200).hex(),) for _ in range(250000)))
        con.commit()
        con.execute("DELETE FROM t WHERE id % 2 = 0")
        con.commit()
        con.close()

    def kill_vacuum(self, path, rebuild):
        """Mata un VACUUM sobre `path` hasta dejar un -journal no vacío; rebuild() rehace la base si el VACUUM
        terminó antes del kill. Omite la prueba si nunca lo logra en esta máquina."""
        script = os.path.join(self.home, "vac.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(VAC)
        for delay in (0.15, 0.3, 0.45, 0.6):                         # el momento exacto depende de la máquina
            if os.path.exists(path + "-journal"):
                os.remove(path + "-journal")
            p = subprocess.Popen([sys.executable, script, path], stdout=subprocess.PIPE, text=True)
            p.stdout.readline()
            time.sleep(delay)
            p.kill()
            p.wait(30)
            p.stdout.close()
            if os.path.exists(path + "-journal") and os.path.getsize(path + "-journal") > 0:
                return delay
            rebuild()                     # terminó antes del kill: la base ya quedó compactada
        self.skipTest("el VACUUM terminó antes de cada kill en esta máquina")

    def test_diario_caliente_tras_matar_un_vacuum(self):
        path = os.path.join(self.home, "grande.db")
        self.make_big(path)

        def rebuild():
            os.remove(path)
            self.make_big(path)
        self.kill_vacuum(path, rebuild)
        # Solo lectura: falla mientras el diario esté caliente ("attempt to write a readonly database"), o, si el
        # kill llegó antes de que el diario tuviera cabecera válida, lee la base sin cambios. Nunca datos a medias.
        ro = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)
        try:
            self.assertEqual(ro.execute("SELECT count(*) FROM t").fetchone()[0], 125000)
        except sqlite3.OperationalError as e:
            self.assertIn("readonly", str(e))
        finally:
            ro.close()
        rw = sqlite3.connect(path, isolation_level=None)
        try:
            self.assertEqual(rw.execute("SELECT count(*) FROM t").fetchone()[0], 125000)
            self.assertEqual(rw.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            # Un diario sin cabecera válida (no caliente) se queda hasta la siguiente escritura real de páginas, que
            # lo reemplaza y lo borra al confirmar.
            rw.execute("CREATE TABLE _sonda (a)")
            rw.execute("DROP TABLE _sonda")
        finally:
            rw.close()
        self.assertFalse(os.path.exists(path + "-journal"))

    def fill_home_db(self):
        con = sqlite3.connect(self.db)
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("DROP TABLE IF EXISTS _relleno")
        con.execute("CREATE TABLE _relleno (id INTEGER PRIMARY KEY, x TEXT)")
        con.executemany("INSERT INTO _relleno (x) VALUES (?)", ((os.urandom(200).hex(),) for _ in range(250000)))
        con.commit()
        con.execute("DELETE FROM _relleno WHERE id % 2 = 0")
        con.commit()
        con.close()

    def test_al_iniciar_tras_un_vacuum_matado_en_la_base_del_home(self):
        # Flujo 5(d) con la base del home y al-iniciar del árbol real (no un sqlite3.connect suelto).
        self.fill_home_db()
        self.kill_vacuum(self.db, self.fill_home_db)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.al_iniciar(self.home)
        self.assertEqual(rc, 0)
        # Corrió de verdad (no salió por subsesión ni por `neb: skip`): llegó a tomar el candado, junto a la base.
        self.assertTrue(os.path.exists(os.path.join(self.claude, ".neb-migrate.lock")))
        # Un diario caliente ya no está (lo revirtió su conexión de escritura); uno sin cabecera válida puede quedar
        # hasta la siguiente escritura de páginas (Change MD, Incidencias), pero no estorba: mode=ro lee abajo.
        ro = sqlite3.connect(Path(self.db).as_uri() + "?mode=ro", uri=True)
        try:
            self.assertEqual(ro.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(ro.execute("SELECT count(*) FROM _relleno").fetchone()[0], 125000)
        finally:
            ro.close()

    def test_restore_de_una_copia_cortada_de_verdad_no_lanza(self):
        # Flujo 5(e): una copia en neb-backups/ con el -journal de un VACUUM matado sobre ella.
        copia = os.path.join(self.backups, "neb.pre-paso-2.20260101T000000Z.db")

        def rebuild():
            if os.path.exists(copia):
                os.remove(copia)
            src = sqlite3.connect(self.db)
            dst = sqlite3.connect(copia)
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")
            dst.close()
            src.close()
        self.fill_home_db()
        rebuild()
        self.kill_vacuum(copia, rebuild)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.restore(self.home, copia)
        res = json.loads(out.getvalue())
        if res["ok"]:
            self.assertEqual(rc, 0)
            con = sqlite3.connect(self.db)
            try:
                self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(con.execute("SELECT count(*) FROM _relleno").fetchone()[0], 125000)
            finally:
                con.close()
        else:
            self.assertEqual((rc, res["motivo"]), (1, "respaldo-ilegible"))


if __name__ == "__main__":
    unittest.main()
