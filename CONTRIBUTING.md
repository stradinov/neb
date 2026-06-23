# Cómo contribuir a Neb

Gracias por tu interés en mejorar **Neb**. Esta guía explica el único canal de contribución abierto: **abrir un issue en GitHub**.

## Cómo se mantiene Neb

Neb se gobierna con sus propias reglas (profile `self-applied`): cada cambio a la metodología es un requerimiento que el equipo mantenedor ejecuta siguiendo las fases y gates de la propia metodología (clarificación, propuesta, implementación, validación), con push directo al repo. El versionado SemVer, el `CHANGELOG.md` fragmentado y los bumps de versión son **ceremonia interna del mantenedor** — no algo que tú necesites hacer para contribuir.

Por eso Neb **no opera con Pull Requests externos**: un PR no encaja en el flujo self-applied. Tu aporte entra por un issue, y ahí se acuerda el alcance.

## Cómo contribuir: abre un issue

Toda contribución —reportar un defecto o proponer una mejora— empieza dando de alta un issue. Hay dos plantillas, y al crear el issue eliges la que aplica:

- **🐞 Reporte de defecto** — algo de Neb no se comporta como su documentación o sus reglas indican (una fase, un profile, un skill, un hook, un comando, un documento, el vocabulario o el plugin).
- **💡 Propuesta de mejora** — una fricción, un gap o una idea para mejorar la metodología o sus herramientas.

**¿Defecto o mejora?** Si Neb no cumple lo que su documentación promete, es un **defecto**; si la documentación o la regla misma debería cambiar, es una **mejora**.

Cada plantilla es un formulario con campos guiados; al llenarlos, tu issue cumple el esquema de descripción que el equipo necesita para triarlo sin ida y vuelta.

> Los issues en blanco están desactivados a propósito: usa una de las dos plantillas para que el reporte llegue con la información mínima.

## Antes de abrir un issue

- **Busca duplicados.** Revisa los [issues existentes](https://github.com/stradinov/neb/issues) (abiertos y cerrados) antes de crear uno nuevo.
- **Conoce el modelo.** Lee el [README](README.md) y la [Guía del usuario](docs/user-guide.md) para ubicar el componente que reportas (fase, profile, skill, hook, comando, documento).

## Qué hace un buen reporte

El formulario te pide estos elementos; respetarlos acelera el triage:

- **Separa hechos de hipótesis.** Describe primero lo que **observaste** (citable, reproducible) y, si tienes una idea de la causa, márcala explícitamente como **hipótesis** — no la mezcles con los hechos.
- **Sé reproducible.** Pasos concretos y, cuando aplique, la versión del plugin y tu entorno (sistema operativo, versión de Claude Code).
- **Cuida la evidencia.** Adjunta transcripts, mensajes de error o capturas, pero **sin información personal (PII), datos de clientes, marcas ni rutas absolutas de tu máquina**. Neb es agnóstica de dominio: usa ejemplos genéricos.

## Qué pasa después

El equipo mantenedor tría el issue. Si se acepta, se convierte en un requerimiento que sigue el flujo self-applied de Neb: se clarifica el alcance, se propone, se implementa con revisión de roles, y se entrega con su entrada en el `CHANGELOG.md` y su bump de versión. El issue queda enlazado al cambio para trazabilidad.

## Para mantenedores

Las convenciones de edición del repo (naming `kebab-case`, imports relativos, versionado SemVer, flujo de `CHANGELOG.md` fragmentado, ownership de archivos `.md`) viven en [`CLAUDE.md`](CLAUDE.md) y en la metodología misma.

## Código de conducta

Sé respetuoso y constructivo. Un `CODE_OF_CONDUCT.md` formal se agregará en una iteración futura.
