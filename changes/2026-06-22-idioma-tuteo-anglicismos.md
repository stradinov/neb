# Política de idioma (mexicano/tuteo + anglicismos) — codificación + barrido repo-wide

**Estado:** Cerrado
**Fecha inicio:** 2026-06-22
**Fecha cierre:** 2026-06-22
**Complejidad estimada:** media
**Complejidad real:** media
**Riesgo de regresión:** medio  <!-- ~45 .md de prosa; protegidos identifiers/código/canónicos; verificado -->

## Contexto

Cierre del pase editorial. Tras revisar README + user-guide doc-por-doc (con ChatGPT) y constatar que el voseo y varios anglicismos son repo-wide (incl. el core), se decidió (a) codificar la política de idioma y (b) barrer la prosa. **Dos rondas de plan-review (3 roles c/u)** acotaron el alcance: anglicismos por **allowlist** (no barrido ciego — habría arrasado los anglicismos canónicos de `vocabulary.md`), política en `communication.md` (no una 3ª fuente), y una lista explícita de protecciones.

## Alcance

### Entra
- **Codificación:** `general/communication.md § "Idioma"` (prosa de los `.md` = español mexicano/tuteo; anglicismos solo tecnológicos/identifiers; referencia a `tooling/redaccion-es.md`); `methodology/principles.md § "No tocar"` enlaza a esa sede.
- **Barrido (~45 `.md` de prosa, vía workflow de 1 agente/archivo + reconciliación manual de user-guide/principles/vocabulary):** voseo→tuteo mexicano + allowlist de anglicismos.
- Minor `5.5.1 → 5.6.0` + `changelog.d/5.6.0.md` + `VERSION` + `plugin.json`.

### No entra
- Anglicismos canónicos (`gate`/`profile`/`overlay`/`workflow`/`override`/`baseline`) y términos tecnológicos (`commit`/`hook`/`plugin`/`deploy`/`push`/`prompt`) — intactos.
- Records (`changes/`, `changelog.d/`, `CHANGELOG.md`, `research/`), código (`hooks/`, `bootstrap/`, `*.sql`), config (`*.json`), `*.template`.
- Ilustración del voseo rioplatense (`tooling/redaccion-es.md:173`) — preservada.
- Anglicismos dev fuera del allowlist (`fork`/`forkear`, `dogfoodear`, `handoff`, `loop`, `score`…) — sin tocar (decisión futura si se quiere ampliar).

## Plan de pruebas

| # | Verificación | Resultado |
|---|---|---|
| 1 | `[crítico]` Scan de términos vetados (PII/marcas) limpio | ✅ (0) |
| 2 | `[crítico]` Voseo residual = 0 (salvo ilustración rioplatense protegida + records) | ✅ |
| 3 | `[crítico]` Canónicos intactos — `gate`/`profile`/`overlay` presentes (55/86 archivos); agents reportan no tocados | ✅ |
| 4 | `assemble-changelog.py --check` verde con 5.6.0; `VERSION` == `plugin.json` | ✅ |
| 5 | Plan-review incorporado: allowlist, sede `communication.md`, protecciones | ✅ |

**Fecha:** 2026-06-22 · **Validador:** Claude (workflow de 45 agentes con summaries + verificación por grep/scan + reconciliación; profile self-applied).

## Trazabilidad

- **Plan aprobado:** conversacional + 2 rondas de plan-review (qa-process-engineer + process-improvement-analyst + context-completeness-reviewer).
- **Commits:** esta confirmación (repo `neb`).
- **Pendientes generados:** ninguno. Pase editorial completo (README/user-guide en `5.5.1`; resto del repo en `5.6.0`).

## Reporte de cierre

| Señal | Valor |
|---|---|
| Archivos tocados | ~47 (.md de prosa + gobernanza) |
| Complejidad estimada / real | media / media |
| Re-entregas | 0 |

Barrido de idioma cerrado: política codificada (`communication.md`) + ~45 `.md` a tuteo mexicano + anglicismos por allowlist, con protecciones verificadas. Sin push aún (se agrupa con `e349a0d`).
