# Bitácora de relevo (logbook)

Base local de trabajos a medias, para retomarlos. Vive en tu máquina (`neb.db`, en la carpeta de datos de Neb: `~/.neb` o la que fije `NEB_DATA`) y guarda dos cosas: el estado de cada REQ en curso y las sesiones sin REQ, para que `/logbook` las localice y te entregue el comando para continuar. Cubre la sesión interrumpida (tokens agotados, corte de energía o de internet) que retomas en la misma máquina.

Continuar en otra máquina, o que otro dev continúe tu trabajo, no pasa por la bitácora sino por git: el Change MD con su `## Relevo`, el plan aprobado y la rama, que lee cualquiera que clone el repo; quien continúa corre `/logbook retomar <ruta-del-Change-MD>` ([`changes.md`](changes.md) § "Relevo").

La **mecánica** (hook de captura, modos de fallo) vive en [`../tooling/logbook.md`](../tooling/logbook.md); el **protocolo operativo** (pasos para retomar y relevar) en [`../process/execution.md`](../process/execution.md) § "Gestión de sesiones (handoff)". Este archivo cubre el **artefacto**: su modelo, ciclo de vida y relación con el resto.

## Unidad y backend

- **Unidad = `work`** (un trabajo a medias). Un `work` de REQ se identifica por `project + req_slug`, el mismo `<nombre>` del Change MD; no por la sesión de Claude, que cambia en cada retomada. Un `work` exploratorio se identifica por su sesión.
- **Backend**: SQLite local en `<datos>/neb.db` (la carpeta de datos de Neb), sin infraestructura; es la misma base de los pendientes ([`pendings.md`](pendings.md)). El esquema es el esquema inicial más los pasos de base ([`../tooling/migrations.md`](../tooling/migrations.md)). Si la base sigue en `~/.claude`, donde vivía hasta 7.x, la captura se detiene hasta mudarla: [`../tooling/logbook.md`](../tooling/logbook.md) § "Base sin mudar".
- **Máquina de origen** (`origin_machine`): la máquina donde se capturó el `work`. Dice dónde vale su `claude_session_id`, por si la base se copia a otra máquina.

## Dos modos

| Modo | Cuándo | Identidad | Cómo se retoma |
|---|---|---|---|
| **Con-REQ** | hay ≥1 `active_<proyecto>_<slug>.md` en memoria (o sección legacy) | `project + req_slug` | En la máquina que lo capturó: `/logbook retomar <id>` (checkout de la rama y sesión nueva con el Change MD). En otra máquina, o por otro dev: por git, con `/logbook retomar <ruta-del-Change-MD>` |
| **Exploratorio** | sin REQ formal (exploración previa) | `session_id` (entrada liviana) | **`--resume` local**: `claude_session_id` solo vale en su máquina de origen |

El modo exploratorio registra la sesión automáticamente (aunque el dev no anuncie pausa) con un resumen y el `transcript_path` local, para que `/logbook` la localice entre muchas y entregue el comando `--resume`. Para continuarla en otra máquina, o para que la continúe otro dev, hay que formalizarla antes en REQ: al formalizarse, el trabajo pasa a un `work` `req` y viaja por git con su Change MD.

## REQ vinculado

Un **REQ vinculado** es una fila de la bitácora local por cada (`project`, `nombre`) de un registro `changes/<AAAA-MM-DD>-<nombre>.md`. Responde, sin recorrer repos ni transcripts a mano, qué sesiones de esta máquina trabajaron el REQ y qué commits publicados lleva. Convive con el `work` `req` de § "Dos modos" sin tocarlo.

- **Dos vías para vincular.**
  - El hook de captura ve, en `Stop` o `PreCompact`, un `Write`, `Edit` o `MultiEdit` del hilo principal sobre el Change MD.
  - Corres `/logbook vincular <ruta>`. Con `--repo <dir>` declaras un repo adicional del REQ, uno por llamada.
- **Leer no vincula.** Leer o nombrar el Change MD no vincula nada, y escribir el plan en `changes/plans/` tampoco. Sin remoto `origin` en el repo del registro no hay vínculo. Un Incident MD se vincula como cualquier registro, con `nombre = incident-<slug>`.
- **Llave: el `nombre`** del registro, el mismo del trailer `Req:`; la fecha es dato. Un worktree o un clon del mismo remoto ligan al mismo REQ.
- **Qué guarda.** Solo lo que git no sabe: el REQ, sus repos declarados y las sesiones de esta máquina que lo trabajaron. Una sesión queda ligada cuando escribe el Change MD o corre `vincular` con su ruta.
- **Qué no guarda: los commits.** `/logbook traza <nombre>` los lee de git al consultar, por el trailer `Req:` o `Confirmacion-autonoma:`, en cada repo declarado; después de un push, la siguiente `traza` ya los trae. Igual que la receta de [`../process/version-control.md`](../process/version-control.md) § "Trailer `Req:` — del commit al REQ", no ve lo que otro dev publicó sin `git fetch`.
- **No toca los works.** No crea ni cambia works y no archiva nada.
- **Desvincular.** `/logbook desvincular <id|nombre|ruta>` quita un REQ vinculado por error, con sus repos y sesiones. Para quitar un repo mal declarado, desvincula y vuelve a vincular.

La mecánica (cuándo corre, límite de tiempo, modos de fallo) vive en [`../tooling/logbook.md`](../tooling/logbook.md) § "Captura (hook `logbook-sync`)"; los verbos, en [`../skills/logbook/SKILL.md`](../skills/logbook/SKILL.md).

## Entrada de la bitácora

Se **deriva** de la memoria del proyecto (los `active_<proyecto>_<slug>.md` —uno por REQ— y su "Pendiente de entrega"); la bitácora es su **proyección local**, que sobrevive al cierre de la sesión. Contiene:

- Metadatos: `project`, `req_slug`, estado del REQ, `branch`, `head_commit`, `repo_path`, `change_md`, `origin_machine` y `claude_session_id` (válido solo en su máquina de origen).
- Estado semántico (`payload_json`): plan resumido, archivos, próximos pasos y "Pendiente de entrega". El **Trabajo en vuelo** de un relevo —prosa sobre **cómo relanzar** agentes o scripts— y sus próximos pasos no viven aquí: viven en `## Relevo` del Change MD al que la entrada apunta ([`changes.md`](changes.md) § "Relevo").
- Transcript: solo la referencia local (`transcript_path`), válida en la máquina de origen. De la conversación, la bitácora solo guarda el resumen del exploratorio (los primeros 120 caracteres del primer mensaje); el resto no se guarda.

El esquema es el esquema inicial de [`../hooks/logbook-schema.sql`](../hooks/logbook-schema.sql) más los pasos de base de [`../tooling/migrations.md`](../tooling/migrations.md) (el vigente lo imprime `bootstrap/neb-migrate.py schema`); la forma legible de una entrada, en [`../templates/logbook-entry.md.template`](../templates/logbook-entry.md.template).

## Ciclo de vida

| Momento | Acción |
|---|---|
| Sesión en curso | El hook registra o actualiza la entrada en cada `Stop`, `SessionEnd` y `PreCompact` (ver [`../tooling/logbook.md`](../tooling/logbook.md)) |
| Relevo | Claude escribe `## Relevo` en el Change MD y entrega de inmediato el registro y su plan aprobado; en la otra máquina, o quien continúa, corre `/logbook retomar <ruta-del-Change-MD>` en una sesión nueva (protocolo en [`../process/execution.md`](../process/execution.md) § "Gestión de sesiones (handoff)") |
| Cierre del REQ | El `work` se marca `archived` (`/logbook archivar <id>`), y sus pendientes abiertos pasan a obsoletos con una nota. **Se preserva, no se borra**: ningún verbo lo borra. Archivarlo no altera el estado canónico del REQ ([`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Estados del requerimiento") |

## Relación con otros artefactos (frontera, no duplicar)

- [`pendings.md`](pendings.md) § "Sesiones pausadas" + `--resume`: reanudar por nombre **la propia sesión** en la misma máquina. La bitácora **no lo reemplaza**: lo complementa con el estado de cada REQ en curso y, en modo exploratorio, automatiza el registro para `--resume`.
- [`memory.md`](memory.md) (`active_<proyecto>_<slug>.md` —uno por REQ— y su "Pendiente de entrega"): estado vivo del REQ en la máquina del dev. La bitácora lo deriva.
- [`changes.md`](changes.md): el Change MD (registro del requerimiento; ver [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Registro del requerimiento") da la trazabilidad del REQ; la entrada de bitácora **apunta** a él, no lo duplica. El relevo a otra máquina o a otro dev viaja en el registro, no en la bitácora: al relevar, el registro y su plan aprobado se entregan de inmediato para que `retomar <ruta-del-Change-MD>` los encuentre en el repo. Esa entrega antes del cierre es la **Entrega temprana del registro** ([`changes.md`](changes.md) § "Ciclo de vida del draft"); sin relevo, el registro se entrega cuando el dev pide push o, si no, al cierre.
