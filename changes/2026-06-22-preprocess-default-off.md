# `preprocess-prompt` arranca en modo `off` por defecto

**Estado:** Cerrado
**Fecha inicio:** 2026-06-22
**Fecha cierre:** 2026-06-22
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** bajo  <!-- cambia un default + doc; no toca ENUMs, imports ni flujo; hook opt-in personal -->

## Contexto

El dev reportó que el hook `preprocess-prompt` (`UserPromptSubmit`) podía "corregir" texto pegado de propuestas de prompt ya definidas externamente que no deben modificarse. Tras desactivarlo en su `~/.claude/settings.json` (sesión personal) y registrar el modelo de control bajo demanda, pidió que la **instalación de Neb** entregue el hook **inerte por defecto**: que se instale pero no actúe hasta que cada dev lo encienda explícitamente.

Decisión del dev (menú): entre "no instalar (sacar del template)" vs "instalar pero arrancar `off`", eligió **arrancar en modo `off`** — el bloque del template se conserva; solo cambia el default de comportamiento.

## Alcance

### Entra
- `hooks/preprocess-prompt.py`: `DEFAULTS["mode"]` `"full"` → `"off"`; fallback de `resolve_mode` (`cfg.get("mode", "full")`) → `"off"`.
- `tooling/prompt-preprocessing.md`: default `off` coherente en 7 sedes de doc — tabla §4, ejemplo + tabla §5, precedencia §6 (+ nota de `$$` bajo default off), snippets de instalación PowerShell/bash §7, nota de activación §7, nota + escenario #5 de §11. **Crítico**: los snippets de §7 escribían `preprocess.json` con `"full"` y, por precedencia (archivo personal > default hardcoded), habrían anulado el cambio del código.
- `commands/preprocess.md`: documenta que el hook arranca en `off` por defecto y que `/preprocess full|fast` lo enciende; `/preprocess off` reformulado como "vuelve al estado por defecto (inerte)". (8ª sede de doc; hallazgo de plan-review.)
- Minor `5.3.1 → 5.4.0` + `changelog.d/5.4.0.md` + assemble.
- `.claude-plugin/plugin.json`: `version` → `5.4.0` (sincroniza con `VERSION`; ver Notas).

### No entra
- `templates/claude-user-settings.json.template`: NO se toca — el hook se sigue instalando (la decisión fue "arrancar off", no "no instalar").
- Sacar el bloque del template (opción descartada por el dev).
- Lógica del hook más allá del default (maquinaria de corrección/eco/confirmación intacta).

## Plan de pruebas

- [x] Con `preprocess.json` ausente y sin `/preprocess`, el hook resuelve `off` y retorna sin llamar a Haiku ni emitir contexto (verificado vía `resolve_mode`/`main`).
- [x] `/preprocess full|fast` y env var siguen activando; el prefijo `$$` conserva precedencia máxima (fuerza `off` en el turno pese a la sesión). Ver nota de §6 sobre su semántica bajo default off.
- [x] Las 10 sedes del default coherentes (2 código + 8 doc, incl. `commands/preprocess.md`); ningún snippet de instalación deja `"full"`.
- [x] `assemble-changelog.py --check` verde con 5.4.0; `VERSION` 5.3.1 → 5.4.0; `plugin.json` == `VERSION` (gate 5 pre-push).

> Riesgo bajo → checklist basta (sin tabla `### Resultado` ni fila `[crítico]`, por `process/planning.md` § "Riesgo de regresión").

## Plan de elaboración

| Elemento | Cambio |
|---|---|
| `hooks/preprocess-prompt.py` | `DEFAULTS` mode → off; fallback → off |
| `tooling/prompt-preprocessing.md` | default off coherente en §4/§5/§6/§7/§11 (incl. snippets de instalación + nota de `$$`) |
| `commands/preprocess.md` | documenta default off + activación con `full`/`fast` |
| `changelog.d/5.4.0.md` · `VERSION` | minor 5.4.0 |
| `.claude-plugin/plugin.json` | version → 5.4.0 |

## Avances realizados

- 2 edits en el hook + 8 edits en `prompt-preprocessing.md` + `commands/preprocess.md` aplicados.
- Fragment 5.4.0 + bump `VERSION` + `plugin.json` + `CHANGELOG.md` ensamblado (`assemble-changelog.py --check` verde).
- Plan-review (qa-process-engineer + context-completeness-reviewer) incorporado: +`commands/preprocess.md` (8ª sede), +nota de `$$` en §6/§11. Verificación funcional de `resolve_mode` OK.
- Commit gated: pendiente OK del dev.

## Trazabilidad

- **Plan aprobado:** conversacional (menú "Implementar ahora") + este change MD.
- **Commits:** commit de cierre `feat(preprocess): default off…` (repo `neb`, rama `main`; **sin push** — se acumula a los commits locales previos).
- **Pendientes generados:** ninguno propio. Hallazgo lateral: drift histórico de `plugin.json` (estaba en 5.1.0) — saneado en este REQ al sincronizar a 5.4.0; los huecos 5.2/5.3 no se reescriben.

## Notas

- **Drift `plugin.json`:** estaba en `5.1.0` mientras `VERSION` iba en `5.3.1` (los REQs 5.2.0/5.3.0/5.3.1 no lo bumpearon). Este REQ lo sincroniza directo a `5.4.0` (salto; hueco aceptable por `process/version-control.md` § "Resolución de colisión de versión"). No se reescriben los huecos.
- **Alcance del cambio de comportamiento:** afecta solo a quien tenga el hook activo y **dependa del default** (sin `preprocess.json` propio). Quien ya creó `preprocess.json` con `"mode": "full"` no se ve afectado (su archivo gana por precedencia). Tampoco afecta a devs que nunca activaron el bloque.
- **Prefijo `$$` (decisión de plan-review):** se mantiene mapeando a `off` (no se cambia el código). Con el default ya en `off`, `$$` deja de tener efecto distintivo en estado base, pero **conserva su utilidad** por su precedencia máxima: tras `/preprocess full|fast` en la sesión, `$$` fuerza `off` en ese turno. La alterna de mapear `$$`→`fast` se descartó: la doc define `$$` como opt-out ("actúa directo sin eco/confirmación" = sin la maquinaria del hook = `off`, no `fast`). Documentado en §6/§11.

## Reporte de cierre

| Señal | Valor |
|---|---|
| Turnos total (Fases 1-7) | ~3 |
| Re-entregas | 0 |
| Complejidad estimada / real | baja / baja |
| Hallazgos de plan-review incorporados | 2 (`commands/preprocess.md` como 8ª sede; nota de semántica de `$$`) |

REQ cerrado: el hook `preprocess-prompt` arranca en modo `off` por defecto (neb v5.4.0). Se instala desde el template pero queda inerte hasta `/preprocess full|fast`. Coherencia del default en 10 sedes (2 código + 8 doc). El plan-review (qa-process-engineer + context-completeness-reviewer) atrapó la sede faltante `commands/preprocess.md` y la semántica de `$$` bajo el nuevo default (documentada, sin cambio de código). Gate version-sync verde (`VERSION`=`plugin.json`=5.4.0). Pendiente: `git push` (commits locales acumulados: ops-capture + REQ-1/2/3 + este).
