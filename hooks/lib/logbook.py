#!/usr/bin/env python3
"""
logbook.py — cliente de la bitácora de relevo (Neb).

Tres modos (dispatch en __main__):
  • captura (sin args reconocidos)  — lo dispara el hook `logbook-sync` en Stop/SessionEnd/PreCompact:
      registra estado + transcript_path del work activo en SQLite local; si el proyecto activa el
      central (NEB_LOGBOOK_ENDPOINT y opt-in por proyecto vía marcador `<!-- neb-logbook: central -->`),
      lanza el modo `sync` detached.
  • sync <guide_dir> <home_dir>     — drena el outbox (works dirty) al central + sube el transcript
      incremental. Best-effort, defensivo (REQ B). Un fallo NO corta el reintento (salvo el 409), pero
      queda VISIBLE en work.last_error / work.transcript_error (ver `sync-status`).
  • CLI (list/show/claim/...)       — lo invoca el comando/skill `/logbook`. Con NEB_LOGBOOK_ENDPOINT
      configurado opera contra el CENTRAL (la autoridad: ids remotos); sin él, contra el SQLite local.
      Excepción: `sync-status` lee SIEMPRE el SQLite local (el estado del outbox no existe en el central)
      y reporta ids LOCALES (`local_id`), que no son válidos para los demás verbos cuando hay central.

Backend local = default + outbox. Backend central (REQ B) = autoridad del lock + corpus buscable.
Filosofía: defensivo — exit 0 siempre; errores a stderr, nunca bloquean al dev. El stderr del sync
detached y del hook se descarta, por eso los fallos de sync se PERSISTEN además de imprimirse.

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

# Infra compartida de la DB (resolver dual-mode + conexión net-new + helpers puros movidos).
# El resolver dual-mode vive SOLO en _db_shared; las 3 sedes de db_path de este módulo lo importan.
from _db_shared import (
    resolve_db_path, _connect, _migrate, begin_immediate, with_write_tx,
    now_iso, posix_to_win, encode_cwd, find_active_reqs, resolve_memory_dir,
    _whoami, _hostname, _git, _git_info, _project_id, _normalize_remote, _basename,
)


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
    memory_dir   = resolve_memory_dir(home_dir, cwd, encoded)   # respeta autoMemoryDirectory; fallback al default
    schema_path  = os.path.join(guide_dir, "hooks", "logbook-schema.sql")
#    db_path      = os.path.join(home_dir, ".claude", "neb-logbook.db")
    db_path      = resolve_db_path(home_dir)

    owner   = _whoami()
    machine = _hostname()
    branch, head = _git_info(cwd)

    active_reqs = find_active_reqs(memory_dir) if os.path.isdir(memory_dir) else []

    con = _connect(db_path, schema_path)
    if con is None:
        return
    try:
        if active_reqs:
            for active in active_reqs:                # N REQ activos (incluye varios del mismo proyecto)
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
        _index_local(con, session_id, None, jsonl_path)   # SR-1: persistir el corpus local (siempre)
        con.commit()
    finally:
        con.close()

    # REQ B: si el entorno es compartido, drenar el outbox al central (detached, best-effort).
    _maybe_spawn_sync(cwd, guide_dir, home_dir)


# --------------------------------------------------------------------------- DB
# _connect / _migrate se movieron a _db_shared.py (importados arriba); aquí solo viven
# los upserts/eventos específicos del logbook que usan esa conexión.

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
# find_active_reqs (plural, soporta N REQ activos) y el parser _field viven ahora en
# _db_shared.py — fuente única compartida con usage-tracker.py (antes había 2 copias).


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
# _whoami / _basename / _hostname / _git / _git_info / _project_id / _normalize_remote
# se movieron a _db_shared.py (importados arriba). Aquí no se redefinen.


# =========================================================================== sync (REQ B)
# Drena el outbox (works dirty) al central + sube el transcript incremental. Best-effort.

def _central():
    """(endpoint, token) del central si ambos están en el entorno; (None, None) si no."""
    ep = os.environ.get("NEB_LOGBOOK_ENDPOINT")
    tok = (os.environ.get("NEB_LOGBOOK_TOKEN") or "").strip()
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
    import http.client
    import urllib.request
    import urllib.error
    url = endpoint.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": "Bearer " + token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        # El Request va DENTRO del try: un endpoint sin esquema ("host/ruta") lanza ValueError al construirlo.
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
        # Sin código HTTP utilizable: DNS/conexión/TLS (URLError), timeout (OSError), respuesta truncada o
        # línea de estado inválida (HTTPException), URL mal formada o un 2xx con cuerpo no-JSON (ValueError:
        # portal cautivo, WAF). Se conserva el motivo para que el fallo sea diagnosticable. El token viaja
        # en el header, pero un token con CR/LF lo hace aparecer en el ValueError de http.client: se enmascara.
        detail = str(e)
        for secret in {token, token.strip()}:
            if secret:
                detail = detail.replace(secret, "***")
        return None, {"error": type(e).__name__, "detail": detail[:200]}


def sync_main(args):
    guide = posix_to_win(args[0]) if args else (os.environ.get("NEB_HOME") or "")
    home  = posix_to_win(args[1]) if len(args) >= 2 else os.path.expanduser("~")
    endpoint, token = _central()
    if not endpoint or not token:
        # El sync detached tiene stderr en DEVNULL: este aviso solo se ve en un `sync` manual,
        # que de otro modo sería un no-op mudo.
        print("[logbook] sync: central no configurado (falta NEB_LOGBOOK_ENDPOINT y/o NEB_LOGBOOK_TOKEN); "
              "nada que drenar", file=sys.stderr)
        return
#    db_path     = os.path.join(home, ".claude", "neb-logbook.db")
    db_path     = resolve_db_path(home)
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


# --- fallos de sync visibles -------------------------------------------------------------------
# Un fallo que no sea 200 NO corta el reintento (salvo el 409, que ya lo cortaba), pero deja de ser
# mudo: se persiste por canal en work.last_error (publish) / work.transcript_error (transcript).
# Dos pares y no uno porque ambos drenajes pueden tocar la misma fila en el mismo sync: con un solo
# slot el segundo pisaría la causa del primero. Cada drenaje escribe y limpia SOLO su par.

_SYNC_ERR_MAX = 500


def _sync_error_text(channel, code, resp, token=None):
    """'<canal> <código|sin respuesta HTTP> <error>: <detail>', omitiendo las partes vacías.
    `resp` viene de _http: puede ser {} (cuerpo no-JSON) o no ser dict (JSON válido que no es objeto)."""
    resp = resp if isinstance(resp, dict) else {}
    head = f"{channel} {code if code is not None else 'sin respuesta HTTP'}"
    parts = [str(resp.get(k) or "").strip() for k in ("error", "detail")]
    body = ": ".join(p for p in parts if p) or "(sin cuerpo JSON)"
    text = f"{head} {body}"
    if token:
        text = text.replace(token, "***")      # defensa en profundidad: el detail lo redacta el servidor
    return text[:_SYNC_ERR_MAX]


def _quiet_rollback(con):
    try:
        if getattr(con, "in_transaction", False):
            con.rollback()
    except Exception:
        pass


def _record_sync_error(con, work_id, col, text, prev, only_if_dirty=False):
    """Persiste el fallo vigente de un canal en work.<col> / work.<col>_at. NUNCA propaga: registrar el
    error no puede tumbar el drenaje de los demás works (antes esta rama no hacía nada y no podía fallar).
    No reescribe si el texto no cambió: en régimen estable son 0 escrituras y <col>_at responde
    'desde cuándo falla', no 'cuándo fue el último reintento'.
    `col` es una constante interna ('last_error' | 'transcript_error'), nunca entrada externa.
    only_if_dirty: no registrar si otro sync ya publicó este work mientras este POST estaba en vuelo."""
    print(f"[logbook] sync work {work_id}: {text}", file=sys.stderr)
    if text == prev:
        return
    sql = f"UPDATE work SET {col}=?, {col}_at=? WHERE id=?" + (" AND dirty=1" if only_if_dirty else "")
    try:
        con.execute(sql, (text, now_iso(), work_id))
        con.commit()
    except Exception as e:
        _quiet_rollback(con)
        print(f"[logbook] aviso: no se pudo registrar el fallo de sync del work {work_id}: {e}", file=sys.stderr)


def _clear_sync_error(con, work_id, col, prev):
    """Limpia el par <col>/<col>_at solo si había algo (evita un UPDATE+commit por fila sana). Nunca propaga."""
    if prev is None:
        return
    try:
        con.execute(f"UPDATE work SET {col}=NULL, {col}_at=NULL WHERE id=?", (work_id,))
        con.commit()
    except Exception as e:
        _quiet_rollback(con)
        print(f"[logbook] aviso: no se pudo limpiar {col} del work {work_id}: {e}", file=sys.stderr)


# --- req_state: ENUM hacia el central -----------------------------------------------------------
# El central declara `req_state` como ENUM del requerimiento (vocabulary.md § "Estados del requerimiento",
# VARCHAR(64) en modo estricto). La memoria del proyecto redacta el `Estado:` como ENUM + prosa, y publicar
# esa prosa cruda hacía que el central rechazara el work en cada sync. Solo el payload se normaliza: la
# bitácora local conserva el texto completo, y la prosa viaja en `payload_json.req_state_note`.

_REQ_STATES = ("En progreso", "En validación", "Listo para aprobación", "Cerrado")
_REQ_STATE_ALIASES = {"listo para produccion": "Listo para aprobación"}   # término anterior, documentado
_REQ_STATE_MAX = 64


def _fold(text):
    """Minúsculas sin acentos ni espacios repetidos, para comparar."""
    import unicodedata
    t = unicodedata.normalize("NFD", text)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " ".join(t.lower().split())


def _normalize_req_state(raw):
    """(enum | None, note | None). `enum` es el valor canónico que se publica; `note` es el texto original
    completo cuando trae algo más que el ENUM (o cuando no empieza por ninguno), para que la prosa no se pierda.
    Reconoce el ENUM al INICIO del texto sin distinguir mayúsculas ni acentos, tolera envoltorios markdown
    y el alias `Listo para producción`; el sufijo documentado `(bloqueado …)` se conserva como `(bloqueado)`."""
    raw = (raw or "").strip()
    if not raw:
        return None, None
    text = raw.strip("*_` \t")
    folded = _fold(text)
    candidates = [(_fold(s), s) for s in _REQ_STATES] + [(k, v) for k, v in _REQ_STATE_ALIASES.items()]
    for key, canon in sorted(candidates, key=lambda kv: -len(kv[0])):      # el más largo primero
        # prefijo + frontera de palabra: "en progreso — nota" sí, "en progresos" no
        if folded == key or (folded.startswith(key) and not folded[len(key)].isalnum()):
            rest = folded[len(key):]
            enum = canon + (" (bloqueado)" if re.search(r"\(\s*bloquead", rest) else "")
            note = None if folded == key else raw
            return enum[:_REQ_STATE_MAX], note
    return None, raw


def _payload_json_with_note(payload_json, note):
    """Copia saliente de payload_json con `req_state_note`. Si no hay nota, o el JSON no es un objeto,
    se manda tal cual (nunca se pierde el publish por esto). No modifica el valor local."""
    if not note:
        return payload_json
    try:
        d = json.loads(payload_json) if payload_json else {}
    except (TypeError, ValueError):
        return payload_json
    if not isinstance(d, dict):
        return payload_json
    d["req_state_note"] = note
    return json.dumps(d, ensure_ascii=False)


def _drain_works(con, endpoint, token):
    rows = con.execute("SELECT * FROM work WHERE dirty=1").fetchall()
    for w in rows:
        # Lista EXPLÍCITA de campos: las columnas del outbox (dirty, conflict, last_error…) son solo locales
        # y no viajan al central. No sustituir por dict(w).
        req_state, note = _normalize_req_state(w["req_state"])
        payload = {
            "mode": w["mode"], "project": w["project"], "req_slug": w["req_slug"],
            "owner": w["owner"], "req_state": req_state, "branch": w["branch"],
            "head_commit": w["head_commit"], "repo_path": w["repo_path"], "change_md": w["change_md"],
            "payload_json": _payload_json_with_note(w["payload_json"], note),
            "payload_version": w["payload_version"],
            "origin_dev": w["origin_dev"], "origin_machine": w["origin_machine"],
            "claude_session_id": w["claude_session_id"],
            "transcript_path": w["transcript_path"],
        }
        try:
            code, resp = _http(endpoint, token, "/work/publish", "POST", payload)
            remote_id = resp.get("remote_id") if isinstance(resp, dict) else None
            if code == 200 and remote_id is None:
                # Un 200 sin remote_id no es una publicación (cuerpo vacío, JSON ajeno de un proxy/portal):
                # darlo por publicado dejaría dirty=0 sin remote_id, invisible para sync-status y fuera del
                # drenaje de transcripts. Se trata como fallo y se conserva el reintento.
                code = "200-sin-remote_id"
            if code == 200:
                # Guard de versión: si el work se re-capturó durante el POST, lo publicado es una versión
                # vieja; no hay que bajar dirty ni borrar un last_error que otro sync registró para la nueva.
                cur = con.execute("UPDATE work SET dirty=0, synced_at=?, remote_id=?, conflict=0, "
                                  "last_error=NULL, last_error_at=NULL WHERE id=? AND payload_version=? AND updated_at=?",
                                  (now_iso(), remote_id, w["id"], w["payload_version"], w["updated_at"]))
                if cur.rowcount == 0:
                    con.execute("UPDATE work SET remote_id=?, synced_at=? WHERE id=?",
                                (remote_id, now_iso(), w["id"]))
                con.commit()
            elif code == 409:
                # Conflicto: corta el reintento (dirty=0) y deja el motivo, en un solo UPDATE.
                text = _sync_error_text("publish", code, resp, token)
                since = w["last_error_at"] if (text == w["last_error"] and w["last_error_at"]) else now_iso()
                con.execute("UPDATE work SET dirty=0, conflict=1, last_error=?, last_error_at=? WHERE id=? "
                            "AND payload_version=? AND updated_at=?",
                            (text, since, w["id"], w["payload_version"], w["updated_at"]))
                con.commit()
            else:
                # Sin respuesta, 4xx≠409 o 5xx: dirty se conserva (reintenta el próximo sync) y el fallo queda VISIBLE.
                _record_sync_error(con, w["id"], "last_error", _sync_error_text("publish", code, resp, token),
                                   w["last_error"], only_if_dirty=True)
        except sqlite3.OperationalError as e:
            _quiet_rollback(con)
            print(f"[logbook] aviso: sync work {w['id']}: {e}", file=sys.stderr)
            continue


def _drain_transcripts(con, endpoint, token):
    works = con.execute(
        "SELECT id, remote_id, claude_session_id, transcript_path, transcript_error FROM work "
        "WHERE remote_id IS NOT NULL AND transcript_path IS NOT NULL").fetchall()
    for w in works:
        sid = w["claude_session_id"]
        path = posix_to_win(w["transcript_path"] or "")
        if not sid or not path or not os.path.isfile(path):
            # Ya no hay nada que reintentar (el .jsonl es efímero): un fallo previo dejaría un aviso
            # permanente y sin acción posible. Decisión de diseño: se limpia.
            _clear_sync_error(con, w["id"], "transcript_error", w["transcript_error"])
            continue
        cur = con.execute("SELECT synced_byte FROM transcript_cursor WHERE session_id=? AND work_id=?",
                          (sid, w["id"])).fetchone()
        start = cur["synced_byte"] if cur else 0
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size <= start:
            _clear_sync_error(con, w["id"], "transcript_error", w["transcript_error"])   # al día
            continue
        try:
            with open(path, "rb") as f:
                f.seek(start)
                chunk = f.read()
        except OSError:
            continue
        content = chunk.decode("utf-8", errors="replace")
        text_plain = _extract_text_plain(content)
        try:
            code, resp = _http(endpoint, token, "/transcript", "POST", {
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
                con.execute("UPDATE work SET transcript_error=NULL, transcript_error_at=NULL "
                            "WHERE id=? AND transcript_error IS NOT NULL", (w["id"],))
                con.commit()
            else:
                # Si otro sync ya subió este tramo mientras el POST estaba en vuelo, el fallo está rancio.
                now = con.execute("SELECT synced_byte FROM transcript_cursor WHERE session_id=? AND work_id=?",
                                  (sid, w["id"])).fetchone()
                if (now["synced_byte"] if now else 0) != start:
                    continue
                # El texto NO lleva el tamaño pendiente: en una sesión viva cambia en cada sync y reescribiría
                # transcript_error_at siempre. `sync-status` lo calcula al vuelo (transcript_pending_bytes).
                _record_sync_error(con, w["id"], "transcript_error",
                                   _sync_error_text("transcript", code, resp, token), w["transcript_error"])
        except sqlite3.OperationalError as e:
            _quiet_rollback(con)
            print(f"[logbook] aviso: sync transcript work {w['id']}: {e}", file=sys.stderr)
            continue


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


# --------------------------------------------------------------- corpus local (SR-1)
# Persiste el text_plain de la sesión LOCALMENTE (el .jsonl es efímero) y permite buscarlo
# sin central. Cursor local = MAX(byte_to) de transcript_local. FTS5 on-demand (fallback LIKE).

def _fts5_available(con):
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp._tfts_probe USING fts5(x)")
        con.execute("DROP TABLE IF EXISTS temp._tfts_probe")
        return True
    except sqlite3.OperationalError:
        return False


def _ensure_transcript_fts(con):
    """Crea/sincroniza transcript_fts (FTS5 standalone) desde transcript_local. True si FTS5 hay.
    Standalone (no external content) + rebuild por INSERT SELECT: robusto y sin triggers."""
    if not _fts5_available(con):
        return False
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(session_id UNINDEXED, text_plain)")
    n_fts = con.execute("SELECT count(*) FROM transcript_fts").fetchone()[0]
    n_src = con.execute("SELECT count(*) FROM transcript_local WHERE text_plain <> ''").fetchone()[0]
    if n_fts != n_src:  # (re)poblar desde la tabla local
        con.execute("DELETE FROM transcript_fts")
        con.execute("INSERT INTO transcript_fts (session_id, text_plain) "
                    "SELECT session_id, text_plain FROM transcript_local WHERE text_plain <> ''")
    return True


def _index_local(con, session_id, work_id, jsonl_path):
    """Persiste el text_plain del tramo NUEVO del .jsonl en transcript_local (idempotente por
    rango; cursor = MAX(byte_to)). Best-effort: nunca rompe la captura."""
    try:
        if not jsonl_path or not os.path.isfile(jsonl_path):
            return
        row = con.execute("SELECT COALESCE(MAX(byte_to), 0) FROM transcript_local WHERE session_id=?",
                          (session_id,)).fetchone()
        start = row[0] if row else 0
        size = os.path.getsize(jsonl_path)
        if size <= start:
            return
        with open(jsonl_path, "rb") as f:
            f.seek(start)
            chunk = f.read()
        text_plain = _extract_text_plain(chunk.decode("utf-8", errors="replace"))
        con.execute(
            "INSERT OR IGNORE INTO transcript_local "
            "(session_id, work_id, byte_from, byte_to, text_plain, created_at) VALUES (?,?,?,?,?,?)",
            (session_id, work_id, start, size, text_plain, now_iso()))
    except (OSError, sqlite3.Error):
        return  # best-effort: la captura nunca falla por el indexado local


def _search_local(con, query):
    """Busca en el corpus local. FTS5 si disponible; fallback LIKE. → [(session_id, snippet)]."""
    if _ensure_transcript_fts(con):
        # Tratar el query como frase literal (evita que '_', '-', '"' rompan la sintaxis FTS5).
        phrase = '"' + query.replace('"', '') + '"'
        try:
            rows = con.execute(
                "SELECT session_id, snippet(transcript_fts, 1, '[', ']', ' … ', 12) AS snip "
                "FROM transcript_fts WHERE transcript_fts MATCH ? LIMIT 50", (phrase,)).fetchall()
            if rows:
                return [(r[0], r[1]) for r in rows]
        except sqlite3.OperationalError:
            pass  # cae a LIKE
    rows = con.execute(
        "SELECT session_id, substr(text_plain, 1, 240) FROM transcript_local "
        "WHERE text_plain LIKE ? AND text_plain <> '' LIMIT 50", (f"%{query}%",)).fetchall()
    return [(r[0], r[1]) for r in rows]


# =========================================================================== CLI (/logbook)
# Con NEB_LOGBOOK_ENDPOINT configurado, el CLI opera contra el CENTRAL (autoridad; ids remotos).
# Sin él, contra el SQLite local (REQ A; lock informativo).

CLI_CMDS = {"list", "show", "claim", "release", "forced-release", "request", "rename", "archive", "search",
            "sync-status"}


def _db_for_cli():
    home  = os.path.expanduser("~")
    guide = posix_to_win(os.environ.get("NEB_HOME", "")) or os.path.join(home, ".claude", "neb")
    return _connect(resolve_db_path(home),
#                    os.path.join(home, ".claude", "neb-logbook.db"),
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

    # Simetría transaccional con pendings: BEGIN IMMEDIATE + COMMIT/ROLLBACK con retry ante
    # SQLITE_BUSY (antes era DEFERRED + commit ciego, que ante un escritor concurrente fallaba
    # sin reintento). El SELECT del owner ya ocurrió arriba (lectura); las escrituras van dentro.
    def _do(c):
        if action == "claim":
            c.execute("UPDATE work SET owner=?, lock_state='owned', locked_at=?, dirty=1 WHERE id=?", (me, ts, wid))
            _event(c, wid, me, machine, "claim", prev_owner=prev_owner)
        elif action == "release":
            c.execute("UPDATE work SET lock_state='released', locked_at=?, dirty=1 WHERE id=?", (ts, wid))
            _event(c, wid, me, machine, "release")
        elif action == "forced-release":
            c.execute("UPDATE work SET owner=?, lock_state='released', takeover_by=NULL, locked_at=?, dirty=1 WHERE id=?", (me, ts, wid))
            _event(c, wid, me, machine, "forced_release", prev_owner=prev_owner)

    with_write_tx(con, _do); con.close()
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

    # Simetría transaccional con pendings: BEGIN IMMEDIATE + COMMIT/ROLLBACK con retry ante BUSY.
    def _do(c):
        c.execute("UPDATE work SET req_slug=?, updated_at=?, dirty=1 WHERE id=? AND mode='req'",
                  (args[1], now_iso(), args[0]))
        _event(c, args[0], _whoami(), _hostname(), "rename", note=f"-> {args[1]}")

    with_write_tx(con, _do); con.close()
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

    # Simetría transaccional con pendings: BEGIN IMMEDIATE + COMMIT/ROLLBACK con retry ante BUSY,
    # emitido ANTES del primer write (y del SAVEPOINT del gancho). El gancho on_work_archived
    # usa un SAVEPOINT que EXIGE estar dentro de una transacción; con DEFERRED dependía del
    # BEGIN implícito del primer UPDATE — ahora el BEGIN IMMEDIATE lo garantiza explícitamente.
    def _do(c):
        c.execute("UPDATE work SET archived_at=?, dirty=1 WHERE id=? AND archived_at IS NULL", (now_iso(), wid))
        _event(c, wid, me, machine, "archive")
        # --- gancho aditivo: disparador de obsolescencia "al cerrar el work ligado" ---
        # Best-effort: si pendings no importa o falla, el archive del work NO se rompe (patrón
        # _maybe_spawn_sync). on_work_archived hace ROLLBACK TO SAVEPOINT propio ante error y
        # re-lanza; lo tragamos aquí para que el COMMIT del work siga su curso.
        try:
            import pendings
            pendings.on_work_archived(c, wid, me, machine)
        except Exception as e:
            print(f"[logbook] aviso: on_work_archived omitido: {e}", file=sys.stderr)

    with_write_tx(con, _do); con.close()
    print(f"archive OK local (work {wid}).")


def cli_search(args):
    if not args:
        print("uso: search <texto>"); return
    query = " ".join(args)
    ep, tok = _central()
    if not ep:
        # Local-only (SR-1): busca en el corpus local persistido (sin central).
        con = _db_for_cli()
        if con is None:
            print("no se pudo abrir la bitácora local."); return
        con.row_factory = sqlite3.Row
        try:
            results = _search_local(con, query)
        finally:
            con.close()
        print(json.dumps([{"session_id": s, "snippet": sn} for s, sn in results],
                         ensure_ascii=False, indent=2, default=str))
        return
    import urllib.parse
    code, resp = _http(ep, tok, "/search?q=" + urllib.parse.quote(query))
    print(json.dumps(resp.get("results", []) if code == 200 else {"error": code, **resp},
                     ensure_ascii=False, indent=2, default=str))


def _transcript_pending_bytes(con, work_id, session_id, transcript_path):
    """Bytes del transcript aún no subidos al central (archivo − cursor). None si el archivo ya no existe."""
    path = posix_to_win(transcript_path or "")
    try:
        if not session_id or not path or not os.path.isfile(path):
            return None
        cur = con.execute("SELECT synced_byte FROM transcript_cursor WHERE session_id=? AND work_id=?",
                          (session_id, work_id)).fetchone()
        return max(0, os.path.getsize(path) - (cur[0] if cur else 0))
    except (OSError, sqlite3.Error):
        return None


def _sync_status_rows(con, central=True):
    """Works locales que requieren atención: pendientes de publicar, en conflicto o con un fallo de sync
    vigente. Función pura sobre la conexión (la comparten el CLI y los tests).
    Sin central configurado `dirty` nace en 1 y nada lo baja: listar por dirty devolvería toda la
    bitácora, así que ahí solo cuentan conflicto y fallos.
    La clave es `local_id`, nunca `id`: con central los demás verbos interpretan ids REMOTOS."""
    where = "conflict=1 OR last_error IS NOT NULL OR transcript_error IS NOT NULL"
    if central:
        where = "dirty=1 OR " + where
    rows = con.execute(
        "SELECT id, mode, project, req_slug, dirty, conflict, remote_id, synced_at, last_error, last_error_at, "
        "transcript_error, transcript_error_at, updated_at, archived_at, claude_session_id, transcript_path "
        f"FROM work WHERE {where} ORDER BY id").fetchall()
    out = []
    for r in rows:
        item = {"local_id": r[0], "mode": r[1], "project": r[2], "req_slug": r[3], "dirty": r[4],
                "conflict": r[5], "remote_id": r[6], "synced_at": r[7], "last_error": r[8],
                "last_error_at": r[9], "transcript_error": r[10], "transcript_error_at": r[11],
                "updated_at": r[12], "archived_at": r[13]}
        if r[10] is not None:
            item["transcript_pending_bytes"] = _transcript_pending_bytes(con, r[0], r[14], r[15])
        out.append(item)
    return out


def cli_sync_status(_args):
    """Estado del outbox. SIEMPRE lee el SQLite local (este estado no existe en el central) y nunca
    hace red. Sale por STDOUT: el wrapper del skill descarta stderr. ensure_ascii=True a propósito:
    en un pipe cp1252 de Windows un carácter fuera de la página produciría salida VACÍA con rc=0,
    que se leería como 'nada atascado' — justo el falso negativo que este verbo existe para evitar."""
    endpoint_set = bool(os.environ.get("NEB_LOGBOOK_ENDPOINT"))
    token_set = bool(os.environ.get("NEB_LOGBOOK_TOKEN"))
    con = _db_for_cli()
    if con is None:
        print(json.dumps({"error": "no se pudo abrir la bitacora local"}, ensure_ascii=True)); return
    try:
        works = _sync_status_rows(con, central=endpoint_set)
    except Exception as e:
        print(json.dumps({"error": "no se pudo leer el estado del sync: " + str(e)[:200]}, ensure_ascii=True)); return
    finally:
        con.close()
    notes = ["local_id es el id LOCAL: no usarlo con show/claim/release/archive cuando hay central "
             "(esos verbos interpretan ids remotos; usar remote_id)."]
    if endpoint_set and not token_set:
        notes.append("Hay endpoint pero falta NEB_LOGBOOK_TOKEN en este entorno: el sync no corre y no deja "
                     "rastro; los works dirty de abajo no se estan publicando.")
    if not endpoint_set:
        notes.append("Sin central configurado: solo se listan conflictos y fallos (dirty no aplica).")
    if any(w["remote_id"] is None for w in works):
        notes.append("remote_id null = este cliente nunca lo publico con exito. Con un 409 el work existe en el "
                     "central a nombre de otro (ubicarlo en `list` por project + req_slug); con un 5xx no existe "
                     "y solo queda corregir la causa que muestra last_error.")
    print(json.dumps({
        "scope": "local", "endpoint_set": endpoint_set, "token_set": token_set,
        "attention": sum(1 for w in works if w["conflict"] or w["last_error"] or w["transcript_error"]),
        "notes": notes, "works": works,
    }, ensure_ascii=True, indent=2, default=str))


def cli_main(argv):
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        cli_list(rest)
    elif cmd == "sync-status":
        cli_sync_status(rest)
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
