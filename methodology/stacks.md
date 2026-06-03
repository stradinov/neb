# Stacks

Lineamiento meta-organizacional: cuándo crear un stack, qué archivos requiere y cómo mantenerlo. Para el "cómo" concreto (estructura, convenciones, bootstrap), ver `stacks/stack-authoring/`.

## ¿Qué es un stack?

Un stack es un conjunto de archivos Markdown bajo `stacks/<nombre>/` que concretiza la metodología para un tipo de proyecto específico. Claude lo carga al detectar el directorio del proyecto y aplica sus convenciones (fases adaptadas, comandos exactos, roles, deploy, troubleshooting) en vez de los lineamientos genéricos.

## Stack vs alternativas

Antes de crear un stack, descartar alternativas más simples:

| ¿El conocimiento es...? | Va en |
|---|---|
| Específico de un proyecto, estable | `CLAUDE.md` del proyecto (o `stacks/<stack>/servers.md` si es infraestructura) |
| Convención que aplica a todos los proyectos del equipo | `general/`, `methodology/`, `process/` o `tooling/` |
| Preferencia del dev, no del equipo | `personal/<usuario>.md` |
| Vocabulario cross-proyecto voluminoso | Skill (ver `methodology/skills.md`) |
| Convenciones específicas de un tipo de proyecto reusadas en varios repos | **Stack** |
| Fases, comandos, deploy y roles que divergen del patrón genérico | **Stack** |

Solo crear un stack cuando un tipo de proyecto requerirá al menos `index.md` + 2 archivos hermanos con contenido no trivial.

## Stack raíz vs overlay

| Tipo | Descripción | Detección | Ejemplos |
|---|---|---|---|
| **Raíz** | El stack **es el repo entero** (repo autónomo con `.git` propio). Heurística por indicadores estructurales del repo. | Archivos/carpetas característicos del repo (e.g. `package.json` + estructura del framework, `*.sql` + script de carga) | `node-api`, `data-pipeline` |
| **Overlay** | El stack cubre un **subdirectorio o tipo de trabajo *dentro*** de un repo ya detectado por otro stack. No sube al `.git` padre; va con prioridad alta en `stacks/index.md`. | Path pattern sobre el cwd absoluto (e.g. `*/reqs/<X>/`, `*/skills/<X>/`) | `skill-authoring`, `stack-authoring`, `requirements-analysis` |

Regla: si el trabajo produce un tipo de entregable diferente al repo padre y ocurre en un subdirectorio propio y recurrente, usar overlay.

## Archivos del stack

### Obligatorios

- `index.md` — entrypoint: cuándo aplica, glosario del stack (concretización del vocabulario abstracto de `methodology/vocabulary.md`), fases adaptadas, archivos clave.

### Estándar (crear salvo stack minimalista de markdown puro, como `self-applied`)

- `deployment.md` — cómo se deploya, ambiente, validación, distribución al equipo.
- `conventions.md` — convenciones específicas (estructura de código/archivos, naming, patrones).
- `troubleshooting.md` — síntomas comunes + diagnóstico + solución.
- `roles.md` — rol principal, revisores default, subagentes por fase.

### Opcionales

- `servers.md` — hosts, paths SSH. Incluido en CLAUDE.md por `link-into-project.sh` si existe.
- `skills.md` — skills que aplican al stack. Si no hay skills propios, crear stub con puntero a `skills/README.md`.
- Archivos de dominio adicionales (e.g. `clarification-template.md`, `operation-modes.md`).

### Cuándo omitir archivos estándar

| Archivo | Se puede omitir si... |
|---|---|
| `deployment.md` | El overlay hereda deploy idéntico del stack base — documentarlo en `index.md`. |
| `conventions.md` | El entregable es markdown puro sin naming ni patrones de código que documentar. |
| `troubleshooting.md` | El stack es nuevo y sin uso real — crear en el primer REQ que detecte un problema recurrente. |

## Nombramiento

- `kebab-case`. Sin prefijos numéricos ni versiones en el nombre.
- Stacks de autoría: sufijo `-authoring` (e.g. `skill-authoring`, `stack-authoring`).
- Stacks de análisis: prefijo del dominio + `-analysis` (e.g. `requirements-analysis`, `security-analysis`).
- Stacks de implementación: nombre del framework o dominio (e.g. `node-api`, `react-native`).
- Stacks auto-aplicados / reflexivos: sin sufijo de dominio (e.g. `self-applied`); la justificación de omitir el sustantivo va en el `index.md` del stack — el stack cubre cualquier marco (metodología, proceso, artefactos) auto-aplicado y no se restringe a un dominio.

## Heurística de detección

Cada stack declara su heurística en `stacks/index.md`. Reglas:

- **Estructural** (stacks raíz): matchear por archivos o carpetas que identifican inequívocamente el tipo de proyecto. Sin `stat` sobre contenido — solo existencia de paths.
- **Por path pattern** (overlays): `grep -qE '<patron>'` sobre el path absoluto del cwd. Usar `(/|$)` al final del segmento para evitar falsos positivos.
- **Primer match gana**: los overlays van ANTES que los stacks raíz en la tabla.
- **Sin ambigüedad**: si dos heurísticas pueden activarse para el mismo directorio, la de mayor prioridad (posición más alta en la tabla) gana. Documentar el caso en `troubleshooting.md` del stack afectado.

## Asociación con roles y subagentes

Decisiones de diseño al crear un stack: (1) definir el rol principal en `stacks/<stack>/roles.md` (siempre persona); (2) decidir si hereda revisores de otro stack (overlay) o define los propios. El **procedimiento operativo completo** (acoples en `process/roles-invocation.md`, `process/execution.md`, `process/delivery.md`, y cómo formalizar un subagente) vive en el `CLAUDE.md` del repo § "Agregar un stack nuevo" / "Agregar un subagente".

## Versionado

| Tipo de cambio | SemVer |
|---|---|
| Nuevo stack | Minor |
| Nuevo archivo en un stack existente | Minor |
| Edición de contenido sin romper imports | Patch |
| Renombrar archivo importado por proyectos cliente | Major |
| Cambio en ENUM de estados (`workflow/index.md`) o vocabulario de `general/` | Major |

## Mantenimiento

Un stack no se actualiza automáticamente. Tres triggers:

1. **Fase 8 del REQ**: si el REQ tocó convenciones del stack, actualizar `stacks/<stack>/conventions.md` o `troubleshooting.md`.
2. **Gap en uso**: si un lineamiento resulta incompleto en una sesión real, abrir REQ de patch.
3. **Nuevo proyecto en el stack**: si el stack tiene `servers.md`, verificar que esté actualizado.
