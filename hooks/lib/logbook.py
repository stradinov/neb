#!/usr/bin/env python3
"""
logbook.py — bitácora de relevo de neb: base local de trabajos a medias (~/.claude/neb.db), para retomarlos.

Dos modos (dispatch en __main__):
  • captura — lo dispara el hook `logbook-sync` en Stop/SessionEnd/PreCompact: registra estado +
      transcript_path del work activo en la base local. De la conversación solo se guarda el resumen del
      exploratorio: el primer mensaje del dev recortado a 120 caracteres (_first_user_prompt). Fuera de eso
      la captura solo lee el tramo nuevo del .jsonl para el REQ vinculado (ver _read_new_chunk), sin
      guardarlo. Entra SOLO con exactamente 6 posicionales, un primer argumento que no es verbo y un
      cuarto argumento que es uno de CAPTURE_EVENTS.
  • CLI (list/show/rename/archive/link/trace/unlink) — lo invoca el comando/skill `/logbook`. `link`,
      `trace` y `unlink` (REQ vinculado, E2) viven en req_link.py. Los verbos retirados responden un JSON
      fijo (_RETIRED_VERBS); cualquier otro primer argumento, «subcomando desconocido».

Si la base sigue con el nombre anterior a 7.0.0, la captura no crea nada y el CLI responde
{ok: false, motivo: "base-sin-migrar", ...} con la migración guiada que la renombra (ver
_db_shared.raise_if_unmigrated).
Filosofía: defensivo — exit 0 siempre; errores a stderr, nunca bloquean al dev.

Args posicionales del modo captura (los arma el wrapper desde el stdin JSON del hook):
  1 session_id  2 cwd  3 transcript_path  4 event_name  5 guide_dir (NEB_HOME)  6 home_dir
"""

import json
import os
import sqlite3
import sys

from _db_shared import (
    resolve_db_path, _connect, INITIAL_SCHEMA_PATH, DbUnavailable, raise_if_unmigrated,
    with_write_tx, _safe_rollback,
    now_iso, posix_to_win, encode_cwd, find_active_reqs, resolve_memory_dir,
    _hostname, _git_info, _project_id,
)


# =========================================================================== captura

def main():
    if len(sys.argv) < 7:
        return

    session_id     = sys.argv[1]
    cwd            = posix_to_win(sys.argv[2])
    transcript_arg = posix_to_win(sys.argv[3])
    event_name     = sys.argv[4]
    guide_dir      = posix_to_win(sys.argv[5])        # lo siguen enviando los wrappers; ya no decide el esquema
    home_dir       = posix_to_win(sys.argv[6]) or os.path.expanduser("~")

    if not session_id or not cwd or not transcript_arg:
        return

    encoded      = encode_cwd(cwd)
    jsonl_path   = transcript_arg
    memory_dir   = resolve_memory_dir(home_dir, cwd, encoded)   # respeta autoMemoryDirectory; fallback al default

    machine = _hostname()
    branch, head = _git_info(cwd)

    active_reqs = find_active_reqs(memory_dir) if os.path.isdir(memory_dir) else []

    try:
        con = _open_db(home_dir)                       # esquema del árbol de este módulo, nunca el de NEB_HOME
    except DbUnavailable as e:
        # El stderr del hook se descarta: lo hacen visible el aviso de migración del inicio de sesión (al-iniciar) y `neb-migrate.py status`.
        print(f"[logbook] captura omitida ({e.motivo}): {e.detalle}", file=sys.stderr)
        return
    if con is None:
        return
    try:
        if active_reqs:
            for active in active_reqs:                # N REQ activos (incluye varios del mismo proyecto), mtime desc
                project  = _project_id(active.get("project_path") or cwd)
                req_slug = active.get("name") or "sin-nombre"
                payload  = json.dumps({
                    "plan": active.get("plan", ""),
                    "next_steps": active.get("next_steps", ""),
                    "files": active.get("files", ""),
                    "pending_delivery": active.get("pending_delivery", ""),
                }, ensure_ascii=False)
                _upsert_req(con, project, req_slug, machine, active.get("state", ""),
                            branch, head, active.get("project_path", ""), active.get("draft", ""),
                            payload, session_id, jsonl_path)
        else:
            summary = _first_user_prompt(jsonl_path)
            _upsert_exploratory(con, session_id, machine, summary, branch, head, cwd, jsonl_path)
        _register_session(con, session_id, jsonl_path)
        chunk = _read_new_chunk(con, session_id, jsonl_path)    # tramo nuevo del .jsonl, insumo de E2
        con.commit()
        _after_capture(con, session_id, chunk, event_name)      # E2: nunca afecta lo ya confirmado
    finally:
        con.close()


def _after_capture(con, session_id, chunk, event_name):
    """E2 (REQ vinculado). Corre DESPUÉS del commit de la captura; cualquier error se avisa y se descarta.
    En SessionEnd sale antes de tocar la base. Si req_link falta (o vale None en sys.modules), el import
    falla dentro del try y la captura no se entera."""
    if not chunk or event_name == "SessionEnd":
        return
    try:
        import req_link
        req_link.after_capture(con, session_id, chunk)
    except Exception as e:
        _safe_rollback(con)
        print(f"[logbook] aviso: vínculo de REQ omitido: {e}", file=sys.stderr)


# --------------------------------------------------------------------------- DB
# _connect / _migrate viven en _db_shared.py; aquí solo viven los upserts específicos del logbook.

def _upsert_req(con, project, req_slug, machine, state, branch, head,
                repo_path, change_md, payload, session_id, transcript_path):
    """Upsert del work del REQ. Devuelve su id local. repo_path se refresca con el «Path del proyecto»
    vigente (un REQ que pasa a otro checkout lo sigue); vacío conserva el anterior."""
    ts = now_iso()
    row = con.execute(
        "SELECT id FROM work WHERE mode='req' AND project=? AND req_slug=?",
        (project, req_slug)).fetchone()
    if row:
        con.execute(
            "UPDATE work SET req_state=?, branch=?, head_commit=?, change_md=?, "
            "payload_json=?, claude_session_id=?, "
            "transcript_path=?, repo_path=COALESCE(NULLIF(?, ''), repo_path), updated_at=? WHERE id=?",
            (state, branch, head, change_md, payload, session_id, transcript_path, repo_path,
             ts, row[0]))
        return row[0]
    cur = con.execute(
        "INSERT INTO work (mode, project, req_slug, req_state, branch, "
        "head_commit, repo_path, change_md, payload_json, origin_machine, "
        "claude_session_id, transcript_path, created_at, updated_at) "
        "VALUES ('req',?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (project, req_slug, state, branch, head, repo_path, change_md, payload,
         machine, session_id, transcript_path, ts, ts))
    return cur.lastrowid


def _upsert_exploratory(con, session_id, machine, summary, branch, head, cwd, transcript_path):
    """Upsert del work exploratorio de la sesión. Devuelve su id local."""
    ts = now_iso()
    payload = json.dumps({"summary": summary}, ensure_ascii=False)
    row = con.execute(
        "SELECT id FROM work WHERE mode='exploratory' AND claude_session_id=?",
        (session_id,)).fetchone()
    if row:
        con.execute(
            "UPDATE work SET payload_json=?, branch=?, head_commit=?, transcript_path=?, "
            "updated_at=? WHERE id=?",
            (payload, branch, head, transcript_path, ts, row[0]))
        return row[0]
    cur = con.execute(
        "INSERT INTO work (mode, branch, head_commit, repo_path, "
        "payload_json, origin_machine, claude_session_id, transcript_path, "
        "created_at, updated_at) VALUES ('exploratory',?,?,?,?,?,?,?,?,?)",
        (branch, head, cwd, payload, machine, session_id, transcript_path, ts, ts))
    return cur.lastrowid


# --------------------------------------------------------------------------- registro de sesión
# Una fila por sesión en session_sync: ruta del .jsonl y cursor de lectura del .jsonl (read_byte, ver
# _read_new_chunk). No guarda texto de la conversación.

def _register_session(con, session_id, transcript_path):
    """Alta o actualización de la fila de la sesión, en la misma transacción de la captura. Refresca la ruta
    del .jsonl. Best-effort."""
    try:
        ts = now_iso()
        cur = con.execute("UPDATE session_sync SET transcript_path=?, updated_at=? WHERE session_id=?",
                          (transcript_path, ts, session_id))
        if cur.rowcount == 0:
            con.execute("INSERT OR IGNORE INTO session_sync (session_id, transcript_path, updated_at) "
                        "VALUES (?,?,?)", (session_id, transcript_path, ts))
    except sqlite3.Error as e:
        print(f"[logbook] aviso: no se pudo registrar la sesión {session_id}: {e}", file=sys.stderr)


def _read_new_chunk(con, session_id, jsonl_path):
    """Lee el tramo NUEVO del .jsonl desde el cursor de la sesión (session_sync.read_byte), avanza el cursor
    y devuelve el texto decodificado del tramo (insumo de E2, req_link.after_capture). No persiste texto.
    None en las salidas tempranas (sin .jsonl, nada nuevo) y ante error. Best-effort: nunca rompe la captura.
    La fila la crea _register_session antes; si faltara, se crea aquí. Si transcript_local sigue en la base
    (la limpieza de la migración falló en esta conexión), el cursor es el mayor entre read_byte y su
    MAX(byte_to): la sesión no se relee desde el byte 0."""
    try:
        if not jsonl_path or not os.path.isfile(jsonl_path):
            return None
        row = con.execute("SELECT read_byte FROM session_sync WHERE session_id=?", (session_id,)).fetchone()
        start = (row[0] or 0) if row else 0
        try:    # la limpieza de la migración no terminó en esta conexión: vale el cursor heredado
            legacy = con.execute("SELECT MAX(byte_to) FROM transcript_local WHERE session_id=?",
                                 (session_id,)).fetchone()
            if legacy and legacy[0] and legacy[0] > start:
                start = legacy[0]
        except sqlite3.OperationalError:
            pass                                      # sin transcript_local: el caso normal tras migrar
        size = os.path.getsize(jsonl_path)
        if size <= start:
            return None
        with open(jsonl_path, "rb") as f:
            f.seek(start)
            chunk = f.read(size - start)              # exactamente el tramo medido
        if not chunk:
            return None
        end = start + len(chunk)
        if row is None:
            con.execute("INSERT OR IGNORE INTO session_sync (session_id, transcript_path, read_byte, updated_at) "
                        "VALUES (?,?,?,?)", (session_id, jsonl_path, end, now_iso()))
        else:
            con.execute("UPDATE session_sync SET read_byte=MAX(read_byte, ?) WHERE session_id=?", (end, session_id))
        return chunk.decode("utf-8", errors="replace")
    except (OSError, sqlite3.Error):
        return None                                   # best-effort: la captura nunca falla por la lectura


# ----------------------------------------------------------------------- memoria
# find_active_reqs (plural, soporta N REQ activos) y el parser _field viven ahora en
# _db_shared.py — fuente única (antes había 2 copias); usage-tracker.py ya no la usa desde 6.29.0.


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


# =========================================================================== CLI (/logbook)
# Siempre contra la base local (~/.claude/neb.db). Salida por stdout: el wrapper del skill descarta stderr.

CLI_CMDS = {"list", "show", "rename", "archive", "link", "trace", "unlink"}

# Eventos en que hooks/hooks.json registra el hook logbook-sync: solo con uno de ellos se entra a captura.
CAPTURE_EVENTS = {"Stop", "SessionEnd", "PreCompact"}

# Verbos retirados: responden un JSON fijo y nunca caen al modo captura. Residuo de transición (sale en 8.0.0).
_RETIRED_VERBS = {
    "sync": {"detalle": "se retiró en neb 7.0.0 junto con el backend central: la bitácora es solo local y no hay "
                        "nada que sincronizar."},
    # attention: 0 evita que un SKILL.md anterior en caché muestre un diagnóstico falso.
    "sync-status": {"detalle": "se retiró en neb 7.0.0 junto con el backend central: la bitácora es solo local y "
                               "no hay estado de sincronización que revisar.",
                    "attention": 0},
    "claim": {"detalle": "se retiró en neb 7.0.0 junto con el candado entre devs; para continuar un REQ usa "
                         "`retomar <ruta-del-Change-MD>` (## Relevo, plan aprobado y rama)."},
    "release": {"detalle": "se retiró en neb 7.0.0 junto con el candado entre devs; para dejar un REQ a otro, deja "
                           "su ## Relevo en el Change MD y entrega el registro por git."},
    "forced-release": {"detalle": "se retiró en neb 7.0.0 junto con el candado entre devs; para continuar un REQ "
                                  "usa `retomar <ruta-del-Change-MD>`."},
    "request": {"detalle": "se retiró en neb 7.0.0 junto con el candado entre devs; para continuar un REQ usa "
                           "`retomar <ruta-del-Change-MD>`."},
    "search": {"detalle": "se retiró en neb 6.41.0: la bitácora no guarda texto de sesiones. Para retomar un REQ "
                          "usa su Change MD, su ## Relevo, el plan aprobado y la rama."},
}


def _retired_verb(verb):
    out = {"ok": False, "motivo": "verbo-retirado", "verbo": verb, **_RETIRED_VERBS[verb]}
    print(json.dumps(out, ensure_ascii=False))


def _open_db(home_dir):
    """Base por omisión con el esquema inicial del árbol de este módulo, con o sin NEB_HOME (6.48.0).
    Pasa por el `_connect` de este módulo para que las pruebas que lo parchean sigan vigilando la captura.
    Lanza UnmigratedDb, antes de crear nada, si la base sigue sin migrar; puede lanzar DbUnavailable."""
    raise_if_unmigrated(home_dir)
    return _connect(resolve_db_path(home_dir), INITIAL_SCHEMA_PATH)


def _db_for_cli():
    # Puede lanzar DbUnavailable: lo atrapa cli_main una sola vez.
    return _open_db(os.path.expanduser("~"))


def cli_list(_args):
    con = _db_for_cli()
    if con is None:
        print("[]"); return
    rows = con.execute(
        "SELECT id, mode, COALESCE(project,''), COALESCE(req_slug,''), COALESCE(req_state,''), updated_at "
        "FROM work WHERE archived_at IS NULL ORDER BY updated_at DESC").fetchall()
    con.close()
    print(json.dumps([
        {"id": r[0], "mode": r[1], "project": r[2], "req_slug": r[3], "req_state": r[4], "updated_at": r[5]}
        for r in rows
    ], ensure_ascii=False, indent=2))


# Columnas que muestra `show`, en lista explícita: en una base donde el borrado del esquema retirado no
# corrió, SELECT * mostraría columnas que ya no significan nada.
_SHOW_COLS = ("id", "mode", "project", "req_slug", "req_state", "branch", "head_commit", "repo_path",
              "change_md", "payload_json", "origin_machine", "claude_session_id", "claude_session_name",
              "transcript_path", "created_at", "updated_at", "archived_at")


def cli_show(args):
    if not args:
        print("uso: show <id>"); return
    con = _db_for_cli()
    if con is None:
        return
    r = con.execute(f"SELECT {', '.join(_SHOW_COLS)} FROM work WHERE id=?", (args[0],)).fetchone()
    con.close()
    if not r:
        print(f"work {args[0]} no encontrado"); return
    print(json.dumps(dict(zip(_SHOW_COLS, r)), ensure_ascii=False, indent=2, default=str))


def cli_rename(args):
    if len(args) < 2:
        print("uso: rename <id> <new_req_slug>"); return
    con = _db_for_cli()
    if con is None:
        return

    # Simetría transaccional con pendings: BEGIN IMMEDIATE + COMMIT/ROLLBACK con retry ante BUSY.
    def _do(c):
        c.execute("UPDATE work SET req_slug=?, updated_at=? WHERE id=? AND mode='req'",
                  (args[1], now_iso(), args[0]))

    with_write_tx(con, _do); con.close()
    print(f"rename OK (work {args[0]} → {args[1]}).")


def cli_archive(args):
    """Archiva el work (cierre del REQ) y cierra los pendientes abiertos ligados a él."""
    if not args:
        print("uso: archivar <id>"); return
    wid = args[0]
    con = _db_for_cli()
    if con is None:
        return

    # BEGIN IMMEDIATE antes del primer write (y del SAVEPOINT del gancho): on_work_archived usa un
    # SAVEPOINT que EXIGE estar dentro de una transacción.
    def _do(c):
        c.execute("UPDATE work SET archived_at=? WHERE id=? AND archived_at IS NULL", (now_iso(), wid))
        # Gancho best-effort: si pendings no importa o falla, el archive del work NO se rompe.
        # on_work_archived hace ROLLBACK TO SAVEPOINT propio ante error y re-lanza; se traga aquí
        # para que el COMMIT del work siga su curso.
        try:
            import pendings
            pendings.on_work_archived(c, wid)
        except Exception as e:
            print(f"[logbook] aviso: on_work_archived omitido: {e}", file=sys.stderr)

    with_write_tx(con, _do); con.close()
    print(f"archive OK (work {wid}).")


def cli_main(argv):
    # Windows: con stdout entubado en cp1252, un carácter fuera de la página (→, ↔) lanza
    # UnicodeEncodeError, el except del __main__ lo absorbe y la salida queda vacía con exit 0.
    # Mismo bloque que pendings.cli_main.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd in _RETIRED_VERBS:
            _retired_verb(cmd)
        elif cmd == "list":
            cli_list(rest)
        elif cmd == "show":
            cli_show(rest)
        elif cmd == "rename":
            cli_rename(rest)
        elif cmd == "archive":
            cli_archive(rest)
        elif cmd in ("link", "trace", "unlink"):
            # REQ vinculado (E2). Import perezoso.
            # JSON en stdout siempre: una excepción (base bloqueada, error de sqlite, import fallido) sale
            # como {ok: false}; una salida vacía se leería como «árbol anterior a estos verbos».
            try:
                import req_link
                getattr(req_link, "cli_" + cmd)(rest, _db_for_cli)
            except DbUnavailable as e:
                print(json.dumps(e.to_dict(), ensure_ascii=False))
            except Exception as e:
                print(json.dumps({"ok": False, "motivo": f"error: {e}"}, ensure_ascii=False))
        else:
            print(f"subcomando desconocido: {cmd}")
    except DbUnavailable as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False))


if __name__ == "__main__":
    try:
        args = sys.argv[1:]
        if args and (args[0] in CLI_CMDS or args[0] in _RETIRED_VERBS):
            cli_main(args)
        elif len(args) == 6 and args[3] in CAPTURE_EVENTS:
            main()
        elif args:
            cli_main(args)
    except Exception as e:
        print(f"[logbook] ERROR inesperado: {e}", file=sys.stderr)
    sys.exit(0)
