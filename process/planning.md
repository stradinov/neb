# Planning

Cubre clarificación, estimación, plan, plan de pruebas, propuesta.

## Insumos de contexto (Fases 1–3)

Antes de clarificar y planear, cargar el contexto relevante:

- Consultar `skills/README.md` (inventario maestro) e identificar los skills cuya columna "Profile(s) aplicable(s)" incluye el profile activo. El plan debe declarar expresamente cuáles aplican al REQ y por qué. Si ninguno aplica, declararlo: "ningún skill del inventario cubre este REQ". Este paso cierra el loop si Claude no activó skills relevantes al iniciar la sesión. Un skill aplicable provee vocabulario, mapas y peculiaridades por proyecto que informan la estimación de impacto y la enumeración de dependientes.
- Si profile activo = `self-applied` y el REQ propone **crear, mover o renombrar archivos** en el repo: consultar [`../methodology/principles.md`](../methodology/principles.md) antes de proponer ubicación. Declarar en el plan la clasificación del archivo afectado (Metodología / Proceso / Mixto) y derivar la ubicación de ella. Para Mixto, justificar la elección de carpeta y la sección que domina la decisión (ver `methodology/principles.md` § "Cuándo separar mixtos"). Aplica también a reorganizaciones de carpetas. No aplica a ediciones in-place ni a typos.

## Trigger de formalización

Gate de entrada al workflow. Contenido canónico en [`phase-transitions.md`](phase-transitions.md) § "Trigger de formalización" — cargado al arranque vía `@import` desde `../general/startup.md`. En resumen: sin trigger explícito (`/plan`, "abre requerimiento"/"formaliza esto", o instrucción concreta de implementación o entrega), Claude responde en prosa breve y ofrece formalizar; no genera plan estructurado (tabla de archivos, versionado, plan de pruebas, change MD) hasta tener el trigger.

## Clarificación

> Aplica cuando el prompt es un requerimiento formal (ver § "Trigger de formalización" arriba). Para observaciones, preguntas de diseño o propuestas exploratorias sin trigger, responder en prosa breve sin generar plan estructurado.

- Reformular el requerimiento con palabras propias.
- Máximo 3 preguntas si algo es ambiguo.
- No proceder sin confirmación.
- Excepción: cambios triviales (una línea, un texto) → ir directo a propuesta.

## Sugerencia de research

Si el REQ toca un tema especializado sin antecedente en skills ni en la memoria del proyecto, y la complejidad estimada es media o alta (ver tabla "Riesgo de regresión" abajo): proponer abrir un REQ de research antes de planear. El dev puede rechazar. Ver disparadores y modos en [`profiles/research/conventions.md`](../profiles/research/conventions.md).

## Sugerencia de plan mode

Si el prompt es ambiguo o cumple algún criterio de [execution.md](execution.md) (múltiples archivos, trade-offs arquitectónicos, conviene ver el plan antes de ejecutar), Claude **sugiere entrar en plan mode**. El dev puede rechazar y Claude procede en modo normal.

## Selección de roles (paso 0 antes del plan inicial)

Si el REQ activa plan-review (ver [process/plan-review.md](plan-review.md) "Cuándo aplica"), Claude analiza el plan de archivos de la propuesta y propone los roles antes de generar el plan inicial. Algoritmo de detección automática y catálogo de dimensiones en [process/roles-invocation.md](roles-invocation.md). Para casos rutinarios usa default sin preguntar; para casos especiales pregunta al dev.

## Estimación, plan y plan de pruebas

El **plan de pruebas es obligatorio** en cualquier nivel.

| Nivel | Criterio | Acción |
|-------|----------|--------|
| Baja  | ≤ 2 elementos | Solo plan de pruebas |
| Media | 3–6 elementos, lógica nueva | Estimado + plan breve + plan de pruebas |
| Alta  | 7+ elementos, cambio de arquitectura | Estimado + plan detallado + plan de pruebas |

El plan de elaboración incluye: rango de tiempo, elementos del entregable con una línea cada uno, riesgos. El profile concretiza qué son "elementos" (archivos en un profile de software, secciones del documento en un profile de análisis).

## Riesgo de regresión

El catálogo de niveles (Bajo/Medio/Alto con criterios y ejemplos) vive en [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Niveles de riesgo de regresión". Reglas de proceso que lo aplican al plan:

- Riesgo `bajo` no requiere flujo crítico identificado.
- Riesgo `medio`/`alto` exige ≥1 fila con prefijo `[crítico]` en la tabla `### Resultado` del [`change.md.template`](../templates/change.md.template). Una fila `[crítico]` con ❌ bloquea el cierre (ver [`../methodology/done-criteria.md`](../methodology/done-criteria.md)).
- Antes de aprobar el plan con riesgo medio/alto: enumerar dependientes (escritura/procesamiento y lectura/display) — vía grep, LSP, lectura directa o inferencia de contexto conocido.

El plan de pruebas incluye: flujos a validar, criterios de éxito, orden, y quién ejecuta cada uno. El usuario valida directamente o delega a Claude (Claude solicita los datos necesarios — ver [delivery.md](delivery.md)).

Cierre: **"¿De acuerdo con este plan?"**

Al recibir aprobación, Claude crea o actualiza la memoria del proyecto y el MD del requerimiento. Ver [workflow/memory.md](../workflow/memory.md) y [workflow/changes.md](../workflow/changes.md). En complejidad **media/alta aprobada sin plan mode**, además persiste el plan literal en `~/.claude/approved-plans/` vía `Write` (en plan mode lo hace el hook) — ver [workflow/approved-plans.md](../workflow/approved-plans.md) § "Persistencia conversacional".

## Propuesta de implementación

Antes de cada bloque de código, describir: qué archivo(s), qué se agrega/modifica/elimina, y por qué (solo si no es obvio).

**No se escribe código sin aprobación del usuario:**
- **Explícita**: "sí", "ok", "adelante", "procede".
- **Implícita**: pregunta sobre detalles de implementación, propuesta de variación, o respuesta que asume que el código se escribirá ("¿y el caso de X?", "mejor usa Y en lugar de Z").
- **No cuenta**: silencio, pregunta de aclaración sin presuponer implementación, contrapropuesta que requiere nueva confirmación.

## Cuándo aplica cada aprobación

Resumen de los criterios dispersos en este archivo y en `communication.md` / `traceability.md`. **Punteros, no contenido** — cada fila remite a su fuente canónica.

| Situación | ¿Plan? | ¿Aprobación del plan? | ¿Se persiste? | Canónico |
|---|---|---|---|---|
| Trivial (1 línea, typo, rename obvio) | No | N/A | No | § Clarificación (arriba) |
| No-formal (sin trigger de formalización) | No (prosa) | N/A | No | [`phase-transitions.md`](phase-transitions.md) § "Trigger de formalización" |
| Baja (≤2 elementos) | Solo plan de pruebas | Implícita o explícita | No | § Estimación + § Propuesta de implementación (arriba) |
| Media/alta vía plan mode | Sí | Explícita (`ExitPlanMode`) | Sí — hook | [`workflow/approved-plans.md`](../workflow/approved-plans.md) |
| Media/alta conversacional | Sí | Explícita ("¿De acuerdo con este plan?") | Sí — `Write` | [`workflow/approved-plans.md`](../workflow/approved-plans.md) |

La **aprobación del plan** (esta tabla) es gate distinto de la **aprobación de implementación** (escribir código), que admite forma implícita — ver § "Propuesta de implementación" arriba. Opcionalidad del artefacto y direccionalidad de la trazabilidad: [`workflow/traceability.md`](../workflow/traceability.md).
