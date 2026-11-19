#!/usr/bin/env python3
"""test_logbook_cli_and_drain.py — CLI en UTF-8 + opt-in al drenar el outbox (6.14.2).

Origen: los tests del fix de Alfredo Estrada sobre 6.4.1, llevados al registro de sesión (session_sync y
su backfill) y al criterio por repo:
  • REQ: opt-in si su repo (primer path de «Path del proyecto», texto libre) trae el marcador.
  • Exploratorio: si su sesión arrancó (cwd raíz del .jsonl) en un dir con marcador.

Framework: unittest (stdlib). DBs, repos y home temporales; nunca toca ~/.claude ni la red.
  py -m unittest hooks.tests.test_logbook_cli_and_drain
"""
import json
import os
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
import logbook

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
MARKER = "# Proyecto\n<!-- neb-logbook: central -->\n"
ENV_KEYS = ("NEB_LOGBOOK_ENDPOINT", "NEB_LOGBOOK_TOKEN")
FAKE_ENV = {"NEB_LOGBOOK_ENDPOINT": "http://central.invalid", "NEB_LOGBOOK_TOKEN": "tok"}


def _make_repo(base, name, marked):
    path = os.path.join(base, name)
    os.makedirs(path)
    with open(os.path.join(path, "CLAUDE.md"), "w", encoding="utf-8") as f:
        f.write(MARKER if marked else "# Proyecto sin opt-in\n")
    return path


def _mark(path):
    with open(os.path.join(path, "CLAUDE.md"), "w", encoding="utf-8") as f:
        f.write(MARKER)


def _jsonl(path, cwd, turns=1):
    """Transcript mínimo: un snapshot sin cwd (como los reales) y `turns` entradas con el cwd de la sesión."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "file-history-snapshot", "snapshot": {}}) + "\n")
        for i in range(turns):
            entry = {"type": "user", "message": {"content": f"hola {i}"}}
            if cwd is not None:
                entry["cwd"] = cwd
            f.write(json.dumps(entry) + "\n")
    return path


def _add_req(con, project, repo_path, session_id, transcript_path=None):
    return logbook._upsert_req(con, project, "req-" + project, "dev", "maq", "En progreso", "main", "abc",
                               repo_path, "", "{}", session_id, transcript_path)


class _Central:
    def __init__(self):
        self.calls = []

    def __call__(self, endpoint, token, path, method="GET", payload=None):
        self.calls.append((path, payload))
        return 200, {"remote_id": 900 + len(self.calls)}

    def published(self, path):
        return [p for (pth, p) in self.calls if pth == path]


class TestCliUtf8(unittest.TestCase):

    def test_list_survives_cp1252_stdout(self):
        home = tempfile.mkdtemp(prefix="neb-test-cli-")
        os.makedirs(os.path.join(home, ".claude"))
        con = _db_shared._connect(_db_shared.resolve_db_path(home), SCHEMA)
        _add_req(con, "proj→uno", "", "s1")
        con.commit()
        con.close()

        env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS + ("PYTHONUTF8",)}
        env.update(HOME=home, USERPROFILE=home, NEB_HOME=NEB_ROOT, PYTHONIOENCODING="cp1252")
        r = subprocess.run([sys.executable, os.path.join(LIB, "logbook.py"), "list"],
                           capture_output=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertNotEqual(r.stdout.strip(), b"", f"stdout vacío; stderr={r.stderr!r}")
        self.assertIn("proj→uno", r.stdout.decode("utf-8"))


class TestRepoDir(unittest.TestCase):
    """«Path del proyecto» es texto libre: el repo es su primer path absoluto."""

    def setUp(self):
        self.repo = os.path.normpath(tempfile.mkdtemp(prefix="neb-test-repo-"))

    def test_texto_libre_real(self):
        for raw in (self.repo,
                    f"{self.repo} (rama `master`)",
                    f"`{self.repo}` (rama `main` = `origin/main` = `0000abcd`)",
                    f"{self.repo} (registro); entregables en otro lado",
                    f"{self.repo} (núcleo) + C:\\otro\\repo (overlay)",
                    f"{self.repo}.",
                    f"  {self.repo}"):
            self.assertEqual(logbook._repo_dir(raw), self.repo, raw)

    def test_comillas_negritas_y_espacios(self):
        con_espacio = os.path.join(self.repo, "mi repo")
        self.assertEqual(logbook._repo_dir(f"`{con_espacio}` (rama `main`)"), con_espacio)
        self.assertEqual(logbook._repo_dir(f'"{con_espacio}"'), con_espacio)
        self.assertEqual(logbook._repo_dir(f"**{self.repo}** (registro)"), self.repo)
        self.assertEqual(logbook._repo_dir(f"{con_espacio} (rama main)"), os.path.join(self.repo, "mi"))  # sin comillas se corta

    def test_tilde_unc_y_posix_de_git_bash(self):
        self.assertEqual(logbook._repo_dir("~"), os.path.normpath(os.path.expanduser("~")))
        if sys.platform == "win32":
            self.assertEqual(logbook._repo_dir(r"\\servidor\recurso\repo (red)"), r"\\servidor\recurso\repo")
            self.assertEqual(logbook._repo_dir("/c/x/repo (rama main)"), r"C:\x\repo")

    def test_sin_path_absoluto_no_hay_repo(self):
        for raw in ("", None, ".", "proyectos/app", "rama main", "(sin ruta)"):
            self.assertEqual(logbook._repo_dir(raw), "", raw)


class _DrainBase(unittest.TestCase):

    def setUp(self):
        self._env = mock.patch.dict(os.environ, FAKE_ENV)
        self._env.start()
        self.base = tempfile.mkdtemp(prefix="neb-test-drain-")
        self.marked = _make_repo(self.base, "marcado", True)
        self.unmarked = _make_repo(self.base, "sin-marcador", False)
        self.home = os.path.join(self.base, "home")                    # sin CLAUDE.md
        os.makedirs(os.path.join(self.home, ".claude"))
        self.con = _db_shared._connect(_db_shared.resolve_db_path(self.home), SCHEMA)
        self.con.row_factory = sqlite3.Row
        self.central = _Central()
        self._http = mock.patch.object(logbook, "_http", self.central)
        self._http.start()

    def tearDown(self):
        self._http.stop()
        self.con.close()
        self._env.stop()

    def _session(self, sid, root):
        """Registro de la sesión como en la captura: ruta del .jsonl y su cwd raíz."""
        path = _jsonl(os.path.join(self.base, f"{sid}.jsonl"), root)
        logbook._register_session(self.con, sid, path, logbook._jsonl_cwd(path))
        self.con.commit()
        return path

    def _publish(self, wid):
        self.con.execute("UPDATE work SET remote_id=?, dirty=0 WHERE id=?", (100 + wid, wid))
        self.con.commit()

    def _row(self, sql, *args):
        return self.con.execute(sql, args).fetchone()


class TestDrainWorks(_DrainBase):

    def test_drain_works_only_marked(self):
        a = _add_req(self.con, "a", self.marked, "sa")
        b = _add_req(self.con, "b", self.unmarked, "sb")
        self.con.commit()
        logbook._drain_works(self.con, "http://x", "tok")
        self.assertEqual([p["repo_path"] for p in self.central.published("/work/publish")], [self.marked])
        self.assertEqual(tuple(self._row("SELECT dirty, remote_id IS NOT NULL FROM work WHERE id=?", a)), (0, 1))
        self.assertEqual(tuple(self._row("SELECT dirty, remote_id FROM work WHERE id=?", b)), (1, None))

    def test_critico_req_de_repo_marcado_con_path_en_texto_libre_se_publica(self):
        _add_req(self.con, "a", f"{self.marked} (rama `master`)", "sa")
        _add_req(self.con, "b", f"`{self.marked}` (registro) · repos: x, y", "sb")
        _add_req(self.con, "c", f"{self.unmarked} (rama `main`)", "sc")
        self.con.commit()
        logbook._drain_works(self.con, "http://x", "tok")
        self.assertEqual(sorted(p["project"] for p in self.central.published("/work/publish")), ["a", "b"])

    def test_empty_or_relative_repo_path_not_published_from_marked_cwd(self):
        _add_req(self.con, "vacio", "", "sv")
        _add_req(self.con, "relativo", ".", "sr")
        self.con.commit()
        old = os.getcwd()
        os.chdir(self.marked)   # una ruta vacía o relativa resolvería contra este cwd
        try:
            logbook._drain_works(self.con, "http://x", "tok")
        finally:
            os.chdir(old)
        self.assertEqual(self.central.published("/work/publish"), [])

    def test_exploratorio_sigue_al_cwd_raiz_no_al_del_primer_stop(self):
        # A arrancó sin marcador e hizo cd al repo marcado antes del primer Stop: su repo_path es el marcado.
        pa = _jsonl(os.path.join(self.base, "A.jsonl"), self.home)
        a = logbook._upsert_exploratory(self.con, "A", "dev", "maq", "resumen A", None, None, self.marked, pa)
        # B arrancó en el repo marcado y su primer Stop fue en otro lado.
        pb = _jsonl(os.path.join(self.base, "B.jsonl"), self.marked)
        b = logbook._upsert_exploratory(self.con, "B", "dev", "maq", "resumen B", None, None, self.unmarked, pb)
        logbook._register_session(self.con, "A", pa, logbook._jsonl_cwd(pa))
        logbook._register_session(self.con, "B", pb, logbook._jsonl_cwd(pb))
        self.con.commit()
        logbook._drain_works(self.con, "http://x", "tok")
        self.assertEqual([p["claude_session_id"] for p in self.central.published("/work/publish")], ["B"])

    def test_cwd_raiz_desconocido_falla_cerrado(self):
        p = _jsonl(os.path.join(self.base, "N.jsonl"), None)               # .jsonl sin ningún cwd
        logbook._upsert_exploratory(self.con, "N", "dev", "maq", "", None, None, self.marked, p)
        logbook._register_session(self.con, "N", p, logbook._jsonl_cwd(p))
        self.con.commit()
        self.assertIsNone(self._row("SELECT root_cwd FROM session_sync WHERE session_id='N'")[0])
        logbook._drain_works(self.con, "http://x", "tok")
        self.assertEqual(self.central.published("/work/publish"), [])

    def test_conflicto_recapturado_sigue_el_opt_in(self):
        a = _add_req(self.con, "a", self.marked, "sa")
        b = _add_req(self.con, "b", self.unmarked, "sb")
        self.con.execute("UPDATE work SET dirty=1, conflict=1")               # recapturado tras un 409
        self.con.commit()
        logbook._drain_works(self.con, "http://x", "tok")
        self.assertEqual(tuple(self._row("SELECT dirty, conflict FROM work WHERE id=?", a)), (0, 0))
        self.assertEqual(tuple(self._row("SELECT dirty, conflict FROM work WHERE id=?", b)), (1, 1))
        _mark(self.unmarked)                                                  # re-entrada: el repo gana el marcador
        logbook._drain_works(self.con, "http://x", "tok")
        self.assertEqual(tuple(self._row("SELECT dirty, conflict FROM work WHERE id=?", b)), (0, 0))

    def test_upsert_req_refreshes_repo_path(self):
        wid = _add_req(self.con, "wt", self.unmarked, "s1")
        _add_req(self.con, "wt", self.marked, "s2")      # el REQ pasa a otro checkout
        _add_req(self.con, "wt", "", "s3")               # memoria sin ruta: conserva la vigente
        self.con.commit()
        self.assertEqual(self._row("SELECT repo_path FROM work WHERE id=?", wid)[0], self.marked)


class TestBackfill(_DrainBase):

    def test_backfill_completa_root_cwd_una_vez(self):
        _add_req(self.con, "a", self.marked, "S")
        path = self._session("S", self.marked)
        self.con.execute("UPDATE session_sync SET root_cwd=NULL")             # fila anterior a 6.14.2
        self.con.commit()
        logbook._backfill_sessions(self.con, None)
        self.assertEqual(self._row("SELECT root_cwd FROM session_sync WHERE session_id='S'")[0], self.marked)
        os.remove(path)                                                       # el .jsonl se borra después
        self.assertTrue(logbook._OptIn(self.con).session("S"))

    def test_critico_backfill_registra_la_sesion_que_un_work_apunta_y_el_exploratorio_se_publica(self):
        """Un exploratorio sin fila en session_sync (capturado por un cliente anterior) no tiene root_cwd con
        qué decidir su opt-in: el backfill registra su sesión, _fill_root_cwd la completa y se publica."""
        p = _jsonl(os.path.join(self.base, "X.jsonl"), self.marked)
        logbook._upsert_exploratory(self.con, "X", "dev", "maq", "", None, None, self.marked, p)
        self.con.commit()
        self.assertIsNone(self._row("SELECT 1 FROM session_sync WHERE session_id='X'"))
        logbook._backfill_sessions(self.con, None)
        self.assertEqual(tuple(self._row("SELECT transcript_path, root_cwd FROM session_sync WHERE session_id='X'")),
                         (p, self.marked))
        logbook._drain_works(self.con, "http://x", "tok")
        self.assertEqual([w["claude_session_id"] for w in self.central.published("/work/publish")], ["X"])
        logbook._backfill_sessions(self.con, None)                            # idempotente
        self.assertEqual(self._row("SELECT count(*) FROM session_sync")[0], 1)


class TestSyncStatusOptIn(_DrainBase):

    def _escenario(self):
        a = _add_req(self.con, "a", self.marked, "sa")
        b = _add_req(self.con, "b", self.unmarked, "sb")
        self.con.execute("UPDATE work SET last_error='publish: HTTP 500'")
        self.con.commit()
        pub = _add_req(self.con, "pub", self.unmarked, "sp")
        self._publish(pub)
        return a, b

    def test_lo_que_queda_local_no_se_lista(self):
        a, _ = self._escenario()
        optin = logbook._OptIn(self.con)
        works = logbook._sync_status_rows(self.con, True, optin)
        self.assertEqual([w["local_id"] for w in works], [a])
        self.assertEqual(optin.hidden, {"works": 1})                          # b

    def test_sin_central_no_filtra(self):
        self._escenario()
        works = logbook._sync_status_rows(self.con, False, None)
        self.assertEqual(len(works), 2)                                          # a y b, con last_error


class TestCapturaConCentral(_DrainBase):

    def test_captura_real_registra_la_sesion_con_su_cwd_raiz(self):
        mem = os.path.join(self.home, ".claude", "projects", _db_shared.encode_cwd(self.marked), "memory")
        os.makedirs(mem)
        with open(os.path.join(mem, "active_p_con.md"), "w", encoding="utf-8") as fh:
            fh.write(f"- **Nombre:** con\n- **Path del proyecto:** {self.marked}\n- **Estado:** En progreso\n")
        t = _jsonl(os.path.join(self.base, "S.jsonl"), self.marked)
        argv = ["logbook.py", "S", self.marked, t, "Stop", NEB_ROOT, self.home]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(logbook, "_maybe_spawn_sync", lambda *a, **k: None):
            logbook.main()
        row = self._row("SELECT transcript_path, root_cwd, work_id, read_byte FROM session_sync WHERE session_id='S'")
        self.assertEqual(tuple(row), (t, self.marked, None, os.path.getsize(t)))
        logbook._drain_works(self.con, "http://x", "tok")
        self.assertEqual([w["req_slug"] for w in self.central.published("/work/publish")], ["con"])


class TestSyncMainCableado(_DrainBase):

    def test_sync_main_aplica_el_opt_in_a_req_y_exploratorios(self):
        _add_req(self.con, "a", self.marked, "home")
        self._session("home", self.home)                                     # REQ marcado, sesión de home
        d = os.path.join(self.home, ".claude", "projects", "p")
        os.makedirs(d)
        pe = _jsonl(os.path.join(d, "E.jsonl"), self.marked)
        logbook._upsert_exploratory(self.con, "E", "dev", "maq", "", None, None, self.marked, pe)
        po = _jsonl(os.path.join(d, "O.jsonl"), self.home)                   # exploratorio de home
        logbook._upsert_exploratory(self.con, "O", "dev", "maq", "", None, None, self.marked, po)
        self.con.commit()                                                    # E y O sin fila: las crea el backfill
        logbook.sync_main([NEB_ROOT, self.home])
        sent = self.central.published("/work/publish")
        self.assertEqual(sorted((p["mode"], p["claude_session_id"]) for p in sent),
                         [("exploratory", "E"), ("req", "home")])
        self.assertEqual({p for (p, _) in self.central.calls}, {"/work/publish"})   # nada más viaja


class TestMigracionRootCwd(unittest.TestCase):

    def test_db_de_6_14_1_gana_las_columnas_y_conserva_sus_filas(self):
        d = tempfile.mkdtemp(prefix="neb-test-mig-")
        db = os.path.join(d, "neb.db")
        raw = sqlite3.connect(db)
        raw.executescript(                                                   # session_sync de 6.14.1, congelada
            "CREATE TABLE session_sync (session_id TEXT PRIMARY KEY, work_id INTEGER, transcript_path TEXT, "
            "synced_byte INTEGER NOT NULL DEFAULT 0, transcript_error TEXT, transcript_error_at TEXT, "
            "updated_at TEXT NOT NULL);")
        raw.execute("INSERT INTO session_sync (session_id, synced_byte, updated_at) VALUES ('S', 7, 'x')")
        raw.commit()
        raw.close()
        con = _db_shared._connect(db, SCHEMA)
        self.assertIsNotNone(con)
        cols = {r[1] for r in con.execute("PRAGMA table_info(session_sync)")}
        self.assertTrue({"root_cwd", "read_byte"} <= cols)
        self.assertEqual(tuple(con.execute("SELECT synced_byte, root_cwd, read_byte FROM session_sync").fetchone()),
                         (7, None, 0))
        con.close()


class TestLocalModeByEmptyEndpoint(unittest.TestCase):

    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}
        self.base = tempfile.mkdtemp(prefix="neb-test-local-")
        self.marked = _make_repo(self.base, "marcado", True)

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_empty_endpoint_is_local_only(self):
        os.environ["NEB_LOGBOOK_ENDPOINT"] = ""
        os.environ["NEB_LOGBOOK_TOKEN"] = "tok"
        self.assertEqual(logbook._central(), (None, None))
        self.assertFalse(logbook._is_shared(self.marked))

    def test_endpoint_with_marker_is_shared(self):
        os.environ["NEB_LOGBOOK_ENDPOINT"] = "http://central.invalid"
        os.environ["NEB_LOGBOOK_TOKEN"] = "tok"
        self.assertEqual(logbook._central(), ("http://central.invalid", "tok"))
        self.assertTrue(logbook._is_shared(self.marked))

    def test_is_shared_empty_path_ignores_process_cwd(self):
        os.environ["NEB_LOGBOOK_ENDPOINT"] = "http://central.invalid"
        old = os.getcwd()
        os.chdir(self.marked)
        try:
            self.assertFalse(logbook._is_shared(""))
            self.assertFalse(logbook._is_shared(None))
        finally:
            os.chdir(old)


if __name__ == "__main__":
    unittest.main()
