# Cómo contribuir a Neb

Gracias por tu interés en mejorar **Neb**. Hay dos canales de contribución: **abrir un issue** o **proponer el cambio con un pull request**.

## Cómo se mantiene Neb

Neb se gobierna con sus propias reglas (profile `self-applied`): cada cambio a la metodología pasa por las fases y gates de la propia metodología, con revisión de roles. El equipo mantenedor publica con push directo al repo. El versionado SemVer, el `CHANGELOG.md` fragmentado y los incrementos de versión son **ceremonia interna del mantenedor**: no los necesitas para contribuir, ni por issue ni por pull request.

## Qué canal usar

| Tienes | Canal |
|---|---|
| Un defecto sin corrección clara, una fricción o una idea | **Issue** |
| Un cambio concreto y acotado al núcleo (una regla, un documento, un arreglo) | **Pull request** |

Si usas Neb con Claude Code, la retroalimentación al cerrar un requerimiento (Fase 9) te propone el canal y prepara el pull request por ti: [`process/upstream-contribution.md`](process/upstream-contribution.md).

## Abrir un issue

Hay dos plantillas, y al crear el issue eliges la que aplica:

- **🐞 Reporte de defecto** — algo de Neb no se comporta como su documentación o sus reglas indican (una fase, un profile, un skill, un hook, un comando, un documento, el vocabulario o el plugin).
- **💡 Propuesta de mejora** — una fricción, una brecha o una idea para mejorar la metodología o sus herramientas.

**¿Defecto o mejora?** Si Neb no cumple lo que su documentación promete, es un **defecto**; si la documentación o la regla misma debería cambiar, es una **mejora**.

Cada plantilla es un formulario con campos guiados; al llenarlos, tu issue cumple el esquema de descripción que el equipo necesita para clasificarlo sin ida y vuelta.

> Los issues en blanco están desactivados a propósito: usa una de las dos plantillas para que el reporte llegue con la información mínima.

## Proponer un pull request

Las reglas son las mismas si lo prepara Claude o lo haces a mano:

- **Parte de `main` actualizado**, en una rama `mejora/<nombre-corto>` de tu fork.
- **Un cambio por pull request**, sin tocar `VERSION`, `CHANGELOG.md`, `changelog.d/` ni el campo `version` de `.claude-plugin/plugin.json` (la versión y la entrada del CHANGELOG las asigna el mantenedor), y sin tocar `.gitattributes` ni `.gitmodules`.
- **Solo texto y sin cambios de formato**: sin archivos binarios, sin cambiar el modo de un archivo y sin reescribir fines de línea. Antes de publicar, revisa que `git diff --summary origin/main...HEAD` no muestre `mode change` y que `git diff --numstat origin/main...HEAD` dé la misma salida con y sin `--ignore-cr-at-eol`.
- **Verifica antes de publicar** (Python 3.8 o posterior, sin paquetes adicionales), desde la raíz del clon:

  ```
  python3 bootstrap/assemble-startup.py --check general/startup.md
  python3 bootstrap/neb-bootstrap-context.py --check-size --root .
  python3 bootstrap/check-style.py --root .
  python3 bootstrap/check-references.py --no-overlay
  ```

  Si tu cambio toca algo que no es `.md`, también `python3 -m unittest discover -s hooks/tests`. En Windows usa `py -3` o `python`. Si `main` ya trae una referencia rota, solo cuentan las que agregue tu cambio: compara con la salida del mismo comando en `main`.
- **Describe el cambio**: la regla vigente (archivo y sección), el escenario que la motiva con nombres neutros, lo que observaste separado de tu hipótesis, el cambio propuesto, el nivel SemVer que sugieres, la versión de Neb que usas y, si quieres, la entrada de CHANGELOG que propones.
- **Sin datos privados** en el diff, los mensajes de commit, el nombre de la rama ni la descripción: ver § "Qué hace un buen reporte". Tu nombre y tu correo de autor quedan en `main`; si no quieres publicar tu correo, usa el correo noreply de GitHub (`git config --local user.email`).

## Antes de contribuir

- **Busca duplicados.** Revisa los [issues](https://github.com/stradinov/neb/issues) y los [pull requests](https://github.com/stradinov/neb/pulls) existentes (abiertos y cerrados).
- **Conoce el modelo.** Lee el [README](README.md) y la [Guía del usuario](docs/user-guide.md) para ubicar el componente que reportas o cambias (fase, profile, skill, hook, comando, documento).

## Qué hace un buen reporte

Vale para un issue y para la descripción de un pull request:

- **Separa hechos de hipótesis.** Describe primero lo que **observaste** (citable, reproducible) y, si tienes una idea de la causa, márcala explícitamente como **hipótesis** — no la mezcles con los hechos.
- **Sé reproducible.** Pasos concretos y, cuando aplique, la versión del plugin y tu entorno (sistema operativo, versión de Claude Code).
- **Cuida la evidencia.** Adjunta transcripciones, mensajes de error o capturas, pero **sin información personal (PII), datos de clientes, marcas ni rutas absolutas de tu máquina**. Neb es agnóstica de dominio: usa ejemplos genéricos.

## Qué pasa después

- **Issue.** El equipo mantenedor lo clasifica. Si se acepta, se convierte en un requerimiento que sigue el flujo `self-applied` de Neb y se entrega con su entrada en el `CHANGELOG.md` y su incremento de versión. El issue queda enlazado al cambio.
- **Pull request.** El mantenedor lo revisa con los roles de la metodología y responde con uno de tres veredictos: incorporar, pedir cambios o rechazar. Si te pide cambios, agrega commits a la misma rama, sin `push --force`. Al incorporarlo, tu cambio entra a `main` como un commit a tu nombre, junto con la versión y la entrada del CHANGELOG que te da crédito. En GitHub el pull request aparece **cerrado**, no fusionado, con un comentario que cita el commit y la versión: es el resultado esperado, no un rechazo.

## Para mantenedores

Las convenciones de edición del repo (convención de nombres `kebab-case`, `@imports` relativos, versionado SemVer, flujo de `CHANGELOG.md` fragmentado, propiedad de los archivos `.md`) viven en [`CLAUDE.md`](CLAUDE.md) y en la metodología misma. Cómo se incorpora un pull request: [`profiles/self-applied/deployment.md`](profiles/self-applied/deployment.md) § "Incorporar un PR".

## Código de conducta

Sé respetuoso y constructivo.
