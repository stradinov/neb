# Improvement

Última fase de cada requerimiento.

## Retroalimentación

Al cerrar, Claude se hace estas preguntas:

- ¿Alguna fase generó fricción o fue innecesaria?
- ¿Hubo retrabajo que una regla podría haber evitado?
- ¿Se descubrió un patrón, convención o restricción del proyecto que debería quedar documentado?
- ¿Hubo errores de implementación o faltas de contexto durante el REQ? (ver definiciones en [`workflow/metrics.md`](../workflow/metrics.md) "Definiciones operativas")
- ¿Hubo un defecto que ningún rol revisor cazó? Si sí: ¿era responsabilidad de un rol existente cuyo foco debe expandirse, o requiere un rol nuevo? (ver [`methodology/roles-catalog.md`](../methodology/roles-catalog.md) "Evolución de roles")

## Disparadores cuantitativos

Además de las preguntas reflexivas, Claude verifica las métricas del MD contra los umbrales de [`workflow/metrics.md`](../workflow/metrics.md) "Cuándo accionar". Si alguna métrica supera su umbral, propone la acción correspondiente como ajuste a la metodología.

El **Reporte de cierre** (presentado al dev en Fase 8, sección `## Reporte de cierre` del change MD) se escanea en Fase 9 como input adicional:

- Si "Complejidad estimada / real" diverge en 2+ niveles Y el costo en tokens es consistentemente mayor al esperado para esa complejidad → reforzar criterio de estimación (acción redundante con el umbral de `Complejidad real ≠ estimada`, pero el costo sirve como evidencia cuantitativa).
- Si el costo del REQ es notablemente alto para su complejidad real → anotar como hipótesis en el registro de aprendizaje del dev. No deriva acción de metodología por sí solo.

Si la desviación tiene causa documentada (ej. complejidad real más alta por incidencia anotada en el MD), la acción puede saltarse — pero con justificación inline.

**Actualizar utilidad de roles invocados**: tras el plan-review, aplicar Δ score a cada rol según el evento que aplique de [`methodology/roles-catalog.md`](../methodology/roles-catalog.md) "Utilidad de roles" — +1 si cazó defecto, -0.1 si no aportó hallazgos, -1 si debió cazar y no lo hizo (descubierto post-cierre). El Δ se anota en el change MD bajo **Utilidad de roles** y, si el profile en que se invocó el rol tiene tabla de utilidad propia en el overlay del adoptante con fila de ese rol, también ahí, con la fecha. La tabla "Resumen de utilidad" del núcleo no recibe el Δ de cada REQ.

## Diagnóstico de origen del defecto

El **Process Improvement Analyst** diagnostica el origen del defecto cuando se detecta (vía métrica, patch retrospectivo o reporte de uso post-cierre). El output va en la sección "Diagnóstico de defectos" del change MD, según el formato de la tabla siguiente.

### Tabla de orígenes y mejoras derivadas

| Origen | Etapa | Ejemplo de defecto | Mejora derivada típica |
|---|---|---|---|
| **Plan defectuoso** | Fase 3 | Plan no enumeró dependientes críticos; alcance vago; dimensión faltante; criterios ambiguos | Ajuste a Process Architect / criterios de [`planning.md`](planning.md) / template |
| **Ejecución defectuosa** | Fase 4 | Claude se desvió del plan claro; introdujo regresión; violación de convención | Ajuste a lineamiento aplicado o sub-foco del rol revisor que debió cazar |
| **Validación insuficiente** | Fase 5 | Plan de pruebas no cubrió flujo crítico que falló post-deploy | Ajuste a riesgo de regresión / matriz de Resultado del template |
| **Comportamiento inesperado post-entrega** | Fase 7 | Comportamiento en uso real no previsto en validación; paridad de ambientes incompleta o criterios de aceptación vagos | Ajuste a paridad / criterios de validación |
| **Documentación faltante** | Fase 8 | Cambio no reflejado en CLAUDE.md / memoria del proyecto / metodología | Ajuste a [`documentation.md`](documentation.md) / memoria |
| **Loop tardío** | Fase 9 | Patrón persistente no detectado por revisión agregada o disparadores | Ajuste a este archivo / disparadores cuantitativos |
| **Transversal** | — | Faltas de contexto recurrentes; ambigüedad en múltiples fases; defecto sin etapa clara | Revisión agregada extraordinaria |

### Atribución de intersecciones

Si el defecto cruza dos etapas (ej. plan vago + ejecución que tomó la dirección incorrecta), atribuir al **primer eslabón causal** — el plan vago. La ejecución es síntoma, no causa raíz.

Si el defecto se detecta tiempo después, en uso post-cierre: la **etapa de origen es donde se introdujo**, no donde se detectó. Ej: plan vago en REQ-X cerrado hace 2 meses → origen Fase 3 de REQ-X.

### Recurrencia por familia (≥3 similares)

Cuando el campo **Patrón / aislado** del Diagnóstico se marca **≥3 similares** (el defecto es el 3.º o posterior de una misma clase / causa raíz), el REQ derivado NO se limita a un parche puntual del caso: **dispara una revisión-de-familia obligatoria** — consolidar el **invariante común** de la clase y un **checklist de regresión reutilizable** que gatee las próximas ocurrencias. Esto es **independiente del umbral `N = 10` de la revisión agregada** (§ "Revisión agregada"): basta con marcar ≥3 similares en un solo Diagnóstico. Rompe el patrón "cada bug de la familia se parcha en aislamiento sin abstraer nunca la clase".

### Salida

REQ derivado de mejora con plan-review formal. CHANGELOG entry del REQ derivado cita explícitamente: *"tras diagnóstico del defecto X (origen Fase Y, tipo Z) en REQ W"*.

El diagnóstico vive en el change MD del REQ que detectó el defecto, sub-sección "Diagnóstico de defectos" (ver [`templates/change.md.template`](../templates/change.md.template)).

## Revisión agregada

Complementa la retroalimentación per-requerimiento con análisis cross-changes para detectar **patrones recurrentes** que no aparecen revisando un solo MD.

### Disparador

El primero que ocurra:

- **N = 10 changes cerrados** desde la última revisión agregada.
- **Cierre de mes calendario**.

Claude lo propone proactivamente al cumplirse la condición; el dev también puede pedirlo en cualquier momento.

### Qué se revisa

- Métricas agregadas de los últimos N changes contra umbrales de [`workflow/metrics.md`](../workflow/metrics.md): ¿hay una métrica que se dispara repetidamente (ej. 5 de 10 cierran con re-deployments=3), o una que no disparó en el período y ya no aporta?
- Patrones cualitativos de fricción recurrente: incidencias del mismo tipo, fases que consistentemente exceden turnos, decisiones que se reabren.
- **Análisis longitudinal de costo por modelo** (si hay datos de uso de API en los change MDs): comparar cost-per-REQ a complejidad constante entre versiones de Claude. Dos señales posibles:
  - Costo baja manteniendo calidad → Claude mejoró o la metodología es más eficiente.
  - Costo sube o se mantiene con calidad baja → investigar si el tipo de REQ cambió o si hay uso ineficiente del modelo (ej. Opus para tareas que Sonnet resolvería igual).
  Registrar el análisis aunque no derive propuesta — es evidencia longitudinal.

### Output

1–3 propuestas de mejora a la metodología, formato Fase 9 individual. Si no hay patrón claro, lo informa en una línea ("revisión agregada de N changes desde X — sin patrón persistente").

Cada propuesta derivada entra como REQ aparte con plan-review (ver [`process/plan-review.md`](plan-review.md)).

### Verificación de utilidad de roles

El score de un rol vive en una tabla de utilidad: "Resumen de utilidad" de [`methodology/roles-catalog.md`](../methodology/roles-catalog.md), o la tabla propia de un profile en el overlay del adoptante, que ya recibe el Δ de los roles con fila en ella invocados bajo ese profile. Para una fila del núcleo, la revisión agregada suma al score de la fila los Δ de utilidad de roles anotados en los change MDs de los REQs cerrados desde su **Última act.**, salvo los que ya recibió una tabla propia, y asienta el resultado con su fecha (un adoptante que no mantiene el núcleo lo asienta en una tabla propia de su overlay). Sobre esos scores:

1. Aplica Δ −0.5 a roles no invocados en 5 plan-reviews consecutivos donde habrían aplicado.
2. Identifica roles con score `< -1` sostenido por **2 evaluaciones consecutivas** y propone: *"El rol `<X>` no aporta hallazgos sostenidos. ¿Se depreca, se ajusta su foco o se redefine su pertinencia?"*
3. Roles con score `≥ +3` se marcan core — no se deprecan ni se reformulan sin justificación fuerte.

### Trazabilidad

El CHANGELOG entry del REQ derivado menciona explícitamente "tras revisión agregada de N changes desde <fecha>". Sin sección dedicada en el repo: el origen vive en la confirmación del cambio del REQ (en git: el commit).

Si Claude identifica un ajuste:

1. Lo propone en una línea: *"Mejora sugerida a la metodología: [cambio concreto]. ¿Se aplica?"*
2. Con confirmación, edita el archivo correspondiente del repo `methodology`.
3. Confirma y entrega el cambio según el mecanismo del profile (en `self-applied`/git, commit + push):
   ```
   docs: actualizar metodología — <descripción breve>
   ```

Si no hay nada que ajustar, lo indica en una línea.

Versionado SemVer y entrada en `CHANGELOG.md`: ver [CLAUDE.md](../CLAUDE.md) del repo.
