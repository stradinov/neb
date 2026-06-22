# Índice de términos canónicos operativos en `vocabulary.md`

**Estado:** Cerrado
**Fecha inicio:** 2026-06-22
**Fecha cierre:** 2026-06-22
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** medio  <!-- vocabulary.md es SSOT citado cross-file; complejidad baja pero riesgo medio -->

## Contexto

Un diagnóstico externo (ChatGPT) propuso convertir `methodology/vocabulary.md` en una "ontología mínima" con plantilla de ~10-12 campos por término y crear varios archivos nuevos. El fact-check (workflow de mapeo del repo + verificación de las afirmaciones) mostró que `vocabulary.md` ya es maduro (modela REQ, registro≠REQ, proyección-no-identidad, ENUM de estados, riesgo de regresión), pero que **`Fase` y `Gate` no están definidos como términos canónicos**, y que la plantilla de 11 campos + los archivos nuevos chocaban con la regla de austeridad (`principles.md`) y el principio anti-fragmentación.

Roadmap acordado con el dev: **3 REQs incrementales**. Este es **REQ-1**. Objetivo del dev: un vocabulario canónico *operativo* de los conceptos que cambian comportamiento (fases, gates, artefactos, estados, perfiles, roles, entregas, validaciones, excepciones), **legible para quien no domina tecnicismos/anglicismos** y **suficiente para un futuro revisor editorial** (REQ-3).

## Alcance

### Entra
- Sección nueva `## Índice de términos canónicos` en `methodology/vocabulary.md`, **aditiva** (insertada tras la tabla de vocabulario abstracto, antes de `## Requerimiento (REQ)`).
- Tabla de **13 términos** con esquema mínimo: Término · Tipo · Glosa (español llano; anglicismo → equivalente) · No confundir con · Sinónimos (→ permitido / ✗ prohibido) · Canónico (puntero a la fuente de verdad).
- Alta de **`Fase`** y **`Gate`** como términos canónicos (antes solo delegados por puntero).
- Bump minor `5.1.0 → 5.2.0` + fragment `changelog.d/5.2.0.md` + `assemble-changelog.py`.

### No entra
- Reescribir secciones/anclas existentes (se preservan intactas — decisión de diseño por las dependencias cross-file).
- Política editorial / 3 modos de redacción / "redacción suficiente" → **REQ-2** (que absorbe `changes/2026-06-19-md-redaction-guidelines.md`).
- Reviewers `terminology`/`docs-style` + consultor editorial externo (ChatGPT) → **REQ-3**.
- Frontmatter de audiencia en `.md` del núcleo (contradice la convención del repo; nada lo consume hoy).
- Archivos nuevos `semantic-model.md` / `writing-policy.md` (anti-fragmentación: ampliar el archivo canónico, separar solo si aparece fricción real).

## Plan de pruebas

- [x] Las 6 anclas citadas externamente quedan intactas (no se renombró ningún heading).
- [x] Los punteros nuevos (fases/gates/perfil/rol/artefacto) resuelven a sección/archivo real.
- [x] El índice no duplica definiciones ni contradice el ENUM/secciones existentes (override "Coherencia global" eje 1: vocabulario canónico).
- [x] `assemble-changelog.py` + `VERSION` → 5.2.0; gate pre-push `--check` pasa.

### Resultado

| # | Flujo | Resultado |
|---|-------|-----------|
| 1 | `[crítico]` Anclas externas intactas — grep confirma `Vocabulario abstracto` (L1), `Requerimiento (REQ)` (L40), `Registro del requerimiento` (L99), `Estados del requerimiento` (L117), `Tipos de validación` (L135), `Niveles de riesgo de regresión` (L146); índice añadido en L20 | ✅ |
| 2 | `[crítico]` Punteros nuevos resuelven — `general/index.md`, `process/phase-transitions.md`, `process/change-control-gate.md`, `workflow/index.md`, `profiles.md`, `roles-catalog.md`, `workflow/changes.md` existen; anclas internas → headings confirmados | ✅ |
| 3 | Índice no duplica definiciones ni contradice el ENUM (solo Tipo + Glosa + puntero) | ✅ |
| 4 | `assemble-changelog.py` → 44 fragments; gate `--check` `EXIT=0`; `VERSION`=5.2.0 | ✅ |

**Fecha:** 2026-06-22
**Validador:** Claude (revisión de roles + coherencia estática; profile self-applied, cierre inmediato)

## Plan de elaboración

| Elemento | Cambio |
|---|---|
| `methodology/vocabulary.md` | + sección `Índice de términos canónicos` (13 términos); anclas existentes intactas |
| `changelog.d/5.2.0.md` | nuevo fragment minor |
| `VERSION` | `5.1.0` → `5.2.0` |
| `CHANGELOG.md` | ensamblado (auto, `assemble-changelog.py`) |

## Avances realizados

- Índice de 13 términos insertado de forma aditiva (alta de `Fase` y `Gate`).
- Glosas en español llano + anotación de anglicismos (gate, profile, commit, ENUM, push, lock) con su equivalente.
- Fragment 5.2.0 + bump VERSION + CHANGELOG ensamblado; gate `--check` verde.

## Trazabilidad

- **Plan aprobado:** — (complejidad baja; aprobación conversacional vía menú de selección)
- **Commits:** esta confirmación (`feat(vocabulary): índice de términos canónicos operativos…`, repo `neb`; sin push aún)
- **Pendientes generados:**
  - `[vocab-req2-editorial]` — REQ-2: política editorial; **absorbe** `changes/2026-06-19-md-redaction-guidelines.md` (untracked, no implementado) y lo **re-versiona** (su `5.2.0` reservado queda superado por este REQ → usar `5.3.0`).
  - `[vocab-req3-reviewers-consultor]` — REQ-3: reviewers terminology/docs-style + consultor editorial externo (ChatGPT) anclado en el patrón "voz LLM externa" de research.

## Métricas

| Métrica | Valor |
|---|---|
| Turnos — Fase 1-3 (clarificación + propuesta, sobre el diagnóstico) | ~5 |
| Turnos — Fase 4 Implementación | 1 |
| Turnos — Fase 5 Validación | (en este turno) |
| **Turnos total** | ~6 |
| Complejidad estimada / real | baja / baja |

## Reporte de cierre

| Señal | Valor |
|---|---|
| Turnos total | ~6 |
| Re-entregas | 0 |
| Complejidad estimada / real | baja / baja |

REQ-1 del roadmap vocabulario+editorial cerrado: índice de 13 términos canónicos operativos en `vocabulary.md`, alta de `Fase`/`Gate`, esquema con glosa (anglicismos → equivalente) y desambiguación (`No confundir con` + sinónimos). Validación: anclas externas intactas + punteros resuelven + gate `assemble-changelog --check` verde. Pendiente solo el `git push` (coordinar por `5643e7d`). Siguientes incrementos: REQ-2 (política editorial, absorbe `md-redaction-guidelines`) y REQ-3 (reviewers + consultor externo ChatGPT).
