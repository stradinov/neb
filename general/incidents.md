# Incidencias en producción

Política transversal para incidentes detectados **post-entrega final**. Para cambios menores que surgen durante el trabajo (pre-entrega final), ver [`../process/execution.md`](../process/execution.md) sección "Incidencias durante el trabajo".

## Detección

Quién: cliente, monitoring, dev, Claude post-deploy. El artefacto que se abre (INCIDENT MD: path, apertura desde template, cierre, cross-link al deploy originador) vive en [`../workflow/changes.md`](../workflow/changes.md) § "Incident MD".

## Severidad

| Nivel | Criterio | Respuesta |
|---|---|---|
| **P1** | Sistema inaccesible, operaciones críticas imposibles, autenticación rota, datos corruptos, fuga de información | Rollback inmediato |
| **P2** | Feature crítica con workaround, errores intermitentes, performance significativamente degradada | Fix forward 24-72h, dev decide rollback |

Ambigüedad entre niveles → tratar como P1. Bugs visuales o edge cases bajo tráfico no son incidente — entran al backlog normal sin INCIDENT MD.

## Respuesta

### P1 — Rollback inmediato

Pre-condición: el punto de restauración previo a la entrega final debe existir (regla en [`../process/delivery.md`](../process/delivery.md) § "Pre-condiciones de entrega final" y [`../methodology/change-control-policy.md`](../methodology/change-control-policy.md) § "Punto de restauración").

Pasos específicos por stack: `stacks/<stack>/deployment.md` sección "Rollback".

### P2 — Fix forward

1. Reproducir el bug en QA si es posible.
2. Si reproducible en QA: fix con flujo normal (clarificación → propuesta → implementación → validación) con scope acotado al bug.
3. Si no reproducible: documentar contexto en el INCIDENT MD y discutir con el dev si rollback o fix con monitoreo.

## Postmortem

Obligatorio P1, opcional P2. Vive en el INCIDENT MD (causa raíz, mitigación, prevención).

Si el postmortem identifica una mejora a la metodología, ingresa a Fase 9 (Retroalimentación de Metodología) — no se crea canal nuevo. Ver [`../process/improvement.md`](../process/improvement.md).

## Cierre

El criterio de cierre del INCIDENT (mitigación verificada + 7 días sin recurrencia) y el cross-link al deploy originador viven con el ciclo de vida del artefacto en [`../workflow/changes.md`](../workflow/changes.md) § "Incident MD".
