#!/usr/bin/env python3
"""
_guided.py — migraciones guiadas: registro, detección y ejecución de pasos guiados (Neb, desde 6.49.0).

Una versión que pide algo más que pasos de base trae `migrations/<versión>.md` (el prompt que sigue Claude)
y `migrations/<versión>.py`, que define `STEPS`: una lista de GuidedStep. Dos clases de paso:

- de catálogo: `op` (nombre de una operación de _machine.OPS) y `args`; detectar y aplicar los hace el catálogo;
- libre: `detectar(ctx)` y `aplicar(ctx)` propios; si deja con qué deshacerlo, `respaldo=True` y `aplicar`
  devuelve {"respaldo": <ruta>}, que el programa comprueba.

Pendiente es lo que la detección dice en el momento (solo lee; no se persiste). Lo único que se guarda es el
«no» del dev a un paso, en `migration_skip`. Corre solo lo que deja con qué deshacerlo (M5); lo demás, con
`apply --include`. Lo usan bootstrap/neb-migrate.py y el aviso del arranque.

Documento: tooling/migrations.md § "Migración guiada".
"""

import glob
import importlib.util
import os
import re
import sqlite3
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

import _machine

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
STEP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
LIVE_DB_NAMES = ("neb.db", "neb-logbook.db")

SKIP_DDL = ("CREATE TABLE IF NOT EXISTS migration_skip ("
            " id TEXT PRIMARY KEY, neb_version TEXT NOT NULL, at TEXT NOT NULL, detail TEXT)")


class GuidedStep:
    """Un paso guiado. De catálogo: op + args. Libre: detectar + aplicar (+ respaldo, deshacer).
    exclusivo: pide las demás sesiones cerradas; `condicion(ctx) -> motivo | None` (por omisión, que ninguna
    otra conexión tenga la base abierta en ese momento). El programa la comprueba antes de actuar, y el paso la
    vuelve a comprobar con ctx.exclusivo_ok() justo antes de la acción que no se deshace (las operaciones del
    catálogo ya lo hacen)."""

    def __init__(self, id, titulo, op=None, args=None, detectar=None, aplicar=None, respaldo=False,
                 deshacer=None, exclusivo=False, condicion=None):
        self.id, self.titulo = id, titulo
        self.op, self.args = op, dict(args or {})
        self.detectar, self.aplicar = detectar, aplicar
        self.respaldo, self.deshacer = respaldo, deshacer
        self.exclusivo, self.condicion = exclusivo, condicion

    @property
    def catalog(self):
        return self.op is not None


class Migration:
    def __init__(self, version, steps, prompt):
        self.version = version
        self.key = tuple(int(x) for x in version.split("."))
        self.steps = steps
        self.prompt = prompt


def migrations_dir(root):
    return os.path.join(root, "migrations")


class InvalidMigration(ValueError):
    """Error de forma de una migración (texto de neb, sin valores): su mensaje se reporta."""


def _validate(version, steps):
    if not isinstance(steps, (list, tuple)):
        raise InvalidMigration("STEPS debe ser una lista de GuidedStep")
    seen = set()
    for s in steps:
        if not isinstance(s, GuidedStep):
            raise InvalidMigration("STEPS trae algo que no es GuidedStep")
        if not STEP_ID_RE.match(str(s.id)) or s.id in seen:
            raise InvalidMigration(f"id de paso inválido o repetido: {str(s.id)[:40]!r}")
        seen.add(s.id)
        if s.catalog:
            if s.op not in _machine.OPS:
                raise InvalidMigration(f"{s.id}: operación desconocida {str(s.op)[:40]!r}")
            try:
                _machine.OPS[s.op].validate(**s.args)
            except (TypeError, ValueError) as e:
                # validate de catálogo: mensajes fijos de neb; TypeError: nombres de argumentos, no valores
                raise InvalidMigration(f"{s.id}: argumentos de {s.op}: {e}") from None
        elif not (callable(s.detectar) and callable(s.aplicar)):
            raise InvalidMigration(f"{s.id}: un paso libre trae detectar y aplicar")


def _self_module():
    """Este módulo como objeto. Cargado por ruta (spec sin registrar en sys.modules) no está ahí: se arma un
    módulo con los mismos objetos, así GuidedStep es la misma clase."""
    mod = sys.modules.get(__name__)
    if mod is not None and getattr(mod, "GuidedStep", None) is GuidedStep:
        return mod
    mod = types.ModuleType("_guided")
    mod.__dict__.update({k: v for k, v in globals().items() if not k.startswith("__")})
    return mod


def load(root):
    """(migraciones ordenadas por versión semántica, errores [(archivo, motivo)]). Un archivo cuyo nombre no es
    una versión semántica se ignora; uno que falla al cargar va a errores y no detiene a los demás."""
    out, errors = [], []
    # `from _guided import GuidedStep` en la migración debe dar este mismo módulo (quien lo cargó por ruta,
    # como el arranque, lo tiene con otro nombre): si no, sus pasos no serían GuidedStep de aquí.
    prev = sys.modules.get("_guided")
    sys.modules["_guided"] = _self_module()
    try:
        for path in glob.glob(os.path.join(glob.escape(migrations_dir(root)), "*.py")):
            version = os.path.splitext(os.path.basename(path))[0]
            if not SEMVER_RE.match(version):
                continue
            try:
                spec = importlib.util.spec_from_file_location("neb_migration_" + version.replace(".", "_"), path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                steps = list(getattr(mod, "STEPS", []))
                _validate(version, steps)
            except (Exception, SystemExit) as e:  # noqa: BLE001 — una migración rota no tumba el arranque
                errors.append((os.path.basename(path), load_error_text(e)))
                continue
            prompt = os.path.join(migrations_dir(root), version + ".md")
            out.append(Migration(version, steps, prompt if os.path.isfile(prompt) else None))
    finally:
        if prev is None:
            sys.modules.pop("_guided", None)
        else:
            sys.modules["_guided"] = prev
    out.sort(key=lambda m: m.key)
    return out, errors


def load_error_text(e):
    """Motivo de una migración que no carga: el tipo y, si es de sintaxis, la línea. Sin el mensaje, como el
    de un paso libre (error_text): viaja al JSON y al contexto de Claude. Un InvalidMigration (forma de la
    migración, texto de neb) conserva el suyo."""
    if isinstance(e, InvalidMigration):
        return f"migración inválida: {e}"
    line = getattr(e, "lineno", None) if isinstance(e, SyntaxError) else None
    return type(e).__name__ + (f" en la línea {line}" if line else "") + " (mensaje omitido)"


def step_key(migration, step):
    return f"{migration.version}:{step.id}"


def find(migrations, key):
    for m in migrations:
        for s in m.steps:
            if step_key(m, s) == key:
                return m, s
    return None, None


# --------------------------------------------------------------------------- migration_skip

def read_skips(con):
    """Ids omitidos por el dev. Sin la tabla (nadie omitió nada), vacío. Otro error de SQLite se propaga: quien
    llama no debe correr como pendiente un paso que el dev omitió."""
    if con is None:
        return set()
    try:
        return {r[0] for r in con.execute("SELECT id FROM migration_skip")}
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return set()
        raise


def add_skip(con, key, neb_version, detail=None):
    con.execute(SKIP_DDL)
    con.execute("INSERT OR REPLACE INTO migration_skip (id, neb_version, at, detail) VALUES (?, ?, ?, ?)",
                (key, neb_version, datetime.now(timezone.utc).isoformat(timespec="seconds"), detail))
    con.commit()


def remove_skip(con, key):
    """True si la fila ya no está."""
    try:
        con.execute("DELETE FROM migration_skip WHERE id = ?", (key,))
        con.commit()
        return True
    except sqlite3.Error:
        return False


# --------------------------------------------------------------------------- detección

def mode(ctx, step):
    """'solo' (deja con qué deshacerlo: corre sin preguntar) o 'dev' (pide al dev)."""
    if step.catalog:
        return _machine.OPS[step.op].mode(ctx, **step.args)
    return "solo" if step.respaldo else "dev"


def detect(ctx, step):
    if step.catalog:
        return bool(_machine.OPS[step.op].detect(ctx, **step.args))
    return bool(step.detectar(ctx))


def error_text(step, e):
    """Motivo de un error. El de un paso libre lleva solo el tipo: su mensaje puede traer un valor (los
    argumentos de un comando, el contenido de un archivo) y viaja al JSON y al contexto de Claude."""
    if step.catalog:
        return f"{type(e).__name__}: {e}"
    return f"{type(e).__name__} en el código del paso (mensaje omitido: puede traer valores)"


def survey(ctx, migrations, skips):
    """Lo pendiente en este momento: [{id, version, titulo, clase, exclusivo, omitido, error}]. Un paso omitido
    se lista sin detectarlo; un error de detección se reporta en su fila."""
    rows = []
    for m in migrations:
        for s in m.steps:
            key = step_key(m, s)
            row = {"id": key, "version": m.version, "titulo": s.titulo, "exclusivo": bool(s.exclusivo),
                   "clase": None, "omitido": key in skips, "error": None}
            if row["omitido"]:
                rows.append(row)
                continue
            try:
                if not detect(ctx, s):
                    continue
                row["clase"] = mode(ctx, s)
            except (Exception, SystemExit) as e:  # noqa: BLE001 — se reporta en la fila
                row["error"] = error_text(s, e)
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- exclusivo

def base_sin_otras_conexiones(ctx):
    """None si ninguna otra conexión tiene la base abierta en este momento. En WAL, prueba pasar a DELETE
    (pide acceso exclusivo: una conexión ajena, aunque esté ociosa, lo impide) y la regresa a WAL; fuera de
    WAL, prueba un BEGIN EXCLUSIVE. No prueba que las demás sesiones estén cerradas: sus hooks abren y cierran
    la base, y una puede abrirla justo después. Un paso cuya acción no tolera eso retiene su propio candado."""
    if not os.path.isfile(ctx.db_path):
        return None
    try:
        con = sqlite3.connect(ctx.db_path, timeout=0, isolation_level=None)
    except sqlite3.Error as e:
        return f"no se pudo abrir la base: {e}"
    switched = False
    try:
        mode_now = str(con.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        if mode_now != "wal":
            con.execute("BEGIN EXCLUSIVE")
            con.execute("ROLLBACK")
            return None
        got = str(con.execute("PRAGMA journal_mode=DELETE").fetchone()[0]).lower()
        if got != "delete":
            return "otra sesión tiene la base abierta"
        switched = True
        back = str(con.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
        if back != "wal":
            return "la base no volvió a WAL tras la prueba: otra sesión la abrió en ese momento"
        switched = False
        return None
    except sqlite3.OperationalError as e:
        if "locked" in str(e) or "busy" in str(e):
            return "otra sesión tiene la base abierta"
        return f"la prueba de exclusividad falló ({type(e).__name__})"
    except sqlite3.Error as e:
        return f"la prueba de exclusividad falló ({type(e).__name__})"
    finally:
        if switched:          # quedó en DELETE: un lector mode=ro posterior no la regresaría a WAL
            try:
                con.execute("PRAGMA journal_mode=WAL")
            except sqlite3.Error:
                pass
        con.close()


# --------------------------------------------------------------------------- ejecución

def _norm(path):
    return os.path.normcase(os.path.realpath(path))


def _snapshot(ctx):
    """Archivos que ya existen en las carpetas donde un respaldo declarado puede quedar."""
    seen = set()
    for d in (ctx.claude_dir, ctx.backups_dir):
        try:
            with os.scandir(d) as it:          # glob("*") no ve los que empiezan con punto (.credentials.json)
                for entry in it:
                    seen.add(_norm(entry.path))
        except OSError:
            pass
    return seen


def _live_files(ctx):
    live = set()
    for base in {ctx.claude_dir, os.path.dirname(os.path.abspath(ctx.db_path))}:
        for name in LIVE_DB_NAMES:
            for suffix in ("", "-wal", "-shm", "-journal"):
                live.add(_norm(os.path.join(base, name + suffix)))
    live.add(_norm(ctx.db_path))
    for name in _machine.SETTINGS_FILES:
        live.add(_norm(os.path.join(ctx.config_dir, name)))
        live.add(_norm(os.path.join(ctx.claude_dir, name)))
    return live


def _check_declared_backup(ctx, path, started, before):
    """Motivo si el respaldo que declaró un paso libre no sirve; None si sirve. Debe ser un archivo nuevo de
    esta corrida, directamente en ~/.claude o en neb-backups/, que no sea un archivo vivo (la base, sus
    -wal/-shm, un settings) ni un enlace; si es una base SQLite, en un solo archivo (no WAL) e íntegra."""
    if not path or not isinstance(path, str):
        return "el paso declaró respaldo y no devolvió su ruta"
    real = _norm(path)
    if _machine.is_link(path):
        return f"el respaldo {path} es un enlace"
    if os.path.dirname(real) not in (_norm(ctx.claude_dir), _norm(ctx.backups_dir)):
        return f"el respaldo {path} no está directamente en ~/.claude ni en neb-backups/"
    if real in _live_files(ctx):
        return f"el respaldo {path} es un archivo vivo, no un respaldo"
    if real in before:
        return f"el respaldo {path} ya existía antes del paso"
    if not os.path.isfile(real) or os.path.getsize(real) == 0:
        return f"el respaldo {path} no existe o está vacío"
    if os.path.getmtime(real) < started - 1:
        return f"el respaldo {path} no se creó en esta corrida"
    with open(real, "rb") as fh:
        head = fh.read(20)
    if head[:16] == b"SQLite format 3\x00":
        if len(head) < 20 or head[18] == 2 or head[19] == 2 or os.path.exists(real + "-wal"):
            return f"el respaldo {path} está en modo WAL: debe quedar en un solo archivo (journal_mode=DELETE)"
        if os.path.exists(real + "-journal"):      # con immutable=1 SQLite no aplica un journal caliente
            return f"el respaldo {path} tiene un -journal al lado: la copia quedó a medias"
        try:
            con = sqlite3.connect(Path(real).as_uri() + "?mode=ro&immutable=1", uri=True)
            try:
                ok = con.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                con.close()
        except sqlite3.Error as e:
            return f"el respaldo {path} no abre: {e}"
        if ok != "ok":
            return f"el respaldo {path} no pasa integrity_check"
    try:
        os.chmod(real, 0o600)          # puede estar directamente en ~/.claude, que no es 0700
    except OSError:
        pass
    return None


def run(ctx, step, allow_dev=False):
    """Corre un paso guiado. {estado: aplicado | sin-cambio | manual | pendiente | fallo, respaldo, detalle}.
    Sin allow_dev, un paso que pide al dev no corre. Un paso exclusivo comprueba su condición antes de actuar."""
    try:
        if not detect(ctx, step):
            return {"estado": "sin-cambio", "respaldo": None, "detalle": "nada que hacer"}
        clase = mode(ctx, step)
    except (Exception, SystemExit) as e:  # noqa: BLE001
        return {"estado": "fallo", "respaldo": None, "detalle": "detección: " + error_text(step, e)}
    if clase == "dev" and not allow_dev:
        return {"estado": "pendiente", "respaldo": None, "detalle": "pide al dev (apply --include)"}
    if step.exclusivo:
        cond = step.condicion or base_sin_otras_conexiones
        motivo = cond(ctx)
        if motivo:
            return {"estado": "pendiente", "respaldo": None,
                    "detalle": f"{motivo}: cierra las demás sesiones y vuelve a correr apply --guiados"}
        ctx.exclusivo_ok = lambda: cond(ctx)
    started = time.time()
    before = set() if step.catalog else _snapshot(ctx)
    try:
        if step.catalog:
            res = _machine.OPS[step.op].apply(ctx, allow_no_backup=allow_dev, **step.args)
        else:
            out = step.aplicar(ctx) or {}
            if out.get("estado") in ("pendiente", "manual", "fallo", "sin-cambio"):
                res = {"estado": out["estado"], "respaldo": out.get("respaldo"), "detalle": out.get("detalle", "")}
            else:
                res = {"estado": "aplicado", "respaldo": out.get("respaldo"), "detalle": out.get("detalle", "")}
                if step.respaldo:
                    motivo = _check_declared_backup(ctx, res["respaldo"], started, before)
                    if motivo:
                        res = {"estado": "fallo", "respaldo": res["respaldo"], "detalle": motivo}
    except (Exception, SystemExit) as e:  # noqa: BLE001 — el fallo de un paso no detiene a los demás
        res = {"estado": "fallo", "respaldo": None, "detalle": error_text(step, e)}
    finally:
        ctx.exclusivo_ok = lambda: None
    return res
