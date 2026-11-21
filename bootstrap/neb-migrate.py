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
  skip <id>                  guarda el «no» del dev a un paso guiado: sale de lo pendiente hasta que se pida
                             con apply --include. Sin base, o con una base más nueva que no tiene la tabla,
                             se niega.
  restore <archivo> [--remigrar]
                             vuelve la base al contenido de un respaldo de neb-backups/ (neb.pre-paso-*.db
                             o neb.pre-restore.*.db). Antes respalda la base actual. Se niega si el código
                             que lo corre no podría operar la base restaurada, o si la siguiente conexión
                             volvería a aplicar los pasos que el respaldo no tiene (--remigrar lo permite).
                             Volver atrás: primero regresar plugin y clon a la versión anterior.
  schema                     imprime el esquema vigente (esquema inicial + todos los pasos de base).

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
from datetime import datetime, timezone

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "lib")
sys.path.insert(0, _LIB)

import _db_shared    # noqa: E402
import _guided       # noqa: E402
import _machine      # noqa: E402
import _migrations   # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_BACKUP_NAME_RE = re.compile(r"^neb\.pre-(paso-(\d+)|restore)\.[0-9TZ]+\.db$")


def _home():
    return os.path.expanduser("~")


def _readable_with_work(path):
    con = _migrations.open_readonly(path)
    if con is None:
        return False
    try:
        con.execute("SELECT count(*) FROM work").fetchone()
        return True
    except sqlite3.Error:
        return False
    finally:
        con.close()


def _existing_db(home):
    """Ruta de la base si existe alguna, o None. Solo lectura: la misma preferencia que resolve_db_path
    (neb.db si tiene `work`, si no neb-logbook.db), sin abrir nada en lectura-escritura."""
    base = os.path.join(home, ".claude")
    present = []
    for name in (_db_shared.NEB_DB_NAME, _db_shared.LEGACY_DB_NAME):
        p = os.path.join(base, name)
        if os.path.isfile(p) and os.path.getsize(p) > 0:
            present.append(p)
    for p in present:
        if _readable_with_work(p):
            return p
    return present[0] if present else None          # la que existe, aunque no se pueda leer


# --------------------------------------------------------------------------- status

def status(home):
    c = _migrations.code_version()
    out = {"neb_version": _migrations.neb_version(), "schema_version_code": c, "db": None,
           "schema_version_db": None, "min_compatible_db": None, "estado": "sin-base",
           "pasos_detenidos": [], "respaldos": [], "guiados": None}
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
              + (" · pide cerrar las demás sesiones" if r["exclusivo"] else ""))
    for r in (g or {}).get("omitidos", []):
        print(f"paso guiado omitido por el dev: {r['id']} ({r['titulo']})")
    for e in (g or {}).get("errores_de_carga", []):
        print(f"migración guiada que no carga: {e['archivo']}: {e['motivo']}")
    if (g or {}).get("error_omitidos"):
        print(f"no se pudieron leer los pasos omitidos: {g['error_omitidos']}")


def _print_status(s):
    print(f"neb {s['neb_version']} · versión de esquema del código: {s['schema_version_code']}")
    if s["db"] is None:
        print("base: " + _ESTADOS["sin-base"])
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

def apply(home, include=(), sin_exclusivos=False, guiados=False):
    """Pasos de base y reparaciones (como la captura) si hay base; sin base no la crea (la crea la primera
    captura, y un paso guiado puede necesitar ver la máquina sin ella). Luego, solo con guiados (lo pide
    /neb:migrate), los pasos guiados: reintentar un paso de base no corre la migración guiada."""
    guiados = bool(guiados or include or sin_exclusivos)
    db = _db_shared.resolve_db_path(home)
    v, skips, skips_error = None, set(), None
    if _existing_db(home) is not None:
        try:
            con = _db_shared._connect(db, retry=True)
        except _db_shared.DbUnavailable as e:
            print(json.dumps(e.to_dict(), ensure_ascii=False))
            return 1
        if con is None:
            print(json.dumps({"ok": False, "motivo": "sin-conexion",
                              "detalle": "no se pudo abrir la base (candado ocupado o error de SQLite)",
                              "accion": "reintenta en unos segundos"}, ensure_ascii=False))
            return 1
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
        guided = _apply_guided(home, db, skips, include, sin_exclusivos)
    s = status(home)
    c = _migrations.code_version()
    # Un paso con `espera` que no corrió (candado ocupado) no deja fila de error: ok exige también V >= C.
    # Una migración guiada que no carga tampoco es ok: sus pasos nunca correrían, en silencio.
    ok = not s["pasos_detenidos"] and (v is None or v >= c)
    if guided is not None:
        ok = ok and not (guided["error"] or guided["fallos"] or guided["no_encontrados"]
                         or guided["errores_de_carga"])
    print(json.dumps({"ok": ok, "base": s["db"], "schema_version_db": v, "schema_version_code": c,
                      "pasos_detenidos": s["pasos_detenidos"], "guiados": guided}, ensure_ascii=False))
    return 0 if ok else 1


def _guided_out():
    return {"aplicados": [], "pendientes": [], "manual": [], "fallos": [], "no_encontrados": [],
            "errores_de_carga": [], "omision_sin_borrar": [], "error": None}


def _apply_guided(home, db, skips, include, sin_exclusivos=False):
    """Corre los pasos guiados pendientes que dejan con qué deshacerlos y los pedidos con --include. Un paso
    omitido por el dev no corre salvo que se incluya; si corre bien, su «no» se borra. Con sin_exclusivos, los
    pasos exclusivos quedan pendientes (el dev eligió «Después»)."""
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
            if step.exclusivo and sin_exclusivos:
                r = {"estado": "pendiente", "respaldo": None, "detalle": "exclusivo: el dev lo dejó para después"}
                try:
                    if not _guided.detect(ctx, step):
                        r = {"estado": "sin-cambio", "respaldo": None, "detalle": ""}
                except (Exception, SystemExit) as e:  # noqa: BLE001
                    r = {"estado": "fallo", "respaldo": None, "detalle": "detección: " + _guided.error_text(step, e)}
            else:
                r = _guided.run(ctx, step, allow_dev=included)
            bucket = {"aplicado": "aplicados", "pendiente": "pendientes", "manual": "manual",
                      "fallo": "fallos"}.get(r["estado"])
            if bucket:
                out[bucket].append({"id": key, "titulo": step.titulo, "detalle": r["detalle"],
                                    "respaldo": r["respaldo"]})
            if r["estado"] in ("aplicado", "sin-cambio") and key in skips:
                unskip.append(key)
    if unskip:
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
    migrations, _errors = _guided.load(ROOT)
    if _guided.find(migrations, key)[1] is None:
        return _refuse("paso-desconocido", f"no hay un paso guiado {key}",
                       "usa un id <versión>:<paso> de `neb-migrate.py status`")
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
    db = _db_shared.resolve_db_path(home)
    folder = _migrations.backup_dir(db)
    name = os.path.basename(archivo)
    m = _BACKUP_NAME_RE.match(name)
    if not m:
        return _refuse("respaldo-no-valido", f"{name} no es un respaldo de neb-backups/",
                       "usa un neb.pre-paso-*.db o neb.pre-restore.*.db de `neb-migrate.py status`")
    if not os.path.isfile(archivo) or _is_link(archivo) or _is_link(folder):
        return _refuse("respaldo-no-valido", "el archivo no existe o hay un enlace en la ruta",
                       "usa la ruta que muestra `neb-migrate.py status`")
    # neb-backups/ y el archivo no pueden ser enlace (arriba); un enlace en una carpeta superior (.claude
    # movido con junction, unidad subst) es del dev y no impide restaurar: se comparan rutas reales.
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
        for p in glob.glob(os.path.join(folder, _migrations.RESTORE_BACKUP_GLOB)):
            if os.path.normcase(os.path.abspath(p)) not in keep:
                for f in (p, p + "-wal", p + "-shm"):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
    print(json.dumps({"ok": True, "restaurada_desde": archivo, "respaldo_previo": pre,
                      "schema_version_db": v_r}, ensure_ascii=False))
    return 0


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
    args = p.parse_args(argv)
    home = _home()
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
        sys.exit(1)
