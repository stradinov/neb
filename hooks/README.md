# Hooks

Hooks de Neb. El plugin registra en `hooks/hooks.json` el `SessionStart` y los hooks opcionales de esta página; los opcionales corren solo si se activan con `NEB_HOOKS` o `NEB_PROJECT_HOOKS` (ver § "Bajo el plugin de Neb").

## Hooks disponibles

### save-approved-plan

`PostToolUse` con matcher `ExitPlanMode`. Solo guarda planes **aprobados** (`PostToolUse` solo dispara al éxito; `ExitPlanMode` solo "tiene éxito" cuando el usuario aprueba). Cubre la vía **plan mode**; los planes aprobados conversacionalmente (media/alta) se persisten vía `Write` — ver [`workflow/approved-plans.md`](../workflow/approved-plans.md) § "Persistencia conversacional".

- **Output**: `~/.claude/approved-plans/<YYYYMMDD-HHMMSS>-<proyecto>-<slug>.md`.
- **Carpeta**: única global, fuera de cualquier repo, no versionada.
- **Bajo el plugin**: lo corre `hooks/lib/approved_plan.py` (Python, sin `jq`). El slug es ASCII completo (`ñ` → `n`, símbolos → `-`).
- **Entrada de settings con clon** (`save-approved-plan.sh`): requiere `bash`, `jq`, `iconv` y `NEB_HOME` apuntando al clon. En Git Bash, `iconv //TRANSLIT` trunca el slug en el primer carácter no ASCII.

### PreCompact legacy (retirados en 6.30.0)

La plantilla de settings del dev traía dos hooks `PreCompact`: un agente (`matcher: "auto"`) que copiaba el estado del REQ activo al draft del change MD antes de compactar, y una guardia (`matcher: "manual"`) que frenaba `/compact` si el draft tenía más de 15 minutos sin cambios. Desde 5.0.0 buscaban el formato legacy (`## Requerimiento activo` en `project_*.md`) y no los `active_*.md`, así que no encontraban el REQ de la sesión, y el agente se lanzaba en cada compactación automática. Se retiraron: el estado del REQ sobrevive a la compactación porque vive en su `active_*.md`, `logbook-sync` lo captura en `PreCompact`, el arranque se reinyecta y [`general/compaction.md`](../general/compaction.md) le dice al resumen qué conservar. El draft lo actualiza Claude en cada transición de fase ([`workflow/changes.md`](../workflow/changes.md) § "Ciclo de vida del draft").

Si tu `~/.claude/settings.json` todavía los tiene, quítalos; el `PreCompact` de `logbook-sync` se queda.

### Medidor de uso (`/neb-usage`) — antes hook `usage-tracker`

No es un hook: es el CLI `hooks/lib/usage-tracker.py report` y el comando [`/neb-usage`](../commands/neb-usage.md). Lee los transcripts de `~/.claude/projects` y reporta tokens y USD a precio de API, por REQ o por ventana de días. El bloque de uso del change MD se escribe al cerrar el REQ con `/neb-usage --write <change MD>` ([`workflow/metrics.md`](../workflow/metrics.md) § "Tokens, costo y breakdown por modelo").

- **Qué cuenta**: el hilo principal y los subagentes, incluidos los agentes de workflow, cada uno con su `agentType`. Cuenta una llamada por `message.id` y deduplica entre archivos (copias de `--resume` y forks); separa la escritura de caché de 5 min y de 1 h. El formato del transcript del que depende es el supuesto R21 de [`methodology/platform-assumptions.md`](../methodology/platform-assumptions.md).
- **Atribución**: una llamada del hilo principal va al último REQ cuyo change MD o `active_*.md` editó la sesión hasta ese momento (`Write`/`Edit`); un `active_*.md` cuenta para el change MD de su campo `Draft changes MD` (o `Change MD`; si no, la primera ruta `changes/AAAA-MM-DD-<slug>.md` que cite) o, si no cita ninguno, para el slug de su nombre de archivo. Las llamadas previas al primer toque van al primer REQ tocado; una sesión sin toques queda «sin REQ». Una llamada de subagente va al REQ vigente en el hilo principal a su misma hora. Las ediciones hechas por Bash o desde un subagente no atribuyen.
- **Señales**: % de llamadas del hilo principal con más de 300k de contexto (y la mediana), compactaciones por disparo y relecturas del transcript completo tras compactar.
- **Precios**: `hooks/pricing.yml`, tabla manual; actualizarla cuando Anthropic publique un modelo o cambie un precio. Un modelo sin precio deja el total marcado como parcial.
- **Escritura**: `--write` solo reemplaza lo que hay entre `<!-- usage-tracker-start -->` y `<!-- usage-tracker-end -->`; sin marcadores no escribe. No guarda estado propio.
- **Retiro del hook (6.29.0)**: el hook `Stop` `usage-tracker` leía `model` y `usage` fuera de `message`, donde el transcript no los trae (registraba ceros), no deduplicaba y atribuía al `active_*.md` de mtime mayor. El nombre ya no corre desde `NEB_HOOKS` / `NEB_PROJECT_HOOKS`, y el arranque avisa que se retiró si sigue ahí (`RETIRED` en `hooks/neb-hook.py`).

**Lógica completa**: `hooks/lib/usage-tracker.py`.

### logbook-sync

`Stop` + `SessionEnd` + `PreCompact` — publica/actualiza la entrada del REQ activo (o de la sesión exploratoria) en la **bitácora de relevo** (SQLite local). Si el proyecto activa el central (`NEB_LOGBOOK_ENDPOINT` y el marcador opt-in `<!-- neb-logbook: central -->` en su `CLAUDE.md`), tras la captura lanza un **sync detached** que drena el outbox + sube el transcript al backend central. Lineamiento en [`tooling/logbook.md`](../tooling/logbook.md); artefacto en [`workflow/logbook.md`](../workflow/logbook.md).

- **Tipo**: `command`. Bajo el plugin, `hooks/neb-hook.py` llama directo a `hooks/lib/logbook.py`. Para una entrada de settings con clon hay dos wrappers hermanos: `logbook-sync.sh` (Linux/Mac, requiere `jq`) y `logbook-sync.ps1` (Windows).
- **Requiere**: Python 3 (`py` / `python` / `python3`) con `sqlite3` (stdlib). Los wrappers requieren además `NEB_HOME`.
- **`SessionEnd` al salir**: Claude Code da 1.5 s a los hooks de `SessionEnd`, y el `timeout` de un hook de plugin no amplía ese presupuesto. La captura de `Stop` y `PreCompact` ya cubre el último turno.
- **Central (opcional)**: con `NEB_LOGBOOK_ENDPOINT` + `NEB_LOGBOOK_TOKEN` en el entorno y el marcador en el `CLAUDE.md` del cwd, la captura lanza `logbook.py sync` **detached** (`subprocess.Popen`, cross-OS) que publica al central solo lo que tiene opt-in (regla en [`../tooling/logbook.md`](../tooling/logbook.md) § "Backend central — contrato y disparador") — los wrappers `.sh`/`.ps1` no cambian. El cliente usa solo stdlib (`urllib`); **PyMySQL es solo del servidor** (distribuido en un repositorio dedicado).
- **Input**: JSON por stdin (`session_id`, `cwd`, `transcript_path`, `hook_event_name`).
- **Windows, entrada de settings con clon**: declarar `"shell": "powershell"` con `logbook-sync.ps1` (ver §Filosofía).
- **Defensivo**: ante cualquier falla (sin Python, DB inaccesible, sin REQ activo) `exit 0`; nunca bloquea.
- **Fallos del sync, visibles**: el wrapper descarta `stderr` y el sync corre detached, así que un rechazo del central no se ve en pantalla. Se persiste sin cortar el reintento: el de publicación en el `work` local (`last_error`) y el del transcript en la sesión (`session_sync.transcript_error`). Lo lista `logbook.py sync-status` (`/logbook estado-sync`). Detalle en [`tooling/logbook.md`](../tooling/logbook.md).
- **Subida del transcript por sesión** (desde 6.12): cada sesión tiene su propio cursor (`session_sync`) y sube **una sola vez**, atribuida a un work, aunque toque varios REQ. Ninguna captura le quita la cola a otra sesión.
  - **Un sync a la vez:** usa un candado `neb-logbook-sync.lock` junto a la DB; uno de más de 10 min se considera rancio.
  - **Tope y presupuesto:** cada envío pesa como máximo 6 MiB de cuerpo serializado, y cada sync manda como máximo 32 MiB, de menor a mayor pendiente. Una sesión que no cabe espera, visible en `estado-sync`.
  - **Adopción:** una sesión que quedó sin work recibe un exploratorio propio (`payload_json.adopted`).
  - **Búsqueda por nombre:** si la ruta guardada del `.jsonl` ya no existe, se busca por nombre en `~/.claude/projects/*/`.
- **Activación voluntaria**: `logbook-sync` en `NEB_HOOKS` (personal) o en `NEB_PROJECT_HOOKS` (proyecto); ver § "Bajo el plugin de Neb".
- **Subsesión interna del corrector**: si `NEB_INTERNAL_SUBSESSION=1` (alias legacy `CLAUDE_PREPROCESS_RECURSION`), `exit 0` — no escribe la subsesión Haiku a la bitácora. Ver `hooks/lib/subsession.py`.
- **Lógica completa**: `hooks/lib/logbook.py` (modo hook de captura + CLI del comando `/logbook`).

### notify-on-permission.{ps1,sh}

`Notification` — reproduce un WAV cuando Claude pide permiso para una herramienta o el prompt input lleva idle > 60s. **Activación voluntaria y personal** (`NEB_HOOKS`): lineamiento completo en [`tooling/notify-on-permission.md`](../tooling/notify-on-permission.md).

- **Tipo**: `command`. Dos scripts hermanos: `.ps1` (Windows) + `.sh` (Linux/Mac). Bajo el plugin, `hooks/neb-hook.py` elige el del sistema operativo.
- **Requiere**:
  - **Windows**: PowerShell 5+. El dispatcher lo llama con `-ExecutionPolicy Bypass`; una entrada de settings con clon requiere `NEB_HOME`.
  - **Linux/Mac**: `bash`, un player en PATH (`afplay`/`paplay`/`aplay`/`play`). `jq` es blando (sin él, defaults completos).
- **Input**: JSON por stdin (no se usa — sin walk-back).
- **Output**: ninguno (reproduce audio async en background process).
- **Defensivo**: ante cualquier falla (config malformado, WAV ausente, player ausente), `exit 0` silencioso.
- **Configurable** en `~/.claude/notify-on-permission.json`: `enabled`, `wav`. Por defecto: 1 chime fijo. Sin scaling ni `min_seconds` (el evento no tiene duración medible).
- **Guard de subsesión interna**: chequea `NEB_INTERNAL_SUBSESSION=1` (alias legacy `CLAUDE_PREPROCESS_RECURSION`), igual que `notify-on-stop`.
- **Coexiste con `Stop`** (`notify-on-stop`): eventos semánticamente distintos; pueden disparar chimes en secuencia. Ver `tooling/notify-on-permission.md` § 5.

### notify-on-stop.{ps1,sh}

`Stop` — reproduce un WAV cada vez que Claude termina un turno. **Activación voluntaria y personal** (`NEB_HOOKS`): lineamiento completo en [`tooling/notify-on-stop.md`](../tooling/notify-on-stop.md).

- **Tipo**: `command`. Dos scripts hermanos: `.ps1` (Windows) + `.sh` (Linux/Mac). Bajo el plugin, `hooks/neb-hook.py` elige el del sistema operativo.
- **Requiere**:
  - **Windows**: PowerShell 5+. El dispatcher lo llama con `-ExecutionPolicy Bypass`; una entrada de settings con clon requiere `NEB_HOME`.
  - **Linux/Mac**: `bash`, `jq` (requisito blando — sin jq, defaults + 1 chime de cortesía), un player en PATH (`afplay`/`paplay`/`aplay`/`play`).
- **Input**: JSON por stdin con `transcript_path`.
- **Output**: ninguno (reproduce audio async en background process).
- **Defensivo**: ante cualquier falla (config malformado, WAV ausente, transcript ilegible, player ausente), `exit 0` silencioso.
- **Configurable** en `~/.claude/notify-on-stop.json`: `enabled`, `wav`, `min_seconds`, `max_chimes`, `scaling` (`per-minute` o `fixed`). Por defecto: 1 chime + 1 por cada minuto del turno (max 5), skip si < 10s.
- **Guard de subsesión interna**: chequea `NEB_INTERNAL_SUBSESSION=1` (alias legacy `CLAUDE_PREPROCESS_RECURSION`) y abandona — evita el "chime fantasma" del subproceso `claude -p` invocado por [`preprocess-prompt.py`](#preprocess-promptpy). Cross-link en `tooling/notify-on-stop.md` § Guard de subsesión interna.

### preprocess-prompt.py

`UserPromptSubmit` — corrige ortografía/sintaxis del prompt del dev y prepara eco + confirmación antes de que Claude actúe. **Activación voluntaria y personal** (`NEB_HOOKS`): lineamiento completo en [`tooling/prompt-preprocessing.md`](../tooling/prompt-preprocessing.md).

- **Tipo**: `command` (script Python cross-OS Linux/Mac/Windows).
- **Requiere**: Python 3 en PATH (`py` / `python` / `python3`), `claude` CLI en PATH.
- **Input**: JSON por stdin con `prompt`, `session_id`, `cwd`, `permission_mode`.
- **Output**: JSON con `hookSpecificOutput.additionalContext` (preámbulo para Claude principal). Sin output si el hook decide skipear (slash command, trivial, payload puro, error). Bajo el plugin, el dispatcher lo corre con `PYTHONIOENCODING=utf-8` y un timeout de 35 s (el de su `claude -p` es de 30 s), y le pasa su stdout.
- **Defensivo**: ante cualquier falla (red, API, timeout, CLI ausente), `exit 0` silencioso y el prompt pasa raw — nunca bloquea la sesión.
- **Configurable** en sesión vía `/preprocess full|fast|off`, prefijo `$$` por prompt o env var `CLAUDE_PREPROCESS_MODE`.
- **Excepción a la filosofía "< 100ms"**: documentada explícitamente — la llamada inevitable a `claude -p` con Haiku justifica 13–25 s (medido localmente; el plan estimaba 2–4 s, la realidad fue mayor). Mitigaciones: timeout 30 s, filtros agresivos de skip, modo `off`, activación voluntaria y personal, guard de subsesión interna via env var `NEB_INTERNAL_SUBSESSION` (alias legacy `CLAUDE_PREPROCESS_RECURSION`) que establece en el subproceso — consumida por todos los hooks de sesión vía `hooks/lib/subsession.py`.

### ops-capture

`SessionEnd` — captura asistida de **conocimiento operativo** descubierto en la sesión. Lee el transcript, aplica un **gate barato** (extrae fragmentos con señales operativas — ssh, mysql, deploy, IPs, DDL…; si no hay, no hace nada y no cuesta nada), e invoca un subagente vía `claude -p` que extrae **deltas propuestos** a un **inbox efímero** (`~/.claude/ops-inbox/`, configurable con `NEB_OPS_INBOX_DIR`). **NO toca ninguna fuente de verdad** — la aplicación de los deltas es **gated** por un comando de revisión definido por el adoptante en su overlay. Implementa la pieza 2a de la metodología (memoria operativa desde sesiones).

- **Tipo**: `command` (Python cross-OS, `hooks/ops-capture.py`). Bajo el plugin, `hooks/neb-hook.py` lo lanza **desacoplado** y no lo espera: Claude Code da 1.5 s a los hooks de `SessionEnd` al salir, y su `claude -p` tarda más. En una entrada de settings con clon, Windows declara `"shell": "powershell"`. La lógica determinística (gate, naming, parse del transcript) vive en `hooks/lib/ops_inbox.py`, cubierta por `hooks/tests/test_ops_capture.py`.
- **Requiere**: Python 3 (`py`/`python3`) y el `claude` CLI en PATH (sin CLI → `exit 0` silencioso).
- **Input**: JSON por stdin (`session_id`, `cwd`, `transcript_path`, `hook_event_name`).
- **Mecanismo genérico, dominio en el overlay**: el prompt de detección por defecto es genérico; el overlay lo especializa con `NEB_OPS_CAPTURE_PROMPT_FILE` (prompt con vocabulario de dominio) y `NEB_OPS_SIGNALS_EXTRA` (regex extra del gate). Modelo configurable con `NEB_OPS_CAPTURE_MODEL` (por defecto, Haiku).
- **Defensivo**: ante cualquier falla (sin transcript, sin actividad operativa, sin CLI, timeout 120s) `exit 0` — nunca bloquea el cierre de sesión. El subagente tiene instrucción de **no volcar secretos** al inbox.
- **Seguridad (decisión de diseño)**: el hook re-envía fragmentos del transcript a la API (vía `claude -p`) y **NO redacta/filtra secretos de entrada**. El transcript de la sesión ya pasó por la API durante la propia sesión (Claude Code), así que el hook no agrega exposición nueva. El manejo de credenciales es responsabilidad **operativa del equipo adoptante**, no del hook — por diseño, el skill no filtra contenido por seguridad.
- **Activación voluntaria**: `ops-capture` en `NEB_HOOKS` o `NEB_PROJECT_HOOKS`, como `logbook-sync`.
- **Guard de subsesión interna**: si `NEB_INTERNAL_SUBSESSION=1` → no captura — evita capturar la subsesión Haiku del corrector y la propia recursión (invoca `claude -p`). Ver `hooks/lib/subsession.py`.
- **Lógica completa**: `hooks/ops-capture.py` + `hooks/lib/ops_inbox.py`.

### pre-push-changelog (git hook del repo, no Claude Code)

`.git/hooks/pre-push` — git hook nativo del **clon del maintainer** (`cp hooks/pre-push-changelog .git/hooks/pre-push`). Es el **único punto de enforcement bloqueante de neb** — ningún hook del plugin bloquea (todos son inyección/registro/UX).

Valida lo que se publica, no la copia. Por cada ref de la entrada estándar del hook (`<local ref> <local sha> <remote ref> <remote sha>`), extrae el árbol del commit que se empuja a un directorio temporal y corre ahí los gates, con los scripts de ese árbol. Lo que está sin commitear en la copia no cuenta, y un push desde un HEAD separado se valida igual. Los archivos que cambia cada ref salen del diff contra el `remote sha`; en una ref nueva, de los commits que ninguna ref remota tiene. Un borrado o una ref que no cambia archivos no corre gates. `git pull` no reinstala el hook: al actualizarlo, repetir el `cp`.

Encadena 6 gates:

1. Integridad de la cadena de imports del arranque (`assemble-startup.py --check`).
2. Términos vetados vía extension point del overlay (`$NEB_WORKSPACE/*/scripts/scan-forbidden-terms.sh`, si existe).
3. Fragmento obligatorio para cambios normativos.
4. Sincronía `CHANGELOG.md` ↔ `changelog.d/`. Su detalle está en [`process/version-control.md`](../process/version-control.md) § "Gate pre-push".
5. Sincronía `plugin.json.version` ↔ `VERSION`.
6. El arranque del núcleo cabe en las partes del `SessionStart` (`neb-bootstrap-context.py --check-size --root <árbol>`). Mide el árbol del commit publicado, no `NEB_HOME`, con una raíz de instalación larga. Falla si el núcleo ocupa más de 8 de las 12 partes, lo que deja lugar al overlay y a la configuración personal.

## Activación en un proyecto

Con el plugin de Neb no se copian bloques de hooks: el plugin ya los registra (§ "Bajo el plugin de Neb"). Para activarlos en un proyecto, el `<proyecto>/.claude/settings.json` declara la lista en su `env`; [`templates/claude-settings.json.template`](../templates/claude-settings.json.template) y `settings.template.json` traen ejemplos:

```json
{ "env": { "NEB_PROJECT_HOOKS": "save-approved-plan,logbook-sync" } }
```

> El script `link-into-project.sh` que generaba ese `settings.json` (modelo clone) fue eliminado en 3.0.0.

## Bajo el plugin de Neb

Cuando Neb se instala como **plugin** de Claude Code, su `hooks/hooks.json` registra:

- **El `SessionStart`** (`bootstrap/neb-bootstrap-context.py`): inyecta el arranque ensamblado, en partes.
  - La plataforma topa cada salida de hook en 10,000 caracteres, y lo que pasa de ahí no llega completo a Claude (supuesto R1 de [`methodology/platform-assumptions.md`](../methodology/platform-assumptions.md)).
  - Por eso hay 12 entradas por matcher (`startup`, `clear` y `compact`), que corren al iniciar, tras `/clear` y al compactar; `clear` está sin verificar en sesión interactiva (R1). Cada entrada corre el script con `--part k`.
  - El arranque usa tantas partes como necesite, hasta 12, cada una de 9,000 caracteres o menos y con la cabecera «parte k de n · huella». Las entradas que sobran no emiten nada.
  - Si el arranque no cabe en las 12 partes, la parte 12 termina con un aviso: qué bloques faltan y de qué archivo leerlos.
  - Costo: cada sesión carga el arranque completo (unos 25–30 k tokens, estimado), y las 12 entradas suman entre 0.6 y 1 s al iniciar.
  - No consume stdin.
- **Los hooks opcionales de este README**: `save-approved-plan`, `logbook-sync`, `notify-on-stop`, `notify-on-permission`, `ops-capture` y `preprocess-prompt`. Hay una entrada por hook, y cada entrada abre con un gate en el shell. Si el hook no está activado, la entrada termina ahí, sin arrancar Python (~50 ms por entrada en Windows). Si está activado, llama a `hooks/neb-hook.py <hook>`. Ese dispatcher lee el JSON del evento y corre el hook con el código del propio plugin: la versión instalada, sin `NEB_HOME`.

**Activación voluntaria**, con dos listas separadas por comas y sin espacios, que se suman:

| Variable | Dónde va | Para qué |
|---|---|---|
| `NEB_HOOKS` | `env` de `~/.claude/settings.json` (todos tus proyectos) o del `settings.local.json` de un proyecto (ahí reemplaza tu lista de usuario: repite los que quieras conservar) | Tus hooks personales: `notify-*`, `preprocess-prompt`, `logbook-sync`… |
| `NEB_PROJECT_HOOKS` | `env` del `.claude/settings.json` versionado del proyecto | Los que el proyecto activa para todo el equipo: `save-approved-plan`, `logbook-sync`… |

- **El valor de proyecto sustituye al de usuario.** En el `env` de Claude Code, una misma variable del proyecto reemplaza a la del usuario. Por eso hay dos variables y el gate evalúa su unión: un proyecto que activa `save-approved-plan` no apaga tus `notify-*`.
- **Para apagar en un proyecto**, redefine la variable en su `settings.local.json`: `"NEB_HOOKS": ""` apaga tus hooks personales ahí, y `"NEB_PROJECT_HOOKS": ""` te excluye de los que activa el proyecto. El marcador `<!-- neb: skip -->` apaga el arranque, no los hooks.
- **Un cambio en estas variables** aplica desde la siguiente sesión.
- **Avisos del arranque.** Avisa de un nombre desconocido o con espacios en las variables, de un arranque que no cupo en las 12 partes (en la parte 12) y de un `NEB_HOME` que apunte al caché del plugin. Esa variable la dejaba un `/wakeup` anterior a 6.14.3, y se ignora.

**Duplicados.** Claude Code no deduplica un hook de plugin contra una entrada de settings. Si activas un hook en estas variables, quita su entrada de tu `settings.json` (las que los templates anteriores a 6.15.0 copiaban desde `$NEB_HOME`), o correrá dos veces. Un maintainer con clon puede conservar sus entradas y no activar las variables; si un proyecto activa por `NEB_PROJECT_HOOKS` un hook que ya tiene como entrada, redefine `NEB_PROJECT_HOOKS` sin ese hook en el `settings.local.json` del proyecto.

**Requisito en Windows: Git Bash** (Git for Windows). Claude Code corre la forma shell de los hooks en Git Bash, y en `sh` en macOS y Linux. Así un solo comando sirve en ambos sistemas (`python … || python3 …`), con el stdin íntegro. Sin Git Bash, Claude Code cae a PowerShell, que no parsea el gate (`case … esac`): las entradas fallan en cada evento, estén activadas o no. En PowerShell 5.1 tampoco parsea el `||` del `SessionStart`; con `pwsh` 7 el `SessionStart` sí funcionaba sin Git Bash, y ahí estas entradas son una regresión (no verificada). Neb ya requiere Git Bash para los snippets bash de `/wakeup`, `/logbook` y `/pendings-review`.

## Agregar un hook nuevo

1. Escribir la lógica en Python bajo `hooks/` o `hooks/lib/` (defensiva, `exit 0`).
2. Agregar su ruta a `hooks/neb-hook.py`: el nombre y sus eventos en `HOOKS`, y la invocación en `dispatch()`.
3. Agregar su entrada a `hooks/hooks.json` con el mismo gate que las demás. `hooks/tests/test_hooks_json.py` verifica que el gate, el argumento y `HOOKS` coincidan.
4. Documentar en este README.
5. Bump minor.

## Filosofía

- Idempotentes: corren múltiples veces sin efectos secundarios.
- Rápidos: si tardan más de 100ms, mover a proceso async. **Excepción documentada**: `preprocess-prompt.py` opera entre 13–25 s porque invoca `claude -p` (Haiku) — la naturaleza de la corrección lo justifica. Es de activación voluntaria y personal: no afecta a devs que no lo activen.
- Defensivos: ante error, `exit 0` y registrar a stderr — un hook no bloquea al usuario.
- Sin secretos: nunca leer/escribir credenciales.
- **Cross-OS**: un solo comando en Git Bash o `sh` (§ "Bajo el plugin de Neb"); `python` corre en Windows y `python3` en Linux/Mac modernos. El problema de stdin de neb v2.23.2 venía de `cmd /c py "%VAR%\..."`, que no propaga el stdin al script. Para una entrada propia de PowerShell en settings sigue sirviendo `"shell": "powershell"` con `$env:VAR`, como la de `logbook-sync.ps1` (§ "logbook-sync").
