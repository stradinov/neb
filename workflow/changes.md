# Changes (registros de requerimientos por proyecto)

Cada proyecto mantiene `changes/` (versionado cuando el proyecto usa control de versiones): la carpeta guarda los registros de sus requerimientos (un change MD por REQ). Trazabilidad histórica de los requerimientos a través de sus registros.

El modelo completo de trazabilidad (plan → change MD → commits, y el caso cross-repo) vive en [traceability.md](traceability.md); este archivo cubre el ciclo de vida del change MD como registro del REQ.

## Path

```
<proyecto>/changes/<YYYY-MM-DD>-<nombre>.md
```

- Una carpeta `changes/` por proyecto, en la raíz: contiene los registros de sus requerimientos.
- Un MD por requerimiento (cardinalidad 1↔1: cada REQ se registra en un único change MD; incluso cross-repo, un solo MD en el repo central — ver [traceability.md](traceability.md)).
- Prefijo `YYYY-MM-DD` para orden cronológico sin renombrados.
- `<nombre>` en kebab-case descriptivo.
- Se confirma con el entregable (en git: commit al repo).

## Contenido

Estructura: ver [`templates/change.md.template`](../templates/change.md.template).

## Ciclo de vida del draft

El MD se crea como draft al aprobar el plan y se completa durante la implementación.

| Momento | Acción |
|---|---|
| Plan aprobado | Crear `changes/YYYY-MM-DD-<req>.md` con estado `En progreso`, contexto, alcance y plan resumido |
| Fase mayor completada | Actualizar archivos modificados e incidencias |
| Cierre | Completar métricas, marcar `Cerrado` (ver [`workflow/index.md`](index.md) "Estados del requerimiento"), confirmar el cambio (en git: commit `docs: change.md ...`) |

El draft **no se confirma** hasta el cierre (en git: no se commitea).

### Plan resumido vs plan literal

El "plan resumido" del draft vive en § "Plan de elaboración" (tabla `Elemento | Cambio`) — es un **resumen**, no el plan literal. En complejidad media/alta el plan literal se persiste aparte en `~/.claude/approved-plans/` (ver [approved-plans.md](approved-plans.md)). Cuando la aprobación fue **conversacional** (sin plan mode), Claude llena el campo `**Plan aprobado:**` de la sección Trazabilidad con el path de ese archivo; en plan mode el path lo deja el hook. Direccionalidad completa: [traceability.md](traceability.md).

Con `autoCompactEnabled: true`, un hook PreCompact actualiza el draft antes de cada compactación usando la sección `## Requerimiento activo` de la memoria (ver [memory.md](memory.md) y [hooks/README.md](../hooks/README.md)).

## Incident MD

Variante del change MD para incidentes detectados post-entrega final: registro reactivo del REQ correctivo, con su propia cardinalidad 1↔1. Comparte carpeta y naturaleza (artefacto versionado en `changes/`). El protocolo reactivo (severidad P1/P2, respuesta, postmortem) vive en [`../general/incidents.md`](../general/incidents.md); aquí el ciclo de vida del artefacto.

- **Path**: `<proyecto>/changes/<YYYY-MM-DD>-incident-<slug>.md`, desde [`templates/incident.md.template`](../templates/incident.md.template).
- **Apertura**: el dev lo crea y lo notifica explícitamente a Claude.
- **Cierre**: marcar `Estado: Cerrado` cuando (1) la mitigación está verificada en producción y (2) hubo 7 días sin recurrencia del síntoma; confirmar el cambio según el mecanismo del profile.
- **Cross-link al requerimiento que lo originó**: si el incidente es atribuible a un deploy identificable, anotar en el INCIDENT MD `**Originado por:** changes/<fecha>-<req>.md (confirmación <ref>)` y la referencia inversa en el change MD original (§ "Resultado post-entrega"). Alimenta la métrica de re-entregas y los análisis de Fase 9. Modelo completo: [traceability.md](traceability.md).

