#!/usr/bin/env bash
# notify-on-permission.sh — Notification hook: reproduce un WAV cuando Claude
# pide permiso para una herramienta o el prompt input lleva idle > 60s.
#
# Opt-in personal. Lineamiento: tooling/notify-on-permission.md.
# Defaults: 1 chime fijo. Sin scaling, sin walk-back de transcript.
# Configurable en ~/.claude/notify-on-permission.json (enabled, wav).
#
# Recursion guard: si CLAUDE_PREPROCESS_RECURSION=1 (subproceso `claude -p`
# del preprocess-prompt.py), abandona sin sonar — evita chime fantasma.
#
# Requisitos: bash, jq (blando), un player (afplay/paplay/aplay/play). Sin
# player en PATH → exit 0 silencioso. Defensivo: cualquier falla → exit 0.

set +e

[ "$CLAUDE_PREPROCESS_RECURSION" = "1" ] && exit 0

log() { printf '[notify-on-permission] %s\n' "$*" >&2; }

# --- Detección de player ---------------------------------------------------

PLAYER=""
for cand in afplay paplay aplay play; do
    if command -v "$cand" >/dev/null 2>&1; then
        PLAYER="$cand"
        break
    fi
done
[ -z "$PLAYER" ] && exit 0

# --- Defaults ---------------------------------------------------------------

ENABLED=true
WAV=""

# --- Cargar config personal -------------------------------------------------

CFG="$HOME/.claude/notify-on-permission.json"
HAVE_JQ=0
command -v jq >/dev/null 2>&1 && HAVE_JQ=1

if [ -f "$CFG" ] && [ "$HAVE_JQ" = "1" ]; then
    if jq empty "$CFG" >/dev/null 2>&1; then
        ENABLED=$(jq -r 'if has("enabled") then .enabled     else true end' "$CFG")
        WAV=$(    jq -r 'if has("wav")     then (.wav // "") else ""   end' "$CFG")
    else
        log "config ilegible, usando defaults"
    fi
fi

[ "$ENABLED" != "true" ] && exit 0

# --- Resolver WAV -----------------------------------------------------------

DEFAULT_WAV="${NEB_WORKSPACE:-$NEB_HOME}/personal/chimes-loud.wav"
if [ -z "$WAV" ]; then
    WAV="$DEFAULT_WAV"
elif [ ! -f "$WAV" ]; then
    if [ -f "$DEFAULT_WAV" ]; then
        log "wav '$WAV' no existe; usando default '$DEFAULT_WAV'"
        WAV="$DEFAULT_WAV"
    else
        exit 0
    fi
fi
[ ! -f "$WAV" ] && exit 0

# --- 1 chime async ----------------------------------------------------------

(
    "$PLAYER" "$WAV" >/dev/null 2>&1
) &
disown 2>/dev/null

exit 0
