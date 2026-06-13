#!/usr/bin/env python3
"""
logbook.py — publica/actualiza la entrada del work activo en la bitácora de relevo (SQLite local).

Disparado por el hook `logbook-sync` en Stop / SessionEnd / PreCompact.
Alcance REQ A: backend LOCAL (registra estado + transcript_path + event publish).
El sync al central y la captura de CONTENIDO del transcript son REQ B (este hook deja el cursor preparado).

Argumentos posicionales (los arma el wrapper desde el stdin JSON del hook):
  1. session_id       — UUID de la sesión Claude
  2. cwd              — working directory de la sesión (real, no codificado)
  3. transcript_path  — ruta del .jsonl (la entrega el hook; "" si ausente → se reconstruye)
  4. event_name       — Stop | SessionEnd | PreCompact
  5. guide_dir        — checkout de neb (NEB_HOME), para localizar el schema
  6. home_dir         — HOME del dev

Salida: exit 0 siempre (hook defensivo — errores a stderr, no bloquean al dev).
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone


def posix_to_win(path):
    """Convierte ruta POSIX de Git Bash (/c/Users/foo) a Windows. No-op si ya es Windows o en Linux/Mac."""
    if sys.platform == "win32" and path and re.match(r"^/[a-zA-Z]/", path):
        return f"{path[1].upper()}:\\{path[2:].replace('/', '\\')}"
    return path


def encode_cwd(cwd):
    """CWD → formato de directorio de proyecto Claude: ':' → '-', luego '/' y '\\' → '-'."""
    return cwd.replace(":", "-").replace("/", "-").replace("\\", "-")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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

    encoded     = encode_cwd(cwd)
    projects_dir = os.path.join(home_dir, ".claude", "projects", encoded)
    jsonl_path  = transcript_arg or os.path.join(projects_dir, f"{session_id}.jsonl")
    memory_dir  = os.path.join(projects_dir, "memory")
    schema_path = os.path.join(guide_dir, "hooks", "logbook-schema.sql")
    db_path     = os.path.join(home_dir, ".claude", "neb-logbook.db")

    owner   = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
    machine = _hostname()
    branch, head = _git_info(cwd)

    # ¿REQ activo en memoria? → modo 'req'; si no → 'exploratory'.
    active = find_active_req(memory_dir) if os.path.isdir(memory_dir) else None

    con = _connect(db_path, schema_path)
    if con is None:
        return
    try:
        if active:
            project  = _basename(active.get("project_path") or cwd)
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
    except (OSError, sqlite3.Error) as e:
        print(f"[logbook] ERROR aplicando schema: {e}", file=sys.stderr)
        con.close()
        return None
    return con


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
    """project_*.md con §Requerimiento activo: el más reciente y bien-formado → dict (o None).

    El memory_dir puede tener varios project_*.md y más de un §Requerimiento activo
    (el invariante de la metodología es uno solo, pero quedan viejos sin cerrar). Heurística:
    preferir los bien-formados (con Nombre + Path), y entre ellos el de mtime más reciente.
    """
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
    """Valor de una línea tipo '- **Label:** value' o 'Label: value' (los ** de cierre van tras ':')."""
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

def _basename(path):
    return os.path.basename(path.rstrip("/\\")) if path else ""


def _hostname():
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown"


def _git_info(cwd):
    """(branch, short_head) del repo en cwd; (None, None) si no es repo o git falla. Rápido, con timeout."""
    def _git(*args):
        try:
            out = subprocess.run(["git", "-C", cwd, *args], capture_output=True,
                                 text=True, timeout=2)
            return out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None
    return _git("rev-parse", "--abbrev-ref", "HEAD"), _git("rev-parse", "--short", "HEAD")


# --------------------------------------------------------------------------- CLI (/logbook)
# El comando/skill `/logbook` invoca estos subcomandos. En backend local-only las operaciones
# de lock son informativas (un dev, una DB); el relevo cross-dev real requiere el central (REQ B).

CLI_CMDS = {"list", "show", "claim", "release", "forced-release", "request", "search"}


def _db_for_cli():
    home   = os.path.expanduser("~")
    guide  = posix_to_win(os.environ.get("NEB_HOME", "")) or os.path.join(home, ".claude", "neb")
    return _connect(os.path.join(home, ".claude", "neb-logbook.db"),
                    os.path.join(guide, "hooks", "logbook-schema.sql"))


def cli_list(_args):
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
    if not args:
        print(f"uso: {action} <id>"); return
    wid = args[0]
    me  = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
    con = _db_for_cli()
    if con is None:
        return
    r = con.execute("SELECT owner FROM work WHERE id=?", (wid,)).fetchone()
    if not r:
        print(f"work {wid} no encontrado"); con.close(); return
    prev_owner = r[0]
    ts, machine = now_iso(), _hostname()
    if action == "claim":
        con.execute("UPDATE work SET owner=?, lock_state='owned', locked_at=?, dirty=1 WHERE id=?", (me, ts, wid))
        _event(con, wid, me, machine, "claim")
    elif action == "release":
        con.execute("UPDATE work SET lock_state='released', locked_at=?, dirty=1 WHERE id=?", (ts, wid))
        _event(con, wid, me, machine, "release")
    elif action == "forced-release":
        con.execute("UPDATE work SET owner=?, lock_state='released', takeover_by=NULL, locked_at=?, dirty=1 WHERE id=?", (me, ts, wid))
        _event(con, wid, me, machine, "forced_release", prev_owner=prev_owner)
    con.commit(); con.close()
    print(f"{action} OK (work {wid}). Nota: en backend local el lock es informativo; "
          f"el relevo cross-dev real requiere el backend central (REQ B).")


def cli_main(argv):
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        cli_list(rest)
    elif cmd == "show":
        cli_show(rest)
    elif cmd in ("claim", "release", "forced-release"):
        cli_lock(cmd, rest)
    elif cmd in ("request", "search"):
        print(f"'{cmd}' requiere el backend central (REQ B); en backend local no aplica.")
    else:
        print(f"subcomando desconocido: {cmd}")


if __name__ == "__main__":
    try:
        if len(sys.argv) >= 2 and sys.argv[1] in CLI_CMDS:
            cli_main(sys.argv[1:])
        else:
            main()
    except Exception as e:
        print(f"[logbook] ERROR inesperado: {e}", file=sys.stderr)
    sys.exit(0)
