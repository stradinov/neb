#!/usr/bin/env python3
"""
neb-migrate.py — estado y operación de la versión de esquema de neb.db y de las migraciones guiadas
(Neb, desde 6.48.0; migraciones guiadas desde 6.49.0).

  status [--json]            versiones del código y de la base, pasos de base detenidos y su motivo,
                             pasos guiados pendientes y omitidos, respaldos. Solo lectura: no crea la base
                             ni escribe.
  apply [--guiados] [--include <id>…] [--sin-exclusivos]
                             abre la base como lo hace la captura (pasos de base pendientes y reparaciones;
                             reintenta ya un paso con fallo reciente; sin base no la crea). Solo con --guiados
                             (lo pasa /neb:migrate) corre además los pasos guiados que dejan con qué deshacerlos;
                             los que piden al dev corren solo con --include <versión>:<paso>; --sin-exclusivos
                             deja pendientes los exclusivos. --include y --sin-exclusivos implican --guiados.
                             Con la base sin mudar (sigue en ~/.claude, donde vivía hasta 7.x) no la abre: corren
                             antes los pasos guiados (8.0.0:mover-base la muda a la carpeta de datos) y después
                             los de base.
  skip <id>                  guarda el «no» del dev a un paso guiado: sale de lo pendiente hasta que se pida
                             con apply --include. Sin base, con la base sin mudar, o con una base más nueva que
                             no tiene la tabla, se niega.
  restore <archivo> [--remigrar]
                             vuelve la base al contenido de un respaldo de la carpeta de respaldos (`backups/`
                             junto a la base: neb.pre-paso-*.db o neb.pre-restore.*.db). Antes respalda la base
                             actual. Con la base sin mudar se niega. Se niega si el código
                             que lo corre no podría operar la base restaurada, o si la siguiente conexión
                             volvería a aplicar los pasos que el respaldo no tiene (--remigrar lo permite).
                             Volver atrás: primero regresar plugin y clon a la versión anterior.
  schema                     imprime el esquema vigente (esquema inicial + todos los pasos de base).
  al-iniciar                 la entrada de migración de SessionStart (desde 7.5.0): con el candado entre corridas,
                             corre lo que deja con qué deshacerlo (como apply --guiados, con presupuesto de tiempo
                             y ventana de reintento de los exclusivos) y emite el aviso para el contexto de Claude:
                             lo aplicado, lo pendiente, el aviso de base y el encargo del menú para lo que pide al
                             dev. Sale siempre con 0.

apply, skip, restore y al-iniciar toman el mismo candado (desde 8.0.0, doble: el de ~/.claude, que toman las
sesiones abiertas con 7.5–7.6, y el de la carpeta de datos): si otra corrida lo tiene, responden
migracion-en-curso. Lo toman después de crear la carpeta de datos (~/.neb o NEB_DATA).

Salida 0 si la operación terminó; 1 si se negó o falló (el motivo va en la salida). Documento:
tooling/migrations.md.
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "lib")
sys.path.insert(0, _LIB)

import _db_shared    # noqa: E402
import _guided       # noqa: E402
import _machine      # noqa: E402
import _migrations   # noqa: E402
import neb_paths     # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_BACKUP_NAME_RE = re.compile(r"^neb\.pre-(paso-(\d+)|restore)\.[0-9TZ]+\.db$")

SIN_TIEMPO = "sin tiempo en este inicio de sesión: se reintenta en el siguiente (o con /neb:migrate)"


def _home():
    return os.path.expanduser("~")


def _existing_db(home):
    """Ruta de la base (resolve_db_path) si existe y no está vacía, o None. Sin abrir nada."""
    p = _db_shared.resolve_db_path(home)
    try:
        return p if os.path.isfile(p) and os.path.getsize(p) > 0 else None
    except OSError:
        return None


def _unmoved(home):
    """UnmovedDb si la base sigue sin mudar en ~/.claude (_db_shared.unmoved_legacy), o None. No crea nada."""
    return _db_shared.unmoved_legacy(home)


def _legacy_skips(home):
    """(omitidos, error) de migration_skip en la base vieja (~/.claude/neb.db), en solo lectura: mientras la base
    no se mude, el «no» del dev a un paso vive ahí y no se vuelve a ofrecer lo ya rechazado."""
    con = _migrations.open_readonly(_db_shared.legacy_db_path(home))
    if con is None:
        return set(), None
    try:
        return _guided.read_skips(con), None
    except sqlite3.Error as e:
        return set(), str(e)
    finally:
        con.close()


# --------------------------------------------------------------------------- status

def status(home):
    c = _migrations.code_version()
    out = {"neb_version": _migrations.neb_version(), "schema_version_code": c, "db": None,
           "schema_version_db": None, "min_compatible_db": None, "estado": "sin-base",
           "pasos_detenidos": [], "respaldos": [], "guiados": None}
    unmoved = _unmoved(home)
    if unmoved is not None:
        out["estado"] = "sin-mudar"
        out["detalle"], out["accion"] = unmoved.detalle, unmoved.accion
        skips, skips_error = _legacy_skips(home)
        out["guiados"] = _guided_status(home, None, skips, skips_error)
        return out
    db = _existing_db(home)
    if db is None:
        out["guiados"] = _guided_status(home, None, set())
        return out
    out["db"] = db
    out["respaldos"] = [{"archivo": p, "bytes": n} for p, n in _migrations.list_backups(db)]
    con = _migrations.open_readonly(db)
    if con is None:
        out["estado"] = "ilegible"
        out["guiados"] = _guided_status(home, db, set())
        return out
    skips, skips_error = set(), None
    try:
        try:
            skips = _guided.read_skips(con)
        except sqlite3.Error as e:
            skips_error = str(e)
        v, f = _migrations.read_version(con)
        out["schema_version_db"], out["min_compatible_db"] = v, f
        if v > c:
            out["estado"] = "mas-nueva-compatible" if c >= f else "incompatible"
        elif v < c:
            out["estado"] = "atras"
        else:
            out["estado"] = "al-dia"
        if v <= c:
            out["pasos_detenidos"] = [{"paso": n, "titulo": t, "motivo": m}
                                      for n, t, m in _migrations.blocked_report(con)]
    except sqlite3.Error as e:
        out["estado"] = "ilegible"
        out["error"] = str(e)
    finally:
        con.close()
    out["guiados"] = _guided_status(home, db, skips, skips_error)
    return out


def _guided_status(home, db, skips, skips_error=None):
    """Pasos guiados pendientes (lo que la detección dice ahora) y omitidos por el dev. Solo lee."""
    migrations, errors = _guided.load(ROOT)
    rows = _guided.survey(_machine.Ctx(home, db_path=db), migrations, skips)
    return {"pendientes": [r for r in rows if not r["omitido"]],
            "omitidos": [r for r in rows if r["omitido"]],
            "errores_de_carga": [{"archivo": a, "motivo": m} for a, m in errors],
            "error_omitidos": skips_error}


_ESTADOS = {
    "sin-base": "no hay base todavía (la crea la primera captura)",
    "sin-mudar": "en ~/.claude, donde la guardaba neb hasta 7.x: neb no la abre hasta que la migración guiada la "
                 "mude a la carpeta de datos",
    "ilegible": "la base no se pudo leer",
    "al-dia": "al día",
    "atras": "atrás: la siguiente conexión aplica los pasos pendientes",
    "mas-nueva-compatible": "más nueva que este código, pero compatible: opera sin migrar",
    "incompatible": "más nueva que este código e incompatible: este código no la toca",
}


def _print_guided(g):
    for r in (g or {}).get("pendientes", []):
        if r["error"]:
            print(f"paso guiado {r['id']} ({r['titulo']}): falló la detección: {r['error']}")
            continue
        clase = "corre solo con apply --guiados" if r["clase"] == "solo" else "pide al dev (apply --include)"
        print(f"paso guiado pendiente {r['id']} ({r['titulo']}): {clase}"
              + (" · corre cuando ninguna otra sesión tenga la base abierta" if r["exclusivo"] else ""))
    for r in (g or {}).get("omitidos", []):
        print(f"paso guiado omitido por el dev: {r['id']} ({r['titulo']})")
    for e in (g or {}).get("errores_de_carga", []):
        print(f"migración guiada que no carga: {e['archivo']}: {e['motivo']}")
    if (g or {}).get("error_omitidos"):
        print(f"no se pudieron leer los pasos omitidos: {g['error_omitidos']}")


def _print_status(s):
    print(f"neb {s['neb_version']} · versión de esquema del código: {s['schema_version_code']}")
    if s["db"] is None:
        print("base: " + _ESTADOS[s["estado"] if s["estado"] == "sin-mudar" else "sin-base"])
        if s.get("detalle"):
            print(f"detalle: {s['detalle']}")
            print(f"acción: {s['accion']}")
        _print_guided(s.get("guiados"))
        return
    print(f"base: {s['db']}")
    if s["schema_version_db"] is not None:
        print(f"versión de esquema de la base: {s['schema_version_db']} "
              f"(mínima compatible: {s['min_compatible_db']})")
    print(f"estado: {_ESTADOS.get(s['estado'], s['estado'])}")
    if s["estado"] == "incompatible":
        print(f"acción: actualiza neb (plugin y clon) a una versión con la versión de esquema "
              f"{s['min_compatible_db']} o mayor")
    for p in s["pasos_detenidos"]:
        print(f"paso de base {p['paso']} ({p['titulo']}) detenido: {p['motivo']}")
    for r in s["respaldos"]:
        print(f"respaldo: {r['archivo']} ({r['bytes']} bytes)")
    _print_guided(s.get("guiados"))


# --------------------------------------------------------------------------- apply

def _open_for_apply(db, retry=True):
    """(con, err): la conexión de apply (pasos de base; con retry, reintento ya de un paso con fallo reciente
    guardado), o None y el dict del motivo, sin imprimirlo (quien llama lo imprime, con lo que ya corrió).
    al-iniciar pasa retry=False: respeta la espera tras un fallo, como la captura (cada intento de un paso
    destructivo copia la base con el candado de SQLite tomado)."""
    try:
        con = _db_shared._connect(db, retry=retry)
    except _db_shared.DbUnavailable as e:
        return None, e.to_dict()
    if con is None:
        return None, {"ok": False, "motivo": "sin-conexion",
                      "detalle": "no se pudo abrir la base (candado ocupado o error de SQLite)",
                      "accion": "reintenta en unos segundos"}
    return con, None


def apply(home, include=(), sin_exclusivos=False, guiados=False):
    """Pasos de base y reparaciones (como la captura) si hay base; sin base no la crea (la crea la primera
    captura, y un paso guiado puede necesitar ver la máquina sin ella). Luego, solo con guiados (lo pide
    /neb:migrate), los pasos guiados: reintentar un paso de base no corre la migración guiada.

    Con la base sin mudar no la abre (abrir <datos>/neb.db lo crearía vacío y escondería la base vieja): sin
    guiados responde base-sin-mudar; con guiados corren antes los pasos guiados (con los omitidos que guarda la
    base vieja) y, si 8.0.0:mover-base la llevó a la carpeta de datos, después los de base.

    Toma el candado entre corridas (desde 7.5.0; doble desde 8.0.0): si otra corrida lo tiene (`al-iniciar` de
    una sesión que está iniciando, otro apply, skip o restore), responde migracion-en-curso sin tocar nada."""
    held = _take_lock(home)
    if _blocked(held):
        return _lock_refusal(held, home)
    try:
        rc, out = _apply_core(home, include, sin_exclusivos, guiados)
    finally:
        _release(held)
    print(json.dumps(out, ensure_ascii=False))
    return rc


def _apply_core(home, include=(), sin_exclusivos=False, guiados=False, deadline=None, window=None, retry=True):
    """Lo que hace apply, sin candado ni impresión: (código, salida). `deadline` (time.monotonic), `window`
    (ExclusiveWindow) y retry=False los usa al-iniciar: pasado `deadline` no empieza otro paso guiado ni el
    bloque de pasos de base que va después de ellos (base sin mudar), los exclusivos reintentan dentro de
    `window`, y un paso de base con fallo reciente guardado espera (_open_for_apply).

    Con la base sin mudar (8.0.0), el orden cambia: primero los pasos guiados (8.0.0:mover-base la muda), luego
    los pasos de base sobre la base ya mudada y, si la mudanza ocurrió en esta corrida, una segunda pasada de los
    guiados: los de versiones anteriores que miran la base en la carpeta de datos (7.3.0:vacuum-neb-db) o que
    esperan un paso de base (7.4.0:compas-tema-proyecto, tras el paso 3) no se detectaban en la primera."""
    guiados = bool(guiados or include or sin_exclusivos)
    db = _db_shared.resolve_db_path(home)
    v, skips, skips_error = None, set(), None
    unmoved = _unmoved(home)
    if unmoved is not None and not guiados:
        return 1, unmoved.to_dict()
    if unmoved is not None:
        skips, skips_error = _legacy_skips(home)
    elif _existing_db(home) is not None:
        con, err = _open_for_apply(db, retry)
        if con is None:
            return 1, err
        try:
            v, _f = _migrations.read_version(con)
            try:
                skips = _guided.read_skips(con)
            except sqlite3.Error as e:
                skips_error = str(e)
        finally:
            con.close()                   # cerrada antes de los pasos guiados: un paso exclusivo no la vería libre
    if not guiados:
        guided = None
    elif skips_error:
        guided = _guided_out()
        guided["error"] = f"no se pudo leer migration_skip ({skips_error}): no corrió ningún paso guiado"
    else:
        guided = _apply_guided(home, db, skips, include, sin_exclusivos, deadline, window)
    if (unmoved is not None and _unmoved(home) is None and _existing_db(home) is not None
            and not _past(deadline)):
        con, err = _open_for_apply(db, retry)    # la base ya está en su lugar: sus pasos de base, con su respaldo
        if con is None:
            return 1, {**err, "guiados": guided}   # sin perder el reporte de la mudanza
        try:
            v, _f = _migrations.read_version(con)
            try:
                skips, skips_error = _guided.read_skips(con), None
            except sqlite3.Error as e:
                skips_error = str(e)
        finally:
            con.close()
        if skips_error:
            guided["error"] = (f"no se pudo leer migration_skip de la base ya mudada ({skips_error}): la segunda "
                               "pasada de los pasos guiados no corrió")
        elif not _past(deadline):
            guided = _merge_guided(guided, _apply_guided(home, db, skips, include, sin_exclusivos, deadline, window))
    s = status(home)
    c = _migrations.code_version()
    # Un paso con `espera` que no corrió (candado ocupado) no deja fila de error: ok exige también V >= C.
    # Una migración guiada que no carga tampoco es ok: sus pasos nunca correrían, en silencio.
    ok = not s["pasos_detenidos"] and (v is None or v >= c) and s["estado"] != "sin-mudar"
    if guided is not None:
        ok = ok and not (guided["error"] or guided["fallos"] or guided["no_encontrados"]
                         or guided["errores_de_carga"])
    return (0 if ok else 1), {"ok": ok, "base": s["db"], "schema_version_db": v, "schema_version_code": c,
                              "pasos_detenidos": s["pasos_detenidos"], "guiados": guided}


def _past(deadline):
    return deadline is not None and time.monotonic() >= deadline


def _merge_guided(first, second):
    """El reporte de las dos pasadas de los pasos guiados (base mudada en esta corrida): lo aplicado en las dos;
    lo pendiente, manual o con fallo, como lo ve la segunda, que detecta todo otra vez sobre la base ya mudada.
    Un fallo de la primera que la segunda ya no reporta de ninguna forma se conserva: no se esconde."""
    out = dict(second)
    out["aplicados"] = first["aplicados"] + second["aplicados"]
    seen = {r["id"] for key in ("aplicados", "pendientes", "manual", "fallos") for r in second[key]}
    out["fallos"] = [r for r in first["fallos"] if r["id"] not in seen] + second["fallos"]
    out["omision_sin_borrar"] = first["omision_sin_borrar"] + [k for k in second["omision_sin_borrar"]
                                                                if k not in first["omision_sin_borrar"]]
    out["error"] = first["error"] or second["error"]
    return out


# --------------------------------------------------------------------------- candado entre corridas

def _take_lock(home):
    """El candado entre corridas (desde 7.5.0; doble desde 8.0.0). Primero crea la carpeta de datos
    (neb_paths.ensure_dir: sin ella la mudanza de 8.0.0 no correría sola) y toma, sin esperar, el candado viejo de
    ~/.claude, que toman las sesiones abiertas con 7.5–7.6 al iniciar o limpiar la sesión (sin él, una de ellas
    podría correr la compactación de 7.3.0 o reescribir compas.md mientras 8.0.0 muda los archivos), y luego el
    de la carpeta de datos. El viejo se toma solo si el archivo ya existe: lo crea la primera corrida de 7.5 o
    7.6, así que sin archivo no hay sesión de esas versiones que lo tome, y crearlo dejaría un residuo nuevo en
    ~/.claude; si existe pero no se puede abrir (enlace, permiso), una sesión 7.x tampoco lo toma y se sigue sin
    él. Devuelve (fd viejo o None, fd nuevo); None si otra corrida tiene cualquiera de los dos; -1 si no se pudo
    crear la carpeta de datos ni el candado nuevo (es un enlace, no se puede escribir o el sistema de archivos
    no admite el candado): entonces no se corre nada."""
    ctx = _machine.Ctx(home)
    path = _guided.lock_path(ctx)
    try:
        neb_paths.ensure_dir(os.path.dirname(path))
    except (OSError, ValueError):
        return -1
    old = None
    legacy = _guided.legacy_lock_path(ctx)
    if not _same_file(legacy, path) and os.path.isfile(legacy):
        try:
            old = _guided.try_lock(legacy, create=False)
            if old is None:
                return None
        except OSError:
            old = None                             # no se pudo abrir: tampoco lo toma una sesión 7.x
    try:
        new = _guided.try_lock(path)
    except OSError:
        new = -1
    if new is None or new == -1:
        if old is not None:
            _guided.unlock(old)
        return new
    return (old, new)


def _same_file(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _release(held):
    if isinstance(held, tuple):
        old, new = held
        _guided.unlock(new)
        if old is not None:
            _guided.unlock(old)


def _blocked(held):
    """True si no se debe correr: otra corrida tiene el candado (None) o no se pudo crear (-1)."""
    return held is None or held == -1


def _lock_refusal(held, home=None):
    if held is None:
        return _refuse("migracion-en-curso",
                       "otra corrida de la migración de neb tiene el candado (una sesión que está iniciando, "
                       "o apply, skip o restore; también una sesión abierta con neb 7.5 o 7.6)",
                       "reintenta en unos segundos; si sigue, el siguiente inicio de sesión lo corre")
    folder = os.path.dirname(_guided.lock_path(_machine.Ctx(home or _home())))
    return _refuse("candado-no-disponible",
                   f"no se pudo tomar el candado entre corridas (.neb-migrate.lock en la carpeta de datos {folder}: "
                   "la carpeta o el candado es un enlace, no se pudo crear, no hay permiso de escritura o el "
                   "sistema de archivos no admite el candado)",
                   "revisa la carpeta de datos de neb (NEB_DATA, si la declaraste, o ~/.neb)")


def _guided_out():
    return {"aplicados": [], "pendientes": [], "manual": [], "fallos": [], "no_encontrados": [],
            "errores_de_carga": [], "omision_sin_borrar": [], "error": None}


def _apply_guided(home, db, skips, include, sin_exclusivos=False, deadline=None, window=None):
    """Corre los pasos guiados pendientes que dejan con qué deshacerlos y los pedidos con --include. Un paso
    omitido por el dev no corre salvo que se incluya; si corre bien, su «no» se borra. Con sin_exclusivos, los
    pasos exclusivos quedan pendientes (el dev eligió «Después»). Pasado `deadline`, un paso pendiente no se
    empieza y queda para el siguiente inicio de sesión; `window` es la ventana de reintento de los exclusivos."""
    migrations, errors = _guided.load(ROOT)
    ctx = _machine.Ctx(home, db_path=db)
    include = set(include)
    out = _guided_out()
    out["no_encontrados"] = sorted(k for k in include if _guided.find(migrations, k)[1] is None)
    out["errores_de_carga"] = [{"archivo": a, "motivo": m} for a, m in errors]
    unskip = []
    for m in migrations:
        for step in m.steps:
            key = _guided.step_key(m, step)
            included = key in include
            if key in skips and not included:
                continue
            late = _past(deadline)
            if late or (step.exclusivo and sin_exclusivos):
                r = {"estado": "pendiente", "respaldo": None,
                     "detalle": SIN_TIEMPO if late else "exclusivo: el dev lo dejó para después"}
                try:
                    if not _guided.detect(ctx, step):
                        r = {"estado": "sin-cambio", "respaldo": None, "detalle": ""}
                except (Exception, SystemExit) as e:  # noqa: BLE001
                    r = {"estado": "fallo", "respaldo": None, "detalle": "detección: " + _guided.error_text(step, e)}
            else:
                r = _guided.run(ctx, step, allow_dev=included, window=window)
            bucket = {"aplicado": "aplicados", "pendiente": "pendientes", "manual": "manual",
                      "fallo": "fallos"}.get(r["estado"])
            if bucket:
                out[bucket].append({"id": key, "titulo": step.titulo, "detalle": r["detalle"],
                                    "respaldo": r["respaldo"]})
            if r["estado"] in ("aplicado", "sin-cambio") and key in skips:
                unskip.append(key)
    if unskip:
        con = None
        if _unmoved(home) is None and _existing_db(home) is not None:   # sin mudar: abrirla la crearía vacía
            try:
                con = _db_shared._connect(db)
            except _db_shared.DbUnavailable:
                con = None
        if con is None:
            out["omision_sin_borrar"] = unskip
        else:
            try:
                out["omision_sin_borrar"] = [k for k in unskip if not _guided.remove_skip(con, k)]
            finally:
                con.close()
    return out


# --------------------------------------------------------------------------- skip

def skip(home, key):
    """Guarda el «no» del dev a un paso guiado, con el candado entre corridas (desde 7.5.0)."""
    held = _take_lock(home)
    if _blocked(held):
        return _lock_refusal(held, home)
    try:
        return _skip(home, key)
    finally:
        _release(held)


def _skip(home, key):
    migrations, _errors = _guided.load(ROOT)
    if _guided.find(migrations, key)[1] is None:
        return _refuse("paso-desconocido", f"no hay un paso guiado {key}",
                       "usa un id <versión>:<paso> de `neb-migrate.py status`")
    unmoved = _unmoved(home)
    if unmoved is not None:                        # abrir <datos>/neb.db lo crearía vacío y escondería la vieja
        return _refuse("base-sin-mudar", unmoved.detalle,
                       "el paso sigue pendiente; el «no» se podrá guardar cuando la migración guiada mude la base "
                       "a la carpeta de datos (el siguiente inicio de sesión o /neb:migrate)")
    if _existing_db(home) is None:                 # como apply: sin base no la crea
        return _refuse("sin-base", "no hay base donde guardar el «no»",
                       "el paso sigue pendiente; se podrá omitir cuando la primera captura cree la base")
    db = _db_shared.resolve_db_path(home)
    try:
        con = _db_shared._connect(db)
    except _db_shared.DbUnavailable as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False))
        return 1
    if con is None:
        return _refuse("sin-conexion", "no se pudo abrir la base (candado ocupado o error de SQLite)",
                       "reintenta en unos segundos")
    try:
        v, _f = _migrations.read_version(con)
        has_table = con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'migration_skip'"
                                ).fetchone() is not None
        if v > _migrations.code_version() and not has_table:
            # Base más nueva que opera sin migrar: este código no le agrega tablas (E1, regla de compatibilidad).
            return _refuse("base-mas-nueva", "la base es de una versión de neb más nueva y no tiene migration_skip",
                           "actualiza neb (plugin y clon) y vuelve a correr /neb:migrate")
        _guided.add_skip(con, key, _migrations.neb_version())
    except sqlite3.Error as e:
        return _refuse("skip-fallido", f"no se pudo guardar el «no»: {e}", "reintenta en unos segundos")
    finally:
        con.close()
    print(json.dumps({"ok": True, "omitido": key}, ensure_ascii=False))
    return 0


# --------------------------------------------------------------------------- restore

def _refuse(motivo, detalle, accion):
    print(json.dumps({"ok": False, "motivo": motivo, "detalle": detalle, "accion": accion}, ensure_ascii=False))
    return 1


def _is_link(path):
    """Enlace simbólico o junction (Path.is_junction es de 3.12; neb soporta 3.8+). Otros reparse points
    (archivos de OneDrive, deduplicados) no son enlaces."""
    try:
        if os.path.islink(path):
            return True
        tag = getattr(os.lstat(path), "st_reparse_tag", 0)
        return tag in (getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C),
                       getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003))
    except OSError:
        return True


def restore(home, archivo, remigrar=False):
    """Vuelve la base al contenido de un respaldo, con el candado entre corridas (desde 7.5.0)."""
    held = _take_lock(home)
    if _blocked(held):
        return _lock_refusal(held, home)
    try:
        return _restore(home, archivo, remigrar)
    finally:
        _release(held)


def _restore(home, archivo, remigrar=False):
    unmoved = _unmoved(home)
    if unmoved is not None:                        # restaurar crearía <datos>/neb.db y escondería la base vieja
        return _refuse("base-sin-mudar", unmoved.detalle,
                       "no se restauró nada: muda primero la base con /neb:migrate (o el siguiente inicio de "
                       "sesión) y vuelve a correr restore")
    db = _db_shared.resolve_db_path(home)
    folder = _migrations.backup_dir(db)
    name = os.path.basename(archivo)
    m = _BACKUP_NAME_RE.match(name)
    if not m:
        return _refuse("respaldo-no-valido", f"{name} no es un respaldo de {folder}",
                       "usa un neb.pre-paso-*.db o neb.pre-restore.*.db de `neb-migrate.py status`")
    if not os.path.isfile(archivo) or _is_link(archivo) or _is_link(folder):
        return _refuse("respaldo-no-valido", "el archivo no existe o hay un enlace en la ruta",
                       "usa la ruta que muestra `neb-migrate.py status`")
    # La carpeta de respaldos y el archivo no pueden ser enlace (arriba); un enlace en una carpeta superior (la
    # carpeta de datos movida con junction, unidad subst) es del dev y no impide restaurar: se comparan rutas
    # reales.
    real_parent = os.path.normcase(os.path.realpath(os.path.dirname(os.path.abspath(archivo))))
    if real_parent != os.path.normcase(os.path.realpath(folder)):
        return _refuse("respaldo-no-valido", f"el respaldo no está directamente en {folder}",
                       "usa la ruta que muestra `neb-migrate.py status`")
    ro = _migrations.open_readonly(archivo)
    if ro is None:
        return _refuse("respaldo-ilegible", f"no se pudo abrir {archivo}", "elige otro respaldo")
    try:
        if ro.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            return _refuse("respaldo-ilegible", f"{archivo} no pasa integrity_check", "elige otro respaldo")
        v_r, f_r = _migrations.read_version(ro)
    except sqlite3.Error as e:            # una copia cortada a medias (desde 7.5.0 se responde, no se lanza)
        return _refuse("respaldo-ilegible", f"{archivo} no se pudo leer ({type(e).__name__}: {e})",
                       "elige otro respaldo")
    finally:
        ro.close()
    c = _migrations.code_version()
    if f_r > c:
        return _refuse("respaldo-incompatible",
                       f"el respaldo pide al menos la versión de esquema {f_r} y este código trae la {c}",
                       "corre restore con una versión de neb que pueda operar ese respaldo")
    if c > v_r and not remigrar:
        return _refuse("se-volveria-a-migrar",
                       f"el respaldo está en la versión de esquema {v_r} y este código trae la {c}: la siguiente "
                       "conexión volvería a aplicar los pasos que el respaldo no tiene",
                       "regresa primero plugin y clon a la versión anterior (y desactiva la actualización "
                       "automática del plugin, que puede traer de vuelta la nueva); o usa --remigrar para "
                       "recuperar los datos y dejar que el paso corra otra vez")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    pre = None
    if os.path.isfile(db) and os.path.getsize(db) > 0:
        try:
            pre = _migrations.take_backup(db, f"neb.pre-restore.{stamp}.db")
        except (OSError, sqlite3.Error) as e:
            return _refuse("respaldo-fallido", f"no se pudo respaldar la base actual: {e}", "no se restauró nada")
    src = dst = None
    try:
        src = sqlite3.connect(archivo)
        dst = sqlite3.connect(db, timeout=5.0)        # conexión directa: nunca _connect, que migraría antes
        src.backup(dst)
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error as e:
        return _refuse("restauracion-fallida", str(e),
                       f"la base actual quedó respaldada en {pre}" if pre else "revisa la base")
    finally:
        for con in (dst, src):
            if con is not None:
                con.close()
    if ok != "ok":
        return _refuse("restauracion-fallida", f"integrity_check tras restaurar: {ok}",
                       f"la base anterior está en {pre}" if pre else "revisa la base")
    # Queda 1 neb.pre-restore: el nuevo; nunca se borra el archivo del que se restauró. Sin base previa
    # (pre = None) no hay nuevo, y no se poda.
    if pre:
        keep = {os.path.normcase(os.path.abspath(p)) for p in (pre, archivo)}
        import glob
        for p in glob.glob(os.path.join(glob.escape(folder), _migrations.RESTORE_BACKUP_GLOB)):
            if os.path.normcase(os.path.abspath(p)) not in keep:
                for f in (p, p + "-wal", p + "-shm", p + "-journal"):   # -journal: copia cortada a medias
                    try:
                        os.remove(f)
                    except OSError:
                        pass
    print(json.dumps({"ok": True, "restaurada_desde": archivo, "respaldo_previo": pre,
                      "schema_version_db": v_r}, ensure_ascii=False))
    return 0


# --------------------------------------------------------------------------- al-iniciar

AL_INICIAR_BUDGET = 20.0      # s desde el inicio: pasado esto no se empieza otro paso (timeout de la entrada: 60)
AL_INICIAR_WINDOW = 3.0       # s de reintento compartidos por todos los exclusivos de una corrida
AL_INICIAR_MAX = 4000         # unidades UTF-16 de la salida (tope de la plataforma por salida: 10,000, R1)
AL_INICIAR_HEADER = "\n> **Aviso de migración de Neb (no es una parte del arranque):** "
AL_INICIAR_TAIL = " … (`neb-migrate.py status` da el detalle)."
# Va al principio del aviso (no junto a una sección) y nombra su objeto: lo pendiente que se reintenta solo no entra.
AL_INICIAR_TELL = ("Dile al dev, en una o dos líneas al cierre de tu primera respuesta y una sola vez por "
                   "conversación, los problemas, lo aplicado y lo que no corre solo de este aviso; lo que se reintenta "
                   "solo, únicamente si pregunta por la migración.")
# El encargo: la instrucción va antes de la lista de pasos, para que el recorte (que acorta la lista) nunca la toque.
# %s del paso 3: si este inicio de sesión corrió la migración, otra corrida la está corriendo, o no corrió.
AL_INICIAR_ASK = (
    "Hay pasos de la migración guiada de Neb que piden al dev (no dejan con qué deshacerlos). Si hay una persona "
    "presente, al cierre de tu primera respuesta y una sola vez por conversación, sigue en esta misma sesión los "
    "pasos %s de `%s`, con `NEB_SRC=%s`: un solo menú con "
    "«Aplicarlo», «No aplicarlo» y «Después». No ofrezcas abrir otra sesión. Sin herramienta de preguntas, díselo "
    "en una línea: los pasos quedan pendientes. Los pasos: ")
AL_INICIAR_PASO3 = {
    "corrio": "1, 2, 4 y 5 (el 3 ya lo corrió el inicio de sesión)",
    "otra": "1, 2, 4 y 5 (el 3 lo está corriendo otra sesión que inicia)",
    "no": "1 a 5 (este inicio de sesión no corrió la migración: el 3 también)",
}
AL_INICIAR_PEND = ("Quedan para el siguiente inicio de sesión (o `/neb:migrate`), sin nada que el dev deba hacer "
                   "(se reintentan solos): ")


def _u16(s):
    return len(s.encode("utf-16-le")) // 2


def _sh_quote(s):
    """`s` entre comillas simples para bash (una ruta con espacios no parte la asignación de NEB_SRC)."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


# --------------------------------------------------------------------------- requisitos del intérprete (7.6.0)
# El Python que corre los hooks (el primero que responde a `python … || python3 …` de hooks.json) se compara con
# lo que neb pide. Si no alcanza, el aviso de al-iniciar encarga a Claude ofrecer instalar uno que sí alcance:
# con winget en Windows (un menú; nada se descarga sin «Instalarlo»), una línea con el comando fuera de Windows.

PYTHON_MIN = (3, 8, 0)                       # las cuatro comprobaciones del aporte por PR (CONTRIBUTING.md)
SQLITE_MIN = _migrations.DROP_COLUMN_SQLITE  # el paso 2 de 7.0.0 sobre una base con el esquema de equipo
PY_WINGET_ID = "Python.Python.3.14"          # 3.12 ya no publica instaladores (winget se quedó en 3.12.10)
PY_WINGET_VERSION = "3.14"
PY_WINGET_SIZE = "unos 33 MB"                # python-3.14.10-amd64.exe: 33,498,520 bytes (python.org, 2026-11-25)
REQ_FILE = ".neb-requisitos.json"            # «No volver a ofrecer»: junto a .neb-migrate.lock (carpeta de datos)


def _ver(t):
    return ".".join(str(n) for n in t)


def _winget_alias():
    """True si existe el alias de ejecución de winget (`%LOCALAPPDATA%\\Microsoft\\WindowsApps\\winget.exe`). Antes de
    Python 3.8, os.stat no resuelve ese tipo de enlace y shutil.which no lo encuentra; lexists sí lo ve (3.7.9,
    2026-11-25). Quien corre winget es el Bash de Claude, no este intérprete."""
    base = os.environ.get("LOCALAPPDATA")
    return bool(base) and os.path.lexists(os.path.join(base, "Microsoft", "WindowsApps", "winget.exe"))


def _requisitos(py=None, sqlite=None, plataforma=None, which=None, exe=None, alias=None):
    """Los requisitos que este intérprete no cumple, o None si cumple todos. Los argumentos son para las pruebas:
    por omisión, sys.version_info, _migrations.SQLITE_VERSION, sys.platform, shutil.which, sys.executable y
    _winget_alias."""
    py = tuple((py if py is not None else sys.version_info)[:3])
    sqlite = tuple((sqlite if sqlite is not None else _migrations.SQLITE_VERSION)[:3])
    plataforma = plataforma if plataforma is not None else sys.platform
    exe = exe if exe is not None else (sys.executable or "python")
    motivos = []
    if py < PYTHON_MIN:
        motivos.append("es Python %s, anterior a %s, que piden las cuatro comprobaciones con que se aporta a neb "
                       "por pull request (`CONTRIBUTING.md`)" % (_ver(py), _ver(PYTHON_MIN)))
    if sqlite < SQLITE_MIN:
        motivos.append("trae SQLite %s, anterior a %s, que pide el paso 2 de neb 7.0.0 (`DROP COLUMN`) sobre una "
                       "base de antes de 7.0.0; el resto de neb funciona desde SQLite 3.24"
                       % (_ver(sqlite), _ver(SQLITE_MIN)))
    if not motivos:
        return None
    winget = False
    if plataforma == "win32":
        winget = bool((which or shutil.which)("winget")) or bool((alias or _winget_alias)())
    return {"motivos": motivos, "exe": exe, "py": _ver(py), "sqlite": _ver(sqlite), "plataforma": plataforma,
            "winget": winget}


def _req_path(home):
    """En la carpeta de datos, junto al candado (desde 8.0.0; hasta 7.6.x, en ~/.claude: lo muda
    8.0.0:mover-requisitos)."""
    return os.path.join(os.path.dirname(_guided.lock_path(_machine.Ctx(home))), REQ_FILE)


def _legacy_req_path(home):
    return os.path.join(neb_paths.legacy_dir(home), REQ_FILE)


def _req_folder_ok(home):
    """True si `requisitos --no-ofrecer` puede guardar ahí su registro: la carpeta de datos existe y no es un
    enlace, o todavía no existe (no_ofrecer la crea; al-iniciar calcula la oferta antes de crearla con el
    candado, y la primera sesión con 8.0.0 puede no tenerla aún)."""
    folder = os.path.dirname(_req_path(home))
    if _machine.is_link(folder):
        return False
    return os.path.isdir(folder) or not os.path.lexists(folder)


def _req_key(r):
    return {"python": r["exe"], "py": r["py"], "sqlite": r["sqlite"]}


def _req_read(home):
    """La lista de «No volver a ofrecer»; [] si no existe o no se puede leer (un archivo ilegible cuenta como
    ningún registro: la oferta sale, y `requisitos --no-ofrecer` lo reescribe). Sin el archivo de la carpeta de
    datos lee el de ~/.claude (7.6.x), que muda 8.0.0:mover-requisitos: al-iniciar calcula la oferta antes de la
    mudanza."""
    path = _req_path(home)
    if not os.path.isfile(path) and os.path.isfile(_legacy_req_path(home)):
        path = _legacy_req_path(home)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("no_ofrecer") if isinstance(data, dict) else None
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def _req_text(home, r=None, **kw):
    """El encargo de la oferta para al-iniciar, o '' si el intérprete cumple o el dev pidió no volver a verla
    para este intérprete y estas versiones."""
    r = r if r is not None else _requisitos(**kw)
    if r is None or _req_key(r) in _req_read(home):
        return ""
    exe = r["exe"].replace("\\", "/")
    root = ROOT.replace("\\", "/")
    folder = _req_folder_ok(home)
    no_ofrecer = "%s %s requisitos --no-ofrecer" % (_sh_quote(exe), _sh_quote(root + "/bootstrap/neb-migrate.py"))
    head = ("El Python que corre los hooks de Neb (`%s`) no alcanza lo que neb pide: %s."
            % (exe, "; ".join(r["motivos"])))
    restart = ("Rige al reiniciar Claude Code (cerrar todas sus ventanas); si ya se instaló y este aviso sigue tras "
               "reiniciar, %s." % ("un Python de todo el equipo va antes en el PATH" if r["plataforma"] == "win32"
                                   else "otro Python va antes en el PATH, o el instalado tampoco alcanza"))
    if r["plataforma"] == "win32" and r["winget"]:
        # InstallLauncherAllUsers=0: el lanzador `py` para todo el equipo pediría elevación en un alcance de usuario.
        install = ("winget install --id %s --exact --source winget --scope user --custom \"InstallLauncherAllUsers=0\" "
                   "--accept-package-agreements --accept-source-agreements --disable-interactivity" % PY_WINGET_ID)
        options = "«Instalarlo (Recomendado)», «Todavía no»" + (" y «No volver a ofrecer»" if folder else "")
        text = ("%s Si hay una persona presente, al cierre de tu primera respuesta y una sola vez por conversación "
                "(después del menú de los pasos guiados, si lo hay), ofrécele un menú con %s. «Instalarlo»: Python "
                "%s de python.org con winget (paquete `%s`), %s, solo para su usuario (alcance de usuario, sin el "
                "lanzador `py` para todo el equipo); elegirlo acepta la licencia PSF-2.0 de Python y los términos del "
                "origen `winget`. "
                "%s Con «Instalarlo», corre en Bash, tal cual, `%s`, dile al dev lo que respondió winget y pídele "
                "reiniciar Claude Code." % (head, options, PY_WINGET_VERSION, PY_WINGET_ID, PY_WINGET_SIZE,
                                            restart, install))
        if folder:
            text += " Con «No volver a ofrecer», corre en Bash, tal cual, `%s`." % no_ofrecer
        return text + (" Sin herramienta de preguntas, díselo en una línea con el comando de instalación y no "
                       "instales.")
    if r["plataforma"] == "win32":
        how = ("instalar Python %s (o 3.12 o superior) desde https://www.python.org/downloads/, marcando «Add "
               "python.exe to PATH»" % PY_WINGET_VERSION)
    elif r["plataforma"] == "darwin":
        how = "`brew install python@%s`" % PY_WINGET_VERSION
    else:
        how = ("un Python %s de https://www.python.org/downloads/ o de un gestor de versiones; el del gestor de "
               "paquetes de la distribución (por ejemplo `sudo apt install python3`) sirve solo si su versión alcanza "
               "(Ubuntu 20.04 trae SQLite 3.31.1)" % PY_WINGET_VERSION)
    text = ("%s Díselo al dev en una línea al cierre de tu primera respuesta, una sola vez por conversación, con el "
            "remedio: %s. %s No corras el comando." % (head, how, restart))
    if folder:
        text += " Si el dev pide no volver a verlo, corre en Bash, tal cual, `%s`." % no_ofrecer
    return text


def no_ofrecer(home, r=None):
    """`requisitos --no-ofrecer`: guarda que el dev no quiere volver a ver la oferta para este intérprete y estas
    versiones (constancia de lo que decidió). Si cambia el intérprete o una versión, la oferta vuelve."""
    r = r if r is not None else _requisitos()
    if r is None:
        print("este Python cumple lo que neb pide: no hay oferta que callar")
        return 0
    path = _req_path(home)
    try:
        neb_paths.ensure_dir(os.path.dirname(path))
    except (OSError, ValueError) as e:
        print("no se pudo usar la carpeta de datos (%s): %s; la oferta seguirá saliendo"
              % (os.path.dirname(path), e), file=sys.stderr)
        return 1
    if _machine.is_link(path):
        print("%s es un enlace: no se escribe a través de él y la oferta seguirá saliendo" % path, file=sys.stderr)
        return 1
    rows = _req_read(home)
    if _req_key(r) not in rows:
        rows.append(_req_key(r))
    tmp = None
    try:
        # Nombre nuevo y exclusivo en la misma carpeta (mkstemp no sigue un enlace plantado con el nombre fijo).
        fd, tmp = tempfile.mkstemp(prefix=REQ_FILE + ".", suffix=".tmp", dir=os.path.dirname(path))
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            json.dump({"no_ofrecer": rows}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        print("no se pudo guardar %s: %s" % (path, e), file=sys.stderr)
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return 1
    print("listo: la oferta no vuelve a salir para %s (Python %s, SQLite %s)" % (r["exe"], r["py"], r["sqlite"]))
    return 0


def _load_bootstrap():
    """El módulo del arranque de este mismo árbol: _relax_axis_step, _db_notice, _project_opts_out,
    is_internal_subsession, resolve_neb_root y _emit."""
    import importlib.util
    path = os.path.join(ROOT, "bootstrap", "neb-bootstrap-context.py")
    spec = importlib.util.spec_from_file_location("neb_bootstrap_context_own", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def al_iniciar(home):
    """La entrada de migración de SessionStart (desde 7.5.0; hooks/hooks.json, matchers startup y clear).
    Con el candado entre corridas: baja la mínima del paso 3 de 7.3.0, corre los pasos de base y los guiados
    que dejan con qué deshacerlos, en el orden de apply --guiados, con presupuesto y ventana de exclusivos.
    Sin el candado (otra corrida lo tiene) no corre nada. En los dos casos emite, en solo lectura, el aviso de
    base que un árbol no opera o de paso detenido y el encargo del menú para lo que pide al dev. Desde 7.6.0,
    también el encargo de la oferta de instalar Python si el intérprete no alcanza lo que neb pide (se calcula
    antes de la corrida y va también en el aviso de falla). Devuelve siempre 0: el envoltorio
    `python … || python3 …` de hooks.json volvería a correrla con otro código."""
    started = time.monotonic()
    try:
        bc = _load_bootstrap()
    except Exception as e:  # noqa: BLE001 — sin el arranque no se sabe si el proyecto optó por no recibir nada
        print(f"[neb-migrate] al-iniciar: no se pudo cargar el arranque ({type(e).__name__})", file=sys.stderr)
        return 0
    req = ""
    try:
        if bc.is_internal_subsession() or bc._project_opts_out():
            return 0
        try:
            req = _req_text(home)
        except Exception as e:  # noqa: BLE001 — la oferta nunca impide la migración
            print(f"[neb-migrate] al-iniciar: no se pudieron comprobar los requisitos ({type(e).__name__})",
                  file=sys.stderr)
        text = _al_iniciar_run(bc, home, started, req)
    except Exception as e:  # noqa: BLE001 — nunca sale con otro código
        text = (AL_INICIAR_HEADER + "la migración automática de Neb falló al iniciar la sesión (%s). %s "
                "`neb-migrate.py status` da el estado.%s\n" % (type(e).__name__, AL_INICIAR_TELL,
                                                               (" " + req) if req else ""))
    if text:
        try:
            bc._emit(text)
        except Exception:  # noqa: BLE001
            pass
    return 0


def _al_iniciar_run(bc, home, started, req=""):
    report, lock_note = None, None
    held = _take_lock(home)
    if not _blocked(held):
        try:
            bc._relax_axis_step(os.path.join(ROOT, "bootstrap"), home=home)
            _rc, report = _apply_core(home, guiados=True, deadline=started + AL_INICIAR_BUDGET,
                                      window=_guided.ExclusiveWindow(AL_INICIAR_WINDOW), retry=False)
        finally:
            _release(held)
    elif held == -1:
        # Sin carpeta de datos usable tampoco corre /neb:migrate (candado-no-disponible): el remedio es la carpeta.
        folder = os.path.dirname(_guided.lock_path(_machine.Ctx(home)))
        lock_note = ("no se pudo tomar el candado de la migración (.neb-migrate.lock en la carpeta de datos %s: la "
                     "carpeta o el candado es un enlace, o no se pudo crear): no corrió ningún paso; revisa la "
                     "carpeta de datos (NEB_DATA, si la declaraste, o ~/.neb)" % folder)
    neb_home = os.path.abspath(bc.resolve_neb_root(ROOT))
    db_text = bc._db_notice(os.path.join(ROOT, "bootstrap"), neb_home, home=home)
    st = status(home)
    paso3 = "corrio" if report is not None else ("otra" if held is None else "no")
    return _al_iniciar_text(report, db_text, st.get("guiados") or {}, lock_note, paso3=paso3, requisitos=req)


def _al_iniciar_text(report, db_text, guided_status, lock_note=None, paso3="corrio", requisitos=""):
    """El aviso de al-iniciar, o '' si no hay nada que decir. Secciones por prioridad de recorte (_fit): 1 encargo
    del menú y fallos (nunca se quitan; si no caben, se acortan sus listas y luego cada entrada de fallo); 2 aviso
    de base; 3 lo pendiente: lo que se reintenta solo, sin pedir que se le diga al dev; 4 lo aplicado, con el
    `detalle` y el respaldo de cada paso
    guiado (no los respaldos de los pasos de base: esos los dan `status` y `/neb:migrate`). La orden de decírselo
    al dev va una sola vez, al principio, si quedó alguna sección que lo pide. `requisitos` (desde 7.6.0) es el
    encargo de la oferta de instalar Python: prioridad 1 entre el encargo del menú y los fallos, todo en el texto
    fijo (el recorte no lo toca) y con su propia instrucción (no pide la orden de decírselo)."""
    rows = guided_status.get("pendientes", [])
    dev = [r for r in rows if r.get("clase") == "dev" and not r.get("error")]
    broken = [r for r in rows if r.get("error")]
    dev_ids = {r["id"] for r in dev}
    g = (report or {}).get("guiados") or {}
    sections = []                                     # dicts: prio, pre, items, post, tell
    fails = []                                        # los de toda la corrida primero: el recorte quita del final
    if lock_note:
        fails.append(lock_note)
    if report and report.get("motivo") and not (report["motivo"] == "base-incompatible" and db_text):
        fails.append("la base no abrió: %s" % (report.get("detalle") or report["motivo"]))
    if g.get("error"):
        fails.append(g["error"])
    if guided_status.get("error_omitidos"):
        fails.append("no se pudieron leer los pasos que el dev omitió (%s): no se ofrece el menú"
                     % guided_status["error_omitidos"])
    for f in g.get("fallos", []):
        fails.append("`%s` (%s) falló: %s" % (f["id"], f["titulo"], f["detalle"]))
    for e in g.get("errores_de_carga", []):
        fails.append("la migración `%s` no carga: %s" % (e["archivo"], e["motivo"]))
    for m in g.get("manual", []):
        fails.append("`%s` (%s) pide algo a mano: %s" % (m["id"], m["titulo"], m["detalle"]))
    if fails:
        sections.append({"prio": 1, "ord": 1, "pre": "Problemas de la migración de Neb al iniciar la sesión: ",
                         "items": fails, "post": ".", "tell": True})
    if (dev or broken) and not guided_status.get("error_omitidos"):
        ids = ["`%s` (%s)" % (r["id"], r["titulo"]) for r in dev]
        ids += ["`%s` (%s; su detección falla: solo «No aplicarlo» o «Después»)" % (r["id"], r["titulo"])
                for r in broken]
        root = ROOT.replace("\\", "/")
        sections.append({"prio": 1, "ord": 0, "pre": AL_INICIAR_ASK % (AL_INICIAR_PASO3[paso3],
                                                                       root + "/commands/migrate.md", _sh_quote(root)),
                         "items": ids, "post": ".", "tell": False})
    if requisitos:
        sections.append({"prio": 1, "ord": 0.5, "pre": requisitos, "items": [], "post": "", "tell": False})
    if db_text:
        sections.append({"prio": 2, "pre": db_text.strip(), "items": [], "post": "", "tell": False})
    pend = ["`%s` (%s): %s" % (p["id"], p["titulo"], p["detalle"])
            for p in g.get("pendientes", []) if p["id"] not in dev_ids]
    if pend:
        sections.append({"prio": 3, "pre": AL_INICIAR_PEND, "items": pend, "post": ".", "tell": False})
    done = ["`%s` (%s)%s%s" % (a["id"], a["titulo"], ": %s" % a["detalle"] if a.get("detalle") else "",
                               ", respaldo `%s`" % a["respaldo"] if a.get("respaldo") else "")
            for a in g.get("aplicados", [])]
    if done:
        sections.append({"prio": 4, "pre": "La migración guiada de Neb aplicó al iniciar la sesión: ",
                         "items": done, "post": ".", "tell": True})
    return _fit(sections)


def _fit(sections):
    """Arma la salida en orden de prioridad (dentro de la 1, el encargo antes que los fallos) y la recorta a
    AL_INICIAR_MAX (unidades UTF-16): quita las secciones de prioridad 4, 3 y 2, en ese orden; las de prioridad 1
    nunca se quitan: si aun así no cabe, acorta sus listas por el final («y N más»), la más larga primero; después,
    acorta la entrada más larga que quede (un `detalle` enorme), nunca el texto fijo de una sección. Como último
    recurso corta el final del texto, que es la lista de fallos: el encargo va antes."""
    if not sections:
        return ""
    keep = [dict(s, items=list(s["items"]), dropped=0)
            for s in sorted(sections, key=lambda s: (s["prio"], s.get("ord", 0)))]
    cut = [False]

    def render(sec):
        items = list(sec["items"])
        if sec["dropped"]:
            items.append("y %d más" % sec["dropped"])
        return sec["pre"] + "; ".join(items) + sec["post"]

    def build():
        body = " ".join(render(sec) for sec in keep)
        if any(sec["tell"] for sec in keep):
            body = AL_INICIAR_TELL + " " + body
        return AL_INICIAR_HEADER + body + (AL_INICIAR_TAIL if cut[0] else "") + "\n"
    text = build()
    while _u16(text) > AL_INICIAR_MAX and len(keep) > 1 and keep[-1]["prio"] > 1:
        keep.pop()
        cut[0] = True
        text = build()
    while _u16(text) > AL_INICIAR_MAX:
        longest = max(keep, key=lambda sec: len(sec["items"]))
        if len(longest["items"]) <= 1:
            break
        longest["items"].pop()
        longest["dropped"] += 1
        cut[0] = True
        text = build()
    while _u16(text) > AL_INICIAR_MAX:
        sec = max(keep, key=lambda x: max((len(i) for i in x["items"]), default=0))
        if not sec["items"]:
            break
        k = max(range(len(sec["items"])), key=lambda j: len(sec["items"][j]))
        item = sec["items"][k]
        if len(item) <= 120:
            break
        excess = _u16(text) - AL_INICIAR_MAX
        sec["items"][k] = item[:max(120, len(item) - excess - 2)].rstrip() + "…"
        cut[0] = True
        text = build()
    if _u16(text) > AL_INICIAR_MAX:
        room = AL_INICIAR_MAX - _u16(AL_INICIAR_HEADER + AL_INICIAR_TAIL + "\n")
        body = text[len(AL_INICIAR_HEADER):-1]
        if body.endswith(AL_INICIAR_TAIL):
            body = body[:-len(AL_INICIAR_TAIL)]
        while body and _u16(body) > room:
            body = body[:-1]
        text = AL_INICIAR_HEADER + body.rstrip() + AL_INICIAR_TAIL + "\n"
    return text


# --------------------------------------------------------------------------- schema

def schema():
    tmp = tempfile.mkdtemp(prefix="neb-schema-")
    try:
        con = _db_shared._connect(os.path.join(tmp, "neb.db"))
        if con is None:
            print("no se pudo construir el esquema", file=sys.stderr)
            return 1
        try:
            rows = con.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL "
                               "AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 "
                               "WHEN 'index' THEN 1 ELSE 2 END, name").fetchall()
        finally:
            con.close()
        print(f"-- esquema vigente de neb.db: versión de esquema {_migrations.code_version()} "
              f"(neb {_migrations.neb_version()})")
        for _t, _n, sql in rows:
            print(sql.strip() + ";\n")
        print("-- fuera de los pasos de base (la crea `skip` con IF NOT EXISTS; su forma no cambia: un cambio "
              "entraría como paso de base):")
        print(_guided.SKIP_DDL + ";")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Versión de esquema de neb.db.")
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true")
    ap = sub.add_parser("apply")
    ap.add_argument("--guiados", action="store_true")
    ap.add_argument("--include", nargs="+", default=[], metavar="ID")
    ap.add_argument("--sin-exclusivos", action="store_true")
    sk = sub.add_parser("skip")
    sk.add_argument("id")
    rs = sub.add_parser("restore")
    rs.add_argument("archivo")
    rs.add_argument("--remigrar", action="store_true")
    sub.add_parser("schema")
    sub.add_parser("al-iniciar")
    rq = sub.add_parser("requisitos")
    rq.add_argument("--no-ofrecer", action="store_true", required=True)
    args = p.parse_args(argv)
    home = _home()
    if args.cmd == "al-iniciar":
        return al_iniciar(home)
    if args.cmd == "requisitos":
        return no_ofrecer(home)
    if args.cmd == "status":
        s = status(home)
        if args.json:
            print(json.dumps(s, ensure_ascii=False, indent=2))
        else:
            _print_status(s)
        return 0
    if args.cmd == "apply":
        return apply(home, args.include, args.sin_exclusivos, args.guiados)
    if args.cmd == "skip":
        return skip(home, args.id)
    if args.cmd == "restore":
        return restore(home, args.archivo, args.remigrar)
    return schema()


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:                       # defensivo, igual que el resto de bootstrap
        print(f"[neb-migrate] ERROR inesperado: {e}", file=sys.stderr)
        # al-iniciar sale siempre con 0: con otro código, el `|| python3` de hooks.json la volvería a correr.
        sys.exit(0 if sys.argv[1:2] == ["al-iniciar"] else 1)
