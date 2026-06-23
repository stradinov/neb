# Revisión editorial de `promises.md` + 1ª evolución de la guía externa

**Estado:** Cerrado
**Fecha inicio:** 2026-06-23
**Fecha cierre:** 2026-06-23
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** bajo  <!-- redacción en docs + refinamiento de un recurso opt-in -->

## Contexto

Primer uso del flujo de `tooling/revision-editorial-externa.md`: un agente externo (ChatGPT) revisó `methodology/promises.md` y devolvió hallazgos + la sección `PROPUESTAS PARA LA GUÍA`. Claude verificó cada `[ACTUAL]` contra el archivo real, aplicó el contenido gated, y **evolucionó la guía** con las propuestas aceptadas + lo aprendido.

## Alcance

### Entra
- **`methodology/promises.md`** — 8 correcciones de contenido: Customizable→Personalizable (alinea con `principles.md`), loop→ciclo, defaults→valores por defecto, customización→personalización, forkear→hacer fork, scaffolding→estructura base, extension points→puntos de extensión, always-on→siempre activas, "imports"→`@imports`, y corte de "(dogfooding)" redundante.
- **`tooling/revision-editorial-externa.md`** — evolución: allowlist ampliada; `trigger` + `@import`/`@imports` a "conservar"/protecciones; lección "no alucines estructura de tabla"; `done` anotado como decisión repo-wide.
- Patch `5.8.0 → 5.8.1` + `changelog.d/5.8.1.md` + `VERSION` + `plugin.json`.

### No entra
- **Hallazgos de estructura de tabla** (H1 + parte de H3/H4): **RECHAZADOS** — la tabla de `promises.md` está intacta (verificado L5-16: sin líneas en blanco ni fila partida); el agente los alucinó.
- **"done"→"terminado"**: no aplicado — término recurrente ligado a `done-criteria.md`; decisión repo-wide pendiente.

## Plan de pruebas

- [x] Verificado contra el archivo real: la tabla de `promises.md` está intacta → structural-findings rechazados (gate de verificación funcionó).
- [x] Anglicismos canónicos (`gate`/`profile`/`overlay`) y `trigger` intactos; identifiers/paths sin tocar.
- [x] `assemble-changelog.py --check` verde con 5.8.1; `VERSION` == `plugin.json`; scan de términos vetados limpio.

## Trazabilidad

- **Plan aprobado:** conversacional (menú); demostración del flujo de revisión externa.
- **Commits:** esta confirmación.
- **Pendientes generados:** `done`→`terminado` como posible barrido repo-wide (si se decide ampliar).

## Reporte de cierre

Primer ciclo completo del flujo de revisión editorial externa: hallazgos aplicados gated + guía auto-mejorada vía `PROPUESTAS PARA LA GUÍA`. El gate de verificación atrapó estructura de tabla alucinada — la lección quedó incorporada a la guía.
