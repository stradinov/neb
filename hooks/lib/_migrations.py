#!/usr/bin/env python3
"""
_migrations.py — versión de esquema y pasos de base de neb.db (Neb, desde 6.48.0).

La base guarda sus pasos aplicados en `schema_step`; el código trae `SCHEMA_VERSION`. Al conectar
(_db_shared._connect → migrate), con V = MAX(step), F = MAX(min_code) y C = SCHEMA_VERSION:

    V == C            opera
    V <  C            aplica los pasos V+1 … C y opera
    V >  C y C >= F   opera sin migrar (base más nueva pero compatible)
    V >  C y C <  F   no toca la base: IncompatibleDb

Un paso de base es un cambio del esquema escrito en código. Corre dentro de BEGIN IMMEDIATE junto con
su fila de `schema_step` (todo o nada); el paso 1 (esquema inicial) también, y además es idempotente.
Un paso destructivo lleva respaldo previo verificado en `<carpeta de la base>/neb-backups/` (queda el último de cada paso).

Este módulo NO importa módulos hermanos: el arranque lee `SCHEMA_VERSION` de otro árbol como texto
(regex sobre este archivo) sin cargarlo. Mantener la asignación en una sola línea literal.

Documento: tooling/migrations.md.
"""

import glob
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone


SCHEMA_VERSION = 3

BACKUP_DIR_NAME   = "neb-backups"
STEP_BACKUP_GLOB  = "neb.pre-paso-*.db"                 # todos los pasos: lo que listan status y restore
RESTORE_BACKUP_GLOB = "neb.pre-restore.*.db"


def step_backup_glob(n):
    """Respaldos de un solo paso: la poda es por paso. El punto tras el número evita que el 1 tome al 12."""
    return f"neb.pre-paso-{n}.*.db"

RETRY_BACKOFF_SECONDS = 600         # tras un fallo guardado, las conexiones esperan esto antes de reintentar
ADVANCED = object()                 # la base ya estaba en el paso: se vuelve a decidir la compatibilidad

_SCHEMA_VERSION_RE = re.compile(r"^SCHEMA_VERSION\s*=\s*(\d+)\s*$", re.MULTILINE)


# --------------------------------------------------------------------------- errores

class DbUnavailable(Exception):
    """La base no se puede operar con este código. Los cli_main la atrapan una sola vez y responden
    {"ok": false, "motivo", "detalle", "accion"} con salida 0."""

    def __init__(self, motivo, detalle, accion):
        super().__init__(f"{motivo}: {detalle}")
        self.motivo, self.detalle, self.accion = motivo, detalle, accion

    def to_dict(self):
        return {"ok": False, "motivo": self.motivo, "detalle": self.detalle, "accion": self.accion}


class IncompatibleDb(DbUnavailable):
    pass


class _Busy(Exception):
    """Candado ocupado al aplicar un paso sin `espera`: _connect devuelve None, como hoy."""


# --------------------------------------------------------------------------- columnas del esquema inicial
# Columnas agregadas después de la creación de cada tabla. CREATE TABLE IF NOT EXISTS no altera una tabla
# existente: el paso 1 las agrega si faltan. Congeladas con el esquema inicial (6.47.0): un cambio nuevo
# del esquema es un paso de base, no una fila aquí.

_WORK_MIGRATIONS = (
    ("conflict",            "ALTER TABLE work ADD COLUMN conflict INTEGER NOT NULL DEFAULT 0"),
    ("last_error",          "ALTER TABLE work ADD COLUMN last_error TEXT"),
    ("last_error_at",       "ALTER TABLE work ADD COLUMN last_error_at TEXT"),
    ("transcript_error",    "ALTER TABLE work ADD COLUMN transcript_error TEXT"),
    ("transcript_error_at", "ALTER TABLE work ADD COLUMN transcript_error_at TEXT"),
)
_SESSION_SYNC_MIGRATIONS = (
    ("root_cwd",  "ALTER TABLE session_sync ADD COLUMN root_cwd TEXT"),
    ("read_byte", "ALTER TABLE session_sync ADD COLUMN read_byte INTEGER NOT NULL DEFAULT 0"),
)
_PENDING_MIGRATIONS = (
    ("slug", "ALTER TABLE pending ADD COLUMN slug TEXT"),
)
_PENDING_TOPIC_MIGRATIONS = (
    ("curated", "ALTER TABLE pending_topic ADD COLUMN curated INTEGER NOT NULL DEFAULT 0"),
)


def _table_exists(con, name):
    """Existencia REAL de la tabla vía el catálogo (sobrevive a conexiones envueltas en tests)."""
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _add_missing_columns(con, table, migrations):
    """Aplica las migraciones de columnas que falten en <table>. Tolera 'duplicate column name'
    (carrera entre procesos); cualquier otro error se propaga."""
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, ddl in migrations:
        if name in cols:
            continue
        try:
            con.execute(ddl)
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise


def add_initial_columns(con):
    """Columnas del esquema inicial que falten. `work` siempre (si existe); las demás solo si su tabla
    existe (una base solo-logbook no debe romper). Solo DDL. Propaga 'database is locked'."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(work)").fetchall()}
    if not cols:
        return
    for name, ddl in _WORK_MIGRATIONS:
        if name in cols:
            continue
        try:
            con.execute(ddl)
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
    if _table_exists(con, "session_sync"):
        _add_missing_columns(con, "session_sync", _SESSION_SYNC_MIGRATIONS)
    if _table_exists(con, "pending"):
        _add_missing_columns(con, "pending", _PENDING_MIGRATIONS)
    if _table_exists(con, "pending_topic"):
        _add_missing_columns(con, "pending_topic", _PENDING_TOPIC_MIGRATIONS)


# --------------------------------------------------------------------------- pasos

class Step:
    """Un paso de base.

    n           número consecutivo
    titulo      nombre corto
    aplicar     fn(con): el cambio; corre dentro de BEGIN IMMEDIATE con una conexión sin control de la
                transacción (_StepConnection: commit, executescript, BEGIN/COMMIT... lanzan error)
    min_code    mínima compatible que deja. Sube cuando una escritura válida del código anterior fallaría
                (NOT NULL sin DEFAULT, UNIQUE, CHECK o trigger nuevos) o cuando un dato que ese código lee
                desaparece o cambia de significado
    destructivo borra o reescribe datos: respaldo previo verificado (salvo base recién creada)
    espera      el código nuevo funciona aunque el paso no se haya aplicado: si no se puede, la conexión
                sigue con la base en V y se reintenta en la siguiente
    precheck    fn(con) -> motivo | None, solo lectura: por qué el paso no puede correr todavía
    inicial     solo el paso 1: esquema inicial + columnas, en su propia transacción
    """

    def __init__(self, n, titulo, aplicar=None, min_code=None, destructivo=False, espera=False,
                 precheck=None, inicial=False):
        self.n, self.titulo, self.aplicar = n, titulo, aplicar
        self.min_code = n if min_code is None else min_code
        self.destructivo, self.espera, self.precheck, self.inicial = destructivo, espera, precheck, inicial


# --------------------------------------------------------------------------- paso 2: retiro del esquema de equipo
# 7.0.0 retira el backend central y el candado entre devs: 2 índices, la tabla event y 19 columnas de work y
# session_sync. Todo o nada (D12 del REQ neb-retiro-team-y-dual-mode): un objeto creado a mano que use algo de
# eso, o un SQLite sin DROP COLUMN, detienen el paso en su precheck sin borrar nada.

DROP_COLUMN_SQLITE = (3, 35, 5)       # 3.35.5 corrigió defectos de DROP COLUMN que podían dañar la base
SQLITE_VERSION = sqlite3.sqlite_version_info     # se lee en cada precheck: las pruebas lo cambian

_RETIRED_TEAM_INDEXES = ("idx_work_dirty", "idx_session_sync_work")
_RETIRED_TEAM_COLUMNS = (
    ("work", ("owner", "lock_state", "takeover_by", "locked_at", "payload_version", "origin_dev", "dirty",
              "synced_at", "remote_id", "conflict", "last_error", "last_error_at", "transcript_error",
              "transcript_error_at")),
    ("session_sync", ("work_id", "synced_byte", "transcript_error", "transcript_error_at", "root_cwd")),
)
_OBJECT_KINDS = {"view": ("la vista", "DROP VIEW"), "trigger": ("el trigger", "DROP TRIGGER"),
                 "index": ("el índice", "DROP INDEX")}


def _names_word(sql, word):
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])", sql, re.IGNORECASE) is not None


def _names_any(sql, words):
    return any(_names_word(sql, w) for w in words)


def _readers(objs, table):
    """La tabla y toda vista que la lea, directa o a través de otra vista (SELECT * propaga columnas)."""
    names, grew = {table}, True
    while grew:
        grew = False
        for kind, name, _tbl, sql in objs:
            if kind == "view" and name.lower() not in names and _names_any(sql, names):
                names.add(name.lower())
                grew = True
    return names


_VIEW_COLUMN_LIST = re.compile(r"\s*CREATE\s+(?:TEMP(?:ORARY)?\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                               r"(?:\"[^\"]+\"|\[[^\]]+\]|`[^`]+`|[^\s(]+)\s*\(", re.IGNORECASE)


def _depends_on_column_count(kind, sql, names):
    """Se rompe si la tabla pierde cualquier columna: vista con lista de columnas o con UNION/INTERSECT/EXCEPT
    sobre un *, o trigger con un * o con un INSERT sin lista de columnas hacia una de esas relaciones."""
    if kind == "view":
        return "*" in sql and (_VIEW_COLUMN_LIST.match(sql) is not None
                               or re.search(r"\b(?:UNION|INTERSECT|EXCEPT)\b", sql, re.IGNORECASE) is not None)
    if "*" in sql:
        return True
    return any(re.search(rf"\bINTO\s+(?:\w+\.)?[\"\[`]?{re.escape(n)}[\"\]`]?\s+(?:VALUES|SELECT|DEFAULT)\b",
                         sql, re.IGNORECASE) for n in names)


def _team_leftovers(con):
    """(índices, ¿existe event?, [(tabla, columna)]) del esquema de equipo que sigue en la base."""
    indexes = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name IN (?,?)", _RETIRED_TEAM_INDEXES).fetchall()]
    has_event = _table_exists(con, "event")
    cols = []
    for table, names in _RETIRED_TEAM_COLUMNS:
        present = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
        cols += [(table, c) for c in names if c in present]
    return indexes, has_event, cols


def _team_blockers(con, has_event, cols):
    """Objetos del usuario que usan lo que el paso retira: [(tipo, nombre, [lo que usa])]. Cuenta lo que usa una
    vista, un trigger o un índice (directo, a través de otra vista o con un *): el DROP COLUMN fallaría, o
    dejaría el trigger o la vista rotos. Una vista que ya no abre bloquea todo (SQLite revalida el esquema
    entero en cada DROP COLUMN). No detecta una columna generada ni un CHECK agregados a mano: ahí falla
    `aplicar`, que revierte."""
    if not (has_event or cols):
        return []
    objs = con.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL AND (type IN "
        "('view','trigger') OR (type='index' AND name NOT IN (?,?) AND lower(tbl_name)<>'event'))",
        _RETIRED_TEAM_INDEXES).fetchall()
    readers = {t: _readers(objs, t) for t in {t for t, _c in cols}}
    broken = set()
    for kind, name, _tbl, _sql in objs:
        if kind == "view":
            try:
                con.execute('SELECT 1 FROM "{}" LIMIT 0'.format(name.replace('"', '""'))).fetchall()
            except sqlite3.Error:
                broken.add(name)
    blockers = []
    for kind, name, tbl, sql in objs:
        if name in broken:
            blockers.append((kind, name, ["todo lo que el paso retira (la vista ya no abre)"]))
            continue
        hits = []
        for t, c in cols:
            via = readers[t]
            if kind == "index":
                hit = tbl.lower() == t and _names_word(sql, c)
            else:
                on_t = (kind == "trigger" and tbl.lower() in via) or _names_any(sql, via)
                hit = on_t and (_names_word(sql, c) or _depends_on_column_count(kind, sql, via))
            if hit:
                hits.append(f"{t}.{c}")
        if kind != "index" and has_event and _names_word(sql, "event"):
            hits.append("event")
        if hits:
            blockers.append((kind, name, hits))
    return blockers


def _blockers_text(blockers, siguiente="y la siguiente conexión aplica el paso"):
    uses = "; ".join(f"{_OBJECT_KINDS[k][0]} {n} usa {', '.join(h)}" for k, n, h in blockers)
    drops = "; ".join(f"{_OBJECT_KINDS[k][1]} {n}" for k, n, _h in blockers)
    return (f"objetos creados a mano usan lo que neb 7.0.0 retira: {uses}. No se borró nada; quítalos "
            f"({drops}) {siguiente}")


def _team_precheck(con):
    indexes, has_event, cols = _team_leftovers(con)
    if not (indexes or has_event or cols):
        return None
    if SQLITE_VERSION < DROP_COLUMN_SQLITE:
        return (f"neb 7.0.0 pide SQLite 3.35.5 o superior (DROP COLUMN) y este Python trae el "
                f"{'.'.join(map(str, SQLITE_VERSION))}: instala un Python que lo traiga desde "
                "https://www.python.org/downloads/ (en Windows, Python 3.12 o superior)")
    blockers = _team_blockers(con, has_event, cols)
    return _blockers_text(blockers) if blockers else None


class UserObjectsInTheWay(Exception):
    """No es de SQLite a propósito: el mecanismo trataría como candado ocupado un mensaje que nombra
    work.locked_at, y no guardaría el fallo."""


def _team_apply(con):
    """Relee dentro de la transacción y borra solo lo que existe: con todo o nada, un DROP COLUMN sobre una
    columna ausente revertiría siempre. Un objeto del usuario creado después del precheck revierte el paso."""
    indexes, has_event, cols = _team_leftovers(con)
    blockers = _team_blockers(con, has_event, cols)
    if blockers:
        raise UserObjectsInTheWay(_blockers_text(blockers, siguiente="y el paso se reintenta"))  # el mecanismo agrega cuándo
    for name in indexes:
        con.execute(f"DROP INDEX {name}")
    if has_event:
        con.execute("DROP TABLE event")
    for table, col in cols:
        con.execute(f"ALTER TABLE {table} DROP COLUMN {col}")


# --------------------------------------------------------------------------- paso 3: eje proyecto
# 7.3.0 renombra la raíz del eje curado 'cliente' a 'proyecto' (slug y name; también la descripción si es la
# que puso el seed: una escrita a mano se conserva). Los hijos cuelgan de la misma fila
# (mismo id), así que las curaciones de pending_topic no se tocan. Sin raíz 'cliente' (base nueva, o con triage
# pero sin taxonomía sembrada: solo el sentinel y temas planos) el paso no hace nada; la raíz 'proyecto' la crea
# el seed. El código <= 7.2.x busca la raíz 'cliente': por eso sube la mínima compatible.

_OLD_AXIS_ROOT = "cliente"
_NEW_AXIS_ROOT = ("proyecto", "Proyecto")
# Descripción que bootstrap/seed-pendings-taxonomy.py da a cada raíz ("Raíz del eje <slug> (…)").
_OLD_ROOT_DESCRIPTION = "Raíz del eje cliente (contenedor; no es un tema)"
_NEW_ROOT_DESCRIPTION = "Raíz del eje proyecto (contenedor; no es un tema)"


def _old_axis_root(con):
    """id de la raíz 'cliente' (parent_id IS NULL), o None."""
    if not _table_exists(con, "topic"):
        return None
    row = con.execute("SELECT id FROM topic WHERE slug = ? AND parent_id IS NULL ORDER BY id LIMIT 1",
                      (_OLD_AXIS_ROOT,)).fetchone()
    return row[0] if row else None


def _project_slug_clash(con, root_id, siguiente="y la siguiente conexión aplica el paso"):
    """Motivo si ya existe un tema con slug 'proyecto' (topic.slug es UNIQUE: el renombre fallaría), o None.
    Solo lectura. Propone un slug libre para el UPDATE que lo quita del camino."""
    row = con.execute("SELECT t.id, p.slug FROM topic t LEFT JOIN topic p ON p.id = t.parent_id "
                      "WHERE t.slug = ?", (_NEW_AXIS_ROOT[0],)).fetchone()
    if row is None:
        return None
    clash_id, parent_slug = row
    free, i = f"{_NEW_AXIS_ROOT[0]}-{clash_id}", 2
    while con.execute("SELECT 1 FROM topic WHERE slug = ?", (free,)).fetchone() is not None:
        free, i = f"{_NEW_AXIS_ROOT[0]}-{clash_id}-{i}", i + 1
    where = f"hijo de '{parent_slug}'" if parent_slug else "sin padre"
    return (f"neb 7.3.0 renombra la raíz del eje 'cliente' (topic id {root_id}) a 'proyecto', y ya existe un tema "
            f"con slug 'proyecto' (topic id {clash_id}, {where}). No se cambió nada; renómbralo (p. ej. "
            f"UPDATE topic SET slug='{free}' WHERE id={clash_id};); si 'proyecto' aparece en «- **Temas:**» de "
            f"~/.claude/compas.md, cámbialo ahí por el nuevo slug (compas.md resuelve por slug: si no, el peso de "
            f"ese objetivo deja de aplicarse), {siguiente}")


def _project_axis_precheck(con):
    root_id = _old_axis_root(con)
    if root_id is None:
        return None
    return _project_slug_clash(con, root_id)


class ProjectSlugInTheWay(Exception):
    """No es de SQLite a propósito (como UserObjectsInTheWay): el fallo se guarda con su motivo legible."""


def _project_axis_apply(con):
    """Relee dentro de la transacción: sin raíz 'cliente' no hace nada (otra versión o el seed ya dejó el eje
    como está); un tema 'proyecto' aparecido después del precheck revierte el paso, que se reintenta."""
    root_id = _old_axis_root(con)
    if root_id is None:
        return
    clash = _project_slug_clash(con, root_id, siguiente="y el paso se reintenta")  # el mecanismo agrega cuándo
    if clash:
        raise ProjectSlugInTheWay(clash)
    # La descripción solo se cambia si es la que puso el seed; una escrita a mano se conserva.
    con.execute("UPDATE topic SET slug = ?, name = ?, description = CASE WHEN description = ? THEN ? "
                "ELSE description END WHERE id = ?",
                (*_NEW_AXIS_ROOT, _OLD_ROOT_DESCRIPTION, _NEW_ROOT_DESCRIPTION, root_id))


STEPS = (
    Step(1, "esquema inicial", min_code=1, inicial=True),
    Step(2, "retiro del esquema de equipo (7.0.0)", aplicar=_team_apply, min_code=2, destructivo=True,
         espera=True, precheck=_team_precheck),
    Step(3, "eje proyecto (7.3.0)", aplicar=_project_axis_apply, min_code=3, destructivo=True,
         espera=False, precheck=_project_axis_precheck),
)


def code_version(steps=None):
    steps = STEPS if steps is None else steps
    return max(s.n for s in steps)


def read_schema_version_text(path):
    """SCHEMA_VERSION de un _migrations.py de OTRO árbol, leído como texto (sin cargarlo).
    Un árbol sin el archivo (anterior a 6.48.0) cuenta como 1; un archivo ilegible, None."""
    try:
        with open(path, encoding="utf-8") as fh:
            m = _SCHEMA_VERSION_RE.search(fh.read())
    except FileNotFoundError:
        return 1
    except (OSError, UnicodeDecodeError):
        return None
    return int(m.group(1)) if m else None


def neb_version():
    """Versión de neb de este árbol (archivo VERSION), constancia en schema_step."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "VERSION")
    try:
        with open(p, encoding="utf-8") as fh:
            return fh.read().strip() or "desconocida"
    except OSError:
        return "desconocida"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


# --------------------------------------------------------------------------- tablas del mecanismo
# No son pasos: las crea el mecanismo con IF NOT EXISTS. Su forma solo cambia agregando columnas con DEFAULT,
# y quien las lee tolera que falten.

_BOOKKEEPING_DDL = (
    """CREATE TABLE IF NOT EXISTS schema_step (
  step        INTEGER PRIMARY KEY,
  min_code    INTEGER NOT NULL,
  title       TEXT NOT NULL,
  neb_version TEXT NOT NULL,
  applied_at  TEXT NOT NULL,
  backup      TEXT
)""",
    """CREATE TABLE IF NOT EXISTS schema_step_error (
  step        INTEGER PRIMARY KEY,
  at          TEXT NOT NULL,
  neb_version TEXT NOT NULL,
  motivo      TEXT NOT NULL
)""",
)


def read_version(con):
    """(V, F) de la base: (0, 0) sin tabla de versión."""
    if not _table_exists(con, "schema_step"):
        return 0, 0
    v, f = con.execute("SELECT COALESCE(MAX(step), 0), COALESCE(MAX(min_code), 0) FROM schema_step").fetchone()
    return int(v), int(f)


def read_errors(con):
    """Fallos vigentes de pasos no aplicados: [(step, at, neb_version, motivo)], ignorando step <= V."""
    if not _table_exists(con, "schema_step_error"):
        return []
    v, _f = read_version(con)
    return [tuple(r) for r in con.execute(
        "SELECT step, at, neb_version, motivo FROM schema_step_error WHERE step > ? ORDER BY step", (v,))]


# --------------------------------------------------------------------------- respaldo

def backup_dir(db_path):
    return os.path.join(os.path.dirname(os.path.abspath(db_path)), BACKUP_DIR_NAME)


def _private_dir(path):
    os.makedirs(path, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def take_backup(db_path, name):
    """Copia verificada de la base con la API de backup, desde una conexión aparte (funciona aunque otra
    conexión tenga BEGIN IMMEDIATE). Devuelve la ruta. Lanza OSError/sqlite3.Error si falla (sin dejar
    archivo a medias)."""
    folder = backup_dir(db_path)
    _private_dir(folder)
    dest = os.path.join(folder, name)
    src = dst = None
    try:
        src = sqlite3.connect(db_path, timeout=5.0)
        dst = sqlite3.connect(dest)
        src.backup(dst)
        # La copia hereda WAL del encabezado de la base; en DELETE queda en un solo archivo y leerla en
        # mode=ro (restore, status) no le deja -wal/-shm que la poda no ve.
        jm = dst.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        if str(jm).lower() != "delete":
            raise sqlite3.DatabaseError(f"el respaldo quedó en journal_mode={jm}")
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise sqlite3.DatabaseError(f"integrity_check del respaldo: {ok}")
    except BaseException:
        for c in (dst, src):
            if c is not None:
                c.close()
        dst = src = None
        for f in (dest, dest + "-wal", dest + "-shm"):
            _remove_quiet(f)
        raise
    finally:
        for c in (dst, src):
            if c is not None:
                c.close()
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    return dest


def prune_backups(db_path, pattern, keep_path):
    """Borra los archivos de <pattern> en neb-backups/ salvo keep_path (queda 1 de ese patrón)."""
    keep = os.path.normcase(os.path.abspath(keep_path)) if keep_path else None
    for p in glob.glob(os.path.join(glob.escape(backup_dir(db_path)), pattern)):
        if keep and os.path.normcase(os.path.abspath(p)) == keep:
            continue
        for f in (p, p + "-wal", p + "-shm"):
            _remove_quiet(f)


def _remove_quiet(path):
    try:
        os.remove(path)
    except OSError:
        pass


# --------------------------------------------------------------------------- aplicación

class _Failure:
    def __init__(self, kind, motivo):
        self.kind, self.motivo = kind, motivo      # kind: busy | precheck | backup | aplicar


_LOCKED_MESSAGES = ("database is locked", "database table is locked", "database schema is locked")


def _is_locked(e):
    """Candado ocupado por el código de SQLite (Python 3.11+) o por el mensaje exacto de SQLITE_BUSY/SQLITE_LOCKED;
    nunca por una palabra suelta: un DROP COLUMN que falla nombra work.locked_at."""
    code = getattr(e, "sqlite_errorcode", None)
    if code is not None:
        return code & 0xFF in (5, 6)                    # SQLITE_BUSY, SQLITE_LOCKED
    return str(e).lower().startswith(_LOCKED_MESSAGES)


def _rollback(con):
    if getattr(con, "in_transaction", False):
        try:
            con.execute("ROLLBACK")
        except sqlite3.Error:
            pass


def _record_error(con, n, motivo):
    """Constancia del fallo de un paso, en una transacción corta con espera corta. Sin insistir: si el
    candado está ocupado o otro proceso ya aplicó el paso, no escribe."""
    saved = con.isolation_level
    try:
        con.execute("PRAGMA busy_timeout=200")
        con.isolation_level = None
        con.execute("BEGIN IMMEDIATE")
        v, _f = read_version(con)
        if v < n:
            for ddl in _BOOKKEEPING_DDL:
                con.execute(ddl)
            con.execute("INSERT OR REPLACE INTO schema_step_error (step, at, neb_version, motivo) "
                        "VALUES (?, ?, ?, ?)", (n, _now(), neb_version(), str(motivo)[:500]))
        con.execute("COMMIT")
    except sqlite3.Error:
        _rollback(con)
    finally:
        con.isolation_level = saved
        try:
            con.execute("PRAGMA busy_timeout=5000")
        except sqlite3.Error:
            pass


def _register(con, step, backup):
    """Fila de schema_step + borrado del fallo vigente. Dentro de la transacción del paso."""
    for ddl in _BOOKKEEPING_DDL:
        con.execute(ddl)
    con.execute("INSERT OR IGNORE INTO schema_step (step, min_code, title, neb_version, applied_at, backup) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (step.n, step.min_code, step.titulo, neb_version(), _now(), backup))
    con.execute("DELETE FROM schema_step_error WHERE step = ?", (step.n,))


_PRAGMA_RE = re.compile(r"^(?:\s|--[^\n]*(?:\n|$))*PRAGMA\b", re.IGNORECASE)


def _schema_statements(schema_path):
    """Sentencias del esquema inicial, una por una y sin sus PRAGMA (los pone _connect fuera de toda
    transacción): así corren dentro del BEGIN IMMEDIATE del paso 1."""
    if not (schema_path and os.path.isfile(schema_path)):
        return []
    with open(schema_path, encoding="utf-8") as fh:
        text = fh.read()
    out, buf = [], ""
    for line in text.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if not _PRAGMA_RE.match(buf):
                out.append(buf.strip())
            buf = ""
    return out


def _apply_initial(con, step, schema_path):
    """Paso 1: esquema inicial + columnas + su fila, en una sola transacción BEGIN IMMEDIATE con relectura de V
    dentro (idempotente: repetirlo no cambia nada). Dentro del candado porque el paso 2 retira columnas y una
    tabla: un paso 1 tardío que corriera después de otro proceso las volvería a agregar."""
    if read_version(con)[0] >= step.n:
        return ADVANCED
    statements = _schema_statements(schema_path)
    saved = con.isolation_level
    try:
        con.isolation_level = None
        try:
            con.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            if _is_locked(e):
                return _Failure("busy", str(e))
            raise
        v, _f = read_version(con)
        if v >= step.n:
            con.execute("COMMIT")
            return ADVANCED
        for sql in statements:
            con.execute(sql)
        if not _table_exists(con, "work"):
            raise sqlite3.OperationalError(f"el esquema inicial no creó la tabla work: {schema_path}")
        add_initial_columns(con)
        _register(con, step, None)
        con.execute("COMMIT")
        return None
    except BaseException:
        _rollback(con)
        raise
    finally:
        con.isolation_level = saved


def _saved_error(con, n):
    """(at, motivo) del fallo guardado del paso n, o None."""
    for step, at, _ver, motivo in read_errors(con):
        if step == n:
            return at, motivo or ""
    return None


def _in_backoff(at):
    """True si el fallo guardado en <at> (ISO UTC) es más reciente que RETRY_BACKOFF_SECONDS."""
    try:
        when = datetime.fromisoformat(at)
    except (TypeError, ValueError):
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - when).total_seconds()
    return 0 <= age < RETRY_BACKOFF_SECONDS             # un reloj que retrocedió no alarga la espera


# Espacios y comentarios antes de la sentencia. `\s` simple, no `\s+`: con cuantificadores anidados una
# sangría larga que no es de control de transacción haría backtracking exponencial en cada execute.
_SQL_LEAD = r"^(?:\s|--[^\n]*(?:\n|$)|/\*.*?\*/)*"
_TX_CONTROL_RE = re.compile(_SQL_LEAD + r"(BEGIN|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE)\b",
                            re.IGNORECASE | re.DOTALL)
_FK_PRAGMA_RE = re.compile(_SQL_LEAD + r"PRAGMA\s+(?:\w+\s*\.\s*)?foreign_keys\s*[=(]", re.IGNORECASE | re.DOTALL)


class _StepConnection:
    """La conexión que recibe `aplicar`: la del paso, sin control de la transacción. commit, rollback,
    executescript (confirma antes de correr) y BEGIN/COMMIT/END/ROLLBACK/SAVEPOINT/RELEASE lanzan error; y
    si SQLite ya revirtió la transacción por su cuenta (disco lleno, una cláusula OR ROLLBACK), la
    siguiente sentencia también, para que nada se confirme suelto. Así un paso nunca deja la base a medias:
    termina confirmado entero o revertido entero."""

    def __init__(self, con):
        self._con = con

    def _check(self, sql):
        m = _TX_CONTROL_RE.match(sql or "")
        if m:
            raise sqlite3.ProgrammingError(f"un paso no controla la transacción: {m.group(1).upper()}")
        if _FK_PRAGMA_RE.match(sql or ""):
            # Dentro de la transacción SQLite lo ignora sin avisar: un paso que reconstruye una tabla
            # creyendo que apagó las FK dispararía los ON DELETE CASCADE / SET NULL.
            raise sqlite3.ProgrammingError("un paso no cambia foreign_keys: dentro de la transacción no surte "
                                           "efecto (lo hace el mecanismo, antes del BEGIN)")
        if not self._con.in_transaction:
            raise sqlite3.OperationalError("SQLite revirtió la transacción del paso")

    def execute(self, sql, *args):
        self._check(sql)
        return self._con.execute(sql, *args)

    def executemany(self, sql, *args):
        self._check(sql)
        return self._con.executemany(sql, *args)

    def executescript(self, *_args):
        raise sqlite3.ProgrammingError("un paso no usa executescript (confirma antes de correr)")

    def commit(self):
        raise sqlite3.ProgrammingError("un paso no confirma: lo confirma el mecanismo junto con su registro")

    def rollback(self):
        raise sqlite3.ProgrammingError("un paso no revierte: lanza una excepción y el mecanismo revierte")

    def cursor(self, *_args):
        raise sqlite3.ProgrammingError("un paso usa execute, no cursor()")

    def __getattr__(self, name):
        return getattr(self._con, name)


def _apply_step(con, db_path, step, fresh, retry=False):
    """Paso n >= 2, todo o nada. Devuelve None si este proceso lo aplicó, ADVANCED si la base ya está en
    n o más (otro proceso avanzó: quien llama vuelve a decidir la compatibilidad), o _Failure.

    `aplicar` recibe un _StepConnection: no puede confirmar nada por su cuenta. Tras un fallo guardado de
    aplicar o de respaldo, las conexiones no lo reintentan durante RETRY_BACKOFF_SECONDS (cada intento de
    un paso destructivo copia la base con el candado tomado); `retry=True` (neb-migrate.py apply)
    reintenta ya."""
    saved_err = _saved_error(con, step.n)
    if saved_err is not None:
        at, motivo = saved_err
        if not retry and _in_backoff(at):
            return _Failure("aplicar", f"{motivo} (reintento después de {RETRY_BACKOFF_SECONDS // 60} min o "
                                       "con `neb-migrate.py apply`)")
    if step.precheck is not None:
        try:
            motivo = step.precheck(con)
            failure = _Failure("precheck", motivo) if motivo else None
        except Exception as e:                          # noqa: BLE001 — un precheck mal escrito no tumba la conexión
            failure = _Failure("aplicar", f"precheck: {e}")
        if failure is not None:
            # El precheck corre sin candado: si otro proceso aplicó el paso en medio, no es un bloqueo.
            if read_version(con)[0] >= step.n:
                return ADVANCED
            return failure
    saved = con.isolation_level
    backup = None
    try:
        con.isolation_level = None
        try:
            con.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            if _is_locked(e):
                return _Failure("busy", str(e))
            raise
        v, _f = read_version(con)
        if v >= step.n:                                 # otro proceso lo aplicó en medio
            con.execute("COMMIT")
            return ADVANCED
        if step.destructivo and not fresh:
            try:
                backup = take_backup(db_path, f"neb.pre-paso-{step.n}.{_stamp()}.db")
            except (OSError, sqlite3.Error) as e:
                _rollback(con)
                _record_error(con, step.n, f"respaldo fallido: {e}")
                return _Failure("backup", f"respaldo fallido: {e}")
        try:
            step.aplicar(_StepConnection(con))
            if not con.in_transaction:                  # SQLite la revirtió y aplicar se tragó el error
                raise sqlite3.OperationalError("SQLite revirtió la transacción del paso")
            _register(con, step, backup)
            con.execute("COMMIT")
        except Exception as e:                          # noqa: BLE001 — también un TypeError de un paso mal escrito
            _rollback(con)                              # nada quedó confirmado: _StepConnection no lo permite
            if backup:
                _remove_quiet(backup)
                backup = None
            if isinstance(e, sqlite3.Error) and _is_locked(e):
                return _Failure("busy", str(e))
            _record_error(con, step.n, f"error al aplicar: {e}")
            return _Failure("aplicar", f"error al aplicar: {e}")
        except BaseException:                           # KeyboardInterrupt / SystemExit: deshacer y propagar
            _rollback(con)
            if backup:
                _remove_quiet(backup)
            raise
    finally:
        con.isolation_level = saved
    if backup:
        # Poda por paso: queda el último respaldo de cada paso destructivo (el neb.pre-paso-2 de 7.0.0, única
        # copia con las columnas de equipo, sobrevive al paso 3).
        prune_backups(db_path, step_backup_glob(step.n), backup)
    return None


def _check_newer(v, f, c):
    """Regla para V > C: False (opera sin migrar) o IncompatibleDb."""
    if c >= f:
        return False
    raise IncompatibleDb(
        "base-incompatible",
        f"la base está en la versión de esquema {v} y pide al menos la {f}; "
        f"este código de neb ({neb_version()}) trae la {c}",
        "actualiza neb (plugin y clon) a una versión con la versión de esquema "
        f"{f} o mayor; `neb-migrate.py status` muestra el detalle")


def migrate(con, db_path, schema_path, steps=None, fresh=None, retry=False):
    """Lleva la base a la versión del código si toca. Devuelve True si las reparaciones deben correr
    (V <= C), False si la base es más nueva y compatible. Lanza IncompatibleDb, DbUnavailable
    (paso-bloqueado) o _Busy; los errores de SQLite se propagan (_connect devuelve None).

    fresh: la base se creó en esta conexión (sin respaldo antes de un paso destructivo). _connect lo
    decide por el archivo antes de abrirlo; None = sin tabla `work`.
    Si otro proceso avanzó la base mientras tanto (ADVANCED), vuelve a leer V y F y a aplicar la regla:
    la compatibilidad no se decide con una lectura vieja."""
    steps = STEPS if steps is None else steps
    c = code_version(steps)
    if fresh is None:
        fresh = not _table_exists(con, "work")
    v, f = read_version(con)
    while True:
        if v > c:
            return _check_newer(v, f, c)
        pending = [s for s in steps if s.n > v]
        advanced = False
        for i, step in enumerate(pending):
            if step.inicial:
                failure = _apply_initial(con, step, schema_path)
            else:
                failure = _apply_step(con, db_path, step, fresh, retry=retry)
            if failure is None:
                continue
            if failure is ADVANCED:
                advanced = True
                break
            if all(s.espera for s in pending[i:]):
                print(f"[logbook] aviso: paso de base {step.n} ({step.titulo}) sin aplicar: {failure.motivo}; "
                      "se reintenta en la siguiente conexión", file=sys.stderr)
                return True
            if failure.kind == "busy":
                raise _Busy(failure.motivo)
            raise DbUnavailable(
                "paso-bloqueado",
                f"el paso de base {step.n} ({step.titulo}) no se puede aplicar: {failure.motivo}",
                "`neb-migrate.py status` muestra qué lo detiene; corrígelo y vuelve a abrir la sesión")
        if not advanced:
            return True
        v, f = read_version(con)


# --------------------------------------------------------------------------- lectura sin escribir

def open_readonly(db_path):
    """Conexión de solo lectura (no crea el archivo). None si no existe, está vacío o no abre."""
    try:
        if not os.path.isfile(db_path) or os.path.getsize(db_path) == 0:
            return None
        from pathlib import Path
        return sqlite3.connect(Path(os.path.abspath(db_path)).as_uri() + "?mode=ro", uri=True, timeout=1.0)
    except (OSError, sqlite3.Error):
        return None


def blocked_report(con, steps=None):
    """Pasos de base de este código detenidos, en solo lectura: [(n, titulo, motivo)]. Junta el fallo
    guardado en schema_step_error y el precheck recalculado. Que la base esté atrás sin motivo no cuenta
    (lo normal en la primera sesión tras actualizar)."""
    steps = STEPS if steps is None else steps
    v, _f = read_version(con)
    saved = {r[0]: r[3] for r in read_errors(con)}
    out = []
    for s in steps:
        if s.n <= v:
            continue
        motivo = None
        if s.precheck is not None:
            try:
                motivo = s.precheck(con)
            except Exception as e:  # noqa: BLE001 — mismo criterio que _apply_step: también bloquea
                motivo = f"precheck: {e}"
        motivo = motivo or saved.get(s.n)
        if motivo:
            out.append((s.n, s.titulo, motivo))
    return out


def list_backups(db_path):
    folder = backup_dir(db_path)
    out = []
    for pattern in (STEP_BACKUP_GLOB, RESTORE_BACKUP_GLOB):
        for p in sorted(glob.glob(os.path.join(glob.escape(folder), pattern))):
            try:
                out.append((p, os.path.getsize(p)))
            except OSError:
                pass
    return out
