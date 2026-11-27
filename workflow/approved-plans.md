# Planes aprobados

En complejidad media/alta, el plan aprobado se guarda como archivo versionado en el repo del proyecto, junto al Change MD que registra su REQ. Viaja por git con el registro, así que llega a la máquina que releva.

## Path

```
<proyecto>/changes/plans/<YYYY-MM-DD>-<nombre>.md
```

- Mismo nombre de archivo que el Change MD del REQ ([changes.md](changes.md) § "Path"): el `<nombre>` enlaza plan y registro en los dos sentidos ([traceability.md](traceability.md)).
- El campo `**Plan aprobado:**` del Change MD lleva esa ruta desde la raíz del repo, en formato código: `changes/plans/<YYYY-MM-DD>-<nombre>.md`.

**Lugar de caída.** El hook `save-approved-plan` corre antes de que exista el Change MD y no conoce el repo; deja el plan en una carpeta global, no versionada, que sirve solo de tránsito:

```
<datos>/approved-plans/<YYYYMMDD-HHMMSS>-<proyecto>-<slug>.md
```

- `<datos>` es la carpeta de datos de Neb: `NEB_DATA` si es una ruta absoluta; si no, `~/.neb`. Ruta exacta: `neb_paths.py path approved-plans` (`hooks/lib/`). Hasta 7.x el lugar de caída era `~/.claude/approved-plans/`; lo que quede ahí lo muda la migración 8.0.0.
- `<proyecto>` = último segmento del cwd; cada `<>:"|?*` → `-`, sin `-` en los extremos; `unknown` si queda vacío.
- `<slug>` = primera línea del plan, normalizada: sin `#` ni espacios al inicio, minúsculas, sin acentos (`ñ` → `n`), cada tramo que no sea `a-z0-9` → `-`, máx 50 chars, `plan` si queda vacío (criterio de `slugify` en `hooks/lib/approved_plan.py`).

## Contenido

Formato: ver [`templates/approved-plan.md.template`](../templates/approved-plan.md.template) — header (`Proyecto` / `Sesión`) + plan literal. El archivo del repo no lleva la línea `**CWD:**` que escribe el hook: es una ruta absoluta de la máquina del dev.

El plan trae la sección obligatoria `## Plan de pruebas` ([`process/planning.md`](../process/planning.md) § "Estimación, plan y plan de pruebas") y, antes de su primera sección, la línea `**Plan-review:**` ([`process/plan-review.md`](../process/plan-review.md) § "Flujo", paso 4). Las dos van en el plan que el dev aprueba, no en el header que escribe el hook.

## Ciclo de vida

| Momento | Acción |
|---|---|
| Aprobación | Claude deja el plan en `changes/plans/` (§ "Vías de persistencia"), crea el Change MD y confirma el plan con commit local **antes de la primera confirmación del entregable**; el Change MD sigue [changes.md](changes.md) § "Ciclo de vida del draft" |
| Re-aprobación | Commit nuevo sobre el mismo archivo. La versión anterior queda en el historial de git y rige el último plan aprobado |
| Entrega | Con el mismo ciclo y los mismos gates que su registro ([changes.md](changes.md) § "Ciclo de vida del draft"), incluida la entrega inmediata al relevar |

Entre aprobaciones el archivo no se edita: un cambio de plan es una aprobación nueva. Los desvíos menores van en el Change MD (`## Plan de elaboración` y `## Incidencias`).

## Vías de persistencia

Las dos vías dejan el **mismo archivo** en el repo; difieren en disparo y en quién escribe primero:

| Vía | Disparo | Cómo llega al repo | Anuncio | Niveles |
|---|---|---|---|---|
| **Plan mode** | `ExitPlanMode` | Si el hook `save-approved-plan` está activado, deja el plan en el lugar de caída; al crear el Change MD, Claude lo mueve a `changes/plans/`, le quita `**CWD:**` y borra la copia del lugar de caída. Si el hook no dejó archivo, Claude lo escribe directo en el repo | 1 línea | los que entren a plan mode |
| **Conversacional** | Aprobación explícita en chat ("¿De acuerdo con este plan?" → sí), **sin** plan mode | Claude lo escribe directo en el repo | 1 línea | media/alta |

### Persistencia conversacional (sin plan mode)

Cuando un plan de complejidad **media/alta** se aprueba en conversación (sin pasar por plan mode), Claude escribe el archivo en `changes/plans/` con el mismo formato:

- `**Sesión:**` = `unknown` si no hay `session_id` disponible (igual que el hook `save-approved-plan`).
- El anuncio es una línea: `Plan persistido: changes/plans/<archivo>`.

Casos borde:

- **No-duplicación**: antes de escribir el plan (tras `ExitPlanMode`, o ante duda tras una compactación), Claude busca primero `changes/plans/<YYYY-MM-DD>-<nombre>.md` en el repo y después, en el lugar de caída, un archivo creado después de la aprobación. Mientras dure la transición a 8.0.0 (hasta 9.0.0) busca también en `~/.claude/approved-plans/`: una sesión abierta con la versión anterior sigue escribiendo ahí hasta reiniciarse. Si está en el repo, no se duplica. Si está en el lugar de caída (en cualquiera de las dos rutas), el hook ya guardó (supuesto R2 de [`platform-assumptions.md`](../methodology/platform-assumptions.md): el hook termina de escribir antes de que Claude siga) y Claude lo mueve. Si no está en ninguno, Claude lo escribe en el repo.
- **Sin repo** (el proyecto no usa control de versiones): el plan queda en `changes/plans/` del proyecto, sin commit.

Niveles **baja / trivial / no-formal** no persisten artefacto (ver [`process/planning.md`](../process/planning.md) § "Cuándo aplica cada aprobación").

## Configuración del hook

El plugin registra el hook `save-approved-plan`, de **activación voluntaria**: corre si está en `NEB_PROJECT_HOOKS` (`env` del `settings.json` versionado del proyecto; base en `settings.template.json`) o en `NEB_HOOKS` (personal). Detalle en [hooks/README.md](../hooks/README.md) § "Bajo el plugin de Neb". El hook guarda solo planes aprobados **vía plan mode** (`PostToolUse` solo dispara al éxito de `ExitPlanMode`) — es una de las dos vías; la otra es la persistencia conversacional de arriba.

No es sustituto de la memoria del proyecto ni del Change MD.
