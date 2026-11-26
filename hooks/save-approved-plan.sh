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

# Carpeta de datos de Neb (8.0.0): la resuelve hooks/lib/neb_paths.py, el resolvedor único (NEB_DATA
# absoluta o ~/.neb). Hasta 7.x era ~/.claude/approved-plans; lo que quede ahí lo muda la migración 8.0.0.
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
NEB_PATHS="$HERE/lib/neb_paths.py"
DEST=""
for PY in python3 python; do
  if command -v "$PY" >/dev/null 2>&1 && [ -f "$NEB_PATHS" ]; then
    # tr: el print de Python en Windows termina en \r\n y $( ) solo quita el \n.
    DEST=$("$PY" "$NEB_PATHS" path approved-plans 2>/dev/null | tr -d '\r') || DEST=""
    [ -n "$DEST" ] && break
  fi
done
if [ -z "$DEST" ]; then
  # Sin Python: misma regla que neb_paths (NEB_DATA solo si es absoluta; si no, ~/.neb).
  case "${NEB_DATA:-}" in
    /*|[A-Za-z]:[\\/]*) DEST="$NEB_DATA/approved-plans" ;;
    *) DEST="$HOME/.neb/approved-plans" ;;
  esac
fi
if command -v cygpath >/dev/null 2>&1; then
  DEST=$(cygpath -u "$DEST")
fi
# Neb no escribe a través de enlaces (como neb_paths.ensure_dir); un hook no rompe la sesión: sale 0.
if [ -L "$DEST" ] || [ -L "$(dirname "$DEST")" ]; then
  echo "save-approved-plan: $DEST es un enlace: no se guarda el plan" >&2
  exit 0
fi
(umask 077 && mkdir -p "$DEST")
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
