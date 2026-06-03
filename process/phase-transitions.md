# Transiciones de fase

Reglas de **enrutamiento del workflow**: cuándo Claude entra o cambia de fase. Este archivo se carga al arranque vía `@import` desde [`../general/startup.md`](../general/startup.md) — debe estar presente desde el primer prompt para que una instrucción de implementación no se salte el flujo formal.

## Trigger de formalización

Gate de entrada al workflow: cuándo un prompt escala a requerimiento formal. El tono de la interacción (prosa breve vs estructura) vive en [`../general/communication.md`](../general/communication.md) § "Tono y forma".

Si el prompt del dev no incluye trigger explícito — `/plan`, frase tipo "abre requerimiento" o "formaliza esto", o instrucción concreta de implementación o entrega —, Claude responde en prosa breve con recomendación + tradeoffs y cierra con "¿lo formalizamos como requerimiento?". No genera plan estructurado (tabla de archivos, propuesta de versionado, plan de pruebas, change MD) hasta tener trigger formal. Una observación, pregunta de diseño o propuesta exploratoria no es trigger.

## Implementación: propuesta aprobada antes de editar

Con un trigger formal de implementación o entrega, Claude entra a **Propuesta**: clarifica lo ambiguo y presenta un plan (archivos, enfoque, pruebas), y **no crea ni edita archivos del entregable hasta que el dev apruebe**. Saltar directo a editar sin plan aprobado viola el flujo (anti-desviación) — esta regla es always-on, no depende de cargar `execution.md` ni de overrides en `personal/<usuario>.md`.

- Aplica aunque la instrucción sea clara y aunque la sesión esté en **auto mode**: auto mode automatiza permisos de tools, no reemplaza la aprobación del plan por el dev.
- Proporcionalidad: un fix trivial (una línea, typo, rename obvio) no requiere plan formal — ver el criterio de plan mode en [`execution.md`](execution.md). La regla apunta a trabajo de implementación real.
- El detalle de los gates por fase vive en [`execution.md`](execution.md) y [`change-control-gate.md`](change-control-gate.md) (on-demand); esta cláusula garantiza el comportamiento base desde el primer prompt.

> **Transiciones especiales de estado** (qué fases se saltan según el tipo de cambio): viven en [`delivery.md`](delivery.md) § "Transiciones especiales de estado" — se consultan al cerrar/entregar, no al arranque, por lo que no se cargan aquí.
