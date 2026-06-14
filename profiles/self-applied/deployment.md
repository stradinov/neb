# Deployment (self-applied)

Cómo se "deploya" un cambio en un proyecto auto-aplicado, y cómo se valida en uso real.

## Deploy

0. Claude corre `py bootstrap/assemble-changelog.py --check`. Si retorna 1: `py bootstrap/assemble-changelog.py`, `git add CHANGELOG.md`, commit como commit final del REQ.
1. `git commit` + `git push` al remote. Profile `self-applied` produce casi exclusivamente `.md`: por `methodology/change-control-policy.md` § "Ownership de archivos `.md`" (operaciones git en `process/version-control.md`), commits y pushes `.md`-only son autónomos. Para commits/pushes mixtos `.md` + código (ej. `bootstrap/*.py`, `bootstrap/*.sh`), aplica el gate de OK del componente de código.
2. `git pull` en cada proyecto cliente que importe la metodología vía `@~/.claude/neb/...`.

No hay servidor QA ni producción tradicional. La metodología aplica desde el momento en que un dev hace pull en un proyecto cliente.

## Ambiente único: prueba = producción

A diferencia de un proyecto de software, en un proyecto de proceso **no existe ambiente QA separado**. Las sesiones donde se aplica el lineamiento son simultáneamente:

- **Ambiente de pruebas** — la fricción real solo aparece al usar el lineamiento.
- **Ambiente de producción** — cada sesión es aplicación efectiva del proceso, no simulacro.

Esta equivalencia es la razón por la que la validación es diferida en uso: no hay QA previo donde "subir" el cambio antes de exponerlo. El "deploy" coincide con la primera oportunidad de prueba — cuando el dev hace pull y aplica la metodología en su próxima sesión.

## Validación diferida en uso

Cuarto tipo de validación, complementa los 3 de [`process/delivery.md`](../../process/delivery.md) "Validación". Aplica a cualquier cambio en profile `self-applied`.

### Por qué diferida

Los walkthroughs mentales en Fase 5 detectan ambigüedad del diseño, no fricción real. La fricción aparece cuando el lineamiento se aplica en una sesión de trabajo en otro profile (cualquier profile de software o documentación). Solo el uso revela si el cambio ayuda, estorba o requiere ajuste.

El periodo entre cierre de Fase 4 y push abre una ventana de exposición a otras sesiones. Ver `process/version-control.md` § Push, bullet "Validación diferida" — Claude commitea localmente al cerrar Fase 4 aunque el push del **entregable** (el lineamiento) se difiera hasta el cierre.

La diferición aplica al **entregable**, no al **registro del requerimiento** (change MD — ver [`../../methodology/vocabulary.md`](../../methodology/vocabulary.md) § "Registro del requerimiento"); cuando el entorno de validación es compartido, el registro puede **entregarse temprano** (ver § "Entrega temprana del registro").

### Entrega temprana del registro

El **registro del requerimiento** (change MD — ver [`../../methodology/vocabulary.md`](../../methodology/vocabulary.md) § "Registro del requerimiento") puede confirmarse y **entregarse** (`git push`) tempranamente, desde que existe el draft (plan aprobado / entrada a Fase 4), **desacoplado** de la Entrega del entregable. Es autónomo: el delta es solo `.md` y aplica el ownership de `.md` (ver [`../../methodology/change-control-policy.md`](../../methodology/change-control-policy.md) § "Ownership de archivos `.md`"); no requiere OK del dev.

**Condición**: aplica cuando el **entorno de validación es compartido**, lo determina Claude. Señal determinista: el `work` se publica a una bitácora compartida (backend central — ver [`../../workflow/logbook.md`](../../workflow/logbook.md)) ⇒ entorno compartido; si la entrada de bitácora apunta al change MD para relevo cross-dev, el registro debe estar **entregado** para que el puntero resuelva en la máquina que releva. Si el entorno **no** es compartido (sesión solo del dev, sin bitácora compartida), el registro se confirma/entrega en el cierre (ver [`../../process/delivery.md`](../../process/delivery.md) § "Cierre del requerimiento").

La **validación diferida del entregable** se mantiene intacta: son `.md` distintos — el registro documenta *sobre* el REQ, el entregable es el lineamiento producido. El push del entregable sigue su gate de validación/cierre.

### Criterio de cierre

El requerimiento cierra cuando:

- **Aplicado en ≥ 10 sesiones de trabajo en otros profiles sin reporte negativo del dev**.

No hay cierre por calendario: el paso del tiempo sin uso no cierra el REQ.

### Tracking

Al cerrar el cambio en estado `Listo para aprobación`, agregar a `~/.claude/pendings.md` una entrada con tag `[<slug>-validacion-uso]`:

```
[ ] [<slug>-validacion-uso] <req> — validación diferida en uso (push <fecha>). Cierre tras ≥ 10 sesiones de trabajo en otros profiles sin reporte negativo. Change MD: <path>.
```

Se elimina cuando se cumple el criterio de cierre (≥ 10 sesiones sin reporte negativo). Al eliminarse, el estado del change MD pasa a `Cerrado` y se ejecuta el cierre atómico (commit + push del change MD — ver [`process/delivery.md`](../../process/delivery.md) § "Cierre del requerimiento"). En entorno compartido el push del registro pudo realizarse antes (entrega temprana, ver § "Entrega temprana del registro"); en ese caso, al cierre solo se confirma/entrega el delta restante.

### Cuando el dev pausa esperando otra sesión paralela

Cuando el dev declara que pausa el REQ esperando que otra sesión cierre (commit + push), el turno de Claude incluye el siguiente comando listo para correr:

```sh
bash bootstrap/wait-for-other-session.sh &
```

> En Windows requiere Git Bash o WSL2 (no PowerShell nativo). Claude usa el parámetro `run_in_background` del Bash tool al correrlo; el `&` aplica si el dev lo corre directo en su terminal.

El script polea `git fetch` + working dir limpio cada 60 s. Al detectar que la condición se cumple (exit 0), Claude notifica al dev y presenta el estado del REQ pausado para que el dev confirme la reanudación. El push de la otra sesión no implica que el REQ activo de esta sesión esté listo para continuar automáticamente — siempre requiere OK explícito del dev.

Timeout default: 8 h (configurable con `--timeout <sec>`). Si expira (exit 124), Claude notifica al dev para que decida.

Ver también `process/version-control.md` § Push, bullet «Validación diferida».

### Si surge fricción

El dev reporta inline en sesión ("este lineamiento estorba en X" / "no quedó claro qué hacer cuando Y"):

- Si rompe un proceso existente → tratar como **incidencia en producción** (ver [`general/incidents.md`](../../general/incidents.md)).
- Si es refinamiento del lineamiento → entra a Fase 9 (ver [`process/improvement.md`](../../process/improvement.md)) como ajuste posterior.

## Lo que NO hace Claude

- Push al remote del **entregable** (el lineamiento) **antes** del cierre del REQ (la validación diferida difiere ese push; al cierre, el push `.md`-only es autónomo — ver [`process/delivery.md`](../../process/delivery.md) § "Cierre del requerimiento" y `process/version-control.md` § Push). **Excepción — el registro del requerimiento (change MD)**: puede entregarse temprano si el entorno de validación es compartido (ver § "Entrega temprana del registro"); su push `.md`-only es autónomo y no arrastra el del entregable.
- Asumir que un proyecto cliente "ya tiró pull" — el dev confirma el deploy real.
- Cerrar el REQ antes del criterio de cierre (≥ 10 sesiones sin reporte negativo).
