# Métricas y handoff de sesión

Métricas que Claude registra automáticamente en `<proyecto>/changes/<fecha>-<nombre>.md` para retroalimentar la metodología.

## Tabla

Tabla en [`templates/change.md.template`](../templates/change.md.template).

- **Turnos por fase** se cuentan al cierre de cada fase.
- **Re-entregas** se incrementa por cada nuevo ciclo de validación fallida (nueva versión enviada al ambiente de revisión o equivalente). **No incluye** fix-revalidate locales pre-validación — sólo cuenta cuando el entregable vuelve a salir al ambiente de revisión o equivalente.
- **Incidencias** y **complejidad estimada vs real** se completan al cerrar (Fase 8).

## Cuándo accionar

Umbrales sugeridos. Al cerrar el requerimiento, Claude compara las métricas contra esta tabla y, si alguna se supera, propone la acción correspondiente en Fase 9 (ver [`process/improvement.md`](../process/improvement.md) "Disparadores cuantitativos").

| Métrica | Umbral | Acción en Fase 9 | Utilidad | Última act. |
|---|---|---|---|---|
| **Re-entregas** | > 2 | Plan de pruebas insuficiente — revisar criterios y casos cubiertos | 1.0 | 2026-05-03 |
| **Turnos Fase 1 (Clarificación)** | > 5 | Propuesta inicial poco clara — destilar lecciones para clarificación | 1.0 | 2026-05-03 |
| **Complejidad real ≠ estimada** | desviación de 2+ niveles (baja↔alta) | Calibrar criterios de estimación en `planning.md` | 1.0 | 2026-05-03 |
| **Incidencias surgidas** | ≥ 3 | Plan no anticipó dependencias — revisar Fase 3 (alcance/riesgos) | 2.0 | 2026-05-03 |
| **Errores de implementación de Claude** | ≥ 2 | Revisar claridad del plan: ¿faltó detalle?, ¿propuesta ambigua?, ¿lineamiento aplicado confuso? | 2.0 | 2026-05-03 |
| **Faltas de contexto** | ≥ 3 | Patch a CLAUDE.md / memoria del proyecto / metodología — la info debería ser hallable sin pedirla | 1.0 | 2026-05-03 |
| **Implementaciones sin aprobación** | ≥ 1 | Revisar criterios de aprobación implícita en `planning.md` § "Propuesta de implementación" | 1.0 | 2026-05-03 |
| **Acciones destructivas no autorizadas** | ≥ 1 | Revisar reglas en [`../process/change-control-gate.md`](../process/change-control-gate.md) § "Acciones destructivas" y reforzar disciplina | 1.0 | 2026-05-03 |
| **Out-of-scope edits** | ≥ 1 | Revisar plan o disciplinar alcance en Fase 3 | 1.0 | 2026-05-03 |

Los umbrales son sugeridos, ajustables por experiencia. Si una desviación tiene causa documentada (ej. complejidad real subió por incidencia mayor anotada), la acción puede saltarse con justificación en el MD.

### Definiciones operativas

Captura: las 3 primeras dependen de señal explícita o ausencia de ella; las 3 últimas son **auto-reportadas por Claude al cierre** (silenciosas para el dev — visibles al revisar Métricas del MD antes de aprobar cierre).

- **Incidencias surgidas**: cambios menores no planeados durante la implementación (rename de columna, archivo SQL faltante, bug detectado en repaso). Sobre el **alcance**.
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

## Heurística de ajuste de utilidad

Cada métrica tiene un score que refleja su valor real para sugerir mejoras. Se ajusta en Fase 9 según el resultado del REQ derivado.

### Eventos

| Evento | Δ score |
|---|---|
| Métrica dispara → propuesta → REQ aprobado e implementado | +1 |
| Métrica dispara → REQ aprobado parcialmente | +0.5 |
| Métrica dispara → REQ rechazado por ceremonia / Process Improvement Analyst | -0.5 |
| Métrica dispara → REQ aprobado pero genera fricción reportada en uso | -0.25 |
| 10 changes consecutivos sin disparar la métrica | -0.1 |

### Rangos

| Score | Interpretación | Acción |
|---|---|---|
| ≥ +3 | Core | Mantener prioritaria |
| +1 a +3 | Útil | Sin acción |
| 0 a +1 | Neutral / nueva | Observar |
| -1 a 0 | Marginal | Revisar umbral o definición |
| < -1 sostenido por 2 ajustes consecutivos | Candidata a deprecar | Propuesta explícita en revisión agregada |

**Cap**: min -2, max +5 (más allá no aporta información).

**Score inicial al introducir una métrica nueva**: 1.0 (neutral, sin evidencia previa).

Trigger del ajuste: en Fase 9 cuando la métrica genere (o no genere por silencio prolongado) propuesta. Revisión agregada (ver `improvement.md`) verifica scores periódicamente y propone deprecaciones.

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
| Pausas / SessionStart | 1/5 | ❌ No admitida | Mezcla señal con ruido de runtime; sin acción derivada clara |
| Duración calendario | 3/5 | ❌ No admitida (descartada en sesión de diseño) | Útil pero cubre otro propósito (gestión de bloqueos); no es datos informativos |

### Tokens, costo y breakdown por modelo

**Por qué pasa los 5 criterios:**

1. Tokens y USD son unidades comparables entre cualquier REQ y profile.
2. Se cruza con complejidad estimada/real, fase, y modelo activo — permite detectar calibración rota.
3. Interpreta directamente: si un REQ de complejidad "baja" costó como "media", el dev recalibra su criterio.
4. Tokens son estables — no los afecta la velocidad del sistema, el modelo usado, ni los reinicios de sesión.
5. Cross-REQs permite separar dos señales: evolución de Claude (mismo modelo, metodología mejoró → costo baja) y evolución del modelo (mismo tipo de REQ → ¿Opus 4.7 es más eficiente que 4.6?).

**Captura:** hook `Stop` (`hooks/usage-tracker.sh`) actualiza automáticamente la sección "Reporte de cierre" del draft del change MD al cierre de cada turno. Requiere al menos un `active_<proyecto>_<slug>.md` (o sección legacy `## Requerimiento activo`); con varios REQ activos, atribuye el costo del turno al de modificación más reciente.

**Breakdown por modelo:** el JSONL de la sesión registra el campo `model` en cada entry de tipo `assistant`. El hook agrupa tokens y costo por modelo en la misma invocación — soporta cambio de modelo mid-sesión (`/model`).

**Pricing:** tabla manual en `hooks/pricing.yml`. Actualizar cuando Anthropic publique nuevo modelo o cambie precios.

**Score inicial:** 1.0 — igual que métricas accionables. Entra al ciclo de revisión agregada (`improvement.md §Revisión agregada`). Si en 10 REQs consecutivos el dato no aporta aprendizaje reportado, proponer revisión.

### Loop pedagógico en la revisión agregada

La revisión agregada (`improvement.md §Revisión agregada`) incluye como sub-análisis adicional:

- **Evolución por modelo**: comparar cost-per-REQ a complejidad constante entre versiones de Claude. Si el costo baja manteniendo calidad → Claude mejoró. Si sube → el dev debe investigar (¿el REQ era comparable? ¿cambió la metodología?).
- **Calibración de complejidad**: si REQs de complejidad "baja" tienen tokens consistentemente en el rango de "media", el criterio de estimación requiere ajuste (ver REQ futuro de calibración automática — requiere corpus N ≥ 20 por nivel).

## Handoff entre sesiones

El procedimiento de handoff (retomar un requerimiento interrumpido, pausar/reanudar la propia sesión por nombre con `claude --resume`, y el **relevo cross-dev** vía la [bitácora de relevo](logbook.md)) es gestión de sesión, no métrica — vive en [`../process/execution.md`](../process/execution.md) § "Gestión de sesiones (handoff)".
