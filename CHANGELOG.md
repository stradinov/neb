# Changelog

Todos los cambios relevantes a esta metodología quedan registrados aquí. Formato: [keep a changelog](https://keepachangelog.com/en/1.1.0/). Versionado SemVer.

## [Unreleased]

## [5.11.0] - 2026-06-25

> **Minor**: los **puntos de customización** se enumeraban en 3 sedes paralelas desincronizadas (follow-up de Fase 9 de v5.10.0). Se designa `methodology/principles.md § "Puntos de customización"` como **lista canónica por diseño**, que declara además el **estado de materialización** de cada punto (con bloque `> Punto de customización` vs pendiente). Las sedes que enumeran lo materializado (`promises.md` p5, `personal-vs-team.md` preconfigurados) espejan ese subconjunto. Hace **visible** el gap "declarado pero no materializado" (lo tiene hoy `models.md`).

### Added

- **`methodology/principles.md § "Puntos de customización"`**: declaración de lista **canónica por diseño** + estado de materialización (materializados: coding-standards, git-conventions, done-criteria, communication; **pendiente**: models) + regla "al agregar un punto o materializar uno pendiente, sincroniza las sedes afectadas".

### Changed

- **`methodology/promises.md`** (promesa 5, celda "Dónde se materializa"): reetiquetada como "Materializado (subconjunto de principles.md)"; lista los puntos con bloque (sin `models`, que está declarado pero no materializado). La prosa de "Criterio verificable" (conceptos customizables por diseño, incluye modelos) se mantiene.
- **`methodology/personal-vs-team.md`** (puntos preconfigurados): reetiquetada como subconjunto materializado de la canónica; se quita `models` (no preconfigurado); path a `principles.md` corregido a idiomático (intra-`methodology/` sin `../`).

### Fixed

- Desincronía entre las 3 sedes: `models.md` figuraba en la canónica pero faltaba en las otras dos. Reencuadrado como pendiente de materializar (visible en la canónica), no como omisión silenciosa.

## [5.10.0] - 2026-06-24

> **Minor**: el idioma se vuelve personalizable por niveles (individuo / adoptante / núcleo). El **idioma base del núcleo es español**; la **variedad regional, el registro y la tolerancia a extranjerismos** (mexicano/tuteo/no-voseo para este repo) pasan de baseline duro a **punto de customización** (promesa 5), sustituible en `personal/<usuario>.md` (individuo) o el overlay (adoptante). Respeta la sede única de la política (`communication.md`, REQ 5.6.0): estratifica dentro, no dispersa. Cambio de fuerza normativa (el default deja de imponer variedad) → Minor, no Patch.

### Added

- **`methodology/personal-vs-team.md`** § "Puntos de customización vs reglas de proceso": distingue **regla de proceso** (tiene eje de severidad → estrecha/agrega, nunca relaja) de **punto de customización** (sin eje de severidad → el override sustituye). Resuelve que `permitir_voseo: true` en un `personal.md` sea legítimo (sustitución de preferencia, no relajación de un control).
- **`general/communication.md` § "Idioma"**: bloque **Punto de customización** (promesa 5) con destinos individuo (`personal/<usuario>.md`, o por-proyecto `<proyecto>/.claude/personal.md`) y adoptante (overlay); esquema y perillas en `tooling/redaccion-es.md`. Materializa el gap promesa↔archivo (las otras personalizaciones ya tenían su bloque; comunicación no).

### Changed

- **`general/communication.md` § "Idioma"**: el idioma base pasa a **español** (agnóstico de variedad); variedad/registro/extranjerismos = customización. Se separan los ámbitos antes fusionados: conversación + errores (canal, customizable), prosa de `.md` (variedad del repo/adoptante), código/identifiers/commits/términos (inglés). La variedad de este repo (`variedad: mexico`, `permitir_voseo: false`, tuteo) se declara como valor de customización, no como baseline del núcleo.
- **`methodology/principles.md` § "No tocar"**: la línea de idioma se reblandece — **español** en prosa (variedad de repo mexicano/tuteo como punto de customización), inglés en identifiers/commits/comandos/paths/términos. Cambio de fuerza normativa de una invariante de "No tocar" → declarado.
- **`methodology/personal-vs-team.md`**: "Preferencias de comunicación más estrictas" → "preferencias (idioma, variedad, registro, formato) que sustituyen el default"; `communication.md § Idioma` sumado a los puntos de customización preconfigurados.
- **`methodology/promises.md`** (promesa 5): la columna "Dónde se materializa" suma `communication.md`; el criterio distingue reglas de proceso (estrecha/agrega/nunca relaja) de puntos de customización (se sustituyen).
- **`tooling/revision-editorial-externa.md`**: el idioma se reencuadra de "español mexicano (tuteo)" (regla universal) a **español, variedad de este repo: mexicano/tuteo** (punto de customización). El valor que el revisor externo aplica no cambia (la prosa del repo sigue en mexicano/tuteo); cambia el encuadre.
- **`templates/personal.md.template`** § "Preferencias de comunicación": ejemplo concreto de preferencia sustituible (variedad/permitir_voseo/registro + formato de salida).

## [5.9.3] - 2026-06-23

> **Patch**: corrige un drift doc↔script en `docs/user-guide.md` (detectado al revisar el barrido 5.9.2): el script `setup-workspace.sh` escribe en `~/.claude/settings.json`, no en el "shell profile", y el efecto se toma al abrir una sesión nueva de Claude Code, no al reiniciar el shell.

### Fixed

- **`docs/user-guide.md`** § "Configurar el entorno": "establece dos variables en tu shell profile (con backup)" → "en `~/.claude/settings.json` (merge no-destructivo)"; "Reinicia tu shell para que surtan efecto" → "Abre una sesión nueva de Claude Code…". Alinea la guía con el comportamiento real del script (`setup-workspace.sh` L192/L209: el shell profile ya no se edita).

## [5.9.2] - 2026-06-23

> **Patch**: barrido terminológico repo-wide en los docs **de cara al humano** — traducción de los 4 anglicismos pervasivos (`workspace`/`opt-in`/`tour`/`dry-run`) decididos en v5.9.1. ~70 ediciones en 18 docs; identifiers, flags, filenames, comillas de output y frontmatter conservados. Validado con plan-review (completitud + consistencia).

### Changed

- **Docs de cara al humano** (`README`, `docs/{user-guide,how-it-works}`, `commands/wakeup`, `general/{onboarding,index}`, `skills/wakeup/{SKILL,validation-prompts}`, `skills/pendings-review/SKILL`, `profiles/self-applied/skills`, `server/INSTALL`, `tooling/{index,logbook,notify-on-stop,notify-on-permission,prompt-preprocessing}`, `methodology/{principles,vocabulary}`): `workspace`→"espacio de trabajo", `opt-in`→"opcional" (o "de activación voluntaria por proyecto/perfil" cuando es activación afirmativa, no mera opcionalidad), `tour`→"recorrido", `dry-run` (prosa)→"simulación".
- **Conservados** (sin tocar): identifier `NEB_WORKSPACE`, archivo `setup-workspace.sh`, dir de ejemplo `neb_workspace/`, flag `--dry-run`, código/inline-code, comillas de output literal del script ("Workspace existente detectado…"), frontmatter `name:`/`description:` de skills/commands y el skill name `wakeup`.
- **Fuera de alcance** (retienen el inglés por decisión de alcance): docs agent-normativos (`process/`, `workflow/`, `general/profile-detection`, `profiles/self-applied/deployment`), `hooks/`, `bootstrap/`, `CHANGELOG`/`changelog.d`/`changes`/`research`, y scripts `*.py`/`*.sh`/`*.json`/`*.template`.
- **`tooling/revision-editorial-externa.md`**: la nota de barrido pasó de "pendiente" a "ejecutado en v5.9.2" con el mapeo final y las reglas de conservación.

## [5.9.1] - 2026-06-23

> **Patch**: revisión editorial de `commands/wakeup.md` (anglicismos de prosa → español) — **1.ª validación en uso de la guía endurecida v5.9.0**: el agente externo NO reportó estructura (la declaró fuera de alcance). Allowlist de la guía ampliada; 4 términos pervasivos (`workspace`/`opt-in`/`tour`/`dry-run`) diferidos a un barrido repo-wide.

### Changed

- **`commands/wakeup.md`**: customizable→personalizable, fallback→ruta de reserva (+ precisión "una instalación reciente"), re-detectes→repitas la detección, config→configuración, refiriendo→remitiendo.
- **`tooling/revision-editorial-externa.md`**: allowlist += customizable→personalizable, fallback→ruta de reserva, config→configuración, y el mapeo canónico de los 4 términos del barrido pendiente (`workspace`→espacio de trabajo, `opt-in`→opcional/voluntario, `tour`→recorrido, `dry-run`→simulación) con sus excepciones de conservación (`NEB_WORKSPACE`, `setup-workspace.sh`, flag `--dry-run`); regla anti-prefijo `re-` calcado.

## [5.9.0] - 2026-06-23

> **Minor**: endurecimiento de `tooling/revision-editorial-externa.md` para erradicar la alucinación de estructura del agente externo, que reincidió pese a la lección en prosa de 5.8.1–5.8.2. Tres lineamientos nuevos en el flujo de revisión.

### Changed

- **`tooling/revision-editorial-externa.md`**: el agente externo ahora (1) **relee la guía en crudo antes de cada documento** —cierra el ciclo de "documento vivo": antes trabajaba con la copia del briefing inicial y nunca recibía las lecciones/allowlist agregadas a media sesión—; (2) **lee la guía y el documento en crudo** (`raw.githubusercontent.com`) en vez de la vista renderizada de GitHub, que le hacía perder los saltos de línea; (3) tiene la **estructura/formato fuera de alcance** como regla dura —solo revisa redacción—. La lección de estructura se reformuló en consecuencia y el prompt recurrente del § "Para el maintainer" pasó a URLs en crudo.

## [5.8.2] - 2026-06-23

> **Patch**: revisión editorial de `CONTRIBUTING.md` (anglicismos de prosa → español) vía el flujo de `tooling/revision-editorial-externa.md`, + 2ª evolución de esa guía. El gate de verificación volvió a rechazar hallazgos de estructura **alucinados** por el agente externo (esta vez colapsó todos los saltos de línea del archivo, no solo una tabla; el archivo estaba intacto).

### Changed

- **`CONTRIBUTING.md`**: bumps→incrementos, gap→brecha, triage/triar/tría→clasificar/clasificación, transcripts→transcripciones, naming→convención de nombres, imports→`@imports`, ownership→propiedad; `self-applied` marcado como código; corte de la promesa futura de `CODE_OF_CONDUCT.md`.
- **`tooling/revision-editorial-externa.md`** (evolución desde `PROPUESTAS PARA LA GUÍA`): allowlist ampliada (bump→incremento, gap→brecha, triage/triar/tría→clasificar/clasificación, transcripts→transcripciones, naming→convención de nombres, ownership→propiedad); lección de estructura reforzada (el agente colapsa saltos de línea en todo el archivo, no solo tablas, y omite emojis); queda `done` como único caso a decidir repo-wide.

## [5.8.1] - 2026-06-23

> **Patch**: revisión editorial de `methodology/promises.md` (anglicismos de prosa → español, idiom, corte de redundancia) aplicada vía el flujo de `tooling/revision-editorial-externa.md`, + primera **evolución** de esa guía a partir de las `PROPUESTAS PARA LA GUÍA` del agente externo y de lo aprendido en el pase. El gate de verificación rechazó hallazgos de estructura de tabla **alucinados** por el agente (la tabla estaba intacta).

### Changed

- **`methodology/promises.md`**: "Customizable"→"Personalizable" (alinea con `principles.md`), loop→ciclo, defaults→valores por defecto, customización→personalización, forkear→hacer fork, scaffolding→estructura base, extension points→puntos de extensión, always-on→siempre activas; "imports"→`@imports` (marcado como mecanismo); corte de "el repo se aplica a sí mismo (dogfooding)" (redundante con la celda anterior).
- **`tooling/revision-editorial-externa.md`** (evolución desde `PROPUESTAS PARA LA GUÍA`): allowlist ampliada (forkear→hacer fork, loop→ciclo, always-on→siempre activas, extension points→puntos de extensión, scaffolding); `trigger` y `@import`/`@imports` movidos a "conservar"/protecciones; nueva lección "no alucines estructura de tabla"; `done` anotado como caso a decidir repo-wide.

## [5.8.0] - 2026-06-22

> **Minor**: nuevo recurso opt-in `tooling/revision-editorial-externa.md` — **briefing dirigido al agente LLM externo** (ChatGPT u otro) que actúa como consultor editorial de los `.md` de Neb. El maintainer apunta al agente a este doc; el doc define rol, reglas, contrato de salida `[ACTUAL]`/`[PROPUESTO]` con banderas, qué revisar, allowlist de anglicismos + protecciones, lecciones aprendidas (primer pase v5.5.1–5.6.0) y la norma de **evolución**: el contrato cierra con una sección `PROPUESTAS PARA LA GUÍA` (el agente sugiere mejoras a este briefing en cada reporte) que Claude evalúa y promueve a norma.

### Added

- **`tooling/revision-editorial-externa.md`**: guía de revisión editorial por agentes externos, registrada en `tooling/index.md`. Referencia (no duplica) la política de idioma (`general/communication.md § "Idioma"`), la doctrina editorial (`methodology/principles.md`), el vocabulario canónico (`methodology/vocabulary.md`) y la taxonomía (`tooling/redaccion-es.md`). Lecciones clave: verificar `[ACTUAL]` (el agente externo puede servir caché o normalizar el texto), aplicar allowlist en vez de las sugerencias del agente a ciegas (no ve consistencia repo-wide), proteger bloques `<!-- human -->`/citas/headings, y pasar las sugerencias por un gate in-repo antes de un barrido grande.

## [5.7.0] - 2026-06-22

> **Minor**: el canal de contribución se reorienta a **issues de GitHub** con esquema guiado. Se retira del `CONTRIBUTING.md` el flujo fork → rama → `changelog.d` → bump SemVer → Pull Request (ceremonia interna del mantenedor que se presentaba, falsamente, como guía para externos) y se establece como canal único abrir un issue con plantilla. Nuevo lineamiento de contribución → Minor.

### Added

- **`.github/ISSUE_TEMPLATE/01-defecto.yml`**: GitHub issue form de reporte de defecto con esquema claro — resumen (BLUF), componente de Neb, versión y entorno, comportamiento observado (hechos) vs esperado, pasos para reproducir, evidencia (sin PII/datos de cliente/marcas/rutas), hipótesis de causa marcada como tal, severidad/impacto y confirmaciones. Refleja `methodology/principles.md § "Suposiciones explícitas"` (separa hechos de hipótesis); la escala de impacto está inspirada en P1/P2 de `general/incidents.md`, adaptada a tres niveles para triage de issues (no es correspondencia directa).
- **`.github/ISSUE_TEMPLATE/02-mejora.yml`**: issue form de propuesta de mejora/fricción/gap (resumen, componente, fricción observada, propuesta, alternativas e impacto).
- **`.github/ISSUE_TEMPLATE/config.yml`**: desactiva issues en blanco (`blank_issues_enabled: false`) y enlaza README/Guía del usuario y Discussions.

### Changed

- **`CONTRIBUTING.md`**: reescrito. Canal único = abrir un issue con plantilla; explica el modelo real (núcleo mantenido por el equipo bajo `self-applied`, sin PRs externos, con SemVer/`CHANGELOG`/bumps como ceremonia interna del mantenedor) y el triage post-issue. Se conserva la regla "sin PII, datos de cliente, marcas ni rutas absolutas" reubicada en "Qué hace un buen reporte". Se elimina el `> Stub inicial (MVP)`.

## [5.6.0] - 2026-06-22

> **Minor**: política de idioma codificada + barrido repo-wide. Se establece que la prosa de los `.md` va en **español mexicano (tuteo)** y que solo se conservan en inglés identifiers/comandos/paths/commits y términos tecnológicos; el resto de anglicismos de prosa se traducen. La política vive en `general/communication.md § "Idioma"` (referenciando `tooling/redaccion-es.md`), con enlace desde `methodology/principles.md`. Cambio de fuerza normativa (endurece la regla de idioma del baseline) → Minor, no Patch.

### Changed

- **`general/communication.md § "Idioma"`** + **`methodology/principles.md § "No tocar"`**: prosa de los `.md` = español mexicano (tuteo, nunca voseo); inglés solo en identifiers/comandos/paths/commits y términos tecnológicos (commit, prompt, hook, plugin, deploy…); el resto de anglicismos de prosa se traducen. Sede canónica en `communication.md`; `principles.md` enlaza; referencia a `tooling/redaccion-es.md` (ya en `variedad: mexico`, `permitir_voseo: false`).
- **Barrido repo-wide (~45 `.md` de prosa)**: voseo→tuteo mexicano + traducción de anglicismos por **allowlist** (markers→marcadores, setea→establece, setup→configuración, runtime→tiempo de ejecución, scaffold→estructura base, troubleshooting→resolución de problemas, system prompt→prompt de sistema, gitignored→ignorada por Git, commitear→hacer commit, rename→renombre, full-text→texto completo, outputs→salidas, fragment→fragmento, cache→caché, deprecado→obsoleto, default→por defecto). Intactos: anglicismos canónicos (`gate`/`profile`/`overlay`/`workflow`/`override`/`baseline`), términos tecnológicos, identifiers/comandos/paths/filenames, headings citados ("Default por profile"), code spans, la ilustración del voseo rioplatense en `redaccion-es.md`, y bloques `<!-- human -->`.

## [5.5.1] - 2026-06-22

> **Patch**: correcciones de redacción en docs de adopción (`README.md`, `docs/user-guide.md`) — sintaxis, claridad, anglicismos de prosa → español, inicio de tuteo — a partir de una revisión editorial externa (ChatGPT) aplicada como deltas gated. Sin cambio de sentido ni de alcance normativo. El barrido repo-wide de tuteo + anglicismos y la codificación de la política de idioma quedan para una versión posterior (5.6.0).

### Changed

- **`README.md`**: 9 correcciones. Dentro del pitch `<!-- human -->` con OK del dev (comma splice, claridad de la enumeración, "definición de tus proyectos"); fuera del bloque (completar "ejecuta" antes de los bloques de comando, "setup" → "configuración inicial", referente "que Neb describe"). Separadores ornamentales `---` y "la Nebuchadnezzar" conservados por decisión del dev.
- **`docs/user-guide.md`**: 23 correcciones — gramática/claridad + anglicismos de prosa → español (markers→marcadores, setea→establece, setup→configuración, runtime→tiempo de ejecución, scaffold→estructura base, troubleshooting→resolución de problemas, system prompt→prompt de sistema, gitignored→ignorada por Git, commitear→hacer commit, rename→renombre, full-text→texto completo, outputs→salidas, fragment→fragmento, cache→caché, deprecado→obsoleto, default→por defecto) + "por vos" → "por ti".

## [5.5.0] - 2026-06-22

> **Minor**: cuadro pedagógico de los 3 modos de redacción (Normativa / Explicativa / Adopción) en `docs/user-guide.md` § "Contribuir al núcleo". Material explicativo de cara al contribuidor; la fuente canónica sigue siendo `methodology/principles.md` § "Lineamientos para editar MDs" — el cuadro **ilustra**, no duplica la regla. Cierra el REQ-4 (opcional) del roadmap vocabulario+editorial.

### Added

- **`docs/user-guide.md` § "Contribuir al núcleo (mantenedores)" > "Cómo se redactan los MDs"**: tabla de los 3 modos de redacción por consumidor (agente austero en el núcleo vs documentación de cara al humano en `docs/`/`README` con más contexto), enlazando a `methodology/principles.md` como fuente canónica. El cuadro vive en `docs/` (capa de adopción, exenta del test M/P) — es contenido modo "adopción" que ejemplifica su propia categoría.

## [5.4.0] - 2026-06-22

> **Minor** (cambio de comportamiento de default): el hook `preprocess-prompt` (`UserPromptSubmit`, opt-in personal) ahora arranca en modo **`off`** por defecto — se instala pero queda **inerte** hasta que el dev lo enciende con `/preprocess full|fast` o fija `"mode"` en su `preprocess.json`. Antes arrancaba en `full` (corrección + eco + confirmación) apenas se copiaba el bloque del template. Motivado por el riesgo de que el corrector altere texto pegado de propuestas ya definidas que no deben modificarse.

### Changed

- **`hooks/preprocess-prompt.py`**: `DEFAULTS["mode"]` `"full"` → `"off"`; fallback de `resolve_mode` alineado a `"off"`.
- **`tooling/prompt-preprocessing.md`** + **`commands/preprocess.md`**: default `off` coherente en las 8 sedes de doc — tabla de modos (§4), ejemplo + tabla de config (§5), precedencia + nota de `$$` (§6), snippets de instalación PowerShell/bash (§7), nota de activación (§7), nota + escenario #5 (§11), y el slash command. Los snippets de §7 escribían `preprocess.json` con `"full"`, que por precedencia (archivo personal > default) habría anulado el cambio del código.

### Notas

- El template `claude-user-settings.json.template` **no cambia**: el hook se sigue instalando; solo arranca inerte. Activación explícita por dev.
- `.claude-plugin/plugin.json` se sincroniza a 5.4.0 (corrige drift preexistente con `VERSION`, que iba en 5.3.1).

## [5.3.1] - 2026-06-22

> **Patch** (ajuste de foco de rol — `roles-catalog.md` § Evolución/Acciones: "ajustar foco con sub-foco nuevo = REQ `docs:` patch"): el subagente `qa-process-engineer` gana un sub-foco de **precisión terminológica** dentro de su foco de vocabulario canónico ya existente. Audita contra el § "Índice de términos canónicos" de `vocabulary.md` (columnas "No confundir con" + "Sinónimos"): detecta sinónimos no declarados, mezcla de conceptos vecinos (REQ/registro/change MD/plan/entregable/commit) y términos nuevos sin clasificar. **No agente nuevo** (regla anti-role-inflation: ajustar foco antes que crear rol).

### Changed

- **`agents/qa-process-engineer.md`** + **`profiles/self-applied/roles.md`**: el foco "Vocabulario canónico" se desdobla en *(a)* agnóstico del profile [existente] y *(b)* precisión terminológica [nuevo], con las columnas "No confundir con"/"Sinónimos" del Índice como oráculo verificable. `description` del agente actualizada.
- **`methodology/roles-catalog.md`** § "Atribución del defecto": nueva fila routea "sinónimo no declarado / término canónico mezclado" a QA (sub-foco precisión terminológica).

## [5.3.0] - 2026-06-22

> **Minor**: política editorial en `methodology/principles.md` § "Lineamientos para editar MDs". Absorbe los lineamientos de redacción del REQ `md-redaction-guidelines` (tría de ejemplos + subsección `### Claridad`) y agrega el contrapeso de **suficiencia** (anti-"escuetez falsa") como contrato de output, más el calibre por **consumidor** (agente austero vs documentación de cara al adoptante en `docs/` y `README.md`, que admite más contexto). Generaliza el criterio de corte de "comportamiento del LLM" a "del consumidor" (cambio de fuerza normativa declarado, no Patch). Plan-review (qa-process-engineer + process-improvement-analyst + context-completeness-reviewer) descartó una tabla de "3 modos" por duplicar la excepción `docs/`, y reformuló la suficiencia para no prescribir razonamiento interno.

### Changed

- **§ "Lineamientos para editar MDs" (intro)**: criterio de corte generalizado a "comportamiento del **consumidor**". El consumidor por defecto es el agente (redacción austera); la documentación de cara al adoptante (`docs/`, `README.md`) admite más contexto/ejemplos (no es lineamiento que el agente aplique). Se declara el **piso inferior** de suficiencia.
- **§ "Lineamientos para editar MDs" > Eliminar**: el bullet de ejemplos pasa a una **tría** convertir/cortar/conservar (un ejemplo con un matiz de conducta no enunciado se eleva a regla; si solo re-ilustra, se corta; cita literal se conserva).

### Added

- **§ "Lineamientos para editar MDs" > `### Claridad`** (nueva subsección): regla-como-contrato-de-output; término-canónico-una-acepción (enlaza a § "Coherencia global" eje 1); claridad-sobre-compresión; y **suficiencia** (una regla normativa enuncia condición · acción · consecuencia; cortar por debajo es escuetez falsa, no austeridad). Canoniza la noción "redacción suficiente" que el changelog 5.2.0 usó inline.

## [5.2.0] - 2026-06-22

> **Minor**: nuevo índice de términos canónicos en `methodology/vocabulary.md` — mapa operativo de los conceptos que cambian comportamiento (fases, gates, artefactos, estados, perfiles, roles, entregas, validaciones, excepciones), con glosa en español llano (anglicismos → equivalente) y desambiguación (`No confundir con` + sinónimos). Cierra dos huecos: `Fase` y `Gate` no eran términos canónicos. Cambio aditivo; no toca las secciones ni anclas existentes.

### Added

- **`methodology/vocabulary.md` § "Índice de términos canónicos"**: tabla de 13 términos con esquema mínimo (Tipo · Glosa · No confundir con · Sinónimos · Canónico). Alta de `Fase` y `Gate` como términos canónicos (antes solo delegados por puntero). Glosa en español llano para lectores no técnicos; anglicismos (gate, profile, commit, ENUM, push, lock…) anotados con su equivalente. El índice **no duplica definiciones**: la columna *Canónico* enlaza a la fuente de verdad de cada término (sección interna del archivo, o `general/`, `process/`, `workflow/`, `profiles.md`, `roles-catalog.md`). Dos consumidores justifican la "redacción suficiente" por encima de la austeridad: el lector humano (comprensión de anglicismos) y el futuro revisor terminológico/editorial.

## [5.1.0] - 2026-06-19

> **Minor**: nuevo hook opt-in `ops-capture` (`SessionEnd`) que captura el conocimiento operativo descubierto en una sesión a un inbox efímero, para revisión y aplicación **gated** por un comando del adoptante (p.ej. `/ops-review`). Mecanismo genérico; el dominio (qué es operativo, dónde aterriza) lo parametriza el overlay vía env vars. Implementa la pieza 2a de la metodología de memoria operativa.

### Added

- **Hook `ops-capture`** (`hooks/ops-capture.py`, `SessionEnd`, tipo `command` Python cross-OS, **opt-in**). Lee el transcript de la sesión, aplica un **gate barato** (extrae fragmentos con señales operativas; sin señales no invoca el modelo), e invoca un subagente vía `claude -p` que extrae **deltas propuestos** a un **inbox efímero** (`~/.claude/ops-inbox/`, configurable con `NEB_OPS_INBOX_DIR`). NO toca ninguna fuente de verdad. Guard de subsesión interna (`NEB_INTERNAL_SUBSESSION`) para no recursar al invocar `claude -p`. Defensivo: `exit 0` siempre.
- **Helper `hooks/lib/ops_inbox.py`** — lógica determinística: resolución del inbox, naming sanitizado cross-OS, parse del transcript JSONL y el gate de actividad operativa (vocabulario genérico, ampliable con `NEB_OPS_SIGNALS_EXTRA`).
- **Parametrización por el overlay**: `NEB_OPS_CAPTURE_PROMPT_FILE` (prompt de detección con vocabulario de dominio), `NEB_OPS_SIGNALS_EXTRA` (regex extra del gate), `NEB_OPS_CAPTURE_MODEL` (modelo, default Haiku).
- **Cobertura**: `hooks/tests/test_ops_capture.py` (14 tests del helper).
- **Registro**: bloque opt-in en `hooks/settings.template.json` (`SessionEnd`, Windows + Linux) y sección en `hooks/README.md`.

## [5.0.0] - 2026-06-17

> **Major**: la memoria de un requerimiento pasa de una sección `## Requerimiento activo` dentro de `project_<nombre>.md` a un **archivo por REQ** (`active_<proyecto>_<slug>.md`), habilitando **varios REQ activos del mismo proyecto en paralelo** en la bitácora de relevo. Además, los hooks ahora **respetan `autoMemoryDirectory`** (setting nativo de Claude Code) para una memoria única independiente del cwd. **Compatible hacia atrás**: los hooks siguen leyendo la sección legacy durante la transición. El major es por el cambio de vocabulario/estructura canónica de la memoria; no hay ruptura de imports.

### Added

- **`active_<proyecto>_<slug>.md` — un archivo por REQ activo.** La bitácora (`work`) ahora captura **N REQ activos por proyecto** (el esquema ya lo soportaba vía `(project, req_slug)`; faltaba el capturador, que asumía un único REQ por cwd). Plantilla nueva: `templates/active-req.md.template`.
- **`_db_shared.find_active_reqs(memory_dir)`** (plural) — escanea `active_*.md` + compat legacy (`project_*.md` con `## Requerimiento activo`), dedup por `(project_path, name)` prefiriendo `active_*`, ordena por mtime. Fuente única compartida por `logbook.py` y `usage-tracker.py` (antes había 2 copias divergentes de `find_active_req`).
- **`_db_shared.resolve_memory_dir(home, cwd, encoded)`** — respeta `autoMemoryDirectory` de `settings.json` (precedencia Local > Project > User; fallback al path derivado del workspace). Memoria única independiente del cwd de arranque; opt-in personal, no se impone. Scopes `managed`/`--settings` fuera de alcance del hook (limitación documentada).
- **Cobertura**: `hooks/tests/test_active_reqs.py` (N REQ, compat legacy, dedup, parser robusto, `resolve_memory_dir` por scope + fallback + expansión `~`).

### Changed

- **`logbook.py`**: `main()` itera todos los REQ activos y hace upsert por cada uno; `memory_dir` vía `resolve_memory_dir`.
- **`usage-tracker.py`**: `memory_dir` vía `resolve_memory_dir` (user scope); con varios REQ activos atribuye el costo del turno al de mtime más reciente. Los archivos de sesión (`.jsonl`/`offset`/`state`) **siguen** ubicándose por cwd (no se mueven con `autoMemoryDirectory`; el `.jsonl` no vive en el dir de memoria custom).
- **"Pendiente de entrega"** se mueve de `project_<nombre>.md` al `active_*.md` del REQ (es por-REQ); `project_<nombre>.md` queda con contexto duradero.
- **Vocabulario y docs** (sección → archivo, singular → plural): `workflow/memory.md` (canónico), `hooks/README.md`, `general/communication.md`, `workflow/{changes,metrics,logbook,index,traceability}.md`, `methodology/{vocabulary,done-criteria}.md`, `process/{execution,documentation}.md`, `templates/project-memory.md.template`.

### Fixed

- **`usage-tracker` no atribuía costos con el formato real de la memoria.** Su `_extract_field` solo matcheaba `Field: value` plano, no `- **Field:** value` (el formato del template) → en la práctica nunca encontraba el REQ activo. Al unificar en `find_active_reqs` (regex `_field` robusto a viñeta/negrita), queda corregido.

## [4.10.1] - 2026-06-17

> **Patch**: corrige dos defectos que dejaban el CLI/skill `/logbook` inoperante en servidores con Python < 3.12 (p.ej. Amazon Linux 2023: `python3` 3.9, `python3.11` vía uv, sin 3.12). Sin cambio de fuerza normativa ni de imports. De paso sincroniza `plugin.json` con `VERSION` (venía en 4.9.0 desde 4.10.0).

### Fixed

- **`SyntaxError` por backslash en expresión de f-string (PEP 701) — bloqueaba el import del módulo.** En `hooks/lib/_db_shared.py`, `posix_to_win` usaba `f"{path[1].upper()}:\\{path[2:].replace('/', '\\')}"`; el backslash dentro de `{…}` solo es válido en Python ≥ 3.12. En 3.9/3.11 lanza `SyntaxError: f-string expression part cannot include a backslash`, y al ser error de parseo el módulo entero no carga (ni en Linux, aunque `posix_to_win` solo actúe en Windows) — tumbando el CLI y, por importación, `logbook.py`/`pendings.py`/`usage-tracker.py`. Se precomputan `drive` y `rest` en variables y el f-string queda sin backslash en sus expresiones. Comportamiento idéntico en Windows; no-op en Linux/Mac. Validado con `py_compile` en 3.9 y 3.11 (exit 0).
- **Wrapper `LB()` del skill `/logbook` sin fallback a `python3`.** `LB() { py … || python …; }` daba exit 127 (`python: command not found`) en cajas que solo tienen `python3` (Amazon Linux 2023 no provee `py` ni `python`), impidiendo que el skill ejecutara el CLI aun con la sintaxis corregida. Se agrega `|| python3 …` como último fallback (Windows sigue usando `py` primero; Linux/Mac caen a `python3`).

## [4.10.0] - 2026-06-15

> Refactor de `general/communication.md` hacia una política orientada a decisiones (BLUF como principio rector, gates por **propiedad de la acción**, captura de tangentes por impacto). Adopta el rediseño del borrador, validado por análisis multi-lente adversarial + revisión de roles (`qa-process-engineer`, `process-improvement-analyst`). **Minor**: cambia la fuerza normativa de varias reglas y agrega lineamientos; no rompe imports (solo anclas de sección intra-archivo de path estable).

### Changed

- **Estilo de respuesta: de obligación a libertad del dev.** Se retiran como obligaciones del baseline las reglas de la antigua § "Tono y forma" — "Respuestas concisas. Sin padding.", "Sin emojis salvo que el usuario los pida.", "Una oración por update mientras trabajas.", "Sin clichés". `communication.md` ahora norma **el fondo** de la comunicación, no la **forma**; el estilo (longitud, tono, formato) queda a libertad del dev. Cambio de fuerza normativa **declarado** (no Patch). El `"¿OK?" en prosa` NO se relaja: se conserva y refuerza en § "Elecciones" ("sin disyuntiva en prosa").
- **Reestructura y reordenamiento de secciones.** "Tono y forma" + "Hilo de la metodología" → "Principio rector", "Hilo conductor y captura de tangentes", "Avance del trabajo: ejecuta-y-reporta vs. gate", "Elecciones: menú de selección", "Pendientes en saludos y conversación trivial", "Reporte de error o bloqueo", "Handoff de sesión", "Idioma", "Delegaciones". Orden **abstracto→concreto + procedural**: principios → foco/hilo conductor → avance → mecánica de elecciones → protocolos situacionales → convención (Idioma) y punteros (Delegaciones). Referencias reapuntadas en `general/index.md`, `hooks/README.md`, `process/execution.md`, `workflow/pendings.md`, `general/onboarding.md`, `skills/wakeup/SKILL.md`, `process/phase-transitions.md`.
- **"Cierre de turno"** pierde el cuantificador "1–2 oraciones" (contradecía "no se norma estilo") y ahora **mantiene el hilo conductor**: reporta qué cambió/qué sigue con el foco en el asunto de fondo y, cuando el fondo concluye, ofrece cerrar como menú (no disyuntiva en prosa).

### Added

- **Confianza en la conclusión** (reposiciona una obligación existente, no inventa eje): cuando la conclusión BLUF descansa en una suposición sin verificar, su marcador (`[asumido]`/`[dominio sin research]` de `principles.md` § "Suposiciones explícitas antes de afirmar") va en la primera línea.
- **Contrato de desacuerdo / push-back** (bullet en § "Avance del trabajo"): objetar con evidencia antes de proceder; no-bloquea → nómbrala y procede; bloquea → la objeción es una opción del menú; el dev puede override.
- **Tangente del dev consolidada** → se ofrece como menú (§ "Elecciones"): formalizar vs. retomar el foco.
- **Captura de tangente menor**: mención específica (qué/dónde) + alta en `neb.db` con el contexto disponible, sin desviarse a investigarla en el momento (norma elevada desde el ejemplo que se eliminó). Los menores capturados se recuerdan por prioridad **al agotarse el foco (antes del cierre)** y en saludos — no se difieren al olvido hasta el próximo arranque.
- **Transición de fase/paso sin gate no se consulta**: se reporta el paso cerrado y se continúa (no "¿procedo a la siguiente?"). Hace explícito el ejecuta-y-reporta en las transiciones de fase y **resuelve la asimetría diferida** en 3.9.0 (b) / 3.10.0 (donde "¿Procedo a Fase X?" se había dejado sin cambiar). Norma elevada desde el ejemplo que se eliminó.
- **Reporte de error/bloqueo**: además de "qué falla / qué bloquea / qué opciones", incluye impacto y estado (reversibilidad; noción de `incidents.md` § "Severidad"), qué se intentó y descartó, y separa lo confirmado/citable de la causa hipotética.
- **Granularidad del tradeoff en gates de alto impacto**: cada opción explicita qué se gana / qué cuesta o arriesga / cuán reversible es (por la misma propiedad que define el gate).

### Fixed

- **Delegación circular del aviso `autoCompactEnabled`**: el borrador delegaba el aviso a `hooks/README.md`, que lo delegaba de vuelta a `communication.md` (sin SessionStart hook ejecutable) → comportamiento huérfano. Se conserva el failsafe inline en § "Pendientes en saludos y conversación trivial"; § "Delegaciones" deja al hook solo el refresco automático del draft (`PreCompact`).
- **Poda de coherencia** (criterio de corte de `principles.md`): coletilla de degradación sin-UI duplicada, eslogan "capturar → priorizar → re-superficiar", prosa justificativa de context-completeness, glose de notación de cita de pendiente (vive en el canónico), anglicismo "on-topic" → "dentro del foco", ejemplo redundante "entrega a producción → menú", coletilla "ni descarrila…", "el loop se cierra solo" (relleno + anglicismo), y "el hilo" → "el hilo conductor" (consistencia de término tras la revisión final de redacción).

## [4.9.0] - 2026-06-15

### Added

- **Notación canónica de cita de pendientes** (`tooling/pendings.md` § "Cómo citar un pendiente"): la cita canónica es el **`[slug]`**; el número, si se usa, es el `id` de `neb.db` como `PD-<id>`. El `#NNN` del `pendings.md` histórico queda **retirado** — la migración a SQLite asignó `id` autoincrement y descartó el número del markdown, que colisiona y no resuelve contra `neb.db`. Reflejado en `general/communication.md` (recordatorio de pendientes), `skills/pendings-review/SKILL.md` (triage) y `workflow/pendings.md` (nota de deprecación del modelo plano).
- **`pendings.py show` resuelve por id o por slug**: nueva `resolve_pending_ref()` acepta `<id|#id|PD-id|[slug]|slug>` (tag exacto → substring), reporta ambigüedad con candidatos y aclara en "no encontrado" que el `#NNN` markdown no resuelve. Tests `TestResolvePendingRef` (suite 77/77).

### Fixed

- **Defecto de comunicación raíz**: las ~100 referencias `#NNN` a pendientes en `MEMORY.md` y memorias `project_*.md` usaban la numeración markdown muerta (0 de 23 en `MEMORY.md` resolvían bien). Reescritas a `[slug]` y notación canónica establecida para que no recurra.

## [4.8.0] - 2026-06-15

### Changed

- **`general/communication.md` § "Tono y forma" (menú de selección):** se nombra explícitamente el anti-patrón **disyuntiva en prosa** — no formular elecciones como «¿A o B?» / «¿seguimos o lo dejamos?» (tampoco al cerrar el turno), porque invitan a respuestas ambiguas («ok», «sí») que no mapean a una rama. Toda elección, incluida la de continuación/cierre, va como menú; si el dev responde ambiguo a una elección, el defecto es de la pregunta, no de la respuesta. Complementa el sub-bullet "Premisa verificada" (4.7.0).

## [4.7.0] - 2026-06-15

### Changed

- **`general/communication.md` § "Tono y forma" (menú de selección):** las opciones ofrecidas al dev deben tener **premisa verificada** — comprobar con lecturas baratas (git/grep/read) que cada opción aplica, antes de enumerarlas. Nada especulativo "por si acaso": una opción cuya validez no se comprobó traslada al dev el costo de descubrir que no aplica. Si la premisa es incierta y cara de comprobar, la opción se formula como «verifico X primero» (la verificación es la acción), no como una rama equivalente. Es el principio context-completeness (no asumir; verificar) aplicado al diseño de opciones.

## [4.6.0] - 2026-06-15

### Fixed

- **El corrector de prompts ya no "responde" en vez de corregir.** La subinvocación `claude -p` (Haiku) de `preprocess-prompt.py` heredaba el `SessionStart` del dev, así que `neb-bootstrap-context.py` le inyectaba el arranque de Neb (instrucciones de asistente + pendientes); con un prompt-pregunta, Haiku respondía la consulta en lugar de corregir ortografía. Ahora `neb-bootstrap-context.py` es inerte dentro de la subsesión interna del corrector. Origen: dogfooding del REQ `neb-pendings-ruteo-consulta-gap`.

### Changed

- **Contrato "hooks inertes en subsesión interna del corrector"** generalizado y documentado. Toda subinvocación `claude -p` del corrector queda marcada y **ningún hook de Neb con efectos de sesión** actúa en ella:
  - Nuevo helper compartido [`hooks/lib/subsession.py`](hooks/lib/subsession.py) (`is_internal_subsession`, `mark_internal_subsession`) — fuente única de los nombres de bandera y la lógica de detección.
  - **Bandera renombrada** `CLAUDE_PREPROCESS_RECURSION` → `NEB_INTERNAL_SUBSESSION`, con la vieja como **alias legacy** (deprecado, retiro diferido a un major). `preprocess-prompt.py` setea **ambas** y todos los consumidores chequean **ambas**, para tolerar plugins de distinta versión en el equipo durante la transición.
  - Guarda **añadida** donde faltaba: `bootstrap/neb-bootstrap-context.py` (SessionStart), `hooks/usage-tracker.sh` (no contar tokens de Haiku contra el REQ activo), `hooks/logbook-sync.{sh,ps1}` (no escribir la subsesión a la bitácora).
  - Guarda **migrada** al nombre nuevo (manteniendo legacy) en `notify-on-stop.{sh,ps1}` y `notify-on-permission.{sh,ps1}`.
  - Doc: contrato canónico en `tooling/prompt-preprocessing.md` § 9; actualizados `hooks/README.md`, `tooling/notify-on-stop.md`, `tooling/notify-on-permission.md`, `templates/claude-user-settings.json.template`.
  - Tests: `hooks/tests/test_subsession.py` (helper + bootstrap inerte con bandera nueva/legacy + inyecta sin bandera). Suite total 72 verde.

## [4.5.0] - 2026-06-15

### Changed

- **Ruteo de consultas de pendientes hacia la capa de valor.** Una consulta de lectura simple ("cuáles son mis pendientes") debe encaminarse por el skill [`pendings-review`](skills/pendings-review/SKILL.md) —que prioriza por banda y aplica la brújula `compas.md`— y no por el `pendings.py list` crudo, que omite priorización y el nudge de `compas.md`. Ajustes:
  - `skills/pendings-review/SKILL.md`: la `description` ahora dispara también en consultas de lectura simple y declara el skill como ÚNICA vía de consulta del dev; el CLI `list`/`show` queda como acceso de bajo nivel/debug. Se eliminó la cláusula de exclusión "pendings.md plano" (fuente ya migrada a `neb.db`, generaba duda de activación).
  - `general/communication.md`: el disparador de saludos/conversación trivial recuerda los pendientes **más relevantes** (top por prioridad, no volcado) desde `neb.db` vía el skill, y encamina a `/pendings-review` para el pase completo. Antes citaba `pendings.md` plano y empujaba al volcado.
  - `tooling/pendings.md`: nueva sección "Vía de consulta del dev: el skill, no el CLI crudo" — `list`/`show` son bajo nivel/debug, no vía equivalente.
  - `skills/wakeup/validation-prompts.md`: ejemplo "Hola" alineado (capa de prioridad, no volcado).
  - `workflow/pendings.md`: el flujo "Lee… cuando el dev pide pendientes" se sirve por el skill sobre `neb.db`, no leyendo el `.md` plano.
  - `profiles/self-applied/skills.md`: celda "Aplica en" del skill incluye los disparadores de lectura simple y declara el skill como única vía de consulta.

  Origen: dogfooding del REQ `neb-pendings-sqlite` — la prueba de validación expuso que la consulta terminaba en el volcado plano y se perdía la brújula. Detalle en el change MD `2026-06-15-neb-pendings-ruteo-consulta-gap.md` (workspace `methodology`).

## [4.4.0] - 2026-06-15

### Added

- **Migrador `pendings.md` → SQLite** (`bootstrap/migrate-pendings-md.py`). Parsea el `pendings.md` (secciones `## …` → temas; ítems numerados → pendings; sub-ítems `(a)/(b)…` → pendings propios ligados al padre vía `pending_link`), migra **solo los activos** (omite los cerrados), idempotente (de-dup por `context_origin`), con **dry-run** por defecto y `--apply` transaccional. Reusa `hooks/lib/pendings.py` + `_db_shared.py` (sin reimplementar schema ni patrón de escritura). Tests: `hooks/tests/test_migrate_pendings_md.py`.

### Fixed

- **CLI de `pendings.py` en Windows**: `cli_main` reconfigura `stdout`/`stderr` a UTF-8 (`errors='replace'`). Antes `list`/`show`/`triage` crasheaban con `UnicodeEncodeError` en consola cp1252 al imprimir `context_origin` con caracteres como `→`/`↔`.

## [4.3.0] - 2026-06-15

### Added

- **Pendientes en SQLite (`neb.db`) — núcleo.** Nuevo backend de pendientes del dev sobre la misma DB del logbook: **6 tablas relacionales** (`pending`, `pending_note`, `pending_link`, `topic`, `topic_link`, `pending_topic`; enums en inglés) en `hooks/logbook-schema.sql`, módulo compartido `hooks/lib/_db_shared.py` (resolver dual-mode `neb.db ∨ neb-logbook.db`, `_connect` con `busy_timeout`, `begin_immediate`) y `hooks/lib/pendings.py` (CRUD + ciclo de vida reversible con bitácora append-only, matching de temas con **FTS5 on-demand + fallback LIKE**, y triage). Migración one-shot idempotente `bootstrap/migrate-neb-db.py` (rename `neb-logbook.db` → `neb.db`, dual-mode permanente para máquinas sin migrar).
- **Recomendador de pendientes (`/pendings-review`) + brújula `compas.md`.** Nuevo skill `pendings-review` que opera el pase unificado sobre `neb.db`: marca obsoletos (señal dura auto-archivada con causa; juicio = sugerencia con confirmación), recomienda prioridad **por tema**, agrupa relacionados como candidatos a REQ conjunto y hace fan-out a soluciones profundas (top-K) vía el agente funcional `pendings-recommender`. La prioridad sigue la jerarquía **prompt > `compas.md` > señales intrínsecas**. `~/.claude/compas.md` (local, no versionado, mantenido por Claude) es la **fuente única** del peso de cada tema; un objetivo puede delegar el orden fino al roadmap real de un proyecto (`roadmap`, frontmatter `priority`/`subsystems`, normalización slug↔subsistema sin acentos y por token, override `NEB_ROADMAP_DIR`). Si la brújula es insuficiente, el recomendador infiere objetivos, pregunta al dev y la escribe — no inventa pesos.
- **Agente funcional `pendings-recommender`** (tools Read/Grep/Glob): invocado por el skill, propone abordaje de solución sin escribir la DB. Registrado en `process/roles-invocation.md` § "Agentes funcionales" (sede nueva; no entra en la cobertura por fase).

### Changed

- **Rename de la bitácora `neb-logbook.db` → `neb.db`** reflejado en la documentación: `docs/how-it-works.md`, `docs/user-guide.md`, `tooling/logbook.md`, `workflow/index.md` (+ nota del dual-mode en `workflow/logbook.md`). El resolver dual-mode (`neb.db ∨ neb-logbook.db`) introducido en la sub-entrega A queda como contrato permanente.
- **`profiles/self-applied/index.md`**: se reconcilia "Sin código ejecutable" — el profile sí produce código ejecutable (los hooks/módulos de `neb.db`), validado con tests unitarios (`py -m unittest`); el supuesto general (entregable markdown, validación roles + coherencia) sigue aplicando al resto.

## [4.2.0] - 2026-06-14

### Added

- **Pre-push: 5° gate — sincronía `plugin.json.version` ↔ `VERSION`.** `hooks/pre-push-changelog` ahora bloquea el push si el campo `version` de `.claude-plugin/plugin.json` no coincide con `VERSION`. Cierra el hueco que permitió publicar el plugin desincronizado: `claude plugin update` compara el semver de `plugin.json.version`, así que un campo congelado hace que el manager reporte "already at latest" y ningún marketplace que liste el plugin entregue las versiones nuevas, aunque `main` esté adelante. El único chokepoint de publicación (el push a la raíz del repo) ahora rechaza un `plugin.json` desincronizado. Usa el mismo resolver de Python que los gates 1 y 4.

### Changed

- **`bootstrap/bump-version.sh` ya no degrada en silencio sin Python.** Antes, si no encontraba intérprete de Python, dejaba `plugin.json.version` sin sincronizar con solo un aviso "hacelo a mano" — la causa raíz de la deriva de versión. Ahora verifica el intérprete **al inicio**, antes de escribir `VERSION` o crear el fragment, y aborta ruidoso si `.claude-plugin/plugin.json` existe y no hay Python, en vez de dejar el repo a medio bumpear. Junto con el 5° gate del pre-push, la sincronía de `plugin.json` queda garantizada en el camino feliz y forzada en el chokepoint de publicación.

### Fixed

- **`plugin.json.version` quedó congelado en 3.8.0 desde 3.9.0.** Los bumps 3.9.0 → 4.1.0 avanzaron `VERSION` y `changelog.d/` pero no el campo `version` de `.claude-plugin/plugin.json` (la sincronización dependía de encontrar Python en el equipo que bumpeaba y se omitió). Como `claude plugin update` compara ese campo, el manager reportaba "already at latest 3.8.0" y bloqueaba la llegada del contenido nuevo al plugin instalado. Sincronizado a la versión publicada en este release. Todo marketplace resuelve el plugin desde el mismo HEAD del repo, así que el catch-up en la raíz basta para destrabar la actualización en todos ellos, sin tocar ningún `marketplace.json`.

## [4.1.0] - 2026-06-14

### Changed

> Cambio de **fuerza normativa** declarado (ver `methodology/principles.md` § "Declarar (nunca Patch)"). Minor: ajusta el lineamiento de comunicación de transiciones de fase.

- **Transiciones de fase: comunicar por acción, no por número; alinear con el modelo de § "Tono y forma".** `general/communication.md` § "Hilo de la metodología": el ejemplo `"Listo Fase 4. ¿Procedo a validar (Fase 5)?"` se reemplaza por comunicar el avance por la **acción** (implementar/validar/entregar), con el número de fase como anotación opcional, siguiendo el modelo **ejecuta-y-reporta / menú** de § "Tono y forma" (el "¿procedo?" en prosa queda retirado también aquí). Cierra la **asimetría** que 3.10.0 dejó fuera de scope: § "Tono y forma" había retirado el "¿OK?"/"¿procedo?" en prosa pero § "Hilo de la metodología" seguía modelándolo. Motivo: el número de fase es jerga interna opaca de cara al dev (evidencia de uso: el propio autor no resolvió "Fase 4" en el flujo).

### Notes

- Afecta `general/communication.md` (§ "Hilo de la metodología").
- Revierte —con evidencia de uso— la decisión "fuera de scope" de 3.10.0 § Notes sobre transiciones de fase: no era falsable que la asimetría no estorbara; estorbó.
- Cierra `pendings.md` #208(c).

## [4.0.0] - 2026-06-14

### Changed

> Cambio de **fuerza normativa Major** declarado (ver `methodology/principles.md` § "Declarar (nunca Patch)" y `CLAUDE.md` § "Versionado SemVer"). Major: elimina un tipo del ENUM de **Tipos de validación** (no el ENUM de estados, que se mantiene) y el criterio de cierre por sesiones en todos los profiles.

- **Eliminada la "validación diferida en uso"** como tipo de validación y criterio de cierre, en **toda la metodología** (`self-applied` + overlays `research`/`skill-authoring`/`profile-authoring` + el template de profiles nuevos). Motivo: "≥N sesiones sin reporte negativo" no es un criterio formal sino un **proxy de su ausencia** — no es falsable, no tiene instrumentación que lo corrobore y produce REQs en limbo "En validación". Era observación post-entrega, no validación.
- **Reemplazo — validación verificable al entregar + cierre inmediato; señal-en-uso → Fase 9.** Cada profile cierra con su mecanismo verificable: `self-applied` por revisión de roles (`qa-process-engineer`) + coherencia estática + dogfooding; `research` por `fact-check-reviewer` (F4); `skill-authoring` por smoke load + `validation-prompts` (F5). La observación en uso (utilidad, triggering, fricción) es retroalimentación de Fase 9 —que sí está instrumentada (disparadores en `process/improvement.md`)—, no un gate que difiera cierre ni push.
- **El push del entregable ya no se difiere** (`process/version-control.md` § Push): en `self-applied` el commit/push del entregable `.md` es autónomo por el **ownership de `.md`** (no por una validación diferida). Resuelve de paso la inconsistencia entre `profiles/self-applied/deployment.md` y `process/change-control-gate.md`/`version-control.md` sobre la autonomía del commit en `self-applied`. La **entrega temprana del registro** sobrevive solo como mecanismo de **relevo cross-dev** (entorno compartido), desacoplada del cierre.

### Notes

- Afecta: `methodology/vocabulary.md`, `methodology/skills.md`, `methodology/roles-catalog.md`, `methodology/change-control-policy.md`, `process/version-control.md`, `process/change-control-gate.md`, `process/delivery.md`, `process/improvement.md`, `process/phase-transitions.md`, `profiles/self-applied/index.md`, `profiles/self-applied/deployment.md`, `profiles/research/index.md`, `profiles/research/deployment.md`, `profiles/research/roles.md`, `profiles/skill-authoring/index.md`, `profiles/skill-authoring/skill-creator-integration.md`, `profiles/profile-authoring/index.md`, `profiles/profile-authoring/deployment.md`, `profiles/profile-authoring/templates/deployment.md.template`, `profiles/index.md`, `templates/change.md.template`.
- **Cierre retroactivo**: los REQs antes "En validación" diferida (#204/#205/#207/#208 en `pendings.md`) cierran porque su **validación verificable al entregar ya está satisfecha** (gate `qa-process-engineer` + commit/push hechos en cada uno). No se invoca "sin reporte negativo en N sesiones" — sería el proxy que este REQ invalida.
- Los `changelog.d/*.md` históricos que mencionan "validación diferida" no se reescriben (registro histórico).

## [3.10.1] - 2026-06-14

### Fixed

- **Referencia rota en `process/planning.md`.** La tabla "Cuándo aplica cada aprobación" (fila "No-formal") citaba `general/communication.md` § "Tono de respuesta según trigger de formalización", sección **inexistente** — el contenido canónico vive en `process/phase-transitions.md` § "Trigger de formalización" (`communication.md:53` solo lo enlaza). Se reapunta la referencia al canónico. Detectado en el plan-review de 3.10.0 (reportar-no-fix).

## [3.10.0] - 2026-06-14

### Changed

> Cambio de **fuerza normativa** declarado (ver `methodology/principles.md` § "Declarar (nunca Patch)"). Minor: no rompe imports. Evoluciona el lineamiento de comunicación de decisiones a partir de su **validación en uso**.

- **Comunicación de decisiones: gate de altitud + menú de selección, retirando el "¿OK?" en prosa.** `general/communication.md` § "Tono y forma": se reemplazan los bullets "Default + binaria" y "Numeración" por tres reglas planas. (a) **Altitud anclada a gate observable**: Claude ejecuta-y-reporta toda decisión que no requiera input que solo el dev tenga ni dispare un gate de autorización (entrega que toca el entregable del destino) — el criterio deja de ser el juicio introspectivo "reversible/bajo riesgo" (anti-patrón `principles.md` § "prescribir el razonamiento interno"). (b) **Menú de selección** para cualquier elección enumerable (en Claude Code, `AskUserQuestion`), con **degradación a lista numerada en prosa** cuando no hay UI interactiva (headless, cron, remoto); la recomendada primero, la inacción como opción explícita, y en un gate la selección de aprobación constituye el OK explícito. (c) El **"¿OK?" en prosa queda retirado**: todo punto de decisión es ejecuto-y-reporto o menú. Origen: el bullet previo producía confirmaciones ambiguas ("ok"/"ve con eso") y comprimía bifurcaciones ocultando opciones — defecto detectado por la validación-en-uso del propio lineamiento (subsume `pendings.md` ítem 114).

### Notes

- Afecta `general/communication.md`, `general/onboarding.md`, `skills/wakeup/SKILL.md` (las dos últimas alinean "opciones numeradas" → "menú de selección"; la numeración sobrevive como fallback, así que sus referencias no quedan huérfanas).
- **Término neutro** "menú de selección" en el cuerpo normativo (con `AskUserQuestion` nombrado una sola vez como implementación en Claude Code) para no acoplar el lineamiento baseline a un tool del harness — `communication.md` es punto de customización para adoptantes externos.
- **Vocabulario agnóstico de profile**: el gate se ancla a "entrega que toca el entregable del destino" (commit, deploy, migración, config), no a "commit/deploy", para cubrir profiles sin deploy (`self-applied`, `research`).
- **Fuera de scope** (decisión del dev): § "Hilo de la metodología" — las transiciones de fase ("¿Procedo a Fase X?") **no cambian**; persiste la asimetría aceptada conscientemente. Consistente con el follow-up (b) diferido en 3.9.0.
- Validación diferida en uso (profile `self-applied`): tag `[neb-decisiones-menu-y-altitud-validacion-uso]` en `pendings.md`.

## [3.9.0] - 2026-06-14

### Changed

> Cambio de **fuerza normativa** declarado (ver `methodology/principles.md` § "Declarar (nunca Patch)"). Minor: no rompe imports. Reancla el ownership en el rol/función **sin mover la frontera** de lo autónomo (enfoque Aditivo).

- **Ownership de `.md` reanclado en la función, no en la extensión.** `methodology/change-control-policy.md` § "Ownership de archivos `.md`": el criterio primario de autonomía pasa a ser el **rol** del artefacto —lo que Neb genera y administra (registros del requerimiento, `pendings`, planes, métricas)—; el formato `.md` queda como criterio **derivado**. Alinea la política con `methodology/vocabulary.md` § "Discriminador registro vs entregable: el rol, no la extensión", que ya predicaba rol-sobre-extensión pero no estaba reflejado en la política de ownership. **Enfoque Aditivo**: la frontera de lo autónomo no cambia (todo artefacto que Neb genera es hoy `.md`); el cambio nombra *por qué* esos artefactos son de Claude y resiste casos futuros donde un artefacto de proceso no sea `.md`.
- **Hook `preprocess-prompt` (modo `full`): el preámbulo defiere al gate en vez de exigir OK genérico.** `hooks/preprocess-prompt.py` (`build_preamble`): el punto 2 ya no pide confirmación antes de *toda* escritura —lo que endurecía el gate más que la propia metodología y forzaba OK incluso para registros y cambios `.md`-only—; ahora remite al gate de autorización del baseline (que ya exime artefactos que Neb genera, `.md`-only y autonomías declaradas por proyecto). Corrige el anti-patrón de duplicar el gate del baseline sin sus excepciones (`methodology/principles.md` § Anti-patrones).

### Notes

- Afecta `methodology/change-control-policy.md`, `process/change-control-gate.md`, `process/version-control.md`, `workflow/changes.md`, `profiles/self-applied/deployment.md`, `hooks/preprocess-prompt.py`, `tooling/prompt-preprocessing.md`.
- Comportamiento neto sin cambio (Aditivo): un `.md` de documentación de producto del cliente sigue siendo autónomo como antes; lo que cambia es el fundamento y, vía el hook, que Claude deja de pedir OK para los registros que Neb ya tenía permitido confirmar.
- **Fuera de scope** (REQ-patch separados — ver `pendings.md`): (a) relajar el gate de confirmación para "plan aprobado + cambio de bajo riesgo/recuperable" (repasar incidentes terzab2c `653b3551`, PRD); (b) comunicar transiciones de fase por **acción** y no por número de fase desnudo de cara al dev (`general/communication.md` § "Hilo de la metodología").

## [3.8.0] - 2026-06-14

### Changed

> Cambio de **fuerza normativa** declarado (ver `methodology/principles.md` § "Declarar (nunca Patch)"). Minor: no rompe imports. Corrige el diseño del disparador introducido en 3.7.0.

- **Disparador del backend central: de opt-out a OPT-IN por proyecto.** El central (compartido) ahora se usa **solo** cuando hay `NEB_LOGBOOK_ENDPOINT` **y** el proyecto lo declara con el marcador `<!-- neb-logbook: central -->` en su `CLAUDE.md`. Sin el marcador, la bitácora queda **local-only** (el default). Invierte el comportamiento de 3.7.0 (que publicaba todo por default salvo opt-out `<!-- neb-logbook: local -->`). Razón: la **bitácora local (REQ A) ya cubre el relevo del propio dev**, así que el central —que publica el trabajo al catálogo del equipo— debe ser una decisión deliberada por proyecto, no el default. Privacidad por defecto.
- **Modo exploratorio: vuelve a local-only por default.** Las sesiones exploratorias solo se publican al catálogo si el proyecto activó el central (opt-in); sin el marcador no salen de la máquina.

### Notes

- El marcador `<!-- neb-logbook: local -->` de 3.7.0 queda **obsoleto**, reemplazado por su inverso `<!-- neb-logbook: central -->`.
- Afecta `hooks/lib/logbook.py` (`_is_shared`), `general/profile-detection.md`, `workflow/logbook.md`, `tooling/logbook.md`, `process/version-control.md`, `workflow/changes.md`, `docs/user-guide.md`, `hooks/README.md`, `server/INSTALL.md`, `bootstrap/env.example`.
- El **despliegue** del central (servidor, DB, exposición tras proxy) no cambia; solo el disparador del cliente.

## [3.7.0] - 2026-06-14

### Added

- **Backend central de referencia de la bitácora de relevo (REQ B).** Servidor `server/logbook_server.py` (stdlib `http.server` + PyMySQL) + DDL MariaDB `server/schema.sql` (`work`/`event`/`transcript`; unicidad por modo vía columna generada `identity_key`; `FULLTEXT(text_plain)`; `ROW_FORMAT=COMPRESSED`) + `server/INSTALL.md` + retención manual `server/purge.py` + `server/.env.example` + `server/requirements.txt`. Contrato HTTP con auth `Bearer NEB_LOGBOOK_TOKEN`: `publish`/`claim`/`release`/`request-takeover`/`forced-release`/`rename`/`archive`/`transcript`/`search`/`work`. Habilita el **relevo cross-dev real** (lock atómico cross-máquina + transcript buscable). El despliegue concreto en la infra del adoptante queda fuera del núcleo.
- **Cliente remoto** en `hooks/lib/logbook.py`: modo `sync` (drena el outbox de works `dirty` —`req` y `exploratory`— + sube el transcript incremental, con parser `text_plain` que excluye `tool_result` y líneas estructurales) disparado detached por el hook; `_project_id` derivado del git remote (`host/owner/repo`); `cli_search`/`cli_request`/`cli_rename` reales contra el central; columna `conflict` (migración idempotente) para reportar el 409 sin loop.

### Changed

> Cambios de **fuerza normativa** declarados (ver `methodology/principles.md` § "Declarar (nunca Patch)"). Minor: no rompen imports.

- **Lock de la bitácora: de informativo a enforcement atómico cross-dev.** Con backend central, el lock se arbitra atómicamente (`UPDATE … WHERE lock_state IN(...)`, veredicto por `rowcount`; nunca read-then-write); `solicitar el mando` y `search` quedan operativos. En local-only el lock sigue informativo (sin cambio).
- **Modo exploratorio: de local-only a compartido por default.** Con central configurado y sin opt-out, las sesiones exploratorias también se publican al catálogo (visibilidad + búsqueda del corpus; **no** relevables cross-dev — `claude_session_id` solo vale en su máquina origen). Antes el exploratorio no subía al central (`workflow/logbook.md` § Dos modos).
- **Disparador del "entorno compartido": de juicio de Claude a determinista.** Con `NEB_LOGBOOK_ENDPOINT` configurado y sin **opt-out por proyecto** (marcador `<!-- neb-logbook: local -->` en el `CLAUDE.md`), el trabajo se publica al central por default. Reemplaza el disparador por juicio de Claude que 3.6.0 dejó como temporal.

### Notes

- **Acota la promesa de 3.6.0**: el disparador determinista per-profile/proyecto que 3.6.0 dejó asignado a REQ B se entrega aquí **por presencia de endpoint + opt-out por proyecto**; el **opt-out por perfil** queda diferido a un REQ posterior (el hook no conoce el perfil de forma trivial).
- **Privacidad**: montar el central comparte todo el trabajo por default (incl. exploratorias); el opt-out por proyecto es el escape. Un dev que trabaja solo no necesita el central. Ver `server/INSTALL.md`.

## [3.6.1] - 2026-06-14

### Changed

- Homologación de redacción (residuos del modelo proyección-no-identidad): `workflow/memory.md` ("draft del changes MD" → "draft del change MD (el registro del requerimiento)") y el comentario de `hooks/usage-tracker.sh` ("draft del REQ activo" → "draft del change MD (registro) del REQ activo"). Sin cambio de fuerza normativa.

## [3.6.0] - 2026-06-14

### Changed

- **Entrega temprana del registro del requerimiento** — el registro (change MD; ver `methodology/vocabulary.md` § "Registro del requerimiento") puede **confirmarse y entregarse (push) de forma autónoma desde que existe el draft** (al aprobar el plan / entrada a Fase 4), **desacoplado** de la entrega del entregable, **cuando el entorno de validación es compartido** (lo determina Claude; señal determinista: el `work` se publica a una bitácora compartida — backend central). Relaja la regla previa "El draft no se confirma hasta el cierre" (`workflow/changes.md` § Ciclo de vida del draft). La autonomía deriva del ownership de `.md` ya existente. **Carve-out**: la validación diferida del **entregable** (p. ej. los `.md` de la metodología misma en `self-applied`) mantiene su gate intacto — son `.md` distintos (el registro documenta *sobre* el REQ; el entregable es lo producido). Invariantes preservados: gate de OK para entregable/código, commits/pushes mixtos por componente más restrictivo, `--no-verify` prohibido, `push --force` a `main`/`master` con gate.
- Archivos alineados a la nueva regla: `workflow/changes.md` (§Ciclo de vida — núcleo), `process/version-control.md` (§Push), `profiles/self-applied/deployment.md`, `methodology/change-control-policy.md` (§Ownership `.md`), `workflow/logbook.md` (§Relación — `work` publicado ⟹ registro entregado), `process/change-control-gate.md`, `process/documentation.md`, `process/delivery.md`, `methodology/vocabulary.md`.

### Notas

- El disparador determinista per-profile/proyecto del entorno compartido (config del backend central de la bitácora) lo implementa el REQ B de la bitácora (handoff); hoy aplica el disparador por juicio de Claude.

## [3.5.0] - 2026-06-14

### Added

- **`methodology/vocabulary.md` — secciones "Requerimiento (REQ)" y "Registro del requerimiento"**: definen el REQ como **unidad abstracta de trabajo** (no un documento) y el change MD como su **registro** (proyección documental versionada, relación 1↔1 incluso cross-repo). Modelo **proyección-no-identidad**, consolidando por referencia ~20 propiedades del REQ (estados, complejidad, riesgo, cross-repo, definición de done, validación diferida, formas especiales, proyecciones en memoria/bitácora/pendings, métricas). "Registro del requerimiento" = término agnóstico para la subclase documental (change MD canónico + incident MD variante), discriminada del entregable por el **rol, no la extensión `.md`**.

### Changed

- **Reconciliación identidad→proyección en el core** — resuelve la inconsistencia interna (`traceability.md` afirmaba "un requerimiento es un Change MD" mientras `logbook.md`/`how-it-works.md` ya usaban proyección-no-identidad). Cardinalidad 1↔1 preservada en todos los casos:
  - `workflow/traceability.md`: "un requerimiento es un Change MD" → "a un requerimiento le corresponde un único Change MD que lo registra (1↔1)"; "el eje" → "eje documental"; grafo nominal y caso cross-repo en lenguaje de registro.
  - `workflow/changes.md`: título → "registros de requerimientos por proyecto"; "un MD por requerimiento" reexpresado como cardinalidad de registro; incident MD = variante con su propia 1↔1.
  - `workflow/index.md`: fila "Requerimiento" → "Change MD (registro del requerimiento)".
  - `process/phase-transitions.md`: la fase es propiedad del REQ; el change MD la **registra**, no la define.
  - `methodology/done-criteria.md`: las condiciones se verifican sobre el registro (change MD) del REQ.
  - `methodology/vocabulary.md` §Estados: estado y fase son propiedades del REQ que el artefacto registra.
  - `general/communication.md`: "draft del requerimiento" → "draft del change MD (registro del requerimiento)".

## [3.4.0] - 2026-06-13

### Added

- **Bitácora de relevo (`logbook`)** — registro cross-dev de trabajos a medias para retomar una sesión interrumpida (tokens agotados, corte de luz/red, handoff a otro dev) **en otra máquina o cuenta**, conservando el contexto vía el transcript. Backend **pluggable**: SQLite local por defecto (`hooks/logbook-schema.sql`, universal, sin infra) que además es outbox; el backend central (servidor de referencia + API) llega en un REQ posterior. Modelo de **ownership** (lock `owned`/`released`/`takeover_requested`; operaciones tomar/liberar/solicitar + `liberar --forzado` con confirmación humana). **Dos modos**: con-REQ (relevo cross-dev) y exploratorio (registro liviano + `--resume` local). Piezas: artefacto `workflow/logbook.md`; mecánica `tooling/logbook.md`; comando + skill `/logbook`; hook `logbook-sync` (`Stop`/`SessionEnd`/`PreCompact`, opt-in, captura estado + transcript a SQLite). Plan: epic "bitácora de relevo" (REQ A — núcleo + backend local).

### Changed

- **`process/execution.md` §"Gestión de sesiones (handoff)"**: nuevo apartado de **relevo cross-dev** (publicar/retomar/relevar) y **Capa C** (trabajo en vuelo) documentada como **prosa que el agente redacta al pausar** (los procesos no se serializan; el hook no los introspecta).
- **`methodology/vocabulary.md`**: declarado el ENUM de lock de la bitácora **ortogonal** al ENUM de estados del requerimiento (un `work` archivado no altera el estado canónico del REQ).
- **`workflow/pendings.md` / `workflow/metrics.md`**: frontera explícita entre "Sesiones pausadas" (reanudar la propia sesión local con `--resume`) y la bitácora (relevo cross-dev / cross-máquina).

# 3.3.1

## Corregido

- **Fallback de `NEB_SRC` marketplace-agnóstico** (`commands/wakeup.md`, `skills/wakeup/SKILL.md`): el glob del cache del plugin asumía instalación desde el marketplace `neb` (`cache/neb/neb/*/`). Generalizado a `cache/*/neb/*/` — el primer segmento es el nombre del marketplace de instalación, que puede ser cualquiera (p. ej. un marketplace interno de equipo que liste este plugin).

## [3.3.0] - 2026-06-11

### Added

- **Simetría del kernel always-on** (de la auditoría: el arranque era duro en la entrada del flujo y blando en la cola). `process/phase-transitions.md` (inyectado en toda sesión) ahora trae: **mapa numerado de las 9 fases** + regla de escalamiento de contexto ("los archivos de fase se leen al entrar a la fase; la fase actual se determina del Estado del change MD activo"); **gates de cola espejo** (OK explícito por confirmación que toca el entregable · no entregar a producción sin Fase 5 o salto con OK · no `Cerrado` sin validación) — el detalle sigue canónico en `change-control-gate.md`/`delivery.md`; **cláusula de conflictos y vacíos normativos** (reportar con alternativas, nunca resolver en silencio) y **no-relajar por override** desde el núcleo.

### Changed

- **Eliminada la doble carga en sesiones del repo neb** (~4,600 tokens/sesión, re-aplicada tras cada compactación): `CLAUDE.md` ya no importa `@general/startup.md` ni `@workflow/index.md` (el hook del plugin los inyecta); conserva `@profiles/self-applied/index.md`. Contribuidor sin plugin: instalarlo (comentario en el CLAUDE.md).
- **`general/index.md` § Orden de lectura alineado con la carga real**: las transversales se separan en "inyectadas al arranque" (las 6 que `startup.md` importa de verdad) y "on-demand con cláusula espejada" (agents, incidents, change-control-gate) — elimina la promesa "(siempre)" sin mecanismo detectada por la auditoría.

## [3.2.0] - 2026-06-11

### Added

- **Pre-push endurecido — único punto de enforcement bloqueante** (de la auditoría externa de carga/adherencia: las 2 reglas de mayor costo-de-fallo eran las peor protegidas). `hooks/pre-push-changelog` ahora encadena 4 gates: (1) **integridad del kernel** — `assemble-startup.py --check` (modo estricto nuevo: exit 1 ante import faltante en la cadena del arranque; el runtime sigue defensivo, pero el maintainer ya no puede publicar un kernel degradado silenciosamente); (2) **términos vetados** — extension point del overlay (`$NEB_WORKSPACE/*/scripts/scan-forbidden-terms.sh` si existe; el guardrail privado corre sin publicarse, con aviso si se omite); (3) **fragment obligatorio** — cambios normativos (fuera de `changelog.d/`, `CHANGELOG.md`, `research/`) exigen un fragment en el mismo push ("Cualquier cambio entra al CHANGELOG" pasa de texto a gate); (4) sincronía `CHANGELOG.md` ↔ `changelog.d/` (gate preexistente). Bypass `--no-verify` se conserva como excepción autorizada. `hooks/README.md` declara explícito que ningún hook del plugin bloquea.

## [3.1.0] - 2026-06-11

### Added

- **Lineamiento "Declarar (nunca Patch)"** en `methodology/principles.md` § "Lineamientos para editar MDs": cambiar la fuerza o el alcance normativo de una regla del baseline (relajar/endurecer, recomendación ↔ obligación, o promover un ejemplo/hipótesis/prosa explicativa a regla) no es redacción — se declara como cambio normativo en el plan y en el fragment del CHANGELOG, y clasifica Minor o Major, nunca Patch. Cierra la clase de cambio que se disfraza de edición editorial pero altera el comportamiento de Claude en sesiones futuras (en un framework auto-aplicado, eso es un cambio metodológico encubierto). Único vacío real detectado por el análisis de autoedición (15 reglas evaluadas: 10 ya existían en forma más fuerte, 1 conflictuaba con artefactos por diseño, 3 se fusionan en este lineamiento). Mapa de redacción de `self-applied` actualizado.

## [3.0.2] - 2026-06-11

### Fixed

- **Review de redacción post-3.0.0** (3 revisores por área; veredicto general: redacción sana, sweep limpio): (1) link roto en `research/README.md` a las convenciones de research (apuntaba al path pre-rename `stacks/` — el README es doc vivo aunque las notas de research sean históricas); (2) `general/profile-detection.md` aclara la coexistencia de los dos marcadores de opt-out (`neb: skip` prevalece sobre `neb-profile: none`); (3) la nota histórica del rename en `methodology/profiles.md` ahora enlaza al CHANGELOG § 3.0.0 (trazabilidad).

## [3.0.1] - 2026-06-11

### Added

- **Mapa de redacción en el profile `self-applied`** (`profiles/self-applied/index.md`): índice de los 4 documentos que norman la redacción/edición de los MDs de Neb (`methodology/principles.md` § "Lineamientos para editar MDs", `CLAUDE.md` del repo, `profiles/profile-authoring/conventions.md`, `methodology/change-control-policy.md`) con cuándo aplica cada uno. Los lineamientos estaban correctamente aislados por capa pero sin descubribilidad — nada decía que eran cuatro lugares. Como `CLAUDE.md` importa el index de `self-applied`, el mapa se carga automáticamente en toda sesión dentro del repo.

## [3.0.0] - 2026-06-11

Cambio mayor: el concepto central **stack** pasa a llamarse **profile** en todo el framework (prosa, paths, identifiers, markers). Razón: "stack" colisionaba con el "tech stack" genérico — las propias heurísticas de detección hablan del stack tecnológico — y el concepto cubre más que tecnología (proceso, roles, deploy, convenciones): es un *perfil de trabajo*. Corte limpio: 3.0.0 solo reconoce los nombres nuevos.

### Changed (BREAKING)

- **Renombres de estructura**: `stacks/` → `profiles/` (con `stack-authoring` → `profile-authoring`); `general/stack-detection.md` → `general/profile-detection.md`; `methodology/stacks.md` → `methodology/profiles.md`; `bootstrap/init-stack-subproject.sh` → `bootstrap/init-profile-subproject.sh`.
- **Marker de workspace**: el overlay del adoptante ahora se descubre por `*/overlays/detect-profile.local.sh` (antes `detect-stack.local.sh`). Consumidores actualizados: `neb-bootstrap-context.py` (discovery del hook), `setup-workspace.sh` (detección, barrido y scaffold).
- **Marcador de opt-out**: `<!-- neb-profile: none -->` (antes `neb-stack: none`). `<!-- neb: skip -->` **no cambia**.
- **Identifiers**: `detect_profile_local`, `get_private_profile_imports`, `PROFILE_NAME`, `PROFILE_DIR`, placeholder de template `{{PROFILE_BASE}}`.
- **Prosa e interfaces**: "profile activo", anuncios `[profile: <X> → <Y>]`, columna "Profile(s) aplicable(s)" en `skills/README.md`, tour de `/wakeup` ("Definir tu primer profile"). Los CHANGELOG/fragments < 3.0.0 conservan el término viejo (la historia no se reescribe).

### Removed (BREAKING)

- **Scripts del modelo clone eliminados** (deprecados desde 2.0.0): `bootstrap/install.sh`, `bootstrap/link-into-project.sh`, `bootstrap/install-skills.sh`, `bootstrap/install-agents.sh`. El plugin auto-descubre skills/agents/commands; el workspace se monta/conecta con `setup-workspace.sh` (vía `/wakeup`).

### Migración 2.x → 3.0

| Qué | Acción |
|---|---|
| Workspace existente | Renombrar `<overlay>/overlays/detect-stack.local.sh` → `detect-profile.local.sh` y dentro: `detect_stack_local` → `detect_profile_local`, `get_private_stack_imports` → `get_private_profile_imports` |
| Imports de profiles propios en CLAUDE.md de proyectos | Si tu overlay renombró su dir (`stacks/` → `profiles/`), actualizar los `@import` |
| Marcador de opt-out | `<!-- neb-stack: none -->` → `<!-- neb-profile: none -->` |
| Plugin | `claude plugin update neb@neb` + sesión nueva |

## [2.2.0] - 2026-06-10

### Added

- **Barrido de workspaces bajo `$HOME`** (nivel 2a de la cascada de `/wakeup`): cuando la raíz actual no es un workspace y no se pasó `--base`, `setup-workspace.sh` barre `$HOME` en una sola pasada de `find` (raíz del workspace a profundidad ≤3; poda ocultos, `node_modules`, `AppData` y `*.bak`) buscando el mismo marker estructural (`*/overlays/detect-stack.local.sh`) y lista lo encontrado en vez de crear a ciegas. El tour ofrece conectar el único resultado o elegir de una lista numerada — el usuario ya no teclea paths a mano. Medido: ~0.2s en Linux, ~4.5s en un home grande de Windows (corre una sola vez, en onboarding).

## [2.1.0] - 2026-06-10

### Added

- **Detección de workspace existente** en `bootstrap/setup-workspace.sh`: en modo default y `--dry-run`, si la raíz actual (git toplevel o cwd) ya es un workspace (markers estructurales: `*/overlays/detect-stack.local.sh` — el mismo glob que usa `neb-bootstrap-context.py` en runtime — o `<overlay>/startup.md`), el script lo reporta y sugiere conectarlo en vez de crear uno adentro. Habilita el flujo de equipo: clonar el repo workspace + `/wakeup` → "Conectar este workspace".
- **`docs/user-guide.md` § "Conectarse al workspace del equipo"** — adopción de un miembro en 3 pasos: instalar el plugin, clonar el repo workspace del equipo, `/wakeup` para conectarlo (+ abrir sesión nueva).

### Changed

- **`--existing` completa el setup del miembro**: además de setear `NEB_WORKSPACE`, crea `personal/<usuario>.md` desde template si falta (antes solo lo hacía el modo create — un miembro que conectaba el workspace del equipo quedaba sin su capa personal).
- **`NEB_HOME` ya no se persiste cuando resuelve al cache del plugin** (path version-specific): por la precedencia D4 (`NEB_HOME` > `CLAUDE_PLUGIN_ROOT`) quedaba sombreando al plugin tras un update. Solo se persiste si el usuario ya lo tenía en env (maintainer con clon) o si el script corre desde un clon.
- **El shell profile ya no se edita**: `settings.json` basta para las sesiones de Claude Code; el script imprime los exports opcionales para shells sueltas. (Elimina el paso manual fantasma en Windows y la contaminación del profile.)
- **`skills/wakeup` + `commands/wakeup`**: cascada de detección explícita (ya conectado → workspace detectado → preguntar/crear) y resolución del script con fallback `NEB_HOME` → `CLAUDE_PLUGIN_ROOT` → cache del plugin — un miembro recién instalado (sin env previo) puede correr `/wakeup` de inmediato.
- **`CLAUDE.md` del repo con imports relativos** (`@stacks/...`, `@general/...`, `@workflow/...`) en lugar de `@~/.claude/neb/...` — el contexto del repo carga en cualquier ubicación del clon (verificado empíricamente).
- **`docs/user-guide.md` § "Contribuir al núcleo"** reescrito a clone-first: clon normal + `git push` directo (+ hook `pre-push` del CHANGELOG); el layout subtree queda como nota histórica.

### Fixed

- `setup-workspace.sh` devolvía exit code 1 en corridas exitosas sin `--dry-run` (un `[ cond ] && cmd` como última línea del script).

## [2.0.4] - 2026-06-10

### Fixed

- **Revertida la declaración `"hooks"` de `plugin.json`** (introducida en 2.0.3 sobre un diagnóstico equivocado). Los hooks de un plugin **se auto-descubren** desde `hooks/hooks.json`; el campo `hooks` del manifest es solo para archivos hook **adicionales**, así que apuntarlo al `hooks/hooks.json` estándar dispara `[ERROR] Duplicate hooks file detected` + `hook-load-failed` (los hooks registran igual porque Claude Code lo salta, pero ensucia el log y marca el plugin como no disponible para MCP). Los plugins oficiales de Anthropic (`explanatory-output-style`, `security-guidance`) traen `SessionStart` **sin** clave `hooks` en `plugin.json`. **Causa real del `0 hooks`/`0 skills` reportado antes**: el plugin estaba **deshabilitado** (`enabledPlugins: { "neb@neb": false }` en `settings.local.json`, que precede al `true` de `settings.json`). Habilitado, el log muestra `Registered 2 hooks from 1 plugins` + `Loaded 1 skills` + `Loaded 5 agents` + `Loaded 1 commands` y el arranque se inyecta. Verificado en Claude Code v2.1.170.

### Added

- **Comando `/wakeup`** (`commands/wakeup.md`) — slash-command que dispara el tour de bienvenida. Antes `wakeup` existía solo como skill (`skills/wakeup/SKILL.md`), por lo que escribir `/wakeup` literal daba "Unknown command"; el comando cierra esa brecha (el skill sigue activándose por intención en lenguaje natural).

## [2.0.3] - 2026-06-09

### Fixed

- **(SUPERSEDED — ver 2.0.4)** Se declaró `"hooks": "./hooks/hooks.json"` en `plugin.json` creyendo que los hooks de un plugin no se auto-descubrían. **El diagnóstico era incorrecto**: los hooks de plugin **sí** se auto-descubren desde `hooks/hooks.json`; el `0 hooks` observado se debía a que el plugin estaba **deshabilitado** en `settings.local.json` (`enabledPlugins: { "neb@neb": false }`, que precede a `settings.json`), no a falta de declaración. La declaración resultó **redundante y dañina** (dispara `Duplicate hooks file detected` + `hook-load-failed`) y se **revierte en 2.0.4**.

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
