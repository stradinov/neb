# Guía del usuario — extender y adoptar neb

Cómo usar neb en tu equipo: montar tu capa propia, agregar capacidades y versionar lo tuyo **sin tocar el núcleo**. Para entender *cómo funciona* el framework por dentro, ver [how-it-works.md](how-it-works.md).

## Montar tu overlay

`neb` es el núcleo y lo actualizás como *upstream*. Lo tuyo —stacks de dominio, agents/skills propios, preferencias— vive en una capa aparte (*overlay*), **nunca dentro de `neb/`**, para poder actualizar el núcleo sin conflictos.

**Con git subtree** (recomendado para equipos): un repo de gobernanza propio con `neb/` como subtree + tu overlay:

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

## Extender — agregar capacidades

El núcleo no requiere modificación para incorporar capacidades nuevas; materializalas en **tu overlay**, no en `neb/`.

### Nuevo stack

```bash
bash bootstrap/init-stack-subproject.sh <nombre>
```

Genera el scaffold con los archivos mínimos. Referencia completa: [`methodology/stacks.md`](../methodology/stacks.md).

### Nuevo skill

1. Crear `skills/<nombre>/SKILL.md` con los campos `name` y `description`.
2. Agregar archivos de contenido y scripts si aplica.
3. Registrar en `skills/README.md` y en el stack correspondiente.

El agente los descubre automáticamente.

### Nuevo subagente revisor

1. Crear `agents/<nombre>.md` con los campos `name`, `description` y `tools`.
2. El cuerpo constituye el system prompt del rol.
3. Registrar en `bootstrap/install-agents.sh`.

## Versionar tu configuración personal

`personal/<usuario>.md` guarda tus preferencias, atajos y overrides individuales (qué son y su contrato "estrecha o agrega, nunca relaja": ver [how-it-works § Personalización](how-it-works.md) y [`methodology/personal-vs-team.md`](../methodology/personal-vs-team.md)). Viene **gitignored** — tu configuración no se publica ni viaja al clonar.

Si querés versionarla (respaldo, portabilidad entre máquinas), quitá la regla `personal/` de **tu** `.gitignore` (no del de `neb/`) y commiteala en tu repo privado. Excluí binarios (`*.wav` y similares). Sus cambios se trazan con el commit normal; no llevan change MD.

## Dónde van tus change MDs

Cada requerimiento se documenta con un change MD en `<proyecto>/changes/` (ver [how-it-works § Artefactos](how-it-works.md)):

- Cambios a **tu overlay** o **tu repo de gobernanza** → su `changes/`.
- Cambios a un **proyecto** donde aplicás neb → `<app>/changes/`.
- El **núcleo `neb`** no usa change MDs: su historia pública es el `CHANGELOG`. Si contribuís al núcleo, viajan el cambio + su entrada de `CHANGELOG`; el *por qué* detallado lo documentás en el `changes/` de tu repo.
