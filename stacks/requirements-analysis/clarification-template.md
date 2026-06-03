# Plantilla — Documento de Clarificación

Plantilla canónica del documento que vive en `<proyecto>/reqs/<nombre>/clarificacion.md`.

---

```yaml
---
proyecto: <nombre del proyecto>
slug: <slug-requerimiento>          # kebab-case descriptivo
estado: Draft                       # Draft | En revisión stakeholder vN | Aprobado
modo_origen: asistido               # asistido | autonomo
version: v1
fecha_inicio: YYYY-MM-DD
complejidad_estimada: media         # baja | media | alta
esfuerzo_estimado: <rango>
---
```

---

# <Título descriptivo del requerimiento>

**Estado:** Draft | En revisión stakeholder vN | Aprobado
**Versión:** vN
**Fecha inicio:** YYYY-MM-DD
**Fecha aprobación:** —
**Complejidad estimada:** baja | media | alta
**Esfuerzo estimado:** <rango>
**BA responsable:** <nombre>

---

## 1. Contexto del proyecto

<!-- Qué hace el proyecto, qué capacidades ya existen, qué problema motiva el requerimiento. -->

...

## 2. Objetivo del requerimiento

<!-- Una sola frase, accionable. Ej: "Agregar autenticación con proveedor externo al sistema de usuarios." -->

...

## 3. Alcance

### Entra

- ...

### No entra

<!-- Al menos 1 ítem. Límite explícito para prevenir scope-creep. -->

- ...

## 4. Stakeholders

| Rol | Nombre / equipo | Responsabilidad |
|---|---|---|
| Decisor / aprobador | | Aprobación final |
| Business Analyst | | Análisis, redacción, estimación |
| Domain Expert | | Validación técnica de estimación |
| Otros involucrados | | |

## 5. Casos de uso

<!-- Cada caso de uso debe tener ≥1 criterio de aceptación en la Sección 8. -->

| # | Actor | Flujo | Pre-condición | Resultado esperado | Complejidad | Notas |
|---|---|---|---|---|---|---|
| CU-01 | | | | | baja / media / alta | |
| CU-02 `[crítico]` | | | | | | Impacta auth / pagos / datos sensibles |

## 6. Supuestos

<!-- Todo supuesto no confirmado lleva tag [S-N]. No usar supuestos para completar gaps críticos sin validación. -->

- `[S-1]` ...
- `[S-2]` ...

## 7. Dependencias técnicas

<!-- Cada dependencia lista artefactos o sistemas afectados. Adaptar las subsecciones al dominio del proyecto. -->

### Esquema / datos

| Entidad | Tipo de cambio | Detalle |
|---|---|---|
| | | |

### Integraciones externas

| Sistema | Tipo de interacción | Observaciones |
|---|---|---|
| | | |

### Componentes / módulos afectados

- ...

## 8. Criterios de aceptación

<!-- Uno por caso de uso o capacidad. Verificables por el stakeholder. -->

| # | Caso de uso / capacidad | Criterio | Verificable por |
|---|---|---|---|
| CA-01 | CU-01 | | Stakeholder / dev |
| CA-02 | CU-02 | | |

## 9. Estimación con desglose

<!-- Adaptar la tabla de artefactos al tipo de proyecto (backend, frontend, infra, etc.). -->

| Componente / tarea | Descripción | Esfuerzo estimado |
|---|---|---|
| | | |
| **Total estimado** | | |

**Complejidad**: baja | media | alta — criterio: <justificación>

## 10. Riesgos

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| R-01 | | bajo / medio / alto | bajo / medio / alto | |

## 11. Alternativas evaluadas

<!-- Opción elegida + 1-2 descartadas con razón. Omitir si no hubo evaluación de alternativas. -->

**Opción elegida**: ...
**Razón**: ...

**Alternativa descartada**: ...
**Razón del descarte**: ...

## 12. Preguntas pendientes

<!-- Abiertas al stakeholder. Se cierran o convierten en supuestos durante iteraciones. -->

- `[Q-1]` ...
- `[Q-2]` ...

## 13. Bitácora de iteraciones

<!-- Append-only. Una entrada por entrega + feedback recibido. -->

### v1 — YYYY-MM-DD — Borrador inicial

Cambios: primer draft completo.
Supuestos pendientes: [S-1], [S-2]. Preguntas abiertas: [Q-1].

### v1 — YYYY-MM-DD — Feedback stakeholder recibido

Comentarios del stakeholder: ...
Ajustes a aplicar: ...

### v2 — YYYY-MM-DD — Entregado

Cambios respecto a v1: ...

---
<!-- Repetir patrón por cada iteración -->

## 14. Aprobación

<!-- Completar solo al cierre. -->

**Firmante:** —
**Fecha de aprobación:** —
**Medio de confirmación:** (correo / documento firmado / tícket cerrado)
**Commit aprobado:** `clar-approved` —
