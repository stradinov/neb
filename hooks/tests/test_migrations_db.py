#!/usr/bin/env python3
"""
test_migrations_db.py — versión de esquema y pasos de base de neb.db (REQ neb-migraciones-de-version, 6.48.0).

Cubre hooks/lib/_migrations.py a través de _db_shared._connect, con una lista de pasos inyectable (pasos
ficticios en lugar de los pasos 2 y 3 de producción; el paso 2 real lo prueba test_logbook_migracion_team.py):
  • base nueva y base de 6.47.0 sin tabla de versión (mismo contenido, segunda conexión sin cambio de esquema);
  • dos procesos a la vez con la base en V = 0;
  • las cuatro filas de la regla de compatibilidad;
  • paso destructivo: respaldo verificado antes, uno por paso después, ninguno si falla, base idéntica tras el fallo;
  • `espera`, `precheck`, candado ocupado sin `espera`, `paso-bloqueado`, `schema_step_error`;
  • isolation_level intacto; un paso que rompe su transacción;
  • reparaciones: sin DDL sobre una base más nueva; la limpieza de transcripts no toma respaldo;
  • el código de 6.47.0 sobre una base ya marcada por 6.48.0;
  • `neb-migrate.py`: status de solo lectura, restore (WAL activo, validaciones, negativas, retención).
  • paso 3 real (7.3.0, eje proyecto): base en la versión 2 con raíz 'cliente' (renombra, el resto igual,
    respaldo previo), base nueva y base solo con el sentinel y temas planos (no hace nada ni bloquea),
    colisión con un tema 'proyecto' (precheck con motivo, nada cambia), carrera entre precheck y aplicar,
    idempotencia y un código 7.2.x sobre la base migrada.

Invariantes: homes y bases temporales; nunca ~/.claude; sin NEB_HOME ni NEB_LOGBOOK_* heredados.
  py -m unittest discover -s hooks/tests -p test_migrations_db.py
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sin_registro  # noqa: E402,F401 — sin el registro real de Windows
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
NEB_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, LIB)

import _db_shared
import _migrations
from _migrations import Step

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
DATA_TABLES_EXCLUDED = ("schema_step", "schema_step_error")


def _load_neb_migrate():
    spec = importlib.util.spec_from_file_location(
        "neb_migrate_cli", os.path.join(NEB_ROOT, "bootstrap", "neb-migrate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NM = _load_neb_migrate()


def table_hashes(path):
    """Hash por tabla de datos (contenido ordenado), sin las tablas del mecanismo."""
    con = sqlite3.connect(path)
    try:
        out = {}
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for t in names:
            if t in DATA_TABLES_EXCLUDED:
                continue
            h = hashlib.sha256()
            for row in con.execute(f"SELECT * FROM {t} ORDER BY 1"):
                h.update(repr(row).encode())
            out[t] = h.hexdigest()
        return out
    finally:
        con.close()


def columns(path, table):
    con = sqlite3.connect(path)
    try:
        return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    finally:
        con.close()


def legacy_647_db(path):
    """Base como la deja 6.47.0: esquema inicial + columnas, sin tabla de versión, con datos."""
    con = sqlite3.connect(path)
    with open(SCHEMA, encoding="utf-8") as fh:
        con.executescript(fh.read())
    _migrations.add_initial_columns(con)
    con.execute("INSERT INTO work (mode, project, req_slug, created_at, updated_at) "
                "VALUES ('req', 'h/o/r', 'req-a', '2026-01-01', '2026-01-01')")
    con.execute("INSERT INTO pending (context_origin, created_at, slug) VALUES ('algo', '2026-01-01', 'algo')")
    con.commit()
    con.close()


def add_column_step(n, min_code=None, **kw):
    def aplicar(con):
        con.execute(f"ALTER TABLE work ADD COLUMN extra{n} TEXT")
    return Step(n, f"columna extra{n}", aplicar, min_code=min_code, **kw)


def drop_column_step(n, col="transcript_error", **kw):
    def aplicar(con):
        con.execute(f"ALTER TABLE work DROP COLUMN {col}")
    return Step(n, f"quita {col}", aplicar, destructivo=True, **kw)


STEP1 = _migrations.STEPS[0]


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-test-mig-")
        self.addCleanup(shutil.rmtree, self.home, True)
        os.makedirs(os.path.join(self.home, ".claude"))
        self.db = os.path.join(self.home, ".claude", "neb.db")
        env = {k: v for k, v in os.environ.items()
               if k != "NEB_HOME" and not k.startswith("NEB_LOGBOOK_")}
        env.update(HOME=self.home, USERPROFILE=self.home)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self, steps=None, path=None, retry=False):
        with contextlib.redirect_stderr(io.StringIO()):
            return _db_shared._connect(path or self.db, SCHEMA, steps=steps, retry=retry)

    def version(self, path=None):
        con = sqlite3.connect(path or self.db)
        try:
            return _migrations.read_version(con)
        finally:
            con.close()

    def backups(self):
        return sorted(os.listdir(_migrations.backup_dir(self.db))) \
            if os.path.isdir(_migrations.backup_dir(self.db)) else []


class TestPaso1(Base):

    def test_base_nueva_queda_en_la_version_del_codigo(self):
        con = self.connect()
        self.assertIsNotNone(con)
        rows = con.execute("SELECT step, min_code, title, neb_version, backup FROM schema_step ORDER BY step").fetchall()
        con.close()
        self.assertEqual([r[:3] for r in rows], [(s.n, s.min_code, s.titulo) for s in _migrations.STEPS])
        self.assertEqual(rows[0][:3], (1, 1, "esquema inicial"))
        self.assertEqual({r[3] for r in rows}, {_migrations.neb_version()})
        self.assertEqual({r[4] for r in rows}, {None}, "una base recién creada no toma respaldo")
        self.assertEqual(self.version(), (_migrations.SCHEMA_VERSION, _migrations.STEPS[-1].min_code))
        self.assertEqual(self.backups(), [])

    def test_base_647_conserva_su_contenido_y_la_segunda_conexion_no_cambia_el_esquema(self):
        legacy_647_db(self.db)
        before = table_hashes(self.db)
        self.connect([STEP1]).close()
        self.assertEqual(self.version(), (1, 1))
        self.assertEqual(table_hashes(self.db), before)
        con = sqlite3.connect(self.db)
        sv = con.execute("PRAGMA schema_version").fetchone()[0]
        con.close()
        self.connect([STEP1]).close()
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("PRAGMA schema_version").fetchone()[0], sv)
        con.close()

    def test_base_con_ddl_anterior_llega_al_esquema_de_647(self):
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE work (id INTEGER PRIMARY KEY, mode TEXT NOT NULL DEFAULT 'req', project TEXT, "
                    "req_slug TEXT, owner TEXT, lock_state TEXT NOT NULL DEFAULT 'owned', takeover_by TEXT, "
                    "locked_at TEXT, req_state TEXT, branch TEXT, head_commit TEXT, repo_path TEXT, change_md TEXT, "
                    "payload_json TEXT, payload_version INTEGER NOT NULL DEFAULT 0, origin_dev TEXT, "
                    "origin_machine TEXT, claude_session_id TEXT, claude_session_name TEXT, transcript_path TEXT, "
                    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived_at TEXT, "
                    "dirty INTEGER NOT NULL DEFAULT 1, synced_at TEXT, remote_id INTEGER)")
        con.commit()
        con.close()
        self.connect([STEP1]).close()
        cols = columns(self.db, "work")
        for c, _ddl in _migrations._WORK_MIGRATIONS:
            self.assertIn(c, cols)
        self.assertEqual(self.version(), (1, 1))

    def test_dos_procesos_a_la_vez_con_la_base_en_cero(self):
        legacy_647_db(self.db)
        barrier = threading.Barrier(2)
        results = []

        def run():
            barrier.wait()
            con = self.connect()
            results.append(con is not None)
            if con is not None:
                con.close()

        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results, [True, True])
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("SELECT count(*) FROM schema_step").fetchone()[0], _migrations.SCHEMA_VERSION)
        con.close()


class TestRegla(Base):

    def test_v_menor_que_c_aplica_los_pasos(self):
        self.connect([STEP1]).close()
        con = self.connect([STEP1, add_column_step(2)])
        self.assertIsNotNone(con)
        con.close()
        self.assertIn("extra2", columns(self.db, "work"))
        self.assertEqual(self.version(), (2, 2))

    def test_base_mas_nueva_compatible_opera_sin_reparaciones(self):
        self.connect([STEP1, add_column_step(2, min_code=1)]).close()
        con = sqlite3.connect(self.db)
        con.execute("DROP INDEX uq_pending_slug")
        con.commit()
        con.close()
        con = self.connect([STEP1])
        self.assertIsNotNone(con)
        con.close()
        con = sqlite3.connect(self.db)
        idx = con.execute("SELECT 1 FROM sqlite_master WHERE name='uq_pending_slug'").fetchone()
        con.close()
        self.assertIsNone(idx, "un código más viejo no le escribe DDL a una base más nueva")

    def test_base_incompatible_no_se_toca(self):
        self.connect([STEP1, add_column_step(2, min_code=2)]).close()
        before = table_hashes(self.db)
        with self.assertRaises(_migrations.IncompatibleDb) as cm:
            self.connect([STEP1])
        self.assertEqual(cm.exception.motivo, "base-incompatible")
        self.assertIn("2", cm.exception.detalle)
        self.assertEqual(table_hashes(self.db), before)

    def test_f_es_el_maximo_de_min_code(self):
        self.connect([STEP1, add_column_step(2, min_code=2), add_column_step(3, min_code=1)]).close()
        self.assertEqual(self.version(), (3, 2))


class TestDestructivo(Base):

    def test_respaldo_verificado_antes_y_uno_por_paso_despues(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        before = table_hashes(self.db)
        self.connect([STEP1, drop_column_step(2)]).close()
        b = self.backups()
        self.assertEqual(len(b), 1)
        self.assertTrue(b[0].startswith("neb.pre-paso-2."))
        bak = os.path.join(_migrations.backup_dir(self.db), b[0])
        self.assertEqual(table_hashes(bak), before)
        self.assertIn("transcript_error", columns(bak, "work"))
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("SELECT backup FROM schema_step WHERE step=2").fetchone()[0], bak)
        con.close()
        self.connect([STEP1, drop_column_step(2), drop_column_step(3, col="transcript_error_at")]).close()
        b = self.backups()
        self.assertEqual(len(b), 2, b)
        self.assertEqual(b[0], os.path.basename(bak), "el respaldo del paso 2 sobrevive al paso 3")
        self.assertTrue(b[1].startswith("neb.pre-paso-3."), b)

    def test_pasos_2_y_3_en_la_misma_corrida_conservan_un_respaldo_de_cada_uno(self):
        """Una base en la versión 1 que aplica dos pasos destructivos en la misma conexión: queda el respaldo de
        cada paso, cada uno con lo que había antes de ese paso."""
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        self.connect([STEP1, drop_column_step(2), drop_column_step(3, col="transcript_error_at")]).close()
        self.assertEqual(self.version()[0], 3)
        b = self.backups()
        self.assertEqual(len(b), 2, b)
        self.assertTrue(b[0].startswith("neb.pre-paso-2.") and b[1].startswith("neb.pre-paso-3."), b)
        folder = _migrations.backup_dir(self.db)
        self.assertIn("transcript_error", columns(os.path.join(folder, b[0]), "work"))
        self.assertNotIn("transcript_error", columns(os.path.join(folder, b[1]), "work"))
        self.assertIn("transcript_error_at", columns(os.path.join(folder, b[1]), "work"))
        con = sqlite3.connect(self.db)
        try:
            rows = con.execute("SELECT step, backup FROM schema_step WHERE step > 1 ORDER BY step").fetchall()
        finally:
            con.close()
        self.assertEqual(rows, [(2, os.path.join(folder, b[0])), (3, os.path.join(folder, b[1]))])

    def test_dos_corridas_del_mismo_paso_conservan_solo_el_ultimo_de_ese_paso(self):
        """La base vuelve a la versión 1 (restore --remigrar de su respaldo) y el paso 2 corre otra vez: su respaldo
        nuevo reemplaza al anterior del mismo paso; el de otro paso no se toca."""
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        folder = _migrations.backup_dir(self.db)
        otro = os.path.join(folder, "neb.pre-paso-3.20200101T000000Z.db")
        self.connect([STEP1, drop_column_step(2)]).close()
        primero = os.path.join(folder, self.backups()[0])
        shutil.copyfile(primero, otro)                    # respaldo de otro paso: la poda del 2 no lo toca
        shutil.copyfile(primero, self.db)                 # vuelve a la versión 1
        self.assertEqual(self.version()[0], 1)
        self.connect([STEP1, drop_column_step(2)]).close()
        self.assertEqual(self.version()[0], 2)
        b = self.backups()
        self.assertEqual(len(b), 2, b)
        self.assertTrue(b[0].startswith("neb.pre-paso-2."), b)
        self.assertNotEqual(os.path.join(folder, b[0]), primero, "queda el respaldo de la segunda corrida")
        self.assertFalse(os.path.exists(primero))
        self.assertEqual(os.path.join(folder, b[1]), otro)

    def test_respaldo_en_un_solo_archivo_y_la_poda_no_deja_restos(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        self.connect([STEP1, drop_column_step(2)]).close()
        folder = _migrations.backup_dir(self.db)
        bak = os.path.join(folder, self.backups()[0])
        ro = sqlite3.connect(pathlib.Path(bak).as_uri() + "?mode=ro", uri=True)
        self.assertEqual(ro.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        ro.execute("SELECT count(*) FROM work").fetchone()
        ro.close()
        self.assertEqual(sorted(os.listdir(folder)), [os.path.basename(bak)])
        viejo = os.path.join(folder, "neb.pre-paso-3.20200101T000000Z.db")   # respaldo anterior del mismo paso
        for suf in ("", "-wal", "-shm"):                  # con restos de una copia anterior a la corrección
            open(viejo + suf, "wb").close()
        self.connect([STEP1, drop_column_step(2), drop_column_step(3, col="transcript_error_at")]).close()
        left = sorted(os.listdir(folder))
        self.assertEqual(len(left), 2, left)
        self.assertEqual(left[0], os.path.basename(bak))
        self.assertTrue(left[1].startswith("neb.pre-paso-3.") and left[1].endswith(".db"), left)
        self.assertNotEqual(left[1], os.path.basename(viejo))

    def test_paso_que_falla_deja_la_base_identica_sin_respaldo_y_con_su_fallo(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        before = table_hashes(self.db)
        cols = columns(self.db, "work")

        def aplicar(con):
            con.execute("ALTER TABLE work DROP COLUMN transcript_error")
            con.execute("SELECT * FROM tabla_que_no_existe")
        con = self.connect([STEP1, Step(2, "falla", aplicar, destructivo=True, espera=True)])
        self.assertIsNotNone(con, "con espera, la conexión sigue")
        con.close()
        self.assertEqual(self.version(), (1, 1))
        self.assertEqual(table_hashes(self.db), before)
        self.assertEqual(columns(self.db, "work"), cols)
        self.assertEqual(self.backups(), [])
        con = sqlite3.connect(self.db)
        errs = _migrations.read_errors(con)
        con.close()
        self.assertEqual([e[0] for e in errs], [2])
        self.assertIn("error al aplicar", errs[0][3])
        self.connect([STEP1, drop_column_step(2)], retry=True).close()   # el paso corregido, vía apply
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("SELECT count(*) FROM schema_step_error").fetchone()[0], 0)
        con.close()

    def test_respaldo_imposible_el_paso_no_corre(self):
        self.connect([STEP1]).close()
        with open(_migrations.backup_dir(self.db), "w") as fh:     # la carpeta es un archivo
            fh.write("x")
        con = self.connect([STEP1, drop_column_step(2, espera=True)])
        self.assertIsNotNone(con)
        con.close()
        self.assertEqual(self.version(), (1, 1))
        self.assertIn("transcript_error", columns(self.db, "work"))
        con = sqlite3.connect(self.db)
        self.assertIn("respaldo fallido", _migrations.read_errors(con)[0][3])
        con.close()

    def test_base_recien_creada_no_respalda(self):
        self.connect([STEP1, drop_column_step(2)]).close()
        self.assertEqual(self.version(), (2, 2))
        self.assertEqual(self.backups(), [])

    def test_respaldo_dentro_de_la_transaccion_con_journal_delete(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        con = sqlite3.connect(self.db)
        con.execute("PRAGMA journal_mode=DELETE")
        con.close()
        bak = None
        con = sqlite3.connect(self.db)
        con.isolation_level = None
        con.execute("BEGIN IMMEDIATE")
        try:
            bak = _migrations.take_backup(self.db, "neb.pre-paso-9.prueba.db")
        finally:
            con.execute("ROLLBACK")
            con.close()
        self.assertTrue(os.path.isfile(bak))


class TestEsperaYBloqueo(Base):

    def test_precheck_con_espera_sigue_sin_candado_ni_respaldo(self):
        self.connect([STEP1]).close()
        con = self.connect([STEP1, drop_column_step(2, espera=True, precheck=lambda c: "vista v_mia")])
        self.assertIsNotNone(con)
        con.close()
        self.assertEqual(self.version(), (1, 1))
        self.assertEqual(self.backups(), [])

    def test_precheck_sin_espera_lanza_paso_bloqueado(self):
        self.connect([STEP1]).close()
        with self.assertRaises(_migrations.DbUnavailable) as cm:
            self.connect([STEP1, drop_column_step(2, precheck=lambda c: "vista v_mia")])
        self.assertEqual(cm.exception.motivo, "paso-bloqueado")
        self.assertIn("v_mia", cm.exception.detalle)

    def test_paso_en_espera_seguido_de_uno_sin_espera_no_entrega_la_base(self):
        self.connect([STEP1]).close()
        steps = [STEP1, drop_column_step(2, espera=True, precheck=lambda c: "bloqueado"), add_column_step(3)]
        with self.assertRaises(_migrations.DbUnavailable):
            self.connect(steps)

    def test_candado_ocupado_sin_espera_da_none(self):
        self.connect([STEP1]).close()
        other = sqlite3.connect(self.db)
        other.isolation_level = None
        other.execute("BEGIN IMMEDIATE")
        try:
            con = self.connect([STEP1, add_column_step(2)])
        finally:
            other.execute("ROLLBACK")
            other.close()
        self.assertIsNone(con)
        self.assertEqual(self.version(), (1, 1))

    def test_fila_vieja_de_error_no_se_reporta(self):
        self.connect([STEP1, add_column_step(2)]).close()
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO schema_step_error VALUES (2, 'x', 'x', 'viejo')")
        con.commit()
        self.assertEqual(_migrations.read_errors(con), [])
        self.assertEqual(_migrations.blocked_report(con, [STEP1, add_column_step(2)]), [])
        con.close()

    def test_error_no_se_escribe_si_otro_proceso_ya_aplico_el_paso(self):
        self.connect([STEP1, add_column_step(2)]).close()
        con = sqlite3.connect(self.db)
        _migrations._record_error(con, 2, "tarde")
        self.assertEqual(con.execute("SELECT count(*) FROM schema_step_error").fetchone()[0], 0)
        con.close()


class TestTransaccion(Base):

    def test_isolation_level_intacto_y_la_captura_confirma_con_commit(self):
        self.connect([STEP1]).close()
        con = self.connect([STEP1, add_column_step(2)])
        self.assertEqual(con.isolation_level, "")
        con.execute("INSERT INTO work (mode, project, req_slug, created_at, updated_at) "
                    "VALUES ('req', 'p', 'r', 'a', 'a')")
        self.assertTrue(con.in_transaction)
        con.commit()
        con.close()
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("SELECT count(*) FROM work").fetchone()[0], 1)
        con.close()

    def test_paso_que_rompe_su_transaccion_se_detecta(self):
        self.connect([STEP1]).close()
        con = self.connect([STEP1, Step(2, "rompe", lambda c: c.execute("COMMIT"), espera=True)])
        con.close()
        self.assertEqual(self.version(), (1, 1))
        c2 = sqlite3.connect(self.db)
        self.assertIn("no controla la transacción", _migrations.read_errors(c2)[0][3])
        c2.close()


class TestRobustez(Base):

    def test_excepcion_ajena_a_sqlite_en_aplicar_se_registra_y_libera_el_candado(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        before = table_hashes(self.db)

        def malo(con):
            con.execute("ALTER TABLE work DROP COLUMN transcript_error")
            raise TypeError("paso mal escrito")
        with self.assertRaises(_migrations.DbUnavailable) as cm:
            self.connect([STEP1, Step(2, "malo", malo, destructivo=True)])
        self.assertEqual(cm.exception.motivo, "paso-bloqueado")
        self.assertIn("paso mal escrito", cm.exception.detalle)
        self.assertEqual(table_hashes(self.db), before)
        self.assertIn("transcript_error", columns(self.db, "work"))
        self.assertEqual(self.backups(), [])
        other = sqlite3.connect(self.db, timeout=0.1)
        other.isolation_level = None
        other.execute("BEGIN IMMEDIATE")                  # el candado quedó libre
        other.execute("ROLLBACK")
        self.assertIn("paso mal escrito", _migrations.read_errors(other)[0][3])
        other.close()

    def test_paso_que_intenta_confirmar_no_deja_nada_confirmado(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        before = table_hashes(self.db)
        for intento in (lambda c: c.execute("COMMIT"), lambda c: c.commit(),
                        lambda c: c.executescript("SELECT 1"), lambda c: c.cursor().execute("COMMIT"),
                        lambda c: c.execute("-- confirmo\nCOMMIT"), lambda c: c.execute("/* x */ end"),
                        lambda c: c.execute("PRAGMA foreign_keys=OFF"), lambda c: c.execute("PRAGMA foreign_keys(0)")):
            def rompe(con, intento=intento):
                con.execute("ALTER TABLE work DROP COLUMN transcript_error")
                intento(con)
            with self.assertRaises(_migrations.DbUnavailable):
                self.connect([STEP1, Step(2, "rompe", rompe, destructivo=True)], retry=True)
            self.assertIn("transcript_error", columns(self.db, "work"))
            self.assertEqual(table_hashes(self.db), before)
            self.assertEqual(self.backups(), [])
            self.assertEqual(self.version(), (1, 1))

    def test_guarda_de_sentencias_sin_backtracking_con_sangria_larga(self):
        import time
        sql = "\n" + " " * 26 + "UPDATE work SET project = project"   # con \s+ anidado tardaría segundos
        t = time.monotonic()
        self.assertIsNone(_migrations._TX_CONTROL_RE.match(sql))
        self.assertIsNone(_migrations._FK_PRAGMA_RE.match(sql))
        self.assertLess(time.monotonic() - t, 0.5)
        self.assertIsNotNone(_migrations._TX_CONTROL_RE.match(" " * 60 + "COMMIT"))

    def test_reversion_de_sqlite_es_un_error_comun_que_se_reintenta(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        calls = []

        def revierte(con):                                # OR ROLLBACK: SQLite revierte la transacción entera
            calls.append(1)
            con.execute("ALTER TABLE work DROP COLUMN transcript_error")
            con.execute("INSERT OR ROLLBACK INTO pending (context_origin, created_at, slug) VALUES ('x', 'a', 'algo')")
        steps = [STEP1, Step(2, "revierte", revierte, destructivo=True)]
        with self.assertRaises(_migrations.DbUnavailable):
            self.connect(steps)
        self.assertIn("transcript_error", columns(self.db, "work"))
        self.assertEqual(self.backups(), [])
        with self.assertRaises(_migrations.DbUnavailable):
            self.connect(steps, retry=True)              # no queda bloqueado para siempre: apply lo reintenta
        self.assertEqual(len(calls), 2)

    def test_paso_que_se_traga_la_reversion_no_confirma_lo_siguiente(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()

        def traga(con):
            con.execute("ALTER TABLE work DROP COLUMN transcript_error")
            try:
                con.execute("INSERT OR ROLLBACK INTO pending (context_origin, created_at, slug) VALUES ('x', 'a', 'algo')")
            except sqlite3.IntegrityError:
                pass
            con.execute("UPDATE pending SET context_origin = 'suelto'")   # sin guarda, se confirmaría suelto
        before = table_hashes(self.db)
        with self.assertRaises(_migrations.DbUnavailable):
            self.connect([STEP1, Step(2, "traga", traga, destructivo=True)])
        self.assertIn("transcript_error", columns(self.db, "work"))
        self.assertEqual(table_hashes(self.db), before)

    def test_paso_que_se_traga_la_reversion_y_termina_no_se_registra(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()

        def traga(con):
            con.execute("ALTER TABLE work DROP COLUMN transcript_error")
            try:
                con.execute("INSERT OR ROLLBACK INTO pending (context_origin, created_at, slug) VALUES ('x', 'a', 'algo')")
            except sqlite3.IntegrityError:
                pass
        with self.assertRaises(_migrations.DbUnavailable):
            self.connect([STEP1, Step(2, "traga", traga, destructivo=True)])
        self.assertEqual(self.version(), (1, 1), "un paso revertido no queda registrado como aplicado")
        self.assertIn("transcript_error", columns(self.db, "work"))

    def test_precheck_que_lanza_se_reporta_en_status(self):
        self.connect([STEP1]).close()

        def malo(con):
            raise ValueError("precheck roto")
        con = sqlite3.connect(self.db)
        rep = _migrations.blocked_report(con, [STEP1, add_column_step(2, precheck=malo)])
        con.close()
        self.assertEqual(len(rep), 1)
        self.assertIn("precheck roto", rep[0][2])

    def test_reloj_que_retrocede_no_alarga_la_espera(self):
        futuro = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat(timespec="seconds")
        self.assertFalse(_migrations._in_backoff(futuro))
        reciente = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(timespec="seconds")
        self.assertTrue(_migrations._in_backoff(reciente))

    def test_precheck_que_falla_porque_otro_proceso_ya_aplico_el_paso_no_bloquea(self):
        self.connect([STEP1]).close()

        def precheck(con):
            o = sqlite3.connect(self.db)
            o.execute("ALTER TABLE work ADD COLUMN extra2 TEXT")
            o.execute("INSERT INTO schema_step VALUES (2, 2, 'columna extra2', 'x', 'x', NULL)")
            o.commit()
            o.close()
            return "columna en uso"
        con = self.connect([STEP1, add_column_step(2, precheck=precheck)])
        self.assertIsNotNone(con)
        con.close()
        self.assertEqual(self.version(), (2, 2))

    def test_otro_proceso_que_avanza_con_mayor_minima_da_base_incompatible(self):
        self.connect([STEP1]).close()

        def precheck(con):
            o = sqlite3.connect(self.db)
            o.execute("INSERT INTO schema_step VALUES (2, 3, 'otro', 'x', 'x', NULL)")
            o.execute("INSERT INTO schema_step VALUES (3, 3, 'otro', 'x', 'x', NULL)")
            o.commit()
            o.close()
            return None
        with self.assertRaises(_migrations.IncompatibleDb):
            self.connect([STEP1, add_column_step(2, precheck=precheck)])
        self.assertNotIn("extra2", columns(self.db, "work"))

    def test_fallo_reciente_no_se_reintenta_hasta_la_espera_o_con_apply(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        calls = []

        def falla(con):
            calls.append(1)
            con.execute("ALTER TABLE work DROP COLUMN no_existe")
        steps = [STEP1, Step(2, "falla", falla, destructivo=True, espera=True)]
        self.connect(steps).close()
        self.connect(steps).close()
        self.assertEqual(len(calls), 1, "dentro de la espera no se reintenta ni se copia la base")
        self.assertEqual(self.backups(), [])
        self.connect(steps, retry=True).close()
        self.assertEqual(len(calls), 2)
        with mock.patch.object(_migrations, "RETRY_BACKOFF_SECONDS", 0):
            self.connect(steps).close()
        self.assertEqual(len(calls), 3)


class TestReparaciones(Base):

    def test_limpieza_de_transcripts_no_toma_respaldo(self):
        legacy_647_db(self.db)
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE transcript_local (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, "
                    "work_id INTEGER, byte_from INTEGER NOT NULL, byte_to INTEGER NOT NULL, "
                    "text_plain TEXT NOT NULL, created_at TEXT NOT NULL)")
        con.execute("INSERT INTO transcript_local VALUES (1, 's', NULL, 0, 10, 'x', 'a')")
        con.commit()
        con.close()
        self.connect([STEP1]).close()
        self.assertFalse(_migrations._table_exists(sqlite3.connect(self.db), "transcript_local"))
        self.assertFalse(os.path.exists(_migrations.backup_dir(self.db)))


class TestCodigoAnterior(Base):

    def test_codigo_647_sobre_base_marcada_por_648(self):
        old = tempfile.mkdtemp(prefix="neb-test-647-")
        self.addCleanup(shutil.rmtree, old, True)
        try:
            src = subprocess.run(["git", "-C", NEB_ROOT, "show", "0a05695:hooks/lib/_db_shared.py"],
                                 capture_output=True, text=True, encoding="utf-8", check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("sin git o sin el commit de 6.47.0")
        with open(os.path.join(old, "_db_shared_647.py"), "w", encoding="utf-8") as fh:
            fh.write(src)
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        before = table_hashes(self.db)
        spec = importlib.util.spec_from_file_location("_db_shared_647", os.path.join(old, "_db_shared_647.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with contextlib.redirect_stderr(io.StringIO()):
            con = mod._connect(self.db, SCHEMA)
        self.assertIsNotNone(con)
        self.assertEqual(con.execute("SELECT count(*) FROM pending").fetchone()[0], 1)
        con.close()
        self.assertEqual(table_hashes(self.db), before)
        self.assertEqual(self.version(), (1, 1))


class TestNebMigrate(Base):

    def run_nm(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = NM.main(list(argv))
        return rc, out.getvalue()

    def test_status_sin_base_no_la_crea(self):
        rc, out = self.run_nm("status", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["estado"], "sin-base")
        self.assertFalse(os.path.exists(self.db))

    def test_status_muestra_paso_detenido_y_no_escribe(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        steps = [STEP1, drop_column_step(2, espera=True, precheck=lambda c: "vista v_mia")]
        with mock.patch.object(_migrations, "STEPS", tuple(steps)):
            before = os.path.getmtime(self.db)
            rc, out = self.run_nm("status", "--json")
        s = json.loads(out)
        self.assertEqual(s["estado"], "atras")
        self.assertEqual(s["pasos_detenidos"][0]["motivo"], "vista v_mia")
        self.assertEqual(os.path.getmtime(self.db), before)

    def _destructive_backup(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        snapshot = table_hashes(self.db)
        self.connect([STEP1, drop_column_step(2)]).close()
        return os.path.join(_migrations.backup_dir(self.db), self.backups()[0]), snapshot

    def test_restore_con_wal_activo_y_un_lector_abierto(self):
        bak, snapshot = self._destructive_backup()
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO pending (context_origin, created_at) VALUES ('nuevo', 'b')")
        con.commit()
        reader = sqlite3.connect(self.db)
        reader.isolation_level = None
        reader.execute("BEGIN")                           # transacción de lectura abierta durante el restore
        reader.execute("SELECT count(*) FROM work").fetchone()
        try:
            with mock.patch.object(_migrations, "STEPS", (STEP1,)):
                rc, out = self.run_nm("restore", bak)
        finally:
            reader.execute("ROLLBACK")
            reader.close()
            con.close()
        self.assertEqual(rc, 0, out)
        self.assertEqual(table_hashes(self.db), snapshot)
        c = sqlite3.connect(self.db)
        self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        c.close()
        names = self.backups()
        self.assertEqual(sum(n.startswith("neb.pre-restore.") for n in names), 1)

    def test_restore_se_niega_si_la_siguiente_conexion_volveria_a_migrar(self):
        bak, _ = self._destructive_backup()
        with mock.patch.object(_migrations, "STEPS", (STEP1, drop_column_step(2))):
            rc, out = self.run_nm("restore", bak)
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads(out)["motivo"], "se-volveria-a-migrar")
            rc, out = self.run_nm("restore", bak, "--remigrar")
        self.assertEqual(rc, 0, out)

    def test_restore_se_niega_si_el_codigo_no_operaria_el_respaldo(self):
        bak, _ = self._destructive_backup()
        con = sqlite3.connect(bak)
        con.execute("INSERT INTO schema_step VALUES (5, 5, 'futuro', 'x', 'x', NULL)")
        con.commit()
        con.close()
        with mock.patch.object(_migrations, "STEPS", (STEP1,)):
            rc, out = self.run_nm("restore", bak)
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["motivo"], "respaldo-incompatible")

    def test_restore_rechaza_archivo_fuera_de_neb_backups_o_con_otro_nombre(self):
        bak, _ = self._destructive_backup()
        fuera = os.path.join(self.home, os.path.basename(bak))
        shutil.copy(bak, fuera)
        otro = os.path.join(_migrations.backup_dir(self.db), "cualquier.db")
        shutil.copy(bak, otro)
        for p in (fuera, otro):
            rc, out = self.run_nm("restore", p)
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads(out)["motivo"], "respaldo-no-valido")

    def _link_dir(self, target, link):
        """Junction en Windows (sin permisos de administrador), symlink en otros sistemas."""
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(target, link)
            else:
                os.symlink(target, link, target_is_directory=True)
        except (OSError, AttributeError, ImportError) as e:
            self.skipTest(f"no se pudo crear el enlace: {e}")

    def test_restore_rechaza_neb_backups_como_enlace(self):
        bak, _ = self._destructive_backup()
        folder = _migrations.backup_dir(self.db)
        real = os.path.join(self.home, "otra-carpeta")
        shutil.move(folder, real)
        self._link_dir(real, folder)
        self.addCleanup(lambda: os.path.isdir(folder) and (os.rmdir(folder) if os.name == "nt" else os.unlink(folder)))
        rc, out = self.run_nm("restore", os.path.join(folder, os.path.basename(bak)))
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["motivo"], "respaldo-no-valido")

    def test_restore_acepta_un_enlace_en_una_carpeta_superior(self):
        claude = os.path.join(self.home, ".claude")
        real = os.path.join(self.home, "claude-real")
        os.rmdir(claude)
        os.makedirs(real)
        self._link_dir(real, claude)
        self.addCleanup(lambda: os.path.isdir(claude) and (os.rmdir(claude) if os.name == "nt" else os.unlink(claude)))
        bak, snapshot = self._destructive_backup()
        with mock.patch.object(_migrations, "STEPS", (STEP1,)):
            rc, out = self.run_nm("restore", bak)
        self.assertEqual(rc, 0, out)
        self.assertEqual(table_hashes(self.db), snapshot)

    def test_restore_sin_base_previa_no_poda_el_pre_restore_anterior(self):
        bak, _ = self._destructive_backup()
        viejo = os.path.join(_migrations.backup_dir(self.db), "neb.pre-restore.20200101T000000Z.db")
        shutil.copy(bak, viejo)
        for suf in ("", "-wal", "-shm"):
            if os.path.exists(self.db + suf):
                os.remove(self.db + suf)
        with mock.patch.object(_migrations, "STEPS", (STEP1,)):
            rc, out = self.run_nm("restore", bak)
        self.assertEqual(rc, 0, out)
        self.assertIsNone(json.loads(out)["respaldo_previo"])
        self.assertTrue(os.path.isfile(viejo))

    def test_status_no_vuelca_un_wal_pendiente(self):
        legacy_647_db(self.db)
        self.connect().close()
        code = ("import sqlite3, os, sys; c = sqlite3.connect(sys.argv[1]); c.execute('PRAGMA journal_mode=WAL');"
                "c.execute('PRAGMA wal_autocheckpoint=0');"
                "c.execute(\"INSERT INTO pending (context_origin, created_at) VALUES ('en-wal', 'a')\"); c.commit();"
                "os._exit(0)")
        subprocess.run([sys.executable, "-c", code, self.db], check=True)
        wal = self.db + "-wal"
        self.assertTrue(os.path.getsize(wal) > 0, "la prueba necesita un -wal con contenido")
        with open(self.db, "rb") as fh:
            main_before = hashlib.sha256(fh.read()).hexdigest()
        wal_before = os.path.getsize(wal)
        rc, out = self.run_nm("status", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["estado"], "al-dia")
        with open(self.db, "rb") as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), main_before)
        self.assertTrue(os.path.exists(wal) and os.path.getsize(wal) == wal_before)

    def test_pre_restore_sobrevive_a_la_poda_y_restaurar_desde_el_no_lo_borra(self):
        bak, _ = self._destructive_backup()
        with mock.patch.object(_migrations, "STEPS", (STEP1,)):
            self.assertEqual(self.run_nm("restore", bak)[0], 0)
        pre = [n for n in self.backups() if n.startswith("neb.pre-restore.")][0]
        pre_path = os.path.join(_migrations.backup_dir(self.db), pre)
        with mock.patch.object(_migrations, "STEPS", (STEP1, drop_column_step(2))):
            rc, out = self.run_nm("restore", pre_path, "--remigrar")
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.isfile(pre_path), "nunca se borra el archivo del que se restauró")
        self.connect([STEP1, drop_column_step(2), drop_column_step(3, col="transcript_error_at")]).close()
        self.assertTrue(any(n.startswith("neb.pre-restore.") for n in self.backups()))


class TestSoloLectura(Base):

    def test_open_readonly_no_crea_el_archivo(self):
        self.assertIsNone(_migrations.open_readonly(self.db))
        self.assertFalse(os.path.exists(self.db))

    def test_open_readonly_con_espacios_y_acentos_en_la_ruta(self):
        path = os.path.join(self.home, "a b ñ José", "neb.db")
        os.makedirs(os.path.dirname(path))
        self.connect(path=path).close()
        con = _migrations.open_readonly(path)
        self.assertIsNotNone(con)
        self.assertEqual(_migrations.read_version(con), (_migrations.SCHEMA_VERSION, _migrations.STEPS[-1].min_code))
        con.close()

    def test_open_readonly_rechaza_escrituras(self):
        self.connect().close()
        con = _migrations.open_readonly(self.db)
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("CREATE TABLE x (a)")
        con.close()

    def test_schema_version_de_otro_arbol_como_texto(self):
        d = tempfile.mkdtemp(prefix="neb-test-arbol-")
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(_migrations.read_schema_version_text(os.path.join(d, "_migrations.py")), 1)
        p = os.path.join(d, "_migrations.py")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("x = 1\nSCHEMA_VERSION = 7\n")
        self.assertEqual(_migrations.read_schema_version_text(p), 7)
        self.assertEqual(_migrations.read_schema_version_text(os.path.join(LIB, "_migrations.py")),
                         _migrations.SCHEMA_VERSION)


class TestRutaConCorchetes(Base):
    """Un home con corchetes (p. ej. un usuario dev[1]) es ruta, no patrón de glob: x[1] no debe leerse como x1.
    Las podas borran: leída como patrón, la ruta borraría en la carpeta x1."""

    OLD_STEP = "neb.pre-paso-2.20200101T000000Z.db"
    OLD_RESTORE = "neb.pre-restore.20200101T000000Z.db"

    def setUp(self):
        super().setUp()
        parent = self.home
        self.home, self.decoy = os.path.join(parent, "x[1]"), os.path.join(parent, "x1")
        for h in (self.home, self.decoy):
            os.makedirs(os.path.join(h, ".claude"))
        self.db = os.path.join(self.home, ".claude", "neb.db")
        os.environ.update(HOME=self.home, USERPROFILE=self.home)   # el patcher de Base restaura el entorno

    def plant(self, name):
        """El mismo respaldo en neb-backups/ del home propio y del señuelo: (propio, señuelo)."""
        out = []
        for h in (self.home, self.decoy):
            d = os.path.join(h, ".claude", _migrations.BACKUP_DIR_NAME)
            os.makedirs(d, exist_ok=True)
            out.append(os.path.join(d, name))
            with open(out[-1], "w", encoding="utf-8") as fh:
                fh.write("x")
        return out

    def test_prune_backups_no_borra_en_otra_carpeta(self):
        own, decoy = self.plant(self.OLD_STEP)
        keep = os.path.join(os.path.dirname(own), "neb.pre-paso-2.20990101T000000Z.db")
        with open(keep, "w", encoding="utf-8") as fh:
            fh.write("x")
        _migrations.prune_backups(self.db, _migrations.STEP_BACKUP_GLOB, keep)
        self.assertFalse(os.path.exists(own))
        self.assertTrue(os.path.exists(keep))
        self.assertTrue(os.path.exists(decoy))

    def test_list_backups_lista_los_propios(self):
        own, _decoy = self.plant(self.OLD_STEP)
        self.assertEqual([p for p, _size in _migrations.list_backups(self.db)], [own])

    def test_restore_poda_sus_pre_restore_y_no_los_de_otra_carpeta(self):
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        self.connect([STEP1, drop_column_step(2)]).close()
        bak = os.path.join(_migrations.backup_dir(self.db), self.backups()[0])
        own, decoy = self.plant(self.OLD_RESTORE)
        out = io.StringIO()
        with mock.patch.object(_migrations, "STEPS", (STEP1,)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = NM.main(["restore", bak])
        self.assertEqual(rc, 0, out.getvalue())
        self.assertFalse(os.path.exists(own))           # queda solo el pre-restore nuevo
        self.assertEqual(sum(n.startswith("neb.pre-restore.") for n in self.backups()), 1)
        self.assertTrue(os.path.exists(decoy))



# --------------------------------------------------------------------------- paso 3 real: eje proyecto (7.3.0)

STEPS_7_2 = _migrations.STEPS[:2]          # los pasos de 7.0.0–7.2.x: una base en la versión 2


class TestPaso3EjeProyecto(Base):
    """Paso de base 3 de producción (7.3.0): renombra la raíz 'cliente' a 'proyecto' (slug y name) y nada más.
    Sin raíz 'cliente' no hace nada; un tema con slug 'proyecto' ya presente lo detiene en su precheck."""

    def v2_db(self, cliente=True, extra=()):
        """Base en la versión 2 (como la deja 7.2.x) con el eje curado: raíces 'cliente' y 'topico', hijos,
        pendientes curados (uno abierto, uno obsoleto), una sugerencia y el sentinel; `extra` son INSERT
        adicionales."""
        self.connect(STEPS_7_2).close()
        self.assertEqual(self.version(), (2, 2))
        con = sqlite3.connect(self.db)
        con.execute("PRAGMA foreign_keys=ON")
        if cliente:
            con.execute("INSERT INTO topic (id, slug, name, keywords) VALUES (33, 'cliente', 'Cliente', 'cliente')")
            con.execute("INSERT INTO topic (id, slug, name, parent_id) VALUES (40, 'alpha', 'Alpha', 33)")
            con.execute("INSERT INTO topic (id, slug, name, parent_id) VALUES (41, 'beta', 'Beta', 33)")
        con.execute("INSERT INTO topic (id, slug, name) VALUES (34, 'topico', 'Tópico')")
        con.execute("INSERT INTO topic (id, slug, name, parent_id) VALUES (50, 'seguridad', 'Seguridad', 34)")
        con.execute("INSERT INTO topic (id, slug, name) VALUES (60, 'sin-clasificar', 'Sin clasificar')")
        con.execute("INSERT INTO pending (id, context_origin, created_at, slug) VALUES (1, 'uno', 't', 'uno')")
        con.execute("INSERT INTO pending (id, context_origin, status, created_at, slug) "
                    "VALUES (2, 'dos', 'obsolete', 't', 'dos')")
        if cliente:
            con.execute("INSERT INTO pending_topic (pending_id, topic_id, priority_band, is_primary, curated) "
                        "VALUES (1, 40, 'high', 1, 1)")
            con.execute("INSERT INTO pending_topic (pending_id, topic_id, priority_band, curated) "
                        "VALUES (2, 41, 'low', 1)")
            con.execute("INSERT INTO topic_link (topic_a, topic_b, relation) VALUES (40, 50, 'related')")
        con.execute("INSERT INTO pending_topic (pending_id, topic_id, priority_score, curated) "
                    "VALUES (1, 50, 0.5, 0)")
        for sql in extra:
            con.execute(sql)
        con.commit()
        con.close()

    def topics(self):
        con = sqlite3.connect(self.db)
        try:
            return con.execute("SELECT * FROM topic ORDER BY id").fetchall()
        finally:
            con.close()

    def without_topic(self, hashes):
        return {k: v for k, v in hashes.items() if k != "topic"}

    def test_critico_base_v2_con_raiz_cliente_renombra_y_lo_demas_queda_igual(self):
        self.v2_db()
        before, topics_before = table_hashes(self.db), self.topics()
        con = self.connect()
        self.assertIsNotNone(con)
        self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        con.close()
        self.assertEqual(self.version(), (3, 3))
        self.assertEqual(self.without_topic(table_hashes(self.db)), self.without_topic(before))
        cols = columns(self.db, "topic")
        renamed = list([r for r in topics_before if r[0] == 33][0])
        renamed[cols.index("slug")], renamed[cols.index("name")] = "proyecto", "Proyecto"
        self.assertEqual(self.topics(), [tuple(renamed) if r[0] == 33 else r for r in topics_before])
        self.assertEqual(renamed[cols.index("keywords")], "cliente", "solo cambian slug y name")

    def test_descripcion_del_seed_se_renombra_y_la_escrita_a_mano_se_conserva(self):
        """La descripción que puso el seed ('Raíz del eje cliente (…)') pasa a la de 'proyecto'; otra se queda."""
        for desc, esperada in (("Raíz del eje cliente (contenedor; no es un tema)",
                                "Raíz del eje proyecto (contenedor; no es un tema)"),
                               ("mi nota", "mi nota")):
            with self.subTest(desc=desc):
                if os.path.exists(self.db):
                    os.remove(self.db)
                    shutil.rmtree(_migrations.backup_dir(self.db), ignore_errors=True)
                self.v2_db(extra=(f"UPDATE topic SET description = '{desc}' WHERE id = 33",))
                self.connect().close()
                con = sqlite3.connect(self.db)
                try:
                    self.assertEqual(con.execute("SELECT slug, description FROM topic WHERE id = 33").fetchone(),
                                     ("proyecto", esperada))
                finally:
                    con.close()

    def test_critico_respaldo_previo_con_la_raiz_cliente_y_constancia(self):
        self.v2_db()
        self.connect().close()
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].startswith("neb.pre-paso-3."), backups)
        bak = os.path.join(_migrations.backup_dir(self.db), backups[0])
        con = sqlite3.connect(self.db)
        row = con.execute("SELECT min_code, title, backup FROM schema_step WHERE step = 3").fetchone()
        con.close()
        self.assertEqual(row, (3, "eje proyecto (7.3.0)", bak))
        con = sqlite3.connect(bak)
        try:
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(con.execute("SELECT slug, name FROM topic WHERE id = 33").fetchone(),
                             ("cliente", "Cliente"))
            self.assertEqual(_migrations.read_version(con), (2, 2))
        finally:
            con.close()

    def test_critico_base_v2_de_700_conserva_el_respaldo_del_paso_2_junto_al_del_paso_3(self):
        """Una base que 7.0.0 llevó de la versión 1 a la 2 guarda su neb.pre-paso-2 (la única copia con las
        columnas de equipo). El paso 3 respalda aunque no haya raíz 'cliente', y la poda es por paso: el
        neb.pre-paso-2 sobrevive y la fila del paso 2 en schema_step sigue apuntando a él (tooling/migrations.md
        § "Paso 3: eje proyecto")."""
        legacy_647_db(self.db)
        self.connect([STEP1]).close()
        self.connect(STEPS_7_2).close()
        self.assertEqual(self.version(), (2, 2))
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].startswith("neb.pre-paso-2."), backups)
        con = sqlite3.connect(self.db)
        try:
            self.assertIsNone(con.execute("SELECT 1 FROM topic WHERE slug = 'cliente'").fetchone())
            paso2 = con.execute("SELECT backup FROM schema_step WHERE step = 2").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(paso2, os.path.join(_migrations.backup_dir(self.db), backups[0]))
        self.connect().close()
        self.assertEqual(self.version(), (3, 3))
        backups = self.backups()
        self.assertEqual(len(backups), 2, backups)
        self.assertEqual(os.path.join(_migrations.backup_dir(self.db), backups[0]), paso2)
        self.assertTrue(backups[1].startswith("neb.pre-paso-3."), backups)
        con = sqlite3.connect(self.db)
        try:
            self.assertEqual(con.execute("SELECT backup FROM schema_step WHERE step = 2").fetchone()[0], paso2)
        finally:
            con.close()
        self.assertTrue(os.path.exists(paso2), "la poda conserva el respaldo de 7.0.0")

    def test_base_nueva_no_hace_nada(self):
        con = self.connect()
        self.assertIsNotNone(con)
        self.assertEqual(con.execute("SELECT count(*) FROM topic").fetchone()[0], 0)
        con.close()
        self.assertEqual(self.version(), (3, 3))
        self.assertEqual(self.backups(), [])

    def test_critico_solo_sentinel_y_temas_planos_no_hace_nada_ni_bloquea(self):
        self.connect(STEPS_7_2).close()
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO topic (id, slug, name) VALUES (1, 'sin-clasificar', 'Sin clasificar')")
        con.execute("INSERT INTO topic (id, slug, name) VALUES (2, 'ventas', 'Ventas')")
        con.execute("INSERT INTO topic (id, slug, name) VALUES (3, 'infra', 'Infra')")
        con.execute("INSERT INTO topic (id, slug, name, parent_id) VALUES (4, 'cliente', 'Cliente', 3)")
        con.execute("INSERT INTO pending (id, context_origin, created_at, slug) VALUES (1, 'uno', 't', 'uno')")
        con.execute("INSERT INTO pending_topic (pending_id, topic_id, curated) VALUES (1, 1, 0)")
        con.commit()
        con.close()
        before = table_hashes(self.db)
        con = self.connect()
        self.assertIsNotNone(con, "no bloquea")
        con.close()
        self.assertEqual(self.version(), (3, 3))
        self.assertEqual(table_hashes(self.db), before, "un 'cliente' que no es raíz no se toca")

    def test_tema_proyecto_sin_raiz_cliente_no_bloquea(self):
        self.v2_db(cliente=False, extra=("INSERT INTO topic (id, slug, name) VALUES (70, 'proyecto', 'Proyecto')",))
        before = table_hashes(self.db)
        self.connect().close()
        self.assertEqual(self.version(), (3, 3))
        self.assertEqual(table_hashes(self.db), before)

    def test_critico_falla_sembrada_hijo_proyecto_detiene_el_paso_sin_cambiar_nada(self):
        self.v2_db(extra=("INSERT INTO topic (id, slug, name, parent_id) VALUES (51, 'proyecto', 'Proyecto', 34)",
                          "INSERT INTO topic (id, slug, name) VALUES (52, 'proyecto-51', 'Ocupado')"))
        before = table_hashes(self.db)
        with self.assertRaises(_migrations.DbUnavailable) as cm:
            self.connect()
        e = cm.exception
        self.assertEqual(e.motivo, "paso-bloqueado")
        self.assertIn("paso de base 3", e.detalle)
        self.assertIn("topic id 51, hijo de 'topico'", e.detalle)
        self.assertIn("UPDATE topic SET slug='proyecto-51-2' WHERE id=51;", e.detalle, "propone un slug libre")
        self.assertIn("No se cambió nada", e.detalle)
        self.assertIn("«- **Temas:**» de ~/.claude/compas.md", e.detalle, "avisa que el slug se cita en compas.md")
        self.assertEqual(table_hashes(self.db), before)
        self.assertEqual(self.version(), (2, 2))
        self.assertEqual(self.backups(), [], "el precheck corre antes del respaldo")
        con = _migrations.open_readonly(self.db)
        try:
            self.assertEqual(_migrations.read_errors(con), [], "el motivo de un precheck no se guarda")
            report = _migrations.blocked_report(con)
        finally:
            con.close()
        self.assertEqual([(n, t) for n, t, _m in report], [(3, "eje proyecto (7.3.0)")])
        self.assertIn("UPDATE topic SET slug='proyecto-51-2' WHERE id=51;", report[0][2])
        con = sqlite3.connect(self.db)
        con.execute("UPDATE topic SET slug='proyecto-51-2' WHERE id=51")
        con.commit()
        con.close()
        self.connect().close()
        self.assertEqual(self.version(), (3, 3))
        topics = {r[0]: r[1] for r in self.topics()}
        self.assertEqual((topics[33], topics[51]), ("proyecto", "proyecto-51-2"))

    def test_tema_proyecto_creado_tras_el_precheck_revierte_y_se_reintenta(self):
        self.v2_db()
        before = table_hashes(self.db)
        real = _migrations.STEPS[2]
        db = self.db

        def precheck(con):
            motivo = real.precheck(con)
            otro = sqlite3.connect(db)
            otro.execute("INSERT INTO topic (id, slug, name) VALUES (80, 'proyecto', 'Tarde')")
            otro.commit()
            otro.close()
            return motivo
        paso3 = Step(3, real.titulo, real.aplicar, min_code=real.min_code, destructivo=real.destructivo,
                     espera=real.espera, precheck=precheck)
        with self.assertRaises(_migrations.DbUnavailable) as cm:
            self.connect(STEPS_7_2 + (paso3,))
        self.assertIn("topic id 80", cm.exception.detalle)
        self.assertIn("el paso se reintenta", cm.exception.detalle)
        self.assertEqual(self.version(), (2, 2))
        self.assertEqual(self.backups(), [], "el respaldo del intento revertido se borra")
        con = sqlite3.connect(self.db)
        try:
            errors = _migrations.read_errors(con)
            self.assertEqual(con.execute("SELECT slug FROM topic WHERE id = 33").fetchone()[0], "cliente")
        finally:
            con.close()
        self.assertEqual([r[0] for r in errors], [3])
        self.assertIn("topic id 80", errors[0][3])
        self.assertEqual(self.without_topic(table_hashes(self.db)), self.without_topic(before))
        con = sqlite3.connect(self.db)
        con.execute("DELETE FROM topic WHERE id = 80")
        con.commit()
        con.close()
        self.connect(retry=True).close()
        self.assertEqual(self.version(), (3, 3))
        con = sqlite3.connect(self.db)
        try:
            self.assertEqual(_migrations.read_errors(con), [])
            self.assertEqual(con.execute("SELECT slug FROM topic WHERE id = 33").fetchone()[0], "proyecto")
        finally:
            con.close()

    def test_critico_idempotente_la_segunda_conexion_no_hace_nada(self):
        self.v2_db()
        self.connect().close()
        after, backups = table_hashes(self.db), self.backups()
        con = sqlite3.connect(self.db)
        sv = con.execute("PRAGMA schema_version").fetchone()[0]
        con.close()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            con = _db_shared._connect(self.db, SCHEMA)
        self.assertIsNotNone(con)
        con.close()
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(table_hashes(self.db), after)
        self.assertEqual(self.backups(), backups, "sin respaldo nuevo")
        con = sqlite3.connect(self.db)
        try:
            self.assertEqual(con.execute("PRAGMA schema_version").fetchone()[0], sv)
            self.assertEqual(con.execute("SELECT count(*) FROM schema_step WHERE step = 3").fetchone()[0], 1)
        finally:
            con.close()

    def test_aplicar_sin_raiz_cliente_no_escribe(self):
        """Relectura dentro del candado: si la raíz ya no está (otro proceso la renombró), aplicar no hace nada.
        El tema 'proyecto' (la raíz que dejó el otro proceso) hace que, sin esa guarda, aplicar lance por choque
        de slug en vez de salir sin escribir."""
        self.v2_db(cliente=False,
                   extra=("INSERT INTO topic (id, slug, name) VALUES (70, 'proyecto', 'Proyecto')",))
        con = sqlite3.connect(self.db)
        con.isolation_level = None
        con.execute("BEGIN IMMEDIATE")
        try:
            before = con.total_changes
            _migrations.STEPS[2].aplicar(_migrations._StepConnection(con))
            self.assertEqual(con.total_changes, before)
        finally:
            con.execute("ROLLBACK")
            con.close()

    def test_un_codigo_7_2_no_opera_la_base_migrada(self):
        self.v2_db()
        self.connect().close()
        with self.assertRaises(_migrations.IncompatibleDb) as cm:
            self.connect(STEPS_7_2)
        self.assertIn("pide al menos la 3", cm.exception.detalle)


if __name__ == "__main__":
    unittest.main()
