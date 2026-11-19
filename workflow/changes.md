# Changes (registros de requerimientos por proyecto)

Cada proyecto mantiene `changes/` (versionado cuando el proyecto usa control de versiones): la carpeta guarda los registros de sus requerimientos (un Change MD por REQ). Trazabilidad histórica de los requerimientos a través de sus registros.

El modelo completo de trazabilidad (plan → Change MD → commits, y el caso cross-repo) vive en [traceability.md](traceability.md); este archivo cubre el ciclo de vida del Change MD como registro del REQ.

## Path

```
<proyecto>/changes/<YYYY-MM-DD>-<nombre>.md
```

- Una carpeta `changes/` por proyecto, en la raíz: contiene los registros de sus requerimientos.
- Un MD por requerimiento (cardinalidad 1↔1: cada REQ se registra en un único Change MD; incluso cross-repo, un solo MD en el repo central — ver [traceability.md](traceability.md)).
- Prefijo `YYYY-MM-DD` para orden cronológico sin renombrados.
- `<nombre>` en kebab-case descriptivo, con forma `[a-z0-9-]+` (los nombres anteriores con otros caracteres quedan como están). Es el **identificador único del REQ**: lo llevan el trailer de sus commits ([`../process/version-control.md`](../process/version-control.md) § "Trailer `Req:` — del commit al REQ"), el archivo de su plan aprobado ([approved-plans.md](approved-plans.md)) y el campo `Nombre` de su `active_*.md` ([memory.md](memory.md)).
- El `<nombre>` es único dentro del `changes/` del proyecto: antes de crear el registro, Claude lista `changes/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-<nombre>.md` y, si existe, elige otro nombre. En un REQ cross-repo corre el mismo patrón en el `changes/` de cada repo que el REQ tocará.
- Se confirma con el entregable (en git: commit al repo).

## Contenido

Estructura: ver [`templates/change.md.template`](../templates/change.md.template).

## Ciclo de vida del draft

El MD se crea como draft al aprobar el plan y se completa durante la implementación.

| Momento | Acción |
|---|---|
| Plan aprobado | Crear `changes/YYYY-MM-DD-<nombre>.md` con estado `En progreso`, contexto, alcance y plan resumido. En media/alta, guardar además el plan aprobado en `changes/plans/` y confirmarlo antes de la primera confirmación del entregable ([approved-plans.md](approved-plans.md) § "Ciclo de vida"). Desde aquí el registro es **entregable de forma temprana y autónoma** (ver abajo) |
| Fase mayor completada | Actualizar archivos modificados e incidencias |
| Relevo | Escribir `## Relevo` y entregar de inmediato el registro y su plan aprobado (§ "Relevo") |
| Cierre | Completar métricas y marcar `Cerrado` (ver [`workflow/index.md`](index.md) § "Estados del requerimiento"). Finaliza el registro **en el mismo commit que entrega el entregable**, con `**Commits:** esta confirmación` (sin hash literal: no existe al redactar, y un cierre `.md`-only posterior dispara el gate de fragment del pre-push — ver [`../process/version-control.md`](../process/version-control.md) § "CHANGELOG fragmentado"). Si el registro ya se entregó antes (entrega temprana), su cierre va en un commit `docs: ...` aparte |

**Entrega temprana del registro.** El **registro del requerimiento** (su Change MD — ver [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Registro del requerimiento") es un **artefacto que Neb genera** (y, derivadamente, `.md`), por lo que confirmarlo y entregarlo es **autónomo** desde su creación (Fase 4) bajo el ownership — no requiere OK del dev cuando el delta es solo `.md` (ver [`change-control-policy.md`](../methodology/change-control-policy.md) § "Ownership de archivos `.md`" y [`version-control.md`](../process/version-control.md) § "Push"). Cuándo se entrega:

- **Entorno de validación compartido** (disparador: [`logbook.md`](logbook.md) § "Entorno compartido (disparador opt-in por proyecto)") → entrega temprana: el registro se confirma y se publica **desacoplado** de la entrega del entregable. El `work` va a la bitácora compartida, y publicarlo para relevo cross-dev exige que su registro esté **entregado** para que el puntero resuelva en la máquina que releva.
- **Entorno no compartido** (sesión solo del dev, sin bitácora compartida) → el registro se confirma y se entrega al cierre.
- **Al relevar**, en cualquiera de los dos entornos → el registro y su plan aprobado se confirman y se entregan de inmediato (§ "Relevo"). Donde el push es por sí mismo una entrega del profile, ese push sigue el gate de esa entrega.

Esto cubre solo el **registro**: el entregable (los `.md` de la metodología misma) mantiene su propio gate de validación/cierre.

### Plan resumido vs plan literal

En complejidad **baja** no hay plan aprobado: el "plan resumido" del draft vive en [`templates/change.md.template`](../templates/change.md.template) § "Plan de elaboración" (tabla `Elemento | Cambio`). En **media/alta** el plan literal vive en el mismo repo (`changes/plans/`, ver [approved-plans.md](approved-plans.md)): `## Plan de elaboración` enlaza a ese archivo y lista solo los desvíos, sin repetirlo. Claude llena el campo `**Plan aprobado:**` de la sección Trazabilidad con la ruta desde la raíz del repo, en formato código (`changes/plans/<YYYY-MM-DD>-<nombre>.md`). Direccionalidad completa: [traceability.md](traceability.md).

El plan de pruebas sigue la misma regla: en media/alta se define en `## Plan de pruebas` del plan aprobado y el Change MD conserva solo `### Resultado` ([`../process/planning.md`](../process/planning.md) § "Estimación, plan y plan de pruebas").

El draft lo actualiza Claude en cada fase mayor completada (tabla de arriba); ningún hook lo reescribe. Lo que la compactación debe conservar del REQ, y de dónde se recupera el detalle después, lo fija [`../general/compaction.md`](../general/compaction.md).

## Relevo

Al pausar para que otro dev u otra máquina continúe, Claude escribe en `## Relevo` del Change MD:

- los próximos pasos;
- el «Trabajo en vuelo»: cómo relanzar lo que quedó a medias (agentes, scripts);
- la línea «relevado por <dev>, <fecha>». Quién tiene el mando lo decide `tomar` ([logbook.md](logbook.md) § "Modelo de ownership").

Después confirma y entrega de inmediato el registro y su plan aprobado, sea cual sea el entorno (§ "Ciclo de vida del draft").

`## Relevo` es el único lugar de esos datos al relevar, y no se llena en cada sesión. Para continuar en la misma máquina siguen sirviendo el `active_*.md` y sus «Próximos pasos» ([memory.md](memory.md)). Quien releva lee el registro, su `## Relevo` y su plan aprobado: [`../process/execution.md`](../process/execution.md) § "Relevo cross-dev (bitácora de relevo)".

## Incident MD

Variante del Change MD para incidentes detectados post-entrega final: registro reactivo del REQ correctivo, con su propia cardinalidad 1↔1. Comparte carpeta y naturaleza (artefacto versionado en `changes/`). El protocolo reactivo (severidad P1/P2, respuesta, postmortem) vive en [`../general/incidents.md`](../general/incidents.md); aquí el ciclo de vida del artefacto.

- **Path**: `<proyecto>/changes/<YYYY-MM-DD>-incident-<slug>.md`, desde [`templates/incident.md.template`](../templates/incident.md.template).
- **Apertura**: el dev lo crea y lo notifica explícitamente a Claude.
- **Cierre**: marcar `Estado: Cerrado` cuando (1) la mitigación está verificada en producción y (2) hubo 7 días sin recurrencia del síntoma; confirmar el cambio según el mecanismo del profile.
- **Cross-link al requerimiento que lo originó**: si el incidente es atribuible a un deploy identificable, anotar en el INCIDENT MD `**Originado por:** changes/<fecha>-<req>.md (confirmación <ref>)` y la referencia inversa en el Change MD original ([`templates/change.md.template`](../templates/change.md.template) § "Resultado post-entrega"). Alimenta la métrica de re-entregas y los análisis de Fase 9. Modelo completo: [traceability.md](traceability.md).

