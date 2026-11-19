# Bitácora de relevo (logbook)

Registro de trabajos a medias para **relevo entre devs y máquinas**. Cubre el caso que `pendings.md` § "Sesiones pausadas" y la memoria del proyecto no cubren: una sesión interrumpida (tokens agotados, corte de energía/internet, o handoff a otro dev) que debe continuar **en otra máquina con otra cuenta**, conservando el contexto vía el Change MD, su `## Relevo` y su plan aprobado.

La **mecánica** (backend pluggable, hook de captura, config, modos de fallo) vive en [`../tooling/logbook.md`](../tooling/logbook.md); el **protocolo operativo** (pasos para publicar/retomar/relevar) en [`../process/execution.md`](../process/execution.md) § "Gestión de sesiones (handoff)". Este archivo cubre el **artefacto**: su modelo, ciclo de vida y relación con el resto.

## Unidad y backend

- **Unidad = `work`** (un trabajo relevable), identificado por `project + req_slug` (estable cross-máquina; **no** la sesión Claude, que es local y efímera).
- **Backend pluggable**: SQLite local por defecto (universal, sin infra) + central opcional para relevo cross-dev real (backend central en un repositorio dedicado, ver [`../tooling/logbook.md`](../tooling/logbook.md)). El SQLite local es además **outbox** que sincroniza al central cuando el **entorno es compartido** (ver "Entorno compartido" abajo). El archivo local es `~/.claude/neb.db`, con **resolver dual-mode permanente** que cae al nombre legado `~/.claude/neb-logbook.db` en máquinas sin migrar (mecánica en [`../tooling/logbook.md`](../tooling/logbook.md) § "Backend pluggable").
- **Identidad del owner**: username del SO + `origin_machine` + nombre del trabajo (contexto desambiguador legible). No usa `git email` (decisión del equipo). *Limitación*: no distingue dos personas con el mismo username ni une al mismo dev con usernames distintos entre máquinas — el caso "continuar lo propio" se cubre con `--resume` local (ver "Dos modos").

## Modelo de ownership

El relevo exige un **único owner activo** por `work`. El lock vive sobre el `work`, no sobre la sesión.

| Estado | Significado |
|---|---|
| `owned` (por X) | X tiene el mando |
| `released` | libre para tomar |
| `takeover_requested` (por Y) | X sigue siendo owner; Y pidió el mando |

| Operación | Efecto |
|---|---|
| `tomar` (claim) | si `released` → el dev pasa a owner |
| `liberar` (release) | el owner libera → `released` |
| `solicitar el mando` (request) | si `owned` por otro → `takeover_requested`; el owner lo ve y libera |
| `liberar --forzado` | un dev **distinto** del owner fuerza la liberación, **con confirmación humana explícita**; registra `event(forced_release, prev_owner, forced_by)`. Escape ante owner ausente (corte sin liberar) sin esperar al takeover automático |

**Enforcement atómico solo en el backend central** (`UPDATE … WHERE lock_state='released'`, veredicto por filas afectadas; nunca read-then-write). **En backend local-only el lock es informativo** (un dev, una DB): `tomar`/`liberar` operan como recordatorio de estado; **`solicitar el mando` no aplica** sin central (no hay a quién solicitar). El takeover automático por desatención/timeout es un requerimiento futuro.

Este ENUM de lock es **ortogonal** al ENUM de estados del requerimiento ([`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Estados del requerimiento"): un `work` `archived` no altera el estado canónico del REQ.

## Dos modos

| Modo | Cuándo | Identidad | Reanudación |
|---|---|---|---|
| **Con-REQ** | hay ≥1 `active_<proyecto>_<slug>.md` en memoria (o sección legacy) | `project + req_slug` | **relevo cross-dev** (lock atómico); estado al central |
| **Exploratorio** | sin REQ formal (exploración previa) | `session_id` (entrada liviana, sin lock) | **`--resume` local** del mismo dev. Si el proyecto activa el central (opt-in), también se publica al catálogo (visibilidad); **no** relevable cross-dev (`claude_session_id` solo vale en su máquina origen) |

El modo exploratorio registra automáticamente la sesión (aunque el dev no anuncie pausa) con un resumen y el `transcript_path` local, para que `/logbook` la localice entre muchas y entregue el comando `--resume`. **Si el proyecto activa el central (opt-in)**, la sesión exploratoria también se publica al catálogo —para visibilidad—, pero **no es relevable cross-dev**: que **otro** dev la retome exige formalizarla en REQ antes. Al **formalizarse en REQ**, pasa a un `work` `req` y entra al relevo cross-dev con lock.

## REQ vinculado

Un **REQ vinculado** es una fila de la bitácora local por cada (`project`, `nombre`) de un registro `changes/<AAAA-MM-DD>-<nombre>.md`. Responde, sin recorrer repos ni transcripts a mano, qué sesiones de esta máquina trabajaron el REQ y qué commits publicados lleva. Convive con el `work` `req` de § "Dos modos" sin tocarlo.

- **Dos vías para vincular.**
  - El hook de captura ve, en `Stop` o `PreCompact`, un `Write`, `Edit` o `MultiEdit` del hilo principal sobre el Change MD.
  - Corres `/logbook vincular <ruta>`. Con `--repo <dir>` declaras un repo adicional del REQ, uno por llamada.
- **Leer no vincula.** Leer o nombrar el Change MD no vincula nada, y escribir el plan en `changes/plans/` tampoco. Sin remoto `origin` en el repo del registro no hay vínculo. Un Incident MD se vincula como cualquier registro, con `nombre = incident-<slug>`.
- **Llave: el `nombre`** del registro, el mismo del trailer `Req:`; la fecha es dato. Un worktree o un clon del mismo remoto ligan al mismo REQ.
- **Qué guarda.** Solo lo que git no sabe: el REQ, sus repos declarados y las sesiones de esta máquina que lo trabajaron. Una sesión queda ligada cuando escribe el Change MD o corre `vincular` con su ruta.
- **Qué no guarda: los commits.** `/logbook traza <nombre>` los lee de git al consultar, por el trailer `Req:` o `Confirmacion-autonoma:`, en cada repo declarado; después de un push, la siguiente `traza` ya los trae. Igual que la receta de [`../process/version-control.md`](../process/version-control.md) § "Trailer `Req:` — del commit al REQ", no ve lo que otro dev publicó sin `git fetch`.
- **Solo local.** No viaja al central, no crea ni cambia works y no archiva nada.
- **Desvincular.** `/logbook desvincular <id|nombre|ruta>` quita un REQ vinculado por error, con sus repos y sesiones. Para quitar un repo mal declarado, desvincula y vuelve a vincular.

La mecánica (cuándo corre, límite de tiempo, modos de fallo) vive en [`../tooling/logbook.md`](../tooling/logbook.md) § "Captura (hook `logbook-sync`)"; los verbos, en [`../skills/logbook/SKILL.md`](../skills/logbook/SKILL.md).

## Entorno compartido (disparador opt-in por proyecto)

El entorno es **compartido** —el trabajo se publica al catálogo central— **solo** cuando se cumplen las dos condiciones; el disparador es **determinista** y **opt-in por proyecto**:

- hay `NEB_LOGBOOK_ENDPOINT` configurado, **y**
- el proyecto lo declara explícitamente con el marcador `<!-- neb-logbook: central -->` en su `CLAUDE.md` (el hook lo lee antes de publicar; análogo a `<!-- neb-profile: none -->`).

Sin endpoint o sin marcador → la bitácora queda **local-only**, que es el **default**: la bitácora local ya cubre el relevo del propio dev ([`pendings.md`](pendings.md) § "Sesiones pausadas" + `--resume`), y el central se reserva a los proyectos que deliberadamente comparten su trabajo con el equipo (relevo cross-dev). *(Opt-in por perfil: requerimiento futuro.)*

El filtro rige también al drenar el outbox de la máquina: sale solo lo que tiene opt-in propio (el work de un REQ, por su repo; el exploratorio, por el dir donde arrancó su sesión) — regla completa en [`../tooling/logbook.md`](../tooling/logbook.md) § "Backend central — contrato y disparador", que además separa **qué se publica** (el marcador) de **contra qué opera el CLI** `/logbook` (las variables).

Publicar el `work` a un entorno compartido **habilita la Entrega temprana del registro** (ver "Relación con otros artefactos" abajo).

## Entrada de la bitácora

Se **deriva** de la memoria del proyecto (los `active_<proyecto>_<slug>.md` — uno por REQ — y su "Pendiente de entrega"); la bitácora es su **proyección publicada al equipo**. Contiene:

- Metadatos: `project`, `req_slug`, `owner`, `lock_state`, estado del REQ, `branch`, `head_commit`, `origin_machine`, `claude_session_id` (válido solo en su máquina origen).
- Estado semántico (`payload_json`): plan resumido, archivos, próximos pasos y "Pendiente de entrega". El **Trabajo en vuelo** de un relevo —prosa sobre **cómo relanzar** agentes/scripts— y sus próximos pasos no viajan aquí: viven en `## Relevo` del Change MD al que la entrada apunta ([`changes.md`](changes.md) § "Relevo").
- Transcript: solo la referencia local (`transcript_path`), informativa y válida en la máquina de origen. De la conversación, la bitácora solo guarda, y con opt-in sube al central, el resumen del exploratorio (los primeros 120 caracteres del primer mensaje); el resto no se guarda ni viaja.

El esquema concreto (SQLite local / central) vive en [`../hooks/logbook-schema.sql`](../hooks/logbook-schema.sql); la plantilla de entrada en [`../templates/logbook-entry.md.template`](../templates/logbook-entry.md.template).

## Ciclo de vida

| Momento | Acción |
|---|---|
| Sesión en curso | El hook publica/actualiza la entrada en cada `Stop`/`SessionEnd`/`PreCompact` (ver [`../tooling/logbook.md`](../tooling/logbook.md)) |
| Relevo | Otro dev `tomar`/`solicitar` el mando; retoma en sesión nueva (ver protocolo en `execution.md`) |
| Cierre del REQ | El `work` se marca `archived` (`/logbook archivar <id>`) — **se preserva, no se borra** (historial de auditoría). El borrado real es purga intencional del backend central |

## Relación con otros artefactos (frontera, no duplicar)

- [`pendings.md`](pendings.md) § "Sesiones pausadas" + `--resume`: reanudar **la propia sesión local** (mismo dev, misma máquina). La bitácora **no lo reemplaza** — lo complementa con el **relevo cross-dev** y, en modo exploratorio, automatiza el registro para `--resume`.
- [`memory.md`](memory.md) (`active_<proyecto>_<slug>.md` — uno por REQ — y su "Pendiente de entrega"): estado vivo del REQ en la máquina del dev. La bitácora lo deriva.
- [`changes.md`](changes.md): el Change MD (registro del requerimiento — ver [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Registro del requerimiento") da la trazabilidad del REQ; la entrada de bitácora **apunta** a él, no lo duplica. Con el `work` publicado a una bitácora **compartida** (backend central, relevo cross-dev), su registro debe estar **entregado** (en git: pusheado) para que el puntero resuelva en la máquina que releva: es la **Entrega temprana del registro** ([`changes.md`](changes.md) § "Ciclo de vida del draft"). En backend local-only el registro sigue el ciclo por defecto, salvo al relevar: ahí se entrega de inmediato junto con su plan aprobado.
