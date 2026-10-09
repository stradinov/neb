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
LB() { py "$NEB_SRC/hooks/lib/logbook.py" "$@" 2>/dev/null || python "$NEB_SRC/hooks/lib/logbook.py" "$@" 2>/dev/null || python3 "$NEB_SRC/hooks/lib/logbook.py" "$@"; }
```

## Operaciones

### Listar (default, sin args)
`LB list` → JSON de los trabajos activos. Presenta una tabla: **id · proyecto/req (o "exploratoria") · owner · lock · estado · antigüedad**. Separa los **con-REQ** (relevables cross-dev) de las **sesiones exploratorias** (reanudables con `--resume` por su dueño).

**Siempre** corre además `LB sync-status` y, **antes** de la tabla, antepón un aviso cuando su salida traiga `attention > 0` (works en conflicto o con un fallo de publicación, o sesiones con un fallo de subida del transcript) o `endpoint_set: true` con `token_set: false` (el sync no está corriendo y no deja rastro). Una línea por work afectado (`local_id` · req · `last_error` · desde cuándo) y una por sesión con `status: error` (`session_id` · `transcript_error` · desde cuándo · `pending_bytes`). Sin este aviso un rechazo permanente del central es invisible: el dev solo se entera si pregunta. Si no hay nada que avisar, no digas nada. **Pero si la salida de `LB sync-status` viene vacía, no es JSON o no trae `attention`, antepón una línea: «no se pudo verificar el estado del sync (¿`NEB_HOME` desactualizado respecto al plugin?)»** — una salida vacía no significa «nada atascado».

### Estado del sync — `estado-sync`
`LB sync-status` → estado del outbox hacia el central. Lee **siempre** la DB local y nunca hace red: ese estado no existe en el central.
- **`works`:** works pendientes de publicar (`dirty`), en conflicto (`conflict`) o con un fallo de publicación (`last_error`).
- **`sessions`:** sesiones cuyo transcript requiere atención, según `status`:
  - `error`: hay un fallo vigente. Incluye «excede el tope por envío», que espera la subida fragmentada.
  - `esperando-work`: tiene cola, pero su work no está publicado.
  - `jsonl-ausente`: el archivo ya no existe y `pending_bytes` nunca llegó al central. Es una pérdida sin reintento posible.

Cada fallo trae su `*_at` = **desde cuándo** falla; no se reescribe mientras el error sea el mismo. `pending_bytes` dice cuánto falta por subir.

Un fallo de sync es **informativo**: el cliente sigue reintentando en cada sync, y cuando la causa se corrige el work se publica solo. Solo el conflicto (`409`) corta el reintento y exige reconciliar (`tomar`/`liberar-forzado`) antes de volver a publicar; con `conflict=1`, `last_error` guarda el motivo del 409. El aviso de un conflicto se apaga cuando una **captura posterior** (siguiente Stop en ese REQ) vuelve a publicar con éxito; reconciliar por sí solo no toca la fila local.

El fallo del transcript es **por sesión** (desde 6.12): varias sesiones alternando sobre el mismo REQ ya no se pisan el aviso ni la cola.

### Retomar — `retomar <id>`
Corre `LB show <id>` y actúa según `mode`:
- **`req`**: (1) `LB claim <id>` (tomar el mando); (2) `git -C <repo_path> checkout <branch>` (y el `head_commit` si aplica); (3) abre una **sesión nueva** y reconstruye contexto leyendo el `transcript_path` (Read) + el `change_md`; (4) relanza lo descrito en **"Trabajo en vuelo"** del `payload_json`. **No** uses `--resume` (no funciona cross-machine — capa B2 descartada).
- **`exploratory`**: entrega al dev `claude --resume <claude_session_id>` (reanuda local; válido **solo** en la máquina origen, `origin_machine`).

### Lock
- `tomar <id>` → `LB claim <id>`.
- `liberar <id>` → `LB release <id>`.
- `liberar-forzado <id>` → **pide confirmación humana explícita** (le quita el mando a otro dev), y con el OK: `LB forced-release <id>`. Queda auditado (`event forced_release`).
- `solicitar <id>` → `LB request <id>`.
- `renombrar <id> <nuevo-slug> [nuevo-project]` → `LB rename <id> <nuevo-slug>` (renombre gobernado: migra la fila preservando `event`/`transcript`; sin esto, un slug nuevo bifurca en otro work).
- `archivar <id>` → `LB archive <id>` (cierre del REQ: marca el work archivado; se preserva para auditoría, la purga es manual en el backend central).

### Buscar — `search <texto>`
`LB search <texto>` (FULLTEXT sobre el transcript del corpus; requiere central).

## Notas
- Con `NEB_LOGBOOK_ENDPOINT` configurado el CLI opera contra el **backend central** (autoridad: lock atómico, `solicitar`/`search`/`renombrar` funcionales; los ids son los **remotos** que devuelve `list`/`search`). En **local-only** el lock es informativo (un dev, una DB) y `solicitar`/`search` no aplican — el CLI lo informa.
- `estado-sync` reporta **`local_id`** (id de la DB local), no `id`. Con central configurado **no** lo uses con `retomar`/`tomar`/`liberar`/`archivar`: esos verbos interpretan ids **remotos** y el mismo número puede ser el work de otro dev. Para operar sobre un work listado ahí, usa su `remote_id`. Si `remote_id` es `null`, este cliente nunca lo publicó con éxito: tras un `409` el work existe en el central a nombre de otro (ubícalo en `LB list` por project + req_slug); tras un `5xx` no existe, y lo único que aplica es corregir la causa que muestra `last_error`.
- El wrapper `LB` descarta `stderr`: todo lo que el dev deba ver sale por `stdout` (por eso `sync-status` lleva sus avisos dentro del JSON, en `notes`).
- No edites la DB a mano: usa los subcomandos (preservan idempotencia y eventos auditados).
