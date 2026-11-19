#!/usr/bin/env python3
"""test_logbook_req_link.py — REQ vinculado en la bitácora local (REQ neb-trazabilidad-indice-commits, E2).

Cubre hooks/lib/req_link.py y su enganche en hooks/lib/logbook.py (filas 2 a 12 del plan de pruebas de E2):
  • esquema: 3 tablas y 2 índices nuevos, base legada, doble _connect, `work` sin cambio
  • patrones CHANGE_RE y LINK_CMD_RE
  • vínculo por escritura (Write/Edit/MultiEdit) y no por lectura; barrido; choque de fecha; worktrees
  • CLI link / unlink / trace, siempre locales; idempotencia y sentencias
  • commits en `trace` leídos de git al consultar (solo lo alcanzable desde origin, trailer exacto)
  • costo del hook (llamadas a git), presupuesto de 4 s y aislamiento de las fallas de E2

Infraestructura: repos git temporales con remoto bare (url https://example.invalid/o/<repo>.git para fijar el
`project` y pushurl al bare para publicar), homes y bases temporales, transcripts sintéticos. Nunca toca
~/.claude ni la copia de neb. Las pruebas con git llevan skipUnless(shutil.which("git")).

Framework: unittest (stdlib).
  py -m unittest discover -s hooks/tests -p test_logbook_req_link.py
"""

import contextlib
import gc
import io
import itertools
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "lib"))
sys.path.insert(0, LIB)

import _db_shared  # noqa: E402
import logbook  # noqa: E402
import req_link  # noqa: E402

SCHEMA = os.path.abspath(os.path.join(HERE, "..", "logbook-schema.sql"))
GUIDE = os.path.abspath(os.path.join(HERE, "..", ".."))       # NEB_HOME de esta copia
LOGBOOK_PY = os.path.join(LIB, "logbook.py")
NO_CENTRAL = {"NEB_LOGBOOK_ENDPOINT": "", "NEB_LOGBOOK_TOKEN": ""}
FAKE_ENV = {"NEB_LOGBOOK_ENDPOINT": "http://central.invalid", "NEB_LOGBOOK_TOKEN": "tok-de-prueba-0123456789"}
HAS_GIT = shutil.which("git") is not None
F = "2026-01-15"           # fecha base de los Change MD de prueba
F2 = "2026-01-20"

_GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
_ENV_PATCH = mock.patch.dict(os.environ)


def setUpModule():
    _ENV_PATCH.start()
    for k in _GIT_VARS:
        os.environ.pop(k, None)
    os.environ["GIT_TERMINAL_PROMPT"] = "0"


def tearDownModule():
    _ENV_PATCH.stop()


# --------------------------------------------------------------------------- utilidades de disco

def _rmtree(path):
    """rmtree tolerante a los objetos de solo lectura de git en Windows."""
    def onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=onerror)


def _fwd(p):
    return p.replace("\\", "/")


def _norm(p):
    return os.path.normcase(os.path.realpath(p))


# --------------------------------------------------------------------------- git

def _g(cwd, *args, check=True):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL)
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} falló: {r.stderr}")
    return r.stdout.strip()


def _gitrepo(tmp, name="repo", origin=True, project=None):
    """Repo con un commit inicial. Con origin: url https://example.invalid/o/<project>.git (fija el
    `project`) y pushurl a un bare temporal; el push inicial deja refs/remotes/origin/main."""
    repo = os.path.join(tmp, name)
    hooks = os.path.join(tmp, "sin-hooks")
    os.makedirs(hooks, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True, stdin=subprocess.DEVNULL)
    for k, v in (("user.name", "t"), ("user.email", "t@t"), ("commit.gpgsign", "false"),
                 ("core.autocrlf", "false"), ("core.hooksPath", _fwd(hooks))):
        _g(repo, "config", k, v)
    with open(os.path.join(repo, "README"), "w", encoding="utf-8") as fh:
        fh.write("x\n")
    _g(repo, "add", "README")
    _g(repo, "commit", "-q", "-m", "inicial")
    if origin:
        bare = os.path.join(tmp, (project or name) + "-remote.git")
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True, stdin=subprocess.DEVNULL)
        _g(repo, "remote", "add", "origin", f"https://example.invalid/o/{project or name}.git")
        _g(repo, "config", "remote.origin.pushurl", _fwd(bare))
        _g(repo, "push", "-q", "origin", "main")
    return repo


_SEQ = itertools.count()


def _commit(repo, msg):
    n = next(_SEQ)
    with open(os.path.join(repo, f"f{n}.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"{n}\n")
    _g(repo, "add", f"f{n}.txt")
    _g(repo, "commit", "-q", "-m", msg)
    return _g(repo, "rev-parse", "HEAD")


def _push(repo, force=False):
    _g(repo, "push", "-q", *(["-f"] if force else []), "origin", "HEAD:main")


def _project(name):
    return f"example.invalid/o/{name}"


def _change_md(root, nombre, fecha=F, sub="changes"):
    p = os.path.join(root, sub, f"{fecha}-{nombre}.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(f"# {nombre}\n")
    return p


# --------------------------------------------------------------------------- transcripts

def _assistant(mid, ts, model="m-a", inp=1, out=10, cw=0, cw1=0, cr=0, tools=(), repeat=1):
    """Líneas de un mensaje del asistente: una por bloque, todas con el mismo id y usage (como el transcript)."""
    usage = {"input_tokens": inp, "output_tokens": out, "cache_creation_input_tokens": cw,
             "cache_read_input_tokens": cr,
             "cache_creation": {"ephemeral_1h_input_tokens": cw1, "ephemeral_5m_input_tokens": cw - cw1}}
    blocks = [{"type": "text", "text": "x"}] * repeat + [
        {"type": "tool_use", "name": n, "input": i} for n, i in tools]
    return [json.dumps({"type": "assistant", "timestamp": ts,
                        "message": {"id": mid, "model": model, "usage": usage, "content": [b]}})
            for b in blocks]


def _w(path):
    return ("Write", {"file_path": path, "content": "# x\n"})


def _bash(cmd, tool="Bash"):
    return (tool, {"command": cmd})


def _lines(tools):
    user = json.dumps({"type": "user", "message": {"role": "user", "content": "hola"}})
    return [user] + _assistant(f"m{next(_SEQ)}", "2026-11-19T10:00:00.000Z", tools=tools)


def _append(transcript, tools):
    os.makedirs(os.path.dirname(transcript), exist_ok=True)
    with open(transcript, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(_lines(tools)) + "\n")
    return transcript


# --------------------------------------------------------------------------- base y captura

def _home(tmp):
    h = os.path.join(tmp, "home")
    os.makedirs(os.path.join(h, ".claude", "projects"), exist_ok=True)
    return h


def _db(home):
    return _db_shared._connect(_db_shared.resolve_db_path(home), SCHEMA)


def _q(home, sql, params=()):
    con = _db(home)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _count(home, table, where="", params=()):
    return _q(home, f"SELECT COUNT(*) FROM {table} {where}", params)[0][0]


def _capturar(home, cwd, sid, transcript, event="Stop"):
    """Captura REAL (logbook.main) con argv del hook y sin central en el entorno. Devuelve el stderr."""
    argv = ["logbook.py", sid, cwd, transcript, event, GUIDE, home]
    err = io.StringIO()
    with mock.patch.dict(os.environ, NO_CENTRAL), mock.patch.object(sys, "argv", argv), \
            mock.patch.object(sys, "stderr", err):
        logbook.main()
    return err.getvalue()


def _cli(verb, args, home, stderr=None):
    """Llama a req_link.cli_<verb> con la base temporal; devuelve el JSON de stdout."""
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", stderr or io.StringIO()):
        getattr(req_link, "cli_" + verb)(list(args), lambda: _db(home))
    return json.loads(out.getvalue())


def _seed(con, project, nombre, fecha=F, change_md=None, linked_by="cli"):
    ts = "2026-01-15T00:00:00Z"
    cur = con.execute(
        "INSERT INTO req_link (project, nombre, fecha, change_md, linked_by, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?)", (project, nombre, fecha, change_md or f"changes/{fecha}-{nombre}.md",
                                   linked_by, ts, ts))
    con.commit()
    return cur.lastrowid


def _snapshot_req(home):
    return {t: _q(home, f"SELECT * FROM {t} ORDER BY 1, 2") for t in ("req_link", "req_repo", "req_session")}


@contextlib.contextmanager
def _contador(tc):
    """Cuenta las llamadas a req_link._git (el único punto de git del módulo) sin cambiar su efecto."""
    tc.assertIs(sys.modules["req_link"], req_link)
    with mock.patch.object(req_link, "_git", wraps=req_link._git) as m:
        yield m


def _gargs(call):
    return call.args[1] if len(call.args) > 1 else call.kwargs["args"]


def _logs(m):
    return [c for c in m.call_args_list if _gargs(c)[:1] == ["log"]]


def _revparses(m):
    return [c for c in m.call_args_list if _gargs(c)[:1] == ["rev-parse"]]


def _git_lento(common_dir=None):
    """_git que, en las llamadas con --git-dir=<common_dir> (o en todas), duerme más que el timeout
    recibido y devuelve timeout; las demás llamadas van al _git real."""
    real = req_link._git
    seen = []

    def fake(prefix, args, timeout):
        if common_dir is None or prefix == ["--git-dir=" + common_dir]:
            seen.append(timeout)
            time.sleep(timeout + 0.05)
            return None, "", "timeout"
        return real(prefix, args, timeout)
    fake.seen = seen
    return fake


class _ConEnvuelta:
    """Conexión que delega todo; registra cada execute, el índice del commit de la captura y el valor de
    in_transaction al cerrar. Con raise_on, lanza IntegrityError en el execute cuyo SQL lo contenga."""
    _OWN = ("_con", "log", "commit_at", "closed_in_tx", "raise_on", "raised", "mark")

    def __init__(self, con, raise_on=None):
        object.__setattr__(self, "_con", con)
        object.__setattr__(self, "log", [])
        object.__setattr__(self, "commit_at", None)
        object.__setattr__(self, "closed_in_tx", None)
        object.__setattr__(self, "raise_on", raise_on)
        object.__setattr__(self, "raised", 0)
        object.__setattr__(self, "mark", None)

    def __getattr__(self, name):
        return getattr(self._con, name)

    def __setattr__(self, name, value):
        if name in self._OWN:
            object.__setattr__(self, name, value)
        else:
            setattr(self._con, name, value)

    def execute(self, sql, params=()):
        self.log.append(sql)
        if self.raise_on and self.raise_on in sql:
            self.raised += 1
            raise sqlite3.IntegrityError("inyectada por la prueba")
        return self._con.execute(sql, params)

    def commit(self):
        if self.commit_at is None:
            self.commit_at = len(self.log)
        return self._con.commit()

    def close(self):
        self.closed_in_tx = self._con.in_transaction
        return self._con.close()


class _Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-test-reqlink-")
        self.addCleanup(_rmtree, self.tmp)
        self.home = _home(self.tmp)
        self.cwd = os.path.join(self.tmp, "cwd")
        os.makedirs(self.cwd)

    def tr(self, sid):
        return os.path.join(self.home, ".claude", "projects", "x", f"{sid}.jsonl")

    def captura(self, sid, tools, event="Stop"):
        t = _append(self.tr(sid), tools)
        return _capturar(self.home, self.cwd, sid, t, event)

    def assertCapturaIntacta(self, sid):
        self.assertGreaterEqual(_count(self.home, "work"), 1)
        self.assertEqual(_count(self.home, "session_sync", "WHERE session_id=?", (sid,)), 1)
        self.assertEqual(_count(self.home, "session_sync", "WHERE session_id=? AND read_byte > 0", (sid,)), 1)

    def assertSinVinculo(self):
        for t in ("req_link", "req_repo", "req_session"):
            self.assertEqual(_count(self.home, t), 0, t)


# =========================================================================== fila 2: esquema

BASE_TABLES = {"event", "pending", "pending_link", "pending_note", "pending_topic", "session_sync", "topic",
               "topic_link", "work"}
WORK_COLS = ["id", "mode", "project", "req_slug", "owner", "lock_state", "takeover_by", "locked_at", "req_state",
             "branch", "head_commit", "repo_path", "change_md", "payload_json", "payload_version", "origin_dev",
             "origin_machine", "claude_session_id", "claude_session_name", "transcript_path", "created_at",
             "updated_at", "archived_at", "dirty", "synced_at", "remote_id", "conflict", "last_error",
             "last_error_at", "transcript_error", "transcript_error_at"]


class TestEsquema(unittest.TestCase):

    def _mem(self):
        m = sqlite3.connect(":memory:")
        with open(SCHEMA, encoding="utf-8") as fh:
            m.executescript(fh.read())
        return m

    def test_sql_vivo_crea_las_3_tablas_y_sus_indices_y_nada_mas(self):
        m = self._mem()
        tables = {r[0] for r in m.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables - BASE_TABLES, {"req_link", "req_repo", "req_session"})
        self.assertTrue(BASE_TABLES <= tables)
        idx = {r[0]: (r[1], r[2]) for r in m.execute(
            "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name IN ('req_link','req_repo','req_session')")}
        self.assertEqual(set(idx), {"uq_req_link", "idx_req_link_nombre"})
        self.assertIn("UNIQUE", idx["uq_req_link"][1])
        self.assertEqual([r[2] for r in m.execute("PRAGMA index_info(uq_req_link)")], ["project", "nombre"])
        self.assertEqual([r[2] for r in m.execute("PRAGMA index_info(idx_req_link_nombre)")], ["nombre"])
        cols = {t: [r[1] for r in m.execute(f"PRAGMA table_info({t})")]
                for t in ("req_link", "req_repo", "req_session")}
        self.assertEqual(cols["req_link"], ["id", "project", "nombre", "fecha", "change_md", "linked_by",
                                            "created_at", "updated_at"])
        self.assertEqual(cols["req_repo"], ["req_id", "common_dir", "path", "project"])
        self.assertEqual(cols["req_session"], ["req_id", "session_id", "via", "first_seen_at", "last_seen_at"])

    def test_work_no_cambia_de_columnas(self):
        m = self._mem()
        self.assertEqual([r[1] for r in m.execute("PRAGMA table_info(work)")], WORK_COLS)
        tmp = tempfile.mkdtemp(prefix="neb-test-reqlink-")
        self.addCleanup(_rmtree, tmp)
        con = _db_shared._connect(os.path.join(tmp, "neb.db"), SCHEMA)
        self.addCleanup(con.close)
        self.assertEqual([r[1] for r in con.execute("PRAGMA table_info(work)")], WORK_COLS)

    def test_base_legada_las_gana_y_doble_connect_sin_error(self):
        tmp = tempfile.mkdtemp(prefix="neb-test-reqlink-")
        self.addCleanup(_rmtree, tmp)
        path = os.path.join(tmp, "neb-logbook.db")
        con = _db_shared._connect(path, SCHEMA)
        con.execute("PRAGMA foreign_keys=OFF")
        for t in ("req_session", "req_repo", "req_link"):
            con.execute(f"DROP TABLE {t}")
        con.commit()
        self.assertFalse(_db_shared._table_exists(con, "req_link"))
        con.close()
        con = _db_shared._connect(path, SCHEMA)
        self.assertIsNotNone(con)
        for t in ("req_link", "req_repo", "req_session"):
            self.assertTrue(_db_shared._table_exists(con, t), t)
        con.close()
        con2 = _db_shared._connect(path, SCHEMA)          # doble _connect: sin error
        self.assertIsNotNone(con2)
        self.assertEqual(con2.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(con2.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        con2.close()


# =========================================================================== fila 3: patrones

def _cli_keys(cmd):
    return {k for k in (req_link.name_of_path(m.group(1)) for m in req_link.LINK_CMD_RE.finditer(cmd)) if k}


class TestPatrones(unittest.TestCase):

    def test_change_re_acepta_ambos_separadores_e_incident(self):
        self.assertEqual(req_link.name_of_path("C:\\r\\changes\\2026-01-15-x.md"), (F, "x"))
        self.assertEqual(req_link.name_of_path("/r/changes/2026-01-15-x.md"), (F, "x"))
        self.assertEqual(req_link.name_of_path("changes/2026-01-15-x.md"), (F, "x"))
        self.assertEqual(req_link.name_of_path("/r/changes/2026-01-15-incident-caida-db.md"),
                         (F, "incident-caida-db"))

    def test_change_re_rechaza(self):
        for p in ("/r/changes/plans/2026-01-15-x.md", "/r/changes/2026-01-15-Mayus.md",
                  "/r/changes/2026-01-15-con espacio.md", "/r/changes/2026-01-15-x.md.bak",
                  "/r/mychanges/2026-01-15-x.md", "C:\\r\\mychanges\\2026-01-15-x.md",
                  "/r/changes/2026-01-15-x.md/y", "/r/Changes/2026-01-15-x.md"):
            with self.subTest(p=p):
                self.assertIsNone(req_link.name_of_path(p))

    def test_pago_y_doble_pago_no_se_confunden(self):
        self.assertEqual(req_link.name_of_path("/r/changes/2026-01-15-pago.md"), (F, "pago"))
        self.assertEqual(req_link.name_of_path("/r/changes/2026-01-15-doble-pago.md"), (F, "doble-pago"))
        self.assertEqual(_cli_keys("LB link changes/2026-01-15-doble-pago.md"), {(F, "doble-pago")})

    def test_link_cmd_re_casa(self):
        casos = {
            "LB link changes/2026-01-15-x.md": {(F, "x")},
            'py "C:/neb/hooks/lib/logbook.py" link changes/2026-01-15-x.md': {(F, "x")},
            "py /neb/hooks/lib/logbook.py link /r/changes/2026-01-15-x.md": {(F, "x")},
            'LB link "C:\\r\\changes\\2026-01-15-x.md"': {(F, "x")},
            "LB link 'C:/r/changes/2026-01-15-x.md' --repo /r2": {(F, "x")},
            "LB link changes/2026-01-15-a.md && LB link changes/2026-01-15-b.md": {(F, "a"), (F, "b")},
            'echo "LB link changes/2026-01-15-x.md"': {(F, "x")},          # límite documentado
        }
        for cmd, esperado in casos.items():
            with self.subTest(cmd=cmd):
                self.assertEqual(_cli_keys(cmd), esperado)

    def test_link_cmd_re_no_casa(self):
        for cmd in ("LB linked changes/2026-01-15-x.md", "MYLB link changes/2026-01-15-x.md",
                    "LB link changes/plans/2026-01-15-x.md", "my-LB link changes/2026-01-15-x.md",
                    "LB show changes/2026-01-15-x.md", "sed -n 1,5p changes/2026-01-15-x.md"):
            with self.subTest(cmd=cmd):
                self.assertEqual(_cli_keys(cmd), set())

    def test_scan_chunk_sobre_input_command(self):
        lines = _lines([_bash("LB link changes/2026-01-15-a.md && LB link changes/2026-01-15-b.md"),
                        _bash('py "C:/n/hooks/lib/logbook.py" link "C:\\r\\changes\\2026-01-15-c.md"',
                              tool="PowerShell"),
                        _bash("LB linked changes/2026-01-15-d.md"),
                        _bash("LB link changes/plans/2026-01-15-e.md")])
        ev = req_link.scan_chunk("\n".join(lines) + "\n")
        self.assertEqual(ev.cli, {(F, "a"), (F, "b"), (F, "c")})
        self.assertEqual(ev.writes, {})


# =========================================================================== fila 4: vínculo por escritura

@unittest.skipUnless(HAS_GIT, "requiere git")
class TestVinculoPorEscritura(_Base):

    def setUp(self):
        super().setUp()
        self.repo = _gitrepo(self.tmp)
        self.cm = _change_md(self.repo, "x")

    def _assert_vinculado(self, nombre="x", fecha=F, via="write", sid="s1"):
        (link,) = _q(self.home, "SELECT id, project, nombre, fecha, change_md, linked_by FROM req_link "
                                "WHERE nombre=?", (nombre,))
        self.assertEqual(link[1:], (_project("repo"), nombre, fecha, f"changes/{fecha}-{nombre}.md", "write"))
        (repo,) = _q(self.home, "SELECT req_id, common_dir, path, project FROM req_repo WHERE req_id=?",
                     (link[0],))
        self.assertEqual(repo[1], _norm(os.path.join(self.repo, ".git")))
        self.assertEqual(repo[2], _norm(self.repo))
        self.assertEqual(repo[3], _project("repo"))
        (ses,) = _q(self.home, "SELECT req_id, session_id, via FROM req_session WHERE req_id=?", (link[0],))
        self.assertEqual(ses, (link[0], sid, via))
        return link[0]

    def test_critico_write_edit_multiedit_vinculan(self):
        for tool in ("Write", "Edit", "MultiEdit"):
            with self.subTest(tool=tool):
                home = _home(os.path.join(self.tmp, "h-" + tool))
                cm = _change_md(self.repo, "req-" + tool.lower())
                inp = {"file_path": cm, "old_string": "a", "new_string": "b"}
                t = _append(os.path.join(home, ".claude", "projects", "x", "s1.jsonl"), [(tool, inp)])
                _capturar(home, self.cwd, "s1", t, "Stop")
                (link,) = _q(home, "SELECT nombre, linked_by FROM req_link")
                self.assertEqual(link, ("req-" + tool.lower(), "write"))
                self.assertEqual(_count(home, "req_repo"), 1)
                self.assertEqual(_q(home, "SELECT session_id, via FROM req_session"), [("s1", "write")])

    def test_critico_write_vincula_con_las_tres_tablas(self):
        self.captura("s1", [_w(self.cm)])
        self._assert_vinculado()
        self.assertCapturaIntacta("s1")

    def test_critico_lectura_no_vincula(self):
        for tools in ([("Read", {"file_path": self.cm})],
                      [("Grep", {"pattern": "x", "path": self.cm})],
                      [_bash(f"sed -n 1,5p {self.cm}")],
                      [_bash(f"sed -n 1,5p '{self.cm}'", tool="PowerShell")]):
            with self.subTest(tool=tools[0][0]):
                self.captura("s-" + tools[0][0] + str(next(_SEQ)), tools)
                self.assertSinVinculo()

    def test_write_en_plans_no_vincula(self):
        self.captura("s1", [_w(_change_md(self.repo, "x", sub=os.path.join("changes", "plans")))])
        self.assertSinVinculo()

    def test_repo_sin_origin_no_vincula(self):
        repo = _gitrepo(self.tmp, "sin-origin", origin=False)
        self.captura("s1", [_w(_change_md(repo, "y"))])
        self.assertSinVinculo()
        self.assertCapturaIntacta("s1")

    def test_session_end_no_consulta_la_base(self):
        envueltas = []

        def connect(path, schema):
            envueltas.append(_ConEnvuelta(_db_shared._connect(path, schema)))
            return envueltas[-1]
        spy = mock.Mock(wraps=req_link.after_capture)
        with mock.patch.object(logbook, "_connect", connect), mock.patch.object(req_link, "after_capture", spy):
            self.captura("s1", [_w(self.cm)], event="SessionEnd")
            self.assertEqual(spy.call_count, 0)
            (con,) = envueltas
            self.assertIsNotNone(con.commit_at)
            self.assertEqual(con.log[con.commit_at:], [])      # 0 execute de E2
            # muestra positiva: el mismo envoltorio sí ve los execute de E2 en un Stop
            self.captura("s1", [_w(self.cm)], event="Stop")
            self.assertEqual(spy.call_count, 1)
            self.assertGreater(len(envueltas[1].log) - envueltas[1].commit_at, 0)
        self.assertEqual(_count(self.home, "req_session"), 1)

    def test_precompact_registra_y_liga_igual_que_stop(self):
        self.captura("s1", [_w(self.cm)], event="PreCompact")
        self._assert_vinculado()

    def test_worktree_y_principal_dan_el_mismo_common_dir(self):
        wt = os.path.join(self.tmp, "wt")
        _g(self.repo, "worktree", "add", "-q", "-b", "rama-wt", wt)
        cm_wt = _change_md(wt, "x")
        self.captura("s-wt", [_w(cm_wt)])
        self.captura("s-main", [_w(self.cm)])
        esperado = _norm(os.path.join(self.repo, ".git"))
        self.assertEqual(_q(self.home, "SELECT common_dir FROM req_repo"), [(esperado,)])
        self.assertEqual(_count(self.home, "req_link"), 1)
        self.assertEqual(sorted(r[0] for r in _q(self.home, "SELECT session_id FROM req_session")),
                         ["s-main", "s-wt"])
        # y por separado, desde un worktree solo
        home2 = _home(os.path.join(self.tmp, "h2"))
        t = _append(os.path.join(home2, ".claude", "projects", "x", "s.jsonl"), [_w(cm_wt)])
        _capturar(home2, self.cwd, "s", t)
        self.assertEqual(_q(home2, "SELECT common_dir FROM req_repo"), [(esperado,)])

    def test_choque_de_fecha_en_el_mismo_project(self):
        r = _cli("link", [self.cm], self.home)
        self.assertTrue(r["ok"])
        cm2 = _change_md(self.repo, "x", fecha=F2)
        with _contador(self) as m:
            err = self.captura("s1", [_w(cm2)])
        self.assertLessEqual(len(_revparses(m)), 1)          # a lo más 1 resolve_repo
        self.assertEqual(_count(self.home, "req_link"), 1)
        self.assertEqual(_q(self.home, "SELECT fecha FROM req_link"), [(F,)])
        self.assertEqual(_count(self.home, "req_session"), 0)
        self.assertIn("ya vinculado con fecha " + F, err)

    def test_fila_previa_reusa_su_id(self):
        con = _db(self.home)
        _seed(con, "otro/proyecto/cualquiera", "otro-req")      # id 1 lo ocupa otro REQ
        con.close()
        r = _cli("link", [self.cm], self.home)
        self.assertGreater(r["id"], 1)
        self.captura("s1", [_w(self.cm)])
        self.assertEqual(_q(self.home, "SELECT DISTINCT req_id FROM req_repo"), [(r["id"],)])
        self.assertEqual(_q(self.home, "SELECT req_id, via FROM req_session"), [(r["id"], "write")])
        self.assertEqual(_count(self.home, "req_link"), 2)

    def test_barrido_tres_no_registra_y_liga_los_vinculados(self):
        ya = _change_md(self.repo, "ya-vinculado")
        _cli("link", [ya], self.home)
        nuevos = [_change_md(self.repo, n) for n in ("a", "b", "c")]
        err = self.captura("s1", [_w(p) for p in nuevos] + [_w(ya)])
        self.assertEqual([r[0] for r in _q(self.home, "SELECT nombre FROM req_link")], ["ya-vinculado"])
        self.assertEqual(_q(self.home, "SELECT s.session_id, s.via FROM req_session s JOIN req_link l "
                                       "ON l.id = s.req_id WHERE l.nombre='ya-vinculado'"), [("s1", "write")])
        self.assertIn("barrido", err)

    def test_barrido_dos_registra_los_dos(self):
        nuevos = [_change_md(self.repo, n) for n in ("a", "b")]
        self.captura("s1", [_w(p) for p in nuevos])
        self.assertEqual(sorted(r[0] for r in _q(self.home, "SELECT nombre FROM req_link")), ["a", "b"])
        self.assertEqual(_count(self.home, "req_session"), 2)
        self.assertEqual(_count(self.home, "req_repo"), 2)


# =========================================================================== fila 5: vínculo por CLI

@unittest.skipUnless(HAS_GIT, "requiere git")
class TestVinculoPorCli(_Base):

    def setUp(self):
        super().setUp()
        self.repo = _gitrepo(self.tmp)
        self.cm = _change_md(self.repo, "x")

    def test_link_registra_sin_commits(self):
        r = _cli("link", [self.cm], self.home)
        self.assertTrue(r["ok"])
        self.assertNotIn("commits", json.dumps(r))
        self.assertEqual((r["project"], r["nombre"], r["fecha"], r["change_md"]),
                         (_project("repo"), "x", F, f"changes/{F}-x.md"))
        self.assertEqual(r["sesiones"], 0)
        self.assertEqual([x["common_dir"] for x in r["repos"]], [_norm(os.path.join(self.repo, ".git"))])
        self.assertEqual(_q(self.home, "SELECT linked_by FROM req_link"), [("cli",)])

    def test_link_errores_dan_ok_false_con_motivo(self):
        sin = _gitrepo(self.tmp, "sin-origin", origin=False)
        casos = [os.path.join(self.repo, "changes", f"{F}-no-existe.md"),
                 _change_md(self.repo, "Mayus"),
                 _change_md(self.repo, "y", sub=os.path.join("changes", "plans")),
                 _change_md(sin, "z")]
        for ruta in casos:
            with self.subTest(ruta=ruta):
                r = _cli("link", [ruta], self.home)
                self.assertIs(r["ok"], False)
                self.assertTrue(r.get("motivo"))
        _cli("link", [self.cm], self.home)
        r = _cli("link", [_change_md(self.repo, "x", fecha=F2)], self.home)
        self.assertEqual(r, {"ok": False, "motivo": f"nombre ya vinculado con fecha {F}"})
        self.assertEqual(_count(self.home, "req_link"), 1)

    def test_link_repetido_misma_fila_y_repo_extra(self):
        r1 = _cli("link", [self.cm], self.home)
        r2 = _cli("link", [self.cm], self.home)
        self.assertEqual(r1["id"], r2["id"])
        otro = _gitrepo(self.tmp, "otro")
        r3 = _cli("link", [self.cm, "--repo", otro], self.home)
        self.assertEqual(r3["id"], r1["id"])
        self.assertEqual(sorted(x["common_dir"] for x in r3["repos"]),
                         sorted([_norm(os.path.join(self.repo, ".git")), _norm(os.path.join(otro, ".git"))]))
        self.assertEqual({x["project"] for x in r3["repos"]}, {_project("repo"), _project("otro")})
        self.assertEqual(_count(self.home, "req_link"), 1)
        self.assertEqual(_count(self.home, "req_repo"), 2)

    def test_repo_invalido_va_a_avisos(self):
        r = _cli("link", [self.cm, "--repo", self.cwd], self.home)
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["avisos"]), 1)
        self.assertEqual(len(r["repos"]), 1)

    def test_repo_sin_directorio_va_a_avisos(self):
        r = _cli("link", [self.cm, "--repo"], self.home)
        self.assertTrue(r["ok"])
        self.assertEqual(r["avisos"], ["--repo sin directorio; se omite"])
        self.assertEqual(len(r["repos"]), 1)

    def test_change_md_conserva_mayusculas_del_directorio(self):
        cm = _change_md(self.repo, "y", sub=os.path.join("Docs", "changes"))
        r = _cli("link", [cm], self.home)
        self.assertTrue(r["ok"])
        self.assertEqual(r["change_md"], f"Docs/changes/{F}-y.md")

    def test_excepcion_en_el_verbo_sale_como_json(self):
        """JSON en stdout siempre (por cli_main): una excepción no deja la salida vacía, que el skill
        leería como «árbol anterior a estos verbos»."""
        def boom(*_a, **_k):
            raise sqlite3.OperationalError("database is locked")
        for argv in (["link", self.cm], ["trace", "x"], ["unlink", "x"]):
            out = io.StringIO()
            with mock.patch.dict(os.environ, NO_CENTRAL), mock.patch.object(logbook, "_db_for_cli", boom), \
                    mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                logbook.cli_main(argv)
            with self.subTest(verb=argv[0]):
                r = json.loads(out.getvalue())
                self.assertIs(r["ok"], False)
                self.assertIn("database is locked", r["motivo"])

    def test_sesiones_cuenta_solo_ligas_capturadas(self):
        r = _cli("link", [self.cm], self.home)
        self.assertEqual(r["sesiones"], 0)
        self.captura("s1", [_bash(f'LB link "{self.cm}"')])
        self.assertEqual(_q(self.home, "SELECT session_id, via FROM req_session"), [("s1", "cli")])
        self.assertEqual(_cli("link", [self.cm], self.home)["sesiones"], 1)

    def test_captura_con_link_de_req_inexistente_no_liga(self):
        self.captura("s1", [_bash(f"LB link {self.cm}")])
        self.assertSinVinculo()

    def test_link_solo_hace_las_llamadas_de_resolve_repo(self):
        with _contador(self) as m:
            _cli("link", [self.cm], self.home)
        self.assertEqual(m.call_count, 2)
        self.assertEqual(_logs(m), [])
        otro = _gitrepo(self.tmp, "otro")
        with _contador(self) as m:
            _cli("link", [self.cm, "--repo", otro], self.home)
        self.assertEqual(m.call_count, 4)
        self.assertEqual(_logs(m), [])

    def test_con_endpoint_queda_local(self):
        def forbidden(*_a, **_k):
            raise AssertionError("E2 no debe ir al central")
        http = mock.Mock(side_effect=forbidden)
        for argv in (["link", self.cm], ["trace", "x"], ["unlink", "x"]):
            out = io.StringIO()
            with mock.patch.dict(os.environ, FAKE_ENV), mock.patch.object(logbook, "_http", http), \
                    mock.patch.object(logbook, "_db_for_cli", lambda: _db(self.home)), \
                    mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                logbook.cli_main(argv)
            with self.subTest(verb=argv[0]):
                self.assertTrue(json.loads(out.getvalue())["ok"])
        self.assertEqual(http.call_count, 0)
        self.assertEqual(_count(self.home, "req_link"), 0)          # el unlink final borró lo local

    def test_verbos_en_cli_cmds(self):
        for v in ("link", "trace", "unlink"):
            self.assertIn(v, logbook.CLI_CMDS)

    def test_exit_0_siempre_por_subproceso(self):
        env = {k: v for k, v in os.environ.items() if k not in ("NEB_LOGBOOK_ENDPOINT", "NEB_LOGBOOK_TOKEN")}
        env.update(HOME=self.home, USERPROFILE=self.home, NEB_HOME=GUIDE, PYTHONDONTWRITEBYTECODE="1",
                   PYTHONIOENCODING="utf-8")
        for ruta, ok in ((self.cm, True), (os.path.join(self.repo, "changes", f"{F}-nada.md"), False)):
            p = subprocess.run([sys.executable, LOGBOOK_PY, "link", ruta], capture_output=True, env=env,
                               stdin=subprocess.DEVNULL)
            with self.subTest(ok=ok):
                self.assertEqual(p.returncode, 0)
                self.assertIs(json.loads(p.stdout.decode("utf-8"))["ok"], ok)
        self.assertEqual(_count(self.home, "req_link"), 1)


# =========================================================================== fila 6: desvincular

@unittest.skipUnless(HAS_GIT, "requiere git")
class TestDesvincular(_Base):

    def setUp(self):
        super().setUp()
        self.repo = _gitrepo(self.tmp)
        self.cm = _change_md(self.repo, "x")

    def _vincular(self):
        r = _cli("link", [self.cm], self.home)
        self.captura("s" + str(next(_SEQ)), [_w(self.cm)])
        self.assertEqual(_count(self.home, "req_session", "WHERE req_id=?", (r["id"],)), 1)
        return r["id"]

    def test_unlink_por_id_nombre_y_ruta(self):
        for como in ("id", "nombre", "ruta"):
            with self.subTest(como=como):
                req_id = self._vincular()
                arg = {"id": str(req_id), "nombre": "x", "ruta": self.cm}[como]
                r = _cli("unlink", [arg], self.home)
                self.assertEqual(r, {"ok": True, "id": req_id, "borrados": {"repos": 1, "sesiones": 1}})
                self.assertEqual(_count(self.home, "req_link"), 0)
                self.assertEqual(_count(self.home, "req_repo", "WHERE req_id=?", (req_id,)), 0)
                self.assertEqual(_count(self.home, "req_session", "WHERE req_id=?", (req_id,)), 0)
                self.assertEqual(_q(self.home, "PRAGMA foreign_key_check"), [])

    def test_nombre_en_dos_project_es_ambiguo_y_no_borra(self):
        otro = _gitrepo(self.tmp, "otro")
        a = _cli("link", [self.cm], self.home)["id"]
        b = _cli("link", [_change_md(otro, "x")], self.home)["id"]
        r = _cli("unlink", ["x"], self.home)
        self.assertEqual(r["ok"], False)
        self.assertEqual(r["motivo"], "ambiguo")
        self.assertEqual(sorted(r["ids"]), sorted([a, b]))
        self.assertEqual(_count(self.home, "req_link"), 2)
        self.assertEqual(_count(self.home, "req_repo"), 2)

    def test_id_inexistente(self):
        r = _cli("unlink", ["999"], self.home)
        self.assertIs(r["ok"], False)
        self.assertTrue(r["motivo"])

    def test_nombre_numerico_frente_a_un_id_es_ambiguo_y_no_borra(self):
        """Un REQ de nombre «2» y otro REQ con id 2: `unlink 2` no borra a ciegas; la ruta desambigua."""
        _cli("link", [self.cm], self.home)                                   # id 1
        id2 = _cli("link", [_change_md(self.repo, "y")], self.home)["id"]    # id 2
        cm_num = _change_md(self.repo, "2")
        id_num = _cli("link", [cm_num], self.home)["id"]                     # nombre «2», otro id
        self.assertEqual(id2, 2)
        self.assertNotEqual(id_num, 2)
        r = _cli("unlink", ["2"], self.home)
        self.assertEqual((r["ok"], r["motivo"]), (False, "ambiguo"))
        self.assertEqual(sorted(r["ids"]), sorted([id2, id_num]))
        self.assertEqual(_count(self.home, "req_link"), 3)
        t = _cli("trace", ["2", "--sin-git"], self.home)
        self.assertEqual(sorted(x["id"] for x in t["reqs"]), sorted([id2, id_num]))
        r = _cli("unlink", [cm_num], self.home)
        self.assertEqual((r["ok"], r["id"]), (True, id_num))
        self.assertEqual([n for (n,) in _q(self.home, "SELECT nombre FROM req_link ORDER BY id")], ["x", "y"])


# =========================================================================== fila 7: idempotencia

@unittest.skipUnless(HAS_GIT, "requiere git")
class TestIdempotencia(_Base):

    def setUp(self):
        super().setUp()
        self.repo = _gitrepo(self.tmp)
        self.cm = _change_md(self.repo, "x")

    def test_dos_sesiones_mismo_tool_use_y_link_repetido(self):
        lines = _lines([_w(self.cm)])                 # el mismo tool_use copiado en dos .jsonl (reanudación)
        for sid in ("s1", "s2"):
            t = self.tr(sid)
            os.makedirs(os.path.dirname(t), exist_ok=True)
            with open(t, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(lines) + "\n")
            err = _capturar(self.home, self.cwd, sid, t)
            self.assertNotIn("omitido", err)
        r = _cli("link", [self.cm], self.home)
        self.assertTrue(r["ok"])
        self.assertEqual(_count(self.home, "req_link"), 1)
        self.assertEqual(_count(self.home, "req_repo"), 1)
        self.assertEqual(sorted(x[0] for x in _q(self.home, "SELECT session_id FROM req_session")), ["s1", "s2"])

    def test_dos_main_seguidos_no_duplican(self):
        self.captura("s1", [_w(self.cm)])
        _capturar(self.home, self.cwd, "s1", self.tr("s1"))        # sin tramo nuevo
        self.captura("s1", [_w(self.cm)])                          # el mismo Write otra vez
        snap = _snapshot_req(self.home)
        self.assertEqual([len(snap[t]) for t in ("req_link", "req_repo", "req_session")], [1, 1, 1])
        self.assertEqual(_q(self.home, "PRAGMA foreign_key_check"), [])

    def test_upsert_de_req_repo_solo_toca_path_y_project(self):
        m = re.search(r"DO UPDATE SET (.+)$", req_link._SQL_UPSERT_REPO)
        cols = {a.split("=")[0].strip() for a in m.group(1).split(",")}
        self.assertEqual(cols, {"path", "project"})
        wt = os.path.join(self.tmp, "wt")
        _g(self.repo, "worktree", "add", "-q", "-b", "rama-wt", wt)
        _cli("link", [self.cm], self.home)
        before = _q(self.home, "SELECT req_id, common_dir FROM req_repo")
        _cli("link", [_change_md(wt, "x")], self.home)
        self.assertEqual(_q(self.home, "SELECT req_id, common_dir FROM req_repo"), before)
        self.assertEqual(_q(self.home, "SELECT path FROM req_repo"), [(_norm(wt),)])

    def test_unlink_entre_lectura_y_escritura_no_lanza(self):
        a = _cli("link", [self.cm], self.home)["id"]
        cm_b = _change_md(self.repo, "b")
        real = req_link.with_write_tx

        def wtx(con, fn, retries=3):
            o = _db(self.home)
            o.execute("DELETE FROM req_link WHERE id=?", (a,))
            o.commit()
            o.close()
            return real(con, fn, retries=retries)
        with mock.patch.object(req_link, "with_write_tx", wtx):
            err = self.captura("s1", [_w(self.cm), _w(cm_b)])
        self.assertNotIn("IntegrityError", err)
        self.assertNotIn("omitido", err)
        self.assertEqual([r[0] for r in _q(self.home, "SELECT nombre FROM req_link")], ["b"])
        self.assertEqual(_q(self.home, "SELECT l.nombre, s.session_id FROM req_session s "
                                       "JOIN req_link l ON l.id = s.req_id"), [("b", "s1")])
        # (sin AUTOINCREMENT, `b` puede reusar el id de `a`: la liga se verifica por nombre, arriba)
        self.assertEqual(_q(self.home, "PRAGMA foreign_key_check"), [])


# =========================================================================== fila 8: commits en trace

@unittest.skipUnless(HAS_GIT, "requiere git")
class TestCommitsEnTraza(_Base):

    def setUp(self):
        super().setUp()
        self.repo = _gitrepo(self.tmp)
        self.cm = _change_md(self.repo, "x")
        self.cd = _norm(os.path.join(self.repo, ".git"))

    def trace(self, arg="x", *extra):
        r = _cli("trace", [arg, *extra], self.home)
        self.assertTrue(r["ok"], r)
        return r

    def shas(self, r, i=0, common_dir=None):
        cd = common_dir or self.cd
        (repo,) = [x for x in r["reqs"][i]["repos"] if x["common_dir"] == cd]
        return [c["sha"] for c in repo["commits"]]

    def test_critico_sin_push_no_aparece_y_tras_push_si(self):
        _cli("link", [self.cm], self.home)
        sha = _commit(self.repo, "feat: a\n\nReq: x")
        self.assertEqual(self.shas(self.trace()), [])
        _push(self.repo)
        self.assertEqual(self.shas(self.trace()), [sha])
        c = self.trace()["reqs"][0]["repos"][0]["commits"][0]
        self.assertRegex(c["committed_at"], r"^\d{4}-\d{2}-\d{2}T")

    def test_critico_trailer_exacto(self):
        _cli("link", [self.cm], self.home)
        _cli("link", [_change_md(self.repo, "otro")], self.home)
        ca = _commit(self.repo, "feat: b\n\nConfirmacion-autonoma: x")
        c_otro = _commit(self.repo, "feat: c\n\nReq: otro")
        _commit(self.repo, "feat: d\n\nReq: x-extra")
        _commit(self.repo, "feat: e\n\nReq: x\n\nun párrafo final que no es bloque de trailers")
        dos = _commit(self.repo, "feat: f\n\nReq: x\nReq: otro")
        # `Req: x` a mitad del cuerpo y otro trailer al final: pasa el --grep de x, pero es solo de `otro`
        medio = _commit(self.repo, "feat: g\n\nReq: x\n\nun párrafo intermedio\n\nReq: otro")
        _push(self.repo)
        self.assertEqual(sorted(self.shas(self.trace("x"))), sorted([ca, dos]))
        self.assertEqual(sorted(self.shas(self.trace("otro"))), sorted([c_otro, dos, medio]))

    def test_critico_segundo_remoto_y_force_push(self):
        _cli("link", [self.cm], self.home)
        a = _commit(self.repo, "feat: a\n\nReq: x")
        _push(self.repo)
        other = os.path.join(self.tmp, "other.git")
        subprocess.run(["git", "init", "-q", "--bare", other], check=True, stdin=subprocess.DEVNULL)
        _g(self.repo, "remote", "add", "other", _fwd(other))
        solo_other = _commit(self.repo, "feat: o\n\nReq: x")
        _g(self.repo, "push", "-q", "other", "HEAD:main")
        _g(self.repo, "fetch", "-q", "other")
        self.assertTrue(_g(self.repo, "rev-parse", "refs/remotes/other/main"))
        self.assertEqual(self.shas(self.trace()), [a])                 # el remoto `other` no aporta
        _g(self.repo, "reset", "-q", "--hard", "HEAD~2")
        b = _commit(self.repo, "feat: b\n\nReq: x")
        _push(self.repo, force=True)
        got = self.shas(self.trace())
        self.assertEqual(got, [b])
        self.assertNotIn(solo_other, got)

    def test_cross_repo_con_repo(self):
        repo2 = _gitrepo(self.tmp, "repo2")
        _cli("link", [self.cm, "--repo", repo2], self.home)
        s1 = _commit(self.repo, "feat\n\nReq: x")
        s2 = _commit(repo2, "feat\n\nReq: x")
        _push(self.repo)
        _push(repo2)
        r = self.trace()
        self.assertEqual(self.shas(r), [s1])
        self.assertEqual(self.shas(r, common_dir=_norm(os.path.join(repo2, ".git"))), [s2])

    def test_dos_req_en_el_mismo_repo(self):
        _cli("link", [self.cm], self.home)
        _cli("link", [_change_md(self.repo, "y")], self.home)
        sx = _commit(self.repo, "feat\n\nReq: x")
        sy = _commit(self.repo, "feat\n\nReq: y")
        _push(self.repo)
        self.assertEqual(self.shas(self.trace("x")), [sx])
        self.assertEqual(self.shas(self.trace("y")), [sy])

    def test_worktree_y_principal_un_repo_y_un_git_log(self):
        wt = os.path.join(self.tmp, "wt")
        _g(self.repo, "worktree", "add", "-q", "-b", "rama-wt", wt)
        _cli("link", [_change_md(wt, "x")], self.home)
        _cli("link", [self.cm], self.home)
        self.assertEqual(_count(self.home, "req_repo"), 1)
        with _contador(self) as m:
            self.trace()
        self.assertEqual(len(_logs(m)), 1)
        self.assertEqual(m.call_count, 1)

    def test_borrar_el_worktree_y_push_desde_el_principal(self):
        wt = os.path.join(self.tmp, "wt")
        _g(self.repo, "worktree", "add", "-q", "-b", "rama-wt", wt)
        self.captura("s1", [_w(_change_md(wt, "x"))])
        self.assertEqual(_q(self.home, "SELECT common_dir FROM req_repo"), [(self.cd,)])
        _g(self.repo, "worktree", "remove", "--force", wt)
        self.assertFalse(os.path.exists(wt))
        sha = _commit(self.repo, "feat\n\nReq: x")
        _push(self.repo)
        self.assertEqual(self.shas(self.trace()), [sha])

    def test_clon_borrado_sale_sin_repo(self):
        clon = _gitrepo(self.tmp, "clon")
        _cli("link", [self.cm, "--repo", clon], self.home)
        sha = _commit(self.repo, "feat\n\nReq: x")
        _push(self.repo)
        cd_clon = _norm(os.path.join(clon, ".git"))
        _rmtree(clon)
        with _contador(self) as m:
            r = self.trace()
        (malo,) = [x for x in r["reqs"][0]["repos"] if x["common_dir"] == cd_clon]
        self.assertEqual(malo["nota"], "sin-repo")
        self.assertNotIn("commits", malo)
        self.assertEqual(self.shas(r), [sha])
        self.assertEqual(m.call_count, 1)
        self.assertFalse([c for c in m.call_args_list if cd_clon in c.args[0][0]])

    def test_sin_git_cero_llamadas(self):
        _cli("link", [self.cm], self.home)
        with _contador(self) as m:
            r = self.trace("x", "--sin-git")
        self.assertEqual(m.call_count, 0)
        self.assertIs(r["git"], False)

    def test_git_lento_en_un_repo_da_timeout(self):
        repo2 = _gitrepo(self.tmp, "repo2")
        _cli("link", [self.cm, "--repo", repo2], self.home)
        sha = _commit(self.repo, "feat\n\nReq: x")
        _push(self.repo)
        cd2 = _norm(os.path.join(repo2, ".git"))
        lento = _git_lento(cd2)
        with mock.patch.object(req_link, "_git", lento):
            r = self.trace()
        self.assertEqual(lento.seen, [req_link.TRACE_GIT_TIMEOUT])
        self.assertEqual(req_link.TRACE_GIT_TIMEOUT, 5.0)
        (malo,) = [x for x in r["reqs"][0]["repos"] if x["common_dir"] == cd2]
        self.assertEqual(malo["nota"], "timeout")
        self.assertEqual(self.shas(r), [sha])

    def test_value_error_en_un_repo_da_nota_error(self):
        repo2 = _gitrepo(self.tmp, "repo2")
        _cli("link", [self.cm, "--repo", repo2], self.home)
        sha = _commit(self.repo, "feat\n\nReq: x")
        _push(self.repo)
        cd2 = _norm(os.path.join(repo2, ".git"))
        real = req_link._git

        def fake(prefix, args, timeout):
            if prefix == ["--git-dir=" + cd2]:
                raise ValueError("falla inyectada")
            return real(prefix, args, timeout)
        with mock.patch.object(req_link, "_git", fake):
            r = self.trace()
        (malo,) = [x for x in r["reqs"][0]["repos"] if x["common_dir"] == cd2]
        self.assertTrue(malo["nota"].startswith("error: "), malo)
        self.assertIn("falla inyectada", malo["nota"])
        self.assertEqual(self.shas(r), [sha])

    def test_critico_ruta_con_acentos(self):
        if sys.flags.utf8_mode:
            self.skipTest("con el modo UTF-8 de Python esta parte no puede dar rojo (se anota en el registro)")
        repo = _gitrepo(self.tmp, "Árbol-ñé", project="arbol")
        cm = _change_md(repo, "acentos")
        self.captura("s1", [_w(cm)])
        cd = _norm(os.path.join(self.tmp, "Árbol-ñé", ".git"))
        self.assertEqual(_q(self.home, "SELECT common_dir FROM req_repo"), [(cd,)])
        sha = _commit(repo, "feat\n\nReq: acentos")
        _push(repo)
        r = self.trace("acentos")
        self.assertEqual(self.shas(r, common_dir=cd), [sha])


# =========================================================================== fila 9: costo del hook

@unittest.skipUnless(HAS_GIT, "requiere git")
class TestCostoHook(_Base):
    """Los nombres llevan prefijo a/b/c: la muestra positiva (2 llamadas) corre primero."""

    def setUp(self):
        super().setUp()
        self.repo = _gitrepo(self.tmp)
        self.cm = _change_md(self.repo, "x")

    def test_a_critico_registro_dos_llamadas_y_luego_cero(self):
        with _contador(self) as m:
            self.captura("s1", [_w(self.cm)])
        self.assertEqual(m.call_count, 2)                         # muestra positiva
        self.assertEqual(_logs(m), [])
        self.assertEqual(_count(self.home, "req_session"), 1)
        with _contador(self) as m:
            self.captura("s1", [_w(self.cm)])
        self.assertEqual(m.call_count, 0)

    def test_b_critico_stop_sin_candidato_cero(self):
        with _contador(self) as m:
            self.captura("s1", [("Read", {"file_path": self.cm}), _bash("git status")])
            self.captura("s2", [])
        self.assertEqual(m.call_count, 0)

    def test_c_critico_sesion_vinculada_cero_en_todos_los_eventos(self):
        with _contador(self) as m:
            self.captura("s1", [_w(self.cm)])
        self.assertEqual(m.call_count, 2)                         # muestra positiva con el mismo helper
        for con_push in (False, True):
            for event in ("Stop", "PreCompact", "SessionEnd"):
                with self.subTest(event=event, con_push=con_push):
                    tools = [("Edit", {"file_path": self.cm, "old_string": "a", "new_string": "b"})]
                    if con_push:
                        _commit(self.repo, "feat\n\nReq: x")
                        _push(self.repo)
                        tools.append(_bash("git push origin HEAD:main"))
                    with _contador(self) as m:
                        self.captura("s1", tools, event=event)
                    self.assertEqual(m.call_count, 0)
                    self.assertEqual(_logs(m), [])
        self.assertEqual(_count(self.home, "req_session"), 1)


# =========================================================================== fila 10: presupuesto

class TestPresupuesto(_Base):

    def test_critico_dos_req_nuevos_con_git_lento_terminan_en_4_5_s(self):
        top = os.path.join(self.tmp, "repo")
        os.makedirs(top)
        calls = []

        def fake(prefix, args, timeout):
            calls.append(timeout)
            if len(calls) > 1:
                time.sleep(max(0, timeout))
            if args[0] == "rev-parse":
                return 0, f"{top}\n{os.path.join(top, '.git')}\n", ""
            return 0, "https://example.invalid/o/repo.git\n", ""
        chunk = "\n".join(_lines([_w(os.path.join(top, "changes", f"{F}-a.md")),
                                  _w(os.path.join(top, "changes", f"{F}-b.md"))])) + "\n"
        con = _db(self.home)
        self.addCleanup(con.close)
        with mock.patch.object(req_link, "_git", fake), mock.patch.object(sys, "stderr", io.StringIO()):
            t0 = time.monotonic()
            try:
                req_link.after_capture(con, "s1", chunk)
            except sqlite3.Error:
                pass
            elapsed = time.monotonic() - t0
        self.assertGreaterEqual(len(calls), 3)                     # el camino lento sí se recorrió
        self.assertLessEqual(elapsed, 4.5)

    @unittest.skipUnless(HAS_GIT, "requiere git")
    def test_critico_base_bloqueada_omite_dentro_del_limite(self):
        repo = _gitrepo(self.tmp)
        cm = _change_md(repo, "x")
        real = req_link.after_capture
        estado = {}

        def envuelta(con, sid, chunk):
            path = con.execute("PRAGMA database_list").fetchone()[2]
            o = sqlite3.connect(path, timeout=1)
            o.isolation_level = None
            o.execute("BEGIN IMMEDIATE")
            estado["o"] = o
            t0 = time.monotonic()
            try:
                return real(con, sid, chunk)
            finally:
                estado["t"] = time.monotonic() - t0
        with mock.patch.object(req_link, "after_capture", envuelta):
            err = self.captura("s1", [_w(cm)])
        estado["o"].execute("ROLLBACK")
        estado["o"].close()
        self.assertLessEqual(estado["t"], 4.5)
        self.assertIn("vínculo de REQ omitido", err)
        self.assertEqual(_count(self.home, "req_session"), 0)
        self.assertCapturaIntacta("s1")

    @unittest.skipUnless(HAS_GIT, "requiere git")
    def test_sin_candado_si_hay_req_session(self):
        repo = _gitrepo(self.tmp)
        self.captura("s1", [_w(_change_md(repo, "x"))])
        self.assertEqual(_count(self.home, "req_session"), 1)

    def test_critico_lanzador_que_deja_un_hijo_con_los_pipes(self):
        script = os.path.join(self.tmp, "git-falso.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("import subprocess, sys, time\n"
                     "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'],\n"
                     "                 stdout=sys.stdout, stderr=sys.stderr)\n"
                     "time.sleep(10)\n")
        with mock.patch.object(req_link, "GIT_CMD", [sys.executable, script]), warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)      # el lanzador queda abandonado a propósito
            t0 = time.monotonic()
            r = req_link._git(["-C", self.tmp], ["status"], timeout=0.5)
            elapsed = time.monotonic() - t0
            gc.collect()
        self.assertEqual(r, (None, "", "timeout"))
        self.assertLessEqual(elapsed, 1.5)

    def test_scan_chunk_60_mb_sin_change_md(self):
        chunk = _chunk_sintetico(60 * 1024 * 1024)
        t0 = time.monotonic()
        ev = req_link.scan_chunk(chunk)
        elapsed = time.monotonic() - t0
        self.assertEqual((ev.writes, ev.cli), ({}, set()))
        self.assertLessEqual(elapsed, 1.0)


def _chunk_sintetico(size):
    """Tramo tipo transcript sin Change MD: tool_use de lectura/shell y tool_result grandes."""
    tool = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "C:/r/src/modulo.py"}}]}})
    bash = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "toolu_2", "name": "Bash", "input": {"command": "git status --short"}}]}})
    res = json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "x = 1\n" * 300}]}})
    bloque = "\n".join([tool, res, bash, res]) + "\n"
    return bloque * (size // len(bloque) + 1)


# =========================================================================== fila 11: aislamiento

class TestAislamiento(_Base):

    def test_critico_a_falla_inyectada_en_subproceso(self):
        root = os.path.join(self.tmp, "arbol")
        shutil.copytree(LIB, os.path.join(root, "hooks", "lib"), ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(SCHEMA, os.path.join(root, "hooks", "logbook-schema.sql"))
        with open(os.path.join(root, "hooks", "lib", "req_link.py"), "w", encoding="utf-8") as fh:
            fh.write("def after_capture(con, session_id, chunk):\n    raise RuntimeError('inyectada')\n")
        t = _append(self.tr("s1"), [_w(os.path.join(self.tmp, "r", "changes", f"{F}-x.md"))])
        env = {k: v for k, v in os.environ.items() if k not in ("NEB_LOGBOOK_ENDPOINT", "NEB_LOGBOOK_TOKEN")}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", HOME=self.home, USERPROFILE=self.home)
        p = subprocess.run([sys.executable, os.path.join(root, "hooks", "lib", "logbook.py"), "s1", self.cwd, t,
                            "Stop", root, self.home], capture_output=True, env=env, stdin=subprocess.DEVNULL)
        self.assertEqual(p.returncode, 0)
        self.assertIn("vínculo de REQ omitido: inyectada", p.stderr.decode("utf-8", errors="replace"))
        self.assertCapturaIntacta("s1")

    @unittest.skipUnless(HAS_GIT, "requiere git")
    def test_critico_b_integrity_error_en_req_session(self):
        repo = _gitrepo(self.tmp)
        cm = _change_md(repo, "x")
        envueltas = []

        def connect(path, schema):
            envueltas.append(_ConEnvuelta(_db_shared._connect(path, schema), raise_on="req_session"))
            return envueltas[-1]
        real = req_link.after_capture

        def marcada(con, sid, chunk):
            con.mark = len(con.log)
            return real(con, sid, chunk)
        with mock.patch.object(logbook, "_connect", connect), mock.patch.object(req_link, "after_capture", marcada):
            err = self.captura("s1", [_w(cm)])
        (con,) = envueltas
        if con.raised != 1:
            self.fail(f"el envoltorio debía lanzar IntegrityError 1 vez y lanzó {con.raised}: el escenario no "
                      f"llegó a la escritura de req_session")
        self.assertIsNotNone(con.mark)
        self.assertFalse([s for s in con.log[con.mark:] if "work" in s.lower()])
        self.assertIs(con.closed_in_tx, False)
        self.assertIn("vínculo de REQ omitido", err)
        self.assertCapturaIntacta("s1")
        self.assertEqual(_count(self.home, "req_link"), 0)          # la escritura de E2 se revirtió completa

    def test_critico_c_req_link_ausente_en_sys_modules(self):
        with mock.patch.dict(sys.modules, {"req_link": None}):
            err = self.captura("s1", [_w(os.path.join(self.tmp, "r", "changes", f"{F}-x.md"))])
        self.assertIn("vínculo de REQ omitido", err)
        self.assertCapturaIntacta("s1")
        self.assertIs(sys.modules["req_link"], req_link)


# =========================================================================== fila 12: trace sin git

class TestTraza(_Base):

    def setUp(self):
        super().setUp()
        con = _db(self.home)
        self.a = _seed(con, "host/o/uno", "x", F)
        self.b = _seed(con, "host/o/dos", "x", F)
        self.c = _seed(con, "host/o/uno", "y", F2)
        self.repo_dir = os.path.join(self.tmp, "cd-a")
        os.makedirs(self.repo_dir)
        con.execute("INSERT INTO req_repo VALUES (?,?,?,?)", (self.a, self.repo_dir, "/arbol", "host/o/uno"))
        self.t_old = _append(self.tr("s-old"), [])
        ts = "2026-01-1%dT00:00:00Z"
        for i, (sid, path) in enumerate((("s-old", self.t_old), ("s-new", self.tr("s-borrado")),
                                         ("s-sin-sync", None))):
            con.execute("INSERT INTO req_session VALUES (?,?,?,?,?)", (self.a, sid, "write", ts % i, ts % i))
            if path:
                con.execute("INSERT INTO session_sync (session_id, transcript_path, updated_at) VALUES (?,?,?)",
                            (sid, path, ts % i))
        con.commit()
        w1 = logbook._upsert_req(con, "host/otro/repo", "x", "dev", "maq", "En progreso", "main", "abc", "/r",
                                 "", "{}", "s9", "/t/s9.jsonl")
        w2 = logbook._upsert_req(con, "host/tercero/repo", "x", "dev", "maq", "Cerrado", "main", "abc", "/r",
                                 "", "{}", "s8", "/t/s8.jsonl")
        con.execute("UPDATE work SET archived_at='2026-01-30T00:00:00Z' WHERE id=?", (w2,))
        con.commit()
        con.close()
        self.works = {w1: False, w2: True}

    def test_sin_argumento_lista_con_cuentas_y_cero_git(self):
        with _contador(self) as m:
            r = _cli("trace", [], self.home)
        self.assertEqual(m.call_count, 0)
        self.assertTrue(r["ok"])
        self.assertNotIn("git", r)
        by = {x["id"]: x for x in r["reqs"]}
        self.assertEqual(set(by), {self.a, self.b, self.c})
        self.assertEqual((by[self.a]["repos"], by[self.a]["sesiones"], by[self.a]["ultima_sesion"]),
                         (1, 3, "2026-01-12T00:00:00Z"))
        self.assertEqual((by[self.b]["repos"], by[self.b]["sesiones"], by[self.b]["ultima_sesion"]), (0, 0, None))
        self.assertEqual(r["reqs"][0]["id"], self.c)                  # fecha DESC
        for k in ("project", "nombre", "fecha"):
            self.assertIn(k, by[self.a])

    def test_nombre_en_dos_project_da_dos_bloques(self):
        r = _cli("trace", ["x", "--sin-git"], self.home)
        self.assertEqual(sorted(x["id"] for x in r["reqs"]), sorted([self.a, self.b]))
        self.assertEqual({x["project"] for x in r["reqs"]}, {"host/o/uno", "host/o/dos"})

    def test_por_id_por_ruta_e_inexistente(self):
        r = _cli("trace", [str(self.c), "--sin-git"], self.home)
        self.assertEqual([x["id"] for x in r["reqs"]], [self.c])
        r = _cli("trace", [f"C:\\otro\\changes\\{F2}-y.md", "--sin-git"], self.home)
        self.assertEqual([x["id"] for x in r["reqs"]], [self.c])
        r = _cli("trace", [f"/r/changes/{F}-y.md", "--sin-git"], self.home)     # misma nombre, otra fecha
        self.assertEqual(r, {"ok": False, "motivo": "no vinculado"})
        for arg in ("no-existe", "999"):
            r = _cli("trace", [arg], self.home)
            self.assertIs(r["ok"], False)
            self.assertTrue(r["motivo"])

    def test_sesiones_leer_works_repos_y_leyenda(self):
        r = _cli("trace", [str(self.a), "--sin-git"], self.home)
        (req,) = r["reqs"]
        ses = {s["session_id"]: s for s in req["sesiones"]}
        self.assertEqual([s["session_id"] for s in req["sesiones"]], ["s-sin-sync", "s-new", "s-old"])
        self.assertEqual((ses["s-old"]["transcript_path"], ses["s-old"]["existe"]), (self.t_old, True))
        self.assertEqual((ses["s-new"]["transcript_path"], ses["s-new"]["existe"]), (self.tr("s-borrado"), False))
        self.assertEqual((ses["s-sin-sync"]["transcript_path"], ses["s-sin-sync"]["existe"]), (None, False))
        for s in req["sesiones"]:
            self.assertEqual(set(s), {"session_id", "via", "first_seen_at", "last_seen_at", "transcript_path",
                                      "existe"})
        self.assertEqual(req["leer"], self.t_old)                   # la más reciente con archivo en disco
        self.assertEqual({w["id"]: w["archivado"] for w in req["works_relacionados"]}, self.works)
        self.assertEqual({w["project"] for w in req["works_relacionados"]}, {"host/otro/repo", "host/tercero/repo"})
        self.assertEqual(req["repos"], [{"project": "host/o/uno", "common_dir": self.repo_dir, "path": "/arbol"}])
        self.assertEqual(req["leyenda"], req_link.LEYENDA)
        self.assertIn("cross-repo", req["leyenda"])
        os.remove(self.t_old)
        r = _cli("trace", [str(self.a), "--sin-git"], self.home)
        self.assertIsNone(r["reqs"][0]["leer"])

    def test_siete_repos_seis_git_log_y_uno_omitido(self):
        con = _db(self.home)
        for i in range(7):
            d = os.path.join(self.tmp, f"cd-{i}")
            os.makedirs(d)
            con.execute("INSERT INTO req_repo VALUES (?,?,?,?)", (self.c, d, d, f"host/o/r{i}"))
        con.commit()
        con.close()
        with _contador(self) as m:
            r = _cli("trace", ["y"], self.home)
        self.assertTrue(r["ok"])
        self.assertIs(r["git"], True)
        self.assertEqual(len(_logs(m)), 6)
        repos = r["reqs"][0]["repos"]
        self.assertEqual(len(repos), 7)
        self.assertEqual(repos[6]["nota"], "omitido: tope de 6 repos")
        self.assertEqual([x for x in repos[:6] if x.get("nota") == "omitido: tope de 6 repos"], [])

    def test_sin_git_repos_sin_commits_ni_llamadas(self):
        with _contador(self) as m:
            r = _cli("trace", [str(self.a), "--sin-git"], self.home)
        self.assertEqual(m.call_count, 0)
        self.assertIs(r["git"], False)
        for x in r["reqs"][0]["repos"]:
            self.assertNotIn("commits", x)
            self.assertNotIn("nota", x)

    def test_trace_no_escribe(self):
        antes = _snapshot_req(self.home)
        for args in ([], ["x"], ["x", "--sin-git"], [str(self.a)], ["y"], ["no-existe"]):
            _cli("trace", args, self.home)
        self.assertEqual(_snapshot_req(self.home), antes)


if __name__ == "__main__":
    unittest.main()
