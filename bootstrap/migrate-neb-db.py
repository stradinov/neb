#!/usr/bin/env python3
"""
migrate-neb-db.py — migración one-shot del maintainer: renombra ~/.claude/neb-logbook.db
→ ~/.claude/neb.db consolidando los sidecars WAL (-wal/-shm).

NO es un .sh: el binario `sqlite3` CLI no está en PATH en Windows; se usa el módulo
sqlite3 de Python. Idempotente, con backup completo y rollback documentado.

Por qué es OPCIONAL: el resolver dual-mode (resolve_db_path en hooks/lib/_db_shared.py)
encuentra neb-logbook.db si neb.db no existe, así que el hook opera sin migrar. Este
script es solo para la máquina del maintainer que quiere el nombre canónico neb.db.

VENTANA DE EJECUCIÓN: correr SIN sesiones activas del dev y SIN sync central detached
en vuelo. El paso "abort-si-bloqueado" lo detecta y aborta, pero la ventana lo hace robusto.

ROLLBACK (si algo sale mal o el logbook-sync deja de operar tras migrar):
  1. Borrar/renombrar  ~/.claude/neb.db
  2. Restaurar  ~/.claude/neb-logbook.db.bak-<stamp>  ->  ~/.claude/neb-logbook.db
     (y los .bak de -wal/-shm si se restauran, aunque tras journal_mode=DELETE no deberían existir)
  3. resolve_db_path vuelve a encontrar neb-logbook.db (dual-mode) -> el hook opera sin cambios.

Uso:
  py bootstrap/migrate-neb-db.py            # migra ~/.claude/
  py bootstrap/migrate-neb-db.py --dry-run  # imprime el plan sin tocar nada
  py bootstrap/migrate-neb-db.py --home <dir>   # opera sobre <dir>/.claude (tests)
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone

# Reusa _is_usable_db del módulo compartido (misma guarda anti-shadowing que el resolver).
_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "lib")
sys.path.insert(0, _LIB)
from _db_shared import _is_usable_db, NEB_DB_NAME, LEGACY_DB_NAME


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _backup(path, stamp):
    """Copia <path> a <path>.bak-<stamp> preservando mtime. No-op si <path> no existe."""
    if os.path.isfile(path):
        dst = f"{path}.bak-{stamp}"
        shutil.copy2(path, dst)
        return dst
    return None


def migrate(home_dir, dry_run=False):
    """Devuelve 0 (éxito / idempotente / dry-run OK) o 1 (abort sin cambios / fallo)."""
    base   = os.path.join(home_dir, ".claude")
    legacy = os.path.join(base, LEGACY_DB_NAME)   # neb-logbook.db
    target = os.path.join(base, NEB_DB_NAME)       # neb.db

    # 2. Idempotencia
    if not os.path.isfile(legacy) and _is_usable_db(target):
        print("[migrate] ya migrado: neb.db usable y no hay neb-logbook.db. Nada que hacer.")
        return 0
    if not os.path.isfile(legacy):
        print("[migrate] no hay neb-logbook.db que migrar. Nada que hacer.")
        return 0

    # 3. Anti-colisión
    if _is_usable_db(target):
        print(f"[migrate] ABORT: {target} ya existe CON contenido; revisar manualmente "
              f"(¿ya migrado? ¿colisión?). No se tocó nada.", file=sys.stderr)
        return 1

    # 4. Abort-si-bloqueado (otra conexión / sync detached corriendo).
    # REUSA esta MISMA conexión para el checkpoint del paso 6 (cierra la ventana TOCTOU:
    # entre el abort-check y el checkpoint no puede colarse otro escritor que tome el lock).
    con = None
    try:
        con = sqlite3.connect(legacy, timeout=0)   # sin espera
        con.execute("BEGIN IMMEDIATE")             # falla si hay otro escritor/lector-WAL activo
        con.execute("ROLLBACK")                    # libera el lock; la conexión queda viva para el paso 6
    except sqlite3.OperationalError:
        print("[migrate] ABORT: DB legacy bloqueada (sesión o sync activo); "
              "cerrar y reintentar. No se tocó nada.", file=sys.stderr)
        if con is not None:
            con.close()
        return 1

    # 5. Backup completo (los 3 archivos si existen)
    stamp = _stamp()
    backups = []
    for suffix in ("", "-wal", "-shm"):
        b = _backup(legacy + suffix, stamp)
        if b:
            backups.append(b)

    if dry_run:
        con.close()
        print("[migrate] --dry-run: plan de migración (NO se ejecuta):")
        print(f"  backups creados: {backups}")
        print(f"  6. wal_checkpoint(TRUNCATE) + journal_mode=DELETE sobre {legacy}")
        print(f"  7. os.replace({legacy}, {target})")
        print(f"  8. verificar _is_usable_db({target})")
        print("[migrate] --dry-run OK (backups SÍ se crearon como muestra; el rename NO).")
        return 0

    # 6. Consolidar sidecars (fusiona -wal/-shm al .db principal y apaga WAL).
    # CAPTURA la fila de wal_checkpoint(TRUNCATE) = (busy, log_frames, checkpointed_frames):
    #   busy==1            -> no se pudo tomar el lock (otro lector/escritor) -> abort
    #   log != checkpointed -> quedaron frames sin aplicar al main -> abort (consolidación incompleta)
    #   row is None         -> resultado inesperado -> abort
    # Abortar deja los backups intactos y la DB legacy sin tocar (aún no se hizo os.replace).
    try:
        row = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if row is None or row[0] == 1 or row[1] != row[2]:
            con.close()
            print(f"[migrate] ABORT en checkpoint: wal_checkpoint(TRUNCATE) devolvió {row} "
                  f"(busy / frames sin aplicar). Backups en {backups}. La DB legacy sigue intacta.",
                  file=sys.stderr)
            return 1
        con.execute("PRAGMA journal_mode=DELETE")          # apaga WAL → borra -wal/-shm al cerrar
        con.commit()
        con.close()
    except sqlite3.Error as e:
        con.close()
        print(f"[migrate] ABORT en checkpoint: {e}. Backups en {backups}. "
              f"La DB legacy sigue intacta.", file=sys.stderr)
        return 1

    # 7. Mover atómico (mismo volumen)
    try:
        os.replace(legacy, target)
        # Tras journal_mode=DELETE los sidecars ya no existen; si quedaran, borrarlos.
        for suffix in ("-wal", "-shm"):
            stale = legacy + suffix
            if os.path.isfile(stale):
                os.remove(stale)
    except OSError as e:
        print(f"[migrate] ABORT moviendo {legacy} -> {target}: {e}. "
              f"Restaurar desde backups si quedó a medias. Backups: {backups}", file=sys.stderr)
        return 1

    # 8. Verificar destino
    if not _is_usable_db(target):
        # Rollback automático: regresar el legacy desde el backup.
        print(f"[migrate] ABORT: {target} no resultó usable tras el rename. "
              f"Ejecutando rollback automático…", file=sys.stderr)
        try:
            if os.path.isfile(target):
                os.remove(target)
            # restaurar legacy desde su backup (.bak del .db principal)
            main_bak = f"{legacy}.bak-{stamp}"
            if os.path.isfile(main_bak):
                shutil.copy2(main_bak, legacy)
                print(f"[migrate] rollback: {legacy} restaurado desde {main_bak}.", file=sys.stderr)
        except OSError as e:
            print(f"[migrate] rollback FALLÓ: {e}. Restaurar manualmente desde {backups}.", file=sys.stderr)
        return 1

    # 9. Éxito
    print(f"[migrate] OK: {legacy} -> {target}.")
    print(f"[migrate] backups: {backups}")
    print("[migrate] rollback (si hiciera falta): borrar neb.db, restaurar "
          f"{legacy}.bak-{stamp} -> neb-logbook.db; el dual-mode lo reencuentra.")
    return 0


def main(argv):
    p = argparse.ArgumentParser(description="Migra neb-logbook.db -> neb.db (one-shot, idempotente).")
    p.add_argument("--home", default=os.path.expanduser("~"),
                   help="directorio HOME a operar (su subdir .claude); default = ~ (tests usan tempdir).")
    p.add_argument("--dry-run", action="store_true", help="imprime el plan sin renombrar.")
    args = p.parse_args(argv)
    return migrate(args.home, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
