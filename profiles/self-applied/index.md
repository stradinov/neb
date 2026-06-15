# Profile: self-applied

Proyectos auto-aplicados — la metodología que se edita es la que se aplica. Caso canónico: el propio repo `neb`.

## Por qué `self-applied` sin sufijo de dominio

El nombre rompe deliberadamente los patrones de naming del repo (`<adjetivo>-<dominio>` como `<lenguaje>-<framework>`; `*-authoring` como `skill-authoring`). El sustantivo de dominio se omite porque el profile cubre cualquier marco auto-aplicado — metodología pura (principios, vocabulario, ENUMs), proceso puro (fases, gates, comandos), artefactos (changes, pendings, plans) — y no se restringe a un dominio. Nombrarlo `self-applied-methodology` o `self-applied-process` reintroduciría la asimetría que el rename buscaba eliminar (ver [`methodology/principles.md`](../../methodology/principles.md)).

La 4ª categoría de naming "Profiles auto-aplicados / reflexivos" está documentada en [`methodology/profiles.md`](../../methodology/profiles.md).

## Características

- **Entregable**: archivos markdown que describen políticas, fases, artefactos, plantillas.
- **Sin código ejecutable** que requiera build, tests unitarios o servidor.
- **Ambiente único: prueba = producción** — no existe QA separado; las sesiones donde se aplica el lineamiento son simultáneamente ambiente de pruebas y de producción (ver [deployment.md](deployment.md) "Ambiente único").
- **Deploy**: `git push` al remote → `git pull` en proyectos cliente que importen vía `@~/.claude/neb/...`.
- **Validación**: revisión de roles + coherencia estática + dogfooding en la misma sesión (ver [deployment.md](deployment.md)); cierre inmediato. La fricción que aparece al aplicar el lineamiento en otra sesión es retroalimentación de Fase 9, no un gate de cierre.
- **Reflexividad**: el repo importa su propio `CLAUDE.md`, lo que hace que Claude trabaje sobre la metodología que aplica.

## Antes de proponer ubicación de archivos

Cualquier archivo nuevo o relocalización en el repo deriva su path de la clasificación Metodología / Proceso / Mixto. Consultar [`../../methodology/principles.md`](../../methodology/principles.md) antes de proponer ubicación en Fases 1–3 (ver bullet en [`../../process/planning.md`](../../process/planning.md) § "Insumos de contexto"). El gate aplica a creación, movimiento y rename — no a ediciones in-place.

## Detección

Heurística: el repo contiene `methodology/principles.md`, `process/plan-review.md` y `general/index.md` con fases canónicas. Hoy aplica al propio repo `neb`; podría extenderse a otros proyectos auto-aplicados futuros (fork de la metodología, metodología hermana con misma propiedad reflexiva).

## Glosario del profile

Concretización del [vocabulario abstracto](../../methodology/vocabulary.md) de la metodología para proyectos auto-aplicados:

| Término abstracto | En este profile |
|---|---|
| Entregable / elaboración | Archivos markdown de políticas, fases, artefactos, plantillas |
| Entrega para revisión | Walkthrough mental + revisión de roles antes de commit |
| Entrega final / aprobación final | `git push` al remote; propagación vía `git pull` en proyectos cliente |
| Ambiente de revisión | Revisión de roles + coherencia en la sesión que edita (dogfooding) |
| Estado aprobado | Lineamiento entregado tras revisión de roles + coherencia (cierre inmediato) |
| Dependientes | Otras secciones o lineamientos que referencian la regla o archivo afectado |
| Flujos críticos | Lineamientos que, si se rompen, generan errores sistemáticos en todos los proyectos |

## Documentos

1. [Deployment](deployment.md) — cómo se "deploya" un cambio + validación (roles + coherencia) + criterio de cierre.
2. [Roles](roles.md) — Process Architect + QA Process Engineer + Process Improvement Analyst (roles fijos sin detección por dimensiones).

## Redacción de los MDs de Neb — mapa

Los lineamientos para redactar/editar la metodología están repartidos por capa (test de pertenencia); este mapa los reúne:

| Documento | Cuándo aplica |
|---|---|
| [`methodology/principles.md`](../../methodology/principles.md) § "Lineamientos para editar MDs" | **Siempre** al editar cualquier `.md` del núcleo: qué eliminar, conservar, no tocar, qué declarar (cambios de fuerza normativa — nunca Patch) y qué reportar sin fix silencioso. En el mismo archivo: capas y test de pertenencia (dónde va un archivo nuevo), coherencia global sobre cambio mínimo, anti-patrones |
| [`CLAUDE.md` del repo](../../CLAUDE.md) | Mecánica del repo: naming `kebab-case`, `index.md` por carpeta, imports relativos, cómo citar archivos (tabla de referencias), "No editar a mano" |
| [`profiles/profile-authoring/conventions.md`](../profile-authoring/conventions.md) | Solo al redactar contenido de **profiles** (estructura, archivos mínimos, templates) |
| [`methodology/change-control-policy.md`](../../methodology/change-control-policy.md) | Ownership: qué puede editar Claude solo vs qué requiere OK humano (bloques `<!-- human -->`) |

> Los lineamientos de edición son núcleo (editar la metodología es aplicarla), no contenido de profile — este mapa solo los indexa.
