#!/usr/bin/env python3
"""
logbook_server.py — servidor de referencia del backend CENTRAL de la bitácora de relevo (Neb, REQ B).

Autoridad del lock + corpus buscable. stdlib http.server + PyMySQL (única dependencia, ver requirements.txt).
Escucha HTTP en host:puerto; se asume detrás de un reverse proxy (Apache/nginx) que termina TLS.
NO maneja TLS ni despliegue — eso es del overlay del adoptante (ver INSTALL.md).

Contrato (todas las rutas salvo /healthz requieren `Authorization: Bearer <NEB_LOGBOOK_TOKEN>`):
  GET  /healthz                  liveness (sin auth)
  POST /work/publish             UPSERT por identity_key (req=project+req_slug, expl=claude_session_id)
  POST /work/claim               toma atómica del lock (solo req)
  POST /work/release             libera el lock (solo req, owner)
  POST /work/request-takeover    marca takeover_requested (solo req)
  POST /work/forced-release      libera el lock sin ser owner (solo req; confirmación en el cliente)
  POST /work/rename              migra req_slug/project preservando historial (solo req, owner)
  POST /work/archive             cierre del REQ: marca archived_at (no borra; idempotente)
  POST /transcript               fragmento incremental idempotente por (session_id,byte_from,byte_to)
  GET  /search?q=...             FULLTEXT sobre transcript.text_plain
  GET  /work                     lista works activos
  GET  /work/<id>                detalle + events

El lock gobierna la escritura: publish/transcript de un work 'req' se aceptan solo si el owner
entrante == owner vigente (o nuevo/released); si no → 409. payload_version optimista. Nunca last-writer-wins.
Las ops de lock sobre un work 'exploratory' devuelven 400 (no tienen lock) — el 409 queda para el conflicto real.

Config por entorno:
  NEB_LOGBOOK_TOKEN        token Bearer esperado (obligatorio)
  NEB_LOGBOOK_DB_HOST      default 127.0.0.1
  NEB_LOGBOOK_DB_PORT      default 3306
  NEB_LOGBOOK_DB_USER      default neb_logbook
  NEB_LOGBOOK_DB_PASSWORD  (obligatorio)
  NEB_LOGBOOK_DB_NAME      default neb_logbook
Flags: --host (default 127.0.0.1) --port (default 8787).
"""

import argparse
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

try:
    import pymysql
    from pymysql.cursors import DictCursor
    from pymysql.err import IntegrityError
except ImportError:
    sys.stderr.write("[logbook-server] falta PyMySQL: pip install -r server/requirements.txt\n")
    raise


# --------------------------------------------------------------------------- config

TOKEN = os.environ.get("NEB_LOGBOOK_TOKEN", "")
DB = {
    "host": os.environ.get("NEB_LOGBOOK_DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("NEB_LOGBOOK_DB_PORT", "3306")),
    "user": os.environ.get("NEB_LOGBOOK_DB_USER", "neb_logbook"),
    "password": os.environ.get("NEB_LOGBOOK_DB_PASSWORD", ""),
    "database": os.environ.get("NEB_LOGBOOK_DB_NAME", "neb_logbook"),
}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _connect():
    return pymysql.connect(charset="utf8mb4", cursorclass=DictCursor, autocommit=False, **DB)


def _event(cur, work_id, dev, machine, action, prev_owner=None, note=None):
    cur.execute(
        "INSERT INTO event (work_id, ts, dev, action, prev_owner, machine, note) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (work_id, _now(), dev or "unknown", action, prev_owner, machine, note))


# ------------------------------------------------------------------------ operations
# Cada op recibe (conn, body|query) y devuelve (status_code, dict). Commit dentro de la op.

def op_publish(conn, b):
    mode = b.get("mode", "req")
    owner = b.get("owner")
    machine = b.get("origin_machine")
    cur = conn.cursor()
    if mode == "req":
        cur.execute("SELECT id, owner, lock_state, payload_version FROM work "
                    "WHERE mode='req' AND project=%s AND req_slug=%s",
                    (b.get("project"), b.get("req_slug")))
    else:
        cur.execute("SELECT id, owner, lock_state, payload_version FROM work "
                    "WHERE mode='exploratory' AND claude_session_id=%s",
                    (b.get("claude_session_id"),))
    row = cur.fetchone()
    now = _now()
    if row is None:
        lock = "owned" if mode == "req" else None
        cur.execute(
            "INSERT INTO work (mode, project, req_slug, owner, lock_state, locked_at, req_state, "
            "branch, head_commit, repo_path, change_md, payload_json, payload_version, origin_dev, "
            "origin_machine, claude_session_id, claude_session_name, transcript_path, created_at, updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (mode, b.get("project"), b.get("req_slug"), owner, lock, now if lock else None,
             b.get("req_state"), b.get("branch"), b.get("head_commit"), b.get("repo_path"),
             b.get("change_md"), b.get("payload_json"), b.get("payload_version", 0), owner,
             machine, b.get("claude_session_id"), b.get("claude_session_name"),
             b.get("transcript_path"), now, now))
        wid = cur.lastrowid
        _event(cur, wid, owner, machine, "publish")
        conn.commit()
        return 200, {"remote_id": wid, "payload_version": b.get("payload_version", 0)}

    wid = row["id"]
    # El LOCK (owner) gobierna la escritura, no el reloj: solo el owner vigente de un work 'req'
    # publica. payload_version es metadato monotónico informativo (contador local del origen, diverge
    # entre máquinas) — NO un gate; la autoridad del 409 es el owner. Se conserva con GREATEST.
    if mode == "req" and row["lock_state"] == "owned" and row["owner"] and row["owner"] != owner:
        return 409, {"error": "not_owner", "detail": "work owned by %s" % row["owner"]}
    cur.execute(
        "UPDATE work SET req_state=%s, branch=%s, head_commit=%s, repo_path=%s, change_md=%s, "
        "payload_json=%s, payload_version=GREATEST(%s, payload_version), claude_session_id=%s, "
        "claude_session_name=%s, transcript_path=%s, updated_at=%s WHERE id=%s",
        (b.get("req_state"), b.get("branch"), b.get("head_commit"), b.get("repo_path"),
         b.get("change_md"), b.get("payload_json"), b.get("payload_version", 0),
         b.get("claude_session_id"), b.get("claude_session_name"), b.get("transcript_path"), now, wid))
    conn.commit()
    return 200, {"remote_id": wid}


def _load_work(cur, wid):
    cur.execute("SELECT id, mode, owner, lock_state FROM work WHERE id=%s", (wid,))
    return cur.fetchone()


def op_claim(conn, b):
    wid, me, machine = b.get("id"), b.get("owner"), b.get("machine")
    cur = conn.cursor()
    row = _load_work(cur, wid)
    if not row:
        return 404, {"error": "not_found"}
    if row["mode"] != "req":
        return 400, {"error": "not_applicable", "detail": "exploratory work has no lock"}
    cur.execute("UPDATE work SET owner=%s, lock_state='owned', takeover_by=NULL, locked_at=%s, "
                "updated_at=%s WHERE id=%s AND lock_state IN ('released','takeover_requested')",
                (me, _now(), _now(), wid))
    if cur.rowcount == 0:
        return 409, {"error": "locked", "detail": "owned by %s" % row["owner"]}
    _event(cur, wid, me, machine, "claim", prev_owner=row["owner"])
    conn.commit()
    return 200, {"ok": True}


def op_release(conn, b):
    wid, me, machine = b.get("id"), b.get("owner"), b.get("machine")
    cur = conn.cursor()
    row = _load_work(cur, wid)
    if not row:
        return 404, {"error": "not_found"}
    if row["mode"] != "req":
        return 400, {"error": "not_applicable", "detail": "exploratory work has no lock"}
    cur.execute("UPDATE work SET lock_state='released', locked_at=%s, updated_at=%s "
                "WHERE id=%s AND owner=%s", (_now(), _now(), wid, me))
    if cur.rowcount == 0:
        return 409, {"error": "not_owner", "detail": "owned by %s" % row["owner"]}
    _event(cur, wid, me, machine, "release")
    conn.commit()
    return 200, {"ok": True}


def op_request_takeover(conn, b):
    wid, me, machine = b.get("id"), b.get("owner"), b.get("machine")
    cur = conn.cursor()
    row = _load_work(cur, wid)
    if not row:
        return 404, {"error": "not_found"}
    if row["mode"] != "req":
        return 400, {"error": "not_applicable", "detail": "exploratory work has no lock"}
    cur.execute("UPDATE work SET lock_state='takeover_requested', takeover_by=%s, updated_at=%s "
                "WHERE id=%s AND lock_state='owned' AND owner<>%s", (me, _now(), wid, me))
    if cur.rowcount == 0:
        return 409, {"error": "not_takeable", "detail": "lock_state=%s owner=%s" % (row["lock_state"], row["owner"])}
    _event(cur, wid, me, machine, "request_takeover", prev_owner=row["owner"])
    conn.commit()
    return 200, {"ok": True}


def op_forced_release(conn, b):
    wid, me, machine = b.get("id"), b.get("owner"), b.get("machine")
    cur = conn.cursor()
    row = _load_work(cur, wid)
    if not row:
        return 404, {"error": "not_found"}
    if row["mode"] != "req":
        return 400, {"error": "not_applicable", "detail": "exploratory work has no lock"}
    cur.execute("UPDATE work SET lock_state='released', takeover_by=NULL, locked_at=%s, updated_at=%s "
                "WHERE id=%s", (_now(), _now(), wid))
    _event(cur, wid, me, machine, "forced_release", prev_owner=row["owner"])
    conn.commit()
    return 200, {"ok": True, "prev_owner": row["owner"]}


def op_rename(conn, b):
    wid, me, machine = b.get("id"), b.get("owner"), b.get("machine")
    new_slug, new_project = b.get("new_req_slug"), b.get("new_project")
    cur = conn.cursor()
    cur.execute("SELECT id, mode, owner, project, req_slug FROM work WHERE id=%s", (wid,))
    row = cur.fetchone()
    if not row:
        return 404, {"error": "not_found"}
    if row["mode"] != "req":
        return 400, {"error": "not_applicable", "detail": "rename only for req works"}
    try:
        cur.execute("UPDATE work SET req_slug=%s, project=COALESCE(%s, project), updated_at=%s "
                    "WHERE id=%s AND owner=%s", (new_slug, new_project, _now(), wid, me))
    except IntegrityError:
        return 409, {"error": "destination_exists", "detail": "a work with that project+req_slug already exists"}
    if cur.rowcount == 0:
        return 409, {"error": "not_owner", "detail": "owned by %s" % row["owner"]}
    note = "%s/%s -> %s/%s" % (row["project"], row["req_slug"], new_project or row["project"], new_slug)
    _event(cur, wid, me, machine, "rename", note=note)
    conn.commit()
    return 200, {"ok": True}


def op_archive(conn, b):
    """Cierre del REQ: marca el work como archivado (no se borra — corpus de auditoría; la purga
    es manual via purge.py). Aplica a req y exploratory; idempotente."""
    wid, me, machine = b.get("id"), b.get("owner"), b.get("machine")
    cur = conn.cursor()
    if not _load_work(cur, wid):
        return 404, {"error": "not_found"}
    cur.execute("UPDATE work SET archived_at=%s, updated_at=%s WHERE id=%s AND archived_at IS NULL",
                (_now(), _now(), wid))
    if cur.rowcount:
        _event(cur, wid, me, machine, "archive")
    conn.commit()
    return 200, {"ok": True}


def op_transcript(conn, b):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transcript (session_id, work_id, byte_from, byte_to, content, text_plain, created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=id",
        (b.get("session_id"), b.get("work_id"), b.get("byte_from"), b.get("byte_to"),
         b.get("content"), b.get("text_plain"), _now()))
    conn.commit()
    return 200, {"ok": True}


def op_search(conn, q):
    cur = conn.cursor()
    cur.execute(
        "SELECT w.id, w.mode, w.project, w.req_slug, w.owner, w.req_state, t.session_id, "
        "SUBSTRING(t.text_plain, 1, 240) AS snippet, "
        "MATCH(t.text_plain) AGAINST(%s IN NATURAL LANGUAGE MODE) AS score "
        "FROM transcript t JOIN work w ON w.id = t.work_id "
        "WHERE MATCH(t.text_plain) AGAINST(%s IN NATURAL LANGUAGE MODE) "
        "ORDER BY score DESC LIMIT 50", (q, q))
    return 200, {"results": cur.fetchall()}


def op_work_list(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, mode, project, req_slug, owner, lock_state, req_state, updated_at "
                "FROM work WHERE archived_at IS NULL ORDER BY updated_at DESC LIMIT 200")
    return 200, {"works": cur.fetchall()}


def op_work_detail(conn, wid):
    cur = conn.cursor()
    cur.execute("SELECT * FROM work WHERE id=%s", (wid,))
    work = cur.fetchone()
    if not work:
        return 404, {"error": "not_found"}
    cur.execute("SELECT ts, dev, action, prev_owner, machine, note FROM event WHERE work_id=%s ORDER BY id", (wid,))
    work["events"] = cur.fetchall()
    return 200, {"work": work}


POST_ROUTES = {
    "/work/publish": op_publish,
    "/work/claim": op_claim,
    "/work/release": op_release,
    "/work/request-takeover": op_request_takeover,
    "/work/forced-release": op_forced_release,
    "/work/rename": op_rename,
    "/work/archive": op_archive,
    "/transcript": op_transcript,
}


# --------------------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "neb-logbook/1.0"

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix) or not TOKEN:
            return False
        return hmac.compare_digest(header[len(prefix):], TOKEN)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/healthz":
            return self._send(200, {"ok": True})
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        conn = None
        try:
            conn = _connect()
            if path == "/search":
                q = (parse_qs(parsed.query).get("q", [""])[0]).strip()
                if not q:
                    return self._send(400, {"error": "missing_q"})
                code, obj = op_search(conn, q)
            elif path == "/work":
                code, obj = op_work_list(conn)
            elif path.startswith("/work/"):
                wid = path[len("/work/"):]
                if not wid.isdigit():
                    return self._send(404, {"error": "not_found"})
                code, obj = op_work_detail(conn, int(wid))
            else:
                code, obj = 404, {"error": "not_found"}
            self._send(code, obj)
        except Exception as e:  # defensivo: nunca tirar el servidor por un request
            self._send(500, {"error": "server_error", "detail": str(e)})
        finally:
            if conn:
                conn.close()

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        op = POST_ROUTES.get(path)
        if not op:
            return self._send(404, {"error": "not_found"})
        body = self._body()
        if body is None:
            return self._send(400, {"error": "bad_json"})
        conn = None
        try:
            conn = _connect()
            code, obj = op(conn, body)
            self._send(code, obj)
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            self._send(500, {"error": "server_error", "detail": str(e)})
        finally:
            if conn:
                conn.close()

    def log_message(self, fmt, *args):  # silenciar el log por defecto a stderr (ruidoso)
        pass


def main():
    ap = argparse.ArgumentParser(description="Neb logbook central reference server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    if not TOKEN:
        sys.stderr.write("[logbook-server] ERROR: NEB_LOGBOOK_TOKEN no configurado.\n")
        sys.exit(1)
    if not DB["password"]:
        sys.stderr.write("[logbook-server] ERROR: NEB_LOGBOOK_DB_PASSWORD no configurado.\n")
        sys.exit(1)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    sys.stderr.write("[logbook-server] escuchando en %s:%d (db %s/%s)\n"
                     % (args.host, args.port, DB["host"], DB["database"]))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
