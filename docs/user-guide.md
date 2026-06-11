# Guía del usuario — adoptar y extender Neb

Cómo poner Neb a trabajar en tu equipo: instalarlo, montar tu capa propia y definir tu primer profile — todo **sin tocar el núcleo**. Para entender *cómo funciona Neb* por dentro, ver [how-it-works.md](how-it-works.md).

## Instalar

Neb se instala como **plugin de Claude Code** — no requiere clonar el repo ni correr instaladores. Desde Claude Code:

```
/plugin marketplace add stradinov/neb
/plugin install neb@neb
```

Luego escribí `/wakeup` — el tour conecta o monta tu workspace (vía `setup-workspace.sh`) y te guía por los pasos de abajo. Un hook `SessionStart` inyecta el arranque de la metodología en cada sesión; los skills, agents y commands del plugin se auto-descubren.

> El modelo de **clonar el repo + correr `bootstrap/install.sh`** fue **eliminado en 3.0.0** (deprecado desde 2.0.0) como vía de uso. El clon solo es necesario para **contribuir al núcleo** (ver [Contribuir al núcleo](#contribuir-al-núcleo-mantenedores)).

## Conectarse al workspace del equipo

Si tu equipo ya tiene un **repo workspace** (overlay + `changes/` + `personal/` centralizados), no creás nada: lo conectás. Tres pasos:

```
/plugin marketplace add stradinov/neb      # + /plugin install neb@neb (una vez)
git clone <repo-workspace-del-equipo> && cd <repo>
/wakeup
```

`/wakeup` detecta que el clon ya es un workspace (markers estructurales: `*/overlays/detect-profile.local.sh` — el mismo criterio que usa el hook en runtime) y ofrece **conectarlo**: setea `NEB_WORKSPACE` en tu `settings.json` y crea tu `personal/<usuario>.md` si falta. El paso final real es **abrir una sesión nueva** de Claude Code: ahí el hook ya inyecta el arranque con el overlay de tu equipo.

## Montar tu overlay

`neb` es el núcleo y lo consumís vía el plugin instalado. Lo tuyo —profiles de dominio, agents/skills propios, preferencias— vive en una capa aparte (*overlay*), **nunca dentro de `neb/`**, para poder actualizar el núcleo (el plugin) sin conflictos. Montar el overlay es el **paso mínimo para usar Neb**: sin él no tenés dónde definir tu primer profile.

El overlay es un directorio propio (`overlay/`, `personal/`, `changes/`) en tu repo de gobernanza o en tu workspace; no necesita ser un subtree de `neb/` para usar Neb. El tour `/wakeup` lo monta por vos vía `setup-workspace.sh`.

```
tu-workspace/
├── overlay/    ← tus profiles/agents/skills de dominio
├── personal/   ← tu config personal (gitignored por defecto)
├── changes/    ← tus change MDs
└── CLAUDE.md   ← importa tus profiles de dominio (el arranque del núcleo lo inyecta el plugin)
```

> El layout con `neb/` como **subtree** del repo y el flujo `git subtree add/pull/push` corresponden al modelo de **contribución al núcleo**, no de uso — ver [Contribuir al núcleo](#contribuir-al-núcleo-mantenedores).

### Configurar el entorno

El tour `/wakeup` corre el script de setup por vos (idempotente — seguro de repetir, sirve para reset o migración). El script (`setup-workspace.sh`, viene con el plugin) crea lo que falte (`overlay/`, `personal/`, `changes/`) y setea **dos variables** en tu shell profile (con backup):

| Variable | Apunta a | Para |
|---|---|---|
| `NEB_HOME` | el directorio del plugin instalado | hooks (`$NEB_HOME/hooks`), templates y bootstrap del núcleo |
| `NEB_WORKSPACE` | la raíz de tu workspace de gobernanza | tu overlay, `personal/`, `changes/` |

Reiniciá tu shell para que tomen efecto. El script detecta un overlay preexistente y no lo pisa; el flag `--overlay <nombre>` solo nombra uno nuevo si no hay ninguno (default `overlay`).

## Definir tu primer profile

Un *profile* concreta Neb para un tipo de proyecto (comandos de build, convenciones de commit, proceso de deploy, revisores aplicables) — es lo que hace a Neb útil para tu dominio. Materializalo en **tu overlay**, no en `neb/`.

```bash
bash bootstrap/init-profile-subproject.sh <nombre>
```

Genera el scaffold con los archivos mínimos. Referencia completa: [`methodology/profiles.md`](../methodology/profiles.md).

Definir un profile **puede implicar** crear capacidades de apoyo:

### Skill de apoyo al profile

Un skill carga conocimiento de dominio cuando Claude lo necesita (mapas de código, convenciones específicas, troubleshooting).

1. Crear `skills/<nombre>/SKILL.md` con los campos `name` y `description`.
2. Agregar archivos de contenido y scripts si aplica.
3. Registrar en `skills/README.md` y en el profile correspondiente.

El agente los descubre automáticamente.

### Agentes revisores del profile

Un profile puede definir revisores adversariales propios (por dimensión: seguridad, datos, convenciones) que actúan en el plan-review.

1. Crear `agents/<nombre>.md` con los campos `name`, `description` y `tools`.
2. El cuerpo constituye el system prompt del rol.

Los agents se auto-descubren del plugin: basta con crear el `agents/<nombre>.md`. Tras agregarlo, `/reload-plugins` lo carga sin reiniciar; en sesión nueva ya está.

## Versionar tu configuración personal

`personal/<usuario>.md` guarda tus preferencias, atajos y overrides individuales (qué son y su contrato "estrecha o agrega, nunca relaja": ver [how-it-works § Personalización](how-it-works.md) y [`methodology/personal-vs-team.md`](../methodology/personal-vs-team.md)). Viene **gitignored** — tu configuración no se publica ni sale del plugin.

Si querés versionarla (respaldo, portabilidad entre máquinas), quitá la regla `personal/` de **tu** `.gitignore` (no del de `neb/`) y commiteala en tu repo privado. Excluí binarios (`*.wav` y similares). Sus cambios se trazan con el commit normal; no llevan change MD.

## Contribuir al núcleo (mantenedores)

Lo anterior cubre **usar** Neb. **Contribuir al núcleo** —corregir o extender lo que vive en el repo neb, no tu overlay— es un rol de mantenedor y requiere un **clon normal del repo**, separado de tu workspace:

```bash
git clone https://github.com/stradinov/neb ~/neb   # o donde prefieras
cp ~/neb/hooks/pre-push-changelog ~/neb/.git/hooks/pre-push   # gate del CHANGELOG
```

Flujo: editás en el clon, fragment de CHANGELOG (`changelog.d/<version>.md` + `bootstrap/assemble-changelog.py`) y `git push` directo (fork + PR si no tenés write). Para **dogfoodear** tus cambios antes de publicarlos, apuntá `NEB_HOME` al clon (el hook `SessionStart` prefiere `NEB_HOME` sobre el cache del plugin) o corré `claude --plugin-dir <clon>`.

El clon del núcleo y tu workspace son repos **independientes**: el núcleo se actualiza con `git pull` sin tocar lo tuyo. (El layout histórico de `neb/` como `git subtree` dentro de un repo de gobernanza sigue siendo posible, pero ya no es el camino recomendado — un clon separado es más simple y el push no requiere `subtree split`.)
