---
name: preprocess
description: Cambia el modo del hook UserPromptSubmit en la sesión actual.
allowed-tools: Bash, Write
---

# /preprocess <full|fast|off>

Cambia el modo del hook de preprocesado de prompts para esta sesión.
Persiste hasta que se ejecute otro `/preprocess <modo>` o termine la sesión.

> El hook arranca en modo **`off`** por defecto (inerte): no corrige nada hasta que lo enciendas aquí con `full` o `fast`.

Uso:
- `/preprocess full` — enciende el hook: corrección + eco + confirmación previa.
- `/preprocess fast` — enciende el hook: corrección + eco; sin confirmación.
- `/preprocess off` — vuelve al estado por defecto (hook inerte) para esta sesión.

Argumento recibido: `$ARGUMENTS`

Implementación:

1. Validar que el argumento es exactamente uno de: `full`, `fast`, `off`. Si no, responder: "Modo inválido. Usá `/preprocess full|fast|off`."
2. Resolver el HOME del dev (`~` en POSIX, `$env:USERPROFILE` en Windows).
3. Resolver el `session_id` de la sesión actual. En Claude Code, el directorio de sesión vive en `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. El `<encoded-cwd>` se obtiene sanitizando el CWD: `:` → `-`, luego `/` y `\` → `-`. El `<session-id>` es el archivo `.jsonl` más reciente en ese directorio.
4. Crear el directorio `~/.claude/preprocess-state/` si no existe.
5. Escribir `~/.claude/preprocess-state/<session_id>.json` con el contenido `{"mode": "<modo>"}` (JSON válido, UTF-8, sin BOM).
6. Confirmar al dev: "Modo del hook preprocess-prompt = `<modo>` para esta sesión."

El hook `preprocess-prompt.py` lee este archivo al inicio de cada prompt subsecuente y aplica el modo. La precedencia completa está documentada en [`tooling/prompt-preprocessing.md`](../tooling/prompt-preprocessing.md).
