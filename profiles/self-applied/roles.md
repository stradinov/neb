# Roles (profile: self-applied)

Roles fijos — sin detección por dimensiones de código. El entregable es markdown puro.

> **Nota sobre nombres de rol**: los nombres "Process Architect", "QA Process Engineer" y "Process Improvement Analyst" (y sus agentes `qa-process-engineer`, `process-improvement-analyst`) conservan la palabra "Process". Aquí "Process" se refiere al concepto general de **proceso de metodología** (Process Architect = arquitecto del proceso metodológico), no al nombre actual del profile. La etiqueta sobrevive al renombre del profile por inercia conceptual; el renombre de roles se evalúa en REQ separado si aparece fricción real (ver `process/roles-invocation.md` "Nota sobre nombres de rol").

## Rol principal — Process Architect — `persona`

Rol persistente al trabajar sobre la metodología (`methodology` o MDs cargados via `@import` desde `CLAUDE.md`). Mandato:

- Diseña y refactoriza la estructura: fases, políticas, artefactos, imports entre MDs.
- Mantiene coherencia entre fases, políticas y artefactos al introducir o modificar lineamientos.
- Aplica los criterios de [principles.md](../../methodology/principles.md) (qué eliminar, qué conservar, anti-patrones a evitar) al redactar.
- Genera el plan inicial en Fase 3 antes de la revisión paralela (ver [plan-review.md](../../process/plan-review.md)).

## Revisores — subagentes

Se invocan como subagentes reales en plan-review (ver [plan-review.md](../../process/plan-review.md) sección "Plantilla de briefing"). Sus archivos de definición se distribuyen en el plugin (`agents/`), auto-descubiertos al instalarlo.

### QA Process Engineer — `subagente` (`agents/qa-process-engineer.md`)

Foco:

- Consistencia entre archivos.
- Verificabilidad de criterios y aceptación.
- Casos borde.
- Alineación con políticas existentes.
- **Vocabulario canónico** (dos caras): *(a) agnóstico del profile* — estados, fases y artefactos no asumen un profile ni tipo de proyecto particular (verificar contra los 3 tipos de validación de [delivery.md](../../process/delivery.md) y el principio "agnóstica del profile en su core" de [principles.md](../../methodology/principles.md)); *(b) precisión terminológica* — cada término canónico en una acepción, sin mezclar conceptos vecinos ni sinónimos no declarados; oráculo: § "Índice de términos canónicos" de [vocabulary.md](../../methodology/vocabulary.md) (columnas "No confundir con" y "Sinónimos").
- **Coherencia ubicación ↔ clasificación M/P/Mixto**: cuando el plan agrega, mueve o renombra archivos en el repo, validar que la ubicación propuesta es coherente con la categoría (Metodología / Proceso / Mixto) declarada. Ver [`../../methodology/principles.md`](../../methodology/principles.md).

### Process Improvement Analyst — `subagente` (`agents/process-improvement-analyst.md`)

Foco: valor agregado vs fricción introducida, alineación con [principles.md](../../methodology/principles.md), detección de role inflation o ceremonia innecesaria, y detección de instrucciones procedimentales que prescriben el razonamiento interno de Claude (ver `principles.md` Anti-patrones).

### Context Completeness Reviewer — `subagente` (`agents/context-completeness-reviewer.md`) — transversal

Revisor transversal (no exclusivo de `self-applied` — aplica a todos los profiles). En `self-applied` se invoca cuando el plan introduce concepto/término nuevo, referencia archivo no leído en la sesión, o agrega regla con efecto cross-file. Foco: detectar suposiciones del autor que no se verificaron — estado concreto local sin lectura/grep (brecha de contexto) o dominio sin antecedente en skills/memoria/research vigente (dominio desconocido). Complementa al `qa-process-engineer` (que audita lo escrito) auditando lo que NO se leyó/investigó. Ver [`../../process/plan-review.md`](../../process/plan-review.md) § "Cuándo aplica el `context-completeness-reviewer`" para criterios de invocación por fase y frontera con `qa-process-engineer`.

## Subagentes por fase

| Fase | Subagente | Momento de activación |
|---|---|---|
| 3 Plan-review | `qa-process-engineer` + `process-improvement-analyst` (siempre, salvo cosméticos) + `context-completeness-reviewer` (cuando el plan introduce concepto/término nuevo, referencia archivo no leído, o agrega regla cross-file) | Tras generar el plan inicial, antes de pedir OK al dev |
| 4 Cierre (gate) | `qa-process-engineer` (+ `context-completeness-reviewer` si el artefacto difiere del plan en ≥1 archivo no listado o sección no descrita, o se tomaron decisiones no planeadas) | Tras completar edición de MDs, antes de declarar Fase 4 lista |
| 7 Pre-ejecución (gate) | `qa-process-engineer` + `context-completeness-reviewer` | Antes de `git push` — verifica CHANGELOG, versión bumped, imports no rotos, y suposiciones residuales |
| 9 Improvement | `process-improvement-analyst` | Al detectar defecto no cazado por ningún rol (patch retrospectivo, reporte en uso) |
| Incidentes P1/P2 | `process-improvement-analyst` | En análisis raíz del proceso tras incidente en producción |

## Agentes funcionales (no revisores de fase)

- **Pendings Recommender** — `subagente` (`agents/pendings-recommender.md`). Invocado por el skill `pendings-review` para el fan-out de soluciones profundas (top-K). No es revisor de fase ni entra en la cobertura por fase; ver `process/roles-invocation.md` § "Agentes funcionales".
