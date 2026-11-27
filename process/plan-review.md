# Revisión del plan (plan-review)

Doble revisión paralela de planes, ejecutada en Fase 3 (Propuesta) antes de pedir OK al dev.

## Cuándo aplica

- **Profile `self-applied`** (cambios sobre `methodology` u otros proyectos auto-aplicados): **siempre**, salvo cosméticos (typos, reordenamientos, fixes de enlaces rotos).
- **Otros profiles** (software): cuando el REQ tiene **complejidad media/alta** O **riesgo de regresión medio/alto** (ver [`process/planning.md`](../process/planning.md)).
- **Complejidad baja sin regresión**: opcional. Claude lo propone solo si el plan toca dimensiones sensibles (auth, BD con DDL, routing crítico) o si el dev lo pide.

## Cuándo aplica el `context-completeness-reviewer`

Transversal a todos los profiles. Adicional a los revisores específicos del profile listados arriba — no los reemplaza. Su mandato es detectar suposiciones que el autor no verificó: estado concreto sin lectura/grep local (brecha de contexto) o dominio sin antecedente en skills/memoria/research (dominio desconocido). Ver [`../agents/context-completeness-reviewer.md`](../agents/context-completeness-reviewer.md).

**Frontera con `qa-process-engineer`**: `qa-process-engineer` audita lo que el autor **escribió** (consistencia entre archivos, vocabulario, casos borde sobre el texto presente). `context-completeness-reviewer` audita lo que el autor **NO leyó/investigó** (suposiciones sobre estado concreto o dominio sin verificar). Ejemplo: si el plan dice "el método A tiene 3 callers", `qa-process-engineer` revisa que la afirmación encaje en el documento; `context-completeness-reviewer` verifica que `grep` confirme los 3 callers o reporta la suposición.

| Fase | Condición de invocación |
|---|---|
| Fase 3 (plan-review) | Profile `self-applied`: cuando el plan introduce concepto/término nuevo, referencia archivo no leído en la sesión, o agrega regla con efecto cross-file. Patches puramente locales (un MD, sin conceptos nuevos) quedan exentos — el resto del plan-review los cubre. Otros profiles: cuando complejidad media/alta o riesgo de regresión medio/alto. |
| Fase 4 (cierre de implementación) | Cuando el artefacto producido difiere del plan aprobado en ≥1 archivo no listado o ≥1 sección no descrita, o cuando el rol principal detecta que hubo decisiones tomadas en implementación que no estaban en el plan. |
| Fase 7 (pre-entrega final) | Siempre que la entrega final cruce un ambiente compartido (PRD, repo público, doc al cliente). |

Output: tabla "Suposición | Tipo (`contexto` / `dominio`) | Cómo se resuelve | Resuelta? S/N". Si hay filas con N, **el gate/cierre de la fase queda bloqueado** hasta resolver (no se inventa estado nuevo del REQ — el ENUM de `workflow/index.md` se mantiene). Para suposiciones de tipo `dominio`, la resolución típica es abrir REQ de research siguiendo [`../profiles/research/conventions.md`](../profiles/research/conventions.md).

## Flujo

0. **Detección automática de roles** (ver [`roles-invocation.md`](roles-invocation.md) § "Algoritmo de detección y consolidación"): Claude analiza la tabla `Archivo | Cambio` del plan propuesto, detecta dimensiones tocadas, consolida revisores, propone al dev: *"Plan toca dimensiones [X, Y]. Roles: principal `<rol>`, revisores `<rol>` + `<rol>`. ¿Ajustás?"*
1. **Rol principal** (Process Architect en profile `self-applied`; Software Engineer en software; o el que aplique según contexto) genera el plan inicial. Si la Re-verificación de [`platform-assumptions.md`](../methodology/platform-assumptions.md) § "Mantenimiento" alcanza a una fila del diseño (un mecanismo nuevo, o una regla que se cambia por cómo se comporta la plataforma), el rol principal prueba lo que de ella se puede probar en una sesión desechable antes de pasar el plan a los revisores; mientras no esté probado, el plan no va a OK.
2. **Revisores en paralelo** — para cada revisor del profile activo, según su implementación (ver [`../methodology/roles-catalog.md`](../methodology/roles-catalog.md) § "Implementación de roles"):
   - **Subagente** (rol tiene `.md` en `agents/`): invocar **solo si su dimensión de activación fue detectada en el paso 0**. Invocar vía `Agent(subagent_type=<nombre>, prompt=<briefing>)` usando la plantilla de briefing de la sección siguiente. Correr en paralelo cuando haya más de un subagente que aplique. Si el dev pidió un workflow, el mismo subagente puede correr como agente del workflow con `agentType`, con el mismo briefing (supuestos R11, R16 y R18 de [`platform-assumptions.md`](../methodology/platform-assumptions.md)). El revisor corre con el modelo y el esfuerzo de la sesión (supuesto R20); bajarlos pide OK del dev.
   - **Persona** (rol sin `.md` en `agents/`): simular inline cambiando de sombrero dentro de la misma respuesta.
   - **Despacho desde el hilo principal**: el rol principal invoca a los revisores porque los hallazgos se consolidan y se le preguntan al dev en el hilo principal. Que la plataforma permita a un subagente lanzar otros (supuesto R13) no cambia este flujo.
3. **Rol principal** consolida hallazgos (subagentes + personas) y presenta el plan revisado en la misma respuesta. Los hallazgos que sostengan una pregunta o una opción al dev, o una corrección del plan, siguen [`../methodology/principles.md`](../methodology/principles.md) § "Suposiciones explícitas antes de afirmar". Una alternativa que un revisor reporta contra la letra del pedido o contra un plan que daba una pieza por hecha llega al dev como opción, o el plan dice por qué no y cita el hallazgo; la letra del pedido, un plan previo o el criterio de un rol no son razón. El briefing no les pide a los revisores decidir qué opciones o decisiones le tocan al dev.
4. Pide OK al dev. El plan que acompaña la petición lleva, en una línea propia antes de su primera sección `##`, la constancia del plan-review en una de tres formas:
   - `**Plan-review:** <rol>, <rol> · <AAAA-MM-DD>`: los roles que lo revisaron y la fecha.
   - `**Plan-review:** exento — <motivo> · override explícito del dev <AAAA-MM-DD>`: solo con ese override; Claude no se exime solo.
   - `**Plan-review:** no aplica — <motivo>`: cuando § "Cuándo aplica" no lo exige (cosmético en `self-applied`, research sin `propósito = decisión`).

   Rige en todo plan de complejidad media/alta y en todo plan que § "Cuándo aplica" sujete a plan-review aunque no se persista (complejidad baja en `self-applied`). Una re-aprobación o un plan delta es una aprobación nueva y lleva su propia línea. El rol principal que detecte un plan aprobado sin la línea (p. ej. por un menú sin el plan a la vista) corre el plan-review retroactivo y pide re-aprobación antes de la primera confirmación del entregable.

## Plantilla de briefing para subagentes

Bloque que el rol principal pasa como `prompt` al invocar a cada subagente revisor. Completar los marcadores `<...>` con el contenido real del plan.

```
Eres <nombre del rol> en la metodología. Revisa el siguiente plan propuesto por el Process Architect / Software Engineer y reporta hallazgos según tu mandato.

## Plan propuesto

**REQ**: <descripción de una línea del requerimiento>
**Profile**: <profile activo> (con la ruta de su `deployment.md` y la del núcleo de Neb en uso, que en `self-applied` es el clon que se edita: el revisor no recibe el arranque de la sesión, supuesto R12 de `methodology/platform-assumptions.md`)
**Registro**: <ruta del registro del requerimiento, si ya existe>
**Archivos afectados**: <lista: Archivo | Cambio>

**Cambios propuestos**:
<contenido del plan en formato tabla o bullets — copiar la sección relevante>

## Lo que ya se sabe

<Si hay contexto relevante que el rol debe conocer (decisión del dev, restricción preexistente, antecedente) — resumir en bullets. En una re-revisión, cada corrección con la fuente que la sostiene y con el texto que agrega o reescribe, literal o por su ubicación; si la fuente es la salida de un comando o un estado que el revisor no puede leer, con su extracto. Si no hay, omitir esta sección.>

## Tu tarea

Aplica tu mandato completo y reporta hallazgos. No decides qué opciones se le presentan al dev ni qué decisiones le tocan: una alternativa que contradice la letra del pedido se reporta con su tradeoff, no se descarta (`general/communication.md` § "Avance del trabajo: ejecuta-y-reporta vs. gate", «Intención sobre letra»). Si la corrección de un hallazgo cae en el registro del REQ o en el changelog, escribe el texto literal que propones y di dónde cae: archivo y línea, o el texto que reemplaza. En una re-revisión, coteja cada corrección con su fuente: la que no tenga fuente, cuya fuente no puedas leer y no traiga extracto, o cuya fuente no la sostenga es un hallazgo. También lo es lo que dependa de una corrección y no la refleje, en los términos del bullet «Corrección de un artefacto del REQ» de `methodology/principles.md` § "Suposiciones explícitas antes de afirmar". <Solo en una re-revisión, en el briefing de uno solo de los subagentes revisores que corren, el que el rol principal elija, agregar (en otro caso, omitir): Además, por cada texto que una corrección agrega o reescribe, busca en el proyecto que se edita y en las rutas de **Profile** lo que ya rige fuera de los cambios del REQ y ese texto contradice, prohíbe o deja sin cubrir, y repórtalo: la corrección se cotejó con su fuente, no con lo que esa fuente no nombra.> Máximo 300 palabras.
```

## Output

Hallazgos breves por rol (bullets) + plan revisado consolidado. Todo inline en la propuesta — no se generan artefactos separados.

Al abrir el registro del REQ tras aprobarse el plan, el rol principal anota en él cada hallazgo con el rol que lo levantó y su desenlace (incorporado al plan o descartado), como en [`execution.md`](execution.md) § "Cierre de Fase 4 (gate de subagente)": la propuesta vive en la conversación, y sin esa anotación el aporte de cada rol en Fase 9 se asigna de memoria. La línea `**Plan-review:**` del paso 4 queda en el plan aprobado; el desglose por rol vive solo en el registro.

## Nota de alcance

Este documento cubre el gate de **Fase 3** (plan-review sobre el plan propuesto). Los gates de **Fase 4** (cierre de implementación) y **Fase 7** (pre-ejecución de entrega final) usan la misma mecánica de invocación y plantilla de briefing, con el artefacto producido en lugar del plan — ver [`process/execution.md`](../process/execution.md) y [`process/delivery.md`](../process/delivery.md) respectivamente. En esos gates:

- La detección de dimensiones del paso 0 se corre sobre los archivos del entregable, haya habido plan-review o no (sin plan-review, opcional en complejidad baja, no hay paso 0 previo).
- Si la detección no activa ningún subagente, el piso de ≥1 subagente de [`roles-invocation.md`](roles-invocation.md) § "Cobertura mínima por fase" se cubre con el revisor default del profile (si el profile no define uno para esa fase, con override explícito del dev).
