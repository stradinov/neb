# Bitácora de relevo — backend y captura (opcional)

Recurso del hook que alimenta la [bitácora de relevo](../workflow/logbook.md). Lo registra el plugin y es de activación voluntaria (`NEB_HOOKS` / `NEB_PROJECT_HOOKS`, § "Activación"). El artefacto y su modelo de ownership viven en [`../workflow/logbook.md`](../workflow/logbook.md); el protocolo de uso en [`../process/execution.md`](../process/execution.md) § "Gestión de sesiones (handoff)"; aquí la mecánica.

## Backend pluggable

- **`local` (por defecto):** SQLite en `~/.claude/neb.db` (esquema inicial en [`../hooks/logbook-schema.sql`](../hooks/logbook-schema.sql) más los pasos de base de [`migrations.md`](migrations.md); WAL — una escritura interrumpida se revierte sola). Universal, sin infra. Es además **outbox** del central. **Resolver dual-mode permanente** (`hooks/lib/_db_shared.resolve_db_path`): prefiere `neb.db` si es usable, y cae a `neb-logbook.db` (nombre legado) en máquinas del equipo sin migrar — el hook opera sin cambios aunque no se corra `bootstrap/migrate-neb-db.py`. La migración del nombre canónico es one-shot del maintainer e idempotente.
- **`central` (opcional):** backend central distribuido en un repositorio dedicado (stdlib `http.server` + PyMySQL) + API HTTP sobre MariaDB. Autoridad del lock y catálogo de works; habilita el relevo cross-dev real. Instalación y exposición: ver el repositorio del backend central. Config del cliente: `NEB_LOGBOOK_ENDPOINT` + **`NEB_LOGBOOK_TOKEN`** por env (nunca en `.md` ni en `personal/`). Son dos decisiones distintas: **qué se publica** lo decide el marcador (§ "Backend central — contrato y disparador"); **contra qué opera el CLI** `/logbook` lo deciden las variables: con endpoint **y** token, el CLI lee y escribe en el central en **cualquier** proyecto (lo que no tiene opt-in no está ahí, salvo lo que se publicó antes de 6.14.2). **Modo local**: endpoint o token vacío o ausente → nada sale y el CLI opera sobre el SQLite local, aunque el proyecto traiga el marcador. Para una consulta suelta basta el prefijo `NEB_LOGBOOK_ENDPOINT=` en la llamada (bash/Git Bash, como el skill invoca el CLI); para toda la máquina, vacíala en la fuente donde la definiste.

## Backend central — contrato y disparador (opcional)

- **Contrato HTTP** (auth `Authorization: Bearer <NEB_LOGBOOK_TOKEN>`): `publish` (UPSERT por identidad, el lock gobierna la escritura → `409` si el owner entrante no es el vigente; `payload_version` optimista; **`req_state` viaja normalizado al ENUM** de [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Estados del requerimiento" — `VARCHAR(64)` en el central — y la prosa que acompaña al `Estado:` en la memoria va en `payload_json.req_state_note`; la bitácora local conserva el texto completo; un `Estado:` que no empiece por un valor del ENUM se publica como `NULL`), `claim`/`release`/`request-takeover`/`forced-release` (lock atómico, solo works `req`; `400` sobre exploratory), `rename` (migra `req_slug`/`project` preservando historial), `archive` (cierre del REQ → `archived_at`; no borra), `work`/`work/{id}`. Detalle: docstring de `logbook_server.py` en el repositorio del backend central.
- **Disparador determinista (de activación voluntaria por proyecto)**: el cliente publica al central **solo** cuando hay `NEB_LOGBOOK_ENDPOINT` **y** el proyecto lo declara con el marcador `<!-- neb-logbook: central -->` en su `CLAUDE.md` (lectura barata antes de spawnear el sync). Sin marcador → local-only (el comportamiento por defecto; la bitácora local ya cubre el relevo del propio dev). *(Activación voluntaria por perfil: futuro.)*
- **El opt-in rige también al drenar**: el sync lo lanza un proyecto con marcador, pero el outbox es de toda la máquina, así que cada elemento se filtra por su propio opt-in:
  - **Work de un REQ**: sale si su repo trae el marcador. El repo es el primer path absoluto del campo «Path del proyecto» de la memoria, que puede ir con texto alrededor (`` `C:\…\repo` (rama `main`) ``). Sin path absoluto (vacío o relativo) queda local; una ruta con espacios solo se reconoce entre comillas o backticks (sin ellas se corta en el primer espacio y también queda local).
  - **Work exploratorio**: sale si su sesión **arrancó** en un dir con marcador (el primer `cwd` del `.jsonl`, que se guarda en `session_sync.root_cwd`; no el `cwd` del momento, que cambia con los `cd`).
  - Cuenta solo el `CLAUDE.md` del dir exacto (sin heredar padres, como el disparador). Sin `cwd` de arranque conocido, nada sale.
  - Lo que no tiene opt-in queda local (`dirty`) y no aparece en `estado-sync`, que dice en `notes` cuántos works quedan así. Si después el repo o el dir gana el marcador, sale el estado vigente del work. Lo publicado antes de tener este filtro no se toca: purgarlo es decisión del backend central (§ "Retención").
- **Reconciliación (409)**: un `publish` rechazado marca el `work` local `conflict=1, dirty=0` (corta el reintento ciego) y deja el motivo en `last_error`/`last_error_at`; `/logbook` lo reporta (aviso al listar + `estado-sync`); el aviso se apaga con la siguiente captura que vuelva a publicar con `200` y `claim`/`forzar` lo reconcilia. Nunca last-writer-wins.
- **Fallos de sync (todo lo que no sea `200` ni `409`)**: sin respuesta, `4xx` o `5xx` **no cortan el reintento** —`dirty` se conserva y el siguiente sync vuelve a intentar— pero dejan de ser mudos: el fallo vigente se persiste en `last_error`/`last_error_at` del `work` local. `last_error_at` marca **desde cuándo** falla: no se reescribe mientras el texto del error sea el mismo. Se limpia con el primer `200`. Cuando la causa se corrige en el central, el work se publica sin intervención. Un `200` que no trae `remote_id` no cuenta como publicación (se registra como fallo). Lo expone `logbook.py sync-status` (`/logbook estado-sync`), que lee siempre la DB local. El conflicto corta el reintento porque exige una decisión humana; un fallo de sync no, porque su causa está fuera del work.
- **`req_slug` rename gobernado**: `/logbook rename <id> <new_slug>` migra la fila en el central (preserva `event`); sin el comando, un slug nuevo bifurca (crea otro work).

## Captura (hook `logbook-sync`)

- Eventos: **`Stop`** (cada turno) + **`SessionEnd`** (cierre graceful) + **`PreCompact`** (antes de compactar).
- Deriva el estado del **REQ activo** de la memoria del proyecto (`find_active_reqs` de `hooks/lib/_db_shared.py`); si no hay REQ → registra **sesión exploratoria** liviana (para `--resume` local).
- Guarda estado + `transcript_path` localmente; de la conversación solo se guarda, y con opt-in se sube, el resumen del exploratorio (los primeros 120 caracteres del primer mensaje); el resto no se guarda ni se sube. Si el entorno es compartido, la captura lanza un **sync detached** (`logbook.py sync`, best-effort) que drena el outbox.
  - **Registro de sesión** (`session_sync`): una fila por sesión con la ruta del `.jsonl`, el `cwd` con el que arrancó (`root_cwd`, opt-in de los exploratorios) y el cursor de lectura (`read_byte`): cada captura lee solo el tramo nuevo del `.jsonl`, que consume el REQ vinculado, y no lo persiste.
  - **Un sync a la vez** por máquina: evita que dos syncs publiquen el mismo work.
- **REQ vinculado** ([`../workflow/logbook.md`](../workflow/logbook.md) § "REQ vinculado"): en `Stop` y `PreCompact`, después del commit de la captura, liga la sesión a los REQ vinculados cuyo Change MD escribió en el tramo, o sobre los que corrió `vincular` (`link <ruta>`), y registra los nuevos. Tiene un límite de 4 s y nunca corre `git log`: las únicas llamadas a git son 2 por REQ nuevo, para ubicar su repo y su `origin`; un REQ ya registrado no vuelve a llamar a git, y uno que no se pudo registrar (sin `origin`, o con el mismo nombre ya vinculado con otra fecha) las repite en cada captura cuyo tramo traiga esa escritura, dentro del mismo límite. En `SessionEnd` no corre. Si el tramo trae 3 o más Change MD sin vincular, no registra ninguno (barrido) y solo liga los ya vinculados.
- **Terminación abrupta:** ningún hook garantiza correr ante SIGKILL/corte de luz → se conserva hasta el último turno (`Stop`) completado. El corte de **red** no pierde nada (el estado queda local; el push al central se difiere por el outbox) y queda visible en `estado-sync`.

## Semántica degradada del lock en local-only

Con solo SQLite local (un dev, una DB): `tomar`/`liberar` son **informativos** (recordatorio de estado); **`solicitar el mando` no aplica** sin central. `renombrar` y `archivar` operan sobre la DB local. El relevo cross-dev real (lock atómico) requiere el backend central.

## Retención

Un `work` cerrado se **archiva** (`archived_at`), no se borra — preserva el historial para auditoría futura. El borrado real es purga **intencional y manual** del central: el `purge.py --before <fecha> [--apply]` del backend central (`--dry-run` por defecto; ver la doc de su repositorio § "Retención").

## Activación

De activación voluntaria: el plugin registra el hook, y corre si `logbook-sync` está en `NEB_HOOKS` (personal: `env` de `~/.claude/settings.json` o del `settings.local.json` del proyecto) o en `NEB_PROJECT_HOOKS` (`env` del `.claude/settings.json` versionado del proyecto). Ver [`../hooks/README.md`](../hooks/README.md) § "Bajo el plugin de Neb". En Windows requiere Git Bash. Una entrada de settings con clon (`logbook-sync.ps1` con `"shell": "powershell"`, o `logbook-sync.sh`) sigue funcionando; no la combines con la variable, o corre dos veces.

## Modos de fallo (defensivo)

- Sin Python → warning a stderr, `exit 0`.
- Sin REQ activo → registra sesión exploratoria (no falla).
- DB inaccesible o error → `exit 0` (nunca bloquea el turno).
- Base que este código ya no puede operar, o paso de base detenido sin `espera` → la captura no escribe y el CLI responde `ok: false` con el motivo (un paso detenido con `espera` deja operar la base en su versión); como el `stderr` se descarta, lo dicen el arranque y `neb-migrate.py status` ([`migrations.md`](migrations.md)).
- El central rechaza o no responde → `exit 0`, el reintento sigue y el fallo queda persistido en el `work` (ver § "Backend central" → *Fallos de sync*). El `stderr` del sync detached y del hook se descarta: por eso el fallo se **persiste** además de imprimirse. Registrar el fallo nunca interrumpe el drenaje de los demás works.
- `sync` invocado a mano sin central configurado → avisa por `stderr` en vez de salir mudo.
- REQ vinculado (§ "Captura (hook `logbook-sync`)"):
  - Un fallo del vínculo no afecta la captura, que ya está confirmada; la evidencia de sesión de ese tramo se pierde y `vincular` la restituye.
  - Base bloqueada o límite de 4 s vencido → la escritura se omite; la liga de sesión y el registro de ese tramo se pierden, y `vincular` los restituye.
  - Esas omisiones (barrido, choque de fecha —el `nombre` ya vinculado con otra fecha en el mismo `project`—, límite vencido, base bloqueada, falla del vínculo) no dejan rastro visible: su aviso solo va a `stderr`, que el hook descarta. Con `link`, el choque de fecha sí se ve: responde `ok: false` con el motivo.
  - En `traza`, un repo cuyo git falla o tarda más de 5 s sale con su nota y no tumba la consulta.

## Requisitos

Python 3 (`py` / `python` / `python3`) con `sqlite3` (stdlib). Además, git ≥ 2.31 en el `PATH` para registrar un REQ vinculado por escritura y para los commits de `traza`; sin git, nada se registra por escritura, `traza` sale con la nota de error en cada repo y la captura sigue igual. La captura del hook usa el módulo del plugin cargado. El CLI (`/logbook`, `/pendings-review`) y los wrappers de una entrada de settings usan el clon de `NEB_HOME` si lo hay (un `NEB_HOME` que apunte al caché del plugin se ignora). Cada módulo usa el esquema de su propio árbol: si plugin y clon traen versiones distintas, los dos operan la base mientras la entiendan, y el que ya no la entiende no la toca y lo avisa el arranque ([`migrations.md`](migrations.md) § "Versión y compatibilidad").
