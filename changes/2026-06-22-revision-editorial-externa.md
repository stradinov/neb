# Guía de revisión editorial por agentes externos (`tooling/`)

**Estado:** Cerrado
**Fecha inicio:** 2026-06-22
**Fecha cierre:** 2026-06-22
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** bajo  <!-- nuevo recurso opt-in en tooling/; no toca el flujo ni imports -->

## Contexto

El kit para usar un agente LLM externo (ChatGPT u otro) como consultor editorial vivía solo en la memoria del dev. Se materializa como **recurso visible y versionado** en el repo, enriquecido con las **lecciones aprendidas** del primer pase editorial (v5.5.1–5.6.0).

## Alcance

### Entra
- **`tooling/revision-editorial-externa.md`** (nuevo): **briefing dirigido al agente externo** (2ª persona; absorbe el prompt inicial). Define rol, reglas de la revisión, contrato `[ACTUAL]`/`[PROPUESTO]` con banderas, qué revisar, allowlist de anglicismos + protecciones, lecciones aprendidas, **norma de evolución** (Claude lo enriquece según hallazgos aceptados/rechazados) y una sección "Para el maintainer". **Referencia (no duplica)** `general/communication.md § "Idioma"`, `methodology/principles.md`, `methodology/vocabulary.md` y `tooling/redaccion-es.md`.
- Registro en `tooling/index.md` (ítem 6).
- Minor `5.7.0 → 5.8.0` + `changelog.d/5.8.0.md` + `VERSION` + `plugin.json` (sync).
- La memoria del dev (`reference_chatgpt_editorial_neb.md`) queda como **puntero** a esta guía + estado del pase.

### No entra
- Duplicar políticas (idioma, doctrina editorial, vocabulario): solo se referencian.
- Formalizar al agente externo como subagente/rol in-repo (sigue siendo consultor ad-hoc manual; decisión de REQ-3 del roadmap).

## Plan de pruebas

- [x] Sede correcta por el test de pertenencia: `tooling/` = recurso opt-in (sibling de `redaccion-es.md`).
- [x] Registrado en `tooling/index.md`; enlaces relativos resuelven.
- [x] `assemble-changelog.py --check` verde con 5.8.0; `VERSION` == `plugin.json`; scan de términos vetados limpio.

## Trazabilidad

- **Plan aprobado:** conversacional (menú); complejidad baja.
- **Commits:** esta confirmación.
- **Pendientes generados:** ninguno.

## Reporte de cierre

Guía de revisión editorial por agentes externos materializada en `tooling/` (5.8.0), con las lecciones del primer pase. La memoria queda como puntero.
