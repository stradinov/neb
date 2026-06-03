# Stack: self-applied

Proyectos auto-aplicados — la metodología que se edita es la que se aplica. Caso canónico: el propio repo `neb`.

## Por qué `self-applied` sin sufijo de dominio

El nombre rompe deliberadamente los patrones de naming del repo (`<adjetivo>-<dominio>` como `<lenguaje>-<framework>`; `*-authoring` como `skill-authoring`). El sustantivo de dominio se omite porque el stack cubre cualquier marco auto-aplicado — metodología pura (principios, vocabulario, ENUMs), proceso puro (fases, gates, comandos), artefactos (changes, pendings, plans) — y no se restringe a un dominio. Nombrarlo `self-applied-methodology` o `self-applied-process` reintroduciría la asimetría que el rename buscaba eliminar (ver [`methodology/principles.md`](../../methodology/principles.md)).

La 4ª categoría de naming "Stacks auto-aplicados / reflexivos" está documentada en [`methodology/stacks.md`](../../methodology/stacks.md).

## Características

- **Entregable**: archivos markdown que describen políticas, fases, artefactos, plantillas.
- **Sin código ejecutable** que requiera build, tests unitarios o servidor.
- **Ambiente único: prueba = producción** — no existe QA separado; las sesiones donde se aplica el lineamiento son simultáneamente ambiente de pruebas y de producción (ver [deployment.md](deployment.md) "Ambiente único").
- **Deploy**: `git push` al remote → `git pull` en proyectos cliente que importen vía `@~/.claude/neb/...`.
- **Validación**: diferida en uso (ver [deployment.md](deployment.md)). Los walkthroughs mentales en Fase 5 detectan ambigüedad del diseño; la fricción real aparece cuando el lineamiento se aplica en sesión de otro stack.
- **Reflexividad**: el repo importa su propio `CLAUDE.md`, lo que hace que Claude trabaje sobre la metodología que aplica.

## Antes de proponer ubicación de archivos

Cualquier archivo nuevo o relocalización en el repo deriva su path de la clasificación Metodología / Proceso / Mixto. Consultar [`../../methodology/principles.md`](../../methodology/principles.md) antes de proponer ubicación en Fases 1–3 (ver bullet en [`../../process/planning.md`](../../process/planning.md) § "Insumos de contexto"). El gate aplica a creación, movimiento y rename — no a ediciones in-place.

## Detección

Heurística: el repo contiene `methodology/principles.md`, `process/plan-review.md` y `general/index.md` con fases canónicas. Hoy aplica al propio repo `neb`; podría extenderse a otros proyectos auto-aplicados futuros (fork de la metodología, metodología hermana con misma propiedad reflexiva).

## Glosario del stack

Concretización del [vocabulario abstracto](../../methodology/vocabulary.md) de la metodología para proyectos auto-aplicados:

| Término abstracto | En este stack |
|---|---|
| Entregable / elaboración | Archivos markdown de políticas, fases, artefactos, plantillas |
| Entrega para revisión | Walkthrough mental + revisión de roles antes de commit |
| Entrega final / aprobación final | `git push` al remote; propagación vía `git pull` en proyectos cliente |
| Ambiente de revisión | Uso real en sesiones de otro stack (validación diferida en uso) |
| Estado aprobado | Lineamiento en uso, ≥10 sesiones sin reporte negativo |
| Dependientes | Otras secciones o lineamientos que referencian la regla o archivo afectado |
| Flujos críticos | Lineamientos que, si se rompen, generan errores sistemáticos en todos los proyectos |

## Documentos

1. [Deployment](deployment.md) — cómo se "deploya" un cambio + tipo de validación "diferida en uso" + criterio de cierre.
2. [Roles](roles.md) — Process Architect + QA Process Engineer + Process Improvement Analyst (roles fijos sin detección por dimensiones).

> Los lineamientos para editar los `.md` de la metodología viven en [`../../methodology/principles.md`](../../methodology/principles.md) § "Lineamientos para editar MDs" — son núcleo (editar la metodología es aplicarla), no contenido de stack.
