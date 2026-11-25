#!/usr/bin/env python3
"""
migrate-neb-db.py — cambia el nombre de la bitácora de ~/.claude/neb-logbook.db (anterior a neb 7.0.0)
a ~/.claude/neb.db. Desde 7.0.0, neb no captura ni abre la base mientras siga con el nombre anterior.

Lo invoca el paso guiado 7.0.0:renombrar-base (migrations/7.0.0.py), que corre solo al iniciar sesión
(`neb-migrate.py al-iniciar`, desde 7.5.0) o con `/neb:migrate`; también se puede correr a mano. Usa el módulo sqlite3 de Python porque el binario `sqlite3` no está en el PATH de Windows.
No migra columnas ni llama a _connect: la primera conexión de neb 7.0.0 sobre neb.db aplica los pasos de
base (el paso 2 retira el esquema de equipo, con su propio respaldo).

Corre solo cuando ninguna otra sesión ni proceso tiene la base abierta: si está ocupada, no cambia el nombre
y se vuelve a correr después (desde 7.4.0 no se pide al dev cerrar sesiones).

Qué hace, en este orden:
  1. Solo acepta un neb.db ausente o de 0 bytes. Ante cualquier otro neb.db (usable, sin tabla `work`,
     que no es una base o bloqueado) aborta con su tamaño, sin tocar nada: hay que moverlo fuera de
     ~/.claude y volver a correr. Si ya existen neb.db-wal, neb.db-shm o neb.db-journal, también aborta.
  2. Abre neb-logbook.db sin espera y comprueba que tiene la tabla `work`. Si no es una base usable (no
     es SQLite, está dañada o le falta la tabla `work`), aborta sin tocar nada: hay que moverla fuera de
     ~/.claude y neb creará un neb.db nuevo.
  3. Si está en WAL: wal_checkpoint(TRUNCATE), que integra el -wal (también uno que dejó un lector), y
     journal_mode=DELETE, que solo se logra sin otra conexión abierta; si no devuelve `delete`, no sigue.
  4. Una transacción de lectura, retenida mientras saca el respaldo: nadie confirma escrituras en ese
     tiempo (la API de backup no copia desde una conexión con una transacción de escritura abierta).
     Respaldo con la API de backup en neb-logbook.db.bak-<fecha>, en journal_mode=DELETE (un solo
     archivo) y verificado con integrity_check. Después, BEGIN EXCLUSIVE y ROLLBACK: nadie más tiene un
     candado sobre la base en ese momento.
  5. Cierra su conexión y, justo antes del cambio de nombre, comprueba otra vez que no existen
     neb-logbook.db-wal/-shm/-journal ni neb.db-wal/-shm/-journal: si aparece alguno, otra conexión abrió
     la base; borra el respaldo de este intento y no cambia el nombre.
  6. os.replace(neb-logbook.db, neb.db); si falla, el nombre no cambió y se vuelve a correr después.
     Verifica neb.db con _probe_db. Solo si es de verdad inservible (ausente, vacío, sin tabla `work` o no
     es una base) devuelve el archivo a su nombre anterior; si otra conexión lo tiene bloqueado, lo deja en
     su lugar con un aviso.
  7. Comprueba que neb-logbook.db y sus archivos auxiliares no reaparecieron. Si reaparecieron, una sesión
     con una versión anterior de neb abrió la base por su nombre viejo después del cambio, y el aviso dice
     si la captura escribió ahí (esas capturas no están en neb.db).
  8. Con neb.db verificado, lo devuelve a journal_mode=WAL, su modo normal. Si no queda en WAL, avisa sin
     abortar: la base ya está migrada y la primera conexión de neb lo pasa a WAL.

--dry-run revisa solo con os.path (existencia, tamaño y sidecars): no abre ninguna base ni escribe nada.

ROLLBACK (volver a 6.x):
  1. Mover ~/.claude/neb.db fuera de ~/.claude (una 6.x lo seguiría usando, aunque ya no tenga las
     columnas que 6.x espera).
  2. Restaurar el respaldo: copiar ~/.claude/neb-logbook.db.bak-<fecha> a ~/.claude/neb-logbook.db.
  3. Volver el clon de neb y el plugin a la versión anterior, los dos juntos.

Uso:
  py bootstrap/migrate-neb-db.py                 # migra ~/.claude
  py bootstrap/migrate-neb-db.py --dry-run       # revisa sin abrir ni escribir nada
  py bootstrap/migrate-neb-db.py --home <dir>    # opera sobre <dir>/.claude (pruebas)
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "lib")
sys.path.insert(0, _LIB)
from _db_shared import _probe_db, NEB_DB_NAME, LEGACY_DB_NAME  # noqa: E402

SIDECARS = ("-wal", "-shm", "-journal")

ROLLBACK_HELP = (
    "Rollback: mueve neb.db fuera de ~/.claude, copia el respaldo neb-logbook.db.bak-<fecha> a "
    "neb-logbook.db y vuelve el clon de neb y el plugin a la versión anterior.")

# Códigos de rename(): ok (cambió el nombre), nada (no había qué hacer), ocupada (otra conexión: se vuelve a
# correr), aborto (el dev debe hacer algo antes) y error (falló algo del propio migrador).
EXIT = {"ok": 0, "nada": 0, "ocupada": 1, "aborto": 1, "error": 1}


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _size(path):
    try:
        return os.path.getsize(path) if os.path.isfile(path) else None
    except OSError:
        return None


def _sidecars(*paths):
    return [p + s for p in paths for s in SIDECARS if os.path.exists(p + s)]


def _remove_quiet(path):
    try:
        os.remove(path)
    except (OSError, TypeError):
        pass


def _result(codigo, mensaje, respaldo=None, aviso=None, escribio=False):
    return {"codigo": codigo, "mensaje": mensaje, "respaldo": respaldo, "aviso": aviso, "escribio": escribio}


def _precheck(base, legacy, target):
    """Revisión solo con os.path. Devuelve (código, mensaje): ('ok', None) si se puede migrar; 'nada' si no
    hay nada que hacer; 'aborto' si hay que abortar."""
    legacy_size = _size(legacy)
    target_size = _size(target)
    if legacy_size is None:
        if target_size:
            return "nada", f"ya migrado: existe {target} y no hay {LEGACY_DB_NAME}. Nada que hacer."
        return "nada", f"no hay {LEGACY_DB_NAME} que migrar en {base}. Nada que hacer."
    if legacy_size == 0:
        return "nada", f"{legacy} está vacío (0 bytes): no hay datos que migrar. No se tocó nada."
    if target_size:
        return "aborto", (f"ya existe {target} ({target_size} bytes) y el migrador no lo pisa. Si es la base que "
                          f"quieres conservar, no hay nada que migrar: neb usa ese {NEB_DB_NAME} y {legacy} queda "
                          f"sin uso. Si quieres migrar {legacy}, mueve fuera de {base} ese {NEB_DB_NAME} y vuelve "
                          "a correr el migrador. No se tocó nada.")
    found = _sidecars(target)
    if found:
        return "aborto", (f"existen archivos auxiliares de {NEB_DB_NAME} ({', '.join(found)}): muévelos fuera "
                          f"de {base} y vuelve a correr el migrador. No se tocó nada.")
    return "ok", None


def _busy(e):
    msg = str(e).lower()
    return "locked" in msg or "busy" in msg


def _backup(con, dst_path):
    """Respaldo con Connection.backup() en un archivo nuevo, en journal_mode=DELETE (un solo archivo: lo
    exige la comprobación del respaldo declarado de un paso guiado) y verificado con integrity_check."""
    if os.path.exists(dst_path):
        raise sqlite3.DatabaseError(f"{dst_path} ya existe")
    dst = sqlite3.connect(dst_path)
    try:
        con.backup(dst)
        mode = dst.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        if str(mode).lower() != "delete":
            raise sqlite3.DatabaseError(f"el respaldo quedó en journal_mode={mode}")
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise sqlite3.DatabaseError(f"integrity_check del respaldo: {ok}")
    finally:
        dst.close()
    try:
        os.chmod(dst_path, 0o600)
    except OSError:
        pass


def _back_to_wal(path):
    """Deja la base vieja otra vez en WAL tras un aborto posterior al cambio a DELETE (sin espera; si otra
    conexión lo impide, la versión anterior de neb la regresa a WAL al abrirla)."""
    try:
        c = sqlite3.connect(path, timeout=0)
        try:
            c.execute("PRAGMA journal_mode=WAL")
        finally:
            c.close()
    except sqlite3.Error:
        pass


def _reappeared(legacy):
    """(aviso, ¿la captura escribió ahí?) si neb-logbook.db o sus auxiliares reaparecieron tras el cambio de
    nombre; (None, False) si no."""
    found = [p for p in (legacy,) + tuple(legacy + s for s in SIDECARS) if os.path.exists(p)]
    if not found:
        return None, False
    text = (f"después del cambio de nombre reapareció {', '.join(found)}: una sesión con una versión anterior de "
            "neb abrió la base por su nombre viejo. ")
    if any((_size(p) or 0) > 0 for p in found):
        return text + ("La captura escribió ahí después del cambio de nombre: esas capturas no están en neb.db. "
                       "Revisa el archivo antes de borrarlo; esa sesión puede seguir escribiendo ahí mientras siga "
                       "abierta, y su siguiente sesión, ya actualizada, usa neb.db."), True
    return text + ("Está vacío: la captura no escribió ahí. Se puede borrar cuando esa sesión termine; su "
                   "siguiente sesión, ya actualizada, usa neb.db."), False


def rename(home_dir):
    """Cambia el nombre de la base. No imprime (lo llama un paso guiado cuya salida es JSON): devuelve
    {codigo, mensaje, respaldo, aviso, escribio}, con codigo de EXIT; escribio: una sesión anterior escribió
    en el nombre viejo después del cambio."""
    base = os.path.join(home_dir, ".claude")
    legacy = os.path.join(base, LEGACY_DB_NAME)
    target = os.path.join(base, NEB_DB_NAME)
    code, msg = _precheck(base, legacy, target)
    if code != "ok":
        return _result(code, msg)

    busy_msg = ("otra sesión o proceso la usa: no se cambió el nombre; se vuelve a correr cuando nadie más la "
                "tenga abierta.")
    try:
        con = sqlite3.connect(legacy, timeout=0, isolation_level=None)
    except sqlite3.Error as e:
        return _result("error", f"no se pudo abrir {legacy} ({e}). No se tocó nada.")
    switched = False
    bak = None
    try:
        try:
            con.execute("SELECT count(*) FROM work").fetchone()
            mode = str(con.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        except sqlite3.Error as e:
            if _busy(e):
                return _result("ocupada", f"no se pudo tomar {legacy} ({e}): {busy_msg}")
            return _result("aborto", f"{legacy} no es una base usable de la bitácora ({e}) y no se puede migrar. "
                                     f"Muévelo fuera de {base} (no lo borres sin revisarlo): neb creará un "
                                     f"{NEB_DB_NAME} nuevo. No se tocó nada.")
        if mode == "wal":
            row = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if row is None or row[0] == 1 or row[1] != row[2]:
                return _result("ocupada", f"wal_checkpoint(TRUNCATE) devolvió {row}: {busy_msg}")
            got = con.execute("PRAGMA journal_mode=DELETE").fetchone()
            if got is None or str(got[0]).lower() != "delete":
                return _result("ocupada", f"journal_mode quedó en {got}: otra conexión tiene abierta la base "
                                          f"(sesión de Claude, hook o herramienta como paneldb). {busy_msg}")
            switched = True
        con.execute("BEGIN")
        con.execute("SELECT count(*) FROM work").fetchone()
        bak = f"{legacy}.bak-{_stamp()}"
        try:
            _backup(con, bak)
        except (OSError, sqlite3.Error) as e:
            for f in (bak,) + tuple(bak + s for s in SIDECARS):
                _remove_quiet(f)
            bak = None
            return _result("error", f"falló el respaldo: {e}. {legacy} sigue intacto y con su nombre.")
        con.execute("COMMIT")
        con.execute("BEGIN EXCLUSIVE")
        con.execute("ROLLBACK")
    except sqlite3.Error as e:
        _remove_quiet(bak)
        bak = None
        if _busy(e):
            return _result("ocupada", f"no se pudo tomar {legacy} ({e}): {busy_msg}")
        return _result("error", f"en el checkpoint o el respaldo: {e}. {legacy} sigue con su nombre.")
    finally:
        con.close()
        if switched and bak is None:
            _back_to_wal(legacy)

    found = _sidecars(legacy, target)
    if found or _size(target):
        _remove_quiet(bak)
        _back_to_wal(legacy)
        if found:
            return _result("ocupada", f"aparecieron archivos auxiliares ({', '.join(found)}): otra conexión abrió "
                                      f"la base. {busy_msg}")
        return _result("aborto", f"apareció {target} ({_size(target)} bytes) durante la migración. No se cambió "
                                 "el nombre.")
    try:
        os.replace(legacy, target)
    except OSError as e:
        _remove_quiet(bak)
        _back_to_wal(legacy)
        return _result("ocupada", f"no se pudo cambiar el nombre {legacy} -> {target}: {e}. {busy_msg}")

    state = _probe_db(target)
    if state in ("sin-work", "no-base", "vacia", "ausente"):
        try:
            os.replace(target, legacy)
            return _result("error", f"{target} no resultó usable tras el cambio de nombre; se devolvió a "
                                    f"{legacy}. Respaldo en {bak}.", bak)
        except OSError as e:
            return _result("error", f"{target} no resultó usable y no se pudo devolver a {legacy} ({e}). "
                                    f"{ROLLBACK_HELP} Respaldo en {bak}.", bak)
    aviso, escribio = _reappeared(legacy)
    if state != "usable":
        extra = (f"{target} quedó en su lugar pero la verificación dio '{state}' (otra conexión la abrió). No lo "
                 "devuelvas.")
        return _result("ok", f"OK con aviso: {extra}", bak, aviso, escribio)
    try:
        c = sqlite3.connect(target, timeout=0)
        try:
            wal = c.execute("PRAGMA journal_mode=WAL").fetchone()
        finally:
            c.close()
        wal_note = None if wal is not None and str(wal[0]).lower() == "wal" else \
            f"{target} quedó en journal_mode={wal}; la primera conexión de neb lo pasa a WAL."
    except sqlite3.Error as e:
        wal_note = f"{target} quedó en journal_mode=DELETE ({e}); la primera conexión de neb lo pasa a WAL."
    return _result("ok", f"OK: {legacy} -> {target}.", bak, " ".join(x for x in (aviso, wal_note) if x) or None,
                   escribio)


def migrate(home_dir, dry_run=False):
    """Devuelve 0 (migrada, nada que hacer o dry-run sin problemas) o 1 (no cambió el nombre)."""
    if dry_run:
        base = os.path.join(home_dir, ".claude")
        legacy = os.path.join(base, LEGACY_DB_NAME)
        target = os.path.join(base, NEB_DB_NAME)
        code, msg = _precheck(base, legacy, target)
        print("[migrate] --dry-run: revisión sin abrir ni escribir nada.")
        for path in (legacy, target):
            size = _size(path)
            print(f"  {path}: {'no existe' if size is None else f'{size} bytes'}")
        print(f"  archivos auxiliares: {', '.join(_sidecars(legacy, target)) or 'ninguno'}")
        if msg is not None:
            print(f"[migrate] {'ABORTARÍA: ' if code == 'aborto' else ''}{msg}")
            return EXIT[code]
        print(f"[migrate] plan: checkpoint, journal_mode=DELETE, respaldo con la API de backup bajo una "
              f"transacción de lectura, BEGIN EXCLUSIVE, comprobación de archivos auxiliares, cambio de nombre "
              f"{legacy} -> {target}, verificación y vuelta a journal_mode=WAL.")
        return 0
    r = rename(home_dir)
    if r["codigo"] in ("ok", "nada"):
        print(f"[migrate] {r['mensaje']}")
        if r["respaldo"]:
            print(f"[migrate] respaldo: {r['respaldo']}")
        if r["codigo"] == "ok":
            print(f"[migrate] {ROLLBACK_HELP}")
        if r["aviso"]:
            print(f"[migrate] aviso: {r['aviso']}", file=sys.stderr)
    else:
        print(f"[migrate] ABORT: {r['mensaje']}", file=sys.stderr)
    return EXIT[r["codigo"]]


def _utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv):
    _utf8_stdout()
    p = argparse.ArgumentParser(
        description=f"Cambia el nombre de la bitácora de {LEGACY_DB_NAME} a {NEB_DB_NAME} (neb 7.0.0). "
                    "Si otra sesión la tiene abierta, no cambia nada y se vuelve a correr después.",
        epilog=ROLLBACK_HELP)
    p.add_argument("--home", default=os.path.expanduser("~"),
                   help="directorio HOME sobre cuyo .claude opera (por omisión, ~; las pruebas usan uno temporal).")
    p.add_argument("--dry-run", action="store_true",
                   help="revisa existencia, tamaño y archivos auxiliares sin abrir ni escribir nada.")
    args = p.parse_args(argv)
    return migrate(args.home, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
