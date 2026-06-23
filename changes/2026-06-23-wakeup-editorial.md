# Revisión editorial de `commands/wakeup.md` + decisión de barrido terminológico

**Estado:** Cerrado
**Fecha inicio:** 2026-06-23
**Fecha cierre:** 2026-06-23
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** bajo

## Contexto

4.º uso del flujo de revisión externa, **1.º con la guía endurecida (v5.9.0)**. El agente **no reportó estructura** —validó 5.9.0—: *"No reporté saltos de línea… porque el briefing los declara fuera de alcance"*. 5 hallazgos de vocabulario; 4 términos resultaron pervasivos → barrido repo-wide.

## Alcance

### Entra
- **`commands/wakeup.md`**: customizable→personalizable (alinea `principles.md`), fallback→ruta de reserva (+ precisión "una instalación reciente"), re-detectes→repitas la detección, config→configuración, refiriendo→remitiendo.
- **`tooling/revision-editorial-externa.md`**: allowlist += esos términos + el mapeo canónico de `workspace`/`opt-in`/`tour`/`dry-run` + regla anti-prefijo `re-`; conserve += excepciones del barrido (`NEB_WORKSPACE`, `setup-workspace.sh`, flag `--dry-run`).
- Patch `5.9.0 → 5.9.1` + `changelog.d/5.9.1.md` + `VERSION` + `plugin.json`.

### No entra — diferido a REQ de barrido repo-wide
- `workspace` (≈33×/7 docs vivos), `opt-in` (≈30×/20 docs), `tour` (≈25×/8 docs; nombre del feature `/wakeup`), `dry-run` (prosa; el flag `--dry-run` se conserva). El dev decidió **traducir los 4**, pero son pervasivos → se ejecutan como **REQ de barrido aparte** para no romper la consistencia cross-doc. Mapeo canónico + excepciones quedan en la guía.

## Plan de pruebas

- [x] **5.9.0 validado en uso:** el agente externo no reportó ningún hallazgo de estructura.
- [x] `assemble-changelog.py --check` verde con 5.9.1; `VERSION` == `plugin.json`; scan de términos vetados limpio.

## Trazabilidad

- **Commits:** esta confirmación.
- **Pendientes generados:** **REQ de barrido terminológico repo-wide** (`workspace`/`opt-in`/`tour`/`dry-run`); mapeo y excepciones de conservación ya en `tooling/revision-editorial-externa.md`.

## Reporte de cierre

1.ª validación en uso de la guía endurecida 5.9.0: exitosa (cero falsos positivos de estructura). El barrido de los 4 términos pervasivos se separa como REQ por su alcance (~30 docs + identifiers/filenames a preservar).
