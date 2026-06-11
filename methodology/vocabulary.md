# Vocabulario abstracto

La metodología usa vocabulario neutro para cubrir entregables de distinta naturaleza (código, documento, proceso). Cada profile concretiza los términos en su `profiles/<profile>/index.md` sección "Glosario del profile".

| Término abstracto | Significado | Ejemplos por tipo de profile |
|---|---|---|
| Entregable / elaboración | Lo que produce el requerimiento | Código (profile de software) · Documento (profile de análisis) · Lineamiento (self-applied) |
| Elaboración asistida | Humano-en-loop durante la elaboración | Un autor redacta con el dev iterando |
| Elaboración autónoma | Claude conduce la elaboración en un único turno (prompt → planeación → output) sin humano en el loop | Borrador auto-generado en un turno |
| Confirmación del cambio | Hacer permanente y recuperable un cambio del entregable | `git commit` (software, self-applied) · commit del documento versionado (análisis) |
| Punto de restauración | Estado previo recuperable que habilita rollback antes de la entrega final | commit local previo (software) · backup de datos (datos) · versión previa del documento (análisis) |
| Entrega | Acción de poner el entregable a disposición del receptor | deploy a servidor vía SSH/SCP (software) · commit versionado + notificación (análisis) · `git push` (self-applied) |
| Entrega para revisión | Primera entrega a un receptor no-final para validación | Deploy a QA (software) · Documento al receptor v1 (análisis) |
| Entrega final / aprobación final | Entrega que cierra el ciclo del requerimiento | Deploy a producción (software) · Aprobación firmada del documento (análisis) |
| Ambiente de revisión | Entorno o canal donde el receptor valida el entregable | QA (software) · Sesión de revisión (análisis) |
| Estado aprobado | El entregable fue aceptado por el receptor final | Producción (software) · Documento aprobado (análisis) |
| Dependientes | Referencias al dato, función o concepto afectado (escritura y lectura/display) | Callers de un método (software) · Secciones que citan un supuesto (análisis) |
| Flujos críticos | Flujos con riesgo de regresión medio/alto que se deben re-validar | Tests de auth/pagos (software) · Casos de uso `[crítico]` del documento (análisis) |

## Estados del requerimiento

ENUM canónico. Cualquier archivo que registre estado usa este vocabulario. El mapa de artefactos por estado y las transiciones especiales (qué fases se saltan) viven en [`../workflow/index.md`](../workflow/index.md) y [`../process/delivery.md`](../process/delivery.md) respectivamente.

| Estado | Significado | Fase |
|---|---|---|
| `En progreso` | Plan aprobado, implementación en curso | 4 |
| `En validación` | Implementación lista, esperando validación (con QA, local con artefactos, o implícita) | 5 |
| `Listo para aprobación` | Validación pasada, esperando entrega final / aprobación del receptor | 6–7 |
| `Cerrado` | Entrega final confirmada por el dev (o aprobación del receptor) | post 8/9 |

**Bloqueado** se anota como sufijo del estado activo: `En progreso (bloqueado por X)`. No es estado paralelo — no inventa transiciones nuevas.

- El draft del change MD existe desde `Plan aprobado` (ver [`../workflow/changes.md`](../workflow/changes.md)); por convención arranca en `En progreso`. No hay estado "Propuesto".
- Los changes históricos pueden contener vocabulario previo (`Propuesto`, `COMPLETADO`, `Listo para producción`); no se migran. `Listo para producción` es el término anterior de `Listo para aprobación` (renombrado en una versión anterior).

## Tipos de validación

Clasificación según la naturaleza del entregable. Los pasos de ejecución de Fase 5 viven en [`../process/delivery.md`](../process/delivery.md) § Validación.

- **Con ambiente de revisión** (e-commerce, etc.): el usuario valida el flujo principal en el ambiente de revisión antes de la entrega final.
- **Con ciclo de revisión cliente** (profiles de análisis): el cliente valida el entregable iterativamente; cada vuelta produce una nueva versión hasta la aprobación final.
- **Sin ambiente pero con artefactos** (scripts, migraciones, CLI): validación directa — ejecución local, dry-run, o revisión.
- **Sin artefactos** (docs sin proceso, comentarios, typos): validación implícita — el usuario revisa en contexto y confirma.
- **Diferida en uso** (profile `self-applied`): los walkthroughs mentales aterrizan el diseño, pero el cierre formal requiere uso real (criterio: ≥ 10 sesiones sin reporte negativo — ver [`../profiles/self-applied/deployment.md`](../profiles/self-applied/deployment.md)).

## Niveles de riesgo de regresión

Eje ortogonal a la complejidad. 1 elemento cambiado con muchos dependientes = complejidad baja + riesgo alto. La regla que ata el riesgo al plan de pruebas (`medio`/`alto` exige fila `[crítico]`) vive en [`../process/planning.md`](../process/planning.md) § "Riesgo de regresión".

| Nivel | Criterio | Ejemplos |
|-------|----------|----------|
| Bajo  | Cambios aislados sin dependientes, docs/comentarios/typos, lógica sin condicionales sensibles | Typo en MD, log nuevo, comentario, formato |
| Medio | Lógica con dependientes acotados conocidos, configs no críticos, cambios localizados con uso identificable | Nuevo método con 2-3 dependientes, config de feature flag, cambio en helper |
| Alto  | Muchos dependientes, contratos públicos, flujos críticos (auth, pagos, datos), refactor transversal | Cambio en hash de password, modificar query SQL central, cambio de schema, rename de método público |
