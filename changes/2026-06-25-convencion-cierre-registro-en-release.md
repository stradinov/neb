# Convención: finalizar el registro del requerimiento dentro del commit del entregable

**Estado:** Cerrado
**Fecha inicio:** 2026-06-25
**Fecha cierre:** 2026-06-25
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** bajo  <!-- 2 ediciones de prosa/template; no toca código ni imports -->

## Contexto

Fase 9 del REQ [`2026-06-25-eliminar-models-policy.md`](2026-06-25-eliminar-models-policy.md) (v6.0.0). Al cerrar ese registro **después** de pushear su release, el commit de cierre (`.md`-only) chocó con el **Gate 3 del pre-push** (`hooks/pre-push-changelog`): todo archivo fuera de `changelog.d/`/`CHANGELOG.md`/`research/` cuenta como cambio normativo y exige un fragment en el mismo push; un cierre de `changes/` aislado no lo lleva → se requirió `git push --no-verify` (autorizado por el dev).

La fricción se evita con una convención **ya usada de facto** (p.ej. [`2026-06-25-puntos-customizacion-sync.md`](2026-06-25-puntos-customizacion-sync.md), que anota `**Commits:** esta confirmación`): finalizar el registro como `Cerrado` **dentro del mismo commit que entrega el entregable**, sin hash literal (que no existe al redactar). Estaba sin documentar.

## Alcance

### Entra

1. **[`workflow/changes.md`](../workflow/changes.md)** (§ "Ciclo de vida del draft", fila "Cierre") — documentar la convención.
2. **[`templates/change.md.template`](../templates/change.md.template)** (§ Trazabilidad, `**Commits:**`) — ofrecer `esta confirmación` como opción.
3. **Versionado** — `VERSION` 6.0.0→6.1.0; `.claude-plugin/plugin.json`→6.1.0; `changelog.d/6.1.0.md`; regenerar `CHANGELOG.md`.

### No entra

- **Modificar el Gate 3 del hook** para excluir `changes/` — más riesgoso (el hook es el único enforcement bloqueante) y la convención resuelve el caso común sin tocarlo. El `--no-verify` sigue disponible para cierres tardíos legítimos (entrega temprana en entorno compartido).

## Plan de pruebas

- [x] `workflow/changes.md` fila "Cierre" enuncia "mismo commit que el entregable" + `**Commits:** esta confirmación`.
- [x] `templates/change.md.template` ofrece `esta confirmación`.
- [x] Este mismo registro se cierra **dentro de su propio commit** con `**Commits:** esta confirmación` (prueba viva): el push pasa el pre-push **sin `--no-verify`** porque lleva su fragment `6.1.0`.
- [x] `py bootstrap/assemble-changelog.py --check` verde; `py bootstrap/assemble-startup.py --check` verde.

## Clasificación SemVer

**Minor** (6.0.0 → 6.1.0): promueve a regla escrita una práctica antes implícita (nuevo lineamiento) — por `methodology/principles.md` § "Declarar (nunca Patch)", no es Patch. No rompe imports.

## Trazabilidad

- **Plan aprobado:** conversacional (Fase 9 del REQ de models); el dev eligió "Documentarla ahora" y aprobó el plan.
- **Commits:** esta confirmación (repo `neb`).
- **Pendientes generados:** ninguno.

## Reporte de cierre

<!-- usage-tracker-start -->
| Modelo | Tokens (in · out · cache_w · cache_r) | Costo USD |
|---|---|---|
| — | — | — |
| **Total** | — | **—** |
<!-- usage-tracker-end -->
