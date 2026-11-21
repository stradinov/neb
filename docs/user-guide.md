# Guía del usuario — adoptar y extender Neb

Cómo poner Neb a trabajar en tu equipo: instalarlo, montar tu capa propia y definir tu primer profile — todo **sin tocar el núcleo**. Para entender *cómo funciona Neb* por dentro, ver [how-it-works.md](how-it-works.md).

## Instalar

Neb se instala como **plugin de Claude Code** — no requiere clonar el repo ni correr instaladores. En Windows requiere **Git for Windows (Git Bash)**: Claude Code corre ahí los hooks del plugin, y sin él fallan en cada evento (ver [`hooks/README.md`](../hooks/README.md) § "Bajo el plugin de Neb"). Desde Claude Code:

```
/plugin marketplace add stradinov/neb
/plugin install neb@neb
```

Luego escribe `/wakeup` — el recorrido conecta o monta tu espacio de trabajo (vía `setup-workspace.sh`) y te guía por los pasos de abajo. Un hook `SessionStart` inyecta el arranque de la metodología en cada sesión; los skills, agents y commands del plugin se auto-descubren.

> El modelo de **clonar el repo + correr `bootstrap/install.sh`** fue **eliminado en 3.0.0** (obsoleto desde 2.0.0) como vía de uso. El clon solo es necesario para **contribuir al núcleo** (ver [Contribuir al núcleo](#contribuir-al-núcleo)).

El plugin no se actualiza solo hasta que lo decidas: ver [Mantener Neb al día](#mantener-neb-al-día).

## Mantener Neb al día

Según la documentación de Claude Code, la actualización automática viene **apagada** en los marketplaces de terceros, y el de Neb es uno de ellos. Mientras no la enciendas, tu instalación se queda en la versión que instalaste. La misma documentación no da a `marketplace.json` un campo para encenderla: la decides tú, una vez por máquina. Según la misma documentación, la decisión es del marketplace, no del plugin: si recibes Neb por un marketplace que trae otros plugins, también esos se actualizarán solos.

**Encenderla.** Hay tres vías:

- **Aceptar la oferta.** Mientras no hayas decidido, Claude te ofrece encenderla al cierre de su primera respuesta. Con tu OK, corre el ayudante del plugin (abajo). Si la rechazas, queda apagada y la oferta no vuelve. La oferta sale solo si tu settings ya trae la entrada del marketplace, que es donde se escribe la decisión.
- **El interruptor «Enable auto-update»** de `/plugin`, pestaña Marketplaces. Según la documentación de Claude Code, escribe esa misma clave, y queda oculto con `DISABLE_AUTOUPDATER=1` mientras no exista `FORCE_AUTOUPDATE_PLUGINS=1`; es el caso de la app de escritorio (abajo).
- **A mano**, en tu `~/.claude/settings.json`. La entrada del marketplace lleva `"autoUpdate": true`. Esa entrada la crea `claude plugin marketplace add` (con `/plugin marketplace add` no se ha comprobado); si no la tienes, agrégala completa:

  ```json
  "extraKnownMarketplaces": {
    "neb": {
      "source": { "source": "github", "repo": "stradinov/neb" },
      "autoUpdate": true
    }
  }
  ```

**Qué esperar con la actualización automática encendida.**

- Después de tu primer mensaje en una sesión interactiva, Claude Code espera hasta diez minutos y actualiza en disco los plugins de los marketplaces con actualización automática encendida. La sesión abierta sigue con la versión que cargó; la nueva rige desde la **siguiente sesión**, o antes con `/reload-plugins` (según la documentación de Claude Code; en la app de escritorio se observó a los 7 minutos).
- Recibes **cada versión que se publica**; hoy no hay un canal estable aparte. Si prefieres elegir el momento, déjala apagada y actualiza a mano.
- **En la app de escritorio** se observó que las sesiones corren con `DISABLE_AUTOUPDATER=1` (versión 2.1.325). Según la documentación de Claude Code, esa variable apaga toda la actualización automática de plugins y oculta el interruptor, salvo que exista `FORCE_AUTOUPDATE_PLUGINS=1`. Esta última la vuelve a encender para **todos** tus marketplaces con actualización automática encendida, no solo para el de Neb. Cuando aceptas la oferta desde la app, el ayudante la agrega al bloque `env` de tu settings. No se ha probado si la actualización corre sin ella. A mano: `"env": { "FORCE_AUTOUPDATE_PLUGINS": "1" }`.

**Actualizar a mano**, con la actualización automática apagada o para no esperar:

```
claude plugin marketplace update neb
claude plugin update neb@neb
```

**Máquinas con sesiones no interactivas** (servidores, CI, tareas programadas): deja `"autoUpdate": false` en la entrada del marketplace. El plugin no cambia de versión sin que lo decidas y el arranque deja de traer la oferta.

**Ver el estado y cambiar de opinión.** Lo más simple es pedírselo a Claude («enciende la actualización automática de Neb», «apágala»). Claude corre el ayudante, que vive en el plugin instalado: `<dir de configuración>/plugins/cache/<marketplace>/neb/<versión>/hooks/lib/autoupdate.py` (el dir de configuración es `~/.claude`, salvo que uses `CLAUDE_CONFIG_DIR`). Si `CLAUDE_CODE_PLUGIN_CACHE_DIR` lleva los plugins fuera de tu dir de configuración, el ayudante no ubica tu settings y no escribe: decide a mano o con el interruptor. También lo corres tú, con Python; pon en la terminal el mismo `CLAUDE_CONFIG_DIR` que tu sesión de Claude Code, o ninguno si tu sesión no lo usa, porque si no coincide el ayudante no escribe:

```
python <ruta>/hooks/lib/autoupdate.py status     # el estado y qué archivo lo decide; no escribe
python <ruta>/hooks/lib/autoupdate.py enable     # la enciende
python <ruta>/hooks/lib/autoupdate.py disable    # la apaga
```

- `enable` y `disable` solo escriben tu settings de usuario, y antes dejan al lado un respaldo `settings.json.bak-neb-<fecha>-<hora>`. Para revertir, restaura ese respaldo o cambia la clave. El contenido del settings se conserva; si el archivo estaba minificado, queda con sangría.
- Para cambiar de opinión sirve cualquiera de las tres vías. Según la documentación de Claude Code, la clave de tu settings manda sobre la de `plugins/known_marketplaces.json` y el interruptor escribe las dos; eso no se ha probado con Neb.
- `disable` no quita `FORCE_AUTOUPDATE_PLUGINS`. Bórrala a mano si ningún otro marketplace la necesita.
- Si tu settings no trae la entrada del marketplace, el ayudante no escribe nada y te muestra el bloque para agregarla a mano.

**Qué pasa con tu base al actualizar** (desde 6.48.0). Tus pendientes y tu bitácora viven en `~/.claude/neb.db`. Cuando una versión cambia el esquema de esa base, el cambio corre solo en la primera conexión de la versión nueva, sin que tengas que hacer nada:

- Si el cambio borra o reescribe datos, Neb copia antes la base, verificada, a `~/.claude/neb-backups/` y conserva la última copia.
- Plugin y clon (si tienes `NEB_HOME`) pueden tener versiones distintas: los dos operan la base mientras la entiendan. Si uno ya no la entiende, no la toca, sus comandos responden `base-incompatible` y el arranque de la sesión te dice cuál actualizar.
- `py <ruta>/bootstrap/neb-migrate.py status` muestra la versión de esquema de tu base y del código, si algo detiene un cambio y qué respaldos hay.
- Para volver a una versión anterior: regresa primero plugin y clon, y después `neb-migrate.py restore <respaldo>`. Detalle en `tooling/migrations.md`.

**Cuando una versión pide configurar tu máquina** (desde 6.49.0). Algunas versiones piden algo más que cambiar la base: quitar una clave de tu `settings.json` o una variable de entorno que ya no se usa. Eso es una **migración guiada**:

- Al abrir sesión, Claude te avisa que hay una migración pendiente y te ofrece abrirla en una sesión nueva: en la app de escritorio, con una tarjeta de sesión nueva cuando la sesión trae esa herramienta (aún no se ha observado con el plugin publicado); si no, con el comando `claude "/neb:migrate"`. La sesión en la que estás trabajando no la empieza por su cuenta.
- En esa sesión, `/neb:migrate` corre solo lo que deja con qué deshacerlo (p. ej. quitar una clave no secreta de `settings.json`, guardando el par quitado en `~/.claude/neb-backups/`). Lo que no deja respaldo, como quitar un token o una variable de entorno, te lo pregunta en un solo menú: aplicarlo, no aplicarlo (deja de ofrecerse) o después.
- Las sesiones y terminales que ya estaban abiertas conservan en su entorno las variables quitadas hasta que las reinicies.
- A mano: `neb-migrate.py status` lista lo pendiente, `apply` corre lo que corre solo, `apply --include <id>` un paso que pide tu OK y `skip <id>` guarda tu «no».

## Conectarse al espacio de trabajo del equipo

Si tu equipo ya tiene un **repositorio del espacio de trabajo** (overlay + `changes/` + `personal/` centralizados), no creas nada: lo conectas. Tres pasos:

```
/plugin marketplace add stradinov/neb      # + /plugin install neb@neb (una vez)
git clone <repo-workspace-del-equipo> && cd <repo>
/wakeup
```

`/wakeup` detecta que el clon ya es un espacio de trabajo (marcadores estructurales: `*/overlays/detect-profile.local.sh` — el mismo criterio que usa el hook en tiempo de ejecución) y ofrece **conectarlo**: establece `NEB_WORKSPACE` en tu `settings.json` y crea tu `personal/<usuario>.md` si falta. El paso final es **abrir una sesión nueva** de Claude Code: ahí el hook ya inyecta el arranque con el overlay de tu equipo.

## Montar tu overlay

`neb` es el núcleo y lo consumes vía el plugin instalado. Lo tuyo —profiles de dominio, agents/skills propios, preferencias— vive en una capa aparte (*overlay*), **nunca dentro de `neb/`**, para poder actualizar el núcleo (el plugin) sin conflictos. Montar el overlay es el **paso mínimo para usar Neb**: sin él no tienes dónde definir tu primer profile.

El overlay es un directorio propio (`overlay/`, `personal/`, `changes/`) en tu repo de gobernanza o en tu espacio de trabajo; no necesita ser un subtree de `neb/` para usar Neb. El recorrido `/wakeup` lo monta por ti vía `setup-workspace.sh`.

```
tu-workspace/
├── overlay/    ← tus profiles/agents/skills de dominio
├── personal/   ← tu config personal (gitignored por defecto)
├── changes/    ← tus change MDs
└── CLAUDE.md   ← importa tus profiles de dominio (el arranque del núcleo lo inyecta el plugin)
```

> El layout con `neb/` como **subtree** del repo y el flujo `git subtree add/pull/push` corresponden al modelo de **contribución al núcleo**, no de uso — ver [Contribuir al núcleo](#contribuir-al-núcleo).

### Configurar el entorno

El recorrido `/wakeup` ejecuta el script de configuración por ti (idempotente — seguro de repetir, sirve para restablecimiento o migración). El script (`setup-workspace.sh`, viene con el plugin) crea lo que falte (`overlay/`, `personal/`, `changes/`) y establece las variables en `~/.claude/settings.json` (merge no-destructivo). Con solo el plugin establece `NEB_WORKSPACE`: `NEB_HOME` no hace falta, porque el plugin resuelve su propio directorio en cada sesión, y fijar el del caché, que es uno por versión, dejaría a Neb en esa versión después de un update.

| Variable | Apunta a | Para |
|---|---|---|
| `NEB_HOME` | el clon de neb (solo si el núcleo viene de un clon) | arranque, templates y bootstrap del núcleo desde el clon. Se ignora si apunta al caché del plugin |
| `NEB_WORKSPACE` | la raíz de tu espacio de trabajo de gobernanza | tu overlay, `personal/`, `changes/` |
| `NEB_HOOKS` / `NEB_PROJECT_HOOKS` | listas de hooks opcionales (las agregas tú; `/wakeup` no las toca) | activar los hooks que registra el plugin (ver [Retomar y relevar trabajo](#retomar-y-relevar-trabajo-bitácora-de-relevo)) |

Abre una **sesión nueva** de Claude Code para que surtan efecto (settings.json se lee por sesión). El script detecta un overlay preexistente y no lo pisa; el flag `--overlay <nombre>` solo nombra uno nuevo si no hay ninguno (por defecto `overlay`).

## Definir tu primer profile

Un *profile* concreta Neb para un tipo de proyecto (comandos de build, convenciones de commit, proceso de deploy, revisores aplicables) — es lo que hace a Neb útil para tu dominio. Materialízalo en **tu overlay**, no en `neb/`.

```bash
bash bootstrap/init-profile-subproject.sh <nombre>
```

Genera la estructura base con los archivos mínimos. Referencia completa: [`methodology/profiles.md`](../methodology/profiles.md).

Definir un profile **puede implicar** crear capacidades de apoyo:

### Skill de apoyo al profile

Un skill carga conocimiento de dominio cuando Claude lo necesita (mapas de código, convenciones específicas, resolución de problemas).

1. Crear `skills/<nombre>/SKILL.md` con los campos `name` y `description`.
2. Agregar archivos de contenido y scripts si aplica.
3. Registrar en `skills/README.md` y en el profile correspondiente.

El agente los descubre automáticamente.

### Agentes revisores del profile

Un profile puede definir revisores adversariales propios (por dimensión: seguridad, datos, convenciones) que actúan en el plan-review.

1. Crear `agents/<nombre>.md` con los campos `name`, `description` y `tools`.
2. El cuerpo constituye el prompt de sistema del rol.

Los agents se auto-descubren del plugin: basta con crear el `agents/<nombre>.md`. Tras agregarlo, `/reload-plugins` lo carga sin reiniciar; en una sesión nueva ya quedan disponibles.

## Versionar tu configuración personal

`personal/<usuario>.md` guarda tus preferencias, atajos y overrides individuales (qué son y su contrato "estrecha o agrega, nunca relaja": ver [how-it-works](how-it-works.md) § "Personalización sin modificar el núcleo" y [`methodology/personal-vs-team.md`](../methodology/personal-vs-team.md)). Viene **ignorada por Git** — tu configuración no se publica ni sale del plugin.

Si quieres versionarla (respaldo, portabilidad entre máquinas), quita la regla `personal/` de **tu** `.gitignore` (no del de `neb/`) y haz commit de ella en tu repo privado. Excluye binarios (`*.wav` y similares). Sus cambios se trazan con el commit normal; no llevan Change MD.

## Retomar y relevar trabajo (bitácora de relevo)

Cuando una sesión queda a medias —tokens agotados, corte de luz/red, o porque otro dev sigue— la **bitácora de relevo** te deja retomarla. Es **opcional**: el plugin registra el hook `logbook-sync`, y tú lo activas agregándolo a `NEB_HOOKS` en el bloque `env` de `~/.claude/settings.json`:

```json
{ "env": { "NEB_HOOKS": "logbook-sync" } }
```

Con eso aplica a todos tus proyectos, desde la siguiente sesión. Para activarlo solo en un proyecto para todo el equipo, usa `NEB_PROJECT_HOOKS` en su `.claude/settings.json` versionado. Corre con el código del plugin instalado, sin `NEB_HOME`. En Windows requiere Git Bash (Git for Windows). Los demás hooks opcionales (`save-approved-plan`, `notify-on-stop`, `notify-on-permission`, `preprocess-prompt`) se activan igual: ver [`hooks/README.md`](../hooks/README.md) § "Bajo el plugin de Neb". Si tu `settings.json` todavía invoca hooks desde `$NEB_HOME` (templates anteriores a 6.15.0), quita esas entradas al activarlos, o correrán dos veces.

El hook registra tu trabajo en una bitácora local (SQLite, `~/.claude/neb.db`) en cada cierre de turno, sin que tengas que anunciar la pausa.

Con el comando `/logbook`:

- **`/logbook`** — lista tus trabajos a medias (con REQ y sesiones exploratorias) con su contexto.
- **`/logbook retomar <id>`** — reconstruye el contexto: para un REQ, toma el mando y abre una sesión nueva con su Change MD, su `## Relevo` y su plan aprobado; para una exploración, te entrega el `claude --resume`.
- **`/logbook retomar <ruta-del-Change-MD>`** — cuando el REQ no tiene trabajo en la bitácora: sin tomar el mando, lee el Change MD, su `## Relevo` y su plan aprobado, y continúa desde ahí ([`skills/logbook/SKILL.md`](../skills/logbook/SKILL.md)).
- **`/logbook tomar | liberar | solicitar <id>`** — opera el "mando" del trabajo (un solo dueño a la vez).
- **`/logbook renombrar <id> <nuevo-slug>`** — renombre gobernado del REQ (con central, preserva su historial en el catálogo del equipo).
- **`/logbook estado-sync`** — qué trabajos siguen sin publicarse al central, cuáles están en conflicto y cuáles tienen un fallo de sync vigente (con su causa y desde cuándo). `/logbook` sin argumentos te avisa si hay conflictos o fallos vigentes. Lee siempre tu bitácora local.
- **`/logbook vincular <ruta>`** — vincula un REQ en tu bitácora local a partir de su Change MD (escribir el Change MD ya lo vincula); con `--repo <dir>` declaras otro repo del REQ, uno por llamada.
- **`/logbook traza <nombre>`** — muestra los commits publicados con trailer `Req:` (o `Confirmacion-autonoma:`) en los repos declarados del REQ, leídos de git al consultar, y las sesiones de esta máquina que lo trabajaron, con su transcript. Sin nombre, lista tus REQ vinculados.
- **`/logbook desvincular <id|nombre|ruta>`** — quita un REQ vinculado por error, con sus repos y sesiones; para corregir un repo mal declarado, desvincula y vuelve a vincular. Nada de esto viaja al central ([`workflow/logbook.md`](../workflow/logbook.md) § "REQ vinculado").

Por defecto la bitácora es **local** (tu máquina) — si trabajas solo, no necesitas nada más. El **relevo entre devs o máquinas** —que otro dev tome tu trabajo y lo devuelva— lo habilita el **backend central** del equipo (servidor opcional, distribuido en un repositorio dedicado).

**Privacidad**: la bitácora es **local por defecto** —nada se publica al equipo salvo que lo pidas, aunque tengas el central configurado—. Para que un proyecto comparta su trabajo al catálogo central (works **y sesiones exploratorias**; de tus conversaciones solo viaja el resumen del exploratorio, su primer mensaje recortado a 120 caracteres), agrega `<!-- neb-logbook: central -->` a su `CLAUDE.md` (**de activación voluntaria por proyecto**). Detalle: [`workflow/logbook.md`](../workflow/logbook.md) y [`tooling/logbook.md`](../tooling/logbook.md).

## Contribuir al núcleo

Lo anterior cubre **usar** Neb. **Contribuir al núcleo** —corregir o extender lo que vive en el repo neb, no tu overlay— requiere un **clon normal del repo**, separado de tu espacio de trabajo:

```bash
git clone https://github.com/stradinov/neb ~/neb   # o donde prefieras
```

**Sin permiso de escritura en el repo** aportas por pull request: sin fragmento de CHANGELOG, sin incremento de versión y sin instalar el hook `pre-push`. Si la mejora sale de la retroalimentación de un requerimiento (Fase 9), Claude prepara el pull request contigo; el procedimiento y las reglas están en [`process/upstream-contribution.md`](../process/upstream-contribution.md) y en [CONTRIBUTING](../CONTRIBUTING.md).

**Como mantenedor** (con permiso de escritura) instalas además la envoltura de los gates del pre-push:

```bash
cp ~/neb/hooks/pre-push-wrapper ~/neb/.git/hooks/pre-push
```

Flujo del mantenedor: editas en el clon, fragmento de CHANGELOG (`changelog.d/<version>.md` + `bootstrap/assemble-changelog.py`) y `git push` directo. Para **dogfoodear** tus cambios antes de publicarlos, apunta `NEB_HOME` al clon (el hook `SessionStart` prefiere `NEB_HOME` sobre el caché del plugin) o corre `claude --plugin-dir <clon>`. Los hooks opcionales activados con `NEB_HOOKS` corren siempre el plugin cargado: para probarlos desde el clon, usa `--plugin-dir`. Ojo: si el clon trae un paso de base nuevo, la primera conexión lo aplica a tu `~/.claude/neb.db`; para probarlo sin tocarla, usa un home temporal (`HOME` y `USERPROFILE`) con una copia de la base.

El clon del núcleo y tu espacio de trabajo son repos **independientes**: el núcleo se actualiza con `git pull` sin tocar lo tuyo. La envoltura instalada ejecuta `hooks/pre-push-changelog` del clon, así que el hook `pre-push` se actualiza con `git pull` sin reinstalarlo. (El layout histórico de `neb/` como `git subtree` dentro de un repo de gobernanza sigue siendo posible, pero ya no es el camino recomendado — un clon separado es más simple y el push no requiere `subtree split`.)

### Cómo se redactan los MDs (modos de redacción)

El calibre de un texto depende de su **consumidor**. Esto es una guía ilustrativa; la fuente canónica es [`methodology/principles.md`](../methodology/principles.md) § "Lineamientos para editar MDs" (criterio de corte por consumidor + suficiencia).

| Modo | Consumidor | Dónde | Calibre |
|---|---|---|---|
| **Normativa** | el agente (aplica el lineamiento) | `general/` · `methodology/` · `process/` · `workflow/` | Austera: criterio de corte estricto + suficiencia mínima (una regla enuncia condición · acción · consecuencia) |
| **Explicativa** | humano que entiende la mecánica | [`how-it-works.md`](how-it-works.md) | Suficiencia; admite contexto y diagramas |
| **Adopción** | humano que adopta o extiende | este archivo · `README.md` | Suficiencia + ejemplos y analogías moderadas |

Los modos **no relajan** la austeridad de la normativa: nombran cuándo un texto de cara al humano admite legítimamente más contexto. La austeridad (no escribir lo que no cambia conducta) y la suficiencia (no cortar lo que el consumidor necesita) son los dos límites.
