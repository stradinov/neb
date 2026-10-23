---
name: logbook
description: Bitácora de relevo — listar, retomar o relevar trabajos a medias (handoff cross-dev o reanudar tu propia sesión interrumpida).
---

# /logbook — bitácora de relevo

El usuario invocó `/logbook` (opcionalmente con un subcomando). Operá la bitácora de relevo siguiendo el skill `logbook` (definición completa en `skills/logbook/SKILL.md` — no la dupliques acá).

Subcomandos: sin args o `list` (listar trabajos a medias) · `retomar <id>` · `tomar <id>` · `liberar <id>` · `liberar-forzado <id>` · `solicitar <id>` · `renombrar <id> <nuevo-slug>` · `archivar <id>` · `search <texto>` · `estado-sync` (works sin publicar, en conflicto o con un fallo de publicación, y sesiones cuyo transcript no sube; siempre local — el verbo del CLI es `sync-status`).

Resuelve el módulo (el clon de `NEB_HOME` si lo hay; si no, la raíz del plugin, que Claude Code sustituye al cargar este comando) y opera vía:

```bash
NEB_SRC="${NEB_HOME:-}"
case "$NEB_SRC" in ""|*/plugins/cache/*|*\\plugins\\cache\\*) NEB_SRC="${CLAUDE_PLUGIN_ROOT}" ;; esac
[ -f "$NEB_SRC/VERSION" ] || echo "Neb: no hay VERSION en '$NEB_SRC'. Si la ruta es la de NEB_HOME, corrígela; si quedó vacía, actualiza Claude Code (sustitución de CLAUDE_PLUGIN_ROOT en skills)" >&2
py "$NEB_SRC/hooks/lib/logbook.py" <subcomando> [args]   # o python / python3
```

Presentá la salida como tabla legible. Al **retomar**, seguí el flujo del skill según el modo: `req` → tomar el mando + sesión nueva con el transcript como contexto; `exploratory` → entregar `claude --resume <id>`.
