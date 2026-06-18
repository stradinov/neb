# Workflow

Lineamientos concretos: qué archivos genera la metodología, dónde viven, cómo se nombran.

## Documentos

1. [Approved plans](approved-plans.md) — MD por plan aprobado (`~/.claude/approved-plans/`, no versionado).
2. [Changes](changes.md) — un change MD por requerimiento, su registro versionado (`<proyecto>/changes/`, versionado cuando el proyecto usa control de versiones).
3. [Memory](memory.md) — `project_<nombre>.md` (duradero) + `active_<proyecto>_<slug>.md` (uno por REQ activo) en memoria de Claude.
4. [Metrics](metrics.md) — métricas por requerimiento + handoff.
5. [Pendings](pendings.md) — `pendings.md` global del dev.
6. [Traceability](traceability.md) — cómo se enlazan los artefactos (plan → change MD → commits) y el modelo cross-repo.
7. [Logbook](logbook.md) — bitácora de relevo (registro cross-dev de trabajos a medias para retomar/relevar).

## Mapa rápido

| Artefacto (registro u otro) | Path | Versionado | Vida |
|---|---|---|---|
| Plan aprobado | `~/.claude/approved-plans/<ts>-<proyecto>-<slug>.md` | No | Histórico, cross-proyecto |
| Change MD (registro del requerimiento) | `<proyecto>/changes/<YYYY-MM-DD>-<nombre>.md` | Sí | Trazabilidad del proyecto |
| Memoria del proyecto (duradero) | `~/.claude/projects/.../memory/project_<nombre>.md` | No | Contexto duradero del proyecto |
| REQ activo | `~/.claude/projects/.../memory/active_<proyecto>_<slug>.md` | No | Estado vivo de un REQ (incluye "Pendiente de entrega"); uno por REQ |
| MEMORY.md (índice) | `~/.claude/projects/.../memory/MEMORY.md` | No | Index de memorias |
| Pendings del dev | `~/.claude/pendings.md` | No | Seguimiento cross-sesión |
| Incidente en prod | `<proyecto>/changes/<YYYY-MM-DD>-incident-<slug>.md` | Sí | Trazabilidad del incidente (ver [`general/incidents.md`](../general/incidents.md)) |
| Bitácora de relevo | `~/.claude/neb.db` (local) + central opcional | No | Relevo cross-dev de sesiones a medias (ver [logbook.md](logbook.md)) |

## Estados del requerimiento

El ENUM canónico de estados (`En progreso` · `En validación` · `Listo para aprobación` · `Cerrado`), el sufijo `Bloqueado` y las notas históricas viven en [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Estados del requerimiento" (es vocabulario canónico). Las transiciones especiales entre estados (qué fases se saltan según el tipo de cambio) viven en [`../process/delivery.md`](../process/delivery.md) § "Transiciones especiales de estado".
