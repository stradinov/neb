#!/usr/bin/env bash
set -euo pipefail

INPUT=$(cat)
PLAN=$(echo "$INPUT" | jq -r '.tool_input.plan // empty')
SID=$(echo "$INPUT"  | jq -r '.session_id // "unknown"')
CWD=$(echo "$INPUT"  | jq -r '.cwd // ""')

if [ -z "$PLAN" ]; then
  exit 0
fi

PROJECT=$(basename "${CWD:-unknown}")
TS=$(date '+%Y%m%d-%H%M%S')

GUIDE="${NEB_HOME:-$HOME/.claude/neb}"
SLUGIFY="$GUIDE/hooks/lib/slugify.sh"

if [ -x "$SLUGIFY" ]; then
  SLUG=$(echo "$PLAN" | head -1 | bash "$SLUGIFY" | head -c 50)
else
  SLUG=$(echo "$PLAN" | head -1 | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | sed 's/--*/-/g; s/^-//; s/-$//' | head -c 50)
fi

[ -z "$SLUG" ] && SLUG="plan"

DEST="${HOME}/.claude/approved-plans"
mkdir -p "$DEST"
FILE="${DEST}/${TS}-${PROJECT}-${SLUG}.md"

{
  echo "# Plan aprobado — $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  echo "**Proyecto:** $PROJECT"
  echo "**Sesión:** $SID"
  echo "**CWD:** $CWD"
  echo
  echo "$PLAN"
} > "$FILE"

exit 0
