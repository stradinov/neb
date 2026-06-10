# Stack: skill-authoring

Autoría, mantenimiento y distribución de skills de Claude Code bajo la metodología. Parte del mecanismo de la [promesa 6 (Expandible)](../../methodology/promises.md) — el adoptante agrega skills propios sin modificar el núcleo de Neb.

## Cuándo aplica este stack

Overlay sobre `self-applied`. Se activa cuando:

- El cwd está dentro de `methodology/skills/<nombre>/`.
- El REQ pide crear, actualizar, deprecar o auditar un skill.

Si el REQ también toca la metodología general (lineamientos, stacks, etc.), el stack activo es `skill-authoring` para los artefactos del skill y `self-applied` para el resto. Si hay ambigüedad, anunciar y preguntar.

## Glosario del stack

| Término | Significado |
|---|---|
| **Skill** | Archivo `SKILL.md` + archivos hermanos, instalado en `~/.claude/skills/<nombre>/`. Claude lo carga selectivamente según contexto |
| **Skill Author** | Dev que diseña y escribe el skill en esta iteración |
| **Skill Maintainer** | Dev responsable del mantenimiento periódico (regen autogen, baselines, distribución) |
| **autogen** | Contenido entre marcadores `<!-- autogen-start --> ... <!-- autogen-end -->` generado por scripts, no editado a mano |
| **Validación en uso** | Prueba diferida: el skill se valida cada vez que se usa en una sesión real, no solo al entregarlo |
| **Undertriggering** | El skill estaba disponible pero Claude no lo cargó/usó cuando habría sido relevante |
| **Sub-especificación** | El skill cargó pero no tenía el vocabulario/orientación necesario para resolver el prompt |

> Overlay sobre `self-applied`: la concretización del [vocabulario abstracto](../../methodology/vocabulary.md) (Entregable, Entrega final, etc.) se hereda de [`self-applied`](../self-applied/index.md). La tabla anterior lista solo los términos propios de skill-authoring.

## Fases adaptadas

| Fase general | Adaptación en skill-authoring |
|---|---|
| **Fase 1 — Clarificación** | Identificar: qué skill se crea/actualiza, qué gap cierra, qué archivos hermanos se tocan, qué casos del `validation-prompts.md` aplican |
| **Fase 3 — Propuesta** | El plan lista archivos fuente a editar/crear + casos de regresión nuevos en `validation-prompts.md` |
| **Fase 4 — Implementación** | Editar fuente en `methodology/skills/<nombre>/`. Los skills se auto-descubren del plugin; tras editar, `/reload-plugins` (o `claude plugin update <plugin>`) refresca; sesión nueva ya está |
| **Fase 5 — Validación** | (1) Smoke load: `/skills` en sesión nueva confirma que el skill carga. (2) Correr los casos afectados de `validation-prompts.md` y documentar resultados |
| **Fase 6–7 — Entrega** | Commit + push al repo `neb`. Aviso al equipo si hay cambios en `description` del frontmatter (puede afectar undertriggering para el resto) |
| **Fase 8 — Documentación** | Change MD del REQ + bump SemVer (`methodology/skills.md` ← patch, `stacks/` ← minor/patch según alcance) + nuevo fragment `changelog.d/<version>.md` + correr `py bootstrap/assemble-changelog.py` + actualizar `skills/README.md` (inventario) |
| **Fase 9 — Retrospectiva** | Si el REQ surgió de un gap de validación en uso, anotar si era sub-especificación o undertriggering y si el patrón es generalizable |

## Archivos clave del stack

| Propósito | Archivo |
|---|---|
| Inventario maestro de skills | `skills/README.md` |
| Decision tree (skill vs alternativas), restricción de contenido, validación en uso | `methodology/skills.md` |
| Convenciones de escritura (frontmatter, progressive disclosure, restricción) | `stacks/skill-authoring/conventions.md` |
| Deploy + distribución | `stacks/skill-authoring/deployment.md` |
| Roles | `stacks/skill-authoring/roles.md` |
| Troubleshooting | `stacks/skill-authoring/troubleshooting.md` |
| Andamiaje con skill-creator de Anthropic | `stacks/skill-authoring/skill-creator-integration.md` |

## Agregar un skill nuevo

1. Crear `skills/<nombre>/SKILL.md` con frontmatter `name` + `description` preciso (ver `conventions.md`).
2. Agregar archivos hermanos de contenido y scripts si aplica.
3. Registrar en `skills/README.md` (inventario maestro).
4. Registrar en `stacks/<stack>/skills.md` del stack donde aplica.
5. Agregar caso(s) en `skills/<nombre>/validation-prompts.md` (al menos 1 positivo + 1 negativo).
6. Bump minor + nuevo fragment `changelog.d/<version>.md` + correr `py bootstrap/assemble-changelog.py`.

Ver `methodology/skills.md` para la decisión de si crear un skill es la opción correcta.
