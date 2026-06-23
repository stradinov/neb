# Revisión editorial de `CONTRIBUTING.md` + 2ª evolución de la guía externa

**Estado:** Cerrado
**Fecha inicio:** 2026-06-23
**Fecha cierre:** 2026-06-23
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** bajo

## Contexto

2.º uso del flujo de `tooling/revision-editorial-externa.md`: el agente externo revisó `CONTRIBUTING.md`. Como en `promises.md`, alucinó rupturas de estructura — esta vez colapsó **todos** los saltos de línea del archivo (headings, párrafos, viñetas, blockquote) y omitió los emojis. Verificado contra el archivo real (intacto, L1-47) → structural-findings rechazados. Apliqué los anglicismos válidos + evolucioné la guía.

## Alcance

### Entra
- **`CONTRIBUTING.md`**: bumps→incrementos, gap→brecha, triage/triar/tría→clasificar/clasificación, transcripts→transcripciones, naming→convención de nombres, "imports relativos"→"`@imports` relativos", ownership→propiedad; `self-applied`→código (×2); corte de la promesa futura de `CODE_OF_CONDUCT.md`.
- **`tooling/revision-editorial-externa.md`**: allowlist ampliada (bump→incremento, gap→brecha, triage/triar/tría→clasificar/clasificación, transcripts→transcripciones, naming→convención de nombres, ownership→propiedad); lección de estructura reforzada (colapso de saltos de línea en todo el archivo, no solo tablas); queda `done` como único caso a decidir repo-wide.
- Patch `5.8.1 → 5.8.2` + `changelog.d/5.8.2.md` + `VERSION` + `plugin.json`.

### No entra
- Estructura alucinada (parte estructural de H1-H8): **rechazada** — `CONTRIBUTING.md` está intacto (verificado).
- Renombrar el heading § "Ownership de archivos `.md`" de `change-control-policy.md`: follow-up (cambia su anchor; doc agent-normativo fuera del pase editorial). El dev decidió traducir `ownership` (no era exceso aceptable).

## Plan de pruebas

- [x] Verificado contra el archivo real: `CONTRIBUTING.md` estructuralmente intacto → structural-findings rechazados.
- [x] Emojis 🐞/💡 preservados; canónicos/identifiers/paths intactos.
- [x] `assemble-changelog.py --check` verde con 5.8.2; `VERSION` == `plugin.json`; scan de términos vetados limpio.

## Trazabilidad

- **Commits:** esta confirmación.
- **Pendientes generados:** `done` como decisión repo-wide; renombrar § "Ownership de archivos `.md`" de `change-control-policy.md` (anchor) para alinear con la prosa traducida en `CONTRIBUTING.md`.

## Reporte de cierre

2.º ciclo del flujo de revisión externa: el gate de verificación volvió a atrapar la alucinación de estructura (ahora en todo el archivo). La lección quedó reforzada en la guía. Anglicismos aplicados gated.
