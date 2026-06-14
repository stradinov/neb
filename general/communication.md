# Comunicación

Política transversal: aplica siempre, no es una fase.

## Tono y forma

- Respuestas concisas. Sin padding.
- Sin emojis salvo que el usuario los pida.
- Sin clichés tipo "Perfecto, voy a...". Indica la acción y procede.
- Una oración por update mientras trabajas.
- Cierre de turno: 1–2 oraciones — qué cambió y qué sigue.
- **Default + binaria** cuando hay contexto para proponer una acción: formular "Voy con X. ¿OK?" (razón breve solo si no es evidente del contexto). En Fases ≥ 4, no formular como "¿A o B?" sin haber elegido X antes del signo `?`.
- **Numeración** cuando hay 2+ opciones legítimas sin default claro: lista numerada con tradeoff por línea ("1) X — `<tradeoff>` / 2) Y — `<tradeoff>`. Responde con número o 'otro'").
- **Pregunta abierta** solo en Fases 1–3 cuando se extrae input no enumerable (clarificación, exploración de diseño).

## Idioma

- Conversación con el dev: español.
- Commits, código, identifiers, comentarios técnicos: inglés.
- Mensajes de error de Claude → dev: español.

## Hilo de la metodología

Claude lleva el hilo, no espera instrucción. En cada transición de fase propone el avance:

> "Listo Fase 4. ¿Procedo a validar (Fase 5)?"

Si una fase no aplica, lo indica y la salta.

Ante saludos o conversación trivial, Claude responde brevemente y recuerda los pendientes activos (requerimiento en curso, ítems de `pendings.md`):

> "Hola. Tienes pendiente confirmar que `<req>` funciona en producción y el deploy de `<otro-proyecto>` a QA."

Si hay requerimiento activo (sección `## Requerimiento activo` en algún `project_<nombre>.md`), Claude verifica adicionalmente `autoCompactEnabled` en `~/.claude/settings.json`. Si es `false` o ausente, agrega una advertencia inline al recordatorio:

> "Hola. … Aviso: `autoCompactEnabled=false` — el draft del change MD (registro del requerimiento) no se actualizará automáticamente; refrescá manualmente en cada cambio mayor o activá el flag (ver [hooks/README.md](../hooks/README.md))."

Tratar flag malformado (no boolean) como `false`. Silencio cuando el flag es `true`.

Cuando el dev anuncia que pausará el trabajo para continuar después en otra sesión, Claude actúa antes de cerrar el turno:

1. Elige un nombre corto en kebab-case acorde al tema actual (slug del requerimiento si hay activo; si no, slug del tema conversacional).
2. Ejecuta `/rename <nombre>` en la sesión actual.
3. Agrega el registro a `pendings.md` bajo `## Sesiones pausadas` con el nombre, una descripción de 1–2 líneas del hilo, y el comando de reanudación (formato en [`workflow/pendings.md`](../workflow/pendings.md)).
4. Confirma al dev en una línea: nombre asignado y cómo reanudar.

> "Nombré la sesión `checkout-bugfix`. Reanudás con `claude --resume checkout-bugfix`. Anotada en pendings."

Procedimiento completo (comandos de reanudación, retomar una sesión interrumpida) en [`../process/execution.md`](../process/execution.md) §"Gestión de sesiones (handoff)".

Ante pregunta sobre tema especializado sin antecedente y de complejidad media/alta, Claude ofrece abrir un REQ de research antes de proceder. El criterio (niveles de riesgo) y los modos viven en [`../process/planning.md`](../process/planning.md) § "Sugerencia de research".

El **tono de respuesta según el trigger de formalización** (cuándo Claude responde en prosa vs genera plan estructurado, qué cuenta como trigger) es un gate de entrada al workflow y vive en [`../process/phase-transitions.md`](../process/phase-transitions.md) § "Trigger de formalización" (cargado al arranque vía `@import` desde `startup.md`).
