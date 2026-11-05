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

Si la desviación tiene causa documentada (ej. complejidad real más alta por incidencia anotada en el MD), la acción puede saltarse — pero con justificación inline. La de Re-entregas no se salta: ya parte de la causa ([`workflow/metrics.md`](../workflow/metrics.md) § "Cuándo accionar").

**Aporte de los roles despachados**: en Fase 9, Claude anota en el registro del REQ, bajo **Aporte de roles**, una línea por rol revisor despachado en el REQ, con una etiqueta: *aportó* (cazó un defecto o dio un hallazgo que cambió el plan o el entregable), *sin hallazgos* o *debió cazar* (un defecto de su foco, descubierto después del cierre del REQ que lo introdujo, con ese REQ). La línea *debió cazar* va en el REQ que descubre el defecto, aunque el rol no se haya despachado en él. La revisión agregada lee estas líneas (§ "Revisión agregada" › "Qué se revisa").

En la misma Fase 9, Claude chequea el disparador de la revisión agregada (§ "Revisión agregada" › "Disparador").

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

Cuando el campo **Patrón / aislado** del Diagnóstico se marca **≥3 similares** (el defecto es el 3.º o posterior de una misma clase / causa raíz), el REQ derivado NO se limita a un parche puntual del caso: **dispara una revisión-de-familia obligatoria** — consolidar el **invariante común** de la clase y un **checklist de regresión reutilizable** que gatee las próximas ocurrencias. Esto es **independiente del disparador de la revisión agregada** (§ "Revisión agregada"): basta con marcar ≥3 similares en un solo Diagnóstico. El campo admite solo `aislado` o `≥3 similares`, con el detalle tras el valor ([`templates/change.md.template`](../templates/change.md.template)); otro valor no dispara la revisión de familia. Rompe el patrón "cada bug de la familia se parcha en aislamiento sin abstraer nunca la clase".

### Salida

REQ derivado de mejora con plan-review formal. CHANGELOG entry del REQ derivado cita explícitamente: *"tras diagnóstico del defecto X (origen Fase Y, tipo Z) en REQ W"*.

El diagnóstico vive en el change MD del REQ que detectó el defecto, sub-sección "Diagnóstico de defectos" (ver [`templates/change.md.template`](../templates/change.md.template)).

## Revisión agregada

Complementa la retroalimentación per-requerimiento con análisis cross-changes para detectar **patrones recurrentes** que no aparecen revisando un solo MD.

### Disparador

La revisión vence al **cambio de mes calendario**: cuando la última revisión registrada es de un mes anterior al actual. Sin revisión registrada, vence al primer cambio de mes después del primer REQ cerrado.

**Cuándo se chequea.** En la Fase 9 de cada REQ, junto a los disparadores cuantitativos. Si vence y no está abierto el pendiente `[revision-agregada-<YYYY-MM>]` del mes en curso, Claude propone abrirla como REQ. Si el dev la pospone, Claude da de alta ese pendiente; la revisión, al correr, cierra los pendientes `[revision-agregada-*]` que encuentre abiertos. El dev también puede pedirla en cualquier momento.

**Registro.** Cada revisión agregada es un REQ. Su change MD va en el `changes/` de la raíz del espacio de trabajo del adoptante (`NEB_WORKSPACE`), y lleva:

- la línea `**Revisión agregada:** <YYYY-MM-DD>`, con la fecha en que armó la lista;
- los `changes/` que abarcó y cómo contó cada REQ una vez (en git, las copias de un worktree son el mismo registro);
- la lista de los REQs que cubre: los cerrados (Estado «Cerrado») antes de ese día que ninguna revisión anterior cubrió. Los que cerraron ese día quedan para la siguiente, porque sus Fases 8 y 9 pueden estar en curso.

Lo que la revisión analiza sale de los REQs de esa lista. La última revisión registrada es la de fecha más reciente.

### Qué se revisa

- Métricas agregadas de los REQs que cubre contra umbrales de [`workflow/metrics.md`](../workflow/metrics.md): ¿hay una métrica que se dispara repetidamente (ej. 5 de 10 cierran con re-entregas=3), o una que no disparó en el período y ya no aporta?
- Patrones cualitativos de fricción recurrente: incidencias del mismo tipo, fases que consistentemente exceden turnos, decisiones que se reabren.
- Pertinencia de cada rol revisor, en cada profile donde está declarado (un rol transversal, en todos). Con las líneas «Aporte de roles» de los REQs que cubren esta revisión y la anterior: ¿un rol que no se despachó en ningún REQ de las dos, aunque su profile tuvo REQs? ¿Uno despachado solo con *sin hallazgos*? ¿Uno con *debió cazar* en más de un REQ? Si su despacho es condicional, la revisión dice si la condición se dio, o que no es determinable. Si hay un rol así, propone deprecarlo, ajustar su foco o redefinir su pertinencia (ver [`methodology/roles-catalog.md`](../methodology/roles-catalog.md) § "Evolución de roles"). Las anotaciones anteriores con Δ cuentan como etiquetas: +1 es *aportó*, −0.1 *sin hallazgos* y −1 *debió cazar*.
- **Análisis longitudinal de costo por modelo** (si hay datos de uso de API en los change MDs): comparar cost-per-REQ a complejidad constante entre versiones de Claude. Dos señales posibles:
  - Costo baja manteniendo calidad → Claude mejoró o la metodología es más eficiente.
  - Costo sube o se mantiene con calidad baja → investigar si el tipo de REQ cambió o si hay uso ineficiente del modelo (ej. Opus para tareas que Sonnet resolvería igual).
  Registrar el análisis aunque no derive propuesta — es evidencia longitudinal.

### Output

1–3 propuestas de mejora a la metodología, formato Fase 9 individual. Si no hay patrón claro, lo informa en una línea ("revisión agregada de N REQs al <fecha> — sin patrón persistente").

Cada propuesta derivada entra como REQ aparte con plan-review (ver [`process/plan-review.md`](plan-review.md)).

### Trazabilidad

El CHANGELOG entry del REQ derivado menciona explícitamente "tras revisión agregada de N REQs al <fecha>". Sin sección dedicada en el repo: el origen vive en la confirmación del cambio del REQ (en git: el commit).

Si Claude identifica un ajuste:

1. Lo propone en una línea: *"Mejora sugerida a la metodología: [cambio concreto]. ¿Se aplica?"*
2. Con confirmación, edita el archivo correspondiente del repo `methodology`.
3. Confirma y entrega el cambio según el mecanismo del profile (en `self-applied`/git, commit + push):
   ```
   docs: actualizar metodología — <descripción breve>
   ```

Si no hay nada que ajustar, lo indica en una línea.

Versionado SemVer y entrada en `CHANGELOG.md`: ver [CLAUDE.md](../CLAUDE.md) del repo.
