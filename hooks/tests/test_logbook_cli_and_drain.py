#!/usr/bin/env python3
"""test_logbook_cli_and_drain.py — CLI en UTF-8 + opt-in al drenar el outbox (6.14.2).

Origen: los tests del fix de Alfredo Estrada sobre 6.4.1, llevados al drenaje por sesión de 6.12
(session_sync, backfill y adopción) y al criterio por repo:
  • REQ: opt-in si su repo (primer path de «Path del proyecto», texto libre) trae el marcador.
  • Exploratorio: si su sesión arrancó (cwd raíz del .jsonl) en un dir con marcador.
  • Transcript: si la sesión arrancó en un dir con marcador Y su work atribuido tiene opt-in.

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
    def __init__(self, transcript_code=200):
        self.calls = []
        self._code = transcript_code

    def __call__(self, endpoint, token, path, method="GET", payload=None, body=None, timeout=5):
        if payload is None and body is not None:
            payload = json.loads(body)
        self.calls.append((path, payload))
        if path == "/transcript":
            return self._code, ({} if self._code == 200 else {"error": "x"})
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

    def _session(self, sid, root, work_ids, optin=None):
        path = _jsonl(os.path.join(self.base, f"{sid}.jsonl"), root)
        logbook._register_session(self.con, sid, path, work_ids, optin)
        self.con.commit()
        return path

    def _publish(self, wid):
        self.con.execute("UPDATE work SET remote_id=?, dirty=0 WHERE id=?", (100 + wid, wid))
        self.con.commit()

    def _row(self, sql, *args):
        return self.con.execute(sql, args).fetchone()

    def _uploaded(self):
        return [p["session_id"] for p in self.central.published("/transcript")]


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
        logbook._register_session(self.con, "A", pa, [a])
        logbook._register_session(self.con, "B", pb, [b])
        self.con.commit()
        logbook._drain_works(self.con, "http://x", "tok")
        self.assertEqual([p["claude_session_id"] for p in self.central.published("/work/publish")], ["B"])

    def test_cwd_raiz_desconocido_falla_cerrado(self):
        p = _jsonl(os.path.join(self.base, "N.jsonl"), None)               # .jsonl sin ningún cwd
        w = logbook._upsert_exploratory(self.con, "N", "dev", "maq", "", None, None, self.marked, p)
        logbook._register_session(self.con, "N", p, [w])
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


class TestDrainTranscripts(_DrainBase):

    def test_drain_transcripts_skips_unmarked_even_if_published(self):
        a = _add_req(self.con, "a", self.marked, "sa")
        b = _add_req(self.con, "b", self.unmarked, "sb")
        self._publish(a)
        self._publish(b)
        self._session("sa", self.marked, [a])
        self._session("sb", self.unmarked, [b])
        logbook._drain_transcripts(self.con, "http://x", "tok")
        self.assertEqual(self._uploaded(), ["sa"])

    def test_critico_sesion_abierta_fuera_de_un_repo_marcado_no_sube(self):
        w = _add_req(self.con, "a", self.marked, "dentro")
        self._publish(w)
        self._session("home", self.home, [w])           # home sin marcador toma el REQ activo de su memoria
        self._session("dentro", self.marked, [w])
        logbook._drain_transcripts(self.con, "http://x", "tok")
        self.assertEqual(self._uploaded(), ["dentro"])
        self.assertEqual(self._row("SELECT synced_byte FROM session_sync WHERE session_id='home'")[0], 0)

    def test_sesion_marcada_atada_a_work_sin_opt_in_no_sube(self):
        # Work publicado antes del fix (o cuyo repo perdió el marcador) y sin otro candidato: la mitad "work"
        # de la compuerta basta para frenar el transcript aunque la sesión arrancó en un dir marcado.
        w = _add_req(self.con, "b", self.unmarked, "S")
        self._publish(w)
        self._session("S", self.marked, [w])
        logbook._drain_transcripts(self.con, "http://x", "tok")
        self.assertEqual(self.central.calls, [])

    def test_atribucion_prefiere_un_work_con_opt_in(self):
        sin = _add_req(self.con, "sin", self.unmarked, "S")
        con_ = _add_req(self.con, "con", self.marked, "S")
        self._publish(sin)
        self._publish(con_)
        # Sin optin (sin central) gana el primero, como antes de 6.14.2.
        self._session("S", self.marked, [sin, con_])
        self.assertEqual(self._row("SELECT work_id FROM session_sync WHERE session_id='S'")[0], sin)
        # Con optin, la siguiente captura la reatribuye al work que sí sube.
        self._session("S", self.marked, [sin, con_], logbook._OptIn(self.con))
        self.assertEqual(self._row("SELECT work_id FROM session_sync WHERE session_id='S'")[0], con_)
        logbook._drain_transcripts(self.con, "http://x", "tok")
        self.assertEqual([p["work_id"] for p in self.central.published("/transcript")], [100 + con_])

    def test_tope_por_envio_sin_opt_in_no_deja_aviso(self):
        a = _add_req(self.con, "a", self.marked, "sa")
        b = _add_req(self.con, "b", self.unmarked, "sb")
        self._publish(a)
        self._publish(b)
        self._session("sa", self.marked, [a])
        self._session("sb", self.unmarked, [b])
        with mock.patch.object(logbook, "_TRANSCRIPT_BODY_MAX", 10):
            logbook._drain_transcripts(self.con, "http://x", "tok")
        self.assertEqual(self._row("SELECT transcript_error FROM session_sync WHERE session_id='sa'")[0],
                         logbook._TRANSCRIPT_TOO_BIG)                       # control: la marcada sí avisa
        self.assertIsNone(self._row("SELECT transcript_error FROM session_sync WHERE session_id='sb'")[0])

    def test_reentrada_al_ganar_el_marcador_sube_todo_lo_acumulado(self):
        repo = _make_repo(self.base, "tarde", False)
        w = _add_req(self.con, "t", repo, "st")
        path = self._session("st", repo, [w])
        logbook._drain_works(self.con, "http://x", "tok")
        logbook._drain_transcripts(self.con, "http://x", "tok")
        self.assertEqual(self.central.calls, [])
        _mark(repo)
        logbook._drain_works(self.con, "http://x", "tok")
        logbook._drain_transcripts(self.con, "http://x", "tok")
        sent = self.central.published("/transcript")
        self.assertEqual([(p["session_id"], p["byte_from"], p["byte_to"]) for p in sent],
                         [("st", 0, os.path.getsize(path))])


class TestAdopcionYBackfill(_DrainBase):

    def _orphan(self, sid, root):
        d = os.path.join(self.home, ".claude", "projects", "p")
        os.makedirs(d, exist_ok=True)
        path = _jsonl(os.path.join(d, f"{sid}.jsonl"), root)
        logbook._index_local(self.con, sid, None, path)
        self.con.commit()
        return path

    def test_critico_adopcion_sin_opt_in_no_crea_work(self):
        self._orphan("dentro", self.marked)
        self._orphan("fuera", self.home)
        index = logbook._JsonlIndex(self.home)
        logbook._backfill_sessions(self.con, index, logbook._OptIn(self.con, index))
        works = [r[0] for r in self.con.execute("SELECT claude_session_id FROM work")]
        rows = [r[0] for r in self.con.execute("SELECT session_id FROM session_sync")]
        self.assertEqual((works, rows), (["dentro"], ["dentro"]))
        self.assertEqual(self._row("SELECT root_cwd FROM session_sync WHERE session_id='dentro'")[0], self.marked)

    def test_backfill_completa_root_cwd_una_vez(self):
        w = _add_req(self.con, "a", self.marked, "S")
        path = self._session("S", self.marked, [w])
        self.con.execute("UPDATE session_sync SET root_cwd=NULL")             # fila anterior a 6.14.2
        self.con.commit()
        logbook._backfill_sessions(self.con, None)
        self.assertEqual(self._row("SELECT root_cwd FROM session_sync WHERE session_id='S'")[0], self.marked)
        os.remove(path)                                                       # el .jsonl se borra después
        self.assertTrue(logbook._OptIn(self.con).session("S"))


class TestSyncStatusOptIn(_DrainBase):

    def _escenario(self):
        a = _add_req(self.con, "a", self.marked, "sa")
        b = _add_req(self.con, "b", self.unmarked, "sb")
        self.con.execute("UPDATE work SET last_error='publish: HTTP 500'")
        self.con.commit()
        pub = _add_req(self.con, "pub", self.unmarked, "sp")
        self._publish(pub)
        for sid, root, wid in (("sa", self.marked, a), ("sb", self.unmarked, b), ("sp", self.unmarked, pub)):
            self._session(sid, root, [wid])
        self.con.execute("UPDATE session_sync SET transcript_error='transcript: HTTP 500'")
        self.con.commit()
        return a, b

    def test_lo_que_queda_local_no_se_lista(self):
        a, _ = self._escenario()
        optin = logbook._OptIn(self.con)
        works = logbook._sync_status_rows(self.con, True, optin)
        sessions = logbook._sync_status_sessions(self.con, None, True, optin)
        self.assertEqual([w["local_id"] for w in works], [a])
        self.assertEqual([s["session_id"] for s in sessions], ["sa"])
        self.assertEqual(optin.hidden, {"works": 1, "sessions": 2})            # b; sb y sp

    def test_sin_central_no_filtra(self):
        self._escenario()
        works = logbook._sync_status_rows(self.con, False, None)
        sessions = logbook._sync_status_sessions(self.con, None, False, None)
        self.assertEqual(len(works), 2)                                          # a y b, con last_error
        self.assertEqual(sorted(s["session_id"] for s in sessions), ["sa", "sb", "sp"])

    def test_jsonl_borrado_sin_opt_in_no_es_perdida(self):
        w = _add_req(self.con, "b", self.unmarked, "sb")
        path = self._session("sb", self.unmarked, [w])
        logbook._index_local(self.con, "sb", None, path)
        self.con.commit()
        os.remove(path)
        optin = logbook._OptIn(self.con)
        self.assertEqual(logbook._sync_status_sessions(self.con, None, True, optin), [])
        self.assertEqual(optin.hidden["sessions"], 1)


class TestCapturaConCentral(_DrainBase):

    def test_captura_real_reatribuye_al_req_con_opt_in(self):
        mem = os.path.join(self.home, ".claude", "projects", _db_shared.encode_cwd(self.marked), "memory")
        os.makedirs(mem)
        for i, (name, repo) in enumerate((("con", self.marked), ("sin", f"{self.unmarked} (rama `main`)"))):
            f = os.path.join(mem, f"active_p_{name}.md")                    # 'sin' queda con el mtime mayor
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(f"- **Nombre:** {name}\n- **Path del proyecto:** {repo}\n- **Estado:** En progreso\n")
            os.utime(f, (time.time() - 100 + i, time.time() - 100 + i))
        t = _jsonl(os.path.join(self.base, "S.jsonl"), self.marked)
        argv = ["logbook.py", "S", self.marked, t, "Stop", NEB_ROOT, self.home]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(logbook, "_maybe_spawn_sync", lambda *a, **k: None):
            logbook.main()
            self.con.execute("UPDATE work SET remote_id=100+id, dirty=0")    # ambos publicados antes del fix
            self.con.commit()
            logbook.main()
        row = self._row("SELECT w.req_slug, s.root_cwd FROM session_sync s JOIN work w ON w.id = s.work_id "
                        "WHERE s.session_id='S'")
        self.assertEqual(tuple(row), ("con", self.marked))


class TestSyncMainCableado(_DrainBase):

    def test_sync_main_aplica_el_opt_in_en_las_tres_rutas(self):
        req = _add_req(self.con, "a", self.marked, "home")
        self._session("home", self.home, [req])                              # REQ marcado, sesión de home
        d = os.path.join(self.home, ".claude", "projects", "p")
        os.makedirs(d)
        pe = _jsonl(os.path.join(d, "E.jsonl"), self.marked)
        e = logbook._upsert_exploratory(self.con, "E", "dev", "maq", "", None, None, self.marked, pe)
        logbook._register_session(self.con, "E", pe, [e])
        po = _jsonl(os.path.join(d, "O.jsonl"), self.home)                   # huérfana de home
        logbook._index_local(self.con, "O", None, po)
        self.con.commit()
        logbook.sync_main([NEB_ROOT, self.home])
        self.assertEqual(sorted(p["mode"] for p in self.central.published("/work/publish")), ["exploratory", "req"])
        self.assertEqual(self._uploaded(), ["E"])
        self.assertIsNone(self._row("SELECT 1 FROM work WHERE claude_session_id='O'"))


class TestMigracionRootCwd(unittest.TestCase):

    def test_db_de_6_14_1_gana_la_columna_y_conserva_sus_filas(self):
        d = tempfile.mkdtemp(prefix="neb-test-mig-")
        db = os.path.join(d, "neb.db")
        with open(SCHEMA, encoding="utf-8") as fh:
            ddl = fh.read()
        old = ddl.replace("  updated_at          TEXT NOT NULL,\n  root_cwd            TEXT", "  updated_at          TEXT NOT NULL")
        self.assertNotEqual(old, ddl)
        raw = sqlite3.connect(db)
        raw.executescript(old)
        raw.execute("INSERT INTO session_sync (session_id, synced_byte, updated_at) VALUES ('S', 7, 'x')")
        raw.commit()
        raw.close()
        con = _db_shared._connect(db, SCHEMA)
        self.assertIsNotNone(con)
        cols = {r[1] for r in con.execute("PRAGMA table_info(session_sync)")}
        self.assertIn("root_cwd", cols)
        self.assertEqual(tuple(con.execute("SELECT synced_byte, root_cwd FROM session_sync").fetchone()), (7, None))
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
