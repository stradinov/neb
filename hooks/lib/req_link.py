#!/usr/bin/env python3
"""req_link.py — REQ vinculado en la bitácora local (REQ neb-trazabilidad-indice-commits, E2).

Base local, sin tocar `work`. Tres tablas (`req_link`, `req_repo`, `req_session`, en
`hooks/logbook-schema.sql`) guardan solo lo que git no sabe: el REQ vinculado, sus repos declarados
y las sesiones de esta máquina que lo trabajaron. Los commits NO se guardan: `trace`
los lee de git al consultar, por el trailer `Req:` / `Confirmacion-autonoma:`.

Dos vías de vínculo:
  • (a) hook: un `tool_use` `Write`, `Edit` o `MultiEdit` del hilo principal sobre
    `changes/<AAAA-MM-DD>-<nombre>.md`. Lo procesa `after_capture`, que `logbook.main()` llama DESPUÉS
    del `con.commit()` de la captura, en `Stop` y `PreCompact` (nunca en `SessionEnd`). Leer o nombrar
    el Change MD no vincula nada.
  • (b) CLI: `logbook.py link <ruta> [--repo <dir>]`. La captura siguiente ve el comando en un
    `tool_use` `Bash`/`PowerShell` y liga la sesión si el REQ ya existe.

Costo del hook: un límite único de 4 s (parseo, lecturas, registro y esperas de candado); el hook
nunca corre `git log`; las únicas llamadas a git son las 2 de `resolve_repo` por REQ nuevo, una vez
en la vida del REQ. Excepción: una escritura a un Change MD que no llega a registrarse (repo sin
`origin`, o choque de fecha en el mismo `project`) vuelve a pagar `resolve_repo` en cada captura cuyo
tramo la traiga, dentro del mismo límite. Las omisiones del hook (barrido, choque de fecha, límite
vencido, base bloqueada) solo avisan en stderr, que el hook descarta: el aviso queda para quien corra
`logbook.py` a mano.

CLI (`link`, `trace`, `unlink`): los despacha `logbook.cli_main`, que atrapa `DbUnavailable` (base
sin mudar a la carpeta de datos, o que este código no puede operar); salida JSON en stdout y exit 0 siempre
(el skill decide por `ok`).
"""

import json
import os
import re
import subprocess
import sys
import time
from collections import namedtuple
from datetime import date, datetime, timedelta

from _db_shared import _normalize_remote, now_iso, with_write_tx

# --------------------------------------------------------------------------- patrones

# Change MD directo bajo `changes/` (no `changes/plans/`); sensible a mayúsculas; el límite final
# excluye `….md.bak` y `….md/x`. Se usa con `search` sobre `input.file_path` y sobre cada token de ruta.
CHANGE_RE = re.compile(r"(?:^|[\\/])changes[\\/](\d{4}-\d{2}-\d{2})-([a-z0-9-]+)\.md(?![\w.\\/-])")

# `LB link <ruta>` (forma del skill) y `... logbook.py link <ruta>` (forma directa); el grupo es el
# token de ruta. Límite conocido: `echo "LB link …"` también casa.
LINK_CMD_RE = re.compile(r"(?:\blogbook\.py[\"']?|(?<![\w-])LB)\s+link\s+[\"']?([^\s\"';&|]+)")

NOMBRE_RE = re.compile(r"[a-z0-9-]+")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

GIT_CMD = ["git"]          # parcheable en pruebas
HOOK_BUDGET = 4.0          # s: límite único de E2 en la captura
GIT_CALL_MAX = 2.0         # s por llamada de git dentro de resolve_repo
BUSY_MAX_MS = 1000         # ms: tope de la espera de candado en la captura
CLI_DEADLINE = 5.0         # s: límite de resolve_repo en `link`
TRACE_GIT_TIMEOUT = 5.0    # s por llamada de `git log` en `trace`
TRACE_MAX_REPOS = 6
LEYENDA = "solo los repos declarados; un REQ cross-repo sin --repo sale incompleto"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}

Evidence = namedtuple("Evidence", "writes cli")   # writes: {(fecha, nombre): file_path}; cli: {(fecha, nombre)}


def _warn(msg):
    print(f"[logbook] aviso: {msg}", file=sys.stderr)


def name_of_path(path):
    """(fecha, nombre) de `changes/<fecha>-<nombre>.md`, o None si la ruta no cumple CHANGE_RE."""
    if not isinstance(path, str):
        return None
    m = CHANGE_RE.search(path)
    return (m.group(1), m.group(2)) if m else None


# --------------------------------------------------------------------------- tramo del transcript

def _candidate_lines(text):
    """Líneas del tramo que contienen `"tool_use"` (con comillas: excluye `tool_use_id`) y además
    `changes` o ` link`. Busca por subcadena sin partir todo el tramo."""
    seen = set()
    pos = text.find('"tool_use"')
    while pos != -1:
        start = text.rfind("\n", 0, pos) + 1
        end = text.find("\n", pos)
        if end == -1:
            end = len(text)
        if start not in seen:
            seen.add(start)
            line = text[start:end]
            if "changes" in line or " link" in line:
                yield line
        pos = text.find('"tool_use"', end)


def scan_chunk(text):
    """Evidencia de vínculo del tramo: escrituras de Change MD y comandos `link` de shell."""
    writes, cli = {}, set()
    if not text:
        return Evidence(writes, cli)
    for line in _candidate_lines(text):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        msg = obj.get("message") if isinstance(obj, dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name, inp = block.get("name"), block.get("input")
            if not isinstance(inp, dict):
                continue
            if name in WRITE_TOOLS:
                fp = inp.get("file_path")
                key = name_of_path(fp)
                if key:
                    writes[key] = fp
            elif name in SHELL_TOOLS:
                cmd = inp.get("command")
                if not isinstance(cmd, str):
                    continue
                for m in LINK_CMD_RE.finditer(cmd):
                    key = name_of_path(m.group(1))
                    if key:
                        cli.add(key)
    return Evidence(writes, cli)


# --------------------------------------------------------------------------- git

def _git(prefix, args, timeout):
    """Único punto de git del módulo → (rc, out, err). rc None si no corrió o venció el tiempo.
    Popen + communicate(timeout): al vencer, kill y communicate(timeout=0.5); si vuelve a vencer
    (un hijo heredó los pipes), se abandona el proceso. Salida en UTF-8 (git escribe UTF-8)."""
    try:
        p = subprocess.Popen([*GIT_CMD, *prefix, "--no-optional-locks", *args],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             encoding="utf-8", errors="replace")
    except (OSError, ValueError) as e:
        return None, "", str(e)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(p)
        return None, "", "timeout"
    except (OSError, ValueError) as e:
        _kill(p)
        return None, "", str(e)
    return p.returncode, out or "", err or ""


def _kill(p):
    try:
        p.kill()
    except OSError:
        pass
    try:
        p.communicate(timeout=0.5)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass   # se abandona el proceso


def _norm(path):
    return os.path.normcase(os.path.realpath(path))


def resolve_repo(dir_, deadline):
    """(top, common_dir, project) del repo que contiene `dir_`, o None (sin repo, sin `origin` o sin
    tiempo). Dos llamadas a git, cada una con min(2, deadline - monotonic())."""
    timeout = min(GIT_CALL_MAX, deadline - time.monotonic())
    if timeout <= 0:
        return None
    rc, out, _err = _git(["-C", dir_ or "."],
                         ["rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"],
                         timeout)
    if rc != 0:
        return None
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if len(lines) < 2 or not all(os.path.isabs(ln) for ln in lines[:2]):
        return None
    top, common_dir = _norm(lines[0]), _norm(lines[1])
    timeout = min(GIT_CALL_MAX, deadline - time.monotonic())
    if timeout <= 0:
        return None
    rc, out, _err = _git(["--git-dir=" + common_dir], ["remote", "get-url", "origin"], timeout)
    url = out.strip() if rc == 0 else ""
    if not url:
        return None
    return top, common_dir, _normalize_remote(url)


def scan_commits(common_dir, nombre, since, timeout):
    """Lectura (solo `trace`): commits alcanzables desde refs/remotes/origin/* con un trailer `Req` o
    `Confirmacion-autonoma` exactamente igual a `nombre` → (ok, [(sha, committed_at)], err).
    Un timeout devuelve err == "timeout" y no reintenta."""
    def run(since_opt):
        return _git(["--git-dir=" + common_dir],
                    ["log", "--remotes=origin", f"{since_opt}={since}", "-E",
                     f"--grep=^(Req|Confirmacion-autonoma): {nombre}$",
                     "--format=%H%x1f%cI%x1f%(trailers:key=Req,key=Confirmacion-autonoma,valueonly,separator=%x1e)%x1d"],
                    timeout)

    rc, out, err = run("--since-as-filter")
    if rc is not None and rc != 0 and "since-as-filter" in err:   # git < 2.37
        rc, out, err = run("--since")
    if rc is None:
        return False, [], err or "timeout"
    if rc != 0:
        return False, [], err
    commits = []
    for rec in out.split("\x1d"):
        rec = rec.strip()
        if not rec:
            continue
        fields = rec.split("\x1f")
        if len(fields) < 3:
            continue
        sha, committed_at = fields[0].strip(), fields[1].strip()
        values = [v.strip() for v in fields[2].split("\x1e")]
        if nombre not in values or not SHA_RE.match(sha):
            continue
        try:
            datetime.fromisoformat(committed_at)
        except ValueError:
            continue
        commits.append((sha, committed_at))
    return True, commits, ""


# --------------------------------------------------------------------------- sentencias

_SQL_INSERT_LINK = ("INSERT INTO req_link (project, nombre, fecha, change_md, linked_by, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(project, nombre) DO NOTHING")
_SQL_SELECT_LINK = "SELECT id, fecha FROM req_link WHERE project = ? AND nombre = ?"
_SQL_TOUCH_LINK = "UPDATE req_link SET updated_at = ? WHERE id = ?"
_SQL_UPSERT_REPO = ("INSERT INTO req_repo (req_id, common_dir, path, project) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(req_id, common_dir) DO UPDATE SET path = excluded.path, project = excluded.project")
_SQL_UPSERT_SESSION = ("INSERT INTO req_session (req_id, session_id, via, first_seen_at, last_seen_at) "
                       "VALUES (?, ?, ?, ?, ?) "
                       "ON CONFLICT(req_id, session_id) DO UPDATE SET last_seen_at = excluded.last_seen_at")


def _placeholders(n):
    return ", ".join("?" * n)


def _change_md_rel(file_path, top, fecha, nombre):
    """Ruta del Change MD desde la raíz de su repo, con '/'. `top` viene con normcase (solo sirve para
    comparar); el tramo relativo se toma del directorio real, para conservar sus mayúsculas."""
    fname = f"{fecha}-{nombre}.md"
    d = os.path.realpath(os.path.dirname(os.path.abspath(file_path)))
    nd = os.path.normcase(d)                    # normcase conserva la longitud: los índices coinciden
    base = top.rstrip("\\/")
    if nd == base:
        return fname
    if not nd.startswith(base + os.sep):
        return "changes/" + fname
    rel = d[len(base) + 1:].replace("\\", "/")
    return f"{rel}/{fname}"


# --------------------------------------------------------------------------- captura (vía a)

def after_capture(con, session_id, chunk):
    """E2 en la captura (`Stop`/`PreCompact`), DESPUÉS del commit. Ver el orden en el docstring del
    módulo y en el plan (§ "Captura: orden exacto"). Las excepciones suben a `logbook._after_capture`,
    que revierte y avisa."""
    deadline = time.monotonic() + HOOK_BUDGET          # 1. antes de cualquier parseo, consulta o git

    def restante():
        return deadline - time.monotonic()

    ev = scan_chunk(chunk)                              # 2.
    if not ev.writes and not ev.cli:
        return
    if restante() <= 0:
        _warn("vínculo de REQ omitido: límite de 4 s vencido al leer el tramo")
        return

    nombres = sorted({n for _f, n in ev.writes} | {n for _f, n in ev.cli})
    rows = con.execute(                                 # 3. lectura (WAL: no espera candado)
        f"SELECT id, project, nombre, fecha FROM req_link WHERE nombre IN ({_placeholders(len(nombres))})",
        nombres).fetchall()

    links = {}                                          # 4. clasificación: id → via (primera evidencia)
    candidatas = []
    for fecha, nombre in sorted(ev.writes):
        hits = [r for r in rows if r[2] == nombre and r[3] == fecha]
        if hits:
            for r in hits:
                links.setdefault(r[0], "write")
        else:
            candidatas.append((fecha, nombre))
    for fecha, nombre in sorted(ev.cli):
        for r in rows:
            if r[2] == nombre and r[3] == fecha:
                links.setdefault(r[0], "cli")
    if len(candidatas) >= 3:
        _warn(f"barrido: {len(candidatas)} Change MD sin vincular en el tramo; no se registra ninguno "
              "(usa `link <ruta>` en los que trabajaste)")
        candidatas = []

    nuevos = []                                         # 5. registro por vía (a), sin transacción
    for fecha, nombre in candidatas:
        if restante() <= 0:
            _warn(f"registro de {nombre} omitido: límite de 4 s vencido")
            break
        file_path = ev.writes[(fecha, nombre)]
        repo = resolve_repo(os.path.dirname(os.path.abspath(file_path)), deadline)
        if repo is None:
            if restante() <= 0:
                _warn(f"registro de {nombre} omitido: límite de 4 s vencido")
            continue                                    # sin repo o sin origin: en silencio
        top, common_dir, project = repo
        otra = [r for r in rows if r[1] == project and r[2] == nombre and r[3] != fecha]
        if otra:
            _warn(f"registro de {nombre} omitido: nombre ya vinculado con fecha {otra[0][3]} en {project}")
            continue
        nuevos.append((project, nombre, fecha, _change_md_rel(file_path, top, fecha, nombre), top, common_dir))

    if not links and not nuevos:
        return
    ms = int(min(BUSY_MAX_MS, restante() * 1000))       # 6. escritura única
    if ms <= 0:
        _warn("vínculo de REQ omitido: límite de 4 s vencido antes de escribir")
        return
    con.execute(f"PRAGMA busy_timeout = {ms}")

    def fn(c):
        ts = now_iso()
        if links:
            ids = sorted(links)
            vivos = {r[0] for r in c.execute(
                f"SELECT id FROM req_link WHERE id IN ({_placeholders(len(ids))})", ids).fetchall()}
            for req_id in ids:
                if req_id in vivos:                     # un `unlink` entre la lectura y la escritura: se salta
                    c.execute(_SQL_UPSERT_SESSION, (req_id, session_id, links[req_id], ts, ts))
        for project, nombre, fecha, change_md, top, common_dir in nuevos:
            c.execute(_SQL_INSERT_LINK, (project, nombre, fecha, change_md, "write", ts, ts))
            row = c.execute(_SQL_SELECT_LINK, (project, nombre)).fetchone()
            if row is None or row[1] != fecha:
                _warn(f"registro de {nombre} omitido: nombre ya vinculado con fecha "
                      f"{row[1] if row else '?'} en {project}")
                continue
            c.execute(_SQL_UPSERT_REPO, (row[0], common_dir, top, project))
            c.execute(_SQL_UPSERT_SESSION, (row[0], session_id, "write", ts, ts))

    with_write_tx(con, fn, retries=1)


# --------------------------------------------------------------------------- CLI

def _default_connect():
    """Misma base y esquema que `logbook._db_for_cli` (para llamadas directas sin conector): el esquema
    inicial del árbol de este módulo (6.48.0). Lanza UnmovedDb si la base sigue en ~/.claude sin mudar; puede
    lanzar DbUnavailable."""
    from _db_shared import open_default_db
    return open_default_db(os.path.expanduser("~"))


def _emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _open(connect):
    return (connect or _default_connect)()


def _split_args(args, flags_with_value=(), flags=()):
    pos, opts = [], {}
    i = 0
    while i < len(args):
        a = args[i]
        if a in flags_with_value:
            opts[a] = args[i + 1] if i + 1 < len(args) else None
            i += 2
            continue
        if a in flags:
            opts[a] = True
        else:
            pos.append(a)
        i += 1
    return pos, opts


def _resolve_target(con, target):
    """Filas (id, project, nombre, fecha, change_md) de `req_link` por id, ruta o nombre. Un argumento
    de solo dígitos casa por id Y por nombre (un nombre numérico es válido): si coincide con los dos,
    salen las dos filas, `unlink` responde «ambiguo» sin borrar y la ruta desambigua."""
    cols = "SELECT id, project, nombre, fecha, change_md FROM req_link"
    if target.isdigit():
        return con.execute(cols + " WHERE id = ? OR nombre = ? ORDER BY id", (int(target), target)).fetchall()
    key = name_of_path(target)
    if key:
        return con.execute(cols + " WHERE nombre = ? AND fecha = ? ORDER BY project",
                           (key[1], key[0])).fetchall()
    if NOMBRE_RE.fullmatch(target):
        return con.execute(cols + " WHERE nombre = ? ORDER BY project", (target,)).fetchall()
    return []


def cli_link(args, connect=None):
    """`link <ruta> [--repo <dir>]`: registra o refresca el REQ y declara un repo adicional. Sin commits."""
    pos, opts = _split_args(args, flags_with_value=("--repo",))
    if not pos:
        _emit({"ok": False, "motivo": "uso: link <ruta> [--repo <dir>]"})
        return
    ruta = pos[0]
    if not os.path.isfile(ruta):
        _emit({"ok": False, "motivo": f"no existe: {ruta}"})
        return
    key = name_of_path(ruta)
    if key is None:
        _emit({"ok": False, "motivo": "nombre inválido: se espera changes/<AAAA-MM-DD>-<nombre>.md "
                                      "con <nombre> de forma [a-z0-9-]+"})
        return
    fecha, nombre = key
    repo = resolve_repo(os.path.dirname(os.path.abspath(ruta)), time.monotonic() + CLI_DEADLINE)
    if repo is None:
        _emit({"ok": False, "motivo": "el Change MD no está en un repo git con remoto origin"})
        return
    top, common_dir, project = repo
    avisos = []
    extra = None
    if "--repo" in opts:
        rdir = opts["--repo"]
        extra = resolve_repo(rdir, time.monotonic() + CLI_DEADLINE) if rdir else None
        if not rdir:
            avisos.append("--repo sin directorio; se omite")
        elif extra is None:
            avisos.append(f"--repo {rdir}: no es un repo git con remoto origin; se omite")
    change_md = _change_md_rel(ruta, top, fecha, nombre)

    con = _open(connect)
    if con is None:
        _emit({"ok": False, "motivo": "sin base local de la bitácora"})
        return
    try:
        def fn(c):
            ts = now_iso()
            c.execute(_SQL_INSERT_LINK, (project, nombre, fecha, change_md, "cli", ts, ts))
            row = c.execute(_SQL_SELECT_LINK, (project, nombre)).fetchone()
            if row[1] != fecha:
                return {"ok": False, "motivo": f"nombre ya vinculado con fecha {row[1]}"}
            req_id = row[0]
            c.execute(_SQL_TOUCH_LINK, (ts, req_id))
            c.execute(_SQL_UPSERT_REPO, (req_id, common_dir, top, project))
            if extra is not None:
                c.execute(_SQL_UPSERT_REPO, (req_id, extra[1], extra[0], extra[2]))
            return {"id": req_id}

        r = with_write_tx(con, fn)
        if not r.get("id"):
            _emit(r)
            return
        req_id = r["id"]
        cm = con.execute("SELECT change_md FROM req_link WHERE id = ?", (req_id,)).fetchone()
        repos = [{"project": p, "common_dir": cd, "path": pa} for cd, pa, p in con.execute(
            "SELECT common_dir, path, project FROM req_repo WHERE req_id = ? ORDER BY common_dir", (req_id,))]
        sesiones = con.execute("SELECT COUNT(*) FROM req_session WHERE req_id = ?", (req_id,)).fetchone()[0]
    finally:
        con.close()
    _emit({"ok": True, "id": req_id, "project": project, "nombre": nombre, "fecha": fecha,
           "change_md": cm[0] if cm else change_md, "repos": repos, "sesiones": sesiones, "avisos": avisos})


def _since(fecha):
    try:
        return (date.fromisoformat(fecha) - timedelta(days=1)).isoformat()
    except ValueError:
        return fecha


def _repo_with_commits(common_dir, path, project, nombre, since):
    base = {"project": project, "common_dir": common_dir, "path": path}
    if not os.path.isdir(common_dir):
        return {**base, "nota": "sin-repo"}
    try:
        ok, commits, err = scan_commits(common_dir, nombre, since, TRACE_GIT_TIMEOUT)
    except Exception as e:   # la falla de un repo no tumba la consulta
        return {**base, "nota": "error: " + (str(e).strip().splitlines() or [type(e).__name__])[0][:200]}
    if ok:
        return {**base, "commits": [{"sha": s, "committed_at": t} for s, t in commits]}
    if err == "timeout":
        return {**base, "nota": "timeout"}
    first = (err or "").strip().splitlines()
    return {**base, "nota": "error: " + (first[0] if first else "git salió con error")[:200]}


def cli_trace(args, connect=None):
    """`trace [<nombre>|<ruta>|<id>] [--sin-git]`: commits publicados (leídos de git al consultar) y
    sesiones de esta máquina. Nunca escribe en la base."""
    pos, opts = _split_args(args, flags=("--sin-git",))
    usar_git = not opts.get("--sin-git")
    con = _open(connect)
    if con is None:
        _emit({"ok": False, "motivo": "sin base local de la bitácora"})
        return
    try:
        if not pos:
            rows = con.execute(
                "SELECT l.id, l.project, l.nombre, l.fecha, "
                "(SELECT COUNT(*) FROM req_repo r WHERE r.req_id = l.id), "
                "(SELECT COUNT(*) FROM req_session s WHERE s.req_id = l.id), "
                "(SELECT MAX(s.last_seen_at) FROM req_session s WHERE s.req_id = l.id) "
                "FROM req_link l ORDER BY l.fecha DESC, l.nombre").fetchall()
            out = {"ok": True, "reqs": [
                {"id": r[0], "project": r[1], "nombre": r[2], "fecha": r[3], "repos": r[4],
                 "sesiones": r[5], "ultima_sesion": r[6]} for r in rows]}
        else:
            found = _resolve_target(con, pos[0])
            if not found:
                out = {"ok": False, "motivo": "no vinculado"}
            else:
                reqs = []
                for req_id, project, nombre, fecha, change_md in found:
                    repos_rows = con.execute(
                        "SELECT common_dir, path, project FROM req_repo WHERE req_id = ? ORDER BY common_dir",
                        (req_id,)).fetchall()
                    ses_rows = con.execute(
                        "SELECT s.session_id, s.via, s.first_seen_at, s.last_seen_at, ss.transcript_path "
                        "FROM req_session s LEFT JOIN session_sync ss ON ss.session_id = s.session_id "
                        "WHERE s.req_id = ? ORDER BY s.last_seen_at DESC", (req_id,)).fetchall()
                    works = con.execute(
                        "SELECT id, project, req_slug, archived_at FROM work WHERE mode = 'req' AND req_slug = ?",
                        (nombre,)).fetchall()
                    reqs.append({"id": req_id, "project": project, "nombre": nombre, "fecha": fecha,
                                 "change_md": change_md, "_repos": repos_rows, "_ses": ses_rows,
                                 "_works": works})
                out = {"ok": True, "git": usar_git, "reqs": reqs}
    finally:
        con.close()

    # git fuera de la conexión: la consulta no retiene la base mientras git corre.
    if out.get("ok") and pos:
        for req in out["reqs"]:
            since = _since(req["fecha"])
            repos = []
            for i, (cd, pa, pr) in enumerate(req.pop("_repos")):
                if not usar_git:
                    repos.append({"project": pr, "common_dir": cd, "path": pa})
                elif i >= TRACE_MAX_REPOS:
                    repos.append({"project": pr, "common_dir": cd, "path": pa,
                                  "nota": f"omitido: tope de {TRACE_MAX_REPOS} repos"})
                else:
                    repos.append(_repo_with_commits(cd, pa, pr, req["nombre"], since))
            sesiones = [{"session_id": s[0], "via": s[1], "first_seen_at": s[2], "last_seen_at": s[3],
                         "transcript_path": s[4], "existe": bool(s[4]) and os.path.isfile(s[4])}
                        for s in req.pop("_ses")]
            leer = next((s["transcript_path"] for s in sesiones if s["existe"]), None)
            works = [{"id": w[0], "project": w[1], "req_slug": w[2], "archivado": w[3] is not None}
                     for w in req.pop("_works")]
            req.update({"repos": repos, "leyenda": LEYENDA, "sesiones": sesiones, "leer": leer,
                        "works_relacionados": works})
    _emit(out)


def cli_unlink(args, connect=None):
    """`unlink <id|nombre|ruta>`: borra el REQ vinculado (el ON DELETE CASCADE borra repos y sesiones)."""
    pos, _opts = _split_args(args)
    if not pos:
        _emit({"ok": False, "motivo": "uso: unlink <id|nombre|ruta>"})
        return
    con = _open(connect)
    if con is None:
        _emit({"ok": False, "motivo": "sin base local de la bitácora"})
        return
    try:
        found = _resolve_target(con, pos[0])
        if not found:
            out = {"ok": False, "motivo": "no vinculado"}
        elif len(found) > 1:
            out = {"ok": False, "motivo": "ambiguo", "ids": [r[0] for r in found]}
        else:
            req_id = found[0][0]

            def fn(c):
                n = c.execute("SELECT (SELECT COUNT(*) FROM req_repo WHERE req_id = ?), "
                              "(SELECT COUNT(*) FROM req_session WHERE req_id = ?)", (req_id, req_id)).fetchone()
                c.execute("DELETE FROM req_link WHERE id = ?", (req_id,))
                return n

            n = with_write_tx(con, fn)
            out = {"ok": True, "id": req_id, "borrados": {"repos": n[0], "sesiones": n[1]}}
    finally:
        con.close()
    _emit(out)
