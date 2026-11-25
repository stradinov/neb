# Inventario de skills

fuente única de los skills de Claude Code disponibles. Cualquier REQ que cree, actualice o deprecate un skill actualiza esta tabla en Fase 8 (Documentation).

## Skills disponibles

| Skill | Versión | Profile(s) aplicable(s) | Último review | Última validación en uso | Estado |
|---|---|---|---|---|---|
| [wakeup](wakeup/SKILL.md) | 1.1.0 (2026-06-03) | `self-applied` | 2026-06-03 | — | Experimental |
| [pendings-review](pendings-review/SKILL.md) | 7.3.0 (2026-11-24) | `self-applied` | 2026-11-24 | — | Experimental |
| [logbook](logbook/SKILL.md) | 7.0.0 (2026-11-19) | `self-applied` | 2026-11-19 | — | Experimental |

## Candidatos (stubs en profiles, sin skill activo)

| Profile | Candidato | Condición para crear |
|---|---|---|
| `research` | `research-prompts` — catálogo de prompts efectivos por tipo de investigación | ≥3 research ejecutados con patrón emergente |

## Estados

| Estado | Significado |
|---|---|
| **Estable** | Probado en uso real ≥1 vez sin gap accionable pendiente |
| **Experimental** | Entregado pero sin validación en uso confirmada |
| **Deprecated** | Marcado para eliminación; consumidores deben migrar antes de la fecha indicada |

## Instalación

Los skills se **auto-descubren** del plugin de Neb instalado — no se copian a `~/.claude`. Basta con instalar/actualizar el plugin (ver [docs/user-guide.md](../docs/user-guide.md) § "Instalar"). Tras editar o agregar un skill, `/reload-plugins` lo refresca sin reiniciar; en sesión nueva ya está disponible. Para traer una versión publicada, `claude plugin update neb@<marketplace>` o la actualización automática (ver [docs/user-guide.md](../docs/user-guide.md) § "Mantener Neb al día").

## Cómo agregar un skill nuevo

Ver `methodology/skills.md` (decision tree: ¿es un skill la opción correcta?) y `profiles/skill-authoring/index.md` (pasos concretos + fases).
