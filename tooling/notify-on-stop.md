# Notify on stop — hook `Stop`

> Lineamiento del hook `notify-on-stop.{ps1,sh}`. **Opt-in personal**: no es baseline del equipo, cada dev decide si lo activa en su `~/.claude/settings.json`.
>
> Artefactos del hook: [`hooks/notify-on-stop.ps1`](../hooks/notify-on-stop.ps1), [`hooks/notify-on-stop.sh`](../hooks/notify-on-stop.sh), [`templates/claude-user-settings.json.template`](../templates/claude-user-settings.json.template).

---

## 1. Problema

El dev hace multitarea: deja un prompt largo corriendo y se va a otra ventana (email, doc, browser). Cuando Claude termina el turno y espera input, el dev no se entera hasta que vuelve a la terminal — pierde minutos a turno. Un aviso sonoro al cierre de turno reduce ese ciclo a segundos.

Opt-in personal porque no todos los devs lo quieren (entorno de oficina compartida, audífonos, preferencia de minimizar fricción auditiva).

## 2. Pipeline

`Stop` se dispara cuando Claude termina un turno y queda esperando al dev. El hook decide cuántos chimes reproducir según la duración del turno (más largo → más chimes, hasta un techo). La reproducción es async — no bloquea el siguiente prompt.

| Paso | Quién | Cómo |
|---|---|---|
| 1. Detectar fin de turno | Claude Code | Dispara `Stop` hook con `transcript_path` en stdin |
| 2. Recursion guard | Hook (script) | Si `CLAUDE_PREPROCESS_RECURSION=1`, `exit 0` |
| 3. Cargar config personal | Hook (script) | Lee `~/.claude/notify-on-stop.json`; campos ausentes caen a defaults |
| 4. Calcular duración del turno | Hook (script) | Walk-back del transcript al último user message no-`toolUseResult` |
| 5. Reproducir N chimes | Hook (script) | Player nativo en background process; el hook retorna inmediato |

## 3. Arquitectura

```
Claude termina turno → Stop hook
                      ├─ Recursion guard (CLAUDE_PREPROCESS_RECURSION=1 → exit 0)
                      ├─ Cargar ~/.claude/notify-on-stop.json (defaults si ausente)
                      ├─ Si enabled=false → exit 0
                      ├─ Resolver WAV (cfg.wav || $NEB_HOME/personal/chimes-loud.wav)
                      ├─ Leer transcript_path del stdin JSON
                      ├─ Walk-back → último user msg no-toolUseResult → timestamp
                      ├─ duración = now - timestamp
                      ├─ Si duración < min_seconds → exit 0
                      └─ N = scaling(duración, max_chimes) → reproducir async
```

## 4. Modos (`scaling`)

| Modo | Cálculo de N | Caso de uso |
|---|---|---|
| `per-minute` (default) | `clamp(1 + floor(secs/60), 1, max_chimes)` | Señal de "qué tan largo fue el turno"; útil para distinguir turnos cortos de largos sin mirar la terminal. |
| `fixed` | `1` constante | Aviso uniforme; útil si los chimes múltiples molestan. |

## 5. Configuración personal default

`~/.claude/notify-on-stop.json`:

```json
{
  "enabled": true,
  "wav": null,
  "min_seconds": 10,
  "max_chimes": 5,
  "scaling": "per-minute"
}
```

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `enabled` | bool | `true` | `false` → `exit 0` inmediato sin reproducir. |
| `wav` | string \| null | `null` (= `$NEB_HOME/personal/chimes-loud.wav`) | Path absoluto. Si no existe → fallback al default + warning a stderr. |
| `min_seconds` | int | `10` | Turnos más cortos → skip silencioso. Útil para que respuestas triviales no suenen. |
| `max_chimes` | int | `5` | Clamp `[1, 20]`. |
| `scaling` | `"per-minute"` \| `"fixed"` | `"per-minute"` | Cualquier otro valor cae a `"per-minute"`. |

Cualquier campo ausente cae al default hardcoded en el script. Si el archivo no existe, todos los defaults aplican. JSON malformado loguea a stderr y aplica defaults.

## 6. Activación

Manual. (El proceso guiado de instalación de `neb` queda como pendiente del repo.)

1. Copiar el bloque `Stop` de [`templates/claude-user-settings.json.template`](../templates/claude-user-settings.json.template) a `~/.claude/settings.json` del dev. Elegir el bloque OS apropiado (Windows / Linux-Mac).

2. Verificar que `NEB_HOME` esté seteado al checkout local del repo.

3. (Opcional) Crear `~/.claude/notify-on-stop.json` con valores explícitos. Si está ausente, los defaults aplican.

4. **Linux/Mac**: verificar `jq` y un player de audio:
   - macOS: `afplay` viene de serie. `jq` vía `brew install jq`.
   - Linux: `paplay` (PulseAudio) o `aplay` (ALSA) o `play` (sox). `jq` vía `apt install jq` / `dnf install jq`.

5. Reiniciar la sesión `claude` para que cargue el hook.

Snippet PowerShell para Windows (copy/paste):

```powershell
@'
{"enabled": true, "wav": null, "min_seconds": 10, "max_chimes": 5, "scaling": "per-minute"}
'@ | Out-File -Encoding utf8 "$env:USERPROFILE\.claude\notify-on-stop.json"
```

Snippet bash (Linux/Mac):

```bash
echo '{"enabled": true, "wav": null, "min_seconds": 10, "max_chimes": 5, "scaling": "per-minute"}' > ~/.claude/notify-on-stop.json
```

### Migración desde script local (el dev)

El dev tenía una versión personal de este hook en `~/.claude/hooks/notify-on-stop.ps1` antes de que entrara al repo. Post-merge:

1. Borrar `~/.claude/hooks/notify-on-stop.ps1` (queda obsoleto; ahora vive en `methodology/hooks/`).
2. Editar `~/.claude/settings.json` → reemplazar la entrada `Stop` actual por el bloque Windows del template (apunta a `$env:NEB_HOME\hooks\notify-on-stop.ps1`).
3. Opcional: crear `~/.claude/notify-on-stop.json` con valores explícitos; si está ausente, los defaults producen exactamente el comportamiento previo (1 chime + 1/minuto, max 5, skip < 10s).
4. Reiniciar sesión `claude`.

## 7. Recursion guard

El hook [`preprocess-prompt.py`](../hooks/preprocess-prompt.py) invoca `claude -p --model claude-haiku-4-5` como subproceso para corregir el prompt del dev. Ese subproceso hereda `~/.claude/settings.json`, incluido el bloque `Stop`. Cuando termina su turno interno, dispara su **propio** `Stop` → el hook se ejecutaría con la sesión Haiku como contexto → chime suena en un "turno fantasma" que no corresponde al dev.

Mecanismo: `preprocess-prompt.py` setea la env var `CLAUDE_PREPROCESS_RECURSION=1` en el ambiente del subproceso. El primer paso del script `notify-on-stop` chequea esa bandera y abandona silenciosamente:

- PowerShell: `if ($env:CLAUDE_PREPROCESS_RECURSION -eq '1') { exit 0 }`
- Bash: `[ "$CLAUDE_PREPROCESS_RECURSION" = "1" ] && exit 0`

Sin este guard, cada prompt no trivial del dev produce 2 chimes: uno del subproceso Haiku (fantasma) y otro del turno real al final.

Cross-link inverso: [`tooling/prompt-preprocessing.md`](prompt-preprocessing.md) §9 "Restricciones técnicas" → bullet recursion guard.

## 8. Heurística de skip

El hook **no reproduce** en los siguientes casos (`exit 0` silencioso):

- `enabled: false` en el config.
- `$env:CLAUDE_PREPROCESS_RECURSION = '1'` (recursion guard).
- Duración del turno < `min_seconds` (default 10).
- `transcript_path` ausente o ilegible — fallback a `play_n 1` (1 chime de cortesía, no skip total).
- WAV inexistente y default inexistente.
- Linux/Mac sin ningún player en PATH.

## 9. Limitaciones y alcances

### Alcances

- Aviso sonoro al cierre de turno, con número de chimes proporcional a la duración.
- Cross-OS Windows + Linux/Mac vía dos scripts hermanos.
- Configuración personal por dev (path al WAV, umbral, máximo, modo).

### No alcances

- **No** reemplaza notificaciones nativas del SO (toast Windows, NotificationCenter macOS, notify-send Linux). Se podrían sumar después; quedan fuera del scope inicial.
- **No** distingue tipo de turno (tool-heavy vs conversacional). El número de chimes solo refleja duración total.
- **No** detecta si el dev ya está mirando la terminal. Suena igual.
- **No** se silencia automáticamente en horarios nocturnos. El dev decide cuándo desactivar.

### Restricciones técnicas

- **Latencia**: < 100 ms del hook al `exit 0`; el sonido corre async en background process. Cumple la filosofía de hooks.
- **Defensivo**: ante cualquier falla (config malformado, WAV ausente, transcript ilegible, player ausente), `exit 0`. Nunca bloquea la sesión.
- **Cross-OS Windows**: `"shell": "powershell"` + `$env:VAR` (mismo bug de stdin documentado en `preprocess-prompt.py`).
- **Linux/Mac**: `jq` es requisito blando — sin `jq`, el script cae a defaults completos y solo puede emitir 1 chime de cortesía (no calcula duración).
- **Múltiples hooks `Stop`**: Claude Code los ejecuta secuencialmente; convive con otros hooks `Stop` del repo (e.g. `usage-tracker.sh`).
- **Coexistencia con `Notification`** (`notify-on-permission`): eventos semánticamente distintos. Si el dev activa ambos, suenan chimes en secuencia (permission → approve → tool corre → cierre de turno). Ver [`tooling/notify-on-permission.md`](notify-on-permission.md) § 5.
- **Sin secretos**: no lee ni escribe credenciales.

## 10. Cuándo desactivarlo

- Entorno de oficina compartida o reuniones por audio donde el chime distrae.
- Sesiones donde el dev ya está mirando la terminal continuamente (debug largo, plan review en vivo).
- Trabajo nocturno donde el chime no debe sonar.

Desactivación temporal: `"enabled": false` en `~/.claude/notify-on-stop.json` (no requiere reiniciar; surte efecto al siguiente turno).

Desactivación permanente: comentar/quitar el bloque `Stop` en `~/.claude/settings.json` y reiniciar `claude`.

## 11. Verificación

Escenarios a probar tras activar:

| # | Acción | Resultado esperado |
|---|---|---|
| 1 | Turno < 10s (default `min_seconds`) | Sin chime. |
| 2 | Turno ~30s | 1 chime. |
| 3 | Turno ~90s | 2 chimes (`1 + floor(90/60) = 2`). |
| 4 | Turno ~6 min | 5 chimes (clamp por `max_chimes`). |
| 5 | Config `scaling: "fixed"`, turno largo | 1 chime constante. |
| 6 | Config `enabled: false` | Sin chime aun en turno largo. |
| 7 | Config `wav` apuntando a archivo inexistente | Fallback al default + warning stderr; chime suena. |
| 8 | Config JSON malformado | Todos defaults aplicados; warning stderr. |
| 9 | Sin config (archivo ausente) | Defaults; chime suena igual que escenarios 2-4. |
| 10 | **Prompt no trivial con `preprocess-prompt.py` activo** (escenario clave) | Solo 1 chime al final del turno real. **Sin chime fantasma** del subproceso `claude -p` (recursion guard). |
| 11 | Transcript inaccesible (path inválido en payload) | 1 chime de cortesía + `exit 0`. |
| 12 | Linux/Mac sin player instalado | `exit 0` silencioso. |
| 13 | Windows con WAV en path con espacios | Suena correctamente. |
| 14 | Coexistencia con `usage-tracker.sh` (otro hook `Stop`) | Ambos corren; ninguno bloquea al otro. |
| 15 | Desactivación permanente (quitar bloque `Stop` de `settings.json` + reiniciar) | Sin chime. |

Escenarios 1–4, 6, 9, 10, 13–15 corren en máquina Windows. Escenarios 12 (Linux/Mac sin player) quedan como verificación pendiente cuando otro dev del equipo lo active.

## 12. Referencias

- [`hooks/README.md`](../hooks/README.md) — catálogo de los hooks.
- [`tooling/notify-on-permission.md`](notify-on-permission.md) — hook hermano (`Notification`) para permission prompts e idle > 60 s. Comparte recursion guard y arquitectura defensiva.
- [`tooling/prompt-preprocessing.md`](prompt-preprocessing.md) — hook recíproco que origina la necesidad del recursion guard.
- Documentación oficial de `Stop`: [Anthropic Claude Code hooks](https://docs.claude.com/en/docs/claude-code/hooks).
