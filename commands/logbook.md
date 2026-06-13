---
name: logbook
description: Bitácora de relevo — listar, retomar o relevar trabajos a medias (handoff cross-dev o reanudar tu propia sesión interrumpida).
---

# /logbook — bitácora de relevo

El usuario invocó `/logbook` (opcionalmente con un subcomando). Operá la bitácora de relevo siguiendo el skill `logbook` (definición completa en `skills/logbook/SKILL.md` — no la dupliques acá).

Subcomandos: sin args o `list` (listar trabajos a medias) · `retomar <id>` · `tomar <id>` · `liberar <id>` · `liberar-forzado <id>` · `solicitar <id>` · `search <texto>`.

Resolvé el módulo y operá vía (fallback para miembros sin `NEB_HOME`):

```bash
NEB_SRC="${NEB_HOME:-${CLAUDE_PLUGIN_ROOT:-$(ls -d "$HOME"/.claude/plugins/cache/*/neb/*/ 2>/dev/null | sort -V | tail -1)}}"
py "$NEB_SRC/hooks/lib/logbook.py" <subcomando> [args]   # o python / python3
```

Presentá la salida como tabla legible. Al **retomar**, seguí el flujo del skill según el modo: `req` → tomar el mando + sesión nueva con el transcript como contexto; `exploratory` → entregar `claude --resume <id>`.
