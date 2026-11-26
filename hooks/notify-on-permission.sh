#!/usr/bin/env bash
# notify-on-permission.sh — Notification hook: reproduce un WAV cuando Claude
# pide permiso para una herramienta o el prompt input lleva idle > 60s.
#
# Opt-in personal. Lineamiento: tooling/notify-on-permission.md.
# Defaults: 1 chime fijo. Sin scaling, sin walk-back de transcript.
# Configurable en la sección notify.permission del config.json de la carpeta de datos de Neb
# (enabled, wav).
#
# Guard de subsesión interna del corrector (preprocess-prompt.py): si
# NEB_INTERNAL_SUBSESSION=1 (o el alias legacy CLAUDE_PREPROCESS_RECURSION=1),
# abandona sin sonar — evita chime fantasma. Ver hooks/lib/subsession.py.
#
# Requisitos: bash, un player (afplay/paplay/aplay/play). Sin
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

# --- Config efectiva --------------------------------------------------------

# Un solo resolvedor (lib/notify_sound.py) lee la sección notify.permission de config.json en la carpeta
# de datos de Neb y resuelve el WAV (presets, ruta absoluta, respaldo). Bajo el despachador del plugin
# llegan ya resueltos en NEB_NOTIFY_ENABLED y NEB_NOTIFY_WAV (esta marca que vienen de él); invocado
# directo (entradas de settings.json anteriores a 6.15.0) se le piden a su CLI `config`, en líneas
# llave=valor. Sin Python: encendido y el sonido de neb.
HERE="$(cd "$(dirname "$0")" && pwd)"
ENABLED=true
WAV=""

if [ -n "${NEB_NOTIFY_WAV:-}" ]; then
    ENABLED="${NEB_NOTIFY_ENABLED:-true}"
    WAV="$NEB_NOTIFY_WAV"
else
    for py in python3 python; do
        if command -v "$py" >/dev/null 2>&1; then
            OUT=$(PYTHONIOENCODING=utf-8 "$py" "$HERE/lib/notify_sound.py" config notify-on-permission 2>/dev/null)
            # Sin `break` incondicional: un alias que no corre Python (el de la Microsoft Store en
            # Git Bash) no imprime nada y se prueba el siguiente.
            [ -z "$OUT" ] && continue
            while IFS='=' read -r key value; do
                value="${value%$'\r'}"
                case "$key" in
                    enabled) ENABLED="$value" ;;
                    wav)     WAV="$value" ;;
                esac
            done <<EOF
$OUT
EOF
            break
        fi
    done
fi

[ "$ENABLED" != "true" ] && exit 0

[ -z "$WAV" ] && WAV="$HERE/sounds/neb-chime.wav"
[ ! -f "$WAV" ] && exit 0

# --- 1 chime async ----------------------------------------------------------

(
    "$PLAYER" "$WAV" >/dev/null 2>&1
) &
disown 2>/dev/null

exit 0
