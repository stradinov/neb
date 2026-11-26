"""
Migración guiada de neb 8.0.0: lo que Neb guardaba suelto en ~/.claude se muda a su carpeta de datos (`<datos>`:
NEB_DATA absoluta o ~/.neb; hooks/lib/neb_paths.py). Lo de Claude Code (settings.json, projects/, plugins/,
backups/) se queda donde está.

Pasos, en este orden; todos libres y con respaldo (corren solos al iniciar sesión o con /neb:migrate):
  mover-base        ~/.claude/neb.db -> <datos>/neb.db (exclusivo); en su lugar queda la base testigo;
  mover-respaldos   ~/.claude/neb-backups/ y los respaldos sueltos de Neb en ~/.claude -> <datos>/backups/;
  mover-compas      ~/.claude/compas.md -> <datos>/compas.md;
  mover-planes      ~/.claude/approved-plans/ -> <datos>/approved-plans/ (cualquier archivo);
  mover-research    ~/.claude/research/ -> <datos>/research/;
  mover-estado      ~/.claude/preprocess-state/ -> <datos>/state/preprocess/ y ~/.claude/neb-sounds/ ->
                    <datos>/cache/sounds/ (estado efímero y caché: con homónimos, queda el más nuevo);
  mover-requisitos  ~/.claude/.neb-requisitos.json -> <datos>/.neb-requisitos.json;
  fusionar-config   ~/.claude/notify-on-stop.json, notify-on-permission.json y preprocess.json ->
                    <datos>/config.json (notify.stop, notify.permission, preprocess).

Los pasos de mover archivos dejan un manifiesto JSON nuevo en <datos>/backups/ (origen, destino y tamaño de cada
archivo: con qué deshacer el movimiento) y nunca pisan un homónimo distinto (queda en su lugar y el paso pide al
dev); son idempotentes: si una sesión abierta con la versión anterior vuelve a dejar archivos en ~/.claude, el
siguiente inicio de sesión los vuelve a mudar. Con NEB_DATA en ~/.claude no hay mudanza (solo fusionar-config).

Prompt: migrations/8.0.0.md. Formato: migrations/README.md. Mecánica: hooks/lib/_relocate.py. Residuo de
transición: sale en 9.0.0.
"""

import fnmatch
import json
import os
import sqlite3
import sys
import types

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_LIB = os.path.join(_ROOT, "hooks", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import _db_shared  # noqa: E402
import _migrations  # noqa: E402
import _relocate  # noqa: E402
import neb_paths  # noqa: E402
from _guided import GuidedStep, base_sin_otras_conexiones  # noqa: E402

VERSION = "8.0.0"

# Respaldos sueltos que Neb dejó directamente en ~/.claude (patrones exactos; también sus -wal/-shm/-journal):
# el migrador de nombre de 7.0.0 (neb-logbook.db.bak-<fecha>), la siembra de la taxonomía con su carpeta por
# omisión anterior a 8.0.0 (<base>.bak-pre-taxonomy-<fecha>: neb-logbook.db.bak-* y neb.db.bak-*) y copias
# anteriores a la carpeta de respaldos (neb.pre-*.db, neb-logbook.pre-*.db, compas.md.bak-*).
LOOSE_BACKUPS = ("neb-logbook.db.bak-*", "neb-logbook.pre-*.db", "neb.pre-*.db", "neb.db.bak-*", "compas.md.bak-*")
LEGACY_BACKUPS_DIR = "neb-backups"
LEGACY_TREES = {                    # paso: (carpeta en ~/.claude, partes de la ruta bajo la carpeta de datos)
    "mover-planes": ("approved-plans", (neb_paths.APPROVED_PLANS_NAME,)),
    "mover-research": ("research", (neb_paths.RESEARCH_NAME,)),
}
STATE_TREES = (("preprocess-state", ("state", "preprocess")), ("neb-sounds", ("cache", "sounds")))
REQ_FILE = ".neb-requisitos.json"
CONFIG_SOURCES = (("notify-on-stop.json", ("notify", "stop")),
                  ("notify-on-permission.json", ("notify", "permission")),
                  ("preprocess.json", ("preprocess",)))
_LIST_MAX = 5                       # rutas que lista el detalle de un conflicto o un fallo


def _misma_carpeta(ctx):
    """True si la carpeta de datos es ~/.claude (NEB_DATA apunta ahí): no hay nada que mudar."""
    return _relocate.same_path(ctx.data_dir, ctx.legacy_dir)


def _manifest_path(ctx, step):
    return os.path.join(ctx.backups_dir, f"manifest-{VERSION}.{step}.{_relocate._stamp()}.json")


def _prepare(ctx, folder):
    """Crea `folder` (0700) comprobando cada nivel desde la carpeta de datos: ninguno puede ser un enlace."""
    try:
        rel = os.path.relpath(os.path.abspath(folder), os.path.abspath(ctx.data_dir))
    except ValueError:                                   # otra unidad (Windows)
        rel = os.pardir
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return _relocate.ensure_tree(folder)
    return _relocate.ensure_tree(ctx.data_dir, "" if rel == os.curdir else rel)


def _rows_text(rows):
    shown = [r["origen"] + (f" ({r['motivo']})" if r.get("motivo") else "") for r in rows[:_LIST_MAX]]
    return ", ".join(shown) + (f" y {len(rows) - _LIST_MAX} más" if len(rows) > _LIST_MAX else "")


def _moves_result(res, what, dst):
    """Estado del paso a partir de lo que devolvió _relocate.apply_moves."""
    respaldo = res["manifiesto"]
    done = len(res["movidos"]) + len(res["reemplazados"])
    dropped = len(res["iguales"]) + len(res["descartados"])
    resumen = f"{done} archivo(s) de {what} a {dst}" + (
        f"; {dropped} ya estaba(n) en el destino y se quitaron del origen" if dropped else "")
    if respaldo:
        resumen += f"; manifiesto con qué deshacerlo: {respaldo}"
    if res["fallos"]:
        return {"estado": "fallo", "respaldo": respaldo,
                "detalle": f"{resumen}. No se pudieron mudar: {_rows_text(res['fallos'])}; se reintenta en el "
                           "siguiente inicio de sesión"}
    if res["conflictos"]:
        return {"estado": "manual", "respaldo": respaldo,
                "detalle": f"{resumen}. Quedan en su lugar, porque en el destino hay un archivo con el mismo nombre "
                           f"y otro contenido: {_rows_text(res['conflictos'])}. Compara cada uno con el del destino, "
                           "conserva el que sirva y quita el otro de ~/.claude"}
    if not respaldo:
        return {"estado": "sin-cambio", "detalle": f"no había {what} que mudar"}
    return {"respaldo": respaldo, "detalle": resumen}


def _apply_pairs(ctx, step, pairs, what, dst_root, newer_wins=False, prune=()):
    try:
        _prepare(ctx, ctx.backups_dir)
        _prepare(ctx, dst_root)
    except (OSError, ValueError) as e:
        return {"estado": "manual", "detalle": f"no se pudo preparar la carpeta de datos ({e}): no se mudó nada"}
    try:
        res = _relocate.apply_moves(pairs, _manifest_path(ctx, step), f"{VERSION}:{step}", ctx.data_dir,
                                    newer_wins=newer_wins, prune=prune, keep=(ctx.legacy_dir,))
    except (OSError, ValueError) as e:
        return {"estado": "fallo", "detalle": f"no se pudo escribir el manifiesto ({type(e).__name__}): no se mudó "
                                              "nada"}
    return _moves_result(res, what, dst_root)


# --------------------------------------------------------------------------- mover-base

def _legacy_db(ctx):
    return os.path.join(ctx.legacy_dir, neb_paths.DB_NAME)


def _detectar_base(ctx):
    """Solo lee: en ~/.claude/neb.db hay algo que no es la base testigo (una base por mudar, o algo que pide al
    dev: un enlace, un archivo que no es base, una base además de la de la carpeta de datos)."""
    if _misma_carpeta(ctx):
        return False
    old = _legacy_db(ctx)
    if _relocate.is_link(old):
        return True
    try:
        if not os.path.isfile(old) or os.path.getsize(old) == 0:
            return False
    except OSError:
        return False
    return not _relocate.is_witness(old)


def _base_vieja_libre(ctx):
    """Condición de exclusivo sobre ~/.claude/neb.db (la de omisión mira ctx.db_path, la de la carpeta de datos):
    que ninguna otra conexión la tenga abierta en este momento. La mudanza la vuelve a comprobar con su propio
    candado (journal_mode=DELETE, lectura retenida durante el respaldo y BEGIN EXCLUSIVE justo antes de mover).
    Si no es una base SQLite, o es un enlace, la prueba fallaría siempre (o escribiría a través del enlace): la
    condición se da por cumplida y aplicar lo rechaza con su motivo."""
    old = _legacy_db(ctx)
    if _relocate.is_link(old):
        return None
    try:
        with open(old, "rb") as fh:
            if fh.read(16) != b"SQLite format 3\x00":
                return None
    except OSError:
        return None
    return base_sin_otras_conexiones(types.SimpleNamespace(db_path=old))


def _mover_base(ctx):
    motivo = ctx.exclusivo_ok()
    if motivo:
        return {"estado": "pendiente", "detalle": motivo}
    old, new = _legacy_db(ctx), ctx.db_path
    if not _relocate.is_link(old) and _relocate.is_witness(old):
        return {"estado": "sin-cambio", "detalle": "la base ya está en la carpeta de datos"}
    if _db_shared._probe_db(new) in ("usable", "bloqueada") and not _relocate.is_link(old):
        return {"estado": "manual",
                "detalle": f"hay una base en {old} además de la de la carpeta de datos ({new}): probablemente la "
                           "creó una sesión abierta con una versión anterior de neb después de la mudanza, o se "
                           "copió a mano. Neb usa la de la carpeta de datos; la de ~/.claude no se mezcla ni se "
                           "pisa. Revisa si trae algo que quieras conservar y muévela fuera de ~/.claude (no la "
                           "borres sin revisarla)"}
    try:
        _prepare(ctx, os.path.dirname(os.path.abspath(new)))
        _prepare(ctx, ctx.backups_dir)
    except (OSError, ValueError) as e:
        return {"estado": "manual", "detalle": f"no se pudo preparar la carpeta de datos ({e}): no se movió nada"}
    stamp = _relocate._stamp()
    backup = os.path.join(ctx.backups_dir, f"neb.pre-{VERSION}.{stamp}.db")
    witness = os.path.join(ctx.legacy_dir, f".{neb_paths.DB_NAME}.testigo-{stamp}")
    witness_ok = True
    try:
        _relocate.write_witness(witness, _migrations.neb_version())
    except (OSError, sqlite3.Error):
        witness_ok = False                      # la base se muda igual; el aviso lo dice
    try:
        r = _relocate.move_db(old, new, backup, witness=witness if witness_ok else None)
    finally:
        for f in (witness,) + tuple(witness + s for s in _relocate.SIDECARS):
            _relocate._remove_quiet(f)          # si ocupó el lugar de la base, ya no existe con este nombre
    detalle = " ".join(x for x in (r["mensaje"], r["aviso"]) if x)
    if r["codigo"] == "ok":
        if witness_ok and _relocate.is_witness(old):
            detalle += (f" En {old} quedó la base testigo (sin datos): una sesión abierta con una versión anterior "
                        "de neb deja de capturar hasta reiniciarla, en vez de crear ahí una base vacía.")
        elif not r["aviso"]:
            detalle += (f" No se pudo dejar la base testigo en {old}: una sesión abierta con una versión anterior "
                        "puede crear ahí una base vacía; el siguiente inicio de sesión lo detecta.")
        return {"respaldo": r["respaldo"], "detalle": detalle}
    if r["codigo"] == "nada":
        return {"estado": "sin-cambio", "detalle": detalle}
    if r["codigo"] == "ocupada":
        return {"estado": "pendiente", "detalle": detalle}
    if r["codigo"] == "aborto":
        return {"estado": "manual", "detalle": detalle}
    return {"estado": "fallo", "respaldo": r["respaldo"], "detalle": detalle}


# --------------------------------------------------------------------------- mover-respaldos

def _loose_backups(ctx):
    """Los respaldos sueltos de Neb directamente en ~/.claude (LOOSE_BACKUPS y sus -wal/-shm/-journal), sin
    enlaces ni carpetas."""
    patterns = [p + s for p in LOOSE_BACKUPS for s in ("",) + _relocate.SIDECARS]
    out = []
    try:
        entries = sorted(os.scandir(ctx.legacy_dir), key=lambda e: e.name)
    except OSError:
        return out
    for e in entries:
        if not any(fnmatch.fnmatchcase(e.name, p) for p in patterns):
            continue
        if _relocate.is_link(e.path):
            continue
        try:
            if e.is_file(follow_symlinks=False):
                out.append(e.path)
        except OSError:
            continue
    return out


def _backup_pairs(ctx):
    src_root = os.path.join(ctx.legacy_dir, LEGACY_BACKUPS_DIR)
    pairs = _relocate.tree_pairs(src_root, ctx.backups_dir)
    pairs += [(p, os.path.join(ctx.backups_dir, os.path.basename(p))) for p in _loose_backups(ctx)]
    return pairs, src_root


def _detectar_respaldos(ctx):
    if _misma_carpeta(ctx):
        return False
    pairs, src_root = _backup_pairs(ctx)
    return bool(pairs) or _relocate.is_link(src_root)


def _mover_respaldos(ctx):
    pairs, src_root = _backup_pairs(ctx)
    if _relocate.is_link(src_root):
        return {"estado": "manual", "detalle": f"{src_root} es un enlace: la mudanza no lo sigue. Mueve sus archivos "
                                               f"a mano a {ctx.backups_dir} y quita el enlace"}
    return _apply_pairs(ctx, "mover-respaldos", pairs, "respaldos de Neb", ctx.backups_dir, prune=(src_root,))


# --------------------------------------------------------------------------- mover-compas y mover-requisitos

def _file_step(name, step, what):
    def pairs(ctx):
        src = os.path.join(ctx.legacy_dir, name)
        return src, os.path.join(ctx.data_dir, name)

    def detectar(ctx):
        if _misma_carpeta(ctx):
            return False
        src, _dst = pairs(ctx)
        return _relocate.is_link(src) or os.path.isfile(src)

    def aplicar(ctx):
        src, dst = pairs(ctx)
        if _relocate.is_link(src):
            return {"estado": "manual", "detalle": f"{src} es un enlace: la mudanza no lo sigue. Mueve el archivo a "
                                                   f"mano a {dst} y quita el enlace"}
        return _apply_pairs(ctx, step, [(src, dst)], what, ctx.data_dir)
    return detectar, aplicar


_detectar_compas, _mover_compas = _file_step(neb_paths.COMPAS_NAME, "mover-compas", "compas.md")
_detectar_requisitos, _mover_requisitos = _file_step(REQ_FILE, "mover-requisitos",
                                                     "la decisión «No volver a ofrecer» de la oferta de Python")


# --------------------------------------------------------------------------- mover-planes, mover-research, mover-estado

def _trees(ctx, specs):
    """[(raíz vieja, raíz nueva)] de cada (carpeta en ~/.claude, partes bajo la carpeta de datos)."""
    return [(os.path.join(ctx.legacy_dir, old), os.path.join(ctx.data_dir, *new)) for old, new in specs]


def _tree_step(step, specs, what, newer_wins=False):
    def detectar(ctx):
        if _misma_carpeta(ctx):
            return False
        return any(_relocate.is_link(src) or _relocate.walk_files(src) for src, _dst in _trees(ctx, specs))

    def aplicar(ctx):
        roots = _trees(ctx, specs)
        linked = [src for src, _dst in roots if _relocate.is_link(src)]
        if linked:
            return {"estado": "manual", "detalle": f"{', '.join(linked)}: es un enlace y la mudanza no lo sigue. Mueve "
                                                   "su contenido a mano a la carpeta de datos y quita el enlace"}
        pairs = [p for src, dst in roots for p in _relocate.tree_pairs(src, dst)]
        dst_text = " y ".join(dst for _src, dst in roots)
        res = None
        for _src, dst in roots:
            try:
                _prepare(ctx, dst)
            except (OSError, ValueError) as e:
                res = {"estado": "manual", "detalle": f"no se pudo preparar {dst} ({e}): no se mudó nada"}
        return res or _apply_pairs(ctx, step, pairs, what, ctx.data_dir, newer_wins=newer_wins,
                                   prune=tuple(src for src, _dst in roots))
    return detectar, aplicar


_detectar_planes, _mover_planes = _tree_step("mover-planes", [LEGACY_TREES["mover-planes"]], "planes aprobados")
_detectar_research, _mover_research = _tree_step("mover-research", [LEGACY_TREES["mover-research"]],
                                                 "investigaciones (research/)")
_detectar_estado, _mover_estado = _tree_step("mover-estado", STATE_TREES,
                                             "estado de preprocess y caché de sonidos", newer_wins=True)


# --------------------------------------------------------------------------- fusionar-config

def _config_sources(ctx):
    return [(os.path.join(ctx.legacy_dir, name), section) for name, section in CONFIG_SOURCES]


def _config_path(ctx):
    return os.path.join(ctx.data_dir, neb_paths.CONFIG_NAME)


def _detectar_config(ctx):
    return any(os.path.lexists(path) for path, _section in _config_sources(ctx))


def _read_text(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8-sig")


def _fusionar_config(ctx):
    """Crea o completa <datos>/config.json con los tres JSON sueltos, sin pisar una llave que ya tenga con otro
    valor, y borra los sueltos. Todo o nada: con un JSON ilegible, un enlace o una llave en conflicto no escribe
    ni borra nada (pide al dev). El respaldo es un archivo nuevo con los textos originales (y el config.json
    previo, si había)."""
    found = [(p, sec) for p, sec in _config_sources(ctx) if os.path.lexists(p)]
    if not found:
        return {"estado": "sin-cambio", "detalle": "no hay configuración suelta en ~/.claude"}
    cfg_path = _config_path(ctx)
    for path in [p for p, _s in found] + [cfg_path]:
        if _relocate.is_link(path) or (os.path.lexists(path) and not os.path.isfile(path)):
            return {"estado": "manual", "detalle": f"{path} es un enlace o no es un archivo: no se sigue ni se toca "
                                                   "nada. Muévelo a mano"}
    texts, values = {}, {}
    for path, _section in found:
        try:
            texts[path] = _read_text(path)
            value = json.loads(texts[path])
        except (OSError, ValueError) as e:
            return {"estado": "manual", "detalle": f"{path} no es JSON legible ({type(e).__name__}): no se tocó "
                                                   "nada. Corrígelo o bórralo a mano"}
        if not isinstance(value, dict):
            return {"estado": "manual", "detalle": f"{path} no es un objeto JSON: no se tocó nada. Corrígelo o "
                                                   "bórralo a mano"}
        values[path] = value
    previous = None
    config = {"schema": neb_paths.CONFIG_SCHEMA}
    if os.path.isfile(cfg_path):
        try:
            previous = _read_text(cfg_path)
            config = json.loads(previous)
        except (OSError, ValueError) as e:
            return {"estado": "manual", "detalle": f"{cfg_path} no es JSON legible ({type(e).__name__}): no se tocó "
                                                   "nada. Corrígelo a mano"}
        if not isinstance(config, dict):
            return {"estado": "manual", "detalle": f"{cfg_path} no es un objeto JSON: no se tocó nada"}
        config.setdefault("schema", neb_paths.CONFIG_SCHEMA)
    conflicts, added = [], 0
    for path, section in found:
        node = config
        for part in section:
            child = node.setdefault(part, {})
            if not isinstance(child, dict):
                conflicts.append(".".join(section))
                child = None
                break
            node = child
        if node is None or child is None:
            continue
        for key, value in values[path].items():
            if key not in node:
                node[key] = value
                added += 1
            elif node[key] != value:
                conflicts.append(".".join(section + (key,)))
    if conflicts:
        return {"estado": "manual",
                "detalle": f"{cfg_path} ya trae con otro valor: {', '.join(conflicts)}. No se escribió ni se borró "
                           "nada: deja en config.json el valor que quieras (rige ese) y borra de ~/.claude el JSON "
                           "suelto, o iguala los dos"}
    try:
        _prepare(ctx, ctx.backups_dir)
        backup = os.path.join(ctx.backups_dir, f"config-sources.pre-{VERSION}.{_relocate._stamp()}.json")
        _relocate._write_new_json(backup, {
            "paso": f"{VERSION}:fusionar-config", "creado": _relocate._now(),
            "deshacer": "vuelve a escribir cada archivo de «archivos» con su texto y deja config.json como "
                        "«config_json_previo» (bórralo si es null)",
            "archivos": texts, "config_json": cfg_path, "config_json_previo": previous})
    except (OSError, ValueError) as e:
        return {"estado": "fallo", "detalle": f"no se pudo escribir el respaldo ({type(e).__name__}): no se tocó nada"}
    try:
        _prepare(ctx, ctx.data_dir)
        _relocate.write_json_atomic(cfg_path, config)
    except (OSError, ValueError) as e:
        _relocate._remove_quiet(backup)
        return {"estado": "fallo", "detalle": f"no se pudo escribir {cfg_path} ({type(e).__name__}): no se tocó nada"}
    failed = []
    for path, _section in found:
        try:
            os.remove(path)
        except OSError as e:
            failed.append(f"{path} ({type(e).__name__})")
    detalle = (f"{cfg_path} {'completado' if previous is not None else 'creado'} con "
               f"{', '.join(os.path.basename(p) for p, _s in found)} ({added} llave(s) nuevas); respaldo de los "
               f"textos originales: {backup}")
    if failed:
        return {"estado": "fallo", "respaldo": backup,
                "detalle": f"{detalle}. No se pudieron borrar: {', '.join(failed)}; se reintenta en el siguiente "
                           "inicio de sesión"}
    return {"respaldo": backup, "detalle": detalle + "; se borraron los originales"}


STEPS = [
    GuidedStep("mover-base", "Mudar la base de ~/.claude/neb.db a la carpeta de datos (deja la base testigo)",
               detectar=_detectar_base, aplicar=_mover_base, respaldo=True, exclusivo=True,
               condicion=_base_vieja_libre),
    GuidedStep("mover-respaldos", "Mudar los respaldos de Neb (neb-backups/ y los sueltos de ~/.claude) a "
                                  "<datos>/backups/",
               detectar=_detectar_respaldos, aplicar=_mover_respaldos, respaldo=True),
    GuidedStep("mover-compas", "Mudar compas.md a la carpeta de datos",
               detectar=_detectar_compas, aplicar=_mover_compas, respaldo=True),
    GuidedStep("mover-planes", "Mudar los planes aprobados (approved-plans/) a la carpeta de datos",
               detectar=_detectar_planes, aplicar=_mover_planes, respaldo=True),
    GuidedStep("mover-research", "Mudar las investigaciones (research/) a la carpeta de datos",
               detectar=_detectar_research, aplicar=_mover_research, respaldo=True),
    GuidedStep("mover-estado", "Mudar el estado de preprocess y la caché de sonidos a la carpeta de datos",
               detectar=_detectar_estado, aplicar=_mover_estado, respaldo=True),
    GuidedStep("mover-requisitos", "Mudar .neb-requisitos.json a la carpeta de datos",
               detectar=_detectar_requisitos, aplicar=_mover_requisitos, respaldo=True),
    GuidedStep("fusionar-config", "Juntar notify-on-stop.json, notify-on-permission.json y preprocess.json en "
                                  "<datos>/config.json",
               detectar=_detectar_config, aplicar=_fusionar_config, respaldo=True),
]
