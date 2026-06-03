# Changelog

Todos los cambios relevantes a esta metodología quedan registrados aquí. Formato: [keep a changelog](https://keepachangelog.com/en/1.1.0/). Versionado SemVer.

## [Unreleased]

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
