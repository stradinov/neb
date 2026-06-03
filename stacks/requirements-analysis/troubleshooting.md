# Troubleshooting (requirements-analysis)

## Stakeholder no responde

**Síntoma**: se entregó `clar-vN` pero el stakeholder no envía feedback.

**Acción**:
1. Registrar en `preguntas-pendientes.md` con fecha de entrega.
2. Actualizar "Pendiente de entrega" en la memoria del proyecto con nota de espera.
3. Marcar estado como `En progreso (bloqueado — esperando feedback stakeholder desde YYYY-MM-DD)`.
4. En la siguiente sesión: recordar el bloqueo en el primer mensaje.
5. No cerrar ni avanzar unilateralmente. El ciclo solo avanza cuando el stakeholder responde.

**Escalada**: si supera el tiempo acordado, el dev decide contacto directo o cierre del análisis.

## Scope-creep durante iteraciones

**Síntoma**: el stakeholder agrega nuevos casos de uso o funcionalidades después de `clar-v2` o posterior.

**Acción**:
1. Identificar si el nuevo ítem está dentro del objetivo del requerimiento (sección 2) o es adicional.
2. Si es adicional: agregar a la sección "No entra" con nota `[propuesto por stakeholder vN, evaluación pendiente]`.
3. Proponer al dev: ¿absorber en este análisis (ampliando alcance y estimación) o diferir a un nuevo sub-proyecto?
4. Si se absorbe: actualizar secciones Alcance, CU, Estimación y bitácora.
5. Si se difiere: documentar en `preguntas-pendientes.md` como `[Q-N]: evaluar nuevo requerimiento <descripción>` y notificar al stakeholder.

**Señal de alerta**: si (CU en v_final) / (CU en v1) > 1.5 → scope-creep alto. Proponer revisión de proceso con el stakeholder.

## Supuestos invalidados

**Síntoma**: el stakeholder confirma que un `[S-N]` es incorrecto durante una iteración.

**Acción**:
1. Marcar el supuesto como `[S-N] ~~supuesto previo~~ → [INVALIDADO] nueva información`.
2. Revisar qué CU, dependencias o estimaciones dependen de ese supuesto.
3. Actualizar las secciones afectadas.
4. Si la invalidación cambia la estimación significativamente (>1 nivel de complejidad): notificar al dev antes de enviar `clar-v(N+1)`.
5. Registrar en bitácora.

## Alucinaciones en `clar-v0-auto`

**Síntoma**: el borrador auto-generado contiene supuestos sobre el proyecto que son incorrectos.

**Acción**:
1. El BA revisa siempre el `clar-v0-auto` antes de elevarlo a `clar-v1`.
2. Para cada supuesto incorrecto: corregir y agregar nota `[corregido por BA]` en la bitácora.
3. Si las alucinaciones son sistémicas (>3 en el mismo borrador): evaluar si falta contexto del dominio en el prompt inicial.
4. **Nunca** enviar el `clar-v0-auto` directamente al stakeholder sin revisión humana.

## Reanudar tras pausa larga

**Síntoma**: el sub-proyecto lleva semanas sin actividad; el dev reanuda sin contexto.

**Acción**:
1. Leer la memoria del proyecto: "Requerimiento activo" y "Pendiente de entrega".
2. Leer el `clarificacion.md` (versión actual) para retomar contexto.
3. Revisar `preguntas-pendientes.md` — ¿hay preguntas que el stakeholder ya respondió fuera de sesión?
4. Resumir estado en una línea al dev: "Retomamos análisis `<slug>` (`clar-v<N>` enviado YYYY-MM-DD, esperando feedback de [Q-1] y [Q-3])."
5. Preguntar si hay información nueva antes de continuar.

## Documento demasiado extenso

**Síntoma**: el documento supera ~300 líneas y se vuelve difícil de revisar.

**Acción**:
1. Evaluar si el requerimiento es en realidad 2+ requerimientos independientes.
2. Si es divisible: proponer separar en 2 sub-proyectos bajo el mismo proyecto.
3. Si no: agregar un "Resumen ejecutivo" al inicio del documento (≤1 página) para que el stakeholder se oriente antes de leer los detalles.
