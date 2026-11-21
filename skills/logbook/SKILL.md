---
name: logbook
description: >
  Cargar cuando el usuario invoca `/logbook` o pide listar o retomar trabajos a medias de la bitácora
  de relevo, la base local `~/.claude/neb.db`: una sesión interrumpida en esta máquina, o un REQ desde
  su Change MD (en otra máquina, o el que dejó otro dev), por git. También para vincular, trazar o
  desvincular un REQ (repos, sesiones y commits). Si piden tomar, liberar o solicitar un trabajo, o el
  estado de la sincronización, cargar para explicar que eso se retiró en neb 7.0.0 y ofrecer
  `retomar <ruta-del-Change-MD>`. NO cargar para consultar o curar pendientes (eso es `pendings-review`)
  ni para implementar el REQ activo.
---

# Skill: logbook (bitácora de relevo)

Opera la bitácora de relevo: la base local de trabajos a medias, para retomarlos. Qué guarda y cómo se relaciona con el Change MD vive en [`../../workflow/logbook.md`](../../workflow/logbook.md); la captura, la base sin migrar y el significado de los campos de `trace`, en [`../../tooling/logbook.md`](../../tooling/logbook.md). Este skill **ejecuta** las operaciones; no repite esos lineamientos.

## Resolver el módulo

```bash
NEB_SRC="${NEB_HOME:-}"
case "$NEB_SRC" in ""|*/plugins/cache/*|*\\plugins\\cache\\*) NEB_SRC="${CLAUDE_PLUGIN_ROOT}" ;; esac
[ -f "$NEB_SRC/VERSION" ] || echo "Neb: no hay VERSION en '$NEB_SRC'. Si la ruta es la de NEB_HOME, corrígela; si quedó vacía, actualiza Claude Code (sustitución de CLAUDE_PLUGIN_ROOT en skills)" >&2
LB() { py "$NEB_SRC/hooks/lib/logbook.py" "$@" 2>/dev/null || python "$NEB_SRC/hooks/lib/logbook.py" "$@" 2>/dev/null || python3 "$NEB_SRC/hooks/lib/logbook.py" "$@"; }
```

## Respuestas que cortan el flujo

Antes de presentar una salida, revisa si es un objeto JSON con `"ok": false` y uno de estos `motivo`:

- **`base-sin-migrar`**: la base conserva el nombre anterior a neb 7.0.0 y ningún verbo la abre hasta migrarla. Muestra al dev el `detalle` y la `accion` tal cual (la migración guiada: `/neb:migrate` en una sesión nueva, que pide cerrar antes las demás sesiones de Claude), y el `comando` como la vía a mano (qué hacer si el migrador se niega: [`../../tooling/logbook.md`](../../tooling/logbook.md) § "Base sin migrar"). No corras el migrador ni la migración guiada sin un OK explícito del dev, y no reintentes con otro verbo: ninguno abre la base hasta migrarla. Detente ahí.
- **`verbo-retirado`** (llega si una versión anterior del skill llamó al verbo): el verbo ya no existe. Dile al dev que se retiró, con el `detalle`, y sigue con la operación que sí aplica (por lo general, `retomar <ruta-del-Change-MD>`).

## Operaciones

### Listar (default, sin args)

`LB list` → arreglo JSON de los trabajos activos, cada uno con `id`, `mode`, `project`, `req_slug`, `req_state` y `updated_at`. Presenta una tabla: **id · proyecto/req (o "exploratoria") · estado · antigüedad**. Separa los **con REQ** (se retoman con `retomar <id>` en esta máquina, o con su Change MD en cualquiera) de las **sesiones exploratorias** (se reanudan con `--resume` en la máquina donde se capturaron). Un arreglo vacío significa que no hay trabajos activos.

### REQ vinculado — `vincular`, `traza`, `desvincular`

Qué es un REQ vinculado y qué guarda: [`../../workflow/logbook.md`](../../workflow/logbook.md) § "REQ vinculado". Decide por `ok`, no por el código de salida: exige `"ok": true`. Si la salida viene vacía o no trae `ok`, no se hizo nada: el módulo es anterior a estos verbos (¿`NEB_HOME` desactualizado respecto al plugin?) o falló sin responder; dilo así. Con `"ok": false`, aplica primero las respuestas que cortan el flujo; con cualquier otro `motivo`, repórtalo.

- `vincular <ruta> [--repo <dir>]` → `LB link <ruta> [--repo <dir>]`. Un `--repo` por llamada; para más repos, repite el comando. Un `--repo` que no se pudo resolver sale en `avisos`. `sesiones` cuenta solo las ligas ya capturadas: puede ser 0 en el mismo turno, porque la captura del siguiente `Stop` liga la sesión. No consulta commits; para verlos, `traza`.
- `traza [<nombre>|<ruta>|<id>] [--sin-git]` → `LB trace [<nombre>|<ruta>|<id>] [--sin-git]`. Sin argumento lista los REQ vinculados; con nombre, ruta o id trae sus repos, sesiones y commits (`--sin-git` omite los commits). Para interpretar cada campo de la salida, lee [`../../tooling/logbook.md`](../../tooling/logbook.md) § "Salida de `traza`".
  - `leer` apunta al transcript de la sesión más reciente que sigue en disco. Si hace falta un dato que `## Relevo` no trae, Claude busca en ese transcript con Grep o lectura parcial, sin leerlo completo.
- `desvincular <id|nombre|ruta>` → `LB unlink <id|nombre|ruta>`. Con `"motivo": "ambiguo"` muestra los `ids` y pide al dev que elija uno. Para quitar un repo mal declarado: desvincular y volver a vincular.

### Retomar — `retomar <id>` o `retomar <ruta-del-Change-MD>`

`retomar <id>`: corre `LB show <id>` y actúa según `mode`.

- **`req`**: vale en la máquina que lo capturó (`origin_machine`), porque `repo_path` es la ruta de su clon. (1) `git -C <repo_path> checkout <branch>` (y el `head_commit` si aplica); (2) abre una **sesión nueva** y reconstruye el contexto desde el `change_md`: su `## Relevo` y su plan aprobado (campo `**Plan aprobado:**`); (3) relanza lo descrito en **"Trabajo en vuelo"** de `## Relevo` (si el registro no trae esa sección, desde `next_steps` del `payload_json`, que copia la línea «Próximos pasos» del `active_*.md`). **No** uses `--resume`: el contexto de un REQ es su Change MD, no el transcript. Desde otra máquina, usa `retomar <ruta-del-Change-MD>`.
- **`exploratory`**: entrega al dev `claude --resume <claude_session_id>`, válido **solo** en la máquina donde se capturó (`origin_machine`).

`retomar <ruta-del-Change-MD>` sirve cuando el trabajo no está en esta base: un REQ que viene de otra máquina, el que dejó otro dev, o uno que nunca se capturó. Claude lee el Change MD, su `## Relevo` y su plan aprobado (campo `**Plan aprobado:**`), hace `git checkout` de la rama anotada en `**Rama:**` y continúa desde los próximos pasos.

### Renombrar y archivar

- `renombrar <id> <nuevo-slug>` → `LB rename <id> <nuevo-slug>`. Solo aplica a works `req`. Es el renombre gobernado: sin él, un slug nuevo bifurca en otro work.
- `archivar <id>` → `LB archive <id>`. Cierre del REQ: el work queda archivado en la base, sin borrarse, y los pendientes abiertos ligados a él pasan a obsoletos.

### Lo que se retiró

Si el dev pide tomar, liberar o solicitar un trabajo, o el estado de la sincronización, no llames al CLI: explícale que eso se retiró en neb 7.0.0, porque la bitácora es solo local, y ofrece `retomar <ruta-del-Change-MD>`. Para dejarle un REQ a otra persona, basta su `## Relevo` en el Change MD y el registro entregado por git. `search` se retiró en neb 6.41.0: la bitácora no guarda texto de sesiones.

## Notas

- El wrapper `LB` descarta `stderr`: todo lo que el dev deba ver sale por `stdout`.
- No edites la base a mano: usa los subcomandos, que preservan la idempotencia.
