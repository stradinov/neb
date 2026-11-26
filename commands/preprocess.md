---
name: preprocess
description: Cambia el modo del hook UserPromptSubmit en la sesión actual.
allowed-tools: Bash
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

1. Validar que el argumento es exactamente uno de: `full`, `fast`, `off`. Si no, responder: "Modo inválido. Usa `/preprocess full|fast|off`."
2. Resolver el `session_id` de la sesión actual. En Claude Code, el directorio de sesión vive en `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. El `<encoded-cwd>` se obtiene sanitizando el CWD: `:` → `-`, luego `/` y `\` → `-`. El `<session-id>` es el archivo `.jsonl` más reciente en ese directorio.
3. Escribir el modo con el propio hook, del árbol del plugin (el mismo código que corre el hook; Claude Code sustituye la raíz al cargar este comando):

   ```bash
   NEB_SRC="${CLAUDE_PLUGIN_ROOT}"
   [ -n "$NEB_SRC" ] || NEB_SRC="${NEB_HOME:-}"   # copia personal en ~/.claude/commands/: sin sustitución
   [ -f "$NEB_SRC/hooks/preprocess-prompt.py" ] || echo "Neb: no hay hooks/preprocess-prompt.py en '$NEB_SRC'; si la ruta quedó vacía, actualiza Claude Code (sustitución de CLAUDE_PLUGIN_ROOT en comandos)" >&2
   py "$NEB_SRC/hooks/preprocess-prompt.py" --set-session-mode "<session_id>" "<modo>"   # o python / python3
   ```

   Escribe atómicamente `<datos>/state/preprocess/<session_id>.json` (la carpeta de datos de Neb: `NEB_DATA` o `~/.neb`) y borra los estados de sesiones de más de 7 días. Salida 0 con la ruta escrita. Con salida 2 (session_id o modo inválido, un enlace en la ruta), reporta el mensaje de stderr y termina sin escribir nada por otra vía. Sin una ruta impresa, el árbol es anterior a 8.0.0 y no conoce `--set-session-mode`: dilo y pide actualizar el plugin.
4. Confirmar al dev: "Modo del hook preprocess-prompt = `<modo>` para esta sesión."

El hook `preprocess-prompt.py` lee este archivo al inicio de cada prompt subsecuente y aplica el modo. La precedencia completa está documentada en [`tooling/prompt-preprocessing.md`](../tooling/prompt-preprocessing.md).
