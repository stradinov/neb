# Stack: stack-authoring

Autoría, mantenimiento y distribución de stacks de la metodología. Materializa la [promesa 6 (Expandible)](../../methodology/promises.md) — el mecanismo por el que el adoptante agrega stacks propios a la metodología sin modificar el núcleo.

## Cuándo aplica este stack

Overlay sobre `self-applied`. Se activa cuando:

- El cwd está dentro de `methodology/stacks/<nombre>/`.
- El REQ pide crear, actualizar, deprecar o auditar un stack.

Si el REQ también toca la metodología general (`general/`, `methodology/`, `process/`, `tooling/`, `workflow/`), el stack activo es `stack-authoring` para los artefactos del stack y `self-applied` para el resto. Si hay ambigüedad, anunciar y preguntar.

## Glosario del stack

| Término | Significado |
|---|---|
| **Stack** | Conjunto de archivos bajo `stacks/<nombre>/` que concretiza la metodología para un tipo de proyecto |
| **Stack Author** | Dev que diseña y escribe el stack en esta iteración |
| **Stack raíz** | Stack que cubre un repo autónomo con `.git` propio; heurística por indicadores estructurales |
| **Overlay** | Stack que cubre un subdirectorio/tipo de trabajo dentro de un repo detectado por otro stack |
| **Heurística de detección** | Regla en `stacks/index.md` que activa el stack al detectar el cwd del proyecto; Claude la lee en runtime (ver `general/stack-detection.md`) |
| **Validación en uso** | El stack se valida en sesiones reales, no solo al entregarlo |

> Overlay sobre `self-applied`: la concretización del [vocabulario abstracto](../../methodology/vocabulary.md) (Entregable, Entrega final, etc.) se hereda de [`self-applied`](../self-applied/index.md). La tabla anterior lista solo los términos propios de stack-authoring.

## Fases adaptadas

| Fase general | Adaptación en stack-authoring |
|---|---|
| **Fase 1 — Clarificación** | Identificar: qué stack se crea/actualiza, qué gap cierra, si es overlay o raíz, archivos hermanos afectados, si requiere subagente nuevo o hereda revisores de `self-applied` |
| **Fase 3 — Propuesta** | El plan lista: archivos a crear/editar, acoples cross-cutting (`stacks/index.md`, `general/stack-detection.md`, `process/roles-invocation.md`, `process/delivery.md`, `process/execution.md`), heurística propuesta, decisión overlay vs raíz |
| **Fase 4 — Implementación** | Crear/editar archivos en `stacks/<nombre>/`. Si se agrega heurística, actualizarla en `stacks/index.md` + `general/stack-detection.md` (Claude la lee en runtime). Al terminar: verificar que el stack se detecta abriendo una sesión Claude en un directorio cubierto |
| **Fase 5 — Validación** | Smoke de detección: abrir una sesión Claude en cwd cubierto y confirmar que el stack activo es el correcto (Claude aplica la heurística de `stacks/index.md`) |
| **Fase 6–7 — Entrega** | Commit + push al repo `neb`. Avisar al equipo si la heurística nueva puede afectar detección en proyectos existentes |
| **Fase 8 — Documentación** | Change MD + bump SemVer (minor si stack nuevo; patch si edición) + nuevo fragment `changelog.d/<version>.md` + correr `py bootstrap/assemble-changelog.py` + actualizar `stacks/index.md` |
| **Fase 9 — Retrospectiva** | Si el REQ surgió de un gap en uso, anotar si era sub-especificación del stack o necesidad de uno nuevo |

## Archivos clave del stack

| Propósito | Archivo |
|---|---|
| Inventario de stacks + heurística de detección | `stacks/index.md` |
| Decisión de cuándo crear un stack, tipos, archivos mínimos, nombramiento | `methodology/stacks.md` |
| Convenciones de escritura (estructura, imports, heurística) | `stacks/stack-authoring/conventions.md` |
| Deploy + distribución | `stacks/stack-authoring/deployment.md` |
| Roles | `stacks/stack-authoring/roles.md` |
| Troubleshooting | `stacks/stack-authoring/troubleshooting.md` |
| Scaffold de stack nuevo | `bootstrap/init-stack-subproject.sh` |

## Agregar un stack nuevo

Correr primero: `bash bootstrap/init-stack-subproject.sh <nombre> [--overlay-base self-applied|none]`

El script crea `stacks/<nombre>/` con los 6 archivos mínimos desde templates e imprime la checklist de acoples pendientes. Ver procedimiento completo en `methodology/stacks.md` y convenciones en `stacks/stack-authoring/conventions.md`.
