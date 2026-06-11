# Políticas generales

Baseline del equipo. Aplican a cualquier proyecto y profile. Un override personal puede estrecharlas o agregar, no relajarlas (ver [methodology/personal-vs-team.md](../methodology/personal-vs-team.md)).

Este archivo es el **índice/mapa** de la metodología: orden de lectura y flujo. Cada política vive en su propio archivo, que se carga según el disparador indicado abajo.

## Orden de lectura

Transversales **inyectadas al arranque** (vía [`startup.md`](startup.md), garantizadas en toda sesión):

- [Communication](communication.md) — tono, idioma, hilo de la metodología.
- [Models](models.md) — selección de modelo según contexto.
- [Profile detection](profile-detection.md) — detección del profile al iniciar y profile activo durante la sesión.
- [Phase transitions](../process/phase-transitions.md) — enrutamiento del workflow: trigger de formalización, anti-desviación, mapa de fases, gates de cola, conflictos normativos.
- [Onboarding](onboarding.md) — oferta del tour `/wakeup`.
- [Workflow index](../workflow/index.md) — mapa de artefactos + ENUM de estados.

Transversales **on-demand** (su cláusula base viaja espejada en el arranque; el detalle se carga al disparador):

- [Agents](agents.md) — al despachar subagentes (tipos y mapeo a fases).
- [Incidents](incidents.md) — al detectar una incidencia post-entrega a producción.
- [Change control gate](../process/change-control-gate.md) — al confirmar cambios (Fase 4); núcleo espejado en phase-transitions § "Gates de cola"; ownership de `.md` y punto de restauración en [methodology/change-control-policy.md](../methodology/change-control-policy.md).

Fases (secuenciales por requerimiento):

1. [Planning](../process/planning.md) — clarificación, estimación, plan, plan de pruebas, propuesta. *(Fases 1–3)*
2. [Execution](../process/execution.md) — implementación, plan mode, tareas, incidencias. *(Fase 4)*
3. [Delivery](../process/delivery.md) — validación, entrega, cierre. *(Fases 5–7)*
4. [Documentation](../process/documentation.md) — qué documentar al cerrar. *(Fase 8)*
5. [Improvement](../process/improvement.md) — retroalimentación de metodología. *(Fase 9)*

Referencia (on-demand):

- [Vocabulary](../methodology/vocabulary.md) — vocabulario abstracto de la metodología; se consulta al concretizar el glosario de un profile o al usar un término del flujo.

## Capas del repo

- [`general/`](index.md) — política operativa transversal (este archivo y sus hermanos).
- [`methodology/`](../methodology/index.md) — criterio, vocabulario y catálogo (principles, roles-catalog, change-control-policy…).
- [`process/`](../process/index.md) — fases, gates y mecanismos de control (planning → improvement, plan-review, version-control…).
- [`workflow/`](../workflow/index.md) — artefactos (changes, pendings, approved-plans, metrics, traceability).
- [`tooling/`](../tooling/index.md) — hooks y recursos opt-in personales.
- [`docs/`](../docs/how-it-works.md) — documentación de cara al adoptante (explicación + guías how-to); **fuera de las capas del flujo** (ver [`../methodology/principles.md`](../methodology/principles.md) § "Capas del repo y test de pertenencia").

## Flujo

```
Clarificación → Estimación → Propuesta → Implementación → Validación → Control de cambios → Producción → Documentación → Retroalimentación
```

**Arranque garantizado**: reglas always-on cargadas vía [`startup.md`](startup.md) (`@import` determinista). Los archivos de fase se leen al entrar en la fase.
