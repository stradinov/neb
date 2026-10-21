# Versionado y entrega con git

Concretización **git** del mecanismo de versionamiento: formato de commits, push, ramas, CHANGELOG. La política universal y agnóstica del mecanismo (ownership de `.md`, acciones destructivas, punto de restauración) vive en [`../methodology/change-control-policy.md`](../methodology/change-control-policy.md); el gate de autorización en Fase 4 vive en [`../process/change-control-gate.md`](../process/change-control-gate.md) — este archivo concretiza ambos para git. Aplica a profiles que usan git; un profile con otro mecanismo lo concretiza en su `profiles/<profile>/deployment.md`.

## Commits

El formato del mensaje, los tipos y las prohibiciones (`--no-verify`, `--force`/`reset --hard` en rama principal, `git add -A`) viven en [`../methodology/git-conventions.md`](../methodology/git-conventions.md) — punto de customización del adoptante. Esta sección cubre las **operaciones** git que materializan los gates del proceso.

### Commit local en Fase 4 — concretización git

El principio del gate (OK explícito antes de confirmar un cambio del entregable en Fase 4; granularidad por confirmación; excepciones `self-applied`, autonomía declarada por proyecto, solo-`.md` y confirmación autónoma declarada por el adoptante) vive en [`../process/change-control-gate.md`](../process/change-control-gate.md) § "Autorización de la confirmación del cambio". En git, "confirmar" = `git commit` local; el OK aplica por cada `git commit` separado, salvo los que califican para una excepción.

Exclusión propia del mecanismo git — el gate **no aplica** a los artefactos de gobernanza del REQ: el propio change MD, bump de `VERSION`, regeneración de `CHANGELOG.md`, fragmentos en `changelog.d/`. Estos se agrupan en el commit de cierre del REQ.

### Confirmación autónoma — concretización git

Concreta en git el piso de [`change-control-gate.md`](change-control-gate.md) § "Excepción — confirmación autónoma declarada por el adoptante":

- **Comando**: `git --literal-pathspecs commit --only -m "<mensaje>" --trailer "Confirmacion-autonoma: <slug-del-requerimiento>" -- '<ruta1>' '<ruta2>' …`, con las rutas exactas del plan (sin directorios ni globs) y sin `git add` previo. Los modificados y los borrados (quitados del working tree, sin `git rm`) se confirman directo; un archivo nuevo lleva `git add --intent-to-add -- <nuevo>` en el mismo comando, justo antes del commit; un renombre se hace como borrado más alta, con las dos rutas en el pathspec (sin `git mv`). Nunca `-A`, `-a`, índice alterno ni stage parcial (`add -p`, `apply --cached`): `--only` toma el archivo completo del working tree.
- **Procedencia** (condición 3): antes de la primera edición de cada ruta, `git diff --quiet HEAD -- <ruta>` y `git diff --cached --quiet -- <ruta>` terminan en 0 (si no, esa ruta pide OK) y se anota la base (`git rev-parse HEAD`); para un archivo nuevo, además `test ! -e <ruta>` (un archivo sin trackear que dejó otra sesión en esa ruta pide OK). Tras los gates se fija `git hash-object -- <ruta>`. Justo antes del commit, en un comando aparte cuya salida se lee antes de seguir: el hash coincide, `git log --format=%H <base>..HEAD -- <rutas>` no lista commits ajenos y `git status --porcelain` completo no trae cambios inesperados en esas rutas.
- **Delta íntegro** (condición 4): `git diff --numstat HEAD -- <ruta>` es igual con y sin `--ignore-cr-at-eol`; ningún `-` en numstat (binario); `git diff --summary HEAD` sin `mode change`; ninguna ruta `.gitattributes` ni `.gitignore`; el conteo de bytes `EF BF BD` (carácter de reemplazo, medido en bytes) no sube frente a `git show HEAD:<ruta>`. Un archivo nuevo no está en `HEAD` y `git diff HEAD` no lo ve: se revisa entero, `git diff --no-index --numstat /dev/null <nuevo>` sin `-` (binario), sin bytes CR ni `EF BF BD` que el plan no declare.
- **Secretos** (condición 5): ninguna ruta del delta está en la lista del adoptante, y el patrón `password|passwd|secret|token|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}` (sin distinguir mayúsculas) da 0 coincidencias sobre las líneas `+` de `git diff HEAD -- <rutas>` y sobre el contenido completo de cada archivo nuevo.
- **Rama** (condición 6): la guarda corre en el mismo comando que el commit, `test "$(git symbolic-ref -q --short HEAD)" = "<rama>" && git --literal-pathspecs commit --only …`; con HEAD separado o en otra rama, aborta y se pide OK.
- **Hooks**: sin hooks activos en `$(git rev-parse --git-path hooks)` (sin contar `*.sample`) ni `core.hooksPath` que el adoptante no haya declarado; si los hay, se pide OK.
- **Trailer**: va con `--trailer` (git lo escribe en el último párrafo del mensaje, el único que `%(trailers)` lee; nunca en el asunto ni mezclado con texto).
- **Verificación posterior**: `git diff-tree --no-commit-id --name-status -r HEAD` coincide con las rutas y operaciones del plan, el blob de cada ruta coincide con el hash fijado y `git log -1 --format='%(trailers:key=Confirmacion-autonoma,valueonly)' HEAD` no sale vacío. Si no coinciden, Claude se detiene y reporta; la recuperación con `git reset --soft HEAD~1` pide OK y procede solo si HEAD sigue siendo ese commit y no está en ningún remoto. Un «nothing to commit» no es éxito: se investiga y se reporta.
- El identificador que se reporta y se anota es el SHA.

### Autonomía de Claude sobre archivos `.md` — operaciones git

El principio (Claude es dueño operativo de los **artefactos que Neb genera** y, derivadamente, de cualquier `.md`; las confirmaciones que tocan **exclusivamente** esos artefactos —o solo `.md`— no requieren OK en ninguna fase ni profile) vive en [`../methodology/change-control-policy.md`](../methodology/change-control-policy.md) § "Ownership de archivos `.md`". En git, ese principio cubre estas operaciones cuando el delta toca solo archivos `.md`:

- **Cubre**: `git commit`, `git push`, creación de ramas, `git merge`, `git rebase` sobre rama propia, `git cherry-pick`, y operaciones destructivas (`reset --hard`, `branch -D`, `push --force` sobre ramas distintas a `main`/`master`) en cualquier path del repo (`changes/`, `research/`, `reqs/<algo>/`, `README.md`, `docs/`, `CHANGELOG.md`, `CLAUDE.md`, etc.). Creación y edición.
- **No cubre** (requiere OK pese a tocar solo `.md`):
  - `push --force` a `main`/`master` — mantiene warn + OK por el prompt de sistema de Claude Code.
  - Commits/pushes mixtos `.md` + código — siguen el gate del código (OK, o confirmación autónoma si la parte de código cumple su piso); la autonomía sobre `.md` no contagia al resto.
  - Memorias personales del dev en `~/.claude/projects/<machine>/memory/*.md` — Claude propone deltas inline; el dev los aplica ("No editar a mano" del `CLAUDE.md` raíz del repo).
  - **Segmentos de contenido humano** (`<!-- human -->` … `<!-- /human -->`) dentro de un `.md` — el bloque marca contenido bajo control directo de un humano, cuya voz e intención no se alteran sin él; modificarlo requiere OK explícito aunque el commit sea solo-`.md` (Claude propone deltas inline). La autonomía cubre el resto del archivo. Ver [`../methodology/change-control-policy.md`](../methodology/change-control-policy.md) § "Ownership de archivos `.md`".
  - `.md` de upstream en repos fork de proyectos externos (ej. el `CHANGELOG.md` y `README.md` del core de un framework de terceros forkeado). La autonomía cubre solo `.md` agregados por el equipo al fork.
  - Operaciones git no rutinarias sobre tags publicados, `git revert` de commits ajenos publicados, reescritura de historia compartida.
- **Caso mixto — recomendación operativa**: cuando sea posible separar en commits atómicos por categoría (uno solo-`.md` autónomo + uno de código con OK), Claude prefiere la separación. Si la atomicidad lógica exige un solo commit (código y su `README.md`), Claude pide OK por el commit mixto (o lo confirma de forma autónoma si la parte de código cumple el piso) y comunica al dev que el `.md` quedó arrastrado al gate del código.
- **No relaja otros lineamientos**: `--no-verify` sigue prohibido sin autorización (§ Commits); pre-commit y pre-push hooks deben pasar; mensajes en formato `tipo: descripción` (español, máx. 72 caracteres); `git add` por nombre, no `-A`.

## Push

- Verificar la rama principal del proyecto (varía: `master`, `main`, etc.).
- Push solo cuando el usuario confirma y los cambios fueron validados, salvo la excepción de abajo (push `.md`-only) y la integración autónoma de § "Integración a la rama principal".
- **Excepción — push `.md`-only**: si los commits que arrastra el push tocan solo archivos `.md`, no requiere OK del dev (ver § Commits "Autonomía de Claude sobre archivos `.md`"). `push --force` a `main`/`master` mantiene su gate.
- **Antes de validar** (entregable): solo recordar al usuario hacer commit; no solicitar push. Aplica al **entregable**, no al **registro del requerimiento** (change MD — ver [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Registro del requerimiento"): la entrega temprana del registro (bullet abajo) es independiente del gate de validación del entregable.
  - **Profiles de proceso (`self-applied` y overlays)**: el entregable es `.md` ⇒ commit y push autónomos por el ownership de `.md` (no por una validación diferida — se eliminó). Se entrega tras validación (roles + coherencia) y cierre, **inmediatos**; no hay push diferido. Si el entregable incluye código (hooks/scripts), ese componente sigue el gate del código (OK, o confirmación autónoma si el adoptante la activa y se cumple su piso; ver § Commits "Caso mixto").
- **Entrega temprana del registro del requerimiento**: el registro (change MD — ver [`../workflow/changes.md`](../workflow/changes.md) § "Ciclo de vida del draft") puede **confirmarse y entregarse (push) de forma autónoma desde que existe el draft** (al aprobar el plan / entrada a Fase 4), **desacoplado** de la entrega del entregable. Es `.md`-only ⇒ autónomo por la § Commits "Autonomía de Claude sobre archivos `.md`"; no requiere OK del dev. **Condición — entorno de validación compartido**: **disparador determinista** (desde el backend central del logbook, ver [`../workflow/logbook.md`](../workflow/logbook.md) § "Entorno compartido"): el entorno es compartido cuando hay `NEB_LOGBOOK_ENDPOINT` configurado **y** el proyecto declaró opt-in (marcador `<!-- neb-logbook: central -->` en su `CLAUDE.md`); entonces el `work` se publica a la bitácora compartida y el registro debe quedar **entregado (pusheado)** para que el puntero de la entrada resuelva en la máquina que releva. Si **no** es compartido (sin endpoint o sin el marcador), el registro se confirma/entrega en el cierre del REQ. No relaja el gate del **entregable**, que sigue su validación/cierre. `push --force` a `main`/`master` mantiene su gate.
- **Después de validar**: preguntar si hacer commit y push. La integración autónoma de § "Integración a la rama principal" quita solo el OK del push de integración; el OK del commit lo rige [`change-control-gate.md`](change-control-gate.md) § "Autorización de la confirmación del cambio", incluida la confirmación autónoma cuando el adoptante la activa.
- Entrega final y acciones que afectan a otros (PRs, force push): siempre confirmar. Además de la excepción `.md`-only de arriba, la integración autónoma de § "Integración a la rama principal" quita el OK del push de integración; nunca cubre un force push ni una entrega final.
- **Push a entrega final sin validación**: Claude detecta y ofrece asistir con las pruebas. El dev acepta, valida por su cuenta, o confirma que ya fue validado fuera de sesión.
- **Si el dev pide push en cualquier momento**: Claude sugiere primero actualizar el registro del requerimiento (change MD); el push `.md`-only de ese registro es autónomo (ver "Entrega temprana del registro del requerimiento" arriba).
- **Confirmaciones autónomas en un push**: antes de cualquier push (con OK, bajo autonomía declarada por proyecto o por integración autónoma), Claude corre `git log --format='%h %(trailers:key=Confirmacion-autonoma,valueonly)' origin/<rama-destino>..<sha>` (si esa ref no existe en el remoto, `git log --format=… <sha> --not --remotes=origin`). Si aparece una confirmación autónoma que no consta como mostrada al dev en su registro (condición 7 de la confirmación autónoma), el push pide OK, la nombra y muestra su diff. Ningún `pull --rebase` ni rebase reescribe confirmaciones autónomas ajenas sin pushear: si haría falta, se pide OK.

## Integración a la rama principal

**Integrar** es llevar a la rama principal del remoto un cambio que ya pasó la validación, sin crear commits: la principal avanza por *fast-forward* hasta el commit validado (`git push origin <sha>:refs/heads/<principal>`). Aplica igual si el REQ vive en una rama propia o en la principal local. No requiere checkout ni merge en el clon compartido, y la principal local no se toca. El adoptante declara su modelo de integración (PR con revisión, o integración directa) en su overlay o en `profiles/<profile>/deployment.md`; sin declaración, integrar sigue § Push (preguntar).

- **Excepción — integración autónoma declarada por el adoptante.** Si el overlay del adoptante o el `deployment.md` del profile la activa, Claude integra sin pedir OK cuando se cumple **todo** el piso de abajo. Sigue el modelo de la autonomía declarada por proyecto de [`change-control-gate.md`](change-control-gate.md), con alcance de adoptante (no de un dev ni de un proyecto), compensado por un piso que fija este núcleo; por eso activarla no es un override que relaje el baseline ([`../methodology/personal-vs-team.md`](../methodology/personal-vs-team.md) § "Regla central"). Una declaración puede agregar condiciones o excluir profiles y repos; nunca quitar condiciones.
- **Piso no relajable.** Justo antes de evaluarlo, Claude corre `git fetch origin` (sin pull) y evalúa contra las refs recién traídas. Si falla una condición, Claude dice cuál y pide OK.
  1. **Validación aprobada con SHA anclado**: la Fase 5 del REQ se ejecutó y pasó (ninguna fila ❌ entre las que corren antes de la entrega final), y el registro del requerimiento anota el **SHA validado** —el commit cuyo contenido se probó— y quién validó: el dev, o Claude con delegación explícita del dev anotada en el registro. Una validación saltada, aunque sea con OK, no cuenta. Con N destinos, el piso se evalúa por repo.
  2. **Lo integrado es lo validado**: el commit a integrar es el SHA validado, o los commits posteriores tocan solo el registro del requerimiento (`git diff --name-only --no-renames <sha-validado> <sha-a-integrar>` lista solo esos archivos); y `git merge-base --is-ancestor origin/<principal> <sha-a-integrar>` termina en 0. Si la principal remota avanzó y ya no es ancestro, integrar exige merge o rebase, y el resultado es una combinación que nadie probó aunque los archivos no se traslapen: Claude no hace pull, merge ni rebase por su cuenta; pide OK y da como insumo los archivos que se cruzan. Si la rama se actualiza y se revalida, el nuevo SHA validado vuelve a calificar.
  3. **Solo commits del REQ**: `git rev-list origin/<principal>..<sha-a-integrar>` contiene solo commits que el registro del requerimiento lista por SHA (ni el autor ni un rango sirven), más los que tocan solo el propio registro (`git diff-tree --no-commit-id --name-only -r <c>` lista solo ese archivo). Si un commit ajeno es ancestro del SHA, Claude pide OK con sus hashes; separarlo con cherry-pick crearía SHAs que nadie validó. Los commits posteriores al SHA no viajan. Toda confirmación autónoma de ese rango consta como mostrada al dev en su registro; si falta alguna, se pide OK.
  4. **Sin dependencia pendiente**: el registro del requerimiento no lista una dependencia (esquema, configuración, paso previo a la entrega) que todavía no se aplica en un ambiente que se entrega desde la rama principal.
  5. **No es ni dispara una entrega**: el push a la principal no es, por sí mismo, una entrega del profile (para revisión o final, según su glosario) ni la dispara (CI, tarea programada que consume la principal, release o tag). El overlay del adoptante o el `deployment.md` del profile declara si un push a la principal dispara algo; sin esa declaración, no se da por descartado. Si lo es o la dispara, sigue el gate de esa entrega.
  6. **Sin efectos colaterales en git**: sin push de tags, sin reescritura de historia y sin mutar la principal local ni el working tree compartido (checkout, reset, rebase, pull). Las prohibiciones de [`git-conventions.md`](../methodology/git-conventions.md) siguen vigentes.
- **Rechazo**: si el remoto rechaza el push (no es fast-forward, hay una restricción de rama o un hook), Claude no reintenta con otra estrategia (pull, rebase, merge, otra rama o `--force`): reporta el rechazo y pide OK.
- **Reporte**: Claude integra, confirma con `git ls-remote origin refs/heads/<principal>` que la punta remota es el SHA integrado, lo reporta en una línea (rama, SHA, condiciones verificadas) y anota el SHA en el registro del requerimiento.
- **Alcance**:
  - Solo el cambio del REQ activo de la sesión, desde la rama del REQ anotada en su registro (la principal o una rama acordada). No aplica a ramas que agregan varios REQs (release), a ramas aparcadas (las marca el dev o el registro) ni a ramas de otro dev, incluido un PR que otro abrió. Si el plan aprobado ubica la integración dentro de un paso con gate (p. ej. una ventana de entrega), rige el plan. No cubre borrar la rama.
  - La integración por fast-forward no crea commits: publica commits que ya pasaron el gate de Fase 4 (con OK o por confirmación autónoma) y la validación, así que el gate por confirmación no aplica. Un merge de la principal hacia la rama del REQ sí cambia lo validado: sigue el gate de Fase 4 y reabre la validación.
  - La integración que cumple la condición 5 no es la entrega final y no pasa por el gate de subagente de Fase 7 ([`delivery.md`](delivery.md)); la entrega final posterior sí. El siguiente punto de no retorno (deploy, migración) sigue su propio gate y no se encadena con la integración.
  - Si el arnés (permisos o el clasificador del modo automático) bloquea el push o pide confirmación, eso prevalece: Claude pide el OK nombrando el push a la rama principal y no busca otra vía.

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
