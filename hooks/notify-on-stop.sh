#!/usr/bin/env bash
# notify-on-stop.sh — Stop hook: reproduce un WAV al cerrar cada turno de Claude.
#
# Opt-in personal. Lineamiento: tooling/notify-on-stop.md.
# Defaults: 1 chime + 1 por cada minuto del turno (max 5), skip si < 10s.
# Configurable en la sección notify.stop del config.json de la carpeta de datos de Neb
# (enabled, wav, min_seconds, max_chimes, scaling).
#
# Guard de subsesión interna del corrector (preprocess-prompt.py): si
# NEB_INTERNAL_SUBSESSION=1 (o el alias legacy CLAUDE_PREPROCESS_RECURSION=1),
# abandona sin sonar — evita chime fantasma. Ver hooks/lib/subsession.py.
#
# Requisitos: bash, jq (blando: sin él, 1 chime de cortesía; la config no lo usa), un player
# (afplay/paplay/aplay/play). Sin player en PATH → exit 0 silencioso.
# Defensivo: cualquier falla → exit 0.

set +e

if [ "${NEB_INTERNAL_SUBSESSION:-}" = "1" ] || [ "${CLAUDE_PREPROCESS_RECURSION:-}" = "1" ]; then exit 0; fi

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

# --- Config efectiva --------------------------------------------------------

# Un solo resolvedor (lib/notify_sound.py) lee la sección notify.stop de config.json en la carpeta de
# datos de Neb, normaliza los valores y resuelve el WAV (presets, ruta absoluta, respaldo). Bajo el
# despachador del plugin llegan ya resueltos en variables NEB_NOTIFY_* (NEB_NOTIFY_WAV marca que vienen
# de él); invocado directo (entradas de settings.json anteriores a 6.15.0) se le piden a su CLI
# `config`, en líneas llave=valor. Sin Python: valores por defecto y el sonido de neb.
HERE="$(cd "$(dirname "$0")" && pwd)"
ENABLED=true
MIN_SEC=10
MAX_CHIMES=5
SCALING="per-minute"
WAV=""

set_value() {
    case "$1" in
        enabled)     ENABLED="$2" ;;
        wav)         WAV="$2" ;;
        min_seconds) MIN_SEC="$2" ;;
        max_chimes)  MAX_CHIMES="$2" ;;
        scaling)     SCALING="$2" ;;
    esac
}

if [ -n "${NEB_NOTIFY_WAV:-}" ]; then
    set_value enabled     "${NEB_NOTIFY_ENABLED:-true}"
    set_value wav         "$NEB_NOTIFY_WAV"
    set_value min_seconds "${NEB_NOTIFY_MIN_SECONDS:-10}"
    set_value max_chimes  "${NEB_NOTIFY_MAX_CHIMES:-5}"
    set_value scaling     "${NEB_NOTIFY_SCALING:-per-minute}"
else
    for py in python3 python; do
        if command -v "$py" >/dev/null 2>&1; then
            OUT=$(PYTHONIOENCODING=utf-8 "$py" "$HERE/lib/notify_sound.py" config notify-on-stop 2>/dev/null)
            # Sin `break` incondicional: un alias que no corre Python (el de la Microsoft Store en
            # Git Bash) no imprime nada y se prueba el siguiente.
            [ -z "$OUT" ] && continue
            while IFS='=' read -r key value; do
                set_value "$key" "${value%$'\r'}"
            done <<EOF
$OUT
EOF
            break
        fi
    done
fi

[ "$ENABLED" != "true" ] && exit 0

# Normalización (red de seguridad: notify_sound.py ya entrega los valores normalizados)
case "$MIN_SEC" in ''|*[!0-9-]*) MIN_SEC=10 ;; esac
[ "$MIN_SEC" -lt 0 ] 2>/dev/null && MIN_SEC=0
case "$MAX_CHIMES" in ''|*[!0-9]*) MAX_CHIMES=5 ;; esac
[ "$MAX_CHIMES" -lt 1  ] 2>/dev/null && MAX_CHIMES=1
[ "$MAX_CHIMES" -gt 20 ] 2>/dev/null && MAX_CHIMES=20
[ "$SCALING" != "fixed" ] && [ "$SCALING" != "per-minute" ] && SCALING="per-minute"

[ -z "$WAV" ] && WAV="$HERE/sounds/neb-chime.wav"
[ ! -f "$WAV" ] && exit 0

HAVE_JQ=0
command -v jq >/dev/null 2>&1 && HAVE_JQ=1

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
