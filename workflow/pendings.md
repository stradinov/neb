# Pendientes

Ítems de seguimiento del dev que no bloquean el cierre de un REQ pero piden acción futura. Viven en `neb.db` (`~/.claude/neb.db`), junto con las sesiones pausadas (§ "Sesiones pausadas").

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

Una sesión Claude nombrada con `/rename` (supuesto R10 de [`platform-assumptions.md`](../methodology/platform-assumptions.md)) que el dev pausa para continuar después se registra en `neb.db` como pendiente de tipo `session`. Permite recuperar el comando de reanudación sin que el dev recuerde el nombre. Es un pendiente más: se cita, se cura y se consulta como los demás (§ "Dónde viven y cómo se citan").

Esto cubre **reanudar la propia sesión local** (misma máquina); la [bitácora de relevo](logbook.md) además registra las sesiones de esta máquina sin depender del anuncio de pausa. Para continuar en otra máquina, o para que otro dev continúe, el relevo va por git: el `## Relevo` del Change MD ([`changes.md`](changes.md) § "Relevo").

Alta (el `[<slug>]` es el del pendiente, como en el alta de una tarea):

```
PD create session "[<slug>] Sesión pausada <nombre-sesion>: <descripción del hilo, 1–2 líneas>. Reanudar: claude --resume <nombre-sesion>"
```

Si el trabajo de la sesión ya tiene un pendiente abierto —el que cita su Change MD o su `active_*.md`, o uno creado con `recordar-sesion` del skill `pendings-review`—, la pausa se anota en ese pendiente (`PD note <id> "<mismo texto>"`) y no se crea otro. La cita del pendiente (`[slug]` y `PD-<id>`) va en la confirmación al dev; con ella se localiza al reanudar.

Los comandos de reanudación viven en [`process/execution.md`](../process/execution.md) § "Pausar y reanudar la misma sesión Claude".

**Cuándo Claude escribe**: al detectar el anuncio de pausa (ver [`general/communication.md`](../general/communication.md) § "Handoff de sesión").

**Cuándo Claude lo archiva**: al reanudar la sesión pausada, por `--resume` o desde la app (paso 5 de [`process/execution.md`](../process/execution.md) § "Retomar una sesión interrumpida"), con `PD archive <id> resolved-otherwise`; o si el dev anuncia descarte explícito, con `PD archive <id> no-longer-applies`. Una pausa anotada en un pendiente existente no lo archiva: Claude anota ahí la reanudación o el descarte.
