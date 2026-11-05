# Métricas y handoff de sesión

Métricas que Claude registra automáticamente en `<proyecto>/changes/<fecha>-<nombre>.md` para retroalimentar la metodología.

## Tabla

Tabla en [`templates/change.md.template`](../templates/change.md.template).

- **Turnos por fase** se cuentan al cierre de cada fase.
- **Re-entregas** se incrementa por cada nuevo ciclo de validación fallida (nueva versión enviada al ambiente de revisión o equivalente). **No incluye** fix-revalidate locales pre-validación — sólo cuenta cuando el entregable vuelve a salir al ambiente de revisión o equivalente. Un ciclo va de una validación que falla a la siguiente validación del entregable corregido; lo que falla a la vez y se corrige junto es un solo ciclo, aunque fallen varias pruebas o revisores.
  - **En un profile de proceso** ([`vocabulary.md`](../methodology/vocabulary.md) § "Tipos de validación"), su validación empieza con la primera revisión de gate de Fase 4 o la primera prueba que juzga otro rol (un subagente o el dev), lo que ocurra antes, y falla con una revisión de gate de Fase 4 o 7 con hallazgos, una prueba del plan que no cumple su criterio o una entrega que el dev devuelve por un defecto, si obliga a corregir el entregable o su changelog; la falla corregida suma aunque no se vuelva a validar. Lo que el rol principal corre y corrige antes es fix-revalidate local. No cuentan: el plan-review de Fase 3, que revisa el plan; la corrección que solo toca el registro, que documenta *sobre* el REQ ([`vocabulary.md`](../methodology/vocabulary.md) § "Discriminador registro vs entregable"), salvo que el plan lo declare parte del entregable; la que corrige la prueba misma; ni el cambio que el dev pide por preferencia o por información nueva.
- **Incidencias** y **complejidad estimada vs real** se completan al cerrar (Fase 8).

## Cuándo accionar

Umbrales sugeridos. Al cerrar el requerimiento, Claude compara las métricas contra esta tabla y, si alguna se supera, propone la acción correspondiente en Fase 9 (ver [`process/improvement.md`](../process/improvement.md) "Disparadores cuantitativos").

| Métrica | Umbral | Acción en Fase 9 |
|---|---|---|
| **Re-entregas** | > 2 | Diagnóstico de los defectos que causaron esos ciclos ([`process/improvement.md`](../process/improvement.md) § "Diagnóstico de origen del defecto"), con la mejora que deriva de su etapa de origen y tipo de causa, o ninguna si el diagnóstico no deriva mejora; si la causa es un caso que el plan de pruebas no cubría, revisar sus criterios y casos |
| **Turnos Fase 1 (Clarificación)** | > 5 | Propuesta inicial poco clara — destilar lecciones para clarificación |
| **Complejidad real ≠ estimada** | desviación de 2+ niveles (baja↔alta) | Calibrar criterios de estimación en `planning.md` |
| **Incidencias surgidas** | ≥ 3 | Plan no anticipó dependencias — revisar Fase 3 (alcance/riesgos) |
| **Errores de implementación de Claude** | ≥ 2 | Revisar claridad del plan: ¿faltó detalle?, ¿propuesta ambigua?, ¿lineamiento aplicado confuso? |
| **Faltas de contexto** | ≥ 3 | Patch a CLAUDE.md / memoria del proyecto / metodología — la info debería ser hallable sin pedirla |
| **Implementaciones sin aprobación** | ≥ 1 | Revisar criterios de aprobación implícita en `planning.md` § "Propuesta de implementación" |
| **Acciones destructivas no autorizadas** | ≥ 1 | Revisar reglas en [`../methodology/change-control-policy.md`](../methodology/change-control-policy.md) § "Acciones destructivas" y reforzar disciplina |
| **Out-of-scope edits** | ≥ 1 | Revisar plan o disciplinar alcance en Fase 3 |

Los umbrales son sugeridos, ajustables por experiencia. Si una desviación tiene causa documentada (ej. complejidad real subió por incidencia mayor anotada), la acción puede saltarse con justificación en el MD, salvo la de Re-entregas, que ya parte de la causa.

### Definiciones operativas

Captura: las 3 primeras dependen de señal explícita o ausencia de ella; las 3 últimas son **auto-reportadas por Claude al cierre** (silenciosas para el dev — visibles al revisar Métricas del MD antes de aprobar cierre).

- **Incidencias surgidas**: cambios menores no planeados durante la implementación (renombre de columna, archivo SQL faltante, bug detectado en repaso). Sobre el **alcance**. En un profile de proceso, entre el plan aprobado y la entrega final, cuenta una incidencia por cada elemento —archivo, sección, regla (también una fila de tabla o un hallazgo de research) o dependencia— que la entrega agrega o quita respecto del alcance aprobado (el plan o, sin plan, el pedido del dev), y por cada defecto ajeno a lo planeado que corrige (así se lee «bug detectado en repaso»), lo encuentre quien lo encuentre: el rol principal, una prueba, un gate o el dev. Un mismo elemento repartido en varios archivos cuenta uno. Una regla nueva cuenta aunque la pida un hallazgo; reescribir una regla planeada para corregir su defecto no cuenta, ni lo que se agrega y se quita antes de la entrega. La métrica cuenta el desvío; si el cambio se tramita como incidencia durante el trabajo o vuelve a Fase 3 lo decide [`process/execution.md`](../process/execution.md) § "Incidencias durante el trabajo", y en los dos casos suma. Incidencias y Re-entregas miden cosas distintas: un mismo hallazgo puede sumar a las dos.
- **Errores de implementación de Claude**: veces que Claude se desvió del plan aprobado y el dev tuvo que señalarlo. Sobre la **ejecución**. NO cuenta autocorrección dentro de la misma respuesta. NO cuenta clarificación legítima sobre info inexistente.
- **Faltas de contexto**: veces que Claude pidió o asumió algo ya documentado en CLAUDE.md, memoria del proyecto o repo de metodología. Sobre la **recuperación de información**. Señal de gap en docs, no en el agente.
- **Implementaciones sin aprobación**: veces que Claude entró a Fase 4 sin OK explícito ni implícito según [`planning.md`](../process/planning.md) § "Propuesta de implementación". **No cuenta como falta** la aprobación implícita válida (pregunta sobre detalles o contrapropuesta que **asume** que el código se escribirá) — eso es aprobación. **Sí cuenta** solo: silencio, pregunta de aclaración sin presuponer implementación, o contrapropuesta que requiere nueva confirmación.
- **Acciones destructivas no autorizadas**: veces que Claude ejecutó una acción que reescribe historia o destruye estado recuperable sin autorización explícita en la sesión (en git: `--force`, `reset --hard`, `--no-verify`, `git add -A/.`, `branch -D`; en BD: `drop table`). NO cuenta cuando la autorización es contextual (ej. restaurar un archivo durante rollback de incidente).
- **Out-of-scope edits**: archivos modificados que NO estaban listados en sección "Alcance / Entra" del change MD. NO cuenta incidencias legítimas — esas viven en `Incidencias surgidas`.

**Patches retrospectivos** (cuando una versión posterior corrige un error u omisión de un REQ previo): cuentan como **error de implementación retroactivo** del REQ original, anotados en el patch nuevo (donde el error se evidencia y corrige), no en el REQ original ya cerrado.

**Auditoría de métricas auto-reportadas**: "Errores de implementación de Claude" y "Faltas de contexto" se completan al cierre (Fase 8) por el rol revisor de calidad del profile, no por auto-reporte:

| Profile | Auditor |
|---|---|
| `self-applied` | QA Process Engineer |
| Profiles de software (futuros) | Code Reviewer |

El auditor revisa la conversación del REQ y completa los conteos. Si el dev nota discrepancia al revisar el MD pre-cierre, ajusta los counts.

## Datos informativos

Señales que aparecen en el **Reporte de cierre** al finalizar un REQ. No tienen umbral ni acción inmediata en Fase 9 — su propósito es cerrar un **loop pedagógico**: el dev forma hipótesis sobre su uso de Claude y la metodología, y las valida en el siguiente REQ.

### Criterios de admisión

Una señal debe pasar todos los criterios para entrar con interpretación sugerida. Pasar 2–3 la admite como dato crudo sin interpretación. Pasar < 2 descarta la señal.

| # | Criterio | Qué exige |
|---|---|---|
| 1 | **Comparable cross-REQ** | Misma unidad, normalizable entre proyectos y profiles |
| 2 | **Atribuible a dimensiones** | Se puede cruzar con complejidad / fase / profile para extraer señal |
| 3 | **Loop pedagógico explícito** | El reporte sugiere qué aprender con ese dato |
| 4 | **Bajo ruido** | No fluctúa por factores externos al REQ (velocidad de red, reinicio de sesión, herramientas lentas) |
| 5 | **Alimenta revisión agregada** | Cross-REQs permite detectar patrones longitudinales (ej. evolución de costo por modelo) |

### Señales evaluadas

| Señal | Criterios | Veredicto | Razón de exclusión (si aplica) |
|---|---|---|---|
| **Tokens + costo + breakdown por modelo** | 5/5 | ✅ Dato informativo (con interpretación) | — |
| Tiempo wall-clock | 2/5 | ❌ No admitida | Ruido por tools lentas; no atribuible a fases; varía con modelo |
| Líneas de código netas | 2/5 | ❌ No admitida | No comparable cross-profile; no atribuible; refactors la distorsionan |
| Conteo de commits | 1/5 | ❌ No admitida | No correlaciona con calidad; no atribuible |
| Pausas / SessionStart | 1/5 | ❌ No admitida | Mezcla señal con ruido de tiempo de ejecución; sin acción derivada clara |
| Duración calendario | 3/5 | ❌ No admitida (descartada en sesión de diseño) | Útil pero cubre otro propósito (gestión de bloqueos); no es datos informativos |

### Tokens, costo y breakdown por modelo

**Por qué pasa los 5 criterios:**

1. Tokens y USD son unidades comparables entre cualquier REQ y profile.
2. Se cruza con complejidad estimada/real, fase, y modelo activo — permite detectar calibración rota.
3. Interpreta directamente: si un REQ de complejidad "baja" costó como "media", el dev recalibra su criterio.
4. Tokens son estables — no los afecta la velocidad del sistema, el modelo usado, ni los reinicios de sesión.
5. Cross-REQs permite separar dos señales: evolución de Claude (mismo modelo, metodología mejoró → costo baja) y evolución del modelo (mismo tipo de REQ → ¿Opus 4.7 es más eficiente que 4.6?).

**Captura:** hook `Stop` `usage-tracker` (`hooks/lib/usage-tracker.py`) actualiza automáticamente la sección "Reporte de cierre" del draft del change MD al cierre de cada turno. Requiere al menos un `active_<proyecto>_<slug>.md` (o sección legacy `## Requerimiento activo`); con varios REQ activos, atribuye el costo del turno al de modificación más reciente.

**Breakdown por modelo:** el JSONL de la sesión registra el campo `model` en cada entry de tipo `assistant`. El hook agrupa tokens y costo por modelo en la misma invocación — soporta cambio de modelo mid-sesión (`/model`).

**Pricing:** tabla manual en `hooks/pricing.yml`. Actualizar cuando Anthropic publique nuevo modelo o cambie precios.

**Revisión:** entra a la revisión agregada (`improvement.md §Revisión agregada`). Si en 10 REQs consecutivos el dato no aporta aprendizaje reportado, proponer revisión.

### Loop pedagógico en la revisión agregada

La revisión agregada (`improvement.md §Revisión agregada`) incluye como sub-análisis adicional:

- **Evolución por modelo**: comparar cost-per-REQ a complejidad constante entre versiones de Claude. Si el costo baja manteniendo calidad → Claude mejoró. Si sube → el dev debe investigar (¿el REQ era comparable? ¿cambió la metodología?).
- **Calibración de complejidad**: si REQs de complejidad "baja" tienen tokens consistentemente en el rango de "media", el criterio de estimación requiere ajuste (ver REQ futuro de calibración automática — requiere corpus N ≥ 20 por nivel).

## Handoff entre sesiones

El procedimiento de handoff (retomar un requerimiento interrumpido, pausar/reanudar la propia sesión por nombre con `claude --resume`, y el **relevo cross-dev** vía la [bitácora de relevo](logbook.md)) es gestión de sesión, no métrica — vive en [`../process/execution.md`](../process/execution.md) § "Gestión de sesiones (handoff)".
