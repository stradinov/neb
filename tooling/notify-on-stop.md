# Notify on stop — hook `Stop`

> Lineamiento del hook `notify-on-stop.{ps1,sh}`. **Opcional personal**: no es baseline del equipo, cada dev decide si lo activa en su `~/.claude/settings.json`.
>
> Artefactos del hook: [`hooks/notify-on-stop.ps1`](../hooks/notify-on-stop.ps1), [`hooks/notify-on-stop.sh`](../hooks/notify-on-stop.sh), [`hooks/neb-hook.py`](../hooks/neb-hook.py) (dispatcher del plugin), [`hooks/lib/notify_sound.py`](../hooks/lib/notify_sound.py) (qué sonido suena), [`hooks/sounds/`](../hooks/sounds/README.md) (sonido por defecto y su licencia), [`hooks/hooks.json`](../hooks/hooks.json).

---

## 1. Problema

El dev hace multitarea: deja un prompt largo corriendo y se va a otra ventana (email, doc, browser). Cuando Claude termina el turno y espera input, el dev no se entera hasta que vuelve a la terminal — pierde minutos a turno. Un aviso sonoro al cierre de turno reduce ese ciclo a segundos.

Opcional personal porque no todos los devs lo quieren (entorno de oficina compartida, audífonos, preferencia de minimizar fricción auditiva).

## 2. Pipeline

`Stop` se dispara cuando Claude termina un turno y queda esperando al dev. El hook decide cuántos chimes reproducir según la duración del turno (más largo → más chimes, hasta un techo). La reproducción es async — no bloquea el siguiente prompt.

| Paso | Quién | Cómo |
|---|---|---|
| 1. Detectar fin de turno | Claude Code | Dispara `Stop` hook con `transcript_path` en stdin |
| 2. Guard de subsesión interna | Hook (script) | Si `NEB_INTERNAL_SUBSESSION=1` (o alias legacy), `exit 0` |
| 3. Cargar config personal y resolver el sonido | `hooks/lib/notify_sound.py` | Lee la sección `notify.stop` de `<datos>/config.json` (campos ausentes o de otro tipo caen a los valores por defecto), normaliza `min_seconds`, `max_chimes` y `scaling` y aplica el valor de `wav` (§ "Configuración personal default"). El dispatcher pasa los valores efectivos al script en `NEB_NOTIFY_ENABLED`, `NEB_NOTIFY_WAV`, `NEB_NOTIFY_MIN_SECONDS`, `NEB_NOTIFY_MAX_CHIMES` y `NEB_NOTIFY_SCALING`; invocado directo, el script se los pide a la CLI `notify_sound.py config notify-on-stop` (líneas `llave=valor`). El script no lee `config.json` por su cuenta |
| 4. Calcular duración del turno | Hook (script) | Walk-back del transcript al último user message no-`toolUseResult` |
| 5. Reproducir N chimes | Hook (script) | Player nativo en background process; el hook retorna inmediato |

## 3. Arquitectura

```
Claude termina turno → Stop hook
                      ├─ Guard de subsesión interna (NEB_INTERNAL_SUBSESSION=1 → exit 0)
                      ├─ Config efectiva y WAV (variables NEB_NOTIFY_* del dispatcher
                      │    || CLI `config` de hooks/lib/notify_sound.py || defaults y hooks/sounds/neb-chime.wav)
                      ├─ Si enabled=false → exit 0
                      ├─ Leer transcript_path del stdin JSON
                      ├─ Walk-back → último user msg no-toolUseResult → timestamp
                      ├─ duración = now - timestamp
                      ├─ Si duración < min_seconds → exit 0
                      └─ N = scaling(duración, max_chimes) → reproducir async
```

## 4. Modos (`scaling`)

| Modo | Cálculo de N | Caso de uso |
|---|---|---|
| `per-minute` (por defecto) | `clamp(1 + floor(secs/60), 1, max_chimes)` | Señal de "qué tan largo fue el turno"; útil para distinguir turnos cortos de largos sin mirar la terminal. |
| `fixed` | `1` constante | Aviso uniforme; útil si los chimes múltiples molestan. |

## 5. Configuración personal default

Sección `notify.stop` de `<datos>/config.json`, el archivo de configuración de Neb (`<datos>` es la carpeta de datos: `~/.neb`, o `NEB_DATA` si es una ruta absoluta; ver [`config.md`](config.md)). Solo hace falta lo que cambia; el resto del archivo es de otras secciones:

```json
{
  "schema": 1,
  "notify": {
    "stop": {
      "enabled": true,
      "wav": null,
      "min_seconds": 10,
      "max_chimes": 5,
      "scaling": "per-minute"
    }
  }
}
```

| Campo | Tipo | Por defecto | Notas |
|---|---|---|---|
| `enabled` | bool | `true` | `false` → `exit 0` inmediato sin reproducir. |
| `wav` | string \| null | `null` (= `hooks/sounds/neb-chime.wav`) | Preset o ruta absoluta; tabla de valores abajo. |
| `min_seconds` | int | `10` | Turnos más cortos → skip silencioso. Útil para que respuestas triviales no suenen. |
| `max_chimes` | int | `5` | Clamp `[1, 20]`. |
| `scaling` | `"per-minute"` \| `"fixed"` | `"per-minute"` | Cualquier otro valor cae a `"per-minute"`. |

Cualquier campo ausente o de otro tipo (p. ej. `"enabled": "false"`, que no apaga) cae al valor por defecto; un `min_seconds` con decimales se trunca. Un `config.json` ilegible aplica todos los valores por defecto. Si `config.json` todavía no existe (máquina que no ha corrido la migración de 8.0.0), se lee el `~/.claude/notify-on-stop.json` de antes; sin ninguno de los dos, todos los valores por defecto aplican.

Valores de `wav` (los resuelve [`hooks/lib/notify_sound.py`](../hooks/lib/notify_sound.py); valen igual para `notify-on-permission`):

| Valor | Suena | SO |
|---|---|---|
| `null`, ausente o `"neb"` | `hooks/sounds/neb-chime.wav`, que viene con el plugin (CC0; fuente y licencia en [`hooks/sounds/README.md`](../hooks/sounds/README.md)) | todos |
| `"chimes"` | El `chimes.wav` original de Windows (`%WINDIR%\Media\chimes.wav`) | Windows |
| `"chimes-loud"` | El mismo `chimes.wav`, amplificado. Se genera en local la primera vez en `<datos>/cache/sounds/chimes-loud.wav` y se regenera si el original cambia | Windows |
| Ruta absoluta: en Windows, con unidad (`C:/…`, `C:\…`) o UNC (`\\servidor\recurso\…`); fuera, empieza con `/` | Ese archivo WAV | todos |

Si el valor no se puede cumplir (preset de Windows en otro SO, ruta inexistente, ruta de Windows sin unidad como `/Windows/Media/x.wav`, valor no reconocido, `chimes.wav` ilegible), suena `neb-chime.wav`. Cuando el hook está activado en `NEB_HOOKS` o `NEB_PROJECT_HOOKS` y no suena como se configuró, o en Linux/Mac no hay reproductor, el arranque de la sesión lo avisa con el motivo; con `enabled: false` no avisa. Los presets de Windows no se distribuyen con Neb: ese audio no se puede redistribuir, así que se lee de la máquina del dev.

## 6. Activación

Manual. El plugin ya registra el hook (ver [`hooks/README.md`](../hooks/README.md) § "Bajo el plugin de Neb").

1. Agregar `notify-on-stop` a `NEB_HOOKS` en el bloque `env` de `~/.claude/settings.json`, por ejemplo `"NEB_HOOKS": "notify-on-stop"` (en una lista ya existente, va separado por comas y sin espacios). En Windows requiere Git Bash.

2. (Opcional) Cambiar valores de la sección `notify.stop` (§ "Configuración personal default") con el snippet de abajo; sin cambiar nada aplican los valores por defecto y suena el sonido que trae el plugin.

3. **Linux/Mac**: verificar `jq` y un player de audio:
   - macOS: `afplay` viene de serie. `jq` vía `brew install jq`.
   - Linux: `paplay` (PulseAudio) o `aplay` (ALSA) o `play` (sox). `jq` vía `apt install jq` / `dnf install jq`.

4. Reiniciar la sesión `claude` para que cargue el hook.

Snippet para cambiar un valor (Git Bash, Linux o Mac; `NEB_SRC` es la raíz del plugin o tu clon de `NEB_HOME`). Escribe solo esa llave en `config.json`, de forma atómica, sin tocar las demás; si el archivo no existe, lo crea con lo que dijeran los JSON sueltos de antes de 8.0.0. El valor va como JSON (un texto, con sus comillas; una ruta de Windows, con `/`):

```bash
py "$NEB_SRC/hooks/lib/neb_paths.py" set notify.stop.wav '"chimes"'          # o python / python3
py "$NEB_SRC/hooks/lib/neb_paths.py" set notify.stop.wav '"C:/sonidos/fin.wav"'
py "$NEB_SRC/hooks/lib/neb_paths.py" set notify.stop.max_chimes 3
py "$NEB_SRC/hooks/lib/neb_paths.py" set notify.stop.enabled false
py "$NEB_SRC/hooks/lib/notify_sound.py" config notify-on-stop               # verifica la config efectiva
```

En Windows PowerShell 5.1 las comillas internas se pierden al pasar el argumento: escríbelas como `'\"chimes\"'`. No crees ni sobrescribas `config.json` con `>` u `Out-File`: borrarías las demás secciones.

### Migración desde una entrada de settings

Si tu `~/.claude/settings.json` invoca este hook desde `$NEB_HOME` (templates anteriores a 6.15.0), quita esa entrada `Stop` y agrega `notify-on-stop` a `NEB_HOOKS` (§ "Activación"); si conservas las dos, suena dos veces.

## 7. Guard de subsesión interna

El hook [`preprocess-prompt.py`](../hooks/preprocess-prompt.py) invoca `claude -p --model claude-haiku-4-5` como subproceso para corregir el prompt del dev. Ese subproceso hereda `~/.claude/settings.json`, incluido el bloque `Stop`. Cuando termina su turno interno, dispara su **propio** `Stop` → el hook se ejecutaría con la sesión Haiku como contexto → chime suena en un "turno fantasma" que no corresponde al dev.

Mecanismo: `preprocess-prompt.py` marca el entorno del subproceso con `NEB_INTERNAL_SUBSESSION=1` (alias legacy `CLAUDE_PREPROCESS_RECURSION=1`). El primer paso del script `notify-on-stop` chequea ambas y abandona silenciosamente:

- PowerShell: `if ($env:NEB_INTERNAL_SUBSESSION -eq '1' -or $env:CLAUDE_PREPROCESS_RECURSION -eq '1') { exit 0 }`
- Bash: `if [ "${NEB_INTERNAL_SUBSESSION:-}" = "1" ] || [ "${CLAUDE_PREPROCESS_RECURSION:-}" = "1" ]; then exit 0; fi`

Sin este guard, cada prompt no trivial del dev produce 2 chimes: uno del subproceso Haiku (fantasma) y otro del turno real al final.

Es **un caso del contrato general** "hooks inertes en subsesión interna del corrector" — definido en [`prompt-preprocessing.md`](prompt-preprocessing.md) § "Limitaciones y alcances" y compartido vía [`hooks/lib/subsession.py`](../hooks/lib/subsession.py).

## 8. Heurística de skip

El hook **no reproduce** en los siguientes casos (`exit 0` silencioso):

- `enabled: false` en el config.
- `$env:NEB_INTERNAL_SUBSESSION = '1'` (o el alias legacy `CLAUDE_PREPROCESS_RECURSION`) — guard de subsesión interna.
- Duración del turno < `min_seconds` (por defecto 10).
- `transcript_path` ausente o ilegible — fallback a `play_n 1` (1 chime de cortesía, no skip total).
- Ningún WAV resoluble: ni el configurado ni `hooks/sounds/neb-chime.wav` (el arranque lo avisa).
- Linux/Mac sin ningún player en PATH (el arranque lo avisa).

## 9. Limitaciones y alcances

### Alcances

- Aviso sonoro al cierre de turno, con número de chimes proporcional a la duración.
- Cross-OS Windows + Linux/Mac vía dos scripts hermanos.
- Configuración personal por dev (sonido por preset o ruta, umbral, máximo, modo).
- Un sonido por defecto que viene con el plugin y suena en todo SO, sin conseguir archivos aparte.

### No alcances

- **No** reemplaza notificaciones nativas del SO (toast Windows, NotificationCenter macOS, notify-send Linux). Se podrían sumar después; quedan fuera del scope inicial.
- **No** distingue tipo de turno (tool-heavy vs conversacional). El número de chimes solo refleja duración total.
- **No** detecta si el dev ya está mirando la terminal. Suena igual.
- **No** se silencia automáticamente en horarios nocturnos. El dev decide cuándo desactivar.

### Restricciones técnicas

- **Latencia**: < 100 ms del hook al `exit 0`; el sonido corre async en background process. Cumple la filosofía de hooks.
- **Defensivo**: ante cualquier falla (config malformado, WAV ausente, transcript ilegible, player ausente), `exit 0`. Nunca bloquea la sesión.
- **Cross-OS**: bajo el plugin, el hook corre en Git Bash en Windows y el dispatcher elige el `.ps1`; en macOS y Linux, el `.sh`. Una entrada de settings con clon declara `"shell": "powershell"` con `$env:VAR` en Windows.
- **Linux/Mac**: `jq` es requisito blando — sin `jq`, el script no calcula la duración del turno y solo emite 1 chime de cortesía. La config y el sonido no dependen de `jq`: los resuelve Python (el del dispatcher o, invocado directo, `python3`/`python`); sin Python aplican los valores por defecto y suena `neb-chime.wav`.
- **Múltiples hooks `Stop`**: Claude Code los ejecuta en paralelo; convive con otros hooks `Stop` del repo (p. ej. `logbook-sync`).
- **Coexistencia con `Notification`** (`notify-on-permission`): eventos semánticamente distintos. Si el dev activa ambos, suenan chimes en secuencia (permission → approve → tool corre → cierre de turno). Ver [`tooling/notify-on-permission.md`](notify-on-permission.md) § "Coexistencia con `notify-on-stop`".
- **Sin secretos**: no lee ni escribe credenciales.

## 10. Cuándo desactivarlo

- Entorno de oficina compartida o reuniones por audio donde el chime distrae.
- Sesiones donde el dev ya está mirando la terminal continuamente (debug largo, plan review en vivo).
- Trabajo nocturno donde el chime no debe sonar.

Desactivación temporal: `notify.stop.enabled` en `false` (`neb_paths.py set notify.stop.enabled false`, § "Activación"); no requiere reiniciar, surte efecto al siguiente turno.

Desactivación permanente: quitar `notify-on-stop` de `NEB_HOOKS` y reiniciar `claude` (con una entrada de settings con clon, quitar esa entrada).

## 11. Verificación

Escenarios a probar tras activar:

| # | Acción | Resultado esperado |
|---|---|---|
| 1 | Turno < 10s (por defecto `min_seconds`) | Sin chime. |
| 2 | Turno ~30s | 1 chime. |
| 3 | Turno ~90s | 2 chimes (`1 + floor(90/60) = 2`). |
| 4 | Turno ~6 min | 5 chimes (clamp por `max_chimes`). |
| 5 | Config `scaling: "fixed"`, turno largo | 1 chime constante. |
| 6 | Config `enabled: false` | Sin chime aun en turno largo. |
| 7 | Config `wav` apuntando a archivo inexistente | Suena `neb-chime.wav`; el arranque de la siguiente sesión avisa del motivo. |
| 8 | `config.json` malformado | Todos los valores por defecto aplicados. |
| 9 | Sin `config.json` ni el JSON suelto anterior | Valores por defecto; chime suena igual que escenarios 2-4. |
| 10 | **Prompt no trivial con `preprocess-prompt.py` activo** (escenario clave) | Solo 1 chime al final del turno real. **Sin chime fantasma** del subproceso `claude -p` (guard de subsesión interna). |
| 11 | Transcript inaccesible (path inválido en payload) | 1 chime de cortesía + `exit 0`. |
| 12 | Linux/Mac sin player instalado | `exit 0` silencioso. |
| 13 | Windows con WAV en path con espacios | Suena correctamente. |
| 14 | Coexistencia con `logbook-sync` (otro hook `Stop`) | Ambos corren; ninguno bloquea al otro. |
| 15 | Desactivación permanente (quitar `notify-on-stop` de `NEB_HOOKS` + reiniciar) | Sin chime. |
| 16 | Config `wav: "chimes"` / `"chimes-loud"` en Windows | Suena el `chimes.wav` original / su versión amplificada (la primera vez se genera en `<datos>/cache/sounds/`). |
| 17 | Config `wav: "chimes"` en Linux/Mac | Suena `neb-chime.wav`; el arranque avisa que el preset solo existe en Windows. |

Escenarios 1–4, 6, 9, 10, 13–16 corren en máquina Windows. Escenarios 12 y 17 (Linux/Mac) quedan como verificación pendiente cuando otro dev del equipo lo active.

## 12. Referencias

- [`hooks/README.md`](../hooks/README.md) — catálogo de los hooks.
- [`tooling/notify-on-permission.md`](notify-on-permission.md) — hook hermano (`Notification`) para permission prompts e idle > 60 s. Comparte el guard de subsesión interna y arquitectura defensiva.
- [`tooling/prompt-preprocessing.md`](prompt-preprocessing.md) — hook recíproco que origina la necesidad del guard de subsesión interna.
- Documentación oficial de `Stop`: [Anthropic Claude Code hooks](https://docs.claude.com/en/docs/claude-code/hooks).
