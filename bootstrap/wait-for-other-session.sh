#!/usr/bin/env bash
# Espera a que origin/<rama> avance y el working dir quede limpio.
# Uso: bash bootstrap/wait-for-other-session.sh [--branch <ref>] [--interval <sec>] [--timeout <sec>]
# Exit 0: condición cumplida. Exit 1: error de config. Exit 124: timeout.
set -euo pipefail

BRANCH="$(git symbolic-ref --short HEAD 2>/dev/null || echo main)"
INTERVAL=60
TIMEOUT=28800

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)   BRANCH="$2";   shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --timeout)  TIMEOUT="$2";  shift 2 ;;
    *) echo "Opción desconocida: $1" >&2; exit 1 ;;
  esac
done

REMOTE="origin"
REMOTE_REF="$REMOTE/$BRANCH"

if ! git remote get-url "$REMOTE" &>/dev/null; then
  echo "[wait-for-other-session] Error: remote '$REMOTE' no encontrado." >&2
  exit 1
fi

git fetch "$REMOTE" "$BRANCH" --quiet 2>/dev/null || true
INITIAL="$(git rev-parse "$REMOTE_REF" 2>/dev/null || echo "")"

if [[ -z "$INITIAL" ]]; then
  echo "[wait-for-other-session] Error: no se pudo leer $REMOTE_REF." >&2
  exit 1
fi

echo "[wait-for-other-session] Polling $REMOTE_REF cada ${INTERVAL}s (timeout ${TIMEOUT}s). Inicial: ${INITIAL:0:7}"

ELAPSED=0
while (( ELAPSED < TIMEOUT )); do
  sleep "$INTERVAL"
  ELAPSED=$(( ELAPSED + INTERVAL ))

  git fetch "$REMOTE" "$BRANCH" --quiet 2>/dev/null || true
  CURRENT="$(git rev-parse "$REMOTE_REF" 2>/dev/null || echo "")"
  STATUS="$(git status -s 2>/dev/null || echo "?")"
  TIMESTAMP="$(date '+%H:%M:%S')"

  if [[ "$CURRENT" != "$INITIAL" && -z "$STATUS" ]]; then
    echo "[$TIMESTAMP] OK: $REMOTE_REF avanzó (${INITIAL:0:7} → ${CURRENT:0:7}), working dir limpio."
    exit 0
  else
    NOTE=""
    [[ "$CURRENT" == "$INITIAL" ]] && NOTE="remoto sin cambio" || NOTE="remoto avanzó"
    [[ -n "$STATUS" ]] && NOTE="$NOTE, working dir sucio"
    echo "[$TIMESTAMP] Esperando... ($NOTE)"
  fi
done

echo "[wait-for-other-session] Timeout tras ${TIMEOUT}s." >&2
exit 124
