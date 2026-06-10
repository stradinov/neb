# Changelog

Todos los cambios relevantes a esta metodología quedan registrados aquí. Formato: [keep a changelog](https://keepachangelog.com/en/1.1.0/). Versionado SemVer.

## [Unreleased]

## [2.0.2] - 2026-06-09

### Changed

- **Quitado el prompt de username del install** — se eliminó `userConfig.username` de `plugin.json`. Pedía un "nombre de usuario Neb" al instalar, lo cual confundía y era opcional. El hook `SessionStart` deriva el identificador de `personal/<username>.md` directamente del usuario del SO (`$USER` / `$USERNAME`). La consistencia cross-máquina (mismo identificador aunque el usuario del SO difiera entre máquinas) queda como mejora futura.

## [2.0.1] - 2026-06-09

### Fixed

- **`plugin install` clona por HTTPS** — el `source` del plugin en `.claude-plugin/marketplace.json` pasó de `{"source":"github","repo":"stradinov/neb"}` a `{"source":"url","url":"https://github.com/stradinov/neb.git"}` (URL HTTPS explícita). Con `source: github`, `claude plugin install` clonaba por **SSH sin fallback a HTTPS** (a diferencia de `marketplace add`), y fallaba con "Host key verification failed" en máquinas con git orientado a SSH o sin la host key de github.com — incluso para un repo público. La URL HTTPS explícita fuerza el clone anónimo. (Si la máquina del adoptante tiene además un rewrite git `insteadOf` https→ssh, debe resolverlo en su entorno: `ssh-keyscan github.com >> ~/.ssh/known_hosts` o quitar el rewrite.)

## [2.0.0] - 2026-06-09

Cambio mayor: Neb pasa del modelo "clone" (imports `@import` en cada `CLAUDE.md`) a un **plugin de Claude Code** que inyecta el arranque por un hook `SessionStart`.

### Added

- **Plugin de Claude Code**: manifests `.claude-plugin/{plugin.json,marketplace.json}` + `hooks/hooks.json` (`SessionStart`, matchers `startup`/`compact`). Al instalar el plugin, el hook inyecta el arranque (framework + overlay + personal) con peso vinculante; skills/agents/commands se auto-descubren.
- `bootstrap/neb-bootstrap-context.py` — orquestador del arranque (ensambla framework desde `$NEB_HOME` + overlay y personal desde `$NEB_WORKSPACE`).
- `bootstrap/assemble-startup.py` — resuelve los `@import` del arranque y reescribe links relativos a rutas absolutas.
- `bootstrap/set-neb-env.py` — merge no-destructivo de `NEB_HOME`/`NEB_WORKSPACE` en `settings.json`.
- `bootstrap/setup-workspace.sh` — crea el workspace del adoptante (overlay + personal + changes) en modos default/`--base`/`--existing`.
- `bootstrap/bump-version.sh` — bump SemVer + sync `plugin.json.version` + fragment de CHANGELOG.
- Marcador **`<!-- neb: skip -->`** activo: el hook lo detecta en el `CLAUDE.md` del proyecto (vía `CLAUDE_PROJECT_DIR`) y no inyecta el arranque (opt-out por proyecto).
- `general/startup.md` ahora incluye `workflow/index.md` (mapa de workflow + ENUM de estados, always-on).

### Changed

- **BREAKING — modelo de consumo**: el arranque se inyecta por el hook `SessionStart`, **no** por `@import` del framework en cada `CLAUDE.md`. Los `CLAUDE.md` de proyecto ya no importan `general/startup.md` ni `workflow/index.md`; conservan solo imports de stack + contenido propio.
- **Adopción**: `/plugin marketplace add` + `/plugin install` + `/wakeup` (reemplaza el flujo `install.sh` + `link-into-project.sh`).
- Comando del hook portable cross-OS: `python` con fallback a `python3`.
- Scaffolders overlay-aware (`init-stack-subproject.sh` default→overlay, `--core`); `install-{skills,agents}.sh` con glob dinámico + extension point de overlay.

### Deprecated

- Modelo "clone": `bootstrap/install.sh`, `link-into-project.sh`, `install-skills.sh`, `install-agents.sh` quedan marcados `[DEPRECADO]` (se conservan para referencia). El plugin auto-descubre skills/agents y el hook reemplaza el enganche por `@import` en `CLAUDE.md`.

## [1.5.0] — 2026-06-03

### Added

- **`bootstrap/setup-workspace.sh`** — idempotent setup of an adopter's governance workspace: scaffolds the overlay (`overlays/detect-stack.local.sh` stub), `personal/` and `changes/`, sets the environment variables in the shell profile (with backup), and verifies `~/CLAUDE.md` without overwriting it. Flags `--overlay <name>` and `--dry-run`. Covers new adopters, migration from an older layout, and reset.
- **Two canonical environment variables** — `NEB_HOME` (the neb checkout: hooks at `$NEB_HOME/hooks`, templates, bootstrap) and `NEB_WORKSPACE` (the governance root: overlay, `personal/`, `changes/`). Documented in `docs/user-guide.md` § "Configurar el entorno".

### Changed

- **`bootstrap/link-into-project.sh`** — the private overlay is now discovered generically: a glob over `$NEB_WORKSPACE/*/overlays/detect-stack.local.sh` (falling back to `dirname(NEB_HOME)`), replacing the previously hardcoded path. An adopter's overlay is picked up regardless of its directory name, without editing the nucleus.
- **`skills/wakeup`** — the tour delegates environment detection and setup to `setup-workspace.sh` (`--dry-run` to detect, then a real run to configure) instead of re-implementing the detection logic.

## [1.4.0] — 2026-06-03

### Changed

- **Adoption/onboarding model reworked.** `docs/user-guide.md` is now the single source for the adoption steps (install → mount overlay → define your first stack, with a support skill and reviewer agents as derivatives of the stack). `general/onboarding.md` no longer spells out the tour steps — it defines only the passive-offer trigger and lists the options that point to the user guide. The tour skill executes those steps interactively, with installation-state detection (installed / overlay mounted / propose reinstall).
- **`welcome` skill renamed to `wakeup`** — the command is now `/wakeup` (Matrix/Nebuchadnezzar theme: "wake up"). Adopters who installed the old `welcome` skill should re-run `bootstrap/install-skills.sh`; the stale `welcome/` skill dir can be removed.

### Removed

- **Adoption levels (L1/L2/L3) removed.** The tour no longer asks the user to choose an adoption level; the construct was never wired to runtime behavior. Mounting an overlay and defining a stack is now the minimal setup to use neb.
- **Promise #8 ("Adopción guiada" / incremental adoption) removed** from `methodology/promises.md` (a user-facing contract change). The remaining promises were renumbered 9→8, 10→9, 11→10 — the framework now declares 10 promises.

## [1.3.0] — 2026-06-03

### Added

- **`docs/user-guide.md`** — adopter how-to guide: mounting your own overlay (git subtree), adding stacks/skills/subagents, versioning your `personal/` config, and where change MDs live. Extracts the "how-to" content from `docs/how-it-works.md` (Diátaxis split: explanation vs. how-to).
- **`docs/` layer documented** — `methodology/principles.md` and `general/index.md` now state that `docs/` (adopter-facing documentation) sits outside the layer-pertinence test; its files are not classified as Methodology/Process.

### Changed

- **`docs/how-it-works.md`** — now explanation-only; the extension how-to moved to `user-guide.md`.

## [1.2.0] — 2026-06-02

### Added

- **`link-into-project.sh` overlay hooks** — three stub functions (`detect_stack_local`, `get_private_stack_imports`, `get_framework_imports`) allow adopters to extend stack detection and import generation without modifying the nucleus. The script sources `<neb-parent>/onibex/overlays/detect-stack.local.sh` when present (sibling-dir convention for neb-as-subtree deployments). Implements P8 (Expandible) for `link-into-project.sh`.

### Fixed

- **`hooks/pre-push-changelog`** — hook auto-detects when `neb` is a git subtree inside a parent repo (checks for `$ROOT/neb/changelog.d`). Previously used hardcoded `$ROOT/bootstrap/assemble-changelog.py` which broke when neb lives under a `neb/` prefix. Now selects the correct `ASSEMBLER` and `CHANGELOG_D` path automatically.

## [1.1.0] - 2026-06-03

### Changed
- **Anti-desviación al núcleo always-on**: `process/phase-transitions.md` ahora establece que, ante una instrucción de implementación o entrega, Claude entra a Propuesta (clarifica + plan) y **no crea ni edita archivos del entregable hasta la aprobación del dev** — regla always-on (cargada vía `@import` desde `general/startup.md`), independiente de `personal/<usuario>.md`. Antes la regla vivía solo en `process/execution.md` (on-demand), por lo que un install limpio sin overrides personales podía saltar directo a editar.

### Fixed
- **Path de hooks en `settings.json`**: los templates usaban `$NEB_HOME/hooks/...`, que resolvía a `/hooks/...` cuando la variable no estaba en el entorno de la sesión de Claude. Ahora usan `${NEB_HOME:-$HOME/.claude/neb}/hooks/...` (fallback a la ruta convencional del clon). Corrige el `Stop hook error: /hooks/usage-tracker.sh: No such file or directory`.

## [1.0.0] - 2026-06-02

Primera versión pública de **neb** — corte open source del núcleo del framework.

### Added
- Núcleo agnóstico del framework: `general/`, `methodology/`, `process/`, `workflow/`, `tooling/`.
- Stacks publicables: `self-applied`, `requirements-analysis`, `stack-authoring`, `skill-authoring`, `research`.
- Subagentes revisores transversales: `qa-process-engineer`, `process-improvement-analyst`, `skill-qa-engineer`, `fact-check-reviewer`, `context-completeness-reviewer`.
- Skill de bienvenida (`/welcome`) para onboarding guiado.
- Andamiaje OSS: `LICENSE` (MIT), `README`, `CONTRIBUTING`.
- Instalador Modelo A (`bootstrap/install.sh`): clona el repo, enlaza los `@import` en el `CLAUDE.md` del adoptante e instala skills, agents y hooks.
- Plantillas de artefactos (`templates/`) y hooks de soporte (`hooks/`).

### Notes
- Esta versión publica una **copia saneada** del núcleo; el set público no contiene PII, marcas ni stacks de dominio privados.
- Idioma de los lineamientos: español (la traducción a inglés es trabajo futuro).
