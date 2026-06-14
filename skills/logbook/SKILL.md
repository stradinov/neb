---
name: logbook
description: >
  Cargar cuando el usuario invoca /logbook o pide listar, retomar o relevar trabajos a medias
  (handoff entre devs o máquinas, reanudar una sesión interrumpida, ver qué quedó pendiente de
  otra sesión). Opera la bitácora de relevo (SQLite local; central opcional). NO cargar para
  tareas de implementación normales ni cuando el usuario ya está trabajando en su REQ activo.
---

# Skill: logbook (bitácora de relevo)

Opera la bitácora de relevo. El artefacto y su modelo de ownership viven en [`../../workflow/logbook.md`](../../workflow/logbook.md); la mecánica del backend en [`../../tooling/logbook.md`](../../tooling/logbook.md). Este skill **ejecuta** las operaciones — no repite esos lineamientos.

## Resolver el módulo

```bash
NEB_SRC="${NEB_HOME:-${CLAUDE_PLUGIN_ROOT:-$(ls -d "$HOME"/.claude/plugins/cache/*/neb/*/ 2>/dev/null | sort -V | tail -1)}}"
LB() { py "$NEB_SRC/hooks/lib/logbook.py" "$@" 2>/dev/null || python "$NEB_SRC/hooks/lib/logbook.py" "$@"; }
```

## Operaciones

### Listar (default, sin args)
`LB list` → JSON de los trabajos activos. Presentá una tabla: **id · proyecto/req (o "exploratoria") · owner · lock · estado · antigüedad**. Separá los **con-REQ** (relevables cross-dev) de las **sesiones exploratorias** (reanudables con `--resume` por su dueño).

### Retomar — `retomar <id>`
Corré `LB show <id>` y actuá según `mode`:
- **`req`**: (1) `LB claim <id>` (tomar el mando); (2) `git -C <repo_path> checkout <branch>` (y el `head_commit` si aplica); (3) abrí una **sesión nueva** y reconstruí contexto leyendo el `transcript_path` (Read) + el `change_md`; (4) relanzá lo descrito en **"Trabajo en vuelo"** del `payload_json`. **No** uses `--resume` (no funciona cross-machine — capa B2 descartada).
- **`exploratory`**: entregá al dev `claude --resume <claude_session_id>` (reanuda local; válido **solo** en la máquina origen, `origin_machine`).

### Lock
- `tomar <id>` → `LB claim <id>`.
- `liberar <id>` → `LB release <id>`.
- `liberar-forzado <id>` → **pedí confirmación humana explícita** (le quita el mando a otro dev), y con el OK: `LB forced-release <id>`. Queda auditado (`event forced_release`).
- `solicitar <id>` → `LB request <id>`.
- `renombrar <id> <nuevo-slug> [nuevo-project]` → `LB rename <id> <nuevo-slug>` (rename gobernado: migra la fila preservando `event`/`transcript`; sin esto, un slug nuevo bifurca en otro work).
- `archivar <id>` → `LB archive <id>` (cierre del REQ: marca el work archivado; se preserva para auditoría, la purga es manual via `server/purge.py`).

### Buscar — `search <texto>`
`LB search <texto>` (FULLTEXT sobre el transcript del corpus; requiere central).

## Notas
- Con `NEB_LOGBOOK_ENDPOINT` configurado el CLI opera contra el **backend central** (autoridad: lock atómico, `solicitar`/`search`/`renombrar` funcionales; los ids son los **remotos** que devuelve `list`/`search`). En **local-only** el lock es informativo (un dev, una DB) y `solicitar`/`search` no aplican — el CLI lo informa.
- No edites la DB a mano: usá los subcomandos (preservan idempotencia y eventos auditados).
