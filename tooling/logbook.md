# Bitácora de relevo — backend y captura (opt-in)

Recurso del hook que alimenta la [bitácora de relevo](../workflow/logbook.md). Opt-in por proyecto (no se auto-registra). El artefacto y su modelo de ownership viven en [`../workflow/logbook.md`](../workflow/logbook.md); el protocolo de uso en [`../process/execution.md`](../process/execution.md) §"Gestión de sesiones (handoff)"; aquí la mecánica.

## Backend pluggable

- **`local` (default):** SQLite en `~/.claude/neb-logbook.db` (esquema en [`../hooks/logbook-schema.sql`](../hooks/logbook-schema.sql); WAL — una escritura interrumpida se revierte sola). Universal, sin infra. Es además **outbox** del central.
- **`central` (opcional, REQ B):** servidor de referencia + API HTTP. Habilita relevo cross-dev real (lock atómico, transcript buscable). Config: endpoint en el workspace del equipo; **token en la env var `NEB_LOGBOOK_TOKEN`** (nunca en `.md` ni en `personal/`).

## Captura (hook `logbook-sync`)

- Eventos: **`Stop`** (cada turno) + **`SessionEnd`** (cierre graceful) + **`PreCompact`** (antes de compactar).
- Deriva el estado del **REQ activo** de la memoria del proyecto (mismo lookup que `usage-tracker`); si no hay REQ → registra **sesión exploratoria** liviana (para `--resume` local).
- Guarda estado + `transcript_path` (no el contenido — eso lo sube el sync al central en REQ B). El cursor del transcript vive en la misma transacción SQLite (no en archivo plano — un corte lo corrompería).
- **Terminación abrupta:** ningún hook garantiza correr ante SIGKILL/corte de luz → se conserva hasta el último turno (`Stop`) completado. El corte de **red** no pierde nada (el estado queda local; el push al central se difiere por el outbox).

## Semántica degradada del lock en local-only

Con solo SQLite local (un dev, una DB): `tomar`/`liberar` son **informativos** (recordatorio de estado); **`solicitar el mando` y `search` no aplican** sin central. El relevo cross-dev real (lock atómico, búsqueda full-text) requiere el backend central.

## Retención

Un `work` cerrado se **archiva** (`archived_at`), no se borra — preserva el corpus para auditoría futura. El borrado real es purga intencional.

## Activación

Opt-in por proyecto en `<proyecto>/.claude/settings.json` (ver [`../hooks/settings.template.json`](../hooks/settings.template.json) y [`../hooks/README.md`](../hooks/README.md) §logbook-sync). **Windows**: `"shell": "powershell"` con `logbook-sync.ps1` (el hook combina stdin + variables de entorno).

## Modos de fallo (defensivo)

- Sin Python → warning a stderr, `exit 0`.
- Sin REQ activo → registra sesión exploratoria (no falla).
- DB inaccesible o error → `exit 0` (nunca bloquea el turno).

## Requisitos

Python 3 (`py` / `python` / `python3`) con `sqlite3` (stdlib). `NEB_HOME` para localizar el módulo y el esquema.
