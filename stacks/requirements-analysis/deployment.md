# Deployment (requirements-analysis)

Sin servidores. La "entrega" es el documento enviado al stakeholder; la "producción" es la aprobación.

## Pre-condiciones de entrega al stakeholder

- Ningún `[Q-N]` crítico sin etiqueta explícita en el documento.
- Frontmatter actualizado con versión y estado (`En revisión stakeholder vN`).

## Entrega para revisión (equivalente a "deploy a QA")

1. Commit: `git commit -m "reqs(<slug>): clar-vN — <descripción breve>"`
2. Push: `git push`
3. Notificar al stakeholder:
   - Medio: el canal del equipo (correo, Slack, tícket, etc.).
   - Contenido mínimo: qué cambió respecto a la versión anterior + link al commit o documento exportado + preguntas `[Q-N]` que requieren respuesta.
4. Actualizar memoria del proyecto: "Pendiente de entrega" con qué feedback se espera.
5. Actualizar frontmatter: `estado: En revisión stakeholder vN`.

**Claude NO marca como "En revisión" sin haber notificado al stakeholder en la misma sesión o sin confirmación del dev de que la notificación se hizo fuera de sesión.**

## Entrega final / aprobación (equivalente a "deploy a producción")

> **Claude NUNCA registra una aprobación sin señal explícita del stakeholder en la misma sesión.** Una aprobación verbal pasada no se reusa sin confirmación.

1. Stakeholder comunica aprobación (correo, doc firmado, tícket cerrado).
2. Completar sección "Aprobación" del documento: firmante, fecha, medio.
3. Actualizar frontmatter: `estado: Aprobado`.
4. Commit: `git commit -m "reqs(<slug>): clar-approved — aprobado por <stakeholder> el YYYY-MM-DD"`
5. Push: `git push`
6. Limpiar "Pendiente de entrega" de la memoria del proyecto.
7. Proceder a Documentación (Fase 8) y cerrar el sub-req en `changes/`.

## Rollback

Si el stakeholder cambia de criterio tras aprobar:

1. Abrir nuevo ciclo iterativo (`clar-v<N+1>`) — no reescribir el commit `clar-approved`.
2. El historial git preserva la versión aprobada.
3. Si el cambio es drástico (nuevo alcance, nuevos stakeholders), evaluar si corresponde un nuevo sub-proyecto o una nueva versión mayor.

## Tipo de validación

**Con ciclo de revisión stakeholder** — iterativo hasta `clar-approved`. No hay "validación implícita": el documento siempre sale al stakeholder antes de considerarse aprobado.

## Criterios de cierre del sub-req de análisis

1. Commit `clar-approved` existe en el repo del proyecto.
2. Sección "Aprobación" del documento completada con firmante y fecha.
3. "Pendiente de entrega" de la memoria del proyecto vacío.
4. Sub-req en `changes/` marcado como `Cerrado`.
