#!/usr/bin/env python3
"""
_db_shared.py — infraestructura compartida de la DB del logbook/pendings (Neb).

Centraliza (DRY) lo que antes vivía en logbook.py y que ahora también consume pendings.py:
  • ruta de la base (~/.claude/neb.db) y guarda de la base sin migrar — viven AQUI y SOLO aqui.
  • conexión: el esquema inicial sale del árbol de este módulo; la versión de esquema y los pasos de
    base viven en _migrations.py (6.48.0); aquí, las dos reparaciones que corren en cada conexión.
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

import _migrations
from _migrations import (                              # reexportados: las pruebas los llaman desde aquí
    DbUnavailable, IncompatibleDb,
    _WORK_MIGRATIONS, _SESSION_SYNC_MIGRATIONS, _PENDING_MIGRATIONS, _PENDING_TOPIC_MIGRATIONS,
    _table_exists, _add_missing_columns,
)


NEB_DB_NAME    = "neb.db"

# Esquema inicial (versión de esquema 1) del árbol de ESTE módulo: nunca el de NEB_HOME.
INITIAL_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logbook-schema.sql")
LEGACY_DB_NAME = "neb-logbook.db"    # nombre anterior a 7.0.0: solo lo leen la guarda y el migrador


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
    """Identidad estable del proyecto entre máquinas: host/owner/repo del git remote.
    Prefiere `origin`; si no, el primer remote. Sin remote → basename(path)
    (NO estable entre máquinas: dos checkouts con el mismo nombre de carpeta colisionan)."""
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
    """Valor de una línea tipo '- **Label:** value' o 'Label: value'. '' si no está o está vacía.
    El prefijo opcional [ \\t\\-*]* tolera viñetas markdown y negritas (formato del template).
    El valor va en la MISMA línea: los separadores son `[ \\t]*` (no `\\s*`, que cruzaba el salto de
    línea y hacía que una línea '- **Estado:**' vacía capturara la línea SIGUIENTE como valor) y la
    captura es `(.*?)` (no `(.+?)`: ante una línea vacía sin espacio final, `\\**` retrocedía un
    asterisco y el valor salía '*'). Misma variante que `pendings._field_value` (6.7.1, PD-517)."""
    pat = re.compile(r"^[ \t\-*]*" + re.escape(label) + r"[ \t]*:[ \t]*\**[ \t]*(.*?)[ \t]*$",
                     re.MULTILINE)
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
            with open(fpath, encoding="utf-8") as fh:
                content = fh.read()
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


# --------------------------------------------------------------------------- ruta de la base y guarda

def _is_usable_db(path):
    """True sii <path> existe, tamaño > 0, y abre con tabla 'work' consultable.
    sqlite3.connect CREA el archivo vacío, así que un neb.db de tamaño 0 o sin la tabla 'work'
    no cuenta como base.
    Abre con un connect normal (no de solo lectura): quien solo lee (el arranque) no pasa por aquí y usa
    _migrations.open_readonly, con Path.as_uri() + '?mode=ro', que sí funciona con letra de unidad."""
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
    """Ruta de la base del logbook/pendings: siempre <home_dir>/.claude/neb.db (exista o no)."""
    return os.path.join(home_dir, ".claude", NEB_DB_NAME)


class UnmigratedDb(DbUnavailable):
    """La base sigue con el nombre anterior a 7.0.0 y no hay un neb.db usable. Su JSON conserva el motivo
    `base-sin-migrar` y trae, además de `accion` (la migración guiada), `comando` (el migrador a mano)."""

    def __init__(self, detalle, comando):
        super().__init__(
            "base-sin-migrar", detalle,
            "abre una sesión nueva de Claude y corre `/neb:migrate`: su paso 7.0.0:renombrar-base cambia el "
            "nombre de la base (pide cerrar antes las demás sesiones)")
        self.comando = comando

    def to_dict(self):
        return {**super().to_dict(), "comando": self.comando}


def _migrator_command(home_dir=None):
    """Comando del migrador desde el árbol de este módulo (sirve también a quien solo tiene el plugin), con
    el intérprete que está corriendo. Agrega --home cuando home_dir no es el de expanduser('~')."""
    script = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "..", "..", "bootstrap", "migrate-neb-db.py"))
    cmd = f'"{sys.executable}" "{script}"'
    if home_dir and (os.path.normcase(os.path.abspath(home_dir))
                     != os.path.normcase(os.path.abspath(os.path.expanduser("~")))):
        cmd += f' --home "{home_dir}"'
    return cmd


def _probe_db(path):
    """Estado de un archivo de base sin crearlo: 'ausente', 'vacia', 'usable', 'sin-work' (abre pero no
    tiene la tabla work), 'no-base' (no es una base SQLite), 'bloqueada' u 'otro'. Solo abre el archivo si
    existe y no está vacío."""
    try:
        if not os.path.isfile(path):
            return "ausente"
        size = os.path.getsize(path)
    except OSError:
        return "otro"
    if size == 0:
        return "vacia"
    con = None
    try:
        con = sqlite3.connect(path, timeout=0.5)      # bloqueada no es «sin migrar»: no vale la pena esperar
        con.execute("SELECT count(*) FROM work").fetchone()
        return "usable"
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        if "no such table" in msg:
            return "sin-work"
        if "locked" in msg or "busy" in msg:
            return "bloqueada"
        return "otro"
    except sqlite3.DatabaseError as e:
        return "no-base" if "not a database" in str(e).lower() else "otro"
    except (sqlite3.Error, OSError):
        return "otro"
    finally:
        if con is not None:
            con.close()


def unmigrated_legacy(home_dir):
    """UnmigratedDb (sin lanzarla) si <home>/.claude/neb-logbook.db existe y no está vacío y neb.db falta,
    pesa 0, no tiene la tabla work o no es una base; None en cualquier otro caso. Una base bloqueada no
    cuenta como sin migrar. No abre nada salvo un neb.db ya existente y no vacío."""
    base = os.path.join(home_dir, ".claude")
    legacy = os.path.join(base, LEGACY_DB_NAME)
    try:
        if not os.path.isfile(legacy) or os.path.getsize(legacy) == 0:
            return None
    except OSError:
        return None
    new_p = os.path.join(base, NEB_DB_NAME)
    state = _probe_db(new_p)
    if state not in ("ausente", "vacia", "sin-work", "no-base"):
        return None
    detalle = (f"La bitácora sigue con el nombre anterior a neb 7.0.0 ({legacy}) y no hay un {NEB_DB_NAME} "
               "usable: neb no captura ni abre la base hasta cambiarle el nombre.")
    if state in ("sin-work", "no-base"):
        try:
            size = os.path.getsize(new_p)
        except OSError:
            size = "?"
        detalle += (f" Antes, mueve fuera de {base} el {NEB_DB_NAME} que hay ahí ({size} bytes), que no es una "
                    "base usable: el cambio de nombre no lo pisa.")
    return UnmigratedDb(detalle, _migrator_command(home_dir))


def raise_if_unmigrated(home_dir):
    """Lanza UnmigratedDb si la base sigue sin migrar (ver unmigrated_legacy). Va antes de abrir la base:
    abrir neb.db lo crearía vacío y escondería la base vieja."""
    err = unmigrated_legacy(home_dir)
    if err is not None:
        raise err


# --------------------------------------------------------------------------- conexión + migración

def _connect(db_path, schema_path=None, timeout=5.0, steps=None, retry=False):
    """Abre la DB y la lleva a la versión de esquema de este código (_migrations.migrate); con V <= C corre
    las dos reparaciones. Devuelve con o None (defensivo), salvo dos casos que lanzan DbUnavailable:
    base incompatible (IncompatibleDb) y paso de base bloqueado sin `espera` (motivo paso-bloqueado). Un
    None ahí haría que los CLI respondan vacío: el fallo silencioso que la versión de esquema quita.

    schema_path: solo para pruebas; producción usa el esquema inicial del árbol de este módulo.
    steps: solo para pruebas (lista de pasos inyectable).
    retry: reintenta ya un paso con fallo reciente guardado (neb-migrate.py apply)."""
    if schema_path is None:
        schema_path = INITIAL_SCHEMA_PATH
    try:
        fresh = not os.path.isfile(db_path) or os.path.getsize(db_path) == 0
    except OSError:
        fresh = False
    try:
        con = sqlite3.connect(db_path, timeout=timeout)
    except sqlite3.Error as e:
        print(f"[logbook] ERROR abriendo {db_path}: {e}", file=sys.stderr)
        return None
    try:
        # Fuera de toda transacción y en cada conexión (antes llegaban por el executescript del esquema).
        con.execute("PRAGMA busy_timeout=5000")       # ms (concurrencia logbook↔pendings)
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        if _migrations.migrate(con, db_path, schema_path, steps=steps, fresh=fresh, retry=retry):
            _repair(con)
    except DbUnavailable:
        con.close()
        raise
    except _migrations._Busy as e:
        print(f"[logbook] ERROR aplicando paso de base: {e}", file=sys.stderr)
        con.close()
        return None
    except (OSError, sqlite3.Error) as e:
        print(f"[logbook] ERROR aplicando schema: {e}", file=sys.stderr)
        con.close()
        return None
    except BaseException:
        con.close()                                   # nunca una conexión abierta con un candado tomado
        raise
    return con


def open_default_db(home_dir):
    """Apertura de producción de la base por omisión (resolve_db_path), con el esquema inicial del árbol de
    este módulo. Lanza UnmigratedDb, antes de crear nada, si la base sigue sin migrar; puede lanzar
    DbUnavailable."""
    raise_if_unmigrated(home_dir)
    return _connect(resolve_db_path(home_dir))


def _repair(con):
    """Reparaciones que se reintentan hasta lograrse. Corren después de los pasos, solo con V <= C (nunca
    sobre una base más nueva que el código): el índice uq_pending_slug si falta, y la limpieza de las
    tablas de transcripts retiradas en 6.41.0 (sin respaldo, como desde 6.41.0)."""
    _ensure_pending_slug_index(con)
    con.commit()
    _drop_retired_transcript_tables(con)


# Tablas del corpus local y del cursor de subida de transcripts, retiradas. _migrate las borra si existen
# (ver _drop_retired_transcript_tables). El índice FTS5 va al final y en su propia transacción: si su
# módulo falta en este SQLite, su DROP falla sin retener las otras dos.
_RETIRED_TRANSCRIPT_TABLES = ("transcript_local", "transcript_cursor", "transcript_fts")


# Las tuplas de columnas (_WORK_MIGRATIONS, _PENDING_MIGRATIONS, …) viven en _migrations.py, congeladas con el
# esquema inicial: un cambio nuevo del esquema es un paso de base. El backfill de `pending.slug` (DML) no es
# migración: lo hace pendings.backfill_slugs.
# Índice que depende de una columna agregada después: no puede ir en el esquema inicial (en una DB existente el
# executescript corre ANTES del ALTER). Es reparación: se crea si falta en sqlite_master.
_PENDING_INDEX_DDL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_slug ON pending(slug) WHERE slug IS NOT NULL",
)


def _ensure_pending_slug_index(con):
    """Crea uq_pending_slug si falta. Tolera duplicados preexistentes (el índice no se crea y la conexión sigue
    usable; se reintenta cuando el dev los sanee). 'database is locked' se propaga."""
    if not _table_exists(con, "pending"):
        return
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='uq_pending_slug'").fetchone():
        return
    for ddl in _PENDING_INDEX_DDL:
        try:
            con.execute(ddl)
        except sqlite3.IntegrityError as e:
            print(f"[logbook] aviso: uq_pending_slug no creado ({e}); saneá los slugs duplicados",
                  file=sys.stderr)


def _migrate(con):
    """Columnas del esquema inicial + reparaciones, sin pasar por la versión de esquema. Se conserva para las
    pruebas que lo llaman directo; producción entra por _connect. Propaga 'database is locked'."""
    _migrations.add_initial_columns(con)
    _repair(con)


def _drop_retired_transcript_tables(con):
    """Borra transcript_fts, transcript_local y transcript_cursor si queda alguna (bases anteriores al retiro
    de la subida de transcripts y del corpus local). Sin ninguna de ellas no escribe ni pide candado.
    En transacciones explícitas separadas, para que un fallo no se lleve lo ya hecho:
      1. Si existe transcript_local, siembra session_sync.read_byte con el MAX(byte_to) de cada sesión cuando
         es mayor que el actual (y crea la fila mínima de las sesiones que no la tienen): una sesión viva no
         se relee desde el byte 0, y un REQ que el dev desvinculó no se vuelve a vincular. Es idempotente
         (solo sube el cursor), así que repetirla en un reintento no cambia nada.
      2. DROP de transcript_local y transcript_cursor.
      3. DROP de transcript_fts (arrastra sus tablas sombra). Si su módulo falta, solo ella se queda.
    Nunca propaga: ante 'database is locked', 'no such module' (FTS5 ausente en este SQLite) o cualquier
    otro error de SQLite revierte la transacción en curso, avisa por stderr y sigue; se reintenta en la
    siguiente conexión. Así la limpieza nunca hace que _connect devuelva None. Si la siembra misma falla
    (candado), transcript_local sigue en la base y el lector de la captura toma de ahí el cursor
    (logbook._read_new_chunk)."""
    try:
        present = [t for t in _RETIRED_TRANSCRIPT_TABLES if _table_exists(con, t)]
    except sqlite3.Error as e:
        print(f"[logbook] aviso: no se pudo revisar las tablas de transcripts retiradas: {e}", file=sys.stderr)
        return
    if not present:
        return
    saved = con.isolation_level
    try:
        con.isolation_level = None                    # transacción explícita: el driver no inyecta BEGIN
        if "transcript_local" in present and _table_exists(con, "session_sync"):
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "UPDATE session_sync SET read_byte = (SELECT MAX(t.byte_to) FROM transcript_local t "
                "WHERE t.session_id = session_sync.session_id) "
                "WHERE read_byte < (SELECT COALESCE(MAX(t.byte_to), 0) FROM transcript_local t "
                "WHERE t.session_id = session_sync.session_id)")
            con.execute(
                "INSERT OR IGNORE INTO session_sync (session_id, read_byte, updated_at) "
                "SELECT session_id, MAX(byte_to), ? FROM transcript_local "
                "WHERE session_id NOT IN (SELECT session_id FROM session_sync) GROUP BY session_id",
                (now_iso(),))
            con.execute("COMMIT")                     # la siembra queda aunque el DROP falle
        for group in (("transcript_local", "transcript_cursor"), ("transcript_fts",)):
            todo = [t for t in group if t in present]
            if not todo:
                continue
            con.execute("BEGIN IMMEDIATE")
            for table in todo:
                con.execute(f"DROP TABLE IF EXISTS {table}")
            con.execute("COMMIT")
    except sqlite3.Error as e:
        _safe_rollback(con)
        print(f"[logbook] aviso: no se pudieron borrar las tablas de transcripts retiradas ({e}); "
              "se reintenta en la siguiente conexión", file=sys.stderr)
    finally:
        con.isolation_level = saved


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
