# Guía del usuario — adoptar y extender Neb

Cómo poner Neb a trabajar en tu equipo: instalarlo, montar tu capa propia y definir tu primer stack — todo **sin tocar el núcleo**. Para entender *cómo funciona Neb* por dentro, ver [how-it-works.md](how-it-works.md).

## Instalar

```bash
# 1. Clona el repo
git clone https://github.com/tu-org/neb.git ~/.claude/neb

# 2. Corre el instalador (una vez por máquina)
bash ~/.claude/neb/bootstrap/install.sh
```

Luego abrí Claude Code y escribí `/wakeup` — el tour te guía por los pasos de abajo.

## Montar tu overlay

`neb` es el núcleo y lo actualizás como *upstream*. Lo tuyo —stacks de dominio, agents/skills propios, preferencias— vive en una capa aparte (*overlay*), **nunca dentro de `neb/`**, para poder actualizar el núcleo sin conflictos. Montar el overlay es el **paso mínimo para usar Neb**: sin él no tenés dónde definir tu primer stack.

**Con git subtree** (recomendado): un repo de gobernanza propio con `neb/` como subtree + tu overlay:

```
tu-repo/
├── neb/        ← núcleo (subtree del repo público; no lo editás para meter lo tuyo)
├── overlay/    ← tus stacks/agents/skills de dominio
├── changes/    ← tus change MDs
└── CLAUDE.md   ← importa neb/ + tu overlay/
```

Setup y mantenimiento:

```bash
git remote add neb <url-del-repo-neb>
git subtree add  --prefix neb/ neb main --squash   # traer el núcleo
git subtree pull --prefix neb/ neb main --squash   # actualizarlo
git subtree push --prefix neb/ neb main            # contribuir al núcleo (opcional; solo viaja neb/)
```

El `--squash` mantiene tu historia limpia. Tu overlay y `neb/` quedan en árboles separados: el núcleo se actualiza sin tocar lo tuyo.

**Camino simple**: forkeás `neb` y traés mejoras con `git pull` del upstream — sirve para empezar, pero mezcla tu historia con la del núcleo.

## Definir tu primer stack

Un *stack* concreta Neb para un tipo de proyecto (comandos de build, convenciones de commit, proceso de deploy, revisores aplicables) — es lo que hace a Neb útil para tu dominio. Materializalo en **tu overlay**, no en `neb/`.

```bash
bash bootstrap/init-stack-subproject.sh <nombre>
```

Genera el scaffold con los archivos mínimos. Referencia completa: [`methodology/stacks.md`](../methodology/stacks.md).

Definir un stack **puede implicar** crear capacidades de apoyo:

### Skill de apoyo al stack

Un skill carga conocimiento de dominio cuando Claude lo necesita (mapas de código, convenciones específicas, troubleshooting).

1. Crear `skills/<nombre>/SKILL.md` con los campos `name` y `description`.
2. Agregar archivos de contenido y scripts si aplica.
3. Registrar en `skills/README.md` y en el stack correspondiente.

El agente los descubre automáticamente.

### Agentes revisores del stack

Un stack puede definir revisores adversariales propios (por dimensión: seguridad, datos, convenciones) que actúan en el plan-review.

1. Crear `agents/<nombre>.md` con los campos `name`, `description` y `tools`.
2. El cuerpo constituye el system prompt del rol.
3. Registrar en `bootstrap/install-agents.sh`.

## Versionar tu configuración personal

`personal/<usuario>.md` guarda tus preferencias, atajos y overrides individuales (qué son y su contrato "estrecha o agrega, nunca relaja": ver [how-it-works § Personalización](how-it-works.md) y [`methodology/personal-vs-team.md`](../methodology/personal-vs-team.md)). Viene **gitignored** — tu configuración no se publica ni viaja al clonar.

Si querés versionarla (respaldo, portabilidad entre máquinas), quitá la regla `personal/` de **tu** `.gitignore` (no del de `neb/`) y commiteala en tu repo privado. Excluí binarios (`*.wav` y similares). Sus cambios se trazan con el commit normal; no llevan change MD.
