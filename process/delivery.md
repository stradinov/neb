# Delivery

Validación, entrega, cierre. (Entrega específica por stack: ver `stacks/<stack>/deployment.md`.)

## Validación

Los 5 tipos de validación (con ambiente de revisión, con ciclo de revisión cliente, sin ambiente pero con artefactos, sin artefactos, diferida en uso) viven en [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Tipos de validación". El stack determina cuál aplica.

Si algo falla: usuario describe error → Claude diagnostica → fix → revalidar. El usuario puede delegar la validación a Claude cuando hay artefactos. Una corrección en la misma sesión **no vuelve a clarificación** salvo que el alcance cambie.

## Transiciones especiales de estado

Aplican sobre el ENUM de estados (ver [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Estados del requerimiento"):

- **Validación implícita** (sin artefactos: docs, metodología): `En progreso` → `Cerrado` directo. Se omiten `En validación` y `Listo para aprobación`.
- **Cambios sin ambiente de revisión pero con artefactos** (scripts, migraciones, CLI): `En progreso` → `En validación` → `Cerrado`. Se omite `Listo para aprobación`.
- **Validación falla**: `En validación` → `En progreso` sin formalizar.

## Confirmación del cambio y entrega

La política universal de control de cambios (autorización en Fase 4, ownership de `.md`, punto de restauración, mecanismo de versionamiento por stack) vive en [change-control.md](change-control-gate.md). Su concretización git (formato de commits, push, ramas, CHANGELOG) en [`process/version-control.md`](version-control.md). Cada stack documenta su mecanismo en `stacks/<stack>/deployment.md`.

## Pre-condiciones de entrega final

Independiente del stack:

- **Punto de restauración**: debe existir un estado previo recuperable antes de la entrega final (ver [change-control.md](change-control-gate.md) § "Punto de restauración"). Sin él no hay rollback rápido — ver [incidents.md](../general/incidents.md).
- Condiciones adicionales por stack (BD, routing crítico, firma del cliente, etc.): ver `stacks/<stack>/deployment.md`.

Pasos específicos por stack: `stacks/<stack>/deployment.md`.

## Definición de done

Los criterios de completitud (obligatorios que bloquean el cierre, checkpoint, confirmación post-entrega) viven en [`../methodology/done-criteria.md`](../methodology/done-criteria.md). El cierre (abajo) los verifica.

## Pre-ejecución de Fase 7 (gate de subagente)

Antes de ejecutar la entrega final (deploy a prod, `git push`, `pscp`/`ssh`, notificación al cliente), el rol principal (persona) invoca al menos un subagente del stack como último gate adversarial. El briefing describe el **artefacto final + ambiente destino** usando la misma plantilla que Fase 3 (ver [`process/plan-review.md`](plan-review.md) "Plantilla de briefing").

Qué subagente por stack (default + obligatorio adicional por dimensión, p. ej. `security-reviewer` si el deploy toca auth/datos sensibles, `database-engineer` si hay DDL): ver la matriz columna **F7** en [`roles-invocation.md`](roles-invocation.md) § "Cobertura mínima por fase". Si el stack no tiene subagente formalizado, el dev declara override explícito.

**Adicional transversal**: el `context-completeness-reviewer` se invoca en este gate siempre que la entrega final cruce un ambiente compartido (PRD, repo público, doc al cliente). Aplica a cualquier stack. Output: tabla de suposiciones contexto/dominio; si hay filas no resueltas, el gate de entrega queda bloqueado hasta resolver. Ver [`plan-review.md`](plan-review.md) § "Cuándo aplica el `context-completeness-reviewer`".

## Cierre del requerimiento

Antes de la entrega final:

1. Verificar pendientes — sección "Pendiente de entrega" de la memoria + tareas abiertas.
2. Si hay pendientes → notificar y preguntar si resolverlos antes de cerrar.
3. Presentar el **Reporte de cierre** — leer la sección `## Reporte de cierre` del draft del change MD y mostrarla al dev inline. Si el bloque de "Uso de API" está vacío (hook no corrió), indicarlo.
4. Si no hay pendientes (o el dev decide no continuar) → preguntar:
   > "¿Damos el requerimiento por terminado? Procedo a Documentación (Fase 8)."
5. Al confirmar → marcar `Cerrado` en el MD (ver [`workflow/index.md`](../workflow/index.md) "Estados del requerimiento"). Marcar `Cerrado` y **confirmar+entregar el change MD son un solo acto**: el commit final y el push del change MD (`.md`-only, autónomo por ownership `.md` — ver [change-control.md](change-control-gate.md) y [`process/version-control.md`](version-control.md) § Push) se ejecutan en el mismo acto de marcar `Cerrado` —que ocurre solo cuando el REQ alcanza el cierre por el criterio de su stack (en `self-applied`, ≥ 10 sesiones; ver `stacks/<stack>/deployment.md`)—, sin esperar una indicación separada del dev. Cubre el push del **change MD**, no del entregable.
6. **Entrega final** — entrega el entregable + documentación juntos según `stacks/<stack>/deployment.md` (en stacks git: push único). El entregable sigue su gate de validación/entrega por stack; el push `.md`-only del cierre no lo arrastra.
7. Salir de auto mode si estaba activo. Proceder a Fase 8.
