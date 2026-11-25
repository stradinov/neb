# Vocabulario abstracto

La metodología usa vocabulario neutro para cubrir entregables de distinta naturaleza (código, documento, proceso). Cada profile concretiza los términos en su `profiles/<profile>/index.md` § "Glosario del profile".

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
| **Requerimiento (REQ)** | unidad abstracta de trabajo | El trabajo lógico a realizar (un cambio coherente con un objetivo); no es ningún archivo. (*REQ* = "requerimiento") | registro · entregable · plan · commit | ✗ "ticket", "tarea", "issue" | [§ "Requerimiento (REQ)"](#requerimiento-req) |
| **Fase** | propiedad del REQ (1–9) | La etapa del flujo en que está el REQ, de 1 Clarificación a 9 Retroalimentación. | gate · estado | ✗ `F<n>` como abreviatura | [`../general/index.md`](../general/index.md) · [`../process/phase-transitions.md`](../process/phase-transitions.md) § "Mapa de fases" |
| **Gate** *(anglicismo)* | punto de control | Punto donde el avance **se detiene** hasta cumplir una condición o recibir tu OK. (*gate* = compuerta) | fase · estado | → "control", "compuerta" | [`../process/phase-transitions.md`](../process/phase-transitions.md) § "Gates de cola" · [`../process/change-control-gate.md`](../process/change-control-gate.md) |
| **Estado** | propiedad del REQ (ENUM) | La situación actual del REQ en una lista cerrada: En progreso · En validación · Listo para aprobación · Cerrado (+ sufijo "Bloqueado"). (*ENUM* = lista cerrada de valores) | fase · `req_state` de la bitácora (copia, no lo define) | ✗ "Propuesto" (no existe); histórico "Listo para producción" → "Listo para aprobación" | [§ "Estados del requerimiento"](#estados-del-requerimiento) |
| **Artefacto** | objeto del flujo | Cualquier objeto que el flujo produce o usa para registrarse: plan, registro, entregable, métricas. | entregable · registro | — | [§ "Vocabulario abstracto"](#vocabulario-abstracto) · [`../workflow/index.md`](../workflow/index.md) |
| **Registro del requerimiento** | subclase documental | El documento que cuenta *sobre* el REQ (contexto, alcance, resultado); su forma canónica es el "Change MD". No es el REQ. (*MD* = Markdown) | REQ · entregable · registro de un correo (tú/ustedes, [`../general/correspondence.md`](../general/correspondence.md)) | → "Change MD"; variante "Incident MD"; ✗ `change MD` en minúscula | [§ "Registro del requerimiento"](#registro-del-requerimiento) |
| **Entregable / elaboración** | lo que el REQ produce | El producto del REQ: código, un documento o un lineamiento. (En *self-applied* el entregable también es un `.md`.) | registro | → "elaboración" | [§ "Vocabulario abstracto"](#vocabulario-abstracto) |
| **Entrega** | acción del flujo | Poner el entregable ante quien lo recibe: *deploy*, *push* o documento enviado. (*push* = subir los cambios al servidor remoto) | entrega para revisión ↔ entrega final · integración | — | [§ "Vocabulario abstracto"](#vocabulario-abstracto) |
| **Integración** | acción del flujo | Llevar a la línea principal compartida, sin crear confirmaciones nuevas, un cambio ya validado. (En git: *fast-forward* de la rama principal remota hasta el commit validado.) No es una entrega del profile. | entrega (para revisión o final) · confirmación del cambio · incorporación | — | [`../process/version-control.md`](../process/version-control.md) § "Integración a la rama principal" |
| **Incorporación** | acción del flujo | Llevar a la línea principal, en una confirmación propia del mantenedor, el contenido de un pull request de quien no tiene permiso de escritura. Crea confirmaciones y nunca es autónoma. | integración · entrega | — | [`../profiles/self-applied/deployment.md`](../profiles/self-applied/deployment.md) § "Incorporar un PR" |
| **Aporte al núcleo** | forma de aplicar un ajuste de Fase 9 | La mejora al núcleo que un adoptante sin permiso de escritura propone por pull request. Es parte de la Fase 9 del REQ que la originó, no un REQ nuevo. | REQ · ajuste en el overlay · issue | — | [`../process/upstream-contribution.md`](../process/upstream-contribution.md) |
| **Mantenedor** | quien publica el núcleo | Quien tiene permiso de escritura en el repo del núcleo y publica sus versiones. | adoptante (usa el núcleo y lo extiende en su overlay) | ✗ "maintainer" (anglicismo) | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
| **Confirmación autónoma** | excepción del gate | Confirmar un cambio del entregable sin un OK por confirmación, dentro del plan aprobado y con el piso del núcleo; solo el adoptante la activa. | confirmación del cambio · integración | — | [`../process/change-control-gate.md`](../process/change-control-gate.md) § "Autorización de la confirmación del cambio" |
| **Perfil (profile)** *(anglicismo)* | concretización por tipo de proyecto | El conjunto de reglas que adapta la metodología a un tipo de proyecto (build, convenciones de commit, roles…). (*profile* = perfil) | rol · ficha de destinatario ([`../general/correspondence.md`](../general/correspondence.md)) | → "perfil"; histórico "stack" | [`profiles.md`](profiles.md) |
| **Rol** | foco de revisión/autoría | Un enfoque especializado (persona o subagente) que revisa o redacta una dimensión del trabajo. | perfil | → "revisor" / "*reviewer*" (cuando es subagente) | [`roles-catalog.md`](roles-catalog.md) |
| **Validación** | mecanismo de aceptación (4 tipos) | Cómo se comprueba que el entregable sirve antes de cerrar: en QA, local con artefactos, ciclo con cliente, o implícita. | gate de cierre · entrega | — | [§ "Tipos de validación"](#tipos-de-validación) |
| **Riesgo de regresión** | eje ortogonal a la complejidad | Qué tan probable es que el cambio rompa algo que ya funcionaba (Bajo/Medio/Alto), aparte de qué tan grande sea. (*regresión* = una falla vieja que reaparece) | complejidad | — | [§ "Niveles de riesgo de regresión"](#niveles-de-riesgo-de-regresión) |
| **Excepción** | desvío reglado del flujo | Un caso que se sale del flujo normal pero está previsto por una regla. | incidencia-durante-el-trabajo | — | [§ "Estados del requerimiento"](#estados-del-requerimiento) (`Bloqueado`) · [`../workflow/changes.md`](../workflow/changes.md) (Incident MD) |
| **Fuente de verdad** | principio sobre los datos que se persisten | El repo y el estado actual del sistema: lo que se lee de ellos se lee al momento; como evidencia solo se persiste la constancia de un momento o el dato verificado. Las excepciones viven en el canónico. | «fuente única» / «una sola fuente de verdad» de una regla ([`principles.md`](principles.md) § "Eliminar") · registro del requerimiento (la constancia de un momento es una clase de dato, no el registro) · proyección | — | [`principles.md`](principles.md) § "Fuente de verdad: el repo y el estado actual" |
| **Marca de verificación** | metadato de un dato persistido | `verificado:` + `Fuente:` de un dato verificado. | supuesto de plataforma · `[asumido]` | — | [`principles.md`](principles.md) § "Fuente de verdad: el repo y el estado actual" |
| **Regla de proceso** | clase de regla | Regla con eje de severidad (gates, plan de pruebas, firma de commits, revisión): un override la estrecha o la agrega, nunca la relaja. Dice qué se exige, no con qué mecanismo. | punto de customización · mecanismo de plataforma | ✗ "invariante" (como sinónimo) | [`personal-vs-team.md`](personal-vs-team.md) § "Puntos de customización vs reglas de proceso" |
| **Mecanismo de plataforma** | cómo se cumple una regla | La forma en que Claude Code cumple hoy una regla del núcleo: subagentes, workflows, modelo, esfuerzo, hooks, herramientas de la interfaz. Se reemplaza cuando la plataforma cambia; la regla no. | regla de proceso · usos genéricos de "mecanismo" (de control, de aceptación, verificable, de versionamiento) · implementación de un rol (persona o subagente: la elección del mecanismo para un rol, [`roles-catalog.md`](roles-catalog.md)). Ejemplo a nivel de profile: [`../profiles/research/conventions.md`](../profiles/research/conventions.md) § "Mecanismo recomendado" | — | [`principles.md`](principles.md) § "Reglas de proceso y mecanismos de plataforma" |
| **Supuesto de plataforma** | hecho sobre Claude Code | Un comportamiento de la plataforma del que depende Neb, con la versión, la interfaz y la fuente donde se verificó (o «sin verificar»). | suposición de contexto o de dominio ([`principles.md`](principles.md) § "Suposiciones explícitas antes de afirmar") | ✗ "registro de supuestos" (el registro es el del requerimiento) | [`platform-assumptions.md`](platform-assumptions.md) |
| **Bitácora de relevo** | tablas de trabajos en la base local `~/.claude/neb.db` | Base local de trabajos a medias, para retomarlos: los REQ del dev y sus sesiones exploratorias en esta máquina. Continuar en otra máquina o pasar el trabajo a otro dev va por git (`## Relevo` del Change MD). | registro del requerimiento · pendiente tipo `session` | ✗ "registro local" | [`../workflow/logbook.md`](../workflow/logbook.md) |
| **Vincular / REQ vinculado** | vínculo local en la bitácora | Una fila por (`project`, `nombre`) del registro en la bitácora local: el REQ, sus repos declarados y las sesiones de esta máquina; `desvincular` la quita. | work `req` (entrada de la bitácora) · seguimiento (pendientes) · alta (complejidad) | ✗ "alta", "track", "índice del REQ" | [`../workflow/logbook.md`](../workflow/logbook.md) § "REQ vinculado" |
| **Traza** (`trace`) | consulta local | Consulta local de los commits publicados (leídos de git al consultar) y las sesiones de esta máquina de un REQ vinculado. | sección Trazabilidad del Change MD | ✗ "show" | [`../workflow/logbook.md`](../workflow/logbook.md) § "REQ vinculado" |
| **Paso de base** | cambio numerado de `neb.db` | Cambio del esquema de `neb.db` escrito en código; lo aplica la primera conexión de una versión que lo trae. | esquema inicial (`hooks/logbook-schema.sql`, que no se edita) · reparación (corre en cada conexión) · paso guiado (configura la máquina) · migración guiada (prompt y pasos guiados de una versión) | ✗ "migración" a secas | [`../tooling/migrations.md`](../tooling/migrations.md) § "Pasos de base" |
| **Versión de esquema** | propiedad de una base y de un código | Número del último paso de base aplicado a una base; el código trae la suya (`SCHEMA_VERSION`). | versión de Neb (`VERSION`) · mínima compatible | — | [`../tooling/migrations.md`](../tooling/migrations.md) § "Versión y compatibilidad" |
| **Mínima compatible** | propiedad de una base | Versión de esquema más baja con la que un código todavía puede operar esa base. | versión de esquema | — | [`../tooling/migrations.md`](../tooling/migrations.md) § "Versión y compatibilidad" |
| **Migración guiada** | lo que una versión pide además de sus pasos de base | Prompt (`migrations/<X.Y.Z>.md`) y pasos guiados (`migrations/<X.Y.Z>.py`) con los que una versión configura la máquina del dev; lo que deja con qué deshacerlo corre solo al iniciar cada sesión, y lo demás se pregunta en un menú en la misma sesión (desde 7.5.0; `/neb:migrate` para reintentar). | paso de base (esquema de `neb.db`, corre solo en la primera conexión) · el migrador de nombre (`bootstrap/migrate-neb-db.py`) | — | [`../tooling/migrations.md`](../tooling/migrations.md) § "Migración guiada" |
| **Paso guiado** | unidad de una migración guiada | Un cambio en la máquina del dev con id `<X.Y.Z>:<paso>`, de catálogo (operación de `hooks/lib/_machine.py`) o libre (`detectar` y `aplicar` propios). Corre solo si deja con qué deshacerlo; si no, pide al dev. | paso de base | ✗ "paso por programa" | [`../tooling/migrations.md`](../tooling/migrations.md) § "Migración guiada" |

## Requerimiento (REQ)

El **requerimiento (REQ)** es la **unidad abstracta de trabajo** de la metodología: un cambio lógico coherente con un objetivo. No es ningún documento. El estado, la fase y la complejidad son **propiedades del REQ**; el Change MD las **registra/refleja**, no las define (modelo proyección-no-identidad, ya en uso en [`../workflow/logbook.md`](../workflow/logbook.md) § "Entrada de la bitácora" y en [`../docs/how-it-works.md`](../docs/how-it-works.md) § "Ciclo de estados").

### Qué lo distingue de un no-REQ

Un prompt escala a REQ solo al cruzar el **trigger de formalización** (`/plan`, "abre requerimiento"/"formaliza esto", o instrucción concreta de implementación o entrega). Sin trigger, una observación, pregunta de diseño o propuesta exploratoria **no es un REQ**: Claude responde en prosa. Canónico en [`../process/phase-transitions.md`](../process/phase-transitions.md) § "Trigger de formalización".

### Identidad y nombre

Identidad del trabajo en la bitácora: `project + req_slug` (ver [`../workflow/logbook.md`](../workflow/logbook.md) § "Unidad y backend"). Entre máquinas, el REQ se identifica por el `<nombre>` de su Change MD. En **Fase 1 no hay nombre formal** — solo un tema conversacional; el nombre nace **al aprobar el plan**, cuando se crea el registro. El `<nombre>` del Change MD es el **identificador único del REQ**; las demás formas lo repiten (ver [`../workflow/changes.md`](../workflow/changes.md) § "Path"):

| Forma | Dónde | Notas |
|---|---|---|
| `<nombre>` del Change MD | `<proyecto>/changes/<YYYY-MM-DD>-<nombre>.md` | siempre presente; forma `[a-z0-9-]+`, único en el `changes/` del proyecto |
| Archivo del plan aprobado | `<proyecto>/changes/plans/<YYYY-MM-DD>-<nombre>.md` | existe en media/alta |
| Trailer del commit | `Req: <nombre>` o `Confirmacion-autonoma: <nombre>` | liga cada commit con su REQ |
| `req_slug` de la bitácora | campo `Nombre` del `active_*.md`, de donde lo toma la bitácora | junto con `project`, identifica el trabajo del REQ en la bitácora; lleva el mismo `<nombre>` |

El `[slug]` de un pendiente es otra cosa: identifica al pendiente, no al REQ ([`../tooling/pendings.md`](../tooling/pendings.md) § "Cómo citar un pendiente").

### Relación 1↔1 con su registro

A cada REQ **le corresponde** un único **registro** (su Change MD): proyección documental versionada, eje **documental** de la trazabilidad (todo enlace entre artefactos pasa por él — ver [`../workflow/traceability.md`](../workflow/traceability.md)). El Change MD **registra** el REQ; no **es** el REQ. La **cardinalidad 1↔1 se preserva incluso cross-repo**: un único Change MD en el repo central, con commits listados por repo ([`../workflow/traceability.md`](../workflow/traceability.md) § "Multi-proyecto").

**Excepción**: `changes_old/` documenta retrospectivamente cambios lógicos reconstruidos del historial git, fuera del flujo normal (no es excepción a la 1↔1, es trazabilidad hacia atrás — ver [`../workflow/changes.md`](../workflow/changes.md) y [`../workflow/traceability.md`](../workflow/traceability.md) § "Casos especiales").

### Propiedades del REQ (punteros canónicos)

| Propiedad | Canónico |
|---|---|
| Estados (`En progreso`…`Cerrado`) + sufijo `Bloqueado` | [§ "Estados del requerimiento"](#estados-del-requerimiento) (abajo) |
| Fases 1–9 (mapa y flujo) | [`../general/index.md`](../general/index.md) |
| Trigger de formalización (gate de entrada) | [`../process/phase-transitions.md`](../process/phase-transitions.md) |
| Complejidad estimada / real | [`../process/planning.md`](../process/planning.md) § "Estimación" |
| Riesgo de regresión (eje ortogonal) | [§ "Niveles de riesgo de regresión"](#niveles-de-riesgo-de-regresión) (abajo) |
| Dos ejes: momento nace-MD vs artefacto persiste-plan | [`../process/planning.md`](../process/planning.md), [`../workflow/traceability.md`](../workflow/traceability.md) § "persistencia y direccionalidad" |
| Cross-repo: un solo Change MD (repo central) | [`../workflow/traceability.md`](../workflow/traceability.md) § "Multi-proyecto" |
| Enlace plan ↔ Change MD por nombre, en los dos sentidos; plan solo en media/alta, plan de pruebas siempre | [`../process/planning.md`](../process/planning.md), [`../workflow/traceability.md`](../workflow/traceability.md) |
| Eslabón Change MD↔commit (bidireccional) | [`../workflow/traceability.md`](../workflow/traceability.md) § "Eslabón Change MD ↔ confirmación" |
| Definición de done + entrega del registro (temprana al relevar o a pedido del dev, o atómica al cierre — push `.md`-only del Change MD) | [`done-criteria.md`](done-criteria.md), [`../process/delivery.md`](../process/delivery.md) § "Cierre del requerimiento", [`../workflow/changes.md`](../workflow/changes.md) § "Ciclo de vida del draft" |
| Validación + cierre por mecanismo verificable del profile (sin gate diferido; señal-en-uso → Fase 9) | [§ "Tipos de validación"](#tipos-de-validación), [`../process/improvement.md`](../process/improvement.md) |

### Formas especiales

| Forma | Canónico |
|---|---|
| REQ de research (antes de planear) | [`../process/planning.md`](../process/planning.md) § "Sugerencia de research" |
| REQ derivado (corrige un defecto Fase 9) | [`../process/improvement.md`](../process/improvement.md) |
| Incidencia-durante-el-trabajo vs sub-requerimiento | [`../process/execution.md`](../process/execution.md) § "Incidencias" |
| Incident MD (variante reactiva post-entrega) | [`../workflow/changes.md`](../workflow/changes.md) § "Incident MD" |

### Proyecciones / representaciones del REQ

El REQ se proyecta (no se duplica) en varios artefactos; cada uno **deriva** del registro o de la memoria. Derivar no autoriza a copiar lo que se lee del repo o del sistema ([`principles.md`](principles.md) § "Fuente de verdad: el repo y el estado actual"):

| Proyección | Qué refleja | Canónico |
|---|---|---|
| Memoria del proyecto `active_<proyecto>_<slug>.md` (uno por REQ activo) | estado vivo del REQ | [`../workflow/memory.md`](../workflow/memory.md) |
| Bitácora de relevo (`work` + `archived`) | trabajo a medias, para retomarlo; deriva de la memoria | [`../workflow/logbook.md`](../workflow/logbook.md) |
| Pendiente en `neb.db` (cita `[slug]`) | seguimiento no bloqueante cross-sesión | [`../workflow/pendings.md`](../workflow/pendings.md) |
| Métricas del REQ | retroalimentación de la metodología | [`../workflow/metrics.md`](../workflow/metrics.md) |
| Diagnóstico de defectos | origen del defecto + REQ derivado | [`../process/improvement.md`](../process/improvement.md) § "Diagnóstico de origen" |

## Registro del requerimiento

**Registro del requerimiento** es el término agnóstico para la **subclase documental de [artefacto](#vocabulario-abstracto)** cuyo rol es **documentar *sobre* un REQ** (su proyección versionada). No es el REQ (ver [§ "Requerimiento (REQ)"](#requerimiento-req)) ni el entregable.

| Forma | Naturaleza | Cardinalidad | Canónico |
|---|---|---|---|
| **Change MD** | canónica | 1↔1 con el REQ (incluso cross-repo) | [`../workflow/changes.md`](../workflow/changes.md) |
| **Incident MD** | variante reactiva (defecto post-entrega final) | propia 1↔1 con su incidente | [`../workflow/changes.md`](../workflow/changes.md) § "Incident MD", [`../general/incidents.md`](../general/incidents.md) |

### Discriminador registro vs entregable: el rol, no la extensión

Lo que separa un registro de un **entregable** (lo producido — ver la fila "Entregable / elaboración" arriba) es el **rol**:

- **Registro**: documenta *sobre* el REQ (contexto, alcance, plan resumido, resultado, métricas, trazabilidad).
- **Entregable**: es lo que el REQ produce (código, documento, lineamiento).

`.md` **no es rasgo definitorio** del registro — es implementación incidental. En el profile `self-applied` el **entregable también es `.md`** (archivos de la metodología), y aun así se distingue del Change MD por su rol. La autonomía de Claude sobre archivos `.md` y el caso de confirmaciones mixtas viven en [`change-control-policy.md`](change-control-policy.md) § "Ownership de archivos `.md`".

## Estados del requerimiento

Estado y fase son propiedades del REQ (la unidad abstracta de trabajo); ningún artefacto las define, solo las **registra**. ENUM canónico: cualquier artefacto que registre el estado del REQ usa este vocabulario. El mapa de artefactos por estado y las transiciones especiales (qué fases se saltan) viven en [`../workflow/index.md`](../workflow/index.md) y [`../process/delivery.md`](../process/delivery.md) respectivamente.

| Estado | Significado | Fase |
|---|---|---|
| `En progreso` | Plan aprobado, implementación en curso | 4 |
| `En validación` | Implementación lista, esperando validación (con QA, local con artefactos, o implícita) | 5 |
| `Listo para aprobación` | Validación pasada, esperando entrega final / aprobación del receptor | 6–7 |
| `Cerrado` | Entrega final confirmada por el dev (o aprobación del receptor) | post 8/9 |

**Bloqueado** se anota como sufijo del estado activo: `En progreso (bloqueado por X)`. No es estado paralelo — no inventa transiciones nuevas.

- El Change MD (registro canónico del REQ, relación 1↔1 incluso cross-repo) existe desde `Plan aprobado` (ver [`../workflow/changes.md`](../workflow/changes.md)); por convención registra `En progreso` como estado inicial. No hay estado "Propuesto".
- Los changes históricos pueden contener vocabulario previo (`Propuesto`, `COMPLETADO`, `Listo para producción`); no se migran. `Listo para producción` es el término anterior de `Listo para aprobación`.

Archivar el `work` de un REQ en la bitácora de relevo no altera el estado canónico del REQ.

## Tipos de validación

Clasificación según la naturaleza del entregable. Los pasos de ejecución de Fase 5 viven en [`../process/delivery.md`](../process/delivery.md) § "Validación".

- **Con ambiente de revisión** (e-commerce, etc.): el usuario valida el flujo principal en el ambiente de revisión antes de la entrega final.
- **Con ciclo de revisión cliente** (profiles de análisis): el cliente valida el entregable iterativamente; cada vuelta produce una nueva versión hasta la aprobación final.
- **Sin ambiente pero con artefactos** (scripts, migraciones, CLI): validación directa — ejecución local, simulación, o revisión.
- **Sin artefactos** (docs sin proceso, comentarios, typos): validación implícita — el usuario revisa en contexto y confirma.

> Los **profiles de proceso** (`self-applied` y sus overlays `research`/`skill-authoring`/`profile-authoring`) no usan un tipo aparte: validan con el mecanismo **verificable** de su entregable —revisión de roles + coherencia para lineamientos, `fact-check-reviewer` para research, smoke load + `validation-prompts` para skills— y **cierran de inmediato**. La observación en uso posterior (utilidad, triggering, fricción) es **retroalimentación de Fase 9** (ver [`../process/improvement.md`](../process/improvement.md)), no un gate de cierre.

## Niveles de riesgo de regresión

Eje ortogonal a la complejidad. 1 elemento cambiado con muchos dependientes = complejidad baja + riesgo alto. La regla que ata el riesgo al plan de pruebas (`medio`/`alto` exige fila `[crítico]`) vive en [`../process/planning.md`](../process/planning.md) § "Riesgo de regresión".

| Nivel | Criterio | Ejemplos |
|-------|----------|----------|
| Bajo  | Cambios aislados sin dependientes, docs/comentarios/typos, lógica sin condicionales sensibles | Typo en MD, log nuevo, comentario, formato |
| Medio | Lógica con dependientes acotados conocidos, configs no críticos, cambios localizados con uso identificable | Nuevo método con 2-3 dependientes, config de feature flag, cambio en helper |
| Alto  | Muchos dependientes, contratos públicos, flujos críticos (auth, pagos, datos), refactor transversal, **directiva/configuración global que altera cómo se resuelve un comportamiento transversal (rutas, identificadores, codificación, enrutamiento)** | Cambio en hash de password, modificar query SQL central, cambio de schema, renombre de método público, **cambiar una directiva de resolución global (rutas/referencias, codificación, enrutamiento) cuyos dependientes son consumidores dispersos —no un símbolo grep-eable— y no se enumeran con grep de callers** |
