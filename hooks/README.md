# Hooks

Hooks compartidos del equipo, enganchados via `.claude/settings.json` de cada proyecto.

## Hooks disponibles

### save-approved-plan.sh

`PostToolUse` con matcher `ExitPlanMode`. Solo guarda planes **aprobados** (`PostToolUse` solo dispara al éxito; `ExitPlanMode` solo "tiene éxito" cuando el usuario aprueba). Cubre la vía **plan mode**; los planes aprobados conversacionalmente (media/alta) se persisten vía `Write` — ver [`workflow/approved-plans.md`](../workflow/approved-plans.md) § "Persistencia conversacional".

- **Output**: `~/.claude/approved-plans/<YYYYMMDD-HHMMSS>-<proyecto>-<slug>.md`.
- **Carpeta**: única global, fuera de cualquier repo, no versionada.
- **Requiere**: `bash`, `jq`, `iconv`.
- **Variable**: `NEB_HOME` apuntando al checkout local del repo.

### PreCompact: preservar estado antes de compactar

Dos hooks en `~/.claude/settings.json` (config **personal del dev**) que preservan el estado de un requerimiento activo antes de que `autoCompactEnabled: true` borre el plan aprobado y el avance.

**Fuente de verdad**: sección `## Requerimiento activo` del `project_<nombre>.md`. Si no existe, los hooks no hacen nada.

Se configuran una vez en `~/.claude/settings.json` del dev — no requieren activación por proyecto. Variantes en [`templates/claude-user-settings.json.template`](../templates/claude-user-settings.json.template).

> **Failsafe del flag**: si `autoCompactEnabled` es `false` o ausente, el hook `auto` no dispara y el draft envejece silenciosamente. La verificación al inicio de sesión vive en [`general/communication.md`](../general/communication.md) "Hilo de la metodología" — Claude advierte al saludar si hay requerimiento activo. No hay SessionStart hook ejecutable (Claude lo verifica al leer settings.json).

#### `matcher: "auto"` — agente silencioso

Tipo `agent`. Antes de cada auto-compactación:
1. Localiza `~/.claude/projects/<project-id>/memory/`.
2. Busca `project_*.md` con sección `## Requerimiento activo`.
3. Extrae: Path del proyecto, Draft changes MD, Estado, Plan resumido, Archivos modificados, Próximos pasos.
4. Actualiza (o crea) `<Path del proyecto>/<Draft changes MD>` con esa información.

Independiente del OS (es un agente Claude, no un comando shell).

#### `matcher: "manual"` — guardia para `/compact` explícito

Tipo `command`. Bloquea `/compact` si hay `## Requerimiento activo` y el draft no fue modificado en los últimos 15 minutos. Si el draft es reciente o no hay requerimiento activo, permite.

UX: el dev ve el bloqueo, actualiza el draft (cualquier cambio renueva el timestamp), re-ejecuta `/compact`.

Depende del OS:
- **Windows**: PowerShell (`shell: "powershell"`).
- **Linux/Mac**: bash con `grep`, `stat`.

Implementaciones en [`templates/claude-user-settings.json.template`](../templates/claude-user-settings.json.template).

### usage-tracker.sh

`Stop` — dispara al cierre de cada turno de Claude. Acumula tokens y costo del turno en la sección **"Reporte de cierre"** del draft del change MD del REQ activo.

- **Requiere**: `bash`, `jq`, Python (`py` / `python` / `python3`).
- **Pricing**: `hooks/pricing.yml` — tabla manual. Actualizar cuando Anthropic publique nuevo modelo o cambie precios.
- **Estado incremental**: `~/.claude/projects/<encoded-cwd>/<session-id>.usage-offset` y `.usage-state.json`. El hook procesa solo las líneas nuevas del JSONL desde la última invocación.
- **Idempotente**: ejecutar dos veces sobre el mismo turno no duplica conteos — el offset file lo previene.
- **REQ activo**: se localiza buscando `## Requerimiento activo` en `project_*.md` del directorio de memoria del proyecto. Extrae `Path del proyecto` y `Draft changes MD` (mismo formato que PreCompact).
- **Marcadores en el draft**: el hook reemplaza el bloque entre `<!-- usage-tracker-start -->` y `<!-- usage-tracker-end -->`. Si los marcadores no están presentes, el hook no modifica el draft.
- **Edge cases**:
  - Sin REQ activo → `exit 0` silencioso.
  - Draft no existe → `exit 0`.
  - Modelo sin entrada en `pricing.yml` → tokens se acumulan, costo se marca `—`; warning a stderr.
  - Python no encontrado → warning a stderr, `exit 0`.
  - Cualquier error → `exit 0` (no bloquea al dev).

**Lógica completa**: `hooks/lib/usage-tracker.py`.

### notify-on-permission.{ps1,sh}

`Notification` — reproduce un WAV cuando Claude pide permiso para una herramienta o el prompt input lleva idle > 60s. **Opt-in personal**: lineamiento completo en [`tooling/notify-on-permission.md`](../tooling/notify-on-permission.md).

- **Tipo**: `command`. Dos scripts hermanos: `.ps1` (Windows) + `.sh` (Linux/Mac).
- **Requiere**:
  - **Windows**: PowerShell 5+, `NEB_HOME` seteado.
  - **Linux/Mac**: `bash`, un player en PATH (`afplay`/`paplay`/`aplay`/`play`). `jq` es blando (sin él, defaults completos).
- **Input**: JSON por stdin (no se usa — sin walk-back).
- **Output**: ninguno (reproduce audio async en background process).
- **Defensivo**: ante cualquier falla (config malformado, WAV ausente, player ausente), `exit 0` silencioso.
- **Configurable** en `~/.claude/notify-on-permission.json`: `enabled`, `wav`. Defaults: 1 chime fijo. Sin scaling ni `min_seconds` (el evento no tiene duración medible).
- **Recursion guard**: chequea `CLAUDE_PREPROCESS_RECURSION=1` (igual que `notify-on-stop`).
- **Coexiste con `Stop`** (`notify-on-stop`): eventos semánticamente distintos; pueden disparar chimes en secuencia. Ver `tooling/notify-on-permission.md` § 5.

### notify-on-stop.{ps1,sh}

`Stop` — reproduce un WAV cada vez que Claude termina un turno. **Opt-in personal**: lineamiento completo en [`tooling/notify-on-stop.md`](../tooling/notify-on-stop.md).

- **Tipo**: `command`. Dos scripts hermanos: `.ps1` (Windows) + `.sh` (Linux/Mac).
- **Requiere**:
  - **Windows**: PowerShell 5+, `NEB_HOME` seteado.
  - **Linux/Mac**: `bash`, `jq` (requisito blando — sin jq, defaults + 1 chime de cortesía), un player en PATH (`afplay`/`paplay`/`aplay`/`play`).
- **Input**: JSON por stdin con `transcript_path`.
- **Output**: ninguno (reproduce audio async en background process).
- **Defensivo**: ante cualquier falla (config malformado, WAV ausente, transcript ilegible, player ausente), `exit 0` silencioso.
- **Configurable** en `~/.claude/notify-on-stop.json`: `enabled`, `wav`, `min_seconds`, `max_chimes`, `scaling` (`per-minute` o `fixed`). Defaults: 1 chime + 1 por cada minuto del turno (max 5), skip si < 10s.
- **Recursion guard**: chequea `CLAUDE_PREPROCESS_RECURSION=1` y abandona — evita el "chime fantasma" del subproceso `claude -p` invocado por [`preprocess-prompt.py`](#preprocess-promptpy). Cross-link en `tooling/notify-on-stop.md` § Recursion guard.

### preprocess-prompt.py

`UserPromptSubmit` — corrige ortografía/sintaxis del prompt del dev y prepara eco + confirmación antes de que Claude actúe. **Opt-in personal**: lineamiento completo en [`tooling/prompt-preprocessing.md`](../tooling/prompt-preprocessing.md).

- **Tipo**: `command` (script Python cross-OS Linux/Mac/Windows).
- **Requiere**: Python 3 en PATH (`py` / `python` / `python3`), `claude` CLI en PATH.
- **Input**: JSON por stdin con `prompt`, `session_id`, `cwd`, `permission_mode`.
- **Output**: JSON con `hookSpecificOutput.additionalContext` (preámbulo para Claude principal). Sin output si el hook decide skipear (slash command, trivial, payload puro, error).
- **Defensivo**: ante cualquier falla (red, API, timeout, CLI ausente), `exit 0` silencioso y el prompt pasa raw — nunca bloquea la sesión.
- **Configurable** en sesión vía `/preprocess full|fast|off`, prefijo `$$` por prompt o env var `CLAUDE_PREPROCESS_MODE`.
- **Excepción a la filosofía "< 100ms"**: documentada explícitamente — la llamada inevitable a `claude -p` con Haiku justifica 13–25 s (medido localmente; el plan estimaba 2–4 s, la realidad fue mayor). Mitigaciones: timeout 30 s, filtros agresivos de skip, modo `off`, opt-in personal, recursion guard via env var `CLAUDE_PREPROCESS_RECURSION`.

### pre-push-changelog (git hook del repo, no Claude Code)

`.git/hooks/pre-push` — git hook nativo del repo `methodology`, lo instala el **maintainer** del núcleo (el viejo `bootstrap/install.sh` quedó deprecado). A diferencia de los anteriores, **no** se engancha vía `settings.json`. Corre `py bootstrap/assemble-changelog.py --check` antes de cada push que toca `changelog.d/`; si el `CHANGELOG.md` está desincronizado respecto a los fragments, aborta el push con mensaje claro. Lineamiento completo en [`process/version-control.md`](../process/version-control.md) § "Gate pre-push".

## Activación en un proyecto

Bajo el plugin de Neb, el `SessionStart` se auto-registra (ver §"Bajo el plugin de Neb" abajo). Los demás hooks son **opt-in por proyecto**: agregalos al `<proyecto>/.claude/settings.json` tomando [`templates/claude-settings.json.template`](../templates/claude-settings.json.template) (o `settings.template.json`) como base.

> El comando `bash $NEB_HOME/bootstrap/link-into-project.sh <ruta>` que generaba ese `settings.json` automáticamente corresponde al modelo clone **deprecado**.

## Bajo el plugin de Neb

Cuando Neb se instala como **plugin** de Claude Code, su `hooks/hooks.json` auto-registra **solo el `SessionStart`** (`bootstrap/neb-bootstrap-context.py` — inyecta el arranque ensamblado; no consume stdin; cross-OS: `python` con fallback a `python3` — `python` corre en Windows, `python3` en Linux/Mac modernos). Los demás hooks de este README (`save-approved-plan`, `usage-tracker`, `notify-*`, `preprocess-prompt`) **NO** se auto-registran por el plugin: son **opt-in por proyecto** vía `settings.json` (`link-into-project.sh` / `settings.template.json`) o config manual del dev. Razones (plan-review REQ-2): (a) varios **no están off por defecto** (`preprocess` corre en `full`, `notify` suena) y auto-registrarlos sería intrusivo para todo adoptante; (b) los que **consumen stdin** (`preprocess`, `usage-tracker`, `save-approved-plan`) requieren `"shell": "powershell"` en Windows (ver §Filosofía) — no aptos para auto-registro cross-OS sin esa variante.

## Agregar un hook nuevo

1. Crear `hooks/<nombre>.sh` con shebang `#!/usr/bin/env bash` y `set -euo pipefail`.
2. Agregarlo a `settings.template.json` con su matcher.
3. Documentar en este README.
4. Bump minor.

## Filosofía

- Idempotentes: corren múltiples veces sin efectos secundarios.
- Rápidos: si tardan más de 100ms, mover a proceso async. **Excepción documentada**: `preprocess-prompt.py` opera entre 13–25 s porque invoca `claude -p` (Haiku) — la naturaleza de la corrección lo justifica. Es opt-in personal, no afecta a devs que no lo activen.
- Defensivos: ante error, `exit 0` y registrar a stderr — un hook no bloquea al usuario.
- Sin secretos: nunca leer/escribir credenciales.
- **Cross-OS — Windows usa `"shell": "powershell"` con `$env:VAR`**: Claude Code invoca `command` sin shell intermediario. En Windows, `cmd /c py "%VAR%\..."` aparenta funcionar (exit 0, expansión de `%VAR%` correcta) pero **no propaga el stdin al subprocess** — el JSON del hook event llega a `cmd` como segundo comando, no al script Python. Declarar `"shell": "powershell"` y referenciar variables con `$env:VAR` resuelve ambos problemas: Claude Code envuelve el comando vía `powershell -NoProfile -Command "..."`, expande la variable y propaga stdin correctamente. En Linux/Mac, `$VAR` con `python3` o bash funciona nativo sin `shell`. Aplica a todo hook Windows que combine variables de entorno + stdin (e.g. `UserPromptSubmit`, `PostToolUse`, `Stop`). Ver template Windows en [`templates/claude-user-settings.json.template`](../templates/claude-user-settings.json.template) y precedente operativo en el hook `PreCompact` `manual` del mismo template.
