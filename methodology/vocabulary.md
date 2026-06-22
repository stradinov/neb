# Vocabulario abstracto

La metodología usa vocabulario neutro para cubrir entregables de distinta naturaleza (código, documento, proceso). Cada profile concretiza los términos en su `profiles/<profile>/index.md` sección "Glosario del profile".

| Término abstracto | Significado | Ejemplos por tipo de profile |
|---|---|---|
| Entregable / elaboración | Lo que produce el requerimiento | Código (profile de software) · Documento (profile de análisis) · Lineamiento (self-applied) |
| Elaboración asistida | Humano-en-loop durante la elaboración | Un autor redacta con el dev iterando |
| Elaboración autónoma | Claude conduce la elaboración en un único turno (prompt → planeación → output) sin humano en el loop | Borrador auto-generado en un turno |
| Confirmación del cambio | Hacer permanente y recuperable un cambio del entregable | `git commit` (software, self-applied) · commit del documento versionado (análisis) |
| Punto de restauración | Estado previo recuperable que habilita rollback antes de la entrega final | commit local previo (software) · backup de datos (datos) · versión previa del documento (análisis) |
| Entrega | Acción de poner el entregable a disposición del receptor | deploy a servidor vía SSH/SCP (software) · commit versionado + notificación (análisis) · `git push` (self-applied) |
| Entrega para revisión | Primera entrega a un receptor no-final para validación | Deploy a QA (software) · Documento al receptor v1 (análisis) |
| Entrega final / aprobación final | Entrega que cierra el ciclo del requerimiento | Deploy a producción (software) · Aprobación firmada del documento (análisis) |
| Ambiente de revisión | Entorno o canal donde el receptor valida el entregable | QA (software) · Sesión de revisión (análisis) |
| Estado aprobado | El entregable fue aceptado por el receptor final | Producción (software) · Documento aprobado (análisis) |
| Dependientes | Referencias al dato, función o concepto afectado (escritura y lectura/display) | Callers de un método (software) · Secciones que citan un supuesto (análisis) |
| Flujos críticos | Flujos con riesgo de regresión medio/alto que se deben re-validar | Tests de auth/pagos (software) · Casos de uso `[crítico]` del documento (análisis) |

## Índice de términos canónicos

Mapa operativo de los conceptos que **cambian comportamiento**. La fuente de verdad de cada término es la columna **Canónico** (aquí no se duplica la definición completa, solo se ubica y desambigua). Anglicismos anotados con su equivalente en español (→).

| Término | Tipo | Glosa | No confundir con | Sinónimos | Canónico |
|---|---|---|---|---|---|
| **Requerimiento (REQ)** | unidad abstracta de trabajo | El trabajo lógico a realizar (un cambio coherente con un objetivo); no es ningún archivo. (*REQ* = "requerimiento") | registro · entregable · plan · commit | ✗ "ticket", "tarea", "issue" | [§ Requerimiento (REQ)](#requerimiento-req) |
| **Fase** | propiedad del REQ (1–9) | La etapa del flujo en que está el REQ, de 1 Clarificación a 9 Retroalimentación. | gate · estado | — | [`../general/index.md`](../general/index.md) · [`../process/phase-transitions.md`](../process/phase-transitions.md) "Mapa de fases" |
| **Gate** *(anglicismo)* | punto de control | Punto donde el avance **se detiene** hasta cumplir una condición o recibir tu OK. (*gate* = compuerta) | fase · estado | → "control", "compuerta" | [`../process/phase-transitions.md`](../process/phase-transitions.md) "Gates de cola" · [`../process/change-control-gate.md`](../process/change-control-gate.md) |
| **Estado** | propiedad del REQ (ENUM) | La situación actual del REQ en una lista cerrada: En progreso · En validación · Listo para aprobación · Cerrado (+ sufijo "Bloqueado"). (*ENUM* = lista cerrada de valores) | fase · *lock* de la bitácora | ✗ "Propuesto" (no existe); histórico "Listo para producción" → "Listo para aprobación" | [§ Estados del requerimiento](#estados-del-requerimiento) |
| **Artefacto** | objeto del flujo | Cualquier objeto que el flujo produce o usa para registrarse: plan, registro, entregable, métricas. | entregable · registro | — | [§ Vocabulario abstracto](#vocabulario-abstracto) · [`../workflow/index.md`](../workflow/index.md) |
| **Registro del requerimiento** | subclase documental | El documento que cuenta *sobre* el REQ (contexto, alcance, resultado); su forma canónica es el "Change MD". No es el REQ. (*MD* = Markdown) | REQ · entregable | → "Change MD"; variante "Incident MD" | [§ Registro del requerimiento](#registro-del-requerimiento) |
| **Entregable / elaboración** | lo que el REQ produce | El producto del REQ: código, un documento o un lineamiento. (En *self-applied* el entregable también es un `.md`.) | registro | → "elaboración" | [§ Vocabulario abstracto](#vocabulario-abstracto) |
| **Entrega** | acción del flujo | Poner el entregable ante quien lo recibe: *deploy*, *push* o documento enviado. (*push* = subir los cambios al servidor remoto) | entrega para revisión ↔ entrega final | — | [§ Vocabulario abstracto](#vocabulario-abstracto) |
| **Perfil (profile)** *(anglicismo)* | concretización por tipo de proyecto | El conjunto de reglas que adapta la metodología a un tipo de proyecto (build, convenciones de commit, roles…). (*profile* = perfil) | rol | → "perfil"; histórico "stack" (renombrado en 3.0.0) | [`profiles.md`](profiles.md) |
| **Rol** | foco de revisión/autoría | Un enfoque especializado (persona o subagente) que revisa o redacta una dimensión del trabajo. | perfil | → "revisor" / "*reviewer*" (cuando es subagente) | [`roles-catalog.md`](roles-catalog.md) |
| **Validación** | mecanismo de aceptación (4 tipos) | Cómo se comprueba que el entregable sirve antes de cerrar: en QA, local con artefactos, ciclo con cliente, o implícita. | gate de cierre · entrega | — | [§ Tipos de validación](#tipos-de-validación) |
| **Riesgo de regresión** | eje ortogonal a la complejidad | Qué tan probable es que el cambio rompa algo que ya funcionaba (Bajo/Medio/Alto), aparte de qué tan grande sea. (*regresión* = una falla vieja que reaparece) | complejidad | — | [§ Niveles de riesgo de regresión](#niveles-de-riesgo-de-regresión) |
| **Excepción** | desvío reglado del flujo | Un caso que se sale del flujo normal pero está previsto por una regla. | incidencia-durante-el-trabajo | — | [§ Estados del requerimiento](#estados-del-requerimiento) (`Bloqueado`) · [`../workflow/changes.md`](../workflow/changes.md) (Incident MD) |

## Requerimiento (REQ)

El **requerimiento (REQ)** es la **unidad abstracta de trabajo** de la metodología: un cambio lógico coherente con un objetivo. No es ningún documento. El estado, la fase y la complejidad son **propiedades del REQ**; el change MD las **registra/refleja**, no las define (modelo proyección-no-identidad, ya en uso en [`../workflow/logbook.md`](../workflow/logbook.md) §"Entrada de la bitácora" y en [`../docs/how-it-works.md`](../docs/how-it-works.md) §"Ciclo de estados").

### Qué lo distingue de un no-REQ

Un prompt escala a REQ solo al cruzar el **trigger de formalización** (`/plan`, "abre requerimiento"/"formaliza esto", o instrucción concreta de implementación o entrega). Sin trigger, una observación, pregunta de diseño o propuesta exploratoria **no es un REQ**: Claude responde en prosa. Canónico en [`../process/phase-transitions.md`](../process/phase-transitions.md) §"Trigger de formalización".

### Identidad y nombre

Identidad estable cross-máquina: `project + req_slug` (ver [`../workflow/logbook.md`](../workflow/logbook.md) §"Unidad y backend"). En **Fase 1 no hay nombre formal** — solo un tema conversacional; el nombre nace **al aprobar el plan**, cuando se crea el registro. Tres formas del nombre **pueden diferir** (no se adoptó naming coordinado — ver [`../workflow/traceability.md`](../workflow/traceability.md) §"persistencia y direccionalidad"):

| Forma | Dónde | Notas |
|---|---|---|
| `<slug>` del plan aprobado | `~/.claude/approved-plans/<ts>-<proyecto>-<slug>.md` | existe en media/alta |
| `<nombre>` del change MD | `<proyecto>/changes/<YYYY-MM-DD>-<nombre>.md` | siempre presente |
| `req_slug` de la bitácora / `[nombre-req]` en pendings | bitácora + `pendings.md` | identidad de relevo / seguimiento |

### Relación 1↔1 con su registro

A cada REQ **le corresponde** un único **registro** (su change MD): proyección documental versionada, eje **documental** de la trazabilidad (todo enlace entre artefactos pasa por él — ver [`../workflow/traceability.md`](../workflow/traceability.md)). El change MD **registra** el REQ; no **es** el REQ. La **cardinalidad 1↔1 se preserva incluso cross-repo**: un único change MD en el repo central, con commits listados por repo ([`../workflow/traceability.md`](../workflow/traceability.md) §"Multi-proyecto"). **Excepción**: `changes_old/` documenta retrospectivamente cambios lógicos reconstruidos del historial git, fuera del flujo normal (no es excepción a la 1↔1, es trazabilidad hacia atrás — ver [`../workflow/changes.md`](../workflow/changes.md) y [`../workflow/traceability.md`](../workflow/traceability.md) §"Casos especiales").

### Propiedades del REQ (punteros canónicos)

| Propiedad | Canónico |
|---|---|
| Estados (`En progreso`…`Cerrado`) + sufijo `Bloqueado` | [§ Estados del requerimiento](#estados-del-requerimiento) (abajo) |
| Fases 1–9 (mapa y flujo) | [`../general/index.md`](../general/index.md) |
| Trigger de formalización (gate de entrada) | [`../process/phase-transitions.md`](../process/phase-transitions.md) |
| Complejidad estimada / real | [`../process/planning.md`](../process/planning.md) §"Estimación" |
| Riesgo de regresión (eje ortogonal) | [§ Niveles de riesgo de regresión](#niveles-de-riesgo-de-regresión) (abajo) |
| Dos ejes: momento nace-MD vs artefacto persiste-plan | [`../process/planning.md`](../process/planning.md), [`../workflow/traceability.md`](../workflow/traceability.md) §"persistencia y direccionalidad" |
| Cross-repo: un solo change MD (repo central) | [`../workflow/traceability.md`](../workflow/traceability.md) §"Multi-proyecto" |
| Trazabilidad unidireccional plan→change MD; plan opcional, pruebas obligatorio | [`../process/planning.md`](../process/planning.md), [`../workflow/traceability.md`](../workflow/traceability.md) |
| Eslabón change MD↔commit (bidireccional) | [`../workflow/traceability.md`](../workflow/traceability.md) §"Eslabón Change MD ↔ confirmación" |
| Definición de done + entrega del registro (temprana si entorno compartido, o atómica al cierre — push `.md`-only del change MD) | [`done-criteria.md`](done-criteria.md), [`../process/delivery.md`](../process/delivery.md) §"Cierre del requerimiento" |
| Validación + cierre por mecanismo verificable del profile (sin gate diferido; señal-en-uso → Fase 9) | [§ Tipos de validación](#tipos-de-validación), [`../process/improvement.md`](../process/improvement.md) |

### Formas especiales

| Forma | Canónico |
|---|---|
| REQ de research (antes de planear) | [`../process/planning.md`](../process/planning.md) §"Sugerencia de research" |
| REQ derivado (corrige un defecto Fase 9) | [`../process/improvement.md`](../process/improvement.md) |
| Incidencia-durante-el-trabajo vs sub-requerimiento | [`../process/execution.md`](../process/execution.md) §"Incidencias" |
| Incident MD (variante reactiva post-entrega) | [`../workflow/changes.md`](../workflow/changes.md) §"Incident MD" |

### Proyecciones / representaciones del REQ

El REQ se proyecta (no se duplica) en varios artefactos; cada uno **deriva** del registro o de la memoria, sin ser una segunda fuente:

| Proyección | Qué refleja | Canónico |
|---|---|---|
| Memoria del proyecto `active_<proyecto>_<slug>.md` (uno por REQ activo) | estado vivo del REQ (fuente de verdad local) | [`../workflow/memory.md`](../workflow/memory.md) |
| Bitácora de relevo (`work` + lock ortogonal + `archived`) | relevo cross-dev; deriva de la memoria | [`../workflow/logbook.md`](../workflow/logbook.md) |
| `pendings.md` (`[nombre-req]` tag) | seguimiento no bloqueante cross-sesión | [`../workflow/pendings.md`](../workflow/pendings.md) |
| Métricas del REQ | retroalimentación de la metodología | [`../workflow/metrics.md`](../workflow/metrics.md) |
| Diagnóstico de defectos | origen del defecto + REQ derivado | [`../process/improvement.md`](../process/improvement.md) §"Diagnóstico de origen" |

## Registro del requerimiento

**Registro del requerimiento** es el término agnóstico para la **subclase documental de [artefacto](#vocabulario-abstracto)** cuyo rol es **documentar *sobre* un REQ** (su proyección versionada). No es el REQ (ver [§ Requerimiento (REQ)](#requerimiento-req)) ni el entregable.

| Forma | Naturaleza | Cardinalidad | Canónico |
|---|---|---|---|
| **Change MD** | canónica | 1↔1 con el REQ (incluso cross-repo) | [`../workflow/changes.md`](../workflow/changes.md) |
| **Incident MD** | variante reactiva (defecto post-entrega final) | propia 1↔1 con su incidente | [`../workflow/changes.md`](../workflow/changes.md) §"Incident MD", [`../general/incidents.md`](../general/incidents.md) |

### Discriminador registro vs entregable: el rol, no la extensión

Lo que separa un registro de un **entregable** (lo producido — ver la fila "Entregable / elaboración" arriba) es el **rol**:

- **Registro**: documenta *sobre* el REQ (contexto, alcance, plan resumido, resultado, métricas, trazabilidad).
- **Entregable**: es lo que el REQ produce (código, documento, lineamiento).

`.md` **no es rasgo definitorio** del registro — es implementación incidental. En el profile `self-applied` el **entregable también es `.md`** (archivos de la metodología), y aun así se distingue del change MD por su rol. La autonomía de Claude sobre archivos `.md` y el caso de confirmaciones mixtas viven en [`change-control-policy.md`](change-control-policy.md) §"Ownership de archivos `.md`".

## Estados del requerimiento

Estado y fase son propiedades del REQ (la unidad abstracta de trabajo); ningún artefacto las define, solo las **registra**. ENUM canónico: cualquier artefacto que registre el estado del REQ usa este vocabulario. El mapa de artefactos por estado y las transiciones especiales (qué fases se saltan) viven en [`../workflow/index.md`](../workflow/index.md) y [`../process/delivery.md`](../process/delivery.md) respectivamente.

| Estado | Significado | Fase |
|---|---|---|
| `En progreso` | Plan aprobado, implementación en curso | 4 |
| `En validación` | Implementación lista, esperando validación (con QA, local con artefactos, o implícita) | 5 |
| `Listo para aprobación` | Validación pasada, esperando entrega final / aprobación del receptor | 6–7 |
| `Cerrado` | Entrega final confirmada por el dev (o aprobación del receptor) | post 8/9 |

**Bloqueado** se anota como sufijo del estado activo: `En progreso (bloqueado por X)`. No es estado paralelo — no inventa transiciones nuevas.

- El change MD (registro canónico del REQ, relación 1↔1 incluso cross-repo) existe desde `Plan aprobado` (ver [`../workflow/changes.md`](../workflow/changes.md)); por convención registra `En progreso` como estado inicial. No hay estado "Propuesto".
- Los changes históricos pueden contener vocabulario previo (`Propuesto`, `COMPLETADO`, `Listo para producción`); no se migran. `Listo para producción` es el término anterior de `Listo para aprobación` (renombrado en una versión anterior).

**ENUM de lock de la bitácora de relevo** (`owned` / `released` / `takeover_requested`, definido en [`../workflow/logbook.md`](../workflow/logbook.md) §"Modelo de ownership") es **ortogonal** a este ENUM: gobierna quién tiene el mando de un `work` para relevo entre devs, no el avance del requerimiento. Un `work` archivado al cerrar no altera el estado canónico del REQ.

## Tipos de validación

Clasificación según la naturaleza del entregable. Los pasos de ejecución de Fase 5 viven en [`../process/delivery.md`](../process/delivery.md) § Validación.

- **Con ambiente de revisión** (e-commerce, etc.): el usuario valida el flujo principal en el ambiente de revisión antes de la entrega final.
- **Con ciclo de revisión cliente** (profiles de análisis): el cliente valida el entregable iterativamente; cada vuelta produce una nueva versión hasta la aprobación final.
- **Sin ambiente pero con artefactos** (scripts, migraciones, CLI): validación directa — ejecución local, dry-run, o revisión.
- **Sin artefactos** (docs sin proceso, comentarios, typos): validación implícita — el usuario revisa en contexto y confirma.

> Los **profiles de proceso** (`self-applied` y sus overlays `research`/`skill-authoring`/`profile-authoring`) no usan un tipo aparte: validan con el mecanismo **verificable** de su entregable —revisión de roles + coherencia para lineamientos, `fact-check-reviewer` para research, smoke load + `validation-prompts` para skills— y **cierran de inmediato**. La observación en uso posterior (utilidad, triggering, fricción) es **retroalimentación de Fase 9** (ver [`../process/improvement.md`](../process/improvement.md)), no un gate de cierre.

## Niveles de riesgo de regresión

Eje ortogonal a la complejidad. 1 elemento cambiado con muchos dependientes = complejidad baja + riesgo alto. La regla que ata el riesgo al plan de pruebas (`medio`/`alto` exige fila `[crítico]`) vive en [`../process/planning.md`](../process/planning.md) § "Riesgo de regresión".

| Nivel | Criterio | Ejemplos |
|-------|----------|----------|
| Bajo  | Cambios aislados sin dependientes, docs/comentarios/typos, lógica sin condicionales sensibles | Typo en MD, log nuevo, comentario, formato |
| Medio | Lógica con dependientes acotados conocidos, configs no críticos, cambios localizados con uso identificable | Nuevo método con 2-3 dependientes, config de feature flag, cambio en helper |
| Alto  | Muchos dependientes, contratos públicos, flujos críticos (auth, pagos, datos), refactor transversal | Cambio en hash de password, modificar query SQL central, cambio de schema, rename de método público |
