# Tipos de subagente de Claude Code

Claude Code expone dos capas de subagentes, con propósitos distintos:

| Capa | Definición | Dónde se configura |
|---|---|---|
| **Built-in agent types** | Predefinidos por Claude Code. Este documento los cubre. | Internos al harness |
| **Custom role agents** | Definidos por el equipo en `agents/<nombre>.md`. | [`process/roles-invocation.md`](../process/roles-invocation.md) "Implementación de roles" |

## Catálogo de built-in agent types

| Tipo | Propósito | Tools disponibles | Limitaciones clave |
|---|---|---|---|
| `Explore` | Búsqueda rápida read-only: localizar archivos por patrón, grep de símbolos, responder "¿dónde está definida X?" | Glob, Grep, Read, WebFetch, WebSearch | Lee excerpts — puede perder contenido fuera de la ventana de lectura. NO usar para revisión de diseño, auditoría cross-file ni análisis abierto. |
| `Plan` | Diseñar planes de implementación: pasos detallados, archivos críticos, trade-offs arquitectónicos | Todo excepto Agent, ExitPlanMode, Edit, Write, NotebookEdit | Devuelve un plan, no implementa. No busca en el codebase (use `Explore` primero). |
| `general-purpose` | Investigación compleja, búsqueda multi-step, tareas que cruzan múltiples ubicaciones cuando el scope es incierto | Todos (*) | Más costoso y lento que `Explore` para búsquedas simples. Escalar desde `Explore` solo cuando sea necesario. |

> Los built-in types `claude-code-guide` y `statusline-setup` son de uso interno del harness y no se prescriben en la metodología.

## Mapeo fase → tipo de agente recomendado

*Orientativo, no prescriptivo. Claude elige el tipo según el contexto del prompt y el scope real de la tarea.*

| Fase | Tipo recomendado | Cuándo |
|---|---|---|
| 1 Clarificación | `Explore` | Lookup puntual: localizar un símbolo, archivo o path específico. Una sola búsqueda bien definida. |
| 1 Clarificación | `general-purpose` | Investigación abierta: scope incierto, múltiples ubicaciones posibles, pregunta que requiere síntesis. |
| 2 Estimación | `Explore` | Enumerar dependientes (escritura + lectura/display) vía grep cuando el nombre del símbolo es conocido. |
| 2 Estimación | `general-purpose` | Dependientes dispersos, nombre ambiguo o múltiples variantes del símbolo. |
| 3 Plan (diseño) | `Plan` | REQ con múltiples archivos, trade-offs arquitectónicos, o cuando conviene ver el plan antes de ejecutar. |
| 3 Plan-review | Custom role agents | `qa-process-engineer`, `process-improvement-analyst`, etc. Ver [`process/plan-review.md`](../process/plan-review.md). |
| 4 Implementación | `Explore` | Verificar existencia o signatura de un método antes de editar. Lookup puntual. |
| 4 Implementación | `general-purpose` | Subtarea compleja que requiere búsqueda + análisis + decisión antes de escribir código. |
| 5 Validación | `Explore` | Verificar que un cambio quedó aplicado en todos los archivos esperados (grep de nombre/constante). |
| 9 Improvement | `general-purpose` | Diagnóstico de defecto cross-REQ, revisión de métricas, análisis de utilidad de roles. |

## Regla de selección y escalamiento

```
Lookup puntual y bien definida          → Explore
Investigación abierta o multi-step     → general-purpose
Diseño de plan arquitectónico          → Plan
Revisión adversarial del plan          → Custom role agent (process/plan-review.md)
```

**Escalamiento Explore → general-purpose**: si `Explore` devuelve excerpts incompletos o el resultado es ambiguo (el símbolo puede estar en más archivos de los que reportó), relanzar la búsqueda con `general-purpose` y scope explícito. No asumir que el resultado de `Explore` es exhaustivo.

## Cuándo NO usar cada tipo

| Tipo | No usar para |
|---|---|
| `Explore` | Revisión de diseño, auditoría cross-file, análisis que requiere leer archivos completos, preguntas de consistencia global |
| `Plan` | Buscar en el codebase, implementar código, decisiones que dependen del contexto conversacional activo |
| `general-purpose` | Lookups simples donde `Explore` basta — costo y latencia innecesarios |

## Limitación de sesión (custom role agents)

Los custom role agents del plugin de Neb se **auto-cargan** al inicio de la sesión — no se copian a `~/.claude/agents/`. Un agent agregado o editado durante una sesión **no está disponible hasta la siguiente** (el harness carga las definiciones al arranque); ejecutar `/reload-plugins` fuerza la recarga sin reiniciar la sesión.
