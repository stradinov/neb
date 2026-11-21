#!/usr/bin/env python3
"""test_logbook_cli_y_captura.py — CLI en UTF-8 y captura real del work y de su sesión.

  • `logbook.py list` no queda vacío con stdout en cp1252 (caracteres fuera de la página).
  • _upsert_req refresca repo_path con el «Path del proyecto» vigente; vacío conserva el anterior.
  • La captura (logbook.main) registra el work del REQ activo y la fila de su sesión (ruta y cursor).

Framework: unittest (stdlib). DBs, repos y home temporales; nunca toca ~/.claude ni la red.
  py -m unittest tests.test_logbook_cli_y_captura
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
NEB_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, LIB)

import _db_shared
import logbook

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")


def _jsonl(path, cwd, turns=1):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "file-history-snapshot", "snapshot": {}}) + "\n")
        for i in range(turns):
            f.write(json.dumps({"type": "user", "cwd": cwd, "message": {"content": f"hola {i}"}}) + "\n")
    return path


def _add_req(con, project, repo_path, session_id, transcript_path=None):
    return logbook._upsert_req(con, project, "req-" + project, "maq", "En progreso", "main", "abc",
                               repo_path, "", "{}", session_id, transcript_path)


class TestCliUtf8(unittest.TestCase):

    def test_list_survives_cp1252_stdout(self):
        home = tempfile.mkdtemp(prefix="neb-test-cli-")
        os.makedirs(os.path.join(home, ".claude"))
        con = _db_shared._connect(_db_shared.resolve_db_path(home), SCHEMA)
        _add_req(con, "proj→uno", "", "s1")
        con.commit()
        con.close()

        env = {k: v for k, v in os.environ.items()
               if not k.startswith("NEB_") and k not in ("PYTHONUTF8", "CLAUDE_PLUGIN_ROOT")}
        env.update(HOME=home, USERPROFILE=home, NEB_HOME=NEB_ROOT, PYTHONIOENCODING="cp1252")
        r = subprocess.run([sys.executable, os.path.join(LIB, "logbook.py"), "list"],
                           capture_output=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertNotEqual(r.stdout.strip(), b"", f"stdout vacío; stderr={r.stderr!r}")
        self.assertIn("proj→uno", r.stdout.decode("utf-8"))


class _Base(unittest.TestCase):

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="neb-test-captura-")
        self.repo = os.path.join(self.base, "repo")
        self.otro = os.path.join(self.base, "otro")
        os.makedirs(self.repo)
        os.makedirs(self.otro)
        self.home = os.path.join(self.base, "home")
        os.makedirs(os.path.join(self.home, ".claude"))
        self.con = _db_shared._connect(_db_shared.resolve_db_path(self.home), SCHEMA)
        self.addCleanup(self.con.close)

    def _row(self, sql, *args):
        return self.con.execute(sql, args).fetchone()


class TestUpsertReq(_Base):

    def test_upsert_req_refreshes_repo_path(self):
        wid = _add_req(self.con, "wt", self.otro, "s1")
        _add_req(self.con, "wt", self.repo, "s2")       # el REQ pasa a otro checkout
        _add_req(self.con, "wt", "", "s3")              # memoria sin ruta: conserva la vigente
        self.con.commit()
        self.assertEqual(self._row("SELECT repo_path, claude_session_id FROM work WHERE id=?", wid),
                         (self.repo, "s3"))
        self.assertEqual(self._row("SELECT count(*) FROM work")[0], 1)


class TestCapturaReal(_Base):

    def test_captura_real_registra_el_work_y_la_sesion_con_su_cursor(self):
        mem = os.path.join(self.home, ".claude", "projects", _db_shared.encode_cwd(self.repo), "memory")
        os.makedirs(mem)
        with open(os.path.join(mem, "active_p_con.md"), "w", encoding="utf-8") as fh:
            fh.write(f"- **Nombre:** con\n- **Path del proyecto:** {self.repo}\n- **Estado:** En progreso\n")
        t = _jsonl(os.path.join(self.base, "S.jsonl"), self.repo)
        argv = ["logbook.py", "S", self.repo, t, "Stop", NEB_ROOT, self.home]
        with mock.patch.object(sys, "argv", argv):
            logbook.main()
        self.assertEqual(self._row("SELECT mode, req_slug, req_state, repo_path, claude_session_id, transcript_path "
                                   "FROM work"),
                         ("req", "con", "En progreso", self.repo, "S", t))
        self.assertEqual(self._row("SELECT transcript_path, read_byte FROM session_sync WHERE session_id='S'"),
                         (t, os.path.getsize(t)))


if __name__ == "__main__":
    unittest.main()
