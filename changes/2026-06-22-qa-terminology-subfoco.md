# Sub-foco de precisión terminológica en `qa-process-engineer`

**Estado:** Cerrado
**Fecha inicio:** 2026-06-22
**Fecha cierre:** 2026-06-22
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** bajo  <!-- refina el prompt de un revisor; no toca ENUMs, imports ni flujo -->

## Contexto

REQ-3 del roadmap vocabulario+editorial. El diagnóstico externo (ChatGPT) proponía dos agentes nuevos (`terminology-reviewer` + `docs-style-reviewer`). El plan-review (qa-process-engineer + process-improvement-analyst + context-completeness-reviewer) los **rechazó** por la regla anti-role-inflation de `roles-catalog.md` (§ "Preferencia explícita": ajustar foco antes que crear rol) y dejó solo la pieza de alto valor: **precisión terminológica como sub-foco de `qa-process-engineer`**.

Decisiones del dev que colapsaron el alcance:
- **P2 (docs-style)** descartado: duplicaba el "calibre por consumidor" cerrado en REQ-2.
- **P3 (consultor externo)** descartado: el dev usará ChatGPT como revisor externo ad-hoc **desde la web**; no se formaliza en Neb.

## Alcance

### Entra
- `agents/qa-process-engineer.md`: el foco "Vocabulario canónico" se desdobla en *(a) agnóstico del profile* [existente] y *(b) precisión terminológica* [nuevo]; `description` actualizada. Oráculo verificable: columnas "No confundir con" + "Sinónimos" del § "Índice de términos canónicos" de `vocabulary.md` (entregado en REQ-1).
- `profiles/self-applied/roles.md`: eco del desdoblamiento en el foco de QA.
- `methodology/roles-catalog.md` § "Atribución del defecto": fila nueva (sinónimo no declarado / término mezclado → QA sub-foco precisión terminológica).
- Patch `5.3.0 → 5.3.1` + `changelog.d/5.3.1.md` + assemble.

### No entra
- Agente nuevo (regla anti-role-inflation; el sub-foco encaja en QA).
- `docs-style` reviewer (P2, descartado — lo cubre REQ-2).
- Consultor editorial externo formalizado en Neb (P3, descartado — ChatGPT ad-hoc desde la web).

## Plan de pruebas

- [x] La frontera (a)/(b) queda explícita → no duplica el foco de vocabulario existente (hallazgo de context-completeness).
- [x] El sub-foco tiene oráculo verificable (columnas del Índice de `vocabulary.md`), no "revisa terminología" genérico (hallazgo de process-improvement).
- [x] Las 3 sedes coherentes (body del agente + `self-applied/roles.md` + `roles-catalog.md`); ningún heading renombrado → sin anclas rotas.
- [x] `assemble-changelog.py --check` verde con 5.3.1; `VERSION` 5.3.0 → 5.3.1.

> Riesgo bajo → checklist basta (sin tabla `### Resultado` ni fila `[crítico]`, por [planning.md](../process/planning.md) § "Riesgo de regresión").

## Plan de elaboración

| Elemento | Cambio |
|---|---|
| `agents/qa-process-engineer.md` | foco vocabulario → (a)+(b); `description` + sub-foco precisión terminológica con oráculo |
| `profiles/self-applied/roles.md` | eco del desdoblamiento |
| `methodology/roles-catalog.md` | fila de atribución para Fase 9 |
| `changelog.d/5.3.1.md` · `VERSION` | patch 5.3.1 |

## Avances realizados

- 3 edits aplicados; fragment 5.3.1 + bump + CHANGELOG ensamblado.
- Plan-review incorporado (frontera declarada + oráculo verificable + 3 sedes).

## Trazabilidad

- **Plan aprobado:** — (complejidad baja; aprobación conversacional + plan-review de 3 roles)
- **Commits:** esta confirmación (repo `neb`; sin push aún)
- **Pendientes generados:** ninguno. Roadmap vocabulario+editorial **completado** (REQ-1/REQ-2/REQ-3); REQ-4 (cuadro de modos en `docs/`) sigue siendo opcional/diferido.

## Métricas

| Métrica | Valor |
|---|---|
| Turnos — Fase 1-3 (propuesta + plan-review) | ~2 |
| Turnos — Fase 4 Implementación | 1 |
| **Turnos total** | ~3 |
| Complejidad estimada / real | baja / baja |

## Reporte de cierre

| Señal | Valor |
|---|---|
| Turnos total | ~3 |
| Re-entregas | 0 |
| Complejidad estimada / real | baja / baja |

REQ-3 cerrado: sub-foco de precisión terminológica en `qa-process-engineer` (no agente nuevo, por la regla anti-role-inflation), con oráculo verificable en el Índice de términos de REQ-1. P2 (docs-style) y P3 (consultor externo) descartados por decisión del dev (ChatGPT ad-hoc desde la web). **Roadmap vocabulario+editorial COMPLETO**: REQ-1 (v5.2.0) + REQ-2 (v5.3.0) + REQ-3 (v5.3.1). Pendiente: `git push` (4 commits locales: ops-capture + REQ-1/2/3). REQ-4 (cuadro de modos en `docs/`) opcional/diferido.
