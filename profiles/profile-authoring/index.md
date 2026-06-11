# Profile: profile-authoring

Autoría, mantenimiento y distribución de profiles de la metodología. Materializa la [promesa 6 (Expandible)](../../methodology/promises.md) — el mecanismo por el que el adoptante agrega profiles propios a la metodología sin modificar el núcleo.

## Cuándo aplica este profile

Overlay sobre `self-applied`. Se activa cuando:

- El cwd está dentro de `methodology/profiles/<nombre>/`.
- El REQ pide crear, actualizar, deprecar o auditar un profile.

Si el REQ también toca la metodología general (`general/`, `methodology/`, `process/`, `tooling/`, `workflow/`), el profile activo es `profile-authoring` para los artefactos del profile y `self-applied` para el resto. Si hay ambigüedad, anunciar y preguntar.

## Glosario del profile

| Término | Significado |
|---|---|
| **Profile** | Conjunto de archivos bajo `profiles/<nombre>/` que concretiza la metodología para un tipo de proyecto |
| **Profile Author** | Dev que diseña y escribe el profile en esta iteración |
| **Profile raíz** | Profile que cubre un repo autónomo con `.git` propio; heurística por indicadores estructurales |
| **Overlay** | Profile que cubre un subdirectorio/tipo de trabajo dentro de un repo detectado por otro profile |
| **Heurística de detección** | Regla en `profiles/index.md` que activa el profile al detectar el cwd del proyecto; Claude la lee en runtime (ver `general/profile-detection.md`) |
| **Validación en uso** | El profile se valida en sesiones reales, no solo al entregarlo |

> Overlay sobre `self-applied`: la concretización del [vocabulario abstracto](../../methodology/vocabulary.md) (Entregable, Entrega final, etc.) se hereda de [`self-applied`](../self-applied/index.md). La tabla anterior lista solo los términos propios de profile-authoring.

## Fases adaptadas

| Fase general | Adaptación en profile-authoring |
|---|---|
| **Fase 1 — Clarificación** | Identificar: qué profile se crea/actualiza, qué gap cierra, si es overlay o raíz, archivos hermanos afectados, si requiere subagente nuevo o hereda revisores de `self-applied` |
| **Fase 3 — Propuesta** | El plan lista: archivos a crear/editar, acoples cross-cutting (`profiles/index.md`, `general/profile-detection.md`, `process/roles-invocation.md`, `process/delivery.md`, `process/execution.md`), heurística propuesta, decisión overlay vs raíz |
| **Fase 4 — Implementación** | Crear/editar archivos en `profiles/<nombre>/`. Si se agrega heurística, actualizarla en `profiles/index.md` + `general/profile-detection.md` (Claude la lee en runtime). Al terminar: verificar que el profile se detecta abriendo una sesión Claude en un directorio cubierto |
| **Fase 5 — Validación** | Smoke de detección: abrir una sesión Claude en cwd cubierto y confirmar que el profile activo es el correcto (Claude aplica la heurística de `profiles/index.md`) |
| **Fase 6–7 — Entrega** | Commit + push al repo `neb`. Avisar al equipo si la heurística nueva puede afectar detección en proyectos existentes |
| **Fase 8 — Documentación** | Change MD + bump SemVer (minor si profile nuevo; patch si edición) + nuevo fragment `changelog.d/<version>.md` + correr `py bootstrap/assemble-changelog.py` + actualizar `profiles/index.md` |
| **Fase 9 — Retrospectiva** | Si el REQ surgió de un gap en uso, anotar si era sub-especificación del profile o necesidad de uno nuevo |

## Archivos clave del profile

| Propósito | Archivo |
|---|---|
| Inventario de profiles + heurística de detección | `profiles/index.md` |
| Decisión de cuándo crear un profile, tipos, archivos mínimos, nombramiento | `methodology/profiles.md` |
| Convenciones de escritura (estructura, imports, heurística) | `profiles/profile-authoring/conventions.md` |
| Deploy + distribución | `profiles/profile-authoring/deployment.md` |
| Roles | `profiles/profile-authoring/roles.md` |
| Troubleshooting | `profiles/profile-authoring/troubleshooting.md` |
| Scaffold de profile nuevo | `bootstrap/init-profile-subproject.sh` |

## Agregar un profile nuevo

Correr primero: `bash bootstrap/init-profile-subproject.sh <nombre> [--overlay-base self-applied|none]`

El script crea `profiles/<nombre>/` con los 6 archivos mínimos desde templates e imprime la checklist de acoples pendientes. Ver procedimiento completo en `methodology/profiles.md` y convenciones en `profiles/profile-authoring/conventions.md`.
