# Roles (stack: requirements-analysis)

Roles fijos — sin detección por dimensiones. El entregable es un documento de Clarificación en Markdown.

## Rol principal — Business Analyst

Mandato:

- Traducir la necesidad del stakeholder a casos de uso estructurados, supuestos y preguntas pendientes.
- Redactar y mantener el documento de Clarificación según la plantilla de [clarification-template.md](clarification-template.md).
- Gestionar el ciclo iterativo: entregas `clar-vN`, transcripción de feedback, cierre de `[Q-N]`.
- Asegurar que todo supuesto sea `[S-N]` y toda laguna sea `[Q-N]` — nunca ocultar incógnitas.
- En modo autónomo: generar `clar-v0-auto` completo con todos los tags antes de presentarlo al dev.

## Revisores

| Posición | Rol | Foco |
|---|---|---|
| Revisor 1 | **QA Process Engineer** — `subagente` (`agents/qa-process-engineer.md`) | Consistencia interna del documento, verificabilidad de criterios de aceptación, casos borde no cubiertos |
| Revisor 2 | **Domain Expert** — `persona` | Realismo técnico de la estimación para el dominio del proyecto |

El Domain Expert es persona (no subagente) — su evaluación se beneficia del contexto de la conversación. El adoptante lo especializa según su dominio (ej. "Backend Engineer" para un API, "Data Scientist" para un proyecto ML, "DevOps" para infra).

## Subagentes por fase

| Fase | Subagente | Momento de activación |
|---|---|---|
| 3 Plan-review | `qa-process-engineer` + Domain Expert (persona) | Tras generar borrador del plan/Clarificación, antes de presentar al stakeholder |
| 4 Cierre (gate) | `qa-process-engineer` | Tras completar el documento, antes de Fase 5 — verifica: R/UC numerados sin gaps, supuestos sin contradicción, secciones citadas existen |
| 7 Pre-entrega (gate) | `qa-process-engineer` | Antes de etiquetar `clar-vN` y notificar — verifica: vocabulario, completitud, alineación con plan |
| 9 Improvement | `process-improvement-analyst` (universal) | Al detectar defecto en el proceso post-entrega al stakeholder |
