# Approved plans

Un plan aprobado puede persistirse como artefacto en `~/.claude/approved-plans/` por **dos vías**: el hook `save-approved-plan.sh` cuando se aprueba en plan mode (`ExitPlanMode`), o un `Write` de Claude cuando se aprueba conversacionalmente (ver § "Persistencia conversacional"). Bitácora cross-proyecto consultable entre sesiones.

## Path

```
~/.claude/approved-plans/<YYYYMMDD-HHMMSS>-<proyecto>-<slug>.md
```

- `<proyecto>` = `basename` del cwd.
- `<slug>` = primera línea del plan, normalizada (lowercase, espacios → guiones, máx 50 chars; criterio de `hooks/lib/slugify.sh`).
- Carpeta global, no versionada.

## Contenido

Formato: ver [`templates/approved-plan.md.template`](../templates/approved-plan.md.template) — header (`Proyecto` / `Sesión` / `CWD`) + plan literal.

## Vías de persistencia

Ambas vías producen el **mismo artefacto** (mismo path, naming y formato); difieren en disparo y alcance:

| Vía | Disparo | Escribe | Anuncio | Niveles | Conoce el Change MD |
|---|---|---|---|---|---|
| **Plan mode** | `ExitPlanMode` | hook `save-approved-plan.sh` (silencioso) | no | los que entren a plan mode | no (corre antes de que nazca el Change MD) |
| **Conversacional** | Aprobación explícita en chat ("¿De acuerdo con este plan?" → sí), **sin** plan mode | Claude vía `Write` | 1 línea | media/alta | sí |

### Persistencia conversacional (sin plan mode)

Cuando un plan de complejidad **media/alta** se aprueba en conversación (sin pasar por plan mode), el artefacto a producir es el mismo archivo `approved-plans/<YYYYMMDD-HHMMSS>-<proyecto>-<slug>.md` que generaría el hook. Convenciones de paridad:

- `**Sesión:**` = `unknown` si no hay `session_id` disponible (igual que el hook, `save-approved-plan.sh`).
- El anuncio es una línea: `Plan persistido: approved-plans/<archivo>`.
- Esta vía además llena el campo `**Plan aprobado:**` del Change MD con el path del archivo escrito (la vía conversacional sí conoce el Change MD; ver [traceability.md](traceability.md)).

Casos borde:

- **Re-aprobación** en la misma sesión: nuevo archivo por timestamp (igual que el hook genera uno por cada `ExitPlanMode`); el último es el vigente.
- **No-duplicación**: esta vía es exclusiva de la aprobación conversacional. Si el plan se aprobó vía `ExitPlanMode`, el hook ya guardó — no se duplica. Ante duda (p. ej. tras compactación), verificar inexistencia previa en `approved-plans/` antes de escribir.

Niveles **baja / trivial / no-formal** no persisten artefacto (ver [`process/planning.md`](../process/planning.md) § "Cuándo aplica cada aprobación").

## Configuración del hook

El hook `save-approved-plan` **no** se auto-registra por el plugin: es **opt-in por proyecto**, declarado en `settings.template.json` (base para el `settings.json` del proyecto). Detalle en [hooks/README.md](../hooks/README.md). (La configuración vía `bootstrap/link-into-project.sh` corresponde al modelo clone **deprecado**.) El hook guarda solo planes aprobados **vía plan mode** (`PostToolUse` solo dispara al éxito de `ExitPlanMode`) — es una de las dos vías; la otra es la persistencia conversacional de arriba.

No es sustituto de la memoria del proyecto ni del Change MD — es bitácora histórica complementaria.
