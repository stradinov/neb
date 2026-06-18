# Definición de done

Criterios que determinan cuándo un **requerimiento** está terminado. Lo que se termina es el requerimiento (la unidad de trabajo); las condiciones se verifican sobre su **registro** —el change MD que lo registra (relación 1↔1, también cross-repo: un único MD en el repo central; ver [`../workflow/traceability.md`](../workflow/traceability.md))—. Son **condiciones** (qué debe cumplirse), no pasos — el gate que las verifica vive en [`../process/delivery.md`](../process/delivery.md) § "Cierre del requerimiento".

> **Punto de customización**: un adoptante puede estrechar o ampliar estos criterios para su contexto (p. ej. exigir cobertura de tests, aprobación de QA, o checklist de accesibilidad) declarándolo en su `profiles/<profile>/` o `personal/<usuario>.md`. No puede relajar los obligatorios del baseline.

## Obligatorios (bloquean el cierre)

- [ ] **Plan de pruebas completado** — según complejidad, verificado en el registro del requerimiento (change MD):
  - **Media/alta**: tabla `### Resultado` del [`change.md.template`](../templates/change.md.template) sin ❌. Cualquier ❌ requiere fix + revalidar.
  - **Baja**: checklist `- [x]` del Plan de pruebas suficiente.
  - **Validación implícita** (sin artefactos, ver [`../process/delivery.md`](../process/delivery.md) § Validación): se omite la tabla; cierre por confirmación inline del dev.
- [ ] **Flujos críticos** — si el riesgo de regresión es `medio`/`alto` (ver [vocabulary.md](vocabulary.md) "Riesgo de regresión"): la tabla incluye ≥1 fila con prefijo `[crítico]` y todas las filas `[crítico]` están en ✅. Cualquier `[crítico]` con ❌ bloquea cierre.
- [ ] **Validación superada** — usuario o Claude confirmó (o cliente aprobó, según profile). Claude registra fecha.
- [ ] **Sin tareas abiertas** — todas en `completed`, ninguna `in_progress`.

## Checkpoint (no bloquea)

**"Pendiente de entrega"** — la sección del `active_<proyecto>_<slug>.md` del REQ (ver [`../workflow/memory.md`](../workflow/memory.md)). Si tiene ítems, el cierre los notifica y espera decisión: resolver antes de cerrar, o cerrar igual.

## Confirmación post-entrega (no bloquea, salvo complejidad alta)

1. **Señal positiva del dev** — agradecimiento o reconocimiento explícito. Si hay varios requerimientos en paralelo, Claude infiere por contexto.
2. **Seguimiento diferido** — sin señal, Claude cierra y agrega a `pendings.md`: `[ ] Confirmar que <req> está aprobado en el ambiente final — validado <fecha>`. El ítem persiste hasta que el dev confirma la aprobación explícitamente; no se auto-elimina por paso del tiempo.
3. **Excepción (complejidad alta, 7+ elementos / arquitectura / regresión alta)** — solicitar confirmación explícita antes de cerrar. No aplica el cierre diferido.
