# Eliminar la política transversal de modelos (`general/models.md`)

**Estado:** En validación
**Fecha inicio:** 2026-06-25
**Fecha cierre:** —
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** medio  <!-- elimina un archivo importado por startup.md; el gate assemble-startup --check protege contra import roto -->

## Contexto

El dev concluyó que, **dado que el agente del loop principal no puede conmutar su propio modelo** a mitad de sesión (lo fija el dev con `/model` o la configuración de sesión; no hay tool del agente para cambiarlo), una política transversal always-on que prometa "selección de modelo según contexto" no aporta lineamiento accionable por el agente. La elección de modelo es responsabilidad del dev y vive en su configuración de Claude Code (`~/.claude/settings.json`), fuera de la metodología.

Decisión: **eliminar `general/models.md`** y depurar todas sus referencias, en vez de reescribirla. Sustituye al REQ previo de reescritura ([`2026-06-25-models-lock-in-customizacion.md`] — revertido sin commitear) y al pendiente de materialización de v5.11.0.

## Alcance

### Entra

1. **Borrar** `general/models.md`.
2. **`general/startup.md`** — quitar la directiva `@models.md`.
3. **`general/index.md`** — quitar el ítem "Models" de las transversales al arranque.
4. **`methodology/principles.md`** — sacar `models.md` de las políticas canónicas (§ "Fases vs políticas") y de los puntos de customización (§ "Puntos de customización", líneas de lista + estado de materialización).
5. **`methodology/promises.md`** — quitar "modelos" de las perillas de la promesa 5.
6. **`process/execution.md`** — borrar la línea "Selección de modelo en plan mode: ver models.md".
7. **`tooling/revision-editorial-externa.md`** — quitar `models` del set "No revises" `general/{startup,models,profile-detection,…}` (referencia colgante por brace-expansion, cazada en plan-review).
8. **`changes/2026-06-25-puntos-customizacion-sync.md`** — anotar el pendiente como superado.
9. **Versionado** — `VERSION` 5.11.0→6.0.0; `.claude-plugin/plugin.json` version→6.0.0 (gate pre-push exige paridad); `changelog.d/6.0.0.md`; regenerar `CHANGELOG.md`.

### No entra

- Tocar `methodology/principles.md:90` (anti-patrón "cambiar/restaurar modelo") — es un principio general válido, no referencia el archivo eliminado.
- Tocar `process/version-control.md` ("comandos de entrega siguen el modelo del contexto activo"), métricas de costo por modelo (`workflow/metrics.md`, `process/improvement.md`), ni la config de modelo de hooks (`tooling/`, `hooks/`) — son telemetría/mecánica, independientes de la política eliminada.
- La configuración personal de modelo del dev (settings.json) — fuera del repo.

## Plan de pruebas

- [x] `general/models.md` no existe.
- [x] `general/startup.md` ya no contiene `@models.md`; `py bootstrap/assemble-startup.py --check general/startup.md` reporta cadena de imports íntegra.
- [x] Sweep ampliado de referencias colgantes (no solo `"models.md"`, también `\bmodels\b` por brace-expansion): `grep -rn -e "models\.md" -e "@models" -e "\bmodels\b"` en `*.md`/`*.py`/`*.sh`/`*.json` — sin referencias vivas fuera de los change MDs históricos y el changelog. (El plan-review cazó una sobreviviente en `tooling/revision-editorial-externa.md:64` escrita como `models`; corregida.)
- [x] Sin consumidores de la política en hooks/bootstrap/templates: `grep models` en `*.py`/`*.sh`/`*.json` sin coincidencias relevantes (el ensamblador resuelve imports solo por directiva `@<path>`, no por enumeración de directorio — un archivo huérfano no rompe nada).
- [x] `principles.md` lista solo `communication.md` como política canónica; la lista de puntos de customización ya no incluye models y no declara pendientes.
- [x] `py bootstrap/assemble-changelog.py --check` verde con el fragment 6.0.0.

## Clasificación SemVer

**Major** (5.11.0 → 6.0.0): elimina un archivo importado (`@models.md` en `startup.md`) — ruptura de import / cambio incompatible del kernel por `CLAUDE.md` § "Versionado SemVer".

## Trazabilidad

- **Plan aprobado:** conversacional; el dev eligió "Eliminarlo (Major)" tras ver el impacto (rompe `@import`, 5+ referencias) y aprobó el plan de ejecución.
- **Commits:** esta confirmación (repo `neb`).
- **Pendientes generados:** ninguno. (Supera el pendiente de materialización de v5.11.0 y reemplaza el REQ de reescritura revertido.)

## Reporte de cierre

<!-- usage-tracker-start -->
| Modelo | Tokens (in · out · cache_w · cache_r) | Costo USD |
|---|---|---|
| — | — | — |
| **Total** | — | **—** |
<!-- usage-tracker-end -->
