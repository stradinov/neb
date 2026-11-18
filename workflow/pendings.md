# Pendientes

Ítems de seguimiento del dev que no bloquean el cierre de un REQ pero piden acción futura. Viven en `neb.db` (`~/.claude/neb.db`). El archivo plano `~/.claude/pendings.md` ya no lleva pendientes: conserva § "Sesiones pausadas" y los avisos que un mecanismo del adoptante le anexe.

## Dónde viven y cómo se citan

- **Backend:** tabla `pending` de `neb.db`, operada por `hooks/lib/pendings.py` (detalle en [`../tooling/pendings.md`](../tooling/pendings.md)).
- **Alta:** `PD create task "[<slug>] <contexto>"`, sin pedir confirmación al dev. `PD` es `hooks/lib/pendings.py` del núcleo en uso; el skill `pendings-review` trae la forma de resolverlo desde cualquier proyecto.
- **Consulta:** la del dev se sirve por el skill [`pendings-review`](../skills/pendings-review/SKILL.md), que prioriza por banda y por la brújula `compas.md`; el `list` del CLI es acceso de bajo nivel.
- **Cita canónica:** el `[slug]` del pendiente y, si se necesita el número, el `id` de `neb.db` como `PD-<id>`; nunca `#NNN`. Contrato de resolución en [`../tooling/pendings.md`](../tooling/pendings.md) § "Cómo citar un pendiente".
- **Clasificación:** cada pendiente curado lleva un cliente y un tópico, decididos por el dev; la banda curada manda sobre la brújula. Ver [`../tooling/pendings.md`](../tooling/pendings.md) § "Ejes curados".

## Cuándo Claude lo escribe / lee

- **Escribe**: al cerrar sin confirmación de prod (ver [delivery.md](../process/delivery.md)) o ítems sin urgencia identificados durante el requerimiento.
- **Lee**: cuando el dev pide pendientes o al saludar (ver [communication.md](../general/communication.md)), por el skill `pendings-review`.

## Sesiones pausadas

Sección `## Sesiones pausadas` de `~/.claude/pendings.md` para sesiones Claude nombradas con `/rename` (supuesto R10 de [`platform-assumptions.md`](../methodology/platform-assumptions.md)) cuando el dev anuncia pausa/continuación posterior. Permite recuperar el comando de reanudación sin que el dev recuerde el nombre.

Esto cubre **reanudar la propia sesión local** (mismo dev, misma máquina). Para **relevo cross-dev / cross-máquina** (otro dev continúa, u otra máquina) ver la [bitácora de relevo](logbook.md), que además registra sesiones automáticamente sin depender del anuncio de pausa.

Formato:

```markdown
## Sesiones pausadas

- **`<nombre-sesion>`** — <descripción del hilo, 1–2 líneas>. Reanudar: `claude --resume <nombre-sesion>`.
```

Claude edita la sección sin pedir confirmación al dev. Procedimiento completo en [`process/execution.md`](../process/execution.md) § "Pausar y reanudar la misma sesión Claude".

**Cuándo Claude escribe**: al detectar el anuncio de pausa (ver [`general/communication.md`](../general/communication.md) § "Handoff de sesión").

**Cuándo Claude elimina**: al reanudar la sesión vía `--resume <nombre>` (paso 5 de [`process/execution.md`](../process/execution.md) § "Retomar una sesión interrumpida"), o si el dev anuncia descarte explícito.

**Ventana de 30 días**: si una sesión pausada no se reanuda en 30 días, Claude pregunta al dev antes de eliminar el ítem (no asume descarte implícito — el hilo puede seguir siendo útil).
