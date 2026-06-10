# Roles (stack: stack-authoring)

Hereda los revisores del stack `self-applied`. Sin subagentes propios adicionales.

## Rol principal — Stack Author — `persona`

Rol activo al crear o modificar un stack. Mandato:

- Diseña la estructura del stack: archivos, heurística de detección, glosario, fases adaptadas.
- Mantiene coherencia entre el stack y los acoples cross-cutting (`stacks/index.md`, `general/stack-detection.md`, `process/roles-invocation.md`, `process/delivery.md`, `process/execution.md`).
- Aplica las convenciones de `stacks/stack-authoring/conventions.md` al redactar.
- Genera el plan inicial en Fase 3 antes de la revisión paralela.

## Revisores — heredados de `self-applied`

Se invocan como subagentes en plan-review. Ver [`stacks/self-applied/roles.md`](../self-applied/roles.md) para el mandato completo de cada uno y sus archivos de definición en `agents/`.

### QA Process Engineer — `subagente` (`agents/qa-process-engineer.md`)

Foco al revisar un stack nuevo o modificado:

- Consistencia entre `stacks/index.md`, `general/stack-detection.md` (detección runtime) y los acoples de `process/roles-invocation.md` / `general/`.
- Verificabilidad de la heurística de detección (sin ambigüedad de prioridad, sin falsos positivos evidentes).
- Casos borde: ¿el overlay se activa sobre directorios no previstos? ¿el stack raíz colisiona con otro?
- Vocabulario canónico: el glosario del stack concretiza — no contradice — el vocabulario abstracto de `methodology/vocabulary.md`.

### Process Improvement Analyst — `subagente` (`agents/process-improvement-analyst.md`)

Foco al revisar un stack nuevo o modificado:

- ¿El stack agrega valor real o es fragmentación innecesaria?
- ¿Las fases adaptadas agregan ceremonia sin cubrir un gap real?
- ¿Los archivos propuestos podrían vivir en `general/` o como extensión de un stack existente?

## Subagentes por fase

| Fase | Subagente | Momento de activación |
|---|---|---|
| 3 Plan-review | `qa-process-engineer` + `process-improvement-analyst` (en paralelo) | Tras generar el plan inicial, antes de pedir OK al dev |
| 4 Cierre (gate) | `qa-process-engineer` | Tras completar edición de archivos, antes de declarar Fase 4 lista |
| 7 Pre-ejecución (gate) | `qa-process-engineer` | Antes de `git push` — verifica CHANGELOG, versión bumped, acoples completos |
| 9 Improvement | `process-improvement-analyst` | Al detectar defecto no cazado por ningún rol |
| Incidentes P1/P2 | `process-improvement-analyst` | En análisis raíz del proceso tras incidente en producción |
