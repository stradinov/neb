#!/usr/bin/env bash
# notify-on-permission.sh — Notification hook: reproduce un WAV cuando Claude
# pide permiso para una herramienta o el prompt input lleva idle > 60s.
#
# Opt-in personal. Lineamiento: tooling/notify-on-permission.md.
# Defaults: 1 chime fijo. Sin scaling, sin walk-back de transcript.
# Configurable en ~/.claude/notify-on-permission.json (enabled, wav).
#
# Guard de subsesión interna del corrector (preprocess-prompt.py): si
# NEB_INTERNAL_SUBSESSION=1 (o el alias legacy CLAUDE_PREPROCESS_RECURSION=1),
# abandona sin sonar — evita chime fantasma. Ver hooks/lib/subsession.py.
#
# Requisitos: bash, jq (blando), un player (afplay/paplay/aplay/play). Sin
# player en PATH → exit 0 silencioso. Defensivo: cualquier falla → exit 0.

set +e

if [ "${NEB_INTERNAL_SUBSESSION:-}" = "1" ] || [ "${CLAUDE_PREPROCESS_RECURSION:-}" = "1" ]; then exit 0; fi

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

# --- Cargar config personal -------------------------------------------------

CFG="$HOME/.claude/notify-on-permission.json"
HAVE_JQ=0
command -v jq >/dev/null 2>&1 && HAVE_JQ=1

if [ -f "$CFG" ] && [ "$HAVE_JQ" = "1" ]; then
    if jq empty "$CFG" >/dev/null 2>&1; then
        ENABLED=$(jq -r 'if has("enabled") then .enabled else true end' "$CFG")
    else
        log "config ilegible, usando defaults"
    fi
fi

[ "$ENABLED" != "true" ] && exit 0

# --- Resolver WAV -----------------------------------------------------------

# Un solo resolvedor (lib/notify_sound.py): presets, ruta absoluta y respaldo. Bajo el
# despachador del plugin llega resuelto en NEB_NOTIFY_WAV; invocado directo (entradas de
# settings.json anteriores a 6.15.0) se le pregunta a su CLI. Sin Python, el sonido de neb.
HERE="$(cd "$(dirname "$0")" && pwd)"
WAV="${NEB_NOTIFY_WAV:-}"
if [ -z "$WAV" ]; then
    for py in python3 python; do
        if command -v "$py" >/dev/null 2>&1; then
            # Sin `break` incondicional: un alias que no corre Python (el de la Microsoft Store en
            # Git Bash) no imprime nada y se prueba el siguiente.
            OUT=$(PYTHONIOENCODING=utf-8 "$py" "$HERE/lib/notify_sound.py" notify-on-permission 2>/dev/null)
            # 3 = el dev apagó el hook en su JSON (sin jq, este script no lee `enabled`).
            [ "$?" = "3" ] && exit 0
            WAV=$(printf '%s\n' "$OUT" | head -n 1)
            [ -n "$WAV" ] && break
        fi
    done
fi
[ -z "$WAV" ] && WAV="$HERE/sounds/neb-chime.wav"
[ ! -f "$WAV" ] && exit 0

# --- 1 chime async ----------------------------------------------------------

(
    "$PLAYER" "$WAV" >/dev/null 2>&1
) &
disown 2>/dev/null

exit 0
