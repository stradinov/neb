# Convenciones (requirements-analysis)

## Naming del subproyecto

- Path: `<proyecto>/reqs/<nombre-requerimiento>/`
- `<nombre-requerimiento>` en kebab-case descriptivo. Ej: `user-auth`, `payment-integration`, `export-to-csv`.

## Nombre del documento de Clarificación

- Siempre `clarificacion.md` (singular, minúsculas). No `requerimiento.md`, no `analisis.md`.
- La plantilla canónica está en [clarification-template.md](clarification-template.md).

## Tags de iteración

| Tag | Uso |
|---|---|
| `[S-N]` | Supuesto (S-1, S-2, …). Incremental por documento; nunca reusar un número. |
| `[Q-N]` | Pregunta pendiente al stakeholder (Q-1, Q-2, …). Al cerrarse: tachar o convertir en supuesto confirmado. |
| `[CU-N]` | Caso de uso (CU-01, CU-02, …). Referenciado desde criterios de aceptación. |
| `[CA-N]` | Criterio de aceptación (CA-01, CA-02, …). |
| `[R-N]` | Riesgo (R-01, R-02, …). |
| `[crítico]` | Prefijo para CU con impacto en autenticación, pagos, datos sensibles o integraciones externas. |

Invariante: todo supuesto no confirmado es `[S-N]`; toda laguna de información es `[Q-N]`. **Nunca ocultar incógnitas en el documento.**

## Estado del documento (frontmatter)

El campo `estado` sigue este ENUM:

```
Draft → En revisión stakeholder v1 → En revisión stakeholder v2 → ... → Aprobado
```

No inventar variantes. El estado cambia en el commit que lo entrega o aprueba.

## Bitácora de iteraciones

La sección "Bitácora de iteraciones" del documento es **append-only**: nunca editar entradas anteriores.
Cada entrega tiene su entrada con fecha y resumen de cambios. El feedback del stakeholder se transcribe textual o resumido fielmente.

## Sub-requerimientos del análisis

Si durante el análisis surge trabajo adicional (ej. rehacer estimación tras cambio de alcance), se documenta como sub-req en `reqs/<nombre>/changes/<YYYY-MM-DD>-<actividad>.md` usando la plantilla estándar del proyecto. No mezclar con `<proyecto>/changes/` (que es para implementación).
