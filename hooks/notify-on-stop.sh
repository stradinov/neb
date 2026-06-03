#!/usr/bin/env bash
# notify-on-stop.sh — Stop hook: reproduce un WAV al cerrar cada turno de Claude.
#
# Opt-in personal. Lineamiento: tooling/notify-on-stop.md.
# Defaults: 1 chime + 1 por cada minuto del turno (max 5), skip si < 10s.
# Configurable en ~/.claude/notify-on-stop.json (enabled, wav, min_seconds, max_chimes, scaling).
#
# Recursion guard: si CLAUDE_PREPROCESS_RECURSION=1 (subproceso `claude -p`
# del preprocess-prompt.py), abandona sin sonar — evita chime fantasma.
#
# Requisitos: bash, jq, un player (afplay/paplay/aplay/play). Sin alguno
# de estos, exit 0 silencioso. Defensivo: cualquier falla → exit 0.

set +e

[ "$CLAUDE_PREPROCESS_RECURSION" = "1" ] && exit 0

log() { printf '[notify-on-stop] %s\n' "$*" >&2; }

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
MIN_SEC=10
MAX_CHIMES=5
SCALING="per-minute"

# --- Cargar config personal -------------------------------------------------

CFG="$HOME/.claude/notify-on-stop.json"
HAVE_JQ=0
command -v jq >/dev/null 2>&1 && HAVE_JQ=1

if [ -f "$CFG" ] && [ "$HAVE_JQ" = "1" ]; then
    if jq empty "$CFG" >/dev/null 2>&1; then
        ENABLED=$(jq -r 'if has("enabled")     then .enabled     else true          end' "$CFG")
        WAV=$(    jq -r 'if has("wav")         then (.wav // "") else ""            end' "$CFG")
        MIN_SEC=$(jq -r 'if has("min_seconds") then .min_seconds else 10            end' "$CFG")
        MAX_CHIMES=$(jq -r 'if has("max_chimes") then .max_chimes else 5            end' "$CFG")
        SCALING=$( jq -r 'if has("scaling")    then .scaling    else "per-minute" end' "$CFG")
    else
        log "config ilegible, usando defaults"
    fi
fi

[ "$ENABLED" != "true" ] && exit 0

# Normalización
case "$MIN_SEC" in ''|*[!0-9-]*) MIN_SEC=10 ;; esac
[ "$MIN_SEC" -lt 0 ] 2>/dev/null && MIN_SEC=0
case "$MAX_CHIMES" in ''|*[!0-9]*) MAX_CHIMES=5 ;; esac
[ "$MAX_CHIMES" -lt 1  ] 2>/dev/null && MAX_CHIMES=1
[ "$MAX_CHIMES" -gt 20 ] 2>/dev/null && MAX_CHIMES=20
[ "$SCALING" != "fixed" ] && [ "$SCALING" != "per-minute" ] && SCALING="per-minute"

# --- Resolver WAV -----------------------------------------------------------

DEFAULT_WAV="$NEB_HOME/personal/chimes-loud.wav"
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

# --- Player N veces (background) -------------------------------------------

play_n() {
    local n=$1
    [ "$n" -lt 1 ] && n=1
    [ "$n" -gt "$MAX_CHIMES" ] && n="$MAX_CHIMES"
    (
        for _ in $(seq 1 "$n"); do
            "$PLAYER" "$WAV" >/dev/null 2>&1
            sleep 0.2
        done
    ) &
    disown 2>/dev/null
}

# --- Leer hook event + transcript ------------------------------------------

RAW=$(cat)
TRANSCRIPT=""
if [ "$HAVE_JQ" = "1" ]; then
    TRANSCRIPT=$(printf '%s' "$RAW" | jq -r '.transcript_path // ""' 2>/dev/null)
fi

if [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ]; then
    play_n 1
    exit 0
fi

# --- Walk-back al último user message no-toolUseResult ---------------------

# tac (GNU) o tail -r (BSD/macOS)
REVERSE=""
if command -v tac >/dev/null 2>&1; then
    REVERSE="tac"
elif tail -r </dev/null >/dev/null 2>&1; then
    REVERSE="tail -r"
fi

BOUNDARY=""
if [ -n "$REVERSE" ] && [ "$HAVE_JQ" = "1" ]; then
    while IFS= read -r line; do
        ts=$(printf '%s' "$line" | jq -r 'select(.type=="user" and (has("toolUseResult")|not)) | .timestamp // empty' 2>/dev/null)
        if [ -n "$ts" ]; then
            BOUNDARY="$ts"
            break
        fi
    done < <($REVERSE "$TRANSCRIPT" 2>/dev/null)
fi

if [ -z "$BOUNDARY" ]; then
    play_n 1
    exit 0
fi

# --- Duración --------------------------------------------------------------

# ISO 8601 con fracciones (e.g. 2026-05-18T12:34:56.789Z).
# GNU date acepta directo; BSD date requiere recortar fracciones.
NOW_EPOCH=$(date -u +%s)
BOUNDARY_TRIM="${BOUNDARY%.*}"
case "$BOUNDARY_TRIM" in *Z) ;; *) BOUNDARY_TRIM="${BOUNDARY_TRIM}Z" ;; esac

BOUNDARY_EPOCH=$(date -u -d "$BOUNDARY" +%s 2>/dev/null)
if [ -z "$BOUNDARY_EPOCH" ]; then
    BOUNDARY_EPOCH=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$BOUNDARY_TRIM" +%s 2>/dev/null)
fi
if [ -z "$BOUNDARY_EPOCH" ]; then
    play_n 1
    exit 0
fi

DUR=$(( NOW_EPOCH - BOUNDARY_EPOCH ))
[ "$DUR" -lt "$MIN_SEC" ] && exit 0

# --- Scaling ---------------------------------------------------------------

if [ "$SCALING" = "fixed" ]; then
    N=1
else
    N=$(( 1 + DUR / 60 ))
fi

play_n "$N"
exit 0
