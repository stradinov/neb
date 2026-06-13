#!/usr/bin/env bash
# logbook-sync.sh — Stop/SessionEnd/PreCompact hook (Linux/Mac): publica la entrada del work a la bitácora local.
# Ver hooks/lib/logbook.py para la lógica. Filosofía: defensivo — exit 0 siempre; errores a stderr.
# En Windows usar logbook-sync.ps1 ("shell": "powershell" — consume stdin; ver hooks/README.md §Filosofía).
set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
CWD=$(echo "$INPUT"        | jq -r '.cwd // ""')
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // ""')
EVENT=$(echo "$INPUT"      | jq -r '.hook_event_name // ""')

[ -z "$SESSION_ID" ] || [ -z "$CWD" ] && exit 0

GUIDE="${NEB_HOME:-$HOME/.claude/neb}"
PYTHON_CMD=""
for cmd in py python python3; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON_CMD="$cmd"
    break
  fi
done

[ -z "$PYTHON_CMD" ] && echo "[logbook] WARNING: Python no encontrado. Hook desactivado." >&2 && exit 0

"$PYTHON_CMD" "$GUIDE/hooks/lib/logbook.py" \
  "$SESSION_ID" "$CWD" "$TRANSCRIPT" "$EVENT" "$GUIDE" "$HOME" \
  2>/dev/null || true

exit 0
