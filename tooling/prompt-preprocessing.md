# Prompt preprocessing — hook `UserPromptSubmit`

> Lineamiento del hook `preprocess-prompt.py`. **Opt-in personal**: no es baseline del equipo, cada dev decide si lo activa en su `~/.claude/settings.json`.
>
> Recurso transversal consumido: [`tooling/redaccion-es.md`](redaccion-es.md).
> Artefactos del hook: [`hooks/preprocess-prompt.py`](../hooks/preprocess-prompt.py), [`commands/preprocess.md`](../commands/preprocess.md), [`templates/claude-user-settings.json.template`](../templates/claude-user-settings.json.template).

---

## 1. Problema

El dev tipea rápido en consola: typos, acentos faltantes, jerga oral, puntuación inconsistente. Claude a veces interpreta mal y procede sobre la interpretación errada — turno desperdiciado, posibles acciones equivocadas. En plan mode el costo es mayor: Claude diseña un plan basado en una mala lectura del prompt.

Aplica a cualquier idioma del dev (español MX, español ES, inglés, portugués, etc.); el hook auto-detecta el idioma del prompt y corrige en él.

Ejemplo (el dev, español MX): `agreaga una funcion que valide el correo en el formulrio de contacto` → Claude lee literalmente la versión con typos y procede; el hook corrige a `Agrega una función que valide el correo en el formulario de contacto` antes de que Claude actúe.

## 2. Pipeline (responsabilidad compartida)

`UserPromptSubmit` no reescribe el prompt del dev — solo inyecta `additionalContext` que Claude ve como system reminder. La corrección + eco + confirmación son responsabilidad **compartida** entre el hook (Python + `claude -p`) y el modelo principal de la sesión.

| Paso | Quién | Cómo |
|---|---|---|
| 1. Corrección ortográfica/sintaxis | Hook (Python + `claude -p --model claude-haiku-4-5`) | Devuelve la versión corregida como `additionalContext` |
| 2. Eco en el idioma del prompt | Claude principal en la sesión | Instruido por preámbulo que el hook inyecta |
| 3. Confirmación previa | Claude principal en la sesión | Instruido por preámbulo (espera "sí"/"ok"/"continúa" antes de tomar acciones de escritura) |

El prompt original se ve tal cual en el transcript; la versión corregida vive en system reminder.

## 3. Arquitectura

```
dev tipea prompt → UserPromptSubmit hook
                  ├─ filtros de skip (slash, < 12 chars, saludo)
                  ├─ Capa A: heurística payload puro → skip
                  ├─ Capa B: claude -p (Haiku) corrige texto conversacional
                  │          preserva código/log/JSON byte por byte
                  └─ Capa C: preámbulo a Claude principal
                            └─ Claude muestra eco + espera confirmación → ejecuta
```

## 4. Modos

| Modo | Corrección | Eco | Confirmación | Cuándo usar |
|---|---|---|---|---|
| `full` (default) | Sí | Sí | Sí | Trabajo normal; máxima protección contra mala lectura |
| `fast` | Sí | Sí | No | Conversación fluida donde la confirmación constante estorba |
| `off` | No | No | No | Sesión exploratoria, dictado correcto, prompt pegado puro |

## 5. Configuración personal default

`~/.claude/preprocess.json`:

```json
{
  "mode": "full",
  "model": "claude-haiku-4-5-20251001",
  "prefix": "$$"
}
```

| Campo | Default | Notas |
|---|---|---|
| `mode` | `"full"` | Uno de `"full"`, `"fast"`, `"off"` |
| `model` | `"claude-haiku-4-5-20251001"` | Modelo Anthropic para corregir. Subir a Sonnet si Haiku falla; cuesta más tokens y latencia |
| `prefix` | `"$$"` | Prefijo opt-out por prompt. `$$` comparte tecla física en distribuciones US y Español LATAM/España |

Cualquier campo ausente cae al default hardcoded en el script. Si el archivo no existe, todos los defaults aplican.

## 6. Cambio de modo en sesión

Precedencia (primero que aplica gana):

1. **Prefijo por prompt** `$$` (bypass una sola vez para ese turno). Ej: `$$explora rapido el repo` → Claude actúa directo, sin eco/confirmación.
2. **Slash command** `/preprocess full|fast|off` — persiste durante la sesión, escribe `~/.claude/preprocess-state/<session_id>.json`.
3. **Env var** `CLAUDE_PREPROCESS_MODE=fast` antes de lanzar `claude` — fija el modo de toda la sesión, ignora `preprocess.json`. En PowerShell: `$env:CLAUDE_PREPROCESS_MODE = "fast"`.
4. **Archivo personal** `~/.claude/preprocess.json` — default personal.
5. **Default hardcoded**: `full`.

## 7. Activación

Manual. (El proceso guiado de instalación de `neb` queda como pendiente del repo.)

1. Copiar el bloque `UserPromptSubmit` de [`templates/claude-user-settings.json.template`](../templates/claude-user-settings.json.template) a `~/.claude/settings.json` del dev. Elegir el bloque OS apropiado (Windows / Linux-Mac).

   > **Windows — por qué `"shell": "powershell"` y no `cmd /c py ...`**: Claude Code ejecuta el `command` del hook sin shell intermediario, así que `%VAR%` no se expande en tiempo de invocación. El intento previo (`cmd /c py "%NEB_HOME%\..."` en v2.23.2) sí desbloqueaba la sesión y dejaba que `cmd` expandiera `%VAR%`, pero el spawn de cmd en Windows no propaga el JSON de stdin al subprocess `py`: el JSON termina interpretándose como segundo comando para cmd (stderr `"..." no se reconoce como un comando`), y el script Python jamás corre. La forma estable es declarar `"shell": "powershell"` — Claude Code envuelve el comando vía `powershell -NoProfile -Command "..."`, expande `$env:NEB_HOME`, y propaga stdin correctamente al subprocess. El template del repo trae la sintaxis correcta — copy/paste tal cual. En bash (Linux/Mac) la expansión de `$VAR` ocurre nativa, no requiere `shell` ni wrapper.

2. Copiar [`commands/preprocess.md`](../commands/preprocess.md) a `~/.claude/commands/`.
3. Crear `~/.claude/preprocess.json` con el esquema completo (ver §5).
4. Verificar Python 3 en PATH:
   - **Windows**: `py --version` o `python --version`.
   - **Linux/Mac**: `python3 --version`.
5. Verificar `claude` CLI en PATH: `claude --version`.
6. Reiniciar la sesión `claude` para que cargue el hook.

Snippet PowerShell para Windows (copy/paste):

```powershell
$env:USERPROFILE | ForEach-Object { New-Item -ItemType Directory -Force -Path "$_\.claude\commands" | Out-Null }
Copy-Item "$env:NEB_HOME\commands\preprocess.md" "$env:USERPROFILE\.claude\commands\preprocess.md"
@'
{"mode": "full", "model": "claude-haiku-4-5-20251001", "prefix": "$$"}
'@ | Out-File -Encoding utf8 "$env:USERPROFILE\.claude\preprocess.json"
```

Snippet bash (Linux/Mac):

```bash
mkdir -p ~/.claude/commands
cp "$NEB_HOME/commands/preprocess.md" ~/.claude/commands/preprocess.md
echo '{"mode": "full", "model": "claude-haiku-4-5-20251001", "prefix": "$$"}' > ~/.claude/preprocess.json
```

## 8. Heurística de skip

El hook **no llama a Haiku** en los siguientes casos (pasa raw a Claude principal):

- Slash command: el prompt empieza con `/`.
- Prompt < 12 caracteres tras `strip()`.
- Match de regex multilingüe de saludos/afirmaciones cortas: `hola|hi|hello|si|sí|yes|no|ok|okay|gracias|thanks|listo|continúa|continua|continue|sigue|dale|va|oui|salut`.
- Capa A — payload puro:
  - Prompt envuelto entre fences ` ``` ` y ` ``` ` sin prosa.
  - Todas las líneas no-vacías matchean stack-trace.
  - `len(prose_lines) == 0` **y** `code_lines / total_lines > 0.80`.

Umbral conservador a propósito: ante duda, pasa a Capa B (Haiku decide).

## 9. Limitaciones y alcances

### Alcances

- Corrección ortográfica/sintáctica en el idioma del prompt (auto-detectado por Haiku).
- Estructura de eco + confirmación delegada a Claude principal via preámbulo.
- Preservación intacta de código, log, JSON y contenido pegado.

### No alcances

- **No** detecta términos desconocidos automáticamente.
- **No** usa glosario de jerga organizacional (e.g. una sigla que significa algo distinto como nombre de cliente y como código de un sistema externo).
- **No** traduce el prompt al inglés (decisión explícita del plan — agregaría latencia/tokens sin valor real porque el hook no reescribe el prompt, solo inyecta contexto).
- **No** traduce paths, comandos shell, nombres propios ni contenido de archivos.
- **No** modifica código, logs, JSON ni contenido pegado de tercero.

### Restricciones técnicas

- El hook **no reescribe** el prompt original — el dev ve su typo en el transcript; la corrección vive en system reminder.
- **No interactivo**: el hook no lee stdin del dev (corre sin terminal controlador).
- **Latencia**: 13–25 s por prompt no trivial (medida localmente con Haiku 4.5 + `--system-prompt` completo). Excepción documentada a la filosofía "< 100ms" de los hooks — la llamada inevitable a Haiku lo justifica. La estimación inicial del plan (2–4 s) era optimista; el dev mide el costo real en uso y decide si compensa los typos que corrige.
- **Costo**: ≈ 40–120 tokens de Haiku por prompt típico.
- **Comportamiento ante falla** (red, API, timeout, Python ausente, `claude` CLI ausente): `exit 0` silencioso sin contexto inyectado; el prompt pasa raw. Nunca bloquea la sesión.
- **Slash commands**: skipeados; el hook detecta `^/` y deja pasar.
- **Plan mode**: SÍ aplica (decisión consciente — corrige antes de planear evita planes erróneos).
- **Múltiples hooks UserPromptSubmit**: Claude Code no soporta matcher en este event; si el equipo agrega otro hook UserPromptSubmit, todos los `additionalContext` se concatenan.
- **Recursion guard**: el hook setea la variable de entorno `CLAUDE_PREPROCESS_RECURSION=1` antes de invocar `claude -p` y abandona temprano si la detecta — evita que el hook se llame a sí mismo cuando la sesión interna de Haiku dispara `UserPromptSubmit` por la misma config del dev. Sin este guard, cada llamada cae en cascada de timeouts hasta que cada nivel abandona. La misma bandera la consume el hook `Stop` [`notify-on-stop`](notify-on-stop.md) para evitar el "chime fantasma" cuando el subproceso `claude -p` termina su turno interno.

## 10. Cuándo desactivarlo

- Sesiones exploratorias largas donde la confirmación rompe el flujo (usar `/preprocess fast` o `/preprocess off`).
- Dictado correcto sin typos (rendimiento de voz a texto del dev es preciso).
- Conversación pura sin acciones de escritura.
- Pegando muchos payloads grandes consecutivos (Capa A debería skipear, pero si falsea positivos, `/preprocess off` ahorra latencia).

Desactivación permanente: comentar bloque `UserPromptSubmit` en `~/.claude/settings.json` y reiniciar `claude`.

## 11. Verificación

Escenarios a probar tras activar (medibles entre Enter y primer carácter de respuesta de Claude):

| # | Acción | Resultado esperado |
|---|---|---|
| 1 | Tipear `hola` | Pasa raw (filtro trivial). Sin latencia adicional. Sin eco. |
| 2 | Tipear `/help` | Pasa raw (slash command). Claude responde normal. |
| 3 | Tipear `agreaga una funcion que valide el correo en el formulrio de contacto` | Latencia 13–25 s; Claude muestra eco en español canónico; espera `sí`/`ok` antes de actuar. |
| 4 | Confirmar con `ok` | Claude actúa sobre la versión corregida (que vio en `additionalContext`). |
| 5 | Tipear `$$explora rapido el repo` | Bypass; Claude actúa directo sin eco/confirmación. |
| 6 | `/preprocess fast` + prompt largo | Latencia 13–25 s; eco breve; sin confirmación. |
| 7 | `/preprocess off` + prompt largo | Sin latencia adicional; sin eco. |
| 8 | `/preprocess full` + prompt largo | Vuelve al comportamiento del escenario 3. |
| 9 | Plan mode activo + prompt no trivial | Hook SÍ aplica; eco + confirmación previa al diseño del plan. |
| 10 | Pegar solo bloque de código con fences | Skip total en Capa A; sin latencia; Claude recibe el código directo. |
| 11 | `por que mi codigo crashea?` + pegar función JS | Capa A no skipea; Capa B corrige solo la pregunta; el código queda intacto byte por byte. |
| 12 | Pegar email sin petición explícita | Capa B detecta que no es petición conversacional y devuelve idéntico; Claude omite eco/confirmación. |
| 13 | Prompt en inglés: `add a validation function for the email field` | Auto-detección; corrección + eco en inglés; confirmación esperada en inglés. |
| 14 | Desconectar red, tipear prompt largo | Timeout interno 30 s; hook abandona; prompt pasa raw. No cuelga la sesión. |
| 15 | Deshabilitar permanentemente | Comentar bloque `UserPromptSubmit` en `~/.claude/settings.json`, reiniciar `claude`. |

## 12. Referencias

- [`hooks/README.md`](../hooks/README.md) — catálogo de los hooks + nota de excepción a "< 100ms".
- [`tooling/redaccion-es.md`](redaccion-es.md) — taxonomía de errores que el hook aplica.
- Documentación oficial de `UserPromptSubmit`: [Anthropic Claude Code hooks](https://docs.claude.com/en/docs/claude-code/hooks).
