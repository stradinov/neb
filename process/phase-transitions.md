# Transiciones de fase

Reglas de **enrutamiento del workflow**: cuándo Claude entra o cambia de fase. Este archivo se carga al arranque vía `@import` desde [`../general/startup.md`](../general/startup.md) — debe estar presente desde el primer prompt para que una instrucción de implementación no se salte el flujo formal.

## Trigger de formalización

Gate de entrada al workflow: cuándo un prompt escala a requerimiento formal y, por tanto, si Claude responde en prosa breve o genera un plan estructurado.

Si el prompt del dev no incluye trigger explícito — `/plan`, frase tipo "abre requerimiento" o "formaliza esto", o instrucción concreta de implementación o entrega —, Claude responde en prosa breve con recomendación + tradeoffs y cierra con "¿lo formalizamos como requerimiento?". No genera plan estructurado (tabla de archivos, propuesta de versionado, plan de pruebas, change MD) hasta tener trigger formal. Una observación, pregunta de diseño o propuesta exploratoria no es trigger.

## Implementación: propuesta aprobada antes de editar

Con un trigger formal de implementación o entrega, Claude entra a **Propuesta**: clarifica lo ambiguo y presenta un plan (archivos, enfoque, pruebas), y **no crea ni edita archivos del entregable hasta que el dev apruebe**. Saltar directo a editar sin plan aprobado viola el flujo (anti-desviación) — esta regla es always-on, no depende de cargar `execution.md` ni de overrides en `personal/<usuario>.md`.

- Aplica aunque la instrucción sea clara y aunque la sesión esté en **auto mode**: auto mode automatiza permisos de tools, no reemplaza la aprobación del plan por el dev.
- Proporcionalidad: un fix trivial (una línea, typo, rename obvio) no requiere plan formal — ver el criterio de plan mode en [`execution.md`](execution.md). La regla apunta a trabajo de implementación real.
- El detalle de los gates por fase vive en [`execution.md`](execution.md) y [`change-control-gate.md`](change-control-gate.md) (on-demand); esta cláusula garantiza el comportamiento base desde el primer prompt.

## Mapa de fases y escalamiento de contexto

Fases del requerimiento: **1** Clarificación · **2** Estimación · **3** Propuesta · **4** Implementación · **5** Validación · **6** Control de cambios · **7** Producción · **8** Documentación · **9** Retroalimentación.

- Los archivos de fase (`process/planning|execution|delivery|documentation|improvement.md`) se leen **al entrar a la fase** — este arranque trae el enrutamiento, no el detalle de cada fase.
- La fase es propiedad del **REQ activo**: se lee del **Estado registrado en su change MD** (que la refleja, no la define) y del último gate cruzado; ante duda, preguntar antes de asumir fase.

## Gates de cola (always-on)

Espejo de las reglas canónicas de [`change-control-gate.md`](change-control-gate.md) y [`delivery.md`](delivery.md) — el detalle vive allá; estas cláusulas garantizan el comportamiento base sin cargarlos:

- **Confirmación**: toda confirmación que toque el entregable del proyecto destino (commit, deploy, migración, config) espera **OK explícito del dev** durante la implementación.
- **Validación antes de entregar**: no se entrega a producción sin Fase 5 ejecutada — o saltada con OK explícito (transiciones especiales en `delivery.md`).
- **Cierre**: un REQ no pasa a `Cerrado` sin validación del dev (o el criterio de validación que defina su profile).

## Conflictos y vacíos normativos (always-on)

- Ante **contradicción entre reglas** o un caso sin regla aplicable: no resolver en silencio — reportar el conflicto con alternativas y esperar decisión (espejo de `methodology/principles.md` § "Detectar y reportar").
- Un override (personal o de profile) **estrecha o agrega, nunca relaja** el baseline (espejo de [`../methodology/personal-vs-team.md`](../methodology/personal-vs-team.md)).

> **Transiciones especiales de estado** (qué fases se saltan según el tipo de cambio): viven en [`delivery.md`](delivery.md) § "Transiciones especiales de estado" — se consultan al cerrar/entregar, no al arranque, por lo que no se cargan aquí.
