# Política editorial: suficiencia + calibre por consumidor en `principles.md`

**Estado:** Cerrado
**Fecha inicio:** 2026-06-22
**Fecha cierre:** 2026-06-22
**Complejidad estimada:** media
**Complejidad real:** media
**Riesgo de regresión:** medio  <!-- principles.md es doctrina núcleo con muchos consumidores -->

## Contexto

REQ-2 del roadmap vocabulario+editorial (tras REQ-1 `vocabulario-canonico-operativo`, cerrado en `b432479`). Atiende dos objetivos del diagnóstico externo (ChatGPT): formalizar que la austeridad no debe volver escuetos los textos de cara al humano, y dar un piso de "redacción suficiente" / anti-"escuetez falsa".

**Absorbe** el change MD untracked `changes/2026-06-19-md-redaction-guidelines.md` (no implementado), cuyos Edit A/B (tría de ejemplos + subsección `### Claridad`) ya habían sido revisados por roles. Su lineaje: los 7 patrones de error de redacción capturados en `communication-refactor` (v4.10.0).

## Alcance

### Entra
- `methodology/principles.md` § "Lineamientos para editar MDs", 3 edits:
  - **A** (absorbido): bullet de ejemplos → tría convertir/cortar/conservar.
  - **B** (absorbido + 1 bullet): nueva subsección `### Claridad` (contrato-de-output · término-canónico-una-acepción · claridad-sobre-compresión · **suficiencia** condición/acción/consecuencia).
  - **C** (nuevo): intro — criterio de corte generalizado a "comportamiento del **consumidor**"; calibre por consumidor (agente austero vs documentación de cara al adoptante `docs/` + `README.md`, que admite más contexto); piso inferior de suficiencia.
- Bump minor `5.2.0 → 5.3.0` + `changelog.d/5.3.0.md` + assemble.
- Eliminación del draft untracked `changes/2026-06-19-md-redaction-guidelines.md` (absorbido).

### No entra
- Tabla de "3 modos de redacción" en `principles.md` — **descartada en plan-review** (duplica la excepción `docs/` L42; ceremonia sin payoff). Si se quiere como material pedagógico, va en `docs/` → diferido a REQ-4.
- "Redacción suficiente" como subsección con 6 preguntas — **reformulada en plan-review** a contrato de output (3 elementos) y fundida en `### Claridad`, para no prescribir el razonamiento interno de Claude (anti-patrón L88).
- Reviewers terminology/docs-style + consultor externo → REQ-3.

## Plan de pruebas

- [x] Anclas: única cita por ancla a `principles.md` es `#características` (en `promises.md`) — no se toca; las subsecciones `###` no se citan por ancla → insertar `### Claridad` no rompe nada.
- [x] Edit B "suficiencia" enlaza a § Eliminar y § Conservar → no crea tercera formulación duplicada del eje "por qué" (L144).
- [x] Edit C no relaja austeridad: la normativa sigue austera; nombra calibre humano como **permitido** (`admite`), no prescrito, consistente con la excepción `docs/` (L42).
- [x] `assemble-changelog.py --check` verde con 5.3.0; `VERSION` 5.2.0 → 5.3.0; no toca el fragment 5.2.0 (REQ-1).

### Resultado

| # | Flujo | Resultado |
|---|-------|-----------|
| 1 | `[crítico]` Anclas externas intactas — `principles.md#características` no tocado; subsecciones no citadas por ancla (verificado por context-completeness-reviewer) | ✅ |
| 2 | `[crítico]` Sin regla duplicada — "suficiencia" enlaza a § Eliminar/§ Conservar (L128) en vez de re-enunciar el eje "por qué" | ✅ |
| 3 | Edit C consistente con excepción `docs/` (calibre permitido, no prescripción); no convierte `docs/`/`README` en clasificable M/P | ✅ |
| 4 | `assemble-changelog.py` → 45 fragments; gate `--check` `EXIT=0`; `VERSION`=5.3.0; fragment 5.2.0 intacto | ✅ |

**Fecha:** 2026-06-22
**Validador:** Claude (plan-review de roles: qa-process-engineer + process-improvement-analyst + context-completeness-reviewer; profile self-applied, cierre inmediato)

## Plan de elaboración

| Elemento | Cambio |
|---|---|
| `principles.md` (intro § Lineamientos) | criterio de corte → "consumidor"; calibre `docs/`+`README`; piso de suficiencia |
| `principles.md` § Eliminar | bullet ejemplos → tría |
| `principles.md` § Claridad (nueva) | 4 bullets (3 absorbidos + suficiencia) |
| `changelog.d/5.3.0.md` | nuevo fragment minor |
| `VERSION` | 5.2.0 → 5.3.0 |
| `changes/2026-06-19-md-redaction-guidelines.md` | eliminado (absorbido) |

## Avances realizados

- 3 edits aplicados a `principles.md`; fragment 5.3.0 + bump + CHANGELOG ensamblado; gate verde.
- Plan-review incorporado: tabla de modos descartada, suficiencia reformulada a contrato de output.
- Edit C ampliado para incluir `README.md` (instrucción del dev).

## Trazabilidad

- **Plan aprobado:** — (aprobación conversacional vía menú + ajuste del dev; complejidad media sin plan mode)
- **Commits:** esta confirmación (repo `neb`; sin push aún)
- **Pendientes generados:**
  - `[vocab-req3-reviewers-consultor]` — REQ-3.
  - `[vocab-req4-docs-modos]` — REQ-4 (opcional): cuadro pedagógico Normativa/Explicativa/Adopción en `docs/` (capa de adopción), no en `principles.md`.

## Métricas

| Métrica | Valor |
|---|---|
| Turnos — Fase 1-3 (clarificación + propuesta + plan-review) | ~3 |
| Turnos — Fase 4 Implementación | 1 |
| **Turnos total** | ~4 |
| Complejidad estimada / real | media / media |
| Re-entregas en validación | 0 |

## Reporte de cierre

| Señal | Valor |
|---|---|
| Turnos total | ~4 |
| Re-entregas | 0 |
| Complejidad estimada / real | media / media |

REQ-2 cerrado: política editorial en `principles.md` § "Lineamientos para editar MDs" — criterio de corte por **consumidor** (austero para el agente; `docs/`/`README.md` admiten más contexto), nueva subsección `### Claridad` con suficiencia/anti-escuetez como **contrato de output**, y tría de ejemplos. Absorbió y superó el draft `md-redaction-guidelines`. Plan-review (3 roles) recortó el alcance: descartó la tabla de 3 modos y reformuló la suficiencia para no prescribir razonamiento interno (anti-patrón L88). Validación: anclas intactas + sin regla duplicada + gate changelog verde. Pendiente: `git push` (3 commits locales). Siguiente: REQ-3 (reviewers + consultor externo); REQ-4 opcional (cuadro de modos en `docs/`).
