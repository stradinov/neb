#!/usr/bin/env python3
"""
_db_shared.py — infraestructura compartida de la DB del logbook/pendings (Neb).

Centraliza (DRY) lo que antes vivía en logbook.py y que ahora también consume pendings.py:
  • resolución de path dual-mode (neb.db ∨ neb-logbook.db) — vive AQUI y SOLO aqui.
  • conexión + aplicación de schema + migración idempotente.
  • begin_immediate (transacción de escritura exclusiva inmediata, para concurrencia).
  • helpers puros movidos desde logbook.py (now_iso, posix_to_win, _whoami, ...).

Filosofía defensiva preservada: las funciones que devolvían None ante error siguen
devolviéndolo; el prefijo de log se mantiene [logbook] (no [neb-db]) para no romper
grep/monitoreo existente.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone


NEB_DB_NAME    = "neb.db"            # nuevo nombre canónico
LEGACY_DB_NAME = "neb-logbook.db"    # nombre legado (máquinas del equipo sin migrar)


# --------------------------------------------------------------------------- helpers puros (movidos de logbook.py)

def posix_to_win(path):
    """Ruta POSIX de Git Bash (/c/Users/foo) a Windows. No-op si ya es Windows o en Linux/Mac."""
    if sys.platform == "win32" and path and re.match(r"^/[a-zA-Z]/", path):
        drive = path[1].upper()
        rest = path[2:].replace('/', '\\')
        return f"{drive}:\\{rest}"
    return path


def encode_cwd(cwd):
    """CWD → formato de directorio de proyecto Claude: ':' → '-', luego '/' y '\\' → '-'."""
    return cwd.replace(":", "-").replace("/", "-").replace("\\", "-")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


# --------------------------------------------------------------------------- memoria del proyecto (REQ activos)

def _field(text, label):
    """Valor de una línea tipo '- **Label:** value' o 'Label: value'. '' si no está.
    El prefijo opcional [\\s\\-*]* tolera viñetas markdown y negritas (formato del template)."""
    pat = re.compile(r"^[\s\-*]*" + re.escape(label) + r"\s*:\s*\**\s*(.+?)\s*$", re.MULTILINE)
    m = pat.search(text)
    return m.group(1).strip() if m else ""


def _parse_active_block(block):
    """Bloque de texto de un REQ activo → dict con los campos canónicos del REQ."""
    return {
        "name":             _field(block, "Nombre"),
        "project_path":     _field(block, "Path del proyecto"),
        "draft":            _field(block, "Draft changes MD"),
        "state":            _field(block, "Estado"),
        "plan":             _field(block, "Plan resumido"),
        "files":            _field(block, "Archivos modificados hasta ahora"),
        "next_steps":       _field(block, "Próximos pasos"),
        "pending_delivery": _field(block, "Pendiente de entrega"),
    }


def find_active_reqs(memory_dir):
    """TODOS los REQ activos del memory_dir → lista de dicts (cada uno + clave 'mtime').

    Estructura A + compatibilidad de transición:
      • active_*.md  — un REQ por archivo (formato nuevo). Soporta N REQ por proyecto.
      • project_*.md con bloque '## Requerimiento activo' (legacy) — para no congelar
        los REQ en vuelo mientras se migra.
    Dedup por (project_path, name): si el mismo REQ aparece en ambos formatos, gana el
    active_*.md; entre iguales, el de mtime mayor. Lista ordenada por mtime desc.
    Devuelve [] ante cualquier error (defensivo; igual contrato que la antigua single)."""
    try:
        names = os.listdir(memory_dir)
    except OSError:
        return []

    found = {}   # (project_path, name) -> (is_active_file, mtime, dict)
    for fname in names:
        if not fname.endswith(".md"):
            continue
        is_active = fname.startswith("active_")
        is_legacy = fname.startswith("project_")
        if not (is_active or is_legacy):
            continue
        fpath = os.path.join(memory_dir, fname)
        try:
            content = open(fpath, encoding="utf-8").read()
            mtime = os.path.getmtime(fpath)
        except (OSError, UnicodeDecodeError):
            continue                                  # un archivo no-UTF-8 se salta, no aborta el escaneo

        if is_active:
            block = content
        elif "## Requerimiento activo" in content:
            block = content.split("## Requerimiento activo", 1)[1]
        else:
            continue

        d = _parse_active_block(block)
        if not (d["name"] and d["project_path"]):
            continue                                  # mal-formado: ignorar (igual que legacy)
        d["mtime"] = mtime
        key = (d["project_path"], d["name"])
        prev = found.get(key)
        if prev is None or (is_active, mtime) > (prev[0], prev[1]):   # active_* gana; luego mtime
            found[key] = (is_active, mtime, d)

    reqs = [v[2] for v in found.values()]
    reqs.sort(key=lambda d: d["mtime"], reverse=True)
    return reqs


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _expand_user(p, home_dir):
    """Expande '~' / '~/...' usando home_dir EXPLÍCITO (os.path.expanduser ignora el
    home temporal de los tests). Rutas absolutas se devuelven tal cual."""
    if not p:
        return ""
    p = p.strip()
    if p == "~":
        return home_dir
    if p.startswith("~/") or p.startswith("~\\"):
        return os.path.join(home_dir, p[2:])
    return p


def resolve_memory_dir(home_dir, cwd, encoded):
    """Dir de auto-memoria EFECTIVO. Respeta el setting nativo 'autoMemoryDirectory' de
    Claude Code (precedencia basada en archivo: Local > Project > User); si ningún scope
    lo define, cae al default derivado del cwd:
        <home>/.claude/projects/<encoded>/memory
    Cuando 'autoMemoryDirectory' está fijado, ÉL es el dir de memoria (contiene MEMORY.md
    directamente; no se le anexa /projects/<encoded>).

    Fuera de alcance (limitación conocida): scopes 'managed' y '--settings' no son
    ubicables desde un hook. Defensivo: cualquier error → default."""
    default = os.path.join(home_dir, ".claude", "projects", encoded, "memory")
    try:
        candidates = []
        if cwd:
            candidates.append(os.path.join(cwd, ".claude", "settings.local.json"))  # Local
            candidates.append(os.path.join(cwd, ".claude", "settings.json"))        # Project
        candidates.append(os.path.join(home_dir, ".claude", "settings.json"))       # User
        for path in candidates:                       # primer scope que lo defina gana
            data = _read_json(path)
            if isinstance(data, dict) and data.get("autoMemoryDirectory"):
                base = _expand_user(str(data["autoMemoryDirectory"]), home_dir)
                if base:
                    return base
    except Exception:
        pass
    return default


# --------------------------------------------------------------------------- resolución de path (dual-mode)

def _is_usable_db(path):
    """True sii <path> existe, tamaño > 0, y abre con tabla 'work' consultable.
    Guarda anti-shadowing: sqlite3.connect CREA el archivo vacío, así que un neb.db
    de tamaño 0 o sin la tabla 'work' NO debe ocultar a neb-logbook.db poblado.
    NO usa uri=True / 'file:...?mode=ro' (el drive-letter 'C:' rompe la URI en Windows)."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            return False
    except OSError:
        return False
    con = None
    try:
        con = sqlite3.connect(path)                   # connect normal, sin uri
        con.execute("SELECT count(*) FROM work").fetchone()
        return True
    except (sqlite3.Error, OSError):
        return False                                  # tabla ausente / archivo no-DB / 0 filas-schema
    finally:
        if con is not None:
            con.close()


def resolve_db_path(home_dir):
    """Path a la DB del logbook/pendings bajo <home_dir>/.claude/.
    Dual-mode permanente: prefiere neb.db SI es usable; si no, cae a neb-logbook.db.
    Si ninguno existe → devuelve la ruta de neb.db (destino de creación nueva).
    Devuelve siempre un str (nunca None)."""
    base   = os.path.join(home_dir, ".claude")
    new_p  = os.path.join(base, NEB_DB_NAME)          # neb.db
    legacy = os.path.join(base, LEGACY_DB_NAME)       # neb-logbook.db
    if _is_usable_db(new_p):
        return new_p
    if _is_usable_db(legacy):
        return legacy
    # Ninguno usable: destino de creación nueva = neb.db (nombre canónico)
    return new_p


# --------------------------------------------------------------------------- conexión + migración

def _connect(db_path, schema_path, timeout=5.0):
    """Abre la DB, aplica schema (executescript) + _migrate. Net-new vs el actual:
    timeout en sqlite3.connect + PRAGMA busy_timeout. Devuelve con o None (defensivo)."""
    try:
        con = sqlite3.connect(db_path, timeout=timeout)
    except sqlite3.Error as e:
        print(f"[logbook] ERROR abriendo {db_path}: {e}", file=sys.stderr)
        return None
    try:
        con.execute("PRAGMA busy_timeout=5000")       # ms; net-new (concurrencia logbook↔pendings)
        if os.path.isfile(schema_path):
            with open(schema_path, encoding="utf-8") as fh:
                con.executescript(fh.read())
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


# --------------------------------------------------------------------------- transacciones

def begin_immediate(con):
    """Inicia una transacción de escritura exclusiva de inmediato (BEGIN IMMEDIATE).
    Contrato: fija con.isolation_level=None (autocommit) DENTRO de esta función Y LO DEJA ASÍ
    — el caller NO necesita setearlo, pero debe asumir que la conexión queda en modo autocommit
    (el driver ya NO inyectará un BEGIN implícito antes de cada DML). Tras retornar, el caller
    hace su SQL y luego con.execute('COMMIT') o con.execute('ROLLBACK')."""
    con.isolation_level = None        # autocommit: que el driver NO inyecte BEGIN implícito (queda así)
    con.execute("BEGIN IMMEDIATE")    # adquiere el lock de escritor ya (falla rápido si BUSY)


def _safe_rollback(con):
    """ROLLBACK defensivo: solo si hay transacción activa. Cuando BEGIN IMMEDIATE falla
    por 'database is locked' NO se abrió transacción, así que un ROLLBACK ciego dispararía
    'cannot rollback - no transaction is active' y enmascararía el SQLITE_BUSY (rompiendo
    el retry). con.in_transaction es la guarda; el try/except traga la carrera residual."""
    if not getattr(con, "in_transaction", False):
        return
    try:
        con.execute("ROLLBACK")
    except sqlite3.OperationalError:
        pass


def with_write_tx(con, fn, retries=3):
    """Ejecuta fn(con) dentro de BEGIN IMMEDIATE; reintenta ante 'database is locked'.
    fn NO debe commitear NI abrir su propia transacción: este helper hace COMMIT/ROLLBACK.
    Fuente única del patrón de escritura (pendings._with_write_tx delega aquí; los comandos
    CLI del logbook lo usan para simetría transaccional con pendings)."""
    for attempt in range(retries):
        try:
            begin_immediate(con)              # fija isolation_level=None + BEGIN IMMEDIATE
            r = fn(con)
            con.execute("COMMIT")
            return r
        except sqlite3.OperationalError as e:
            _safe_rollback(con)               # defensivo: si BEGIN IMMEDIATE falló no hay tx que revertir
            if "locked" in str(e).lower() and attempt < retries - 1:
                time.sleep(0.1 * (attempt + 1))
                continue
            raise
