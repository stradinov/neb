---
name: logbook
description: "Bitácora de relevo local: listar o retomar trabajos a medias (tu sesión interrumpida, o un REQ desde su Change MD) y vincular o trazar un REQ."
---

# /logbook — bitácora de relevo

El usuario invocó `/logbook` (opcionalmente con un subcomando). Opera la bitácora de relevo siguiendo el skill `logbook` (definición completa en `skills/logbook/SKILL.md` — no la dupliques aquí).

Subcomandos: sin args o `list` (listar trabajos a medias) · `retomar <id>` o `retomar <ruta-del-Change-MD>` (desde otra máquina o sin work en la bitácora) · `renombrar <id> <nuevo-slug>` · `archivar <id>` · `vincular <ruta>` · `traza [<nombre>|<ruta>|<id>]` · `desvincular <id|nombre|ruta>`. `search` se retiró en neb 6.41.0.

Resuelve el módulo (el clon de `NEB_HOME` si lo hay; si no, la raíz del plugin, que Claude Code sustituye al cargar este comando) y opera vía:

```bash
NEB_SRC="${NEB_HOME:-}"
case "$NEB_SRC" in ""|*/plugins/cache/*|*\\plugins\\cache\\*) NEB_SRC="${CLAUDE_PLUGIN_ROOT}" ;; esac
[ -f "$NEB_SRC/VERSION" ] || echo "Neb: no hay VERSION en '$NEB_SRC'. Si la ruta es la de NEB_HOME, corrígela; si quedó vacía, actualiza Claude Code (sustitución de CLAUDE_PLUGIN_ROOT en skills)" >&2
py "$NEB_SRC/hooks/lib/logbook.py" <subcomando> [args]   # o python / python3
```

Presenta la salida como tabla legible. Al **retomar**, sigue el flujo del skill según el modo: `req` → checkout de la rama y sesión nueva con el Change MD, su `## Relevo` y su plan aprobado como contexto; `exploratory` → entregar `claude --resume <claude_session_id>` (solo en la máquina de `origin_machine`); con una ruta de Change MD → leer el Change MD, su `## Relevo` y su plan aprobado, y hacer checkout de su rama.
