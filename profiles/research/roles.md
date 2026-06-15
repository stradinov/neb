# Roles (profile: research)

## Rol principal — Process Architect — `persona`

Diseña la pregunta de investigación, selecciona las fuentes y el motor de investigación, conduce las consultas, sintetiza outputs destilados, presenta la síntesis al dev (la calidad se validó en el gate F4; la utilidad posterior es señal de Fase 9, no un gate) y decide el formato final del documento.

Hereda de `profiles/self-applied/roles.md`. El nombre Process Architect aplica sin cambio al dominio de investigación.

## Revisores

### Fact-Check Reviewer — `subagente` (`agents/fact-check-reviewer.md`)

Revisor adversarial especializado en verificación de claims. Ver `agents/fact-check-reviewer.md` para el mandato completo.

Cobertura mínima:

- **Fase 7 (pre-commit)**: siempre.
- **Fase 4 (cierre)**: cuando `propósito = decisión`, o divergencia material entre fuentes que el Process Architect no pudo resolver con una fuente autoritativa adicional en una dimensión `[crítico]`.

### Para Fase 3 (plan-review de un research de propósito decisión)

Hereda revisores de `self-applied`: `qa-process-engineer` + `process-improvement-analyst`. Ver `process/plan-review.md`.

## Subagentes por fase

| Fase | Subagente | Momento de activación |
|---|---|---|
| 3 Plan-review (si `propósito = decisión`) | `qa-process-engineer` + `process-improvement-analyst` | Tras generar el plan inicial |
| 4 Cierre (gate) | `fact-check-reviewer` | Si `propósito = decisión` o divergencia material no resuelta en `[crítico]` |
| 7 Pre-ejecución (gate) | `fact-check-reviewer` | Antes del commit — siempre |
| 9 Improvement | `process-improvement-analyst` | Al detectar defecto no cazado |
| Incidentes P1/P2 | `process-improvement-analyst` | En análisis raíz |
