# Bitácora de relevo (logbook)

Registro de trabajos a medias para **relevo entre devs y máquinas**. Cubre el caso que `pendings.md` §"Sesiones pausadas" y la memoria del proyecto no cubren: una sesión interrumpida (tokens agotados, corte de energía/internet, o handoff a otro dev) que debe continuar **en otra máquina con otra cuenta**, conservando el contexto vía el transcript.

La **mecánica** (backend pluggable, hook de captura, config, modos de fallo) vive en [`../tooling/logbook.md`](../tooling/logbook.md); el **protocolo operativo** (pasos para publicar/retomar/relevar) en [`../process/execution.md`](../process/execution.md) §"Gestión de sesiones (handoff)". Este archivo cubre el **artefacto**: su modelo, ciclo de vida y relación con el resto.

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

Este ENUM de lock es **ortogonal** al ENUM de estados del requerimiento ([`../methodology/vocabulary.md`](../methodology/vocabulary.md) §"Estados del requerimiento"): un `work` `archived` no altera el estado canónico del REQ.

## Dos modos

| Modo | Cuándo | Identidad | Reanudación |
|---|---|---|---|
| **Con-REQ** | hay ≥1 `active_<proyecto>_<slug>.md` en memoria (o sección legacy) | `project + req_slug` | **relevo cross-dev** (lock atómico); estado + transcript al central |
| **Exploratorio** | sin REQ formal (exploración previa) | `session_id` (entrada liviana, sin lock) | **`--resume` local** del mismo dev. Si el proyecto activa el central (opt-in), también se publica al catálogo (visibilidad/búsqueda); **no** relevable cross-dev (`claude_session_id` solo vale en su máquina origen) |

El modo exploratorio registra automáticamente la sesión (aunque el dev no anuncie pausa) con un resumen y el `transcript_path` local, para que `/logbook` la localice entre muchas y entregue el comando `--resume`. **Si el proyecto activa el central (opt-in)**, la sesión exploratoria también se publica al catálogo —para visibilidad y búsqueda del corpus—, pero **no es relevable cross-dev**: que **otro** dev la retome exige formalizarla en REQ antes. Al **formalizarse en REQ**, se vincula a un `work` `req` y entra al relevo cross-dev con lock.

## Entorno compartido (disparador opt-in por proyecto)

El **disparador** de "entorno compartido" es **determinista** y **opt-in por proyecto**: el trabajo se publica al catálogo central **solo** cuando hay `NEB_LOGBOOK_ENDPOINT` configurado **y** el proyecto lo declara explícitamente con el marcador `<!-- neb-logbook: central -->` en su `CLAUDE.md` (el hook lo lee antes de publicar; análogo a `<!-- neb-profile: none -->`). Sin endpoint o sin marcador → la bitácora queda **local-only**, que es el **default**. El default es local porque la **bitácora local (REQ A) ya cubre el relevo del propio dev** ([`pendings.md`](pendings.md) §"Sesiones pausadas" + `--resume`); el central se reserva a los proyectos que deliberadamente comparten su trabajo con el equipo (relevo cross-dev + corpus buscable). *(Opt-in por perfil: requerimiento futuro.)* Publicar el `work` a un entorno compartido **habilita la Entrega temprana del registro** (ver "Relación con otros artefactos" abajo).

## Entrada de la bitácora

Se **deriva** de la memoria del proyecto (los `active_<proyecto>_<slug>.md` — uno por REQ — y su "Pendiente de entrega"; fuente de verdad); la bitácora es su **proyección publicada al equipo**, no una segunda fuente. Contiene:

- Metadatos: `project`, `req_slug`, `owner`, `lock_state`, estado del REQ, `branch`, `head_commit`, `origin_machine`, `claude_session_id` (válido solo en su máquina origen).
- Estado semántico (`payload_json`): plan resumido, archivos, próximos pasos, "Pendiente de entrega", y **Trabajo en vuelo** — prosa que el agente redacta al pausar sobre **cómo relanzar** agentes/scripts (no se introspecta el proceso: ver [`../process/execution.md`](../process/execution.md) §handoff).
- Transcript: referencia local (`transcript_path`); con central, fragmentos de texto buscables (ver REQ central). Sin scrub — el contenido se preserva íntegro para reproducibilidad; el corpus es interno del equipo.

El esquema concreto (SQLite local / central) vive en [`../hooks/logbook-schema.sql`](../hooks/logbook-schema.sql); la plantilla de entrada en [`../templates/logbook-entry.md.template`](../templates/logbook-entry.md.template).

## Ciclo de vida

| Momento | Acción |
|---|---|
| Sesión en curso | El hook publica/actualiza la entrada en cada `Stop`/`SessionEnd`/`PreCompact` (ver [`../tooling/logbook.md`](../tooling/logbook.md)) |
| Relevo | Otro dev `tomar`/`solicitar` el mando; retoma en sesión nueva (ver protocolo en `execution.md`) |
| Cierre del REQ | El `work` se marca `archived` (`/logbook archivar <id>`) — **se preserva, no se borra** (corpus de auditoría). El borrado real es purga intencional del backend central |

## Relación con otros artefactos (frontera, no duplicar)

- [`pendings.md`](pendings.md) §"Sesiones pausadas" + `--resume`: reanudar **la propia sesión local** (mismo dev, misma máquina). La bitácora **no lo reemplaza** — lo complementa con el **relevo cross-dev** y, en modo exploratorio, automatiza el registro para `--resume`.
- [`memory.md`](memory.md) (`active_<proyecto>_<slug>.md` — uno por REQ — y su "Pendiente de entrega"): **fuente de verdad** local del estado del REQ. La bitácora la deriva.
- [`changes.md`](changes.md): el change MD (registro del requerimiento — ver [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Registro del requerimiento") da la trazabilidad del REQ; la entrada de bitácora **apunta** a él, no lo duplica. Si el `work` se publica a una bitácora **compartida** (backend central, relevo cross-dev), su registro debe estar **entregado** (en git: pusheado) para que el puntero resuelva en la máquina que releva — publicar el `work` a un entorno compartido **habilita la Entrega temprana del registro** (ver [`changes.md`](changes.md) § "Ciclo de vida del draft"). En backend local-only el registro sigue el ciclo por defecto.
