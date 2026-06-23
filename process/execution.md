# Execution

Estándares de implementación, plan mode, gestión de tareas, incidencias.

## Insumos de contexto (Fase 4)

Al implementar en un proyecto cuyo profile tiene un skill asociado (ver `profiles/<profile>/skills.md`), consultarlo antes de modificar código para:

- Mapear callers/dependientes antes de tocar un método o campo compartido (convención de `personal/<usuario>.md`).
- Identificar el patrón de override correcto si se toca código del core/upstream.

## Estándares

Los estándares de código (baseline: sin comentarios salvo WHY no obvio, sanitizar en fronteras, sin features/refactors no pedidos, sin backwards-compat innecesario) viven en [`../methodology/coding-standards.md`](../methodology/coding-standards.md); cada profile los concreta en `profiles/<profile>/conventions.md`. Al terminar la implementación: lista de archivos modificados con una línea por cambio.

## Plan mode

- Solo acciones read-only y edición del archivo de plan.
- Cierra con `ExitPlanMode` (aprobación del usuario).
- Al ejecutar `ExitPlanMode`, salir también de auto mode si estaba activo.
- Cada plan aprobado en plan mode se guarda automáticamente vía hook; los aprobados conversacionalmente (media/alta) se persisten vía `Write` (ver [workflow/approved-plans.md](../workflow/approved-plans.md)).

Usar plan mode cuando: el cambio toca múltiples archivos, hay decisiones arquitectónicas, o conviene ver el plan antes de gastar tiempo en código.

NO usar para: bug fix de una línea, renombres triviales, tareas exploratorias.

Selección de modelo en plan mode: ver [models.md](../general/models.md).

## Tareas

Para 3+ pasos discretos, usar `TaskCreate` y `TaskUpdate`. Marcar `in_progress` al iniciar y `completed` al terminar — no batchear.

Si una tarea se bloquea, mantenerla `in_progress` y crear una nueva describiendo el bloqueo. No marcar completada si tests fallan, hay implementación parcial, o errores sin resolver.

## Confirmación del cambio en Fase 4

Antes de cada confirmación del cambio que toque el entregable del proyecto destino, Claude espera OK explícito del dev. La regla canónica (alcance, granularidad, excepciones) vive en [`change-control.md`](change-control-gate.md) § "Autorización de la confirmación del cambio"; su concretización git (qué es un `git commit`, exclusiones de gobernanza) en [`process/version-control.md`](version-control.md).

## Cierre de Fase 4 (gate de subagente)

Antes de declarar Fase 4 terminada y transicionar a Fase 5, el rol principal (persona) invoca al menos un subagente del profile como gate adversarial del **artefacto implementado** — no del plan. El subagente recibe un briefing explícito con el artefacto final usando la misma plantilla que Fase 3 (ver [`process/plan-review.md`](plan-review.md) "Plantilla de briefing"), adaptando la sección "Plan propuesto" para describir el artefacto producido.

Qué subagente por profile (por defecto + paralelos por dimensión): ver la matriz columna **F4** en [`roles-invocation.md`](roles-invocation.md) § "Cobertura mínima por fase". Si el profile no tiene subagente formalizado, el dev declara override explícito antes de avanzar a Fase 5.

**Adicional transversal**: el `context-completeness-reviewer` se invoca en este gate cuando el artefacto producido difiere del plan aprobado en ≥1 archivo no listado o ≥1 sección no descrita, o cuando el rol principal detecta que hubo decisiones tomadas en implementación que no estaban en el plan. Aplica a cualquier profile. Output: tabla de suposiciones contexto/dominio; si hay filas no resueltas, el cierre del gate queda bloqueado hasta resolver. Ver [`plan-review.md`](plan-review.md) § "Cuándo aplica el `context-completeness-reviewer`".

## Gestión de sesiones (handoff)

### Retomar una sesión interrumpida

Al retomar un requerimiento interrumpido:

1. Leer la memoria del proyecto (`project_<nombre>.md` para contexto duradero + el `active_<proyecto>_<slug>.md` del REQ).
2. Leer el MD del requerimiento (`<proyecto>/changes/<fecha>-<nombre>.md`) para ver estado.
3. Si el `active_*.md` tiene "Pendiente de entrega" → atender primero.
4. Si la última fase no está cerrada → continuar desde ahí.
5. Si la sesión se reanudó vía `claude --resume <nombre>`, eliminar la entrada correspondiente en `pendings.md` §"Sesiones pausadas".

Resumir el estado en una línea al inicio:

> "Retomamos `proteger-textos-zonacliente` (en Fase 5 — validación pendiente). ¿Validaste el flujo principal?"

### Pausar y reanudar la misma sesión Claude

Cuando el dev anuncia que pausará para continuar después en otra sesión, la sesión actual debe quedar recuperable por nombre — `claude --continue` solo recupera la última, y si el dev abre una sesión intermedia se pierde el hilo. La **acción de Claude** al detectar el anuncio de pausa (nombrar la sesión, registrar en `pendings.md`, confirmar) vive en [`../general/communication.md`](../general/communication.md) §"Handoff de sesión".

**Comandos disponibles para el dev**:

- `claude --resume <nombre>` — reanudar por nombre.
- `claude --resume` — picker interactivo (todas las sesiones del proyecto; `Ctrl+A` para todos los proyectos).
- `claude -n <nombre>` — nombrar al iniciar una sesión nueva (si el dev quiere prefijar antes del primer turno).

### Relevo cross-dev (bitácora de relevo)

Para retomar trabajo **en otra máquina o por otro dev** (lo que `--resume` no permite cross-machine), Neb usa la **bitácora de relevo**. El artefacto y su modelo de ownership viven en [`../workflow/logbook.md`](../workflow/logbook.md); la mecánica (backend, hook, config) en [`../tooling/logbook.md`](../tooling/logbook.md). El protocolo:

- **Publicar (automático).** El hook publica/actualiza la entrada del `work` en cada `Stop`/`SessionEnd`/`PreCompact`. Al pausar deliberadamente, Claude redacta en el estado semántico el bloque **"Trabajo en vuelo"**: cómo **relanzar** agentes/scripts que quedaron a medias — es prosa que Claude escribe (los procesos no se serializan; el hook no los introspecta), junto a "próximos pasos".
- **Retomar.** En la otra máquina/cuenta: `/logbook search`/`list` (contra el central) lista los `work` relevables; el dev **toma el mando** (`tomar`, atómico en el central) y abre una **sesión nueva** (no `--resume` cross-machine) alimentada con el transcript como contexto + el índice semántico. **Continúa el mismo `change_md`** que apunta la entrada (no crea uno nuevo): el registro ya está entregado por la entrega temprana. Relanza el trabajo en vuelo desde lo materializado.
- **Relevar.** El owner **libera** al pausar; otro dev **solicita el mando** si está `owned`; **`liberar --forzado`** (con confirmación) cubre el caso de owner ausente (corte sin liberar). Estados y reglas: [`../workflow/logbook.md`](../workflow/logbook.md) §"Modelo de ownership".
- **Reconciliación al volver a un `work` ya relevado.** Si un dev retoma una sesión cuyo `work` otro ya tomó/cerró, su `publish` recibe **`409`** (marca `conflict` local) y `/logbook` lo reporta. El registro (change MD) de quien cerró es **canónico** — Claude avisa y el dev reconcilia su trabajo local (código no pusheado) sobre el head publicado, **no lo duplica** (el `--resume` cross-machine no transfiere el working tree; ver [`../workflow/logbook.md`](../workflow/logbook.md)).
- **Modo exploratorio** (sin REQ formal): se reanuda con **`--resume` local** del mismo dev; con **entorno compartido** también se publica al catálogo (visibilidad/búsqueda), pero no es relevable cross-dev hasta formalizarse en REQ (ver [`../workflow/logbook.md`](../workflow/logbook.md) §"Dos modos" y §"Entorno compartido").

## Incidencias durante el trabajo

(Para incidentes detectados post-entrega final, ver [incidents.md](../general/incidents.md).)

Cambios menores que surgen durante el trabajo (renombre de columna, archivo SQL faltante, bug detectado en repaso) se tratan como **incidencias durante el trabajo** — no como sub-requerimientos — siempre que no afecten el plan original.

Claude propone el cambio en una línea y procede con aprobación implícita o explícita. **No vuelve a clarificación ni genera estimado nuevo.**

Al resolver, documentar de inmediato en la memoria del proyecto (lo duradero en `project_<nombre>.md`; lo propio del REQ en su `active_<proyecto>_<slug>.md`):
- Qué fue (una línea).
- Cómo se resolvió (una línea).
- Si requiere paso adicional en la entrega final → "Pendiente de entrega" del `active_*.md`.
