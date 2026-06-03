# Plan review

Doble revisión paralela de planes, ejecutada en Fase 3 (Propuesta) antes de pedir OK al dev.

## Cuándo aplica

- **Stack `self-applied`** (cambios sobre `methodology` u otros proyectos auto-aplicados): **siempre**, salvo cosméticos (typos, reordenamientos, fixes de enlaces rotos).
- **Otros stacks** (software): cuando el REQ tiene **complejidad media/alta** O **riesgo de regresión medio/alto** (ver [`process/planning.md`](../process/planning.md)).
- **Complejidad baja sin regresión**: opcional. Claude lo propone solo si el plan toca dimensiones sensibles (auth, BD con DDL, routing crítico) o si el dev lo pide.

## Cuándo aplica el `context-completeness-reviewer`

Transversal a todos los stacks. Adicional a los revisores específicos del stack listados arriba — no los reemplaza. Su mandato es detectar suposiciones que el autor no verificó: estado concreto sin lectura/grep local (brecha de contexto) o dominio sin antecedente en skills/memoria/research (dominio desconocido). Ver [`../agents/context-completeness-reviewer.md`](../agents/context-completeness-reviewer.md).

**Frontera con `qa-process-engineer`**: `qa-process-engineer` audita lo que el autor **escribió** (consistencia entre archivos, vocabulario, casos borde sobre el texto presente). `context-completeness-reviewer` audita lo que el autor **NO leyó/investigó** (suposiciones sobre estado concreto o dominio sin verificar). Ejemplo: si el plan dice "el método A tiene 3 callers", `qa-process-engineer` revisa que la afirmación encaje en el documento; `context-completeness-reviewer` verifica que `grep` confirme los 3 callers o reporta la suposición.

| Fase | Condición de invocación |
|---|---|
| Fase 3 (plan-review) | Stack `self-applied`: cuando el plan introduce concepto/término nuevo, referencia archivo no leído en la sesión, o agrega regla con efecto cross-file. Patches puramente locales (un MD, sin conceptos nuevos) quedan exentos — el resto del plan-review los cubre. Otros stacks: cuando complejidad media/alta o riesgo de regresión medio/alto. |
| Fase 4 (cierre de implementación) | Cuando el artefacto producido difiere del plan aprobado en ≥1 archivo no listado o ≥1 sección no descrita, o cuando el rol principal detecta que hubo decisiones tomadas en implementación que no estaban en el plan. |
| Fase 7 (pre-entrega final) | Siempre que la entrega final cruce un ambiente compartido (PRD, repo público, doc al cliente). |

Output: tabla "Suposición | Tipo (`contexto` / `dominio`) | Cómo se resuelve | Resuelta? S/N". Si hay filas con N, **el gate/cierre de la fase queda bloqueado** hasta resolver (no se inventa estado nuevo del REQ — el ENUM de `workflow/index.md` se mantiene). Para suposiciones de tipo `dominio`, la resolución típica es abrir REQ de research siguiendo [`../stacks/research/conventions.md`](../stacks/research/conventions.md).

## Flujo

0. **Detección automática de roles** (ver [`roles-invocation.md`](roles-invocation.md) "Algoritmo de detección y consolidación"): Claude analiza la tabla `Archivo | Cambio` del plan propuesto, detecta dimensiones tocadas, consolida revisores, propone al dev: *"Plan toca dimensiones [X, Y]. Roles: principal `<rol>`, revisores `<rol>` + `<rol>`. ¿Ajustás?"*
1. **Rol principal** (Process Architect en stack `self-applied`; Software Engineer en software; o el que aplique según contexto) genera el plan inicial.
2. **Revisores en paralelo** — para cada revisor del stack activo, según su implementación (ver [`../methodology/roles-catalog.md`](../methodology/roles-catalog.md) "Implementación de roles"):
   - **Subagente** (rol tiene `.md` en `agents/`): invocar **solo si su dimensión de activación fue detectada en el paso 0**. Invocar vía `Agent(subagent_type=<nombre>, prompt=<briefing>)` usando la plantilla de briefing de la sección siguiente. Correr en paralelo cuando haya más de un subagente que aplique.
   - **Persona** (rol sin `.md` en `agents/`): simular inline cambiando de sombrero dentro de la misma respuesta.
   - **Nota de anidamiento**: los subagentes son invocados siempre por el rol principal en persona — nunca desde dentro de otro subagente. No hay riesgo de anidamiento en el flujo normal de plan-review.
3. **Rol principal** consolida hallazgos (subagentes + personas) y presenta el plan revisado en la misma respuesta.
4. Pide OK al dev.

## Plantilla de briefing para subagentes

Bloque que el rol principal pasa como `prompt` al invocar a cada subagente revisor. Completar los marcadores `<...>` con el contenido real del plan.

```
Eres <nombre del rol> en la metodología. Revisa el siguiente plan propuesto por el Process Architect / Software Engineer y reporta hallazgos según tu mandato.

## Plan propuesto

**REQ**: <descripción de una línea del requerimiento>
**Stack**: <stack activo>
**Archivos afectados**: <lista: Archivo | Cambio>

**Cambios propuestos**:
<contenido del plan en formato tabla o bullets — copiar la sección relevante>

## Lo que ya se sabe

<Si hay contexto relevante que el rol debe conocer (decisión del dev, restricción preexistente, antecedente) — resumir en bullets. Si no hay, omitir esta sección.>

## Tu tarea

Aplica tu mandato completo y reporta hallazgos. Máximo 300 palabras.
```

## Output

Hallazgos breves por rol (bullets) + plan revisado consolidado. Todo inline en la propuesta — no se generan artefactos separados.

## Nota de alcance

Este documento cubre el gate de **Fase 3** (plan-review sobre el plan propuesto). Los gates de **Fase 4** (cierre de implementación) y **Fase 7** (pre-ejecución de entrega final) usan la misma mecánica de invocación y plantilla de briefing, con el artefacto producido en lugar del plan — ver [`process/execution.md`](../process/execution.md) y [`process/delivery.md`](../process/delivery.md) respectivamente.
