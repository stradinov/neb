#!/usr/bin/env bash
# usage-tracker.sh — Stop hook: acumula tokens/costo del turno al draft del change MD (registro) del REQ activo.
# Ver hooks/lib/usage-tracker.py para la lógica completa.
# Filosofía: defensivo — exit 0 siempre; errores a stderr.
set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
CWD=$(echo "$INPUT"       | jq -r '.cwd // ""')

[ -z "$SESSION_ID" ] || [ -z "$CWD" ] && exit 0

# Codificar CWD al formato de directorio de proyecto Claude.
# Regla: ':' → '-', luego '/' y '\' → '-'.
# Ejemplo: C:\Users\foo\bar → C-\Users\foo\bar → C--Users-foo-bar
ENCODED=$(echo "$CWD" | sed 's/:/\-/g' | tr '/\\' '-')

GUIDE="${NEB_HOME:-$HOME/.claude/neb}"
PYTHON_CMD=""
for cmd in py python python3; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON_CMD="$cmd"
    break
  fi
done

[ -z "$PYTHON_CMD" ] && echo "[usage-tracker] WARNING: Python no encontrado. Hook desactivado." >&2 && exit 0

"$PYTHON_CMD" "$GUIDE/hooks/lib/usage-tracker.py" \
  "$SESSION_ID" "$ENCODED" "$GUIDE" "$HOME" \
  2>/dev/null || true

exit 0
