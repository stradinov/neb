# Endurecer la guía de revisión externa contra la alucinación de estructura

**Estado:** Cerrado
**Fecha inicio:** 2026-06-23
**Fecha cierre:** 2026-06-23
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** bajo

## Contexto

El agente externo (ChatGPT) reincidió en reportar "rupturas de estructura" inexistentes —colapsa los saltos de línea de todo el archivo— en `promises.md` y `CONTRIBUTING.md`, pese a la lección en prosa agregada en 5.8.1–5.8.2. Diagnóstico (con el dev):

- La lección sola no basta: el agente **no detecta** su propio colapso de saltos.
- Causa mecánica: lee la **vista renderizada** de GitHub, no el crudo.
- **Nunca releía la guía** —trabajaba con la copia del briefing inicial—, así que las lecciones/allowlist agregadas a media sesión nunca lo alcanzaban (punto clave aportado por el dev).

## Alcance

### Entra
- **`tooling/revision-editorial-externa.md`** — 3 lineamientos:
  1. **Releer la guía en crudo antes de cada doc** (§ "Tu rol" + § "Reglas de la revisión" + prompt recurrente del § "Para el maintainer").
  2. **Lectura en crudo** (`raw.githubusercontent.com`) de la guía y del doc objetivo, no la vista renderizada.
  3. **Estructura/formato fuera de alcance** (regla dura en § "Reglas"); solo redacción. Lección de estructura reformulada.
- Minor `5.8.2 → 5.9.0` + `changelog.d/5.9.0.md` + `VERSION` + `plugin.json`.

### No entra
- Otros docs: este REQ solo toca la guía.

## Plan de pruebas

- [x] `assemble-changelog.py --check` verde con 5.9.0; `VERSION` == `plugin.json`; scan de términos vetados limpio.
- [ ] **Validación en uso:** el próximo doc revisado con la guía releída en crudo → el agente ya no reporta estructura (pendiente del siguiente ciclo; re-briefear ChatGPT con la guía nueva).

## Trazabilidad

- **Commits:** esta confirmación.
- **SemVer:** Minor (nuevos lineamientos en el flujo de revisión), no Patch.

## Reporte de cierre

La lección en prosa había fallado 2 veces. Se pasó de "pídele que se auto-vigile" a quitar la causa (lectura en crudo), cerrar el canal (releer la guía cada ciclo) y eliminar el modo de falla (estructura fuera de alcance). Validación real en el siguiente doc.
