# Inventario de skills

Single source of truth de los skills de Claude Code disponibles. Cualquier REQ que cree, actualice o deprecate un skill actualiza esta tabla en Fase 8 (Documentation).

## Skills disponibles

| Skill | Versión | Stack(s) aplicable(s) | Último review | Última validación en uso | Estado |
|---|---|---|---|---|---|
| [welcome](welcome/SKILL.md) | 1.0.0 (2026-06-02) | `self-applied` | 2026-06-02 | — | Experimental |

## Candidatos (stubs en stacks, sin skill activo)

| Stack | Candidato | Condición para crear |
|---|---|---|
| `research` | `research-prompts` — catálogo de prompts efectivos por tipo de investigación | ≥3 research ejecutados con patrón emergente |

## Estados

| Estado | Significado |
|---|---|
| **Estable** | Probado en uso real ≥1 vez sin gap accionable pendiente |
| **Experimental** | Entregado pero sin validación en uso confirmada |
| **Deprecated** | Marcado para eliminación; consumidores deben migrar antes de la fecha indicada |

## Instalación

```bash
bash ~/.claude/neb/bootstrap/install-skills.sh
```

O como parte del bootstrap inicial:

```bash
bash ~/.claude/neb/bootstrap/install.sh
```

## Cómo agregar un skill nuevo

Ver `methodology/skills.md` (decision tree: ¿es un skill la opción correcta?) y `stacks/skill-authoring/index.md` (pasos concretos + fases).
