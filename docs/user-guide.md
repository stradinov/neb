# Guía del usuario — adoptar y extender Neb

Cómo poner Neb a trabajar en tu equipo: instalarlo, montar tu capa propia y definir tu primer profile — todo **sin tocar el núcleo**. Para entender *cómo funciona Neb* por dentro, ver [how-it-works.md](how-it-works.md).

## Instalar

Neb se instala como **plugin de Claude Code** — no requiere clonar el repo ni correr instaladores. Desde Claude Code:

```
/plugin marketplace add stradinov/neb
/plugin install neb@neb
```

Luego escribe `/wakeup` — el recorrido conecta o monta tu espacio de trabajo (vía `setup-workspace.sh`) y te guía por los pasos de abajo. Un hook `SessionStart` inyecta el arranque de la metodología en cada sesión; los skills, agents y commands del plugin se auto-descubren.

> El modelo de **clonar el repo + correr `bootstrap/install.sh`** fue **eliminado en 3.0.0** (obsoleto desde 2.0.0) como vía de uso. El clon solo es necesario para **contribuir al núcleo** (ver [Contribuir al núcleo](#contribuir-al-núcleo-mantenedores)).

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

> El layout con `neb/` como **subtree** del repo y el flujo `git subtree add/pull/push` corresponden al modelo de **contribución al núcleo**, no de uso — ver [Contribuir al núcleo](#contribuir-al-núcleo-mantenedores).

### Configurar el entorno

El recorrido `/wakeup` ejecuta el script de configuración por ti (idempotente — seguro de repetir, sirve para restablecimiento o migración). El script (`setup-workspace.sh`, viene con el plugin) crea lo que falte (`overlay/`, `personal/`, `changes/`) y establece **dos variables** en `~/.claude/settings.json` (merge no-destructivo):

| Variable | Apunta a | Para |
|---|---|---|
| `NEB_HOME` | el directorio del plugin instalado | hooks (`$NEB_HOME/hooks`), templates y bootstrap del núcleo |
| `NEB_WORKSPACE` | la raíz de tu espacio de trabajo de gobernanza | tu overlay, `personal/`, `changes/` |

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

`personal/<usuario>.md` guarda tus preferencias, atajos y overrides individuales (qué son y su contrato "estrecha o agrega, nunca relaja": ver [how-it-works § Personalización](how-it-works.md) y [`methodology/personal-vs-team.md`](../methodology/personal-vs-team.md)). Viene **ignorada por Git** — tu configuración no se publica ni sale del plugin.

Si quieres versionarla (respaldo, portabilidad entre máquinas), quita la regla `personal/` de **tu** `.gitignore` (no del de `neb/`) y haz commit de ella en tu repo privado. Excluye binarios (`*.wav` y similares). Sus cambios se trazan con el commit normal; no llevan change MD.

## Retomar y relevar trabajo (bitácora de relevo)

Cuando una sesión queda a medias —tokens agotados, corte de luz/red, o porque otro dev sigue— la **bitácora de relevo** te deja retomarla. Es **opcional**: agrega el hook `logbook-sync` a tu `<proyecto>/.claude/settings.json` (base en `hooks/settings.template.json`; en Windows usa la variante `"shell": "powershell"`). El hook registra tu trabajo en una bitácora local (SQLite, `~/.claude/neb.db`) en cada cierre de turno, sin que tengas que anunciar la pausa.

Con el comando `/logbook`:

- **`/logbook`** — lista tus trabajos a medias (con REQ y sesiones exploratorias) con su contexto.
- **`/logbook retomar <id>`** — reconstruye el contexto: para un REQ, toma el mando y abre una sesión nueva con el transcript; para una exploración, te entrega el `claude --resume`.
- **`/logbook tomar | liberar | solicitar <id>`** — opera el "mando" del trabajo (un solo dueño a la vez).
- **`/logbook search <texto>`** — busca en el corpus de transcripts (requiere central).
- **`/logbook renombrar <id> <nuevo-slug>`** — renombre gobernado del REQ (requiere central).

Por defecto la bitácora es **local** (tu máquina) — si trabajas solo, no necesitas nada más. El **relevo entre devs o máquinas** —que otro dev tome tu trabajo y lo devuelva, con búsqueda de texto completo del corpus— lo habilita el **backend central** del equipo (servidor opcional, distribuido en un repositorio dedicado). **Privacidad**: la bitácora es **local por defecto** —nada se publica al equipo salvo que lo pidas, aunque tengas el central configurado—. Para que un proyecto comparta su trabajo al catálogo central (works **y sesiones exploratorias**, con su transcript sin las salidas de herramientas), agrega `<!-- neb-logbook: central -->` a su `CLAUDE.md` (**de activación voluntaria por proyecto**). Detalle: [`workflow/logbook.md`](../workflow/logbook.md) y [`tooling/logbook.md`](../tooling/logbook.md).

## Contribuir al núcleo (mantenedores)

Lo anterior cubre **usar** Neb. **Contribuir al núcleo** —corregir o extender lo que vive en el repo neb, no tu overlay— es un rol de mantenedor y requiere un **clon normal del repo**, separado de tu espacio de trabajo:

```bash
git clone https://github.com/stradinov/neb ~/neb   # o donde prefieras
cp ~/neb/hooks/pre-push-changelog ~/neb/.git/hooks/pre-push   # gate del CHANGELOG
```

Flujo: editas en el clon, fragmento de CHANGELOG (`changelog.d/<version>.md` + `bootstrap/assemble-changelog.py`) y `git push` directo (fork + PR si no tienes write). Para **dogfoodear** tus cambios antes de publicarlos, apunta `NEB_HOME` al clon (el hook `SessionStart` prefiere `NEB_HOME` sobre el caché del plugin) o corre `claude --plugin-dir <clon>`.

El clon del núcleo y tu espacio de trabajo son repos **independientes**: el núcleo se actualiza con `git pull` sin tocar lo tuyo. (El layout histórico de `neb/` como `git subtree` dentro de un repo de gobernanza sigue siendo posible, pero ya no es el camino recomendado — un clon separado es más simple y el push no requiere `subtree split`.)

### Cómo se redactan los MDs (modos de redacción)

El calibre de un texto depende de su **consumidor**. Esto es una guía ilustrativa; la fuente canónica es [`methodology/principles.md`](../methodology/principles.md) § "Lineamientos para editar MDs" (criterio de corte por consumidor + suficiencia).

| Modo | Consumidor | Dónde | Calibre |
|---|---|---|---|
| **Normativa** | el agente (aplica el lineamiento) | `general/` · `methodology/` · `process/` · `workflow/` | Austera: criterio de corte estricto + suficiencia mínima (una regla enuncia condición · acción · consecuencia) |
| **Explicativa** | humano que entiende la mecánica | [`how-it-works.md`](how-it-works.md) | Suficiencia; admite contexto y diagramas |
| **Adopción** | humano que adopta o extiende | este archivo · `README.md` | Suficiencia + ejemplos y analogías moderadas |

Los modos **no relajan** la austeridad de la normativa: nombran cuándo un texto de cara al humano admite legítimamente más contexto. La austeridad (no escribir lo que no cambia conducta) y la suficiencia (no cortar lo que el consumidor necesita) son los dos límites.
