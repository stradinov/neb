# Bitácora de relevo — backend y captura (opt-in)

Recurso del hook que alimenta la [bitácora de relevo](../workflow/logbook.md). Opt-in por proyecto (no se auto-registra). El artefacto y su modelo de ownership viven en [`../workflow/logbook.md`](../workflow/logbook.md); el protocolo de uso en [`../process/execution.md`](../process/execution.md) §"Gestión de sesiones (handoff)"; aquí la mecánica.

## Backend pluggable

- **`local` (default):** SQLite en `~/.claude/neb.db` (esquema en [`../hooks/logbook-schema.sql`](../hooks/logbook-schema.sql); WAL — una escritura interrumpida se revierte sola). Universal, sin infra. Es además **outbox** del central. **Resolver dual-mode permanente** (`hooks/lib/_db_shared.resolve_db_path`): prefiere `neb.db` si es usable, y cae a `neb-logbook.db` (nombre legado) en máquinas del equipo sin migrar — el hook opera sin cambios aunque no se corra `bootstrap/migrate-neb-db.py`. La migración del nombre canónico es one-shot del maintainer e idempotente.
- **`central` (opcional):** servidor de referencia en [`../server/`](../server/logbook_server.py) (stdlib `http.server` + PyMySQL) + API HTTP sobre MariaDB. Autoridad del lock + corpus buscable; habilita el relevo cross-dev real. Instalación y exposición: [`../server/INSTALL.md`](../server/INSTALL.md). Config del cliente: `NEB_LOGBOOK_ENDPOINT` + **`NEB_LOGBOOK_TOKEN`** por env (nunca en `.md` ni en `personal/`).

## Backend central — contrato y disparador (opt-in)

- **Contrato HTTP** (auth `Authorization: Bearer <NEB_LOGBOOK_TOKEN>`): `publish` (UPSERT por identidad, el lock gobierna la escritura → `409` si el owner entrante no es el vigente; `payload_version` optimista), `claim`/`release`/`request-takeover`/`forced-release` (lock atómico, solo works `req`; `400` sobre exploratory), `rename` (migra `req_slug`/`project` preservando historial), `archive` (cierre del REQ → `archived_at`; no borra), `transcript` (fragmento idempotente por `session_id,byte_from,byte_to`), `search` (FULLTEXT), `work`/`work/{id}`. Detalle: docstring de [`../server/logbook_server.py`](../server/logbook_server.py).
- **Disparador determinista (opt-in por proyecto)**: el cliente publica al central **solo** cuando hay `NEB_LOGBOOK_ENDPOINT` **y** el proyecto lo declara con el marcador `<!-- neb-logbook: central -->` en su `CLAUDE.md` (lectura barata antes de spawnear el sync). Sin marcador → local-only (el default; la bitácora local ya cubre el relevo del propio dev). *(Opt-in por perfil: futuro.)*
- **Reconciliación (409)**: un `publish` rechazado marca el `work` local `conflict=1, dirty=0` (corta el reintento ciego); `/logbook` lo reporta y `claim`/`forzar` lo reconcilia. Nunca last-writer-wins.
- **`req_slug` rename gobernado**: `/logbook rename <id> <new_slug>` migra la fila en el central (preserva `event`/`transcript`); sin el comando, un slug nuevo bifurca (crea otro work).

## Captura (hook `logbook-sync`)

- Eventos: **`Stop`** (cada turno) + **`SessionEnd`** (cierre graceful) + **`PreCompact`** (antes de compactar).
- Deriva el estado del **REQ activo** de la memoria del proyecto (mismo lookup que `usage-tracker`); si no hay REQ → registra **sesión exploratoria** liviana (para `--resume` local).
- Guarda estado + `transcript_path` localmente. Si el entorno es compartido, la captura lanza un **sync detached** (`logbook.py sync`, best-effort) que drena el outbox y sube el **contenido del transcript incremental** (`text_plain` excluye `tool_result` y líneas estructurales — no indexa secretos de outputs). El cursor del transcript vive en la misma transacción SQLite (no en archivo plano — un corte lo corrompería).
- **Terminación abrupta:** ningún hook garantiza correr ante SIGKILL/corte de luz → se conserva hasta el último turno (`Stop`) completado. El corte de **red** no pierde nada (el estado queda local; el push al central se difiere por el outbox).

## Semántica degradada del lock en local-only

Con solo SQLite local (un dev, una DB): `tomar`/`liberar` son **informativos** (recordatorio de estado); **`solicitar el mando` y `search` no aplican** sin central. El relevo cross-dev real (lock atómico, búsqueda full-text) requiere el backend central.

## Retención

Un `work` cerrado se **archiva** (`archived_at`), no se borra — preserva el corpus para auditoría futura. El borrado real es purga **intencional y manual** del central: `server/purge.py --before <fecha> [--apply]` (`--dry-run` por default; ver [`../server/INSTALL.md`](../server/INSTALL.md) § Retención).

## Activación

Opt-in por proyecto en `<proyecto>/.claude/settings.json` (ver [`../hooks/settings.template.json`](../hooks/settings.template.json) y [`../hooks/README.md`](../hooks/README.md) §logbook-sync). **Windows**: `"shell": "powershell"` con `logbook-sync.ps1` (el hook combina stdin + variables de entorno).

## Modos de fallo (defensivo)

- Sin Python → warning a stderr, `exit 0`.
- Sin REQ activo → registra sesión exploratoria (no falla).
- DB inaccesible o error → `exit 0` (nunca bloquea el turno).

## Requisitos

Python 3 (`py` / `python` / `python3`) con `sqlite3` (stdlib). `NEB_HOME` para localizar el módulo y el esquema.
