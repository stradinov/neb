#!/usr/bin/env python3
"""approved_plan.py — hook `save-approved-plan` en Python (PostToolUse de ExitPlanMode).

Port de `hooks/save-approved-plan.sh` para el dispatcher del plugin (`hooks/neb-hook.py`): misma ruta
(`~/.claude/approved-plans/<ts>-<proyecto>-<slug>.md`) y mismo encabezado, sin `jq` (no viene en Git Bash).

Dos diferencias deliberadas con el `.sh`:
- El slug es ASCII completo (`ñ` → `n`, símbolos → `-`). `slugify.sh` usa `iconv //TRANSLIT`, que en Git Bash
  trunca en el primer carácter no ASCII («Instalación» → `instalaci`).
- El proyecto es el último segmento del cwd con `/` o `\\`; `basename` de bash no corta en `\\`.
"""
import os
import re
import unicodedata
from datetime import datetime


def slugify(text, limit=50):
    """Primera línea del plan → slug kebab-case ASCII de hasta `limit` caracteres ('plan' si queda vacío)."""
    s = re.sub(r"^[\s#]*", "", text).lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:limit].rstrip("-") or "plan"


def save(event, home, now=None):
    """Escribe el plan aprobado del evento. Devuelve la ruta escrita, o None si el evento no trae plan."""
    plan = (event.get("tool_input") or {}).get("plan") or ""
    if not plan:
        return None
    sid = event.get("session_id") or "unknown"
    cwd = event.get("cwd") or ""
    project = re.split(r"[/\\]", cwd.rstrip("/\\"))[-1] if cwd else ""
    # Sin caracteres que Windows no admite en un nombre: con el cwd en `C:\`, `C:` abriría un flujo NTFS.
    project = re.sub(r'[<>:"|?*]', "-", project).strip("-") or "unknown"
    now = now or datetime.now()

    dest = os.path.join(home, ".claude", "approved-plans")
    os.makedirs(dest, exist_ok=True)
    path = os.path.join(dest, "%s-%s-%s.md" % (
        now.strftime("%Y%m%d-%H%M%S"), project, slugify(plan.splitlines()[0])))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Plan aprobado — %s\n\n" % now.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("**Proyecto:** %s\n" % project)
        f.write("**Sesión:** %s\n" % sid)
        f.write("**CWD:** %s\n\n" % cwd)
        f.write(plan + "\n")
    return path
