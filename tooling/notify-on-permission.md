# Notify on permission — hook `Notification`

> Lineamiento del hook `notify-on-permission.{ps1,sh}`. **Opt-in personal**: no es baseline del equipo, cada dev decide si lo activa en su `~/.claude/settings.json`.
>
> Artefactos del hook: [`hooks/notify-on-permission.ps1`](../hooks/notify-on-permission.ps1), [`hooks/notify-on-permission.sh`](../hooks/notify-on-permission.sh), [`templates/claude-user-settings.json.template`](../templates/claude-user-settings.json.template).
>
> Hermano de [`tooling/notify-on-stop.md`](notify-on-stop.md). Detalles compartidos (recursion guard, filosofía hooks, cross-OS Windows, restricciones técnicas) viven allí — este documento referencia sin duplicar.

---

## 1. Problema

El hook `Stop` (`notify-on-stop`) cubre el cierre de turno, pero hay otro evento donde el dev también pierde minutos si no está mirando la terminal: cuando Claude **pide permiso** para usar una herramienta (Bash con comando no allowlisted, Edit en path restringido, MCP no autorizado, etc.) o el prompt input lleva **idle > 60 s**. Sin señal sonora, el dev no se entera hasta que vuelve a la ventana.

Hook nativo de Claude Code: `Notification` dispara precisamente en esos dos eventos. Reusa la misma arquitectura defensiva de `notify-on-stop`.

Opt-in personal por las mismas razones que `notify-on-stop` (oficina compartida, audífonos, fricción auditiva personal).

## 2. Pipeline

```
Claude pide permiso o idle > 60s → Notification hook
                                  ├─ Recursion guard (CLAUDE_PREPROCESS_RECURSION=1 → exit 0)
                                  ├─ Cargar ~/.claude/notify-on-permission.json (defaults si ausente)
                                  ├─ Si enabled=false → exit 0
                                  ├─ Resolver WAV (cfg.wav || $NEB_HOME/personal/chimes-loud.wav)
                                  └─ Reproducir 1 chime async (sin scaling, sin walk-back)
```

Sin walk-back de transcript: el evento `Notification` no corresponde a "cierre de turno con duración medible", por lo que no aplica la heurística de scaling de [`notify-on-stop.md § 4`](notify-on-stop.md). Siempre 1 chime fijo.

## 3. Configuración personal default

`~/.claude/notify-on-permission.json`:

```json
{
  "enabled": true,
  "wav": null
}
```

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `enabled` | bool | `true` | `false` → `exit 0` inmediato sin reproducir. |
| `wav` | string \| null | `null` (= `$NEB_HOME/personal/chimes-loud.wav`) | Path absoluto. Si no existe → fallback al default + warning a stderr. |

Sin campos `min_seconds`, `max_chimes` ni `scaling`: el evento no tiene duración medible ni escala. Si en el futuro aparece necesidad de N chimes, se agrega.

Cualquier campo ausente cae al default hardcoded en el script. Si el archivo no existe, todos los defaults aplican. JSON malformado loguea a stderr y aplica defaults.

## 4. Activación

Manual, mismo procedimiento que [`notify-on-stop.md § 6`](notify-on-stop.md).

1. Copiar el bloque `Notification` de [`templates/claude-user-settings.json.template`](../templates/claude-user-settings.json.template) a `~/.claude/settings.json`. Elegir el bloque OS apropiado (Windows / Linux-Mac).

2. Verificar que `NEB_HOME` esté seteado al checkout local del repo.

3. (Opcional) Crear `~/.claude/notify-on-permission.json` con valores explícitos. Si está ausente, los defaults aplican.

4. Reiniciar la sesión `claude` para que cargue el hook.

Snippet PowerShell para Windows (copy/paste):

```powershell
@'
{"enabled": true, "wav": null}
'@ | Out-File -Encoding utf8 "$env:USERPROFILE\.claude\notify-on-permission.json"
```

Snippet bash (Linux/Mac):

```bash
echo '{"enabled": true, "wav": null}' > ~/.claude/notify-on-permission.json
```

## 5. Coexistencia con `notify-on-stop`

Ambos hooks pueden estar activos simultáneamente. Caso típico: dev pide permiso → aprueba → tool corre → turno termina.

| Evento | Hook que dispara | Chime |
|---|---|---|
| Claude pide permiso | `Notification` | 1 |
| Claude queda idle > 60 s | `Notification` | 1 |
| Cierre de turno | `Stop` (`notify-on-stop`) | 1 + 1/minuto, max 5 |

**Comportamiento aceptado**: si el flujo arriba ocurre en pocos segundos, suenan dos eventos sonoros consecutivos. No se evita — son señales semánticamente distintas. Si molesta, el dev desactiva uno en su config personal (`enabled: false` en el archivo correspondiente).

## 6. Verificación

Escenarios a probar tras activar:

| # | Acción | Resultado esperado |
|---|--------|--------------------|
| 1 | Acción que dispare permission prompt (e.g. `Bash` con comando no allowlisted) | 1 chime al pedir permiso. |
| 2 | Aprobar el permiso → tool corre → turno termina | Después del chime de Notification, suena el chime de Stop (separados). |
| 3 | Idle > 60 s sin permission prompt previo | 1 chime al cumplirse el idle. |
| 4 | Config `enabled: false` | Sin chime. |
| 5 | Config `wav` apuntando a archivo inexistente | Fallback al default + warning stderr; chime suena. |
| 6 | Config JSON malformado | Defaults aplicados; warning stderr. |
| 7 | Sin config (archivo ausente) | Defaults; chime suena. |
| 8 | **Prompt no trivial con `preprocess-prompt.py` activo** (escenario clave) | Sin chime fantasma del subproceso `claude -p` (recursion guard via `CLAUDE_PREPROCESS_RECURSION`). |
| 9 | Windows con WAV en path con espacios | Suena correctamente. |
| 10 | Coexistencia con otros hooks `Notification` futuros | Todos ejecutan secuencialmente; ninguno bloquea al otro (filosofía de `hooks/README.md`). |
| 11 | Linux/Mac sin player instalado | `exit 0` silencioso. |
| 12 | Desactivación permanente (quitar bloque `Notification` de `settings.json` + reiniciar) | Sin chime aun en evento. |

Escenarios 1–7, 9–10, 12 corren en máquina Windows. Escenario 11 (Linux/Mac sin player) queda como verificación pendiente cuando otro dev del equipo lo active.

## Referencias

- [`tooling/notify-on-stop.md`](notify-on-stop.md) — hook hermano (`Stop`). Detalles compartidos: recursion guard (§ 7), heurística de skip (§ 8), limitaciones y restricciones técnicas (§ 9), cuándo desactivar (§ 10).
- [`tooling/prompt-preprocessing.md`](prompt-preprocessing.md) — hook que origina la necesidad del recursion guard via `CLAUDE_PREPROCESS_RECURSION`.
- [`hooks/README.md`](../hooks/README.md) — catálogo de los hooks + filosofía (idempotencia, < 100 ms, defensivos, sin secretos, cross-OS).
- Documentación oficial de `Notification`: [Anthropic Claude Code hooks](https://docs.claude.com/en/docs/claude-code/hooks).
