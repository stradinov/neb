#!/usr/bin/env python3
"""
test_logbook_migracion_team.py — base única y retiro del esquema de equipo (neb 7.0.0).

Cubre:
  • Resolvedor único: resolve_db_path devuelve siempre <home>/.claude/neb.db.
  • Guarda del nombre anterior (open_default_db / unmigrated_legacy): con neb-logbook.db poblado y sin un
    neb.db usable no se crea nada y se responde base-sin-migrar con la migración guiada (`accion`) y el
    migrador (`comando`); una base bloqueada no cuenta como sin migrar. También por subproceso
    (`logbook.py list`, `logbook.py trace <x>`) y de punta a punta por el hook (`neb-hook.py logbook-sync`
    y, en Windows, `logbook-sync.ps1`).
  • Las entradas del hook (neb-hook.py, logbook-sync.ps1 y logbook-sync.sh) quedan en silencio (stdout
    vacío, rc 0, sin base) con un payload sin transcript_path o sin hook_event_name.
  • Paso de base 2 (hooks/lib/_migrations.py) sobre una base 6.45.0 (su DDL es el esquema inicial): salen
    las 19 columnas, los 2 índices y la tabla event, con respaldo verificado; el esquema queda igual al de
    una base nueva; los datos que se conservan no cambian; una segunda conexión no escribe DDL. Todo o nada:
    un SQLite anterior a 3.35.5 (simulado) o un objeto del usuario sobre lo retirado detienen el paso en su
    precheck sin borrar nada, con la conexión y la captura funcionando, y el motivo dice el requisito o
    nombra cada objeto y cómo quitarlo; un objeto creado entre el precheck y aplicar revierte el paso, que
    se reintenta. Candado ocupado, concurrencia entre procesos, candado ajeno sobre una base ya migrada y
    journal_mode=DELETE.
  • _add_missing_columns: tolera la carrera «duplicate column name» y propaga cualquier otro error.

Invariantes: DBs y homes temporales (tempfile); nunca ~/.claude; ningún test hace red.
Framework: unittest (stdlib).
  py -m unittest tests.test_logbook_migracion_team
"""

import hashlib
import io
import json
import os
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
NEB_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, LIB)

import _db_shared
import _migrations
import logbook

sys.path.insert(0, HERE)
from test_neb_root import BASH

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
HOOK = os.path.join(HERE, "..", "neb-hook.py")
PS1 = os.path.join(HERE, "..", "logbook-sync.ps1")
SH = os.path.join(HERE, "..", "logbook-sync.sh")
STEP1 = _migrations.STEPS[0]


RETIRED_WORK = ("owner", "lock_state", "takeover_by", "locked_at", "payload_version", "origin_dev", "dirty",
                "synced_at", "remote_id", "conflict", "last_error", "last_error_at", "transcript_error",
                "transcript_error_at")
RETIRED_SESSION = ("work_id", "synced_byte", "transcript_error", "transcript_error_at", "root_cwd")
RETIRED_INDEXES = ("idx_work_dirty", "idx_session_sync_work")
KEPT_WORK = ("id", "mode", "project", "req_slug", "req_state", "branch", "head_commit", "repo_path",
             "change_md", "payload_json", "origin_machine", "claude_session_id", "claude_session_name",
             "transcript_path", "created_at", "updated_at", "archived_at")
KEPT_SESSION = ("session_id", "transcript_path", "updated_at", "read_byte")
KEPT_TABLES = ("pending", "pending_note", "pending_link", "pending_topic", "topic", "topic_link",
               "req_link", "req_repo", "req_session")


def _child_env(home, **extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("NEB_") and k not in ("PYTHONUTF8", "CLAUDE_PLUGIN_ROOT",
                                                     "CLAUDE_PREPROCESS_RECURSION")}
    env.update(HOME=home, USERPROFILE=home, PYTHONIOENCODING="utf-8")
    env.update(extra)
    return env


def _home():
    h = tempfile.mkdtemp(prefix="neb-test-team-")
    os.makedirs(os.path.join(h, ".claude"))
    return h


def _base_645(path, journal=None):
    """Base de 6.45.0 (su DDL es el esquema inicial, sin tabla de versión) con datos en todas sus tablas,
    incluidas las columnas y la tabla retiradas."""
    raw = sqlite3.connect(path)
    with open(SCHEMA, encoding="utf-8") as fh:
        raw.executescript(fh.read())
    # Una base 6.45.0 real ya pasó por el _migrate de 6.45.0, que crea este índice.
    raw.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_slug ON pending(slug) WHERE slug IS NOT NULL")
    if journal:
        raw.execute(f"PRAGMA journal_mode={journal}")
    raw.execute(
        "INSERT INTO work (id, mode, project, req_slug, owner, lock_state, takeover_by, locked_at, req_state, "
        "branch, head_commit, repo_path, change_md, payload_json, payload_version, origin_dev, origin_machine, "
        "claude_session_id, claude_session_name, transcript_path, created_at, updated_at, archived_at, dirty, "
        "synced_at, remote_id, conflict, last_error, last_error_at, transcript_error, transcript_error_at) "
        "VALUES (1,'req','host/o/repo','mi-req','dev','takeover_requested','otro','t0','En progreso','main',"
        "'abc','C:\\repo','changes/x.md','{\"plan\":\"p\"}',3,'dev','maq','S1','nombre','C:\\t\\S1.jsonl',"
        "'2026-01-01','2026-01-02',NULL,1,'t1',501,1,'publish 409','t2','tx','t3')")
    raw.execute(
        "INSERT INTO work (id, mode, payload_json, origin_machine, claude_session_id, transcript_path, "
        "created_at, updated_at, archived_at) VALUES (2,'exploratory','{\"summary\":\"hola\"}','maq','S2',"
        "NULL,'2026-01-03','2026-01-04','2026-02-01')")
    for wid, action in ((1, "publish"), (1, "claim"), (2, "archive")):
        raw.execute("INSERT INTO event (work_id, ts, dev, action, prev_owner, machine, note) "
                    "VALUES (?, 't', 'dev', ?, 'x', 'maq', 'n')", (wid, action))
    raw.execute("INSERT INTO session_sync (session_id, work_id, transcript_path, synced_byte, transcript_error, "
                "transcript_error_at, updated_at, root_cwd, read_byte) "
                "VALUES ('S1', 1, 'C:\\t\\S1.jsonl', 40, 'e', 't', 't', 'C:\\repo', 900)")
    raw.execute("INSERT INTO session_sync (session_id, updated_at, read_byte) VALUES ('S2', 't', 12)")
    raw.execute("INSERT INTO pending (id, type, context_origin, status, work_ref, created_at) "
                "VALUES (1, 'task', 'ligado al REQ', 'open', 1, 't')")
    raw.execute("INSERT INTO pending (id, type, context_origin, status, session_ref, created_at) "
                "VALUES (2, 'session', 'sesión pausada', 'open', 2, 't')")
    raw.execute("INSERT INTO pending_note (pending_id, note, ts) VALUES (1, 'nota', 't')")
    raw.execute("INSERT INTO pending_link (a, b, relation) VALUES (1, 2, 'related')")
    raw.execute("INSERT INTO topic (id, slug, name) VALUES (1, 'cliente', 'Cliente')")
    raw.execute("INSERT INTO topic (id, slug, name, parent_id) VALUES (2, 'alpha', 'Alpha', 1)")
    raw.execute("INSERT INTO topic_link (topic_a, topic_b, relation) VALUES (1, 2, 'related')")
    raw.execute("INSERT INTO pending_topic (pending_id, topic_id, priority_band, is_primary) VALUES (1, 2, 'high', 1)")
    raw.execute("INSERT INTO req_link (id, project, nombre, fecha, change_md, linked_by, created_at, updated_at) "
                "VALUES (1, 'host/o/repo', 'mi-req', '2026-01-01', 'changes/2026-01-01-mi-req.md', 'cli', 't', 't')")
    raw.execute("INSERT INTO req_repo (req_id, common_dir, path, project) VALUES (1, 'c:\\repo\\.git', 'C:\\repo', 'p')")
    raw.execute("INSERT INTO req_session (req_id, session_id, via, first_seen_at, last_seen_at) "
                "VALUES (1, 'S1', 'write', 't', 't')")
    raw.commit()
    raw.close()
    return path


def _legacy_home(populated=True):
    """Home con ~/.claude/neb-logbook.db (base 6.45.0 poblada) y sin neb.db."""
    home = _home()
    legacy = os.path.join(home, ".claude", "neb-logbook.db")
    if populated:
        _base_645(legacy)
    else:
        open(legacy, "wb").close()
    return home, legacy, os.path.join(home, ".claude", "neb.db")


def _connect_quiet(path):
    err = io.StringIO()
    with mock.patch.object(sys, "stderr", err):
        con = _db_shared._connect(path, SCHEMA)
    return con, err.getvalue()


def _table_info(con, table):
    return [tuple(r) for r in con.execute(f"PRAGMA table_info({table})")]


def _index_shape(con, table):
    out = []
    for _seq, name, unique, origin, partial in con.execute(f"PRAGMA index_list({table})"):
        cols = tuple(r[2] for r in con.execute(f"PRAGMA index_info({name})"))
        out.append((name, unique, origin, partial, cols))
    return sorted(out)


def _schema_shape(con):
    """Forma del esquema comparable entre una base migrada y una nueva (el texto del CREATE no cuenta)."""
    names = sorted((r[0], r[1]) for r in con.execute(
        "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
    tables = [n for t, n in names if t == "table"]
    return names, {t: (_table_info(con, t), _index_shape(con, t)) for t in tables}


def _fresh_shape():
    d = tempfile.mkdtemp(prefix="neb-test-fresh-")
    con = _db_shared._connect(os.path.join(d, "neb.db"), SCHEMA)
    try:
        return _schema_shape(con)
    finally:
        con.close()


def _hashes(path):
    """Hash por tabla de las columnas que se conservan."""
    c = sqlite3.connect(path)
    try:
        out = {}
        for table, cols in (("work", KEPT_WORK), ("session_sync", KEPT_SESSION)):
            rows = c.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY 1").fetchall()
            out[table] = hashlib.sha256(repr(rows).encode()).hexdigest()
        for table in KEPT_TABLES:
            rows = c.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            out[table] = hashlib.sha256(repr(rows).encode()).hexdigest()
        return out
    finally:
        c.close()


def _schema_version(path):
    c = sqlite3.connect(path)
    try:
        return c.execute("PRAGMA schema_version").fetchone()[0]
    finally:
        c.close()


def _schema_step_version(path):
    c = sqlite3.connect(path)
    try:
        return _migrations.read_version(c)
    finally:
        c.close()


def _jsonl(path, text="hola"):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {"content": text}}) + "\n")
    return path


# =========================================================================== resolvedor y guarda

class TestResolvedorUnico(unittest.TestCase):

    def test_siempre_neb_db_con_o_sin_la_base_anterior(self):
        home, legacy, newp = _legacy_home()
        self.assertEqual(_db_shared.resolve_db_path(home), newp)
        open(newp, "wb").close()
        self.assertEqual(_db_shared.resolve_db_path(home), newp)
        self.assertEqual(_db_shared.resolve_db_path(_home()).rsplit(os.sep, 2)[-2:], [".claude", "neb.db"])


class TestGuarda(unittest.TestCase):

    def _assert_unmigrated(self, home, legacy, newp, newp_bytes):
        size = os.path.getsize(legacy)
        with self.assertRaises(_db_shared.UnmigratedDb) as cm:
            _db_shared.open_default_db(home)
        e = cm.exception
        self.assertIsInstance(e, _db_shared.DbUnavailable)
        self.assertEqual(e.motivo, "base-sin-migrar")
        self.assertIn(legacy, e.detalle)
        self.assertIn("/neb:migrate", e.accion)
        self.assertIn("7.0.0:renombrar-base", e.accion)
        self.assertIn("migrate-neb-db.py", e.comando)
        self.assertEqual(os.path.getsize(legacy), size)
        if newp_bytes is None:
            self.assertFalse(os.path.exists(newp))
        else:
            with open(newp, "rb") as fh:
                self.assertEqual(fh.read(), newp_bytes)
        self.assertEqual(sorted(os.listdir(os.path.dirname(legacy))),
                         sorted(["neb-logbook.db"] + ([] if newp_bytes is None else ["neb.db"])))
        return e

    def test_critico_solo_la_base_anterior_no_crea_neb_db(self):
        home, legacy, newp = _legacy_home()
        e = self._assert_unmigrated(home, legacy, newp, None)
        self.assertNotIn("mueve fuera", e.detalle)
        self.assertIsInstance(_db_shared.unmigrated_legacy(home), _db_shared.UnmigratedDb)

    def test_neb_db_de_0_bytes_al_lado_tampoco(self):
        home, legacy, newp = _legacy_home()
        open(newp, "wb").close()
        e = self._assert_unmigrated(home, legacy, newp, b"")
        self.assertNotIn("mueve fuera", e.detalle)

    def test_neb_db_no_vacio_sin_tabla_work_pide_moverlo(self):
        home, legacy, newp = _legacy_home()
        c = sqlite3.connect(newp)
        c.execute("CREATE TABLE foo (x)")
        c.commit()
        c.close()
        with open(newp, "rb") as fh:
            before = fh.read()
        e = self._assert_unmigrated(home, legacy, newp, before)
        self.assertIn("mueve fuera", e.detalle)
        self.assertIn(f"({len(before)} bytes)", e.detalle)
        self.assertIn(os.path.dirname(newp), e.detalle)

    def test_neb_db_que_no_es_una_base_pide_moverlo(self):
        home, legacy, newp = _legacy_home()
        data = b"esto no es una base SQLite" * 40
        with open(newp, "wb") as fh:
            fh.write(data)
        e = self._assert_unmigrated(home, legacy, newp, data)
        self.assertIn("mueve fuera", e.detalle)
        self.assertIn(f"({len(data)} bytes)", e.detalle)

    def test_ninguna_de_las_dos_crea_neb_db(self):
        home = _home()
        con = _db_shared.open_default_db(home)
        self.assertIsNotNone(con)
        con.close()
        self.assertTrue(_db_shared._is_usable_db(os.path.join(home, ".claude", "neb.db")))
        self.assertIsNone(_db_shared.unmigrated_legacy(home))

    def test_base_anterior_vacia_no_bloquea(self):
        home, _legacy, newp = _legacy_home(populated=False)
        self.assertIsNone(_db_shared.unmigrated_legacy(home))
        _db_shared.open_default_db(home).close()
        self.assertTrue(_db_shared._is_usable_db(newp))

    def test_neb_db_usable_se_abre_aunque_quede_la_base_anterior(self):
        home, _legacy, newp = _legacy_home()
        _db_shared._connect(newp, SCHEMA).close()
        self.assertIsNone(_db_shared.unmigrated_legacy(home))
        con = _db_shared.open_default_db(home)
        self.assertEqual(con.execute("SELECT count(*) FROM work").fetchone()[0], 0)
        con.close()

    def test_base_bloqueada_no_cuenta_como_sin_migrar(self):
        home, _legacy, newp = _legacy_home()
        c = sqlite3.connect(newp)
        c.execute("CREATE TABLE work (id INTEGER PRIMARY KEY)")      # journal_mode=DELETE por omisión
        c.commit()
        c.close()
        locker = sqlite3.connect(newp, isolation_level=None)
        self.addCleanup(locker.close)
        locker.execute("BEGIN EXCLUSIVE")
        self.assertEqual(_db_shared._probe_db(newp), "bloqueada")
        self.assertIsNone(_db_shared.unmigrated_legacy(home))


class TestGuardaCli(unittest.TestCase):
    """JSON de base sin migrar por subproceso: motivo base-sin-migrar (no «error»), las claves `accion` y
    `comando`, y sin crear neb.db."""

    def _run(self, home, *args):
        r = subprocess.run([sys.executable, os.path.join(LIB, "logbook.py")] + list(args), capture_output=True,
                           env=_child_env(home, NEB_HOME=NEB_ROOT), timeout=60)
        self.assertEqual(r.returncode, 0)
        return r

    def _check(self, home, legacy, newp, *args):
        size = os.path.getsize(legacy)
        out = json.loads(self._run(home, *args).stdout.decode("utf-8"))
        self.assertEqual(out["ok"], False)
        self.assertEqual(out["motivo"], "base-sin-migrar")
        self.assertIn(legacy, out["detalle"])
        self.assertIn("migrate-neb-db.py", out["comando"])
        self.assertIn("/neb:migrate", out["accion"])
        self.assertEqual(list(out), ["ok", "motivo", "detalle", "accion", "comando"])
        self.assertFalse(os.path.exists(newp))
        self.assertEqual(os.path.getsize(legacy), size)

    def test_critico_list(self):
        self._check(*_legacy_home(), "list")

    def test_critico_trace_por_subproceso(self):
        self._check(*_legacy_home(), "trace", "mi-req")

    def test_show_rename_archive_unlink(self):
        home, legacy, newp = _legacy_home()
        for args in (("show", "1"), ("rename", "1", "otro"), ("archive", "1"), ("unlink", "mi-req")):
            with self.subTest(args=args):
                self._check(home, legacy, newp, *args)

    def test_un_verbo_retirado_se_atiende_antes_que_la_guarda(self):
        home, _legacy, newp = _legacy_home()
        out = json.loads(self._run(home, "claim", "1").stdout.decode("utf-8"))
        self.assertEqual(out["motivo"], "verbo-retirado")
        self.assertFalse(os.path.exists(newp))


class TestGuardaPuntaAPunta(unittest.TestCase):
    """Entrada real del hook con HOME y USERPROFILE temporales: la captura no crea neb.db ni toca la base
    anterior. El control positivo (sin base anterior) comprueba que el mismo camino sí captura."""

    def _payload(self, home):
        cwd = os.path.join(home, "repo")
        os.makedirs(cwd, exist_ok=True)
        t = _jsonl(os.path.join(home, "S-e2e.jsonl"))
        return json.dumps({"session_id": "S-e2e", "cwd": cwd, "transcript_path": t,
                           "hook_event_name": "Stop"}).encode("utf-8")

    def _neb_hook(self, home):
        subprocess.run([sys.executable, HOOK, "logbook-sync"], input=self._payload(home), capture_output=True,
                       env=_child_env(home, NEB_HOOKS="logbook-sync"), timeout=60)

    def _ps1(self, home):
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1],
                       input=self._payload(home), capture_output=True,
                       env=_child_env(home, NEB_HOME=NEB_ROOT), timeout=120)

    def _works(self, newp):
        c = sqlite3.connect(newp)
        try:
            return c.execute("SELECT mode, claude_session_id FROM work").fetchall()
        finally:
            c.close()

    def _check_guard(self, runner):
        home, legacy, newp = _legacy_home()
        st = os.stat(legacy)
        runner(home)
        self.assertFalse(os.path.exists(newp))
        st2 = os.stat(legacy)
        self.assertEqual((st2.st_size, st2.st_mtime_ns), (st.st_size, st.st_mtime_ns))

    def _check_control(self, runner):
        home = _home()
        newp = os.path.join(home, ".claude", "neb.db")
        runner(home)
        self.assertTrue(os.path.exists(newp))
        self.assertEqual(self._works(newp), [("exploratory", "S-e2e")])

    def test_critico_neb_hook_dispatch(self):
        self._check_guard(self._neb_hook)

    def test_neb_hook_dispatch_control_positivo(self):
        self._check_control(self._neb_hook)

    @unittest.skipUnless(sys.platform == "win32" and shutil.which("powershell"), "logbook-sync.ps1: solo Windows")
    def test_critico_logbook_sync_ps1(self):
        self._check_guard(self._ps1)

    @unittest.skipUnless(sys.platform == "win32" and shutil.which("powershell"), "logbook-sync.ps1: solo Windows")
    def test_logbook_sync_ps1_control_positivo(self):
        self._check_control(self._ps1)


class TestHookSinDatoEnSilencio(unittest.TestCase):
    """Entrada real del hook con un payload sin transcript_path o sin hook_event_name (ausente o vacío):
    stdout vacío, rc 0, sin captura y sin base. En PowerShell 5.1 un argumento vacío se descarta y logbook.py
    leería el session_id como subcomando del CLI, con su respuesta en el stdout del hook."""

    FALTANTES = (("sin transcript_path", "transcript_path", None), ("transcript_path vacío", "transcript_path", ""),
                 ("sin hook_event_name", "hook_event_name", None), ("hook_event_name vacío", "hook_event_name", ""))

    def _payload(self, home, campo=None, valor=None):
        cwd = os.path.join(home, "repo")
        os.makedirs(cwd, exist_ok=True)
        ev = {"session_id": "S-e2e", "cwd": cwd, "transcript_path": _jsonl(os.path.join(home, "S-e2e.jsonl")),
              "hook_event_name": "Stop"}
        if campo:
            if valor is None:
                del ev[campo]
            else:
                ev[campo] = valor
        return json.dumps(ev).encode("utf-8")

    def _neb_hook(self, home, payload):
        return subprocess.run([sys.executable, HOOK, "logbook-sync"], input=payload, capture_output=True,
                              env=_child_env(home, NEB_HOOKS="logbook-sync"), timeout=60)

    def _ps1(self, home, payload):
        return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1],
                              input=payload, capture_output=True, env=_child_env(home, NEB_HOME=NEB_ROOT),
                              timeout=120)

    def _sh(self, home, payload):
        return subprocess.run([BASH, SH], input=payload, capture_output=True,
                              env=_child_env(home, NEB_HOME=NEB_ROOT), timeout=60)

    def _check_silencio(self, runner):
        for nombre, campo, valor in self.FALTANTES:
            with self.subTest(caso=nombre):
                home = _home()
                r = runner(home, self._payload(home, campo, valor))
                self.assertEqual(r.stdout, b"")
                self.assertEqual(r.returncode, 0)
                self.assertFalse(os.path.exists(os.path.join(home, ".claude", "neb.db")))

    def _check_control(self, runner):
        home = _home()
        r = runner(home, self._payload(home))
        self.assertEqual(r.stdout, b"")
        self.assertEqual(r.returncode, 0)
        c = sqlite3.connect(os.path.join(home, ".claude", "neb.db"))
        try:
            self.assertEqual(c.execute("SELECT claude_session_id FROM work").fetchall(), [("S-e2e",)])
        finally:
            c.close()

    def test_critico_neb_hook_sin_dato_en_silencio(self):
        self._check_silencio(self._neb_hook)

    def test_neb_hook_payload_completo_captura(self):
        self._check_control(self._neb_hook)

    @unittest.skipUnless(sys.platform == "win32" and shutil.which("powershell"), "logbook-sync.ps1: solo Windows")
    def test_critico_logbook_sync_ps1_sin_dato_en_silencio(self):
        self._check_silencio(self._ps1)

    @unittest.skipUnless(sys.platform == "win32" and shutil.which("powershell"), "logbook-sync.ps1: solo Windows")
    def test_logbook_sync_ps1_payload_completo_captura(self):
        self._check_control(self._ps1)

    @unittest.skipUnless(BASH and shutil.which("jq"), "logbook-sync.sh: requiere bash y jq")
    def test_critico_logbook_sync_sh_sin_dato_en_silencio(self):
        self._check_silencio(self._sh)

    @unittest.skipUnless(BASH and shutil.which("jq"), "logbook-sync.sh: requiere bash y jq")
    def test_logbook_sync_sh_payload_completo_captura(self):
        self._check_control(self._sh)

    def _check_otro_evento(self, runner):
        home = _home()
        r = runner(home, self._payload(home, "hook_event_name", "SubagentStop"))
        self.assertEqual(r.stdout, b"")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(home, ".claude", "neb.db")))

    @unittest.skipUnless(sys.platform == "win32" and shutil.which("powershell"), "logbook-sync.ps1: solo Windows")
    def test_logbook_sync_ps1_registrado_en_otro_evento_calla(self):
        self._check_otro_evento(self._ps1)

    @unittest.skipUnless(BASH and shutil.which("jq"), "logbook-sync.sh: requiere bash y jq")
    def test_logbook_sync_sh_registrado_en_otro_evento_calla(self):
        self._check_otro_evento(self._sh)


class TestCapturaSinMigrar(unittest.TestCase):

    def test_captura_en_proceso_avisa_y_no_crea_nada(self):
        home, legacy, newp = _legacy_home()
        cwd = os.path.join(home, "repo")
        os.makedirs(cwd)
        t = _jsonl(os.path.join(home, "S.jsonl"))
        err = io.StringIO()
        argv = ["logbook.py", "S", cwd, t, "Stop", NEB_ROOT, home]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(sys, "stderr", err):
            logbook.main()
        self.assertFalse(os.path.exists(newp))
        self.assertIn("[logbook] captura omitida (base-sin-migrar): La bitácora sigue con el nombre anterior",
                      err.getvalue())


# =========================================================================== paso de base 2: retiro del esquema de equipo

class _Paso2(unittest.TestCase):
    """Base de 6.45.0 (esquema inicial, con las columnas, los índices y la tabla que 7.0.0 retira) en un home
    temporal, para el paso de base 2 a través de _connect y de la API de pasos."""

    def setUp(self):
        self.home = _home()
        self.path = _base_645(os.path.join(self.home, ".claude", "neb.db"))

    def _raw(self, *sqls):
        c = sqlite3.connect(self.path)
        for s in sqls:
            c.execute(s)
        c.commit()
        c.close()

    def _cols(self, con, table):
        return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]

    def _nombres(self, con):
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master")}

    def _version(self):
        return _schema_step_version(self.path)

    def _backups(self):
        folder = _migrations.backup_dir(self.path)
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def _detenido(self):
        """Motivo con que status y el arranque ven detenido el paso 2 (blocked_report, solo lectura)."""
        con = _migrations.open_readonly(self.path)
        try:
            return {n: m for n, _t, m in _migrations.blocked_report(con)}.get(2)
        finally:
            con.close()

    def _errores(self):
        c = sqlite3.connect(self.path)
        try:
            return _migrations.read_errors(c)
        finally:
            c.close()

    def assert_intacta(self, con):
        """Nada del esquema retirado se borró."""
        self.assertTrue(set(RETIRED_WORK) <= set(self._cols(con, "work")))
        self.assertTrue(set(RETIRED_SESSION) <= set(self._cols(con, "session_sync")))
        self.assertTrue({"event", *RETIRED_INDEXES} <= self._nombres(con))

    def assert_como_nueva(self):
        con, err = _connect_quiet(self.path)
        try:
            self.assertEqual(self._version(), (2, 2), err)
            self.assertEqual(self._cols(con, "work"), list(KEPT_WORK))
            self.assertEqual(self._cols(con, "session_sync"), list(KEPT_SESSION))
            self.assertFalse({"event", *RETIRED_INDEXES} & self._nombres(con))
        finally:
            con.close()


class TestMigracion645(_Paso2):

    def test_critico_salen_columnas_indices_y_event_y_el_esquema_queda_como_uno_nuevo(self):
        antes = _hashes(self.path)
        con, err = _connect_quiet(self.path)
        self.assertIsNotNone(con, err)
        self.assertEqual(err, "")
        work_cols = [r[1] for r in con.execute("PRAGMA table_info(work)")]
        sess_cols = [r[1] for r in con.execute("PRAGMA table_info(session_sync)")]
        self.assertEqual(work_cols, list(KEPT_WORK))
        self.assertEqual(sess_cols, list(KEPT_SESSION))
        nombres = self._nombres(con)
        self.assertFalse(set(RETIRED_INDEXES) & nombres)
        self.assertNotIn("event", nombres)
        self.assertNotIn("idx_event_work", nombres)
        self.assertTrue({"uq_work_req", "uq_work_exploratory", "idx_work_active"} <= nombres)
        self.assertEqual(_schema_shape(con), _fresh_shape())
        self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        con.close()
        self.assertEqual(_hashes(self.path), antes)
        self.assertEqual(self._version(), (2, 2))

    def test_respaldo_verificado_con_lo_retirado_y_constancia_en_schema_step(self):
        _connect_quiet(self.path)[0].close()
        backups = self._backups()
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].startswith("neb.pre-paso-2."))
        bak = os.path.join(_migrations.backup_dir(self.path), backups[0])
        c = sqlite3.connect(self.path)
        row = c.execute("SELECT min_code, backup FROM schema_step WHERE step = 2").fetchone()
        c.close()
        self.assertEqual(row, (2, bak))
        with open(bak, "rb") as fh:
            self.assertEqual(fh.read(20)[18:20], b"\x01\x01", "el respaldo queda en un solo archivo (sin WAL)")
        c = sqlite3.connect(bak)
        try:
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertIn("owner", self._cols(c, "work"))
            self.assertEqual(c.execute("SELECT count(*) FROM event").fetchone()[0], 3)
        finally:
            c.close()

    def test_base_nueva_no_toma_respaldo(self):
        d = tempfile.mkdtemp(prefix="neb-test-nueva-")
        path = os.path.join(d, "neb.db")
        _db_shared._connect(path, SCHEMA).close()
        self.assertFalse(os.path.exists(_migrations.backup_dir(path)))
        self.assertEqual(_schema_step_version(path), (2, 2))

    def test_segunda_conexion_mismo_schema_version_y_sin_aviso(self):
        _connect_quiet(self.path)[0].close()
        v = _schema_version(self.path)
        con, err = _connect_quiet(self.path)
        self.assertIsNotNone(con)
        con.close()
        self.assertEqual(err, "")
        self.assertEqual(_schema_version(self.path), v)

    def test_los_datos_conservados_no_cambian(self):
        con, _ = _connect_quiet(self.path)
        con.close()
        c = sqlite3.connect(self.path)
        w = c.execute(f"SELECT {', '.join(KEPT_WORK)} FROM work WHERE id=1").fetchone()
        s = c.execute("SELECT session_id, transcript_path, read_byte FROM session_sync ORDER BY 1").fetchall()
        p = c.execute("SELECT id, work_ref, session_ref, status FROM pending ORDER BY id").fetchall()
        c.close()
        self.assertEqual(w, (1, "req", "host/o/repo", "mi-req", "En progreso", "main", "abc", "C:\\repo",
                             "changes/x.md", '{"plan":"p"}', "maq", "S1", "nombre", "C:\\t\\S1.jsonl",
                             "2026-01-01", "2026-01-02", None))
        self.assertEqual(s, [("S1", "C:\\t\\S1.jsonl", 900), ("S2", None, 12)])
        self.assertEqual(p, [(1, 1, None, "open"), (2, None, 2, "open")])

    def test_borrar_un_work_tras_migrar_respeta_las_llaves_foraneas(self):
        con, _ = _connect_quiet(self.path)
        con.execute("DELETE FROM work WHERE id=2")
        con.commit()
        self.assertIsNone(con.execute("SELECT session_ref FROM pending WHERE id=2").fetchone()[0])
        con.close()

    def test_columna_generada_que_nombra_locked_at_guarda_el_fallo(self):
        """El precheck no ve columnas generadas: el DROP COLUMN falla nombrando work.locked_at, y eso no es
        candado ocupado: el fallo se guarda (con su espera) y no hay respaldo en cada conexión."""
        self._raw("ALTER TABLE work ADD COLUMN sin_candado INTEGER "
                  "GENERATED ALWAYS AS (locked_at IS NULL) VIRTUAL")
        con, _err = _connect_quiet(self.path)
        con.close()
        self.assertEqual(self._version(), (1, 1))
        self.assertEqual([e[0] for e in self._errores()], [2])
        self.assertEqual(self._backups(), [])

    def test_candado_ocupado_la_conexion_sigue_en_la_version_1_y_se_reintenta(self):
        with mock.patch.object(_migrations, "STEPS", (STEP1,)):
            _connect_quiet(self.path)[0].close()
        locker = sqlite3.connect(self.path, isolation_level=None, timeout=0.1)
        locker.execute("BEGIN IMMEDIATE")
        locker.execute("UPDATE work SET origin_machine='otra' WHERE id=2")
        err = io.StringIO()
        try:
            with mock.patch.object(sys, "stderr", err):
                con = _db_shared._connect(self.path, SCHEMA)
            self.assertIsNotNone(con, err.getvalue())
            self.assertIn("paso de base 2", err.getvalue())
            self.assertFalse(con.in_transaction)
            self.assert_intacta(con)
            con.close()
        finally:
            locker.execute("COMMIT")
            locker.close()
        self.assertEqual(self._version(), (1, 1))
        self.assertEqual(self._backups(), [])
        self.assert_como_nueva()


class TestSqliteSinDropColumn(_Paso2):
    """D13: neb 7.0.0 pide SQLite 3.35.5 o superior. Con uno anterior (simulado) el precheck del paso 2 lo detiene
    con un motivo que dice el requisito y de dónde bajar un Python que lo trae: no se borra nada, no hay
    respaldo, la conexión y la captura siguen en la versión 1."""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(_migrations, "SQLITE_VERSION", (3, 35, 4))
        p.start()
        self.addCleanup(p.stop)

    def test_critico_no_borra_nada_y_el_motivo_dice_el_requisito(self):
        antes = _hashes(self.path)
        con, err = _connect_quiet(self.path)
        self.assertIsNotNone(con, err)
        self.assert_intacta(con)
        con.close()
        self.assertEqual(self._version(), (1, 1))
        self.assertEqual(self._backups(), [])
        self.assertEqual(self._errores(), [], "el motivo de un precheck no se guarda: se recalcula")
        motivo = self._detenido()
        self.assertIn("SQLite 3.35.5", motivo)
        self.assertIn("3.35.4", motivo)
        self.assertIn("https://www.python.org/downloads/", motivo)
        self.assertIn(motivo, err)
        self.assertEqual(_hashes(self.path), antes)

    def test_la_captura_inserta_con_la_base_en_la_version_1(self):
        cwd = os.path.join(self.home, "repo")
        os.makedirs(cwd)
        t = _jsonl(os.path.join(self.home, "S9.jsonl"), "tema nuevo")
        with mock.patch.object(sys, "argv", ["logbook.py", "S9", cwd, t, "Stop", NEB_ROOT, self.home]), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            logbook.main()
        c = sqlite3.connect(self.path)
        row = c.execute("SELECT mode, payload_json FROM work WHERE claude_session_id='S9'").fetchone()
        sess = c.execute("SELECT transcript_path, read_byte FROM session_sync WHERE session_id='S9'").fetchone()
        c.close()
        self.assertEqual(row[0], "exploratory")
        self.assertEqual(json.loads(row[1]), {"summary": "tema nuevo"})
        self.assertEqual(sess, (t, os.path.getsize(t)))
        self.assertEqual(self._version(), (1, 1))

    def test_con_sqlite_al_dia_el_paso_se_aplica_completo(self):
        _connect_quiet(self.path)[0].close()
        with mock.patch.object(_migrations, "SQLITE_VERSION", (3, 35, 5)):
            self.assert_como_nueva()
            con, _ = _connect_quiet(self.path)
            self.assertEqual(_schema_shape(con), _fresh_shape())
            con.close()

    def test_sin_nada_que_retirar_no_detiene(self):
        d = tempfile.mkdtemp(prefix="neb-test-nueva-")
        path = os.path.join(d, "neb.db")
        with mock.patch.object(_migrations, "SQLITE_VERSION", (3, 35, 5)):
            _db_shared._connect(path, SCHEMA).close()
        c = sqlite3.connect(path)
        try:
            self.assertIsNone(_migrations._team_precheck(c))
        finally:
            c.close()


class TestObjetosDelUsuario(_Paso2):
    """D12: una vista, un trigger o un índice creado a mano que usa lo retirado detiene el paso 2 en su
    precheck: no se borra nada, no hay respaldo, la conexión y la captura funcionan, y el motivo nombra cada
    objeto y cómo quitarlo. Al quitarlo, la siguiente conexión aplica el paso completo."""

    def _bloqueado(self, nombre, drop, *usa):
        con, err = _connect_quiet(self.path)
        self.assertIsNotNone(con, err)
        self.assert_intacta(con)
        con.close()
        self.assertEqual(self._version(), (1, 1))
        self.assertEqual(self._backups(), [])
        motivo = self._detenido()
        self.assertIsNotNone(motivo)
        self.assertIn(nombre, motivo)
        self.assertIn(f"{drop} {nombre}", motivo)
        self.assertIn("No se borró nada", motivo)
        for u in usa:
            self.assertIn(u, motivo)
        self.assertIn("paso de base 2", err)
        return motivo

    def _quitar_y_aplicar(self, *sqls):
        self._raw(*sqls)
        self.assert_como_nueva()
        con, _ = _connect_quiet(self.path)
        self.assertEqual(_schema_shape(con), _fresh_shape())
        con.close()

    def test_critico_vista_sobre_work_owner(self):
        self._raw("CREATE VIEW v_duenos AS SELECT id, owner FROM work")
        self._bloqueado("v_duenos", "DROP VIEW", "la vista v_duenos usa work.owner")
        c = sqlite3.connect(self.path)
        self.assertEqual(c.execute("SELECT owner FROM v_duenos WHERE id=1").fetchone(), ("dev",))
        c.close()
        locker = sqlite3.connect(self.path, isolation_level=None, timeout=0.1)
        locker.execute("BEGIN IMMEDIATE")
        locker.execute("UPDATE work SET origin_machine='otra' WHERE id=2")
        t0 = time.monotonic()
        con, err = _connect_quiet(self.path)
        elapsed = time.monotonic() - t0
        locker.execute("ROLLBACK")
        locker.close()
        self.assertIsNotNone(con, err)
        con.close()
        self.assertLess(elapsed, 3.0, "un precheck con motivo no pide candado")
        self._quitar_y_aplicar("DROP VIEW v_duenos")

    def test_critico_trigger_que_escribe_dirty(self):
        self._raw("CREATE TRIGGER t_marca AFTER UPDATE OF payload_json ON work "
                  "BEGIN UPDATE work SET dirty = 1 WHERE id = new.id; END")
        self._bloqueado("t_marca", "DROP TRIGGER", "el trigger t_marca usa work.dirty")
        c = sqlite3.connect(self.path)
        c.execute("UPDATE work SET payload_json='{\"summary\":\"otro\"}' WHERE id=2")
        c.commit()
        self.assertEqual(c.execute("SELECT dirty FROM work WHERE id=2").fetchone(), (1,))
        c.close()
        self._quitar_y_aplicar("DROP TRIGGER t_marca")

    def test_vista_sobre_event(self):
        self._raw("CREATE VIEW v_eventos AS SELECT work_id, action FROM event")
        self._bloqueado("v_eventos", "DROP VIEW", "la vista v_eventos usa event")
        self._quitar_y_aplicar("DROP VIEW v_eventos")

    def test_critico_objetos_propios_de_neb_no_bloquean(self):
        import pendings
        c = sqlite3.connect(self.path)
        pendings._ensure_fts(c)
        c.execute("CREATE TRIGGER t_pending_nota AFTER INSERT ON pending BEGIN "
                  "INSERT INTO pending_note (pending_id, note, ts) VALUES (new.id, new.context_origin, 't'); END")
        c.commit()
        c.close()
        con, err = _connect_quiet(self.path)
        self.assertIsNotNone(con, err)
        self.assertEqual(err, "")
        con.close()
        self.assert_como_nueva()

    def test_critico_vista_sobre_vista(self):
        self._raw("CREATE VIEW v_todo AS SELECT * FROM work",
                  "CREATE VIEW v_duenos AS SELECT id, owner FROM v_todo")
        self._bloqueado("v_duenos", "DROP VIEW", "la vista v_duenos usa work.owner")
        self._quitar_y_aplicar("DROP VIEW v_duenos", "DROP VIEW v_todo")

    def test_critico_trigger_de_auditoria_con_select_star(self):
        self._raw("CREATE TABLE work_hist AS SELECT * FROM work WHERE 0",
                  "CREATE TRIGGER t_hist AFTER UPDATE ON work BEGIN "
                  "INSERT INTO work_hist SELECT * FROM work WHERE id = new.id; END")
        self._bloqueado("t_hist", "DROP TRIGGER", "el trigger t_hist usa")
        self._quitar_y_aplicar("DROP TRIGGER t_hist", "DROP TABLE work_hist")

    def test_critico_indice_del_usuario(self):
        self._raw("CREATE INDEX mi_idx_owner ON work(owner)")
        self._bloqueado("mi_idx_owner", "DROP INDEX", "el índice mi_idx_owner usa work.owner")
        self._quitar_y_aplicar("DROP INDEX mi_idx_owner")

    def test_vista_que_ya_no_abre(self):
        self._raw("CREATE TABLE t_aparte (a)", "CREATE VIEW v_rota AS SELECT a FROM t_aparte",
                  "DROP TABLE t_aparte")
        self._bloqueado("v_rota", "DROP VIEW", "ya no abre")
        self._quitar_y_aplicar("DROP VIEW v_rota")

    def test_vista_con_lista_de_columnas_sobre_asterisco(self):
        c = sqlite3.connect(self.path)
        n = len(c.execute("PRAGMA table_info(work)").fetchall())
        c.execute("CREATE VIEW v_cols(%s) AS SELECT * FROM work" % ", ".join(f"c{i}" for i in range(n)))
        c.commit()
        c.close()
        self._bloqueado("v_cols", "DROP VIEW", "la vista v_cols usa")
        self._quitar_y_aplicar("DROP VIEW v_cols")

    def test_vista_con_union_sobre_asterisco(self):
        self._raw("CREATE TABLE work_hist AS SELECT * FROM work WHERE 0",
                  "CREATE VIEW v_union AS SELECT * FROM work UNION ALL SELECT * FROM work_hist")
        self._bloqueado("v_union", "DROP VIEW", "la vista v_union usa")
        self._quitar_y_aplicar("DROP VIEW v_union", "DROP TABLE work_hist")

    def test_trigger_con_insert_sin_lista_de_columnas(self):
        self._raw("CREATE TRIGGER t_copia AFTER DELETE ON session_sync BEGIN "
                  "INSERT INTO session_sync VALUES (old.session_id || '-b', NULL, NULL, 0, NULL, NULL, 't', NULL, 0); "
                  "END")
        self._bloqueado("t_copia", "DROP TRIGGER", "el trigger t_copia usa")
        self._quitar_y_aplicar("DROP TRIGGER t_copia")

    def test_varios_objetos_se_nombran_todos(self):
        self._raw("CREATE VIEW v_duenos AS SELECT id, owner FROM work", "CREATE INDEX mi_idx_dirty ON work(dirty)")
        motivo = self._bloqueado("v_duenos", "DROP VIEW", "DROP INDEX mi_idx_dirty", "el índice mi_idx_dirty usa work.dirty")
        self.assertIn("la vista v_duenos usa work.owner", motivo)
        self._quitar_y_aplicar("DROP VIEW v_duenos", "DROP INDEX mi_idx_dirty")


class TestObjetoEntrePrecheckYAplicar(_Paso2):
    """Un objeto del usuario creado después del precheck (con el candado todavía libre) hace que `aplicar` lo
    vea dentro de la transacción: el paso revierte entero, deja su motivo en schema_step_error, borra su
    respaldo y se reintenta."""

    def _steps_con_carrera(self, sql):
        real = _migrations.STEPS[1]

        def precheck(con):
            motivo = real.precheck(con)
            otro = sqlite3.connect(self.path)
            otro.execute(sql)
            otro.commit()
            otro.close()
            return motivo
        paso2 = _migrations.Step(2, real.titulo, real.aplicar, min_code=real.min_code, destructivo=real.destructivo,
                                 espera=real.espera, precheck=precheck)
        return (STEP1, paso2)

    def _check(self, sql, nombre, drop_sql):
        antes = _hashes(self.path)
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err):
            con = _db_shared._connect(self.path, SCHEMA, steps=self._steps_con_carrera(sql))
        self.assertIsNotNone(con, err.getvalue())
        self.assert_intacta(con)
        con.close()
        self.assertEqual(self._version(), (1, 1))
        self.assertEqual(self._backups(), [], "el respaldo del intento revertido se borra")
        errores = self._errores()
        self.assertEqual([e[0] for e in errores], [2])
        self.assertIn(nombre, errores[0][3])
        self.assertEqual(_hashes(self.path), antes)
        self._raw(drop_sql)
        with mock.patch.object(sys, "stderr", io.StringIO()):
            _db_shared._connect(self.path, SCHEMA, retry=True).close()
        self.assertEqual(self._errores(), [])
        self.assert_como_nueva()

    def test_critico_trigger_con_asterisco_creado_tras_el_precheck(self):
        self._check("CREATE TRIGGER t_tarde AFTER UPDATE ON work BEGIN SELECT * FROM work; END", "t_tarde",
                    "DROP TRIGGER t_tarde")

    def test_vista_creada_tras_el_precheck(self):
        self._check("CREATE VIEW v_tarde AS SELECT owner FROM work", "v_tarde", "DROP VIEW v_tarde")


_RACER = r"""
import sys, time, json
sys.path.insert(0, sys.argv[1])
import _db_shared
t0 = float(sys.argv[4])
while time.time() < t0:
    time.sleep(0.005)
con = _db_shared._connect(sys.argv[2], sys.argv[3])
if con is None:
    print(json.dumps({"ok": False}))
else:
    n = con.execute("SELECT count(*) FROM work").fetchone()[0]
    print(json.dumps({"ok": True, "works": n}))
    con.close()
"""


class TestConcurrencia(unittest.TestCase):

    def test_critico_dos_procesos_sobre_una_base_sin_migrar(self):
        path = _base_645(os.path.join(tempfile.mkdtemp(prefix="neb-test-race-"), "neb.db"))
        antes = _hashes(path)
        t0 = str(time.time() + 1.5)
        procs = [subprocess.Popen([sys.executable, "-c", _RACER, LIB, path, SCHEMA, t0],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_child_env(tempfile.gettempdir()))
                 for _ in range(2)]
        outs = [p.communicate(timeout=60) for p in procs]
        for out, err in outs:
            self.assertEqual(json.loads(out.decode()), {"ok": True, "works": 2}, err.decode("utf-8", "replace"))
        con, err = _connect_quiet(path)
        self.assertEqual(err, "")
        self.assertEqual(_schema_shape(con), _fresh_shape())
        self.assertEqual(con.execute("SELECT step FROM schema_step ORDER BY step").fetchall(), [(1,), (2,)])
        con.close()
        self.assertEqual(_hashes(path), antes)
        self.assertEqual(len(os.listdir(_migrations.backup_dir(path))), 1)


class TestBaseMigradaSinCandado(unittest.TestCase):

    def test_candado_ajeno_no_retrasa_a_connect(self):
        path = _base_645(os.path.join(tempfile.mkdtemp(prefix="neb-test-migrada-"), "neb.db"))
        _connect_quiet(path)[0].close()
        locker = sqlite3.connect(path, isolation_level=None, timeout=0.1)
        self.addCleanup(locker.close)
        locker.execute("BEGIN IMMEDIATE")
        locker.execute("UPDATE work SET origin_machine='otra' WHERE id=2")
        t0 = time.monotonic()
        con, err = _connect_quiet(path)
        elapsed = time.monotonic() - t0
        self.assertIsNotNone(con, err)
        con.close()
        self.assertEqual(err, "")
        self.assertLess(elapsed, 3.0)


class TestJournalDelete(unittest.TestCase):

    def test_connect_sobre_una_base_en_journal_delete(self):
        path = _base_645(os.path.join(tempfile.mkdtemp(prefix="neb-test-delete-"), "neb.db"), journal="DELETE")
        c = sqlite3.connect(path)
        self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        c.close()
        antes = _hashes(path)
        con, err = _connect_quiet(path)
        self.assertIsNotNone(con, err)
        self.assertEqual(err, "")
        self.assertEqual(_schema_shape(con), _fresh_shape())
        logbook._upsert_exploratory(con, "SD", "maq", "resumen", None, None, "/c", None)
        con.commit()
        self.assertEqual(con.execute("SELECT count(*) FROM work").fetchone()[0], 3)
        con.close()
        self.assertEqual({k: v for k, v in _hashes(path).items() if k != "work"},
                         {k: v for k, v in antes.items() if k != "work"})
        self.assertEqual(_schema_step_version(path), (2, 2))
        self.assertEqual(len(os.listdir(_migrations.backup_dir(path))), 1)


# =========================================================================== _add_missing_columns
class TestAddMissingColumns(unittest.TestCase):
    """Mudadas de test_logbook_sync_errors.py (retirado en 7.0.0): el contrato de _migrate sigue vivo."""

    def test_el_perdedor_de_la_carrera_no_pierde_la_conexion(self):
        """Dos procesos ven que read_byte falta; el segundo ALTER da 'duplicate column name'. Se tolera."""
        path = os.path.join(tempfile.mkdtemp(prefix="neb-test-carrera-"), "neb.db")
        real = sqlite3.connect(path)
        real.executescript(
            "CREATE TABLE work (id INTEGER PRIMARY KEY, mode TEXT, created_at TEXT, updated_at TEXT);"
            "CREATE TABLE session_sync (session_id TEXT PRIMARY KEY, transcript_path TEXT, updated_at TEXT);")
        for _name, ddl in _db_shared._SESSION_SYNC_MIGRATIONS:
            real.execute(ddl)                                # el 'otro proceso' ya migró
        real.commit()

        class _StaleView:                                    # este proceso aún ve el table_info viejo
            def __init__(self, con): self._con = con
            def execute(self, sql, *a):
                if sql.startswith("PRAGMA table_info"):
                    class _R:
                        def fetchall(_s): return [(0, "id"), (1, "mode")]
                    return _R()
                return self._con.execute(sql, *a)
            def __getattr__(self, n): return getattr(self._con, n)

        _db_shared._migrate(_StaleView(real))                # no debe lanzar
        real.close()

    def test_otros_errores_si_se_propagan(self):
        """'database is locked' NO se traga: _connect debe devolver None (invariante: conexión = esquema completo)."""
        class _Locked:
            def execute(self, sql, *a):
                if sql.startswith("PRAGMA table_info"):
                    class _R:
                        def fetchall(_s): return [(0, "id")]
                    return _R()
                raise sqlite3.OperationalError("database is locked")
            def commit(self): pass
        with self.assertRaises(sqlite3.OperationalError):
            _db_shared._migrate(_Locked())


if __name__ == "__main__":
    unittest.main()
