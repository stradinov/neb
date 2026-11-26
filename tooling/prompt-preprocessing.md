# Prompt preprocessing — hook `UserPromptSubmit`

> Lineamiento del hook `preprocess-prompt.py`. **Opcional personal**: no es baseline del equipo, cada dev decide si lo activa en su `~/.claude/settings.json`.
>
> Recurso transversal consumido: [`tooling/redaccion-es.md`](redaccion-es.md).
> Artefactos del hook: [`hooks/preprocess-prompt.py`](../hooks/preprocess-prompt.py), [`commands/preprocess.md`](../commands/preprocess.md), [`hooks/neb-hook.py`](../hooks/neb-hook.py) (dispatcher del plugin), [`hooks/hooks.json`](../hooks/hooks.json).

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
| 3. Confirmación previa | Claude principal en la sesión | Instruido por preámbulo: aplica el gate de autorización de la metodología (no pide OK donde el gate ya exime — artefactos que Neb genera, `.md`-only, autonomías declaradas por proyecto) |

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

**El modo por defecto es `off`**: el hook se instala pero arranca **inerte** (no llama a Haiku ni inyecta contexto). El dev lo enciende cuando quiere con `/preprocess full|fast` o fijándolo en la sección `preprocess` de su `config.json` (§ "Configuración personal default").

| Modo | Corrección | Eco | Confirmación | Cuándo usar |
|---|---|---|---|---|
| `off` (por defecto) | No | No | No | **Por defecto**: arranca inerte. También para sesión exploratoria, dictado correcto o prompt pegado puro |
| `full` | Sí | Sí | Según gate | Trabajo normal; máxima protección contra mala lectura |
| `fast` | Sí | Sí | No | Conversación fluida donde la confirmación constante estorba |

## 5. Configuración personal default

Sección `preprocess` de `<datos>/config.json`, el único archivo de configuración de Neb desde 8.0.0 (`<datos>` es la carpeta de datos: `NEB_DATA` si es una ruta absoluta; si no, `~/.neb`). Solo hace falta lo que cambia; el resto del archivo es de otras secciones:

```json
{
  "schema": 1,
  "preprocess": {
    "mode": "off",
    "model": "claude-haiku-4-5-20251001",
    "prefix": "$$"
  }
}
```

| Campo | Por defecto | Notas |
|---|---|---|
| `mode` | `"off"` | Uno de `"off"`, `"full"`, `"fast"`. **Por defecto `off`** (arranca inerte); pon `"full"` o `"fast"` para activarlo de forma permanente |
| `model` | `"claude-haiku-4-5-20251001"` | Modelo Anthropic para corregir. Subir a Sonnet si Haiku falla; cuesta más tokens y latencia |
| `prefix` | `"$$"` | Prefijo opt-out por prompt. `$$` comparte tecla física en distribuciones US y Español LATAM/España |

Cualquier campo ausente, vacío o de otro tipo cae al valor por defecto, y un `mode` fuera de los tres también (no enciende el hook). El archivo se lee en UTF-8 con o sin BOM. Si `config.json` todavía no existe (máquina que no ha corrido la migración de 8.0.0), el hook lee el `~/.claude/preprocess.json` de antes; sin ninguno de los dos, todos los valores por defecto aplican.

## 6. Cambio de modo en sesión

Precedencia (primero que aplica gana):

1. **Prefijo por prompt** `$$` (bypass una sola vez para ese turno). Ej: `$$explora rapido el repo` → Claude actúa directo, sin eco/confirmación.
2. **Slash command** `/preprocess full|fast|off` — persiste durante la sesión, escribe `<datos>/state/preprocess/<session_id>.json` con `preprocess-prompt.py --set-session-mode` (de paso borra los estados de sesiones de más de 7 días). Un `session_id` con caracteres fuera de letras, dígitos, `_` y `-` no tiene estado. Mientras dure la transición a 8.0.0, si ese archivo no existe el hook lee el de la ruta anterior, `~/.claude/preprocess-state/<session_id>.json`.
3. **Env var** `CLAUDE_PREPROCESS_MODE=fast` antes de lanzar `claude` — fija el modo de toda la sesión, ignora `config.json`. En PowerShell: `$env:CLAUDE_PREPROCESS_MODE = "fast"`.
4. **Configuración personal** — sección `preprocess` de `<datos>/config.json` (§ "Configuración personal default").
5. **Por defecto hardcoded**: `off`.

> Con el valor por defecto en `off`, el prefijo `$$` solo tiene efecto observable si activaste el hook en la sesión (`/preprocess full|fast`): por su precedencia máxima fuerza `off` en ese turno pese al modo de sesión. En el estado por defecto (off) es redundante e inocuo (solo se elimina el `$$` del prompt).

## 7. Activación

Manual. El plugin ya registra el hook (ver [`hooks/README.md`](../hooks/README.md) § "Bajo el plugin de Neb").

1. Agregar `preprocess-prompt` a `NEB_HOOKS` en el bloque `env` de `~/.claude/settings.json` (en una lista ya existente, va separado por comas y sin espacios). En Windows requiere Git Bash.

2. El comando viene con el plugin como `/neb:preprocess`; no hace falta copiarlo. Una copia personal anterior a 8.0.0 en `~/.claude/commands/preprocess.md` sigue escribiendo el estado en `~/.claude/preprocess-state/`, que el hook deja de leer en 9.0.0: bórrala y usa `/neb:preprocess`, o reemplázala por la versión actual de [`commands/preprocess.md`](../commands/preprocess.md).
3. Opcional: fijar un modo persistente en `config.json` (ver § "Configuración personal default" y el snippet de abajo). Sin él, el hook arranca en `off`.
4. Verificar Python 3 en PATH:
   - **Windows**: `py --version` o `python --version`.
   - **Linux/Mac**: `python3 --version`.
5. Verificar `claude` CLI en PATH: `claude --version`.
6. Reiniciar la sesión `claude` para que cargue el hook.

> Tras instalar, el hook arranca en modo **`off`** (inerte): no actúa hasta que lo enciendas con `/preprocess full` (o `fast`), o cambies `preprocess.mode` en `config.json`. Deliberado — copiar la instalación no altera el comportamiento de tus prompts hasta que tú lo decidas.

Snippet para fijar el modo persistente (Git Bash, Linux o Mac; `NEB_SRC` es la raíz del plugin o tu clon de `NEB_HOME`). Escribe solo `preprocess.mode` en `config.json`, de forma atómica, sin tocar las demás llaves; si el archivo no existe, lo crea con lo que dijeran los JSON sueltos de antes de 8.0.0. El valor va como JSON, con sus comillas:

```bash
py "$NEB_SRC/hooks/lib/neb_paths.py" set preprocess.mode '"fast"'   # o python / python3
py "$NEB_SRC/hooks/lib/neb_paths.py" config preprocess              # verifica la sección efectiva
```

En Windows PowerShell 5.1 las comillas internas se pierden al pasar el argumento: escríbelas como `'\"fast\"'`.

## 8. Heurística de skip

El hook **no llama a Haiku** en los siguientes casos (pasa raw a Claude principal):

- Slash command: el prompt empieza con `/`.
- Prompt < 12 caracteres tras `strip()`.
- Match de regex multilingüe de saludos/afirmaciones cortas: `hola|hi|hello|si|sí|yes|no|ok|okay|gracias|thanks|listo|continúa|continua|continue|sigue|dale|va|oui|salut`.
- Capa A — payload puro:
  - Prompt envuelto entre fences ` ``` ` y ` ``` ` sin prosa.
  - Todas las líneas no-vacías matchean profile-trace.
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
- **Guard de subsesión interna** (contrato canónico): el hook marca el entorno del subproceso `claude -p` con `NEB_INTERNAL_SUBSESSION=1` (vía `mark_internal_subsession` de [`hooks/lib/subsession.py`](../hooks/lib/subsession.py)) y abandona temprano si la detecta. La subsesión de Haiku hereda el `settings.json` del dev, así que dispararía **todos** los hooks de Neb; cada uno debe ser **inerte** dentro de ella. Consumidores que respetan la bandera (vía `is_internal_subsession` o el snippet shell canónico):
  - `preprocess-prompt.py` (`UserPromptSubmit`) — evita la auto-recursión (cascada de timeouts); fue el motivo original de la bandera.
  - `neb-bootstrap-context.py` (`SessionStart`) — **no inyecta el arranque**; sin esto el Haiku corrector recibe instrucciones de asistente + pendientes y **responde** la pregunta en vez de corregirla.
  - `hooks/neb-hook.py` (los hooks opcionales bajo el plugin) — no despacha ninguno en la subsesión.
  - `logbook-sync.{sh,ps1}` (`Stop`/`SessionEnd`/`PreCompact`, entrada de settings con clon) — no escribe la subsesión a la bitácora.
  - `notify-on-stop` / `notify-on-permission` — evitan el "chime fantasma".

  **Alias legacy** `CLAUDE_PREPROCESS_RECURSION` (obsoleto, retiro diferido a un major): `mark_internal_subsession` establece **ambas** y todos los consumidores chequean **ambas**, para tolerar la convivencia de plugins de distinta versión en el equipo durante la transición.

## 10. Cuándo desactivarlo

- Sesiones exploratorias largas donde la confirmación rompe el flujo (usar `/preprocess fast` o `/preprocess off`).
- Dictado correcto sin typos (rendimiento de voz a texto del dev es preciso).
- Conversación pura sin acciones de escritura.
- Pegando muchos payloads grandes consecutivos (Capa A debería skipear, pero si falsea positivos, `/preprocess off` ahorra latencia).

Desactivación permanente: quitar `preprocess-prompt` de `NEB_HOOKS` y reiniciar `claude` (con una entrada de settings con clon, quitar esa entrada).

## 11. Verificación

> **El valor por defecto es `off`**: los escenarios de corrección activa (3, 4, 6, 8, 9) requieren encender antes el hook con `/preprocess full` (o `fast`). En su estado por defecto, todo prompt pasa raw (como el escenario 7).

Escenarios a probar (medibles entre Enter y primer carácter de respuesta de Claude):

| # | Acción | Resultado esperado |
|---|---|---|
| 1 | Tipear `hola` | Pasa raw (filtro trivial). Sin latencia adicional. Sin eco. |
| 2 | Tipear `/help` | Pasa raw (slash command). Claude responde normal. |
| 3 | Tipear `agreaga una funcion que valide el correo en el formulrio de contacto` | Latencia 13–25 s; Claude muestra eco en español canónico; espera `sí`/`ok` antes de actuar. |
| 4 | Confirmar con `ok` | Claude actúa sobre la versión corregida (que vio en `additionalContext`). |
| 5 | Con `/preprocess full` activo, tipear `$$explora rapido el repo` | El prefijo gana sobre la sesión (precedencia máxima): bypass en ese turno, Claude actúa directo sin eco/confirmación. |
| 6 | `/preprocess fast` + prompt largo | Latencia 13–25 s; eco breve; sin confirmación. |
| 7 | `/preprocess off` + prompt largo | Sin latencia adicional; sin eco. |
| 8 | `/preprocess full` + prompt largo | Vuelve al comportamiento del escenario 3. |
| 9 | Plan mode activo + prompt no trivial | Hook SÍ aplica; eco + confirmación previa al diseño del plan. |
| 10 | Pegar solo bloque de código con fences | Skip total en Capa A; sin latencia; Claude recibe el código directo. |
| 11 | `por que mi codigo crashea?` + pegar función JS | Capa A no skipea; Capa B corrige solo la pregunta; el código queda intacto byte por byte. |
| 12 | Pegar email sin petición explícita | Capa B detecta que no es petición conversacional y devuelve idéntico; Claude omite eco/confirmación. |
| 13 | Prompt en inglés: `add a validation function for the email field` | Auto-detección; corrección + eco en inglés; confirmación esperada en inglés. |
| 14 | Desconectar red, tipear prompt largo | Timeout interno 30 s; hook abandona; prompt pasa raw. No cuelga la sesión. |
| 15 | Deshabilitar permanentemente | Quitar `preprocess-prompt` de `NEB_HOOKS`, reiniciar `claude`. |

## 12. Referencias

- [`hooks/README.md`](../hooks/README.md) — catálogo de los hooks + nota de excepción a "< 100ms".
- [`tooling/redaccion-es.md`](redaccion-es.md) — taxonomía de errores que el hook aplica.
- Documentación oficial de `UserPromptSubmit`: [Anthropic Claude Code hooks](https://docs.claude.com/en/docs/claude-code/hooks).
