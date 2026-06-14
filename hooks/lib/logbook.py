#!/usr/bin/env python3
"""
logbook.py — cliente de la bitácora de relevo (Neb).

Tres modos (dispatch en __main__):
  • captura (sin args reconocidos)  — lo dispara el hook `logbook-sync` en Stop/SessionEnd/PreCompact:
      registra estado + transcript_path del work activo en SQLite local; si el proyecto activa el
      central (NEB_LOGBOOK_ENDPOINT y opt-in por proyecto vía marcador `<!-- neb-logbook: central -->`),
      lanza el modo `sync` detached.
  • sync <guide_dir> <home_dir>     — drena el outbox (works dirty) al central + sube el transcript
      incremental. Best-effort, defensivo (REQ B).
  • CLI (list/show/claim/...)       — lo invoca el comando/skill `/logbook`. Con NEB_LOGBOOK_ENDPOINT
      configurado opera contra el CENTRAL (la autoridad: ids remotos); sin él, contra el SQLite local.

Backend local = default + outbox. Backend central (REQ B) = autoridad del lock + corpus buscable.
Filosofía: defensivo — exit 0 siempre; errores a stderr, nunca bloquean al dev.

Args posicionales del modo captura (los arma el wrapper desde el stdin JSON del hook):
  1 session_id  2 cwd  3 transcript_path  4 event_name  5 guide_dir (NEB_HOME)  6 home_dir
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone


def posix_to_win(path):
    """Ruta POSIX de Git Bash (/c/Users/foo) a Windows. No-op si ya es Windows o en Linux/Mac."""
    if sys.platform == "win32" and path and re.match(r"^/[a-zA-Z]/", path):
        return f"{path[1].upper()}:\\{path[2:].replace('/', '\\')}"
    return path


def encode_cwd(cwd):
    """CWD → formato de directorio de proyecto Claude: ':' → '-', luego '/' y '\\' → '-'."""
    return cwd.replace(":", "-").replace("/", "-").replace("\\", "-")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# =========================================================================== captura

def main():
    if len(sys.argv) < 7:
        return

    session_id     = sys.argv[1]
    cwd            = posix_to_win(sys.argv[2])
    transcript_arg = posix_to_win(sys.argv[3])
    event_name     = sys.argv[4]
    guide_dir      = posix_to_win(sys.argv[5])
    home_dir       = posix_to_win(sys.argv[6]) or os.path.expanduser("~")

    if not session_id or not cwd:
        return

    encoded      = encode_cwd(cwd)
    projects_dir = os.path.join(home_dir, ".claude", "projects", encoded)
    jsonl_path   = transcript_arg or os.path.join(projects_dir, f"{session_id}.jsonl")
    memory_dir   = os.path.join(projects_dir, "memory")
    schema_path  = os.path.join(guide_dir, "hooks", "logbook-schema.sql")
    db_path      = os.path.join(home_dir, ".claude", "neb-logbook.db")

    owner   = _whoami()
    machine = _hostname()
    branch, head = _git_info(cwd)

    active = find_active_req(memory_dir) if os.path.isdir(memory_dir) else None

    con = _connect(db_path, schema_path)
    if con is None:
        return
    try:
        if active:
            project  = _project_id(active.get("project_path") or cwd)
            req_slug = active.get("name") or "sin-nombre"
            payload  = json.dumps({
                "plan": active.get("plan", ""),
                "next_steps": active.get("next_steps", ""),
                "files": active.get("files", ""),
                "pending_delivery": active.get("pending_delivery", ""),
            }, ensure_ascii=False)
            _upsert_req(con, project, req_slug, owner, machine, active.get("state", ""),
                        branch, head, active.get("project_path", ""), active.get("draft", ""),
                        payload, session_id, jsonl_path)
        else:
            summary = _first_user_prompt(jsonl_path)
            _upsert_exploratory(con, session_id, owner, machine, summary, branch, head, cwd, jsonl_path)
        con.commit()
    finally:
        con.close()

    # REQ B: si el entorno es compartido, drenar el outbox al central (detached, best-effort).
    _maybe_spawn_sync(cwd, guide_dir, home_dir)


# --------------------------------------------------------------------------- DB

def _connect(db_path, schema_path):
    try:
        con = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        print(f"[logbook] ERROR abriendo {db_path}: {e}", file=sys.stderr)
        return None
    try:
        if os.path.isfile(schema_path):
            con.executescript(open(schema_path, encoding="utf-8").read())
        _migrate(con)
    except (OSError, sqlite3.Error) as e:
        print(f"[logbook] ERROR aplicando schema: {e}", file=sys.stderr)
        con.close()
        return None
    return con


def _migrate(con):
    """Migraciones idempotentes para DBs de REQ A ya existentes (CREATE TABLE IF NOT EXISTS no altera)."""
    cols = [r[1] for r in con.execute("PRAGMA table_info(work)").fetchall()]
    if cols and "conflict" not in cols:
        con.execute("ALTER TABLE work ADD COLUMN conflict INTEGER NOT NULL DEFAULT 0")
        con.commit()


def _upsert_req(con, project, req_slug, owner, machine, state, branch, head,
                repo_path, change_md, payload, session_id, transcript_path):
    ts = now_iso()
    row = con.execute(
        "SELECT id FROM work WHERE mode='req' AND project=? AND req_slug=?",
        (project, req_slug)).fetchone()
    if row:
        con.execute(
            "UPDATE work SET req_state=?, branch=?, head_commit=?, change_md=?, "
            "payload_json=?, payload_version=payload_version+1, claude_session_id=?, "
            "transcript_path=?, updated_at=?, dirty=1 WHERE id=?",
            (state, branch, head, change_md, payload, session_id, transcript_path, ts, row[0]))
    else:
        cur = con.execute(
            "INSERT INTO work (mode, project, req_slug, owner, lock_state, req_state, branch, "
            "head_commit, repo_path, change_md, payload_json, origin_dev, origin_machine, "
            "claude_session_id, transcript_path, created_at, updated_at) "
            "VALUES ('req',?,?,?,'owned',?,?,?,?,?,?,?,?,?,?,?,?)",
            (project, req_slug, owner, state, branch, head, repo_path, change_md, payload,
             owner, machine, session_id, transcript_path, ts, ts))
        _event(con, cur.lastrowid, owner, machine, "publish")


def _upsert_exploratory(con, session_id, owner, machine, summary, branch, head, cwd, transcript_path):
    ts = now_iso()
    payload = json.dumps({"summary": summary}, ensure_ascii=False)
    row = con.execute(
        "SELECT id FROM work WHERE mode='exploratory' AND claude_session_id=?",
        (session_id,)).fetchone()
    if row:
        con.execute(
            "UPDATE work SET payload_json=?, branch=?, head_commit=?, transcript_path=?, "
            "updated_at=?, dirty=1 WHERE id=?",
            (payload, branch, head, transcript_path, ts, row[0]))
    else:
        cur = con.execute(
            "INSERT INTO work (mode, owner, lock_state, branch, head_commit, repo_path, "
            "payload_json, origin_dev, origin_machine, claude_session_id, transcript_path, "
            "created_at, updated_at) VALUES ('exploratory',?,'owned',?,?,?,?,?,?,?,?,?,?)",
            (owner, branch, head, cwd, payload, owner, machine, session_id, transcript_path, ts, ts))
        _event(con, cur.lastrowid, owner, machine, "publish")


def _event(con, work_id, dev, machine, action, prev_owner=None, note=None):
    con.execute(
        "INSERT INTO event (work_id, ts, dev, action, prev_owner, machine, note) VALUES (?,?,?,?,?,?,?)",
        (work_id, now_iso(), dev, action, prev_owner, machine, note))


# ----------------------------------------------------------------------- memoria

def find_active_req(memory_dir):
    """project_*.md con §Requerimiento activo: el más reciente y bien-formado → dict (o None)."""
    try:
        files = [f for f in os.listdir(memory_dir) if f.startswith("project_") and f.endswith(".md")]
    except OSError:
        return None
    candidates = []
    for fname in files:
        fpath = os.path.join(memory_dir, fname)
        try:
            content = open(fpath, encoding="utf-8").read()
            mtime = os.path.getmtime(fpath)
        except OSError:
            continue
        if "## Requerimiento activo" not in content:
            continue
        block = content.split("## Requerimiento activo", 1)[1]
        d = {
            "name":         _field(block, "Nombre"),
            "project_path": _field(block, "Path del proyecto"),
            "draft":        _field(block, "Draft changes MD"),
            "state":        _field(block, "Estado"),
            "plan":         _field(block, "Plan resumido"),
            "files":        _field(block, "Archivos modificados hasta ahora"),
            "next_steps":   _field(block, "Próximos pasos"),
            "pending_delivery": _field(block, "Pendiente de entrega"),
        }
        well_formed = bool(d["name"] and d["project_path"])
        candidates.append((well_formed, mtime, d))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    return candidates[0][2]


def _field(text, label):
    """Valor de una línea tipo '- **Label:** value' o 'Label: value'."""
    pat = re.compile(r"^[\s\-*]*" + re.escape(label) + r"\s*:\s*\**\s*(.+?)\s*$", re.MULTILINE)
    m = pat.search(text)
    return m.group(1).strip() if m else ""


def _first_user_prompt(jsonl_path, limit=120):
    """Primer turno de usuario con texto (resumen del tema en modo exploratorio)."""
    if not os.path.isfile(jsonl_path):
        return ""
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "user":
                    continue
                msg = entry.get("message") or {}
                content = msg.get("content")
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
                text = text.strip()
                if text and not text.startswith("<"):
                    return text[:limit]
    except OSError:
        pass
    return ""


# -------------------------------------------------------------------------- util

def _whoami():
    return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


def _basename(path):
    return os.path.basename(path.rstrip("/\\")) if path else ""


def _hostname():
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown"


def _git(cwd, *args):
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=2)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _git_info(cwd):
    """(branch, short_head) del repo en cwd; (None, None) si no es repo o git falla."""
    return _git(cwd, "rev-parse", "--abbrev-ref", "HEAD"), _git(cwd, "rev-parse", "--short", "HEAD")


def _project_id(path):
    """Identidad estable del proyecto cross-máquina: host/owner/repo del git remote (REQ B).
    Prefiere `origin`; si no, el primer remote. Sin remote → basename(path)
    (NO estable cross-máquina → ese work no es relevable cross-dev de forma fiable)."""
    if not path:
        return ""
    url = _git(path, "remote", "get-url", "origin")
    if not url:
        remotes = _git(path, "remote")
        if remotes:
            first = remotes.splitlines()[0].strip()
            if first:
                url = _git(path, "remote", "get-url", first)
    if not url:
        return _basename(path)
    return _normalize_remote(url)


def _normalize_remote(url):
    """git@host:owner/repo(.git) | proto://[user@]host/owner/repo(.git) → host/owner/repo."""
    u = url.strip()
    if u.endswith(".git"):
        u = u[:-4]
    m = re.match(r"^[^@/]+@([^:/]+):(.+)$", u)          # scp-like ssh
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://(?:[^@/]+@)?([^/]+)/(.+)$", u)  # url scheme
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return u


# =========================================================================== sync (REQ B)
# Drena el outbox (works dirty) al central + sube el transcript incremental. Best-effort.

def _central():
    """(endpoint, token) del central si ambos están en el entorno; (None, None) si no."""
    ep = os.environ.get("NEB_LOGBOOK_ENDPOINT")
    tok = os.environ.get("NEB_LOGBOOK_TOKEN")
    return (ep, tok) if ep and tok else (None, None)


def _is_shared(cwd):
    """Disparador determinista: el central (compartido) es OPT-IN por proyecto.
    Compartido sii hay endpoint Y el CLAUDE.md del cwd trae el marcador `<!-- neb-logbook: central -->`.
    Sin endpoint o sin marcador → local-only (la bitácora local de REQ A es el default).
    El default es local porque la bitácora local ya cubre el relevo del propio dev; el central
    se reserva a los proyectos que deliberadamente lo comparten con el equipo."""
    if not os.environ.get("NEB_LOGBOOK_ENDPOINT"):
        return False
    claude_md = os.path.join(cwd, "CLAUDE.md")
    try:
        if os.path.isfile(claude_md):
            txt = open(claude_md, encoding="utf-8", errors="replace").read()
            if re.search(r"<!--\s*neb-logbook:\s*central\s*-->", txt):
                return True
    except OSError:
        pass
    return False


def _maybe_spawn_sync(cwd, guide_dir, home_dir):
    """Lanza `logbook.py sync` detached si el entorno es compartido. No bloquea el turno."""
    if not _is_shared(cwd):
        return
    try:
        kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "sync", guide_dir, home_dir], **kwargs)
    except Exception:
        pass


def _http(endpoint, token, path, method="GET", payload=None):
    """Request JSON al central. Devuelve (status_code|None, dict). Defensivo (timeouts cortos)."""
    import urllib.request
    import urllib.error
    url = endpoint.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": "Bearer " + token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}
    except (urllib.error.URLError, OSError, ValueError):
        return None, {}


def sync_main(args):
    guide = posix_to_win(args[0]) if args else (os.environ.get("NEB_HOME") or "")
    home  = posix_to_win(args[1]) if len(args) >= 2 else os.path.expanduser("~")
    endpoint, token = _central()
    if not endpoint or not token:
        return
    db_path     = os.path.join(home, ".claude", "neb-logbook.db")
    schema_path = os.path.join(guide, "hooks", "logbook-schema.sql") if guide else ""
    con = _connect(db_path, schema_path)
    if con is None:
        return
    con.row_factory = sqlite3.Row
    try:
        _drain_works(con, endpoint, token)
        _drain_transcripts(con, endpoint, token)
    finally:
        con.close()


def _drain_works(con, endpoint, token):
    rows = con.execute("SELECT * FROM work WHERE dirty=1").fetchall()
    for w in rows:
        payload = {
            "mode": w["mode"], "project": w["project"], "req_slug": w["req_slug"],
            "owner": w["owner"], "req_state": w["req_state"], "branch": w["branch"],
            "head_commit": w["head_commit"], "repo_path": w["repo_path"], "change_md": w["change_md"],
            "payload_json": w["payload_json"], "payload_version": w["payload_version"],
            "origin_dev": w["origin_dev"], "origin_machine": w["origin_machine"],
            "claude_session_id": w["claude_session_id"],
            "transcript_path": w["transcript_path"],
        }
        code, resp = _http(endpoint, token, "/work/publish", "POST", payload)
        if code == 200:
            con.execute("UPDATE work SET dirty=0, synced_at=?, remote_id=?, conflict=0 WHERE id=?",
                        (now_iso(), resp.get("remote_id"), w["id"]))
            con.commit()
        elif code == 409:
            con.execute("UPDATE work SET dirty=0, conflict=1 WHERE id=?", (w["id"],))
            con.commit()
        # None/5xx: dejar dirty=1 → reintenta el próximo turno


def _drain_transcripts(con, endpoint, token):
    works = con.execute(
        "SELECT id, remote_id, claude_session_id, transcript_path FROM work "
        "WHERE remote_id IS NOT NULL AND transcript_path IS NOT NULL").fetchall()
    for w in works:
        sid = w["claude_session_id"]
        path = posix_to_win(w["transcript_path"] or "")
        if not sid or not path or not os.path.isfile(path):
            continue
        cur = con.execute("SELECT synced_byte FROM transcript_cursor WHERE session_id=? AND work_id=?",
                          (sid, w["id"])).fetchone()
        start = cur["synced_byte"] if cur else 0
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size <= start:
            continue
        try:
            with open(path, "rb") as f:
                f.seek(start)
                chunk = f.read()
        except OSError:
            continue
        content = chunk.decode("utf-8", errors="replace")
        text_plain = _extract_text_plain(content)
        code, _ = _http(endpoint, token, "/transcript", "POST", {
            "session_id": sid, "work_id": w["remote_id"],
            "byte_from": start, "byte_to": size,
            "content": content, "text_plain": text_plain,
        })
        if code == 200:
            con.execute(
                "INSERT INTO transcript_cursor (session_id, work_id, synced_byte, updated_at) "
                "VALUES (?,?,?,?) ON CONFLICT(session_id, work_id) DO UPDATE SET "
                "synced_byte=excluded.synced_byte, updated_at=excluded.updated_at",
                (sid, w["id"], size, now_iso()))
            con.commit()


def _extract_text_plain(jsonl_text):
    """Texto conversacional (bloques user/assistant type=='text') del JSONL. Omite tool_result/tool_use
    y las líneas estructurales no-conversacionales (last-prompt, file-history-snapshot, attachment, etc.):
    al generalizar de 'user' a 'assistant' se pierde el filtro implícito de _first_user_prompt → filtrar por type."""
    out = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") not in ("user", "assistant"):
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, str):
            if content:
                out.append(content)
        elif isinstance(content, list):
            for blk in content:
                if isinstance(blk, dict) and blk.get("type") == "text":
                    t = blk.get("text", "")
                    if t:
                        out.append(t)
    return "\n".join(out)


# =========================================================================== CLI (/logbook)
# Con NEB_LOGBOOK_ENDPOINT configurado, el CLI opera contra el CENTRAL (autoridad; ids remotos).
# Sin él, contra el SQLite local (REQ A; lock informativo).

CLI_CMDS = {"list", "show", "claim", "release", "forced-release", "request", "rename", "archive", "search"}


def _db_for_cli():
    home  = os.path.expanduser("~")
    guide = posix_to_win(os.environ.get("NEB_HOME", "")) or os.path.join(home, ".claude", "neb")
    return _connect(os.path.join(home, ".claude", "neb-logbook.db"),
                    os.path.join(guide, "hooks", "logbook-schema.sql"))


def cli_list(_args):
    ep, tok = _central()
    if ep:
        code, resp = _http(ep, tok, "/work")
        print(json.dumps(resp.get("works", []) if code == 200 else {"error": code, **resp},
                         ensure_ascii=False, indent=2, default=str))
        return
    con = _db_for_cli()
    if con is None:
        print("[]"); return
    rows = con.execute(
        "SELECT id, mode, COALESCE(project,''), COALESCE(req_slug,''), owner, lock_state, "
        "COALESCE(req_state,''), updated_at FROM work WHERE archived_at IS NULL "
        "ORDER BY updated_at DESC").fetchall()
    con.close()
    print(json.dumps([
        {"id": r[0], "mode": r[1], "project": r[2], "req_slug": r[3], "owner": r[4],
         "lock_state": r[5], "req_state": r[6], "updated_at": r[7]} for r in rows
    ], ensure_ascii=False, indent=2))


def cli_show(args):
    if not args:
        print("uso: show <id>"); return
    ep, tok = _central()
    if ep:
        code, resp = _http(ep, tok, "/work/" + str(args[0]))
        print(json.dumps(resp, ensure_ascii=False, indent=2, default=str) if code == 200 else f"work {args[0]}: {code}")
        return
    con = _db_for_cli()
    if con is None:
        return
    cur = con.execute("SELECT * FROM work WHERE id=?", (args[0],))
    r = cur.fetchone()
    cols = [c[0] for c in cur.description] if r else []
    ev = [dict(zip(("ts", "dev", "action", "prev_owner"), e))
          for e in con.execute("SELECT ts,dev,action,prev_owner FROM event WHERE work_id=? ORDER BY id", (args[0],))]
    con.close()
    if not r:
        print(f"work {args[0]} no encontrado"); return
    print(json.dumps({**dict(zip(cols, r)), "events": ev}, ensure_ascii=False, indent=2, default=str))


def cli_lock(action, args):
    """claim/release/forced-release. Con central → atómico ahí; sin central → informativo local (REQ A)."""
    if not args:
        print(f"uso: {action} <id>"); return
    wid = args[0]
    me  = _whoami()
    machine = _hostname()
    ep, tok = _central()
    if ep:
        path = {"claim": "/work/claim", "release": "/work/release",
                "forced-release": "/work/forced-release"}[action]
        code, resp = _http(ep, tok, path, "POST", {"id": int(wid), "owner": me, "machine": machine})
        print(f"{action} → {code}: {json.dumps(resp, ensure_ascii=False)}")
        return
    con = _db_for_cli()
    if con is None:
        return
    r = con.execute("SELECT owner FROM work WHERE id=?", (wid,)).fetchone()
    if not r:
        print(f"work {wid} no encontrado"); con.close(); return
    prev_owner = r[0]
    ts = now_iso()
    if action == "claim":
        con.execute("UPDATE work SET owner=?, lock_state='owned', locked_at=?, dirty=1 WHERE id=?", (me, ts, wid))
        _event(con, wid, me, machine, "claim", prev_owner=prev_owner)
    elif action == "release":
        con.execute("UPDATE work SET lock_state='released', locked_at=?, dirty=1 WHERE id=?", (ts, wid))
        _event(con, wid, me, machine, "release")
    elif action == "forced-release":
        con.execute("UPDATE work SET owner=?, lock_state='released', takeover_by=NULL, locked_at=?, dirty=1 WHERE id=?", (me, ts, wid))
        _event(con, wid, me, machine, "forced_release", prev_owner=prev_owner)
    con.commit(); con.close()
    print(f"{action} OK (work {wid}). Nota: en backend local el lock es informativo; "
          f"el relevo cross-dev real requiere el backend central (NEB_LOGBOOK_ENDPOINT).")


def cli_request(args):
    if not args:
        print("uso: request <id>"); return
    ep, tok = _central()
    if not ep:
        print("'request' (solicitar el mando) requiere el backend central "
              "(NEB_LOGBOOK_ENDPOINT/NEB_LOGBOOK_TOKEN no configurados)."); return
    code, resp = _http(ep, tok, "/work/request-takeover", "POST",
                       {"id": int(args[0]), "owner": _whoami(), "machine": _hostname()})
    print(f"request → {code}: {json.dumps(resp, ensure_ascii=False)}")


def cli_rename(args):
    if len(args) < 2:
        print("uso: rename <id> <new_req_slug> [new_project]"); return
    ep, tok = _central()
    if ep:
        payload = {"id": int(args[0]), "owner": _whoami(), "machine": _hostname(), "new_req_slug": args[1]}
        if len(args) >= 3:
            payload["new_project"] = args[2]
        code, resp = _http(ep, tok, "/work/rename", "POST", payload)
        print(f"rename → {code}: {json.dumps(resp, ensure_ascii=False)}")
        return
    con = _db_for_cli()
    if con is None:
        return
    con.execute("UPDATE work SET req_slug=?, updated_at=?, dirty=1 WHERE id=? AND mode='req'",
                (args[1], now_iso(), args[0]))
    _event(con, args[0], _whoami(), _hostname(), "rename", note=f"-> {args[1]}")
    con.commit(); con.close()
    print(f"rename OK local (work {args[0]} → {args[1]}).")


def cli_archive(args):
    """Archiva el work (cierre del REQ). Con central → POST /work/archive; sin central → local."""
    if not args:
        print("uso: archivar <id>"); return
    wid, me, machine = args[0], _whoami(), _hostname()
    ep, tok = _central()
    if ep:
        code, resp = _http(ep, tok, "/work/archive", "POST", {"id": int(wid), "owner": me, "machine": machine})
        print(f"archive → {code}: {json.dumps(resp, ensure_ascii=False)}")
        return
    con = _db_for_cli()
    if con is None:
        return
    con.execute("UPDATE work SET archived_at=?, dirty=1 WHERE id=? AND archived_at IS NULL", (now_iso(), wid))
    _event(con, wid, me, machine, "archive")
    con.commit(); con.close()
    print(f"archive OK local (work {wid}).")


def cli_search(args):
    if not args:
        print("uso: search <texto>"); return
    ep, tok = _central()
    if not ep:
        print("'search' requiere el backend central (NEB_LOGBOOK_ENDPOINT/NEB_LOGBOOK_TOKEN no configurados)."); return
    import urllib.parse
    code, resp = _http(ep, tok, "/search?q=" + urllib.parse.quote(" ".join(args)))
    print(json.dumps(resp.get("results", []) if code == 200 else {"error": code, **resp},
                     ensure_ascii=False, indent=2, default=str))


def cli_main(argv):
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        cli_list(rest)
    elif cmd == "show":
        cli_show(rest)
    elif cmd in ("claim", "release", "forced-release"):
        cli_lock(cmd, rest)
    elif cmd == "request":
        cli_request(rest)
    elif cmd == "rename":
        cli_rename(rest)
    elif cmd == "archive":
        cli_archive(rest)
    elif cmd == "search":
        cli_search(rest)
    else:
        print(f"subcomando desconocido: {cmd}")


if __name__ == "__main__":
    try:
        if len(sys.argv) >= 2 and sys.argv[1] == "sync":
            sync_main(sys.argv[2:])
        elif len(sys.argv) >= 2 and sys.argv[1] in CLI_CMDS:
            cli_main(sys.argv[1:])
        else:
            main()
    except Exception as e:
        print(f"[logbook] ERROR inesperado: {e}", file=sys.stderr)
    sys.exit(0)
