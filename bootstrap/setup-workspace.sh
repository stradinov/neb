#!/usr/bin/env bash
set -euo pipefail

# setup-workspace.sh — crea/configura el WORKSPACE del adoptante de Neb y lo conecta.
#
# El NUCLEO (neb) vive aparte: bajo plugin en ${CLAUDE_PLUGIN_ROOT}; en clone, en $NEB_HOME.
# Este script crea el workspace del adoptante (overlay + personal + changes + overlay/startup.md)
# y setea NEB_HOME/NEB_WORKSPACE en ~/.claude/settings.json (via set-neb-env.py) y en el shell profile.
# NEB_HOME y NEB_WORKSPACE son independientes (no se exige que uno contenga al otro).
#
# Ubicacion del workspace (carpeta neb_workspace) — 3 modos:
#   (default)          <cwd>/neb_workspace
#   --base <dir>       <dir>/neb_workspace
#   --existing <dir>   conecta NEB_WORKSPACE a <dir> ya existente (no crea estructura;
#                      si crea personal/<usuario>.md si falta)
#
# Auto-deteccion: en modo default y --dry-run, si la raiz actual (git toplevel o cwd) ya es
# un workspace (markers: */overlays/detect-profile.local.sh — el mismo glob que usa
# neb-bootstrap-context.py en runtime — o <overlay>/startup.md), lo reporta y sugiere
# --existing en vez de crear uno adentro.
# Si la raiz actual NO es workspace y no se paso --base, barre $HOME (una pasada de find,
# podando ocultos/node_modules/AppData/*.bak) buscando el mismo marker y lista lo encontrado
# en vez de crear a ciegas (nivel 2a de la cascada de /wakeup).
#
# Opciones: --overlay <nombre> (default: overlay) · --dry-run (no escribe)
#
# NEB_HOME se determina: ${CLAUDE_PLUGIN_ROOT} (plugin) > $NEB_HOME (env) > el dir padre de este script.
# NEB_HOME NO se persiste cuando resuelve al cache del plugin (path version-specific).

MODE="create"
BASE=""
EXISTING=""
OVERLAY_NAME="overlay"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="${2:?--base requiere un dir}"; shift 2 ;;
    --existing) MODE="existing"; EXISTING="${2:?--existing requiere un dir}"; shift 2 ;;
    --overlay) OVERLAY_NAME="${2:?--overlay requiere un nombre}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opcion desconocida: $1" >&2; exit 1 ;;
  esac
done

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m%s\033[0m\n" "$*"; }
info() { printf "  %s\n" "$*"; }
warn() { printf "  \033[33m%s\033[0m\n" "$*"; }

# Resolver de Python: primer interprete que existe Y corre. Rechaza el stub python3
# del Microsoft Store en Windows (existe en PATH pero no ejecuta) cayendo a python/py.
neb_python() {
  local c
  for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c '' >/dev/null 2>&1; then
      printf '%s\n' "$c"; return 0
    fi
  done
  return 1
}

# 1. NEB_HOME (nucleo)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEB_HOME_VAL="${CLAUDE_PLUGIN_ROOT:-${NEB_HOME:-$(dirname "$SCRIPT_DIR")}}"
NEB_HOME_VAL="$(cd "$NEB_HOME_VAL" 2>/dev/null && pwd || echo "$NEB_HOME_VAL")"
bold "NEB_HOME (nucleo): $NEB_HOME_VAL"

# 2. Resolver el workspace
# _is_workspace: markers estructurales de un workspace de Neb (mismo criterio que el
# discovery del overlay en neb-bootstrap-context.py — si el marker esta, el hook inyecta).
_is_workspace() {
  local d="$1"
  compgen -G "$d/*/overlays/detect-profile.local.sh" > /dev/null 2>&1 && return 0
  [ -f "$d/overlay/startup.md" ] && return 0
  return 1
}

if [ "$MODE" = "existing" ]; then
  [ -d "$EXISTING" ] || { echo "El dir no existe: $EXISTING" >&2; exit 1; }
  WS="$(cd "$EXISTING" && pwd)"
  bold "NEB_WORKSPACE (conectar workspace existente): $WS"
  _is_workspace "$WS" || warn "El dir no tiene markers de workspace (*/overlays/detect-profile.local.sh) — el hook no encontrara overlay que inyectar."
else
  # Auto-deteccion: no crear un workspace adentro de uno existente
  DETECT_ROOT="${BASE:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
  DETECT_ROOT="$(cd "$DETECT_ROOT" 2>/dev/null && pwd || echo "$DETECT_ROOT")"
  if _is_workspace "$DETECT_ROOT"; then
    bold "Workspace existente detectado en: $DETECT_ROOT"
    info "marker: $(ls -d "$DETECT_ROOT"/*/overlays/detect-profile.local.sh 2>/dev/null | head -1 || echo "$DETECT_ROOT/overlay/startup.md")"
    info "Conectalo:  bash $0 --existing \"$DETECT_ROOT\""
    info "O crea en otra parte:  bash $0 --base <otro-dir>"
    [ "$DRY_RUN" -eq 1 ] && info "(dry-run: no se escribio nada)"
    exit 0
  fi

  # Nivel 2a: barrido acotado bajo $HOME (solo modo default sin --base; --base = intencion
  # explicita y salta el barrido). Una pasada de find hasta el marker (raiz del workspace a
  # profundidad <=3 de $HOME), podando ocultos, node_modules, AppData y *.bak.
  _scan_workspaces() {
    find "$HOME" -maxdepth 5 \
      \( -name '.*' -o -name node_modules -o -name AppData -o -name '*.bak' \) -prune -o \
      -type f -path '*/overlays/detect-profile.local.sh' -print 2>/dev/null \
    | while IFS= read -r f; do
        dirname "$(dirname "$(dirname "$f")")"
      done | sort -u
  }
  if [ -z "$BASE" ]; then
    FOUND="$(_scan_workspaces || true)"
    if [ -n "$FOUND" ]; then
      N="$(printf '%s\n' "$FOUND" | wc -l | tr -d '[:space:]')"
      bold "Workspace(s) existente(s) encontrado(s) bajo \$HOME ($N):"
      printf '%s\n' "$FOUND" | while IFS= read -r w; do info "$w"; done
      info "Conectalo:  bash $0 --existing \"<dir>\""
      info "O crea uno nuevo en otra parte:  bash $0 --base <otro-dir>"
      [ "$DRY_RUN" -eq 1 ] && info "(dry-run: no se escribio nada)"
      exit 0
    fi
  fi

  BASE_DIR="${BASE:-$(pwd)}"
  WS="$BASE_DIR/neb_workspace"
  bold "NEB_WORKSPACE (crear): $WS"
fi

# 3. Scaffolding (solo en modo create)
if [ "$MODE" = "create" ]; then
  bold "Scaffolding del workspace"
  if [ "$DRY_RUN" -eq 1 ]; then
    info "[dry-run] crearia: $OVERLAY_NAME/overlays/detect-profile.local.sh, $OVERLAY_NAME/startup.md, personal/, changes/"
  else
    mkdir -p "$WS/$OVERLAY_NAME/overlays" "$WS/personal" "$WS/changes"
    [ -f "$WS/changes/.gitkeep" ] || touch "$WS/changes/.gitkeep"
    if [ ! -f "$WS/$OVERLAY_NAME/overlays/detect-profile.local.sh" ]; then
      cat > "$WS/$OVERLAY_NAME/overlays/detect-profile.local.sh" <<'OV'
#!/usr/bin/env bash
# detect-profile.local.sh — overlay privado del adoptante. Sobreescribi estas funciones
# para tus profiles de dominio. El archivo es ademas el marker estructural del workspace
detect_profile_local()        { echo "unknown"; }   # devolve el nombre de tu profile segun $PROJECT
get_private_profile_imports() { :; }                 # imprimi los @-imports de tu profile privado
OV
      ok "$OVERLAY_NAME/overlays/detect-profile.local.sh (stub)"
    fi
    # overlay/startup.md (D1): arranque del overlay, lo consume el hook SessionStart de neb
    if [ ! -f "$WS/$OVERLAY_NAME/startup.md" ]; then
      cat > "$WS/$OVERLAY_NAME/startup.md" <<'OV'
# Arranque del overlay

<!-- El hook SessionStart de Neb ensambla este archivo DESPUES del arranque del framework.
     Importa aqui (via @relative.md, paths relativos a este archivo) los lineamientos propios
     de tu overlay que deben cargarse al inicio de cada sesion. Si tu overlay no tiene arranque
     propio todavia, deja este archivo minimo. -->
OV
      ok "$OVERLAY_NAME/startup.md (D1)"
    fi
    ok "personal/ + changes/"
  fi
fi

# 4. personal/<username>.md (username del SO; mismo lookup que el hook SessionStart)
#    Aplica en create Y en existing — un miembro que conecta el workspace del equipo
#    necesita su personal/<usuario>.md aunque la estructura ya exista.
USER_NAME="${CLAUDE_PLUGIN_OPTION_USERNAME:-${USER:-${USERNAME:-}}}"
if [ -n "$USER_NAME" ] && [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$WS/personal"
  PERSONAL="$WS/personal/$USER_NAME.md"
  if [ ! -f "$PERSONAL" ]; then
    TPL="$NEB_HOME_VAL/templates/personal.md.template"
    if [ -f "$TPL" ]; then
      sed "s/<USUARIO>/$USER_NAME/g; s/<usuario>/$USER_NAME/g" "$TPL" > "$PERSONAL" 2>/dev/null || cp "$TPL" "$PERSONAL"
    else
      printf '# Personal — %s\n\n## Atajos personales\n\n## Preferencias de comunicacion\n\n## Notas privadas\n' "$USER_NAME" > "$PERSONAL"
    fi
    ok "personal/$USER_NAME.md"
  else
    info "personal/$USER_NAME.md ya existe"
  fi
elif [ -z "$USER_NAME" ]; then
  warn "Sin username (USER/USERNAME) — no creo personal/<username>.md. Re-corre con el username seteado."
fi

# 5. Conectar variables en settings.json (helper).
#    NEB_HOME NO se persiste cuando resuelve al cache del plugin y el usuario no lo tenia
#    en env: el path del cache es version-specific y, por la precedencia D4
#    (NEB_HOME > CLAUDE_PLUGIN_ROOT), quedaria sombreando al plugin tras un update.
PERSIST_NEB_HOME=1
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -z "${NEB_HOME:-}" ]; then
  PERSIST_NEB_HOME=0
fi

bold "Conectando variables en ~/.claude/settings.json"
ENV_ARGS=("NEB_WORKSPACE=$WS")
[ "$PERSIST_NEB_HOME" -eq 1 ] && ENV_ARGS=("NEB_HOME=$NEB_HOME_VAL" "${ENV_ARGS[@]}")
if [ "$DRY_RUN" -eq 1 ]; then
  info "[dry-run] set-neb-env.py ${ENV_ARGS[*]}"
  [ "$PERSIST_NEB_HOME" -eq 0 ] && info "[dry-run] NEB_HOME no se persiste (resuelve al cache del plugin)"
else
  PYBIN="$(neb_python || true)"
  if [ -n "$PYBIN" ]; then
    "$PYBIN" "$NEB_HOME_VAL/bootstrap/set-neb-env.py" "${ENV_ARGS[@]}" \
      || warn "No se pudo actualizar settings.json (revisa $PYBIN). Setea NEB_WORKSPACE a mano en ~/.claude/settings.json."
  else
    warn "No encontre Python (probe python3/python/py). Setea NEB_WORKSPACE a mano en ~/.claude/settings.json."
  fi
  [ "$PERSIST_NEB_HOME" -eq 0 ] && info "NEB_HOME no se persiste (el plugin resuelve su propio path en cada sesion)"
fi

# El shell profile ya no se edita (settings.json basta para las sesiones de Claude Code).
# Para correr hooks/scripts de neb en shells sueltas, exporta a mano si lo necesitas:
info "Exports opcionales para shells fuera de Claude Code:"
[ "$PERSIST_NEB_HOME" -eq 1 ] && info "  export NEB_HOME=\"$NEB_HOME_VAL\""
info "  export NEB_WORKSPACE=\"$WS\""

bold "Listo"
info "NEB_HOME=$NEB_HOME_VAL"
info "NEB_WORKSPACE=$WS"
info "Abri una sesion nueva de Claude Code para que el hook tome el workspace."
if [ "$DRY_RUN" -eq 1 ]; then info "(dry-run: no se escribio nada)"; fi
