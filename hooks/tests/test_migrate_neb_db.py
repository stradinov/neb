#!/usr/bin/env python3
"""
test_migrate_neb_db.py — bootstrap/migrate-neb-db.py, el cambio de nombre de la base (neb-logbook.db ->
neb.db, neb 7.0.0) que corre el paso guiado 7.0.0:renombrar-base o el dev a mano.

Cubre, contra directorios HOME temporales (nunca toca ~/.claude):
  • camino feliz: cambia el nombre, respaldo con la API de backup, sin sidecars, sin migrar columnas
  • rename(): no imprime; devuelve código, mensaje y respaldo (nombre con microsegundos, un solo archivo
    en journal_mode=DELETE, íntegro); otra conexión abierta impide salir de WAL y no cambia el nombre;
    nadie confirma escrituras mientras saca el respaldo; un os.replace fallido no cambia el nombre; la
    base vieja que reaparece tras el cambio, vacía o con escrituras
  • destino de 0 bytes: se acepta
  • destino no vacío (sin tabla work, que no es una base, o usable): aborta y lo conserva byte a byte; la
    guarda de _db_shared responde la instrucción de moverlo fuera
  • sidecars del destino ya presentes, o de la base vieja o del destino que aparecen tras el checkpoint:
    abortan antes del cambio de nombre
  • --dry-run: no abre ninguna base; deja igual el hash de cada archivo y la lista de la carpeta
  • base vieja bloqueada, checkpoint ocupado, destino no usable tras el cambio de nombre, ya migrado y
    base vieja vacía
  • base vieja no vacía pero inservible (no es SQLite o sin tabla work): aborta sin tocar nada y pide
    moverla fuera
  • destino bloqueado en la verificación: queda en su lugar con un aviso (no se devuelve)
  • neb.db queda en WAL tras migrar, y varios procesos abren a la vez con open_default_db (aplican los
    pasos de base, el 2 incluido)
  • comando de la guarda: intérprete que corre y --home solo cuando el home no es el de ~

Carga migrate-neb-db.py con importlib (el nombre lleva guiones).

Framework: unittest (stdlib), no pytest.
"""

import hashlib
import importlib.util
import io
import os
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared  # noqa: E402

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
_MIGRATE_PATH = os.path.join(HERE, "..", "..", "bootstrap", "migrate-neb-db.py")


def _load_migrate():
    spec = importlib.util.spec_from_file_location("migrate_neb_db", _MIGRATE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load_migrate()


def _seed_legacy(home, rows=1):
    """<home>/.claude/neb-logbook.db con el esquema inicial (el de 6.45.0, en WAL) y `rows` works."""
    os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
    legacy = os.path.join(home, ".claude", _db_shared.LEGACY_DB_NAME)
    con = sqlite3.connect(legacy)
    with open(SCHEMA, encoding="utf-8") as fh:
        con.executescript(fh.read())
    for _ in range(rows):
        con.execute("INSERT INTO work (mode, owner, lock_state, created_at, updated_at) "
                    "VALUES ('exploratory','dev','owned','t','t')")
    con.commit()
    con.close()
    return legacy


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _snapshot(folder):
    return {name: _sha(os.path.join(folder, name)) for name in sorted(os.listdir(folder))}


def _work_count(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT count(*) FROM work").fetchone()[0]
    finally:
        con.close()


class _ConnWrapper:
    """Delega en la conexión real; `on_close` corre después de cerrarla, `busy_checkpoint` finge un
    wal_checkpoint(TRUNCATE) ocupado y `stays_wal` un journal_mode=DELETE que responde `wal` sin error."""

    def __init__(self, real, on_close=None, busy_checkpoint=False, stays_wal=False):
        self._real = real
        self._on_close = on_close
        self._busy = busy_checkpoint
        self._stays_wal = stays_wal

    def execute(self, sql, *a, **k):
        if self._busy and "wal_checkpoint" in sql.lower():
            return _Row((1, -1, -1))
        if self._stays_wal and sql.lower().replace(" ", "") == "pragmajournal_mode=delete":
            return _Row(("wal",))
        return self._real.execute(sql, *a, **k)

    def close(self):
        self._real.close()
        if self._on_close is not None:
            self._on_close()
            self._on_close = None

    def __getattr__(self, name):
        return getattr(self._real, name)


class _Row:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-migrate-")
        self.addCleanup(shutil.rmtree, self.home, True)
        out = mock.patch("sys.stdout", new_callable=io.StringIO)
        out.start()
        self.addCleanup(out.stop)
        self.base = os.path.join(self.home, ".claude")
        self.legacy = os.path.join(self.base, _db_shared.LEGACY_DB_NAME)
        self.target = os.path.join(self.base, _db_shared.NEB_DB_NAME)

    def _patch_legacy_connect(self, **wrapper_kw):
        real_connect = sqlite3.connect
        legacy = self.legacy

        def fake_connect(path, *a, **k):
            con = real_connect(path, *a, **k)
            if os.path.abspath(path) == os.path.abspath(legacy):
                return _ConnWrapper(con, **wrapper_kw)
            return con
        return mock.patch.object(M.sqlite3, "connect", fake_connect)

    def _backups(self):
        return [f for f in os.listdir(self.base) if ".bak-" in f]


class TestMigrar(_Base):

    def test_camino_feliz(self):
        _seed_legacy(self.home, rows=3)
        self.assertEqual(M.migrate(self.home), 0)
        self.assertFalse(os.path.exists(self.legacy))
        self.assertTrue(_db_shared._is_usable_db(self.target))
        self.assertEqual(_work_count(self.target), 3)
        con = sqlite3.connect(self.target)
        try:
            self.assertEqual(con.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            cols = {r[1] for r in con.execute("PRAGMA table_info(work)")}
        finally:
            con.close()
        self.assertIn("owner", cols, "el migrador no migra columnas: eso lo hace la primera conexión de 7.0.0")
        baks = self._backups()
        self.assertEqual(len(baks), 1)
        self.assertEqual(_work_count(os.path.join(self.base, baks[0])), 3)
        self.assertEqual(M._sidecars(self.legacy, self.target), [])

    def test_destino_de_0_bytes_se_acepta(self):
        _seed_legacy(self.home)
        open(self.target, "wb").close()
        self.assertEqual(M.migrate(self.home), 0)
        self.assertFalse(os.path.exists(self.legacy))
        self.assertEqual(_work_count(self.target), 1)

    def test_ya_migrado_no_toca_nada(self):
        _seed_legacy(self.home)
        os.replace(self.legacy, self.target)
        before = _snapshot(self.base)
        self.assertEqual(M.migrate(self.home), 0)
        self.assertEqual(_snapshot(self.base), before)

    def test_base_vieja_vacia_no_toca_nada(self):
        os.makedirs(self.base)
        open(self.legacy, "wb").close()
        before = _snapshot(self.base)
        self.assertEqual(M.migrate(self.home), 0)
        self.assertEqual(_snapshot(self.base), before)


class TestDestinoNoVacio(_Base):

    def _destino_sin_work(self):
        con = sqlite3.connect(self.target)
        con.execute("CREATE TABLE otra (x)")
        con.execute("INSERT INTO otra VALUES (1)")
        con.commit()
        con.close()

    def _destino_no_base(self):
        with open(self.target, "wb") as fh:
            fh.write(b"esto no es una base SQLite" * 10)

    def _destino_usable(self):
        con = sqlite3.connect(self.target)
        con.execute("CREATE TABLE work (id INTEGER PRIMARY KEY)")
        con.commit()
        con.close()

    def test_aborta_y_conserva_el_destino_byte_a_byte(self):
        for nombre, sembrar in (("sin-work", self._destino_sin_work), ("no-base", self._destino_no_base),
                                ("usable", self._destino_usable)):
            with self.subTest(nombre):
                shutil.rmtree(self.base, True)
                _seed_legacy(self.home)
                sembrar()
                before = _snapshot(self.base)
                size = os.path.getsize(self.target)
                with mock.patch("sys.stderr") as err:
                    self.assertEqual(M.migrate(self.home), 1)
                salida = "".join(c.args[0] for c in err.write.call_args_list)
                self.assertIn(f"({size} bytes)", salida)
                self.assertIn("mueve fuera", salida)
                self.assertEqual(_snapshot(self.base), before)

    def test_la_guarda_pide_moverlo_fuera(self):
        for sembrar in (self._destino_sin_work, self._destino_no_base):
            with self.subTest(sembrar.__name__):
                shutil.rmtree(self.base, True)
                _seed_legacy(self.home)
                sembrar()
                err = _db_shared.unmigrated_legacy(self.home)
                self.assertIsNotNone(err)
                self.assertIn(f"mueve fuera de {self.base}", err.detalle)
                self.assertIn(f"({os.path.getsize(self.target)} bytes)", err.detalle)
                self.assertIn("migrate-neb-db.py", err.comando)


class TestSidecars(_Base):

    def test_sidecar_previo_del_destino_aborta_sin_tocar_nada(self):
        for suf in M.SIDECARS:
            with self.subTest(suf):
                shutil.rmtree(self.base, True)
                _seed_legacy(self.home)
                open(self.target + suf, "wb").close()
                before = _snapshot(self.base)
                self.assertEqual(M.migrate(self.home), 1)
                self.assertEqual(_snapshot(self.base), before)

    def test_sidecar_que_aparece_tras_el_checkpoint_aborta_antes_del_cambio_de_nombre(self):
        for path_attr in ("legacy", "target"):
            for suf in M.SIDECARS:
                with self.subTest(f"{path_attr}{suf}"):
                    shutil.rmtree(self.base, True)
                    _seed_legacy(self.home)
                    sidecar = getattr(self, path_attr) + suf

                    def aparece(p=sidecar):
                        open(p, "wb").close()
                    with self._patch_legacy_connect(on_close=aparece):
                        self.assertEqual(M.migrate(self.home), 1)
                    self.assertTrue(os.path.isfile(self.legacy))
                    self.assertFalse(os.path.exists(self.target))
                    self.assertEqual(_work_count(self.legacy), 1)


class TestDryRun(_Base):

    def _sin_abrir(self):
        def prohibido(*a, **k):
            raise AssertionError("--dry-run no debe abrir ninguna base")
        return mock.patch.object(M.sqlite3, "connect", prohibido)

    def test_no_abre_ni_cambia_nada(self):
        _seed_legacy(self.home)
        open(self.target, "wb").close()
        open(self.legacy + "-wal", "wb").close()
        before = _snapshot(self.base)
        with self._sin_abrir():
            self.assertEqual(M.migrate(self.home, dry_run=True), 0)
        self.assertEqual(_snapshot(self.base), before)

    def test_con_destino_no_vacio_dice_que_abortaria(self):
        _seed_legacy(self.home)
        with open(self.target, "wb") as fh:
            fh.write(b"x" * 100)
        before = _snapshot(self.base)
        with self._sin_abrir():
            self.assertEqual(M.migrate(self.home, dry_run=True), 1)
        self.assertEqual(_snapshot(self.base), before)


class TestAbortos(_Base):

    def test_base_vieja_bloqueada(self):
        _seed_legacy(self.home)
        other = sqlite3.connect(self.legacy, isolation_level=None)
        other.execute("BEGIN IMMEDIATE")
        try:
            with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                self.assertEqual(M.migrate(self.home), 1)
        finally:
            other.execute("ROLLBACK")
            other.close()
        self.assertIn("otra sesión o proceso la usa", err.getvalue())
        self.assertIn("vuelve a correr", err.getvalue())
        self.assertNotIn("no es una base usable", err.getvalue())
        self.assertTrue(os.path.isfile(self.legacy))
        self.assertFalse(os.path.exists(self.target))
        self.assertEqual(self._backups(), [])

    def test_checkpoint_ocupado(self):
        _seed_legacy(self.home)
        with self._patch_legacy_connect(busy_checkpoint=True):
            self.assertEqual(M.migrate(self.home), 1)
        self.assertTrue(os.path.isfile(self.legacy))
        self.assertFalse(os.path.exists(self.target))

    def test_destino_no_usable_vuelve_a_su_nombre(self):
        for state in ("sin-work", "no-base", "vacia", "ausente"):
            with self.subTest(state):
                shutil.rmtree(self.base, True)
                _seed_legacy(self.home)
                with mock.patch.object(M, "_probe_db", return_value=state), mock.patch("sys.stderr"):
                    self.assertEqual(M.migrate(self.home), 1)
                self.assertTrue(os.path.isfile(self.legacy))
                self.assertFalse(os.path.exists(self.target))
                self.assertEqual(_work_count(self.legacy), 1)

    def test_destino_bloqueado_en_la_verificacion_queda_en_su_lugar(self):
        _seed_legacy(self.home)
        with mock.patch.object(M, "_probe_db", return_value="bloqueada"):
            self.assertEqual(M.migrate(self.home), 0)
        self.assertFalse(os.path.exists(self.legacy))
        self.assertTrue(os.path.isfile(self.target))
        self.assertIn("OK con aviso", sys.stdout.getvalue())
        self.assertEqual(_work_count(self.target), 1)


def _journal(path):
    c = sqlite3.connect(path)
    try:
        return c.execute("PRAGMA journal_mode").fetchone()[0].lower()
    finally:
        c.close()


class TestRename(_Base):
    """rename() es lo que llama el paso guiado: su resultado decide el estado del paso."""

    BAK_RE = re.compile(r"^neb-logbook\.db\.bak-\d{8}T\d{12}Z$")

    def _rename(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            r = M.rename(self.home)
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""), "rename() no imprime")
        self.assertEqual(sorted(r), ["aviso", "codigo", "escribio", "mensaje", "respaldo"])
        return r

    def test_critico_ok_con_respaldo_en_un_solo_archivo(self):
        _seed_legacy(self.home, rows=2)
        r = self._rename()
        self.assertEqual((r["codigo"], r["aviso"], r["escribio"]), ("ok", None, False))
        self.assertEqual(os.path.dirname(r["respaldo"]), self.base)
        self.assertRegex(os.path.basename(r["respaldo"]), self.BAK_RE)
        self.assertEqual(self._backups(), [os.path.basename(r["respaldo"])])
        self.assertEqual(M._sidecars(r["respaldo"]), [])
        with open(r["respaldo"], "rb") as fh:
            head = fh.read(20)
        self.assertEqual((head[18], head[19]), (1, 1), "respaldo en journal_mode=DELETE, no WAL")
        c = sqlite3.connect(r["respaldo"])
        try:
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(c.execute("SELECT count(*) FROM work").fetchone()[0], 2)
        finally:
            c.close()
        self.assertEqual(_journal(self.target), "wal")

    def test_nada_que_hacer(self):
        os.makedirs(self.base)
        self.assertEqual(self._rename()["codigo"], "nada")

    def test_critico_otra_conexion_abierta_impide_salir_de_wal(self):
        _seed_legacy(self.home)
        other = sqlite3.connect(self.legacy)
        try:
            other.execute("SELECT count(*) FROM work").fetchone()
            r = self._rename()
            self.assertEqual(other.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
        finally:
            other.close()
        self.assertEqual(r["codigo"], "ocupada")
        self.assertIn("Cierra las demás sesiones de Claude", r["mensaje"])
        self.assertIsNone(r["respaldo"])
        self.assertEqual(self._backups(), [])
        self.assertTrue(os.path.isfile(self.legacy))
        self.assertFalse(os.path.exists(self.target))
        self.assertEqual(_journal(self.legacy), "wal")

    def test_critico_journal_mode_que_no_queda_en_delete_no_sigue(self):
        _seed_legacy(self.home)
        respaldos = []
        with self._patch_legacy_connect(stays_wal=True), \
                mock.patch.object(M, "_backup", lambda con, dst: respaldos.append(dst)):
            r = self._rename()
        self.assertEqual(r["codigo"], "ocupada")
        self.assertIn("journal_mode quedó en", r["mensaje"])
        self.assertEqual(respaldos, [], "no saca el respaldo sin salir de WAL")
        self.assertTrue(os.path.isfile(self.legacy))
        self.assertFalse(os.path.exists(self.target))

    def test_critico_nadie_confirma_escrituras_durante_el_respaldo(self):
        _seed_legacy(self.home)
        real = M._backup
        intentos = []

        def espia(con, dst):
            w = sqlite3.connect(self.legacy, timeout=0)
            try:
                w.execute("INSERT INTO work (mode, created_at, updated_at) VALUES ('exploratory','t','t')")
                w.commit()
                intentos.append("confirmó")
            except sqlite3.OperationalError as e:
                intentos.append(str(e))
            finally:
                w.close()
            return real(con, dst)
        with mock.patch.object(M, "_backup", espia):
            r = self._rename()
        self.assertEqual(r["codigo"], "ok")
        self.assertEqual(intentos, ["database is locked"])
        self.assertEqual(_work_count(self.target), 1)
        self.assertEqual(_work_count(r["respaldo"]), 1)

    def test_fallo_de_os_replace_no_cambia_el_nombre(self):
        _seed_legacy(self.home)
        real = os.replace
        legacy = self.legacy

        def falla(src, dst):
            if os.path.abspath(src) == os.path.abspath(legacy):
                raise PermissionError(13, "El proceso no tiene acceso al archivo")
            return real(src, dst)
        with mock.patch.object(M.os, "replace", falla):
            r = self._rename()
        self.assertEqual(r["codigo"], "ocupada")
        self.assertIn("no se pudo cambiar el nombre", r["mensaje"])
        self.assertEqual(self._backups(), [])
        self.assertTrue(os.path.isfile(self.legacy))
        self.assertFalse(os.path.exists(self.target))
        self.assertEqual(_journal(self.legacy), "wal")

    def _reaparece(self, data):
        legacy = self.legacy
        real = M._probe_db

        def sonda(path):
            with open(legacy, "wb") as fh:
                fh.write(data)
            return real(path)
        with mock.patch.object(M, "_probe_db", sonda):
            return self._rename()

    def test_base_vieja_que_reaparece_vacia(self):
        _seed_legacy(self.home)
        r = self._reaparece(b"")
        self.assertEqual((r["codigo"], r["escribio"]), ("ok", False))
        self.assertIn("reapareció", r["aviso"])
        self.assertIn("la captura no escribió ahí", r["aviso"])
        self.assertTrue(os.path.isfile(self.target))

    def test_critico_base_vieja_que_reaparece_con_escrituras(self):
        _seed_legacy(self.home)
        r = self._reaparece(b"x" * 4096)
        self.assertEqual((r["codigo"], r["escribio"]), ("ok", True))
        self.assertIn("esas capturas no están en neb.db", r["aviso"])
        self.assertTrue(os.path.isfile(self.target))


class TestBaseViejaInservible(_Base):

    def _vieja_no_sqlite(self):
        os.makedirs(self.base, exist_ok=True)
        with open(self.legacy, "wb") as fh:
            fh.write(b"no soy sqlite" * 100)

    def _vieja_sin_work(self):
        os.makedirs(self.base, exist_ok=True)
        con = sqlite3.connect(self.legacy)
        con.execute("CREATE TABLE otra (a)")
        con.commit()
        con.close()

    def test_aborta_sin_tocar_nada_y_pide_moverla_fuera(self):
        for sembrar in (self._vieja_no_sqlite, self._vieja_sin_work):
            with self.subTest(sembrar.__name__):
                shutil.rmtree(self.base, True)
                sembrar()
                before = _snapshot(self.base)
                with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                    self.assertEqual(M.migrate(self.home), 1)
                salida = err.getvalue()
                self.assertIn("no es una base usable de la bitácora", salida)
                self.assertIn(f"Muévelo fuera de {self.base}", salida)
                self.assertIn("No se tocó nada.", salida)
                self.assertNotIn("vuelve a correr", salida)
                self.assertEqual(_snapshot(self.base), before)
                self.assertEqual(self._backups(), [])


_OPENER = r"""
import sys, time, json
sys.path.insert(0, sys.argv[1])
import _db_shared
t0 = float(sys.argv[3])
while time.time() < t0:
    time.sleep(0.005)
try:
    con = _db_shared.open_default_db(sys.argv[2])
except _db_shared.UnmigratedDb:
    con = None
if con is None:
    print(json.dumps({"ok": False}))
else:
    n = con.execute("SELECT count(*) FROM work").fetchone()[0]
    print(json.dumps({"ok": True, "works": n}))
    con.close()
"""


def _child_env(home):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("NEB_") and k not in ("PYTHONUTF8", "CLAUDE_PLUGIN_ROOT",
                                                     "CLAUDE_PREPROCESS_RECURSION")}
    env.update(HOME=home, USERPROFILE=home, PYTHONIOENCODING="utf-8")
    return env


class TestConcurrenciaTrasMigrar(unittest.TestCase):

    PROCESOS = 8
    REPETICIONES = 3

    def test_varios_procesos_abren_a_la_vez_tras_el_migrador(self):
        for rep in range(self.REPETICIONES):
            with self.subTest(rep=rep):
                home = tempfile.mkdtemp(prefix="neb-migrate-race-")
                self.addCleanup(shutil.rmtree, home, True)
                _seed_legacy(home, rows=2)
                with mock.patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(M.migrate(home), 0)
                t0 = str(time.time() + 1.5)
                procs = [subprocess.Popen([sys.executable, "-c", _OPENER, LIB, home, t0],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_child_env(home))
                         for _ in range(self.PROCESOS)]
                outs = [p.communicate(timeout=60) for p in procs]
                for out, err in outs:
                    self.assertEqual(json.loads(out.decode()), {"ok": True, "works": 2},
                                     err.decode("utf-8", "replace"))


class TestComandoDelMigrador(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-migrate-cmd-")
        self.addCleanup(shutil.rmtree, self.home, True)
        _seed_legacy(self.home)

    def test_usa_el_interprete_que_corre(self):
        cmd = _db_shared.unmigrated_legacy(self.home).comando
        self.assertTrue(cmd.startswith(f'"{sys.executable}" "'), cmd)
        self.assertIn("migrate-neb-db.py", cmd)

    def test_agrega_home_si_no_es_el_de_la_tilde(self):
        otro = tempfile.mkdtemp(prefix="neb-migrate-otro-")
        self.addCleanup(shutil.rmtree, otro, True)
        with mock.patch.dict(os.environ, {"HOME": otro, "USERPROFILE": otro}):
            cmd = _db_shared.unmigrated_legacy(self.home).comando
        self.assertTrue(cmd.endswith(f' --home "{self.home}"'), cmd)

    def test_sin_home_si_es_el_de_la_tilde(self):
        with mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home}):
            self.assertEqual(os.path.expanduser("~"), self.home)
            cmd = _db_shared.unmigrated_legacy(self.home).comando
        self.assertNotIn("--home", cmd)


if __name__ == "__main__":
    unittest.main()
