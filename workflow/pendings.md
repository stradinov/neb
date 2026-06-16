# pendings.md

Archivo global del dev con ítems de seguimiento que no bloquean el cierre pero requieren acción futura.

> **Backend migrado a `neb.db` (2026-06-15, REQ `neb-pendings-sqlite`).** Los pendientes viven en SQLite; el `pendings.md` plano quedó como puntero/histórico. Las secciones "Formato", "Asignación de IDs" y la numeración `NNN.` de abajo describen el **modelo plano deprecado** y se conservan solo como referencia del histórico — no se asignan números nuevos a mano. La creación/consulta va por el skill [`pendings-review`](../skills/pendings-review/SKILL.md) sobre `neb.db` (backend en [`../tooling/pendings.md`](../tooling/pendings.md)).
>
> **Cita canónica de un pendiente: su `[slug]`** (no `#NNN`). El número, si se usa, es el `id` de `neb.db` como `PD-<id>`. El `#NNN` del markdown histórico **no resuelve** contra `neb.db` (colisiona; numeración muerta). Contrato de resolución en [`../tooling/pendings.md`](../tooling/pendings.md) § "Cómo citar un pendiente".

## Path

```
~/.claude/pendings.md
```

Editar directamente sin pedir confirmación al dev

## Formato

```markdown
## <Proyecto>

1. **[nombre-req]** Descripción del ítem pendiente
2. **[nombre-req]** Descripción del ítem pendiente
```

Numerado. `[nombre-req]` identifica el requerimiento de origen.

## Asignación de IDs

Los IDs numerados son **globales al archivo** (no por sección de proyecto) y deben ser únicos. Antes de agregar un nuevo ítem, verificar el ID máximo actualmente en uso para evitar colisiones con ítems pre-existentes en otras secciones:

```bash
grep -oE '^[0-9]+\.' ~/.claude/pendings.md | sort -t. -k1 -n | tail -1
```

Asignar al nuevo ítem el **siguiente entero libre** (típicamente `máx + 1`, pero también vale cualquier hueco si el dev numera con saltos por convención).

**Por qué la regla**: el archivo se edita desde múltiples sesiones; una sesión que asume "voy por el siguiente número después del último que veo" colisiona con otra sección ya existente.

## Cuándo Claude lo escribe / lee

- **Escribe**: al cerrar sin confirmación de prod (ver [delivery.md](../process/delivery.md)) o ítems sin urgencia identificados durante el requerimiento.
- **Lee**: cuando el dev pide pendientes o al saludar (ver [communication.md](../general/communication.md)) — la consulta se sirve por el skill [`pendings-review`](../skills/pendings-review/SKILL.md) sobre `neb.db` (capa de valor: prioriza por banda + brújula `compas.md`), no leyendo el `.md` plano.

## Sección "Sesiones pausadas"

Heading dedicado en `pendings.md` para sesiones Claude nombradas con `/rename` cuando el dev anuncia pausa/continuación posterior. Permite recuperar el comando de reanudación sin que el dev recuerde el nombre.

Esto cubre **reanudar la propia sesión local** (mismo dev, misma máquina). Para **relevo cross-dev / cross-máquina** (otro dev continúa, u otra máquina) ver la [bitácora de relevo](logbook.md), que además registra sesiones automáticamente sin depender del anuncio de pausa.

Formato:

```markdown
## Sesiones pausadas

- **`<nombre-sesion>`** — <descripción del hilo, 1–2 líneas>. Reanudar: `claude --resume <nombre-sesion>`.
```

No numerado (los ítems numerados son pendientes accionables; estos son recuperables). Procedimiento completo en [`workflow/metrics.md`](metrics.md) §"Pausar y reanudar la misma sesión Claude".

**Cuándo Claude escribe**: al detectar el anuncio de pausa (ver [`general/communication.md`](../general/communication.md) §"Handoff de sesión").

**Cuándo Claude elimina**: al reanudar la sesión vía `--resume <nombre>` (paso 5 de §"Retomar una sesión interrumpida"), o si el dev anuncia descarte explícito.

**Ventana de 30 días**: si una sesión pausada no se reanuda en 30 días, Claude pregunta al dev antes de eliminar el ítem (no asume descarte implícito — el hilo puede seguir siendo útil).
