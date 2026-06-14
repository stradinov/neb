#!/usr/bin/env python3
"""
purge.py — retención del corpus central (Neb, REQ B).

Política: un `work` cerrado se ARCHIVA (`archived_at`), no se borra — el corpus es de auditoría.
La purga es una acción INTENCIONAL y manual (no hay cron). Este script la materializa con
`--dry-run` por default (solo cuenta); requiere `--apply` para ejecutar el DELETE
(CASCADE elimina sus `event` y `transcript`).

Uso:
  python purge.py --before 2025-01-01            # dry-run: cuántos works archivados se purgarían
  python purge.py --before 2025-01-01 --apply    # ejecuta el DELETE

Lee la misma config de DB que el servidor (NEB_LOGBOOK_DB_*). Ver INSTALL.md.
"""

import argparse
import os
import sys

try:
    import pymysql
except ImportError:
    sys.stderr.write("[purge] falta PyMySQL: pip install -r requirements.txt\n")
    raise

DB = {
    "host": os.environ.get("NEB_LOGBOOK_DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("NEB_LOGBOOK_DB_PORT", "3306")),
    "user": os.environ.get("NEB_LOGBOOK_DB_USER", "neb_logbook"),
    "password": os.environ.get("NEB_LOGBOOK_DB_PASSWORD", ""),
    "database": os.environ.get("NEB_LOGBOOK_DB_NAME", "neb_logbook"),
}

WHERE = "archived_at IS NOT NULL AND archived_at < %s"


def main():
    ap = argparse.ArgumentParser(description="Purga works archivados del corpus central (manual).")
    ap.add_argument("--before", required=True, help="YYYY-MM-DD: purga works con archived_at anterior a esta fecha")
    ap.add_argument("--apply", action="store_true", help="ejecuta el DELETE (default: dry-run)")
    args = ap.parse_args()

    conn = pymysql.connect(charset="utf8mb4", autocommit=False, **DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM work WHERE " + WHERE, (args.before,))
        n = cur.fetchone()[0]
        if not args.apply:
            print("[dry-run] %d works archivados anteriores a %s se purgarían "
                  "(con sus event/transcript en cascada). Re-ejecutá con --apply." % (n, args.before))
            return
        cur.execute("DELETE FROM work WHERE " + WHERE, (args.before,))
        conn.commit()
        print("[apply] %d works purgados (anteriores a %s)." % (cur.rowcount, args.before))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
