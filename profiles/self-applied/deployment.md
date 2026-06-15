# Deployment (self-applied)

Cómo se "deploya" un cambio en un proyecto auto-aplicado, y cómo se valida.

## Deploy

0. Claude corre `py bootstrap/assemble-changelog.py --check`. Si retorna 1: `py bootstrap/assemble-changelog.py`, `git add CHANGELOG.md`, commit como commit final del REQ.
1. `git commit` + `git push` al remote. Profile `self-applied` produce casi exclusivamente `.md`: por `methodology/change-control-policy.md` § "Ownership de archivos `.md`" (operaciones git en `process/version-control.md`), commits y pushes `.md`-only son autónomos. Para commits/pushes mixtos `.md` + código (ej. `bootstrap/*.py`, `bootstrap/*.sh`), aplica el gate de OK del componente de código.
2. `git pull` en cada proyecto cliente que importe la metodología vía `@~/.claude/neb/...`.

No hay servidor QA ni producción tradicional. La metodología aplica desde el momento en que un dev hace pull en un proyecto cliente.

## Ambiente único: prueba = producción

A diferencia de un proyecto de software, en un proyecto de proceso **no existe ambiente QA separado**. Las sesiones donde se aplica el lineamiento son simultáneamente:

- **Ambiente de pruebas** — la fricción real solo aparece al usar el lineamiento.
- **Ambiente de producción** — cada sesión es aplicación efectiva del proceso, no simulacro.

Por eso la validación al entregar se apoya en lo verificable sin uso (revisión de roles + coherencia + dogfooding en la misma sesión), y la fricción que solo aparece al aplicar el lineamiento en otra sesión se trata como **retroalimentación de Fase 9**, no como un gate que difiera el cierre.

## Validación

El entregable de `self-applied` (lineamientos `.md`) se valida **al entregar**, con mecanismos verificables — no se difiere a un conteo de sesiones:

- **Revisión de roles** — `qa-process-engineer` (coherencia entre archivos, vocabulario canónico, verificabilidad) + `context-completeness-reviewer` (suposiciones), en plan-review (Fase 3) y el gate de pre-entrega (Fase 7). Ver [roles.md](roles.md) y [`../../process/plan-review.md`](../../process/plan-review.md).
- **Coherencia estática** — `py bootstrap/assemble-changelog.py --check`, enlaces/anclas e imports vigentes, el principio "coherencia global sobre cambio mínimo" ([`../../methodology/principles.md`](../../methodology/principles.md)).
- **Dogfooding en la misma sesión** — por la reflexividad del profile, editar la metodología es aplicarla: cuando el cambio se ejerce en la sesión que lo edita, se observa en vivo.
- **Ejecutable** (si el cambio toca hooks/scripts) — prueba directa / dry-run del artefacto.

Con eso el REQ **cierra de inmediato** (sin esperar N sesiones). La observación posterior en uso real (un lineamiento que estorba o no quedó claro al aplicarse en otro profile) es **retroalimentación de Fase 9**, no un gate de cierre.

> Por qué no un conteo de sesiones: "≥N sesiones sin reporte negativo" no es un criterio formal sino un proxy de su ausencia — no es falsable, no tiene instrumentación que lo corrobore y produce REQs en limbo "En validación". La validación verificable al entregar sí se corrobora una vez; la señal-en-uso pertenece a Fase 9, que sí está instrumentada (disparadores en [`../../process/improvement.md`](../../process/improvement.md)).

## Entrega temprana del registro (relevo cross-dev)

El **registro del requerimiento** (change MD — ver [`../../methodology/vocabulary.md`](../../methodology/vocabulary.md) § "Registro del requerimiento") puede confirmarse y **entregarse** (`git push`) desde que existe el draft (entrada a Fase 4), independiente del cierre del entregable. Es autónomo: el delta es solo `.md` y aplica el ownership (ver [`../../methodology/change-control-policy.md`](../../methodology/change-control-policy.md) § "Ownership de archivos `.md`"); no requiere OK del dev.

**Cuándo**: cuando el **entorno es compartido** — señal determinista desde el backend central del logbook (`NEB_LOGBOOK_ENDPOINT` + opt-in `<!-- neb-logbook: central -->`; ver [`../../workflow/logbook.md`](../../workflow/logbook.md)): el `work` se publica a la bitácora compartida y su registro debe estar **entregado** para que el puntero resuelva en la máquina que releva. Si el entorno no es compartido, el registro se entrega en el cierre del REQ (que ya no se difiere).

## Cuando el dev pausa esperando otra sesión paralela

Cuando el dev declara que pausa el REQ esperando que otra sesión cierre (commit + push), el turno de Claude incluye el siguiente comando listo para correr:

```sh
bash bootstrap/wait-for-other-session.sh &
```

> En Windows requiere Git Bash o WSL2 (no PowerShell nativo). Claude usa el parámetro `run_in_background` del Bash tool al correrlo; el `&` aplica si el dev lo corre directo en su terminal.

El script polea `git fetch` + working dir limpio cada 60 s. Al detectar que la condición se cumple (exit 0), Claude notifica al dev y presenta el estado del REQ pausado para que el dev confirme la reanudación. El push de la otra sesión no implica que el REQ activo de esta sesión esté listo para continuar automáticamente — siempre requiere OK explícito del dev.

Timeout default: 8 h (configurable con `--timeout <sec>`). Si expira (exit 124), Claude notifica al dev para que decida.

Ver también [`../../process/version-control.md`](../../process/version-control.md) § Push.

## Si surge fricción

El dev reporta inline en sesión ("este lineamiento estorba en X" / "no quedó claro qué hacer cuando Y"):

- Si rompe un proceso existente → tratar como **incidencia en producción** (ver [`../../general/incidents.md`](../../general/incidents.md)).
- Si es refinamiento del lineamiento → entra a Fase 9 (ver [`../../process/improvement.md`](../../process/improvement.md)) como ajuste posterior.

## Lo que NO hace Claude

- Cerrar el REQ sin la validación al entregar (roles + coherencia; ejecutable si toca código).
- Asumir que un proyecto cliente "ya tiró pull" — el dev confirma el deploy real.
