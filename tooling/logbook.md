# Bitácora de relevo — backend y captura (opcional)

Recurso del hook que alimenta la [bitácora de relevo](../workflow/logbook.md). De activación voluntaria por proyecto (no se auto-registra). El artefacto y su modelo de ownership viven en [`../workflow/logbook.md`](../workflow/logbook.md); el protocolo de uso en [`../process/execution.md`](../process/execution.md) §"Gestión de sesiones (handoff)"; aquí la mecánica.

## Backend pluggable

- **`local` (por defecto):** SQLite en `~/.claude/neb.db` (esquema en [`../hooks/logbook-schema.sql`](../hooks/logbook-schema.sql); WAL — una escritura interrumpida se revierte sola). Universal, sin infra. Es además **outbox** del central. **Resolver dual-mode permanente** (`hooks/lib/_db_shared.resolve_db_path`): prefiere `neb.db` si es usable, y cae a `neb-logbook.db` (nombre legado) en máquinas del equipo sin migrar — el hook opera sin cambios aunque no se corra `bootstrap/migrate-neb-db.py`. La migración del nombre canónico es one-shot del maintainer e idempotente.
- **`central` (opcional):** backend central distribuido en un repositorio dedicado (stdlib `http.server` + PyMySQL) + API HTTP sobre MariaDB. Autoridad del lock + corpus buscable; habilita el relevo cross-dev real. Instalación y exposición: ver el repositorio del backend central. Config del cliente: `NEB_LOGBOOK_ENDPOINT` + **`NEB_LOGBOOK_TOKEN`** por env (nunca en `.md` ni en `personal/`).

## Backend central — contrato y disparador (opcional)

- **Contrato HTTP** (auth `Authorization: Bearer <NEB_LOGBOOK_TOKEN>`): `publish` (UPSERT por identidad, el lock gobierna la escritura → `409` si el owner entrante no es el vigente; `payload_version` optimista; **`req_state` viaja normalizado al ENUM** de [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Estados del requerimiento" — `VARCHAR(64)` en el central — y la prosa que acompaña al `Estado:` en la memoria va en `payload_json.req_state_note`; la bitácora local conserva el texto completo; un `Estado:` que no empiece por un valor del ENUM se publica como `NULL`), `claim`/`release`/`request-takeover`/`forced-release` (lock atómico, solo works `req`; `400` sobre exploratory), `rename` (migra `req_slug`/`project` preservando historial), `archive` (cierre del REQ → `archived_at`; no borra), `transcript` (fragmento idempotente por `session_id,byte_from,byte_to`), `search` (FULLTEXT), `work`/`work/{id}`. Detalle: docstring de `logbook_server.py` en el repositorio del backend central.
- **Disparador determinista (de activación voluntaria por proyecto)**: el cliente publica al central **solo** cuando hay `NEB_LOGBOOK_ENDPOINT` **y** el proyecto lo declara con el marcador `<!-- neb-logbook: central -->` en su `CLAUDE.md` (lectura barata antes de spawnear el sync). Sin marcador → local-only (el comportamiento por defecto; la bitácora local ya cubre el relevo del propio dev). *(Activación voluntaria por perfil: futuro.)*
- **Reconciliación (409)**: un `publish` rechazado marca el `work` local `conflict=1, dirty=0` (corta el reintento ciego) y deja el motivo en `last_error`/`last_error_at`; `/logbook` lo reporta (aviso al listar + `estado-sync`); el aviso se apaga con la siguiente captura que vuelva a publicar con `200` y `claim`/`forzar` lo reconcilia. Nunca last-writer-wins.
- **Fallos de sync (todo lo que no sea `200` ni `409`)**: sin respuesta, `4xx` o `5xx` **no cortan el reintento** —`dirty` se conserva y el siguiente sync vuelve a intentar— pero dejan de ser mudos: el fallo vigente se persiste por canal en el `work` local, `last_error`/`last_error_at` (publicación) y `transcript_error`/`transcript_error_at` (subida del transcript). `*_at` marca **desde cuándo** falla: no se reescribe mientras el texto del error sea el mismo. Cada canal escribe y limpia solo su par, así que un fallo de transcript no pisa la causa de un rechazo de publicación. Se limpia por canal: el de publicación, con el primer `200`; el de transcript, con un `200` **o cuando ya no hay nada que reintentar** (el `.jsonl` ya no existe o está al día) — que el aviso desaparezca no implica que el transcript se haya subido. Cuando la causa se corrige en el central, el work se publica sin intervención. Un `200` que no trae `remote_id` no cuenta como publicación (se registra como fallo). Lo expone `logbook.py sync-status` (`/logbook estado-sync`), que lee siempre la DB local. El conflicto corta el reintento porque exige una decisión humana; un fallo de sync no, porque su causa está fuera del work.
- **`req_slug` rename gobernado**: `/logbook rename <id> <new_slug>` migra la fila en el central (preserva `event`/`transcript`); sin el comando, un slug nuevo bifurca (crea otro work).

## Captura (hook `logbook-sync`)

- Eventos: **`Stop`** (cada turno) + **`SessionEnd`** (cierre graceful) + **`PreCompact`** (antes de compactar).
- Deriva el estado del **REQ activo** de la memoria del proyecto (mismo lookup que `usage-tracker`); si no hay REQ → registra **sesión exploratoria** liviana (para `--resume` local).
- Guarda estado + `transcript_path` localmente. Si el entorno es compartido, la captura lanza un **sync detached** (`logbook.py sync`, best-effort) que drena el outbox y sube el **contenido del transcript incremental** (`text_plain` excluye `tool_result` y líneas estructurales — no indexa secretos de salidas). El cursor del transcript vive en la misma transacción SQLite (no en archivo plano — un corte lo corrompería).
- **Terminación abrupta:** ningún hook garantiza correr ante SIGKILL/corte de luz → se conserva hasta el último turno (`Stop`) completado. El corte de **red** no pierde nada (el estado queda local; el push al central se difiere por el outbox) y queda visible en `estado-sync`.

## Semántica degradada del lock en local-only

Con solo SQLite local (un dev, una DB): `tomar`/`liberar` son **informativos** (recordatorio de estado); **`solicitar el mando` y `search` no aplican** sin central. El relevo cross-dev real (lock atómico, búsqueda de texto completo) requiere el backend central.

## Retención

Un `work` cerrado se **archiva** (`archived_at`), no se borra — preserva el corpus para auditoría futura. El borrado real es purga **intencional y manual** del central: el `purge.py --before <fecha> [--apply]` del backend central (`--dry-run` por defecto; ver la doc de su repositorio § Retención).

## Activación

De activación voluntaria por proyecto en `<proyecto>/.claude/settings.json` (ver [`../hooks/settings.template.json`](../hooks/settings.template.json) y [`../hooks/README.md`](../hooks/README.md) §logbook-sync). **Windows**: `"shell": "powershell"` con `logbook-sync.ps1` (el hook combina stdin + variables de entorno).

## Modos de fallo (defensivo)

- Sin Python → warning a stderr, `exit 0`.
- Sin REQ activo → registra sesión exploratoria (no falla).
- DB inaccesible o error → `exit 0` (nunca bloquea el turno).
- El central rechaza o no responde → `exit 0`, el reintento sigue y el fallo queda persistido en el `work` (ver § "Backend central" → *Fallos de sync*). El `stderr` del sync detached y del hook se descarta: por eso el fallo se **persiste** además de imprimirse. Registrar el fallo nunca interrumpe el drenaje de los demás works.
- `sync` invocado a mano sin central configurado → avisa por `stderr` en vez de salir mudo.

## Requisitos

Python 3 (`py` / `python` / `python3`) con `sqlite3` (stdlib). `NEB_HOME` para localizar el módulo y el esquema.
