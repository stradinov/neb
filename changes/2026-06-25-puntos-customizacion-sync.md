# Puntos de customización: canónica por diseño + estado de materialización

**Estado:** Cerrado
**Fecha inicio:** 2026-06-25
**Fecha cierre:** 2026-06-25
**Complejidad estimada:** baja
**Complejidad real:** media  <!-- el plan-review destapó una premisa falsa que recalibró el diseño -->
**Riesgo de regresión:** bajo  <!-- 3 ediciones de prosa/tabla; no toca código ni imports -->

## Contexto

Follow-up de Fase 9 del REQ [`2026-06-24-idioma-personalizable-niveles.md`](2026-06-24-idioma-personalizable-niveles.md) (v5.10.0). La retrospectiva detectó que los **puntos de customización** se enumeran en **3 sedes paralelas** desincronizadas.

**El plan-review (`qa-process-engineer`) refutó la premisa inicial** ("las 3 listas deben ser idénticas"): las sedes tienen **propósitos distintos** y `models.md` está **declarado customizable pero NO materializado** (sin bloque `> Punto de customización`) — el mismo gap que tenía `communication.md` antes de v5.10.0. Forzar igualdad literal habría listado `models` como materializado siendo falso.

## Diseño (recalibrado: "diseño vs materializado")

- **`principles.md § "Puntos de customización"` = lista canónica POR DISEÑO** (6: coding-standards, git-conventions, done-criteria, communication, models, personal-vs-team). Declara explícitamente el **estado de materialización**: materializados (coding/git/done/communication) vs **pendiente** (models).
- Las sedes que enumeran lo **materializado** —`promises.md` p5 celda, `personal-vs-team.md` preconfigurados— espejan el **subconjunto materializado**, no la lista por diseño. Así el gap (declarado sin materializar) queda **visible**, no oculto.

Esto resuelve además los 2 hallazgos del qa: la auto-omisión de `personal-vs-team` y la coexistencia prosa/celda en `promises.md` se explican por el reencuadre (la prosa de "Criterio verificable" describe conceptos por diseño —incluye modelos—; la celda describe lo materializado).

## Alcance

### Entra

1. **[`methodology/principles.md` § "Puntos de customización"](../methodology/principles.md)** — declarar canónica por diseño + estado de materialización (models = pendiente) + regla: al agregar un punto o materializar uno pendiente, sincroniza las sedes afectadas.
2. **[`methodology/promises.md`](../methodology/promises.md)** (promesa 5, celda "Dónde se materializa") — anotar "Materializado (subconjunto de principles.md)"; lista materializados (sin models). La prosa de "Criterio verificable" (conceptos por diseño, incluye modelos) se mantiene.
3. **[`methodology/personal-vs-team.md`](../methodology/personal-vs-team.md)** (preconfigurados) — anotar "subconjunto materializado"; lista materializados (sin models); path a principles.md corregido a idiomático.

### No entra

- **Materializar `models.md`** (agregarle su bloque) — queda como pendiente generado (mismo patrón que cerró communication en v5.10.0).
- DRY puro (enlace sin enumerar) y test automatizado — descartados (legibilidad / no atrapa omisiones).

## Plan de pruebas

| # | Verificación | Umbral binario | Resultado |
|---|---|---|---|
| 1 | principles.md declara canónica por diseño + estado de materialización | grep "por diseño" + "pendiente de materializar" + "models.md" en principles.md | ✅ |
| 2 | Sedes materializadas NO listan models (era el error) | `models` ausente de la celda promesa 5 y de personal-vs-team.md l.11 | ✅ |
| 3 | Sedes materializadas anotan "subconjunto"/"materializado" + enlazan a la canónica | grep "subconjunto" + "principles.md" en promises.md p5 y personal-vs-team.md | ✅ |
| 4 | Paths relativos correctos (intra-methodology sin `../`) | `[principles.md](principles.md)` en personal-vs-team.md | ✅ |
| 5 | Versionado | `bump-version.sh` 5.10.0→5.11.0; `changelog.d/5.11.0.md`; `assemble-changelog.py --check` verde | ✅ |

## Clasificación SemVer

**Minor** (5.10.0 → 5.11.0): nuevo lineamiento (canónica por diseño + estado de materialización + regla de sincronización) + corrección de la desincronía. No rompe imports.

## Trazabilidad

- **Plan aprobado:** plan-review (`qa-process-engineer`, escalado proporcional a 1 rol) refutó la premisa inicial; diseño recalibrado y aprobado por el dev.
- **Commits:** esta confirmación (repo `neb`).
- **Pendientes generados:** **materializar el bloque `> Punto de customización` en `general/models.md`** (declarado customizable por diseño, sin materializar) — mismo patrón que cerró `communication.md` en v5.10.0. **Superado (v6.0.0):** `models.md` fue **eliminado** (la política de modelos se retiró del kernel); la materialización ya no aplica. Ver [`2026-06-25-eliminar-models-policy.md`](2026-06-25-eliminar-models-policy.md).
