# Versionado y entrega con git

Concretización **git** del mecanismo de versionamiento: formato de commits, push, ramas, CHANGELOG. La política universal y agnóstica del mecanismo (ownership de `.md`, acciones destructivas, punto de restauración) vive en [`../methodology/change-control-policy.md`](../methodology/change-control-policy.md); el gate de autorización en Fase 4 vive en [`../process/change-control-gate.md`](../process/change-control-gate.md) — este archivo concretiza ambos para git. Aplica a profiles que usan git; un profile con otro mecanismo lo concretiza en su `profiles/<profile>/deployment.md`.

## Commits

El formato del mensaje, los tipos y las prohibiciones (`--no-verify`, `--force`/`reset --hard` en rama principal, `git add -A`) viven en [`../methodology/git-conventions.md`](../methodology/git-conventions.md) — punto de customización del adoptante. Esta sección cubre las **operaciones** git que materializan los gates del proceso.

### Commit local en Fase 4 — concretización git

El principio del gate (OK explícito antes de confirmar un cambio del entregable en Fase 4; granularidad por confirmación; excepciones `self-applied`, autonomía declarada por proyecto y solo-`.md`) vive en [`../process/change-control-gate.md`](../process/change-control-gate.md) § "Autorización de la confirmación del cambio". En git, "confirmar" = `git commit` local; el OK aplica por cada `git commit` separado.

Exclusión propia del mecanismo git — el gate **no aplica** a los artefactos de gobernanza del REQ: el propio change MD, bump de `VERSION`, regeneración de `CHANGELOG.md`, fragmentos en `changelog.d/`. Estos se agrupan en el commit de cierre del REQ.

### Autonomía de Claude sobre archivos `.md` — operaciones git

El principio (Claude es dueño operativo de los **artefactos que Neb genera** y, derivadamente, de cualquier `.md`; las confirmaciones que tocan **exclusivamente** esos artefactos —o solo `.md`— no requieren OK en ninguna fase ni profile) vive en [`../methodology/change-control-policy.md`](../methodology/change-control-policy.md) § "Ownership de archivos `.md`". En git, ese principio cubre estas operaciones cuando el delta toca solo archivos `.md`:

- **Cubre**: `git commit`, `git push`, creación de ramas, `git merge`, `git rebase` sobre rama propia, `git cherry-pick`, y operaciones destructivas (`reset --hard`, `branch -D`, `push --force` sobre ramas distintas a `main`/`master`) en cualquier path del repo (`changes/`, `research/`, `reqs/<algo>/`, `README.md`, `docs/`, `CHANGELOG.md`, `CLAUDE.md`, etc.). Creación y edición.
- **No cubre** (requiere OK pese a tocar solo `.md`):
  - `push --force` a `main`/`master` — mantiene warn + OK por el prompt de sistema de Claude Code.
  - Commits/pushes mixtos `.md` + código — el commit completo pide OK por el componente más restrictivo (código); la autonomía sobre `.md` no contagia al resto.
  - Memorias personales del dev en `~/.claude/projects/<machine>/memory/*.md` — Claude propone deltas inline; el dev los aplica ("No editar a mano" del `CLAUDE.md` raíz del repo).
  - **Segmentos de contenido humano** (`<!-- human -->` … `<!-- /human -->`) dentro de un `.md` — el bloque marca contenido bajo control directo de un humano, cuya voz e intención no se alteran sin él; modificarlo requiere OK explícito aunque el commit sea solo-`.md` (Claude propone deltas inline). La autonomía cubre el resto del archivo. Ver [`../methodology/change-control-policy.md`](../methodology/change-control-policy.md) § "Ownership de archivos `.md`".
  - `.md` de upstream en repos fork de proyectos externos (ej. el `CHANGELOG.md` y `README.md` del core de un framework de terceros forkeado). La autonomía cubre solo `.md` agregados por el equipo al fork.
  - Operaciones git no rutinarias sobre tags publicados, `git revert` de commits ajenos publicados, reescritura de historia compartida.
- **Caso mixto — recomendación operativa**: cuando sea posible separar en commits atómicos por categoría (uno solo-`.md` autónomo + uno de código con OK), Claude prefiere la separación. Si la atomicidad lógica exige un solo commit (código y su `README.md`), Claude pide OK por el commit mixto y comunica al dev que el `.md` quedó arrastrado al gate del código.
- **No relaja otros lineamientos**: `--no-verify` sigue prohibido sin autorización (§ Commits); pre-commit y pre-push hooks deben pasar; mensajes en formato `tipo: descripción` (español, máx. 72 caracteres); `git add` por nombre, no `-A`.

## Push

- Verificar la rama principal del proyecto (varía: `master`, `main`, etc.).
- Push solo cuando el usuario confirma y los cambios fueron validados.
- **Excepción — push `.md`-only**: si los commits que arrastra el push tocan solo archivos `.md`, no requiere OK del dev (ver § Commits "Autonomía de Claude sobre archivos `.md`"). `push --force` a `main`/`master` mantiene su gate.
- **Antes de validar** (entregable): solo recordar al usuario hacer commit; no solicitar push. Aplica al **entregable**, no al **registro del requerimiento** (change MD — ver [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Registro del requerimiento"): la entrega temprana del registro (bullet abajo) es independiente del gate de validación del entregable.
  - **Profiles de proceso (`self-applied` y overlays)**: el entregable es `.md` ⇒ commit y push autónomos por el ownership de `.md` (no por una validación diferida — se eliminó). Se entrega tras validación (roles + coherencia) y cierre, **inmediatos**; no hay push diferido. Si el entregable incluye código (hooks/scripts), ese componente sí pide OK (ver § Commits "Caso mixto").
- **Entrega temprana del registro del requerimiento**: el registro (change MD — ver [`../workflow/changes.md`](../workflow/changes.md) § "Ciclo de vida del draft") puede **confirmarse y entregarse (push) de forma autónoma desde que existe el draft** (al aprobar el plan / entrada a Fase 4), **desacoplado** de la entrega del entregable. Es `.md`-only ⇒ autónomo por la § Commits "Autonomía de Claude sobre archivos `.md`"; no requiere OK del dev. **Condición — entorno de validación compartido**: **disparador determinista** (desde el backend central del logbook, ver [`../workflow/logbook.md`](../workflow/logbook.md) § "Entorno compartido"): el entorno es compartido cuando hay `NEB_LOGBOOK_ENDPOINT` configurado **y** el proyecto declaró opt-in (marcador `<!-- neb-logbook: central -->` en su `CLAUDE.md`); entonces el `work` se publica a la bitácora compartida y el registro debe quedar **entregado (pusheado)** para que el puntero de la entrada resuelva en la máquina que releva. Si **no** es compartido (sin endpoint o sin el marcador), el registro se confirma/entrega en el cierre del REQ. No relaja el gate del **entregable**, que sigue su validación/cierre. `push --force` a `main`/`master` mantiene su gate.
- **Después de validar**: preguntar si hacer commit y push.
- Entrega final y acciones que afectan a otros (PRs, force push): siempre confirmar.
- **Push a entrega final sin validación**: Claude detecta y ofrece asistir con las pruebas. El dev acepta, valida por su cuenta, o confirma que ya fue validado fuera de sesión.
- **Si el dev pide push en cualquier momento**: Claude sugiere primero actualizar el registro del requerimiento (change MD); el push `.md`-only de ese registro es autónomo (ver "Entrega temprana del registro del requerimiento" arriba).

## Comandos de entrega a servidores

`pscp`, `ssh` y similares no son comandos locales — forman parte del proceso de entrega del profile (ver `profiles/<profile>/deployment.md`). Siguen el modelo del contexto activo, no Haiku.

## Rama principal por profile

- `self-applied`: `main` o la rama principal del repo de metodología.
- Un profile de software puede usar `master` u otra rama; lo declara en su `profiles/<profile>/deployment.md` (override por proyecto).
- Otros profiles: declarar en `profiles/<profile>/deployment.md`.

## CHANGELOG fragmentado (profile `self-applied`)

Aplicable a repos que mantienen `CHANGELOG.md` y son trabajados por sesiones paralelas del mismo dev. Caso canónico: el propio repo `neb`.

`CHANGELOG.md` es generado y administrado por Claude en cada REQ — el dev no lo edita directamente.

### Motivación

Un solo `CHANGELOG.md` con orden DESC es punto de conflicto entre sesiones paralelas: ambas reclaman el "tope" del archivo. Patrones de fallo observados con el modelo de archivo único: huecos de versión aceptados cuando dos REQs avanzan en paralelo, drift entre `VERSION` y `CHANGELOG` (una sesión bumpea el entry y olvida `VERSION`), y correcciones retroactivas del orden de dos releases cercanos.

### Estructura

- `changelog.d/<X.Y.Z>.md` — un archivo por release. Contenido: el bloque del entry tal como aparecería en `CHANGELOG.md` (incluye el header `## [X.Y.Z] — YYYY-MM-DD` + secciones `### Added`/`### Changed`/`### Notas`).
- `bootstrap/assemble-changelog.py` — ensamblador que lee `changelog.d/*.md`, ordena por SemVer DESC y reescribe `CHANGELOG.md`.
- `CHANGELOG.md` — versionado, regenerado por el ensamblador. Visible en remote para consumidores que clonan o navegan.

### Flujo al cerrar REQ

Claude ejecuta estos pasos como parte de Fase 6/7, antes del push del REQ:

1. Crear `changelog.d/<X.Y.Z>.md` con el entry del REQ. Naming: el stem del archivo es la versión SemVer en `<major>.<minor>.<patch>` (sin prefijo `v`).
2. Bumpear `VERSION` al mismo número.
3. Correr `py bootstrap/assemble-changelog.py` — regenera `CHANGELOG.md`.
4. `git add changelog.d/<X.Y.Z>.md CHANGELOG.md VERSION` (más archivos del REQ) y commit.

### Gate pre-push

El git hook `.git/hooks/pre-push` del repo `neb` (lo instala el maintainer: `cp hooks/pre-push-changelog .git/hooks/pre-push`) corre `assemble-changelog.py --check` antes de cada push que toca `changelog.d/`. Si retorna 1:

- El push aborta con mensaje claro.
- Claude (leyendo el mensaje del hook) regenera (`py bootstrap/assemble-changelog.py`), hace commit de `CHANGELOG.md` como commit final del REQ y reintenta push.

Bypass: `git push --no-verify` — requiere autorización explícita del dev (ver § Commits).

### Resolución de colisión de versión

Dos sesiones paralelas pueden crear `changelog.d/1.5.0.md` cada una con contenido distinto, o ambas bumpear `VERSION` al mismo valor. Reglas:

- La primera en cerrar Fase 4 hace commit primero y reclama el número.
- La segunda renombra su fragmento al siguiente valor disponible (e.g. `changelog.d/1.5.0.md` → `changelog.d/1.6.0.md`) y bumpea `VERSION` al mismo valor.
- Un hueco en la historia (e.g. v1.5.0 saltado entre v1.4.0 y v1.6.0) es aceptable y no se reescribe historia.
- `VERSION` sigue siendo single-line por convención SemVer; la colisión sobre `VERSION` es trivial (1 número, primera en hacer commit gana).
