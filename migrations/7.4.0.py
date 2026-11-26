"""
Migración guiada de neb 7.4.0: el slug de un tema que el paso de base 3 movió para que la raíz del eje tome
'proyecto' también se cambia en «- **Temas:**» de compas.md.

Desde 7.4.0 el paso de base 3 ya no se detiene si un tema ocupa el slug 'proyecto': lo mueve al slug libre
'proyecto-<id>' (o 'proyecto-<id>-<n>', _migrations.free_project_slug) y la raíz toma 'proyecto'. compas.md
resuelve los temas por slug: si un objetivo citaba 'proyecto' en «- **Temas:**», ahora apuntaría a la raíz del
eje (que nunca pondera) y el peso de ese objetivo dejaría de aplicarse sin aviso. Este paso lo cambia por el slug
nuevo, sin pedirle nada al dev.

Prompt: migrations/7.4.0.md. Formato: migrations/README.md.
"""

import os
import re
import sqlite3
import stat
import sys
from pathlib import Path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_LIB = os.path.join(_ROOT, "hooks", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import _machine  # noqa: E402
from _guided import GuidedStep  # noqa: E402

COMPAS_NAME = "compas.md"
AXIS_ROOT = "proyecto"
_BOM = b"\xef\xbb\xbf"

# Misma forma de línea que lee parse_compas (`_field_value`): prefijo de guiones, asteriscos o espacios, la
# etiqueta, sus dos puntos, los asteriscos de cierre y el valor hasta el fin de línea.
_TEMAS_RE = re.compile(r"^([ \t\-*]*Temas[ \t]*:[ \t]*\**[ \t]*)(.*?)([ \t]*\r?\n?)$")


def _remove_quiet(path):
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass
    try:
        os.remove(path)
    except OSError:
        pass


def _compas_path(ctx):
    """compas.md de la carpeta de datos (desde 8.0.0) si existe; si no, el de ~/.claude: una máquina que todavía
    no corre la mudanza de 8.0.0, o este paso pendiente cuando compas.md sigue sin mudar."""
    data_dir = getattr(ctx, "data_dir", None)
    if data_dir:
        new = os.path.join(data_dir, COMPAS_NAME)
        if os.path.isfile(new):
            return new
    return os.path.join(ctx.claude_dir, COMPAS_NAME)


def _read(path):
    """Bytes de compas.md, o None si no existe o no es un archivo regular."""
    if _machine.is_link(path) or not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()


def moved_slug(db_path):
    """Slug al que el paso de base 3 movió el tema que ocupaba 'proyecto', o None. Solo lee (mode=ro). Lo
    reconoce por su forma, que free_project_slug deriva del id del tema: 'proyecto-<id>' o 'proyecto-<id>-<n>',
    con la raíz 'proyecto' presente. Con más de un candidato no decide (None)."""
    if not os.path.isfile(db_path):
        return None
    try:
        con = sqlite3.connect(Path(os.path.abspath(db_path)).as_uri() + "?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        if con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'topic'").fetchone() is None:
            return None
        if con.execute("SELECT 1 FROM topic WHERE slug = ? AND parent_id IS NULL",
                       (AXIS_ROOT,)).fetchone() is None:
            return None
        found = [slug for tid, slug in con.execute(
                     "SELECT id, slug FROM topic WHERE slug LIKE ? ESCAPE '\\'", (AXIS_ROOT + "-%",))
                 if re.fullmatch(rf"{AXIS_ROOT}-{tid}(-\d+)?", slug)]
        return found[0] if len(found) == 1 else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


def rewrite_temas(text, new_slug):
    """El texto con cada `proyecto` de las líneas «Temas:» cambiado por new_slug (mismo espaciado y fines de
    línea); el resto, igual. Devuelve (texto, cambios)."""
    out, changes = [], 0
    for line in text.splitlines(keepends=True):
        m = _TEMAS_RE.match(line)
        if m:
            cells = m.group(2).split(",")
            for i, cell in enumerate(cells):
                if cell.strip().lower() == AXIS_ROOT:
                    cells[i] = cell.replace(cell.strip(), new_slug)
                    changes += 1
            line = m.group(1) + ",".join(cells) + m.group(3)
        out.append(line)
    return "".join(out), changes


def _decode(raw):
    bom = _BOM if raw.startswith(_BOM) else b""
    return bom, raw[len(bom):].decode("utf-8")


def _detectar(ctx):
    """Solo lee: compas.md cita 'proyecto' en «Temas:» y la base trae el tema que el paso 3 movió."""
    try:
        raw = _read(_compas_path(ctx))
    except OSError:
        return False
    if raw is None:
        return False
    data = raw[len(_BOM):] if raw.startswith(_BOM) else raw
    _t, changes = rewrite_temas(data.decode("utf-8", errors="replace"), "x")
    return changes > 0 and moved_slug(ctx.db_path) is not None


def _aplicar(ctx):
    path = _compas_path(ctx)
    new_slug = moved_slug(ctx.db_path)
    if new_slug is None:
        return {"estado": "sin-cambio", "detalle": "la base no trae un tema movido por el paso 3"}
    try:
        raw = _read(path)
    except OSError as e:
        return {"estado": "fallo", "detalle": f"no se pudo leer compas.md ({type(e).__name__})"}
    if raw is None:
        return {"estado": "sin-cambio", "detalle": "no hay compas.md"}
    try:
        bom, text = _decode(raw)
    except UnicodeDecodeError:
        return {"estado": "fallo", "detalle": "compas.md no es UTF-8: no se tocó"}
    new_text, changes = rewrite_temas(text, new_slug)
    if not changes:
        return {"estado": "sin-cambio", "detalle": "compas.md no cita 'proyecto' en Temas:"}
    new = bom + new_text.encode("utf-8")
    # Solo lectura: se quita la protección justo antes de reemplazarlo y el archivo nuevo la conserva.
    read_only = not os.access(path, os.W_OK)
    orig_mode = None
    backup = tmp = None
    try:
        _machine._private_dir(ctx.backups_dir)
        backup = os.path.join(ctx.backups_dir, f"compas.pre-7.4.0.{_machine._stamp()}.md")
        with open(backup, "xb") as fh:          # archivo nuevo de esta corrida
            fh.write(raw)
        tmp = os.path.join(os.path.dirname(path), f".{COMPAS_NAME}.tmp-{_machine._stamp()}")   # junto al original
        with open(tmp, "xb") as fh:
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        import shutil
        shutil.copymode(path, tmp)              # si falla, es fallo: el nuevo perdería permisos o protección
        if _read(path) != raw:                  # otra sesión lo reescribió: no se pisa su versión
            _remove_quiet(tmp)
            _remove_quiet(backup)
            return {"estado": "pendiente", "detalle": "compas.md cambió mientras se migraba: se reintenta en el "
                                                      "siguiente inicio de sesión"}
        if read_only:
            orig_mode = stat.S_IMODE(os.stat(path).st_mode)
            os.chmod(path, orig_mode | stat.S_IWRITE)
        os.replace(tmp, path)
        tmp = None
    except OSError as e:
        if orig_mode is not None:
            try:
                os.chmod(path, orig_mode)
            except OSError:
                pass
        if tmp:
            _remove_quiet(tmp)
        if backup and os.path.exists(backup):
            _remove_quiet(backup)
        return {"estado": "fallo", "detalle": f"no se pudo reescribir compas.md ({type(e).__name__}): "
                                              f"el original quedó intacto"}
    return {"respaldo": backup,
            "detalle": f"compas.md: 'proyecto' pasó a '{new_slug}' en Temas: ({changes} cita(s))"
                      + ("; era de solo lectura: se le quitó la protección para reemplazarlo y el archivo "
                         "nuevo la conserva" if read_only else "")}


STEPS = [
    GuidedStep("compas-tema-proyecto",
               "Cambiar en Temas: de compas.md el slug del tema que el paso de base 3 movió de 'proyecto'",
               detectar=_detectar, aplicar=_aplicar, respaldo=True),
]
