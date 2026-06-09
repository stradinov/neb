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
#   --existing <dir>   reconecta NEB_WORKSPACE a <dir> ya existente (no crea estructura)
#
# Opciones: --overlay <nombre> (default: overlay) · --dry-run (no escribe)
#
# NEB_HOME se determina: ${CLAUDE_PLUGIN_ROOT} (plugin) > $NEB_HOME (env) > el dir padre de este script.

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

# 1. NEB_HOME (nucleo)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEB_HOME_VAL="${CLAUDE_PLUGIN_ROOT:-${NEB_HOME:-$(dirname "$SCRIPT_DIR")}}"
NEB_HOME_VAL="$(cd "$NEB_HOME_VAL" 2>/dev/null && pwd || echo "$NEB_HOME_VAL")"
bold "NEB_HOME (nucleo): $NEB_HOME_VAL"

# 2. Resolver el workspace
if [ "$MODE" = "existing" ]; then
  [ -d "$EXISTING" ] || { echo "El dir no existe: $EXISTING" >&2; exit 1; }
  WS="$(cd "$EXISTING" && pwd)"
  bold "NEB_WORKSPACE (reconectar, sin crear estructura): $WS"
else
  BASE_DIR="${BASE:-$(pwd)}"
  WS="$BASE_DIR/neb_workspace"
  bold "NEB_WORKSPACE (crear): $WS"
fi

# 3. Scaffolding (solo en modo create)
if [ "$MODE" = "create" ]; then
  bold "Scaffolding del workspace"
  if [ "$DRY_RUN" -eq 1 ]; then
    info "[dry-run] crearia: $OVERLAY_NAME/overlays/detect-stack.local.sh, $OVERLAY_NAME/startup.md, personal/, changes/"
  else
    mkdir -p "$WS/$OVERLAY_NAME/overlays" "$WS/personal" "$WS/changes"
    [ -f "$WS/changes/.gitkeep" ] || touch "$WS/changes/.gitkeep"
    if [ ! -f "$WS/$OVERLAY_NAME/overlays/detect-stack.local.sh" ]; then
      cat > "$WS/$OVERLAY_NAME/overlays/detect-stack.local.sh" <<'OV'
#!/usr/bin/env bash
# detect-stack.local.sh — overlay privado del adoptante. Sobreescribi estas funciones
# para tus stacks de dominio (sourced por neb/bootstrap/link-into-project.sh).
detect_stack_local()        { echo "unknown"; }   # devolve el nombre de tu stack segun $PROJECT
get_private_stack_imports() { :; }                 # imprimi los @-imports de tu stack privado
OV
      ok "$OVERLAY_NAME/overlays/detect-stack.local.sh (stub)"
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

# 4. personal/<username>.md (username de userConfig del plugin, o del SO)
USER_NAME="${CLAUDE_PLUGIN_OPTION_USERNAME:-${USER:-${USERNAME:-}}}"
if [ -n "$USER_NAME" ] && [ "$MODE" = "create" ] && [ "$DRY_RUN" -eq 0 ]; then
  PERSONAL="$WS/personal/$USER_NAME.md"
  if [ ! -f "$PERSONAL" ]; then
    TPL="$NEB_HOME_VAL/templates/personal.md.template"
    if [ -f "$TPL" ]; then
      sed "s/<USUARIO>/$USER_NAME/g; s/<usuario>/$USER_NAME/g" "$TPL" > "$PERSONAL" 2>/dev/null || cp "$TPL" "$PERSONAL"
    else
      printf '# Personal — %s\n\n## Atajos personales\n\n## Preferencias de comunicacion\n\n## Notas privadas\n' "$USER_NAME" > "$PERSONAL"
    fi
    ok "personal/$USER_NAME.md"
  fi
elif [ -z "$USER_NAME" ] && [ "$MODE" = "create" ]; then
  warn "Sin username (userConfig/USER/USERNAME) — no creo personal/<username>.md. Re-corre con el username seteado."
fi

# 5. Conectar variables: settings.json (helper) + shell profile
bold "Conectando NEB_HOME + NEB_WORKSPACE"
if [ "$DRY_RUN" -eq 1 ]; then
  info "[dry-run] set-neb-env.py NEB_HOME=$NEB_HOME_VAL NEB_WORKSPACE=$WS"
else
  python "$NEB_HOME_VAL/bootstrap/set-neb-env.py" "NEB_HOME=$NEB_HOME_VAL" "NEB_WORKSPACE=$WS" \
    || warn "No se pudo actualizar settings.json (revisa python). Seteá NEB_WORKSPACE a mano en ~/.claude/settings.json."
fi

PROFILE=""
for cand in "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile"; do
  [ -f "$cand" ] && { PROFILE="$cand"; break; }
done
if [ -z "$PROFILE" ]; then
  warn "Sin shell profile; agregá a mano: export NEB_HOME=\"$NEB_HOME_VAL\"; export NEB_WORKSPACE=\"$WS\""
elif [ "$DRY_RUN" -eq 1 ]; then
  info "[dry-run] actualizaria $PROFILE con NEB_HOME/NEB_WORKSPACE"
elif grep -qF "export NEB_WORKSPACE=\"$WS\"" "$PROFILE" && grep -qF "export NEB_HOME=\"$NEB_HOME_VAL\"" "$PROFILE"; then
  ok "shell profile ya correcto ($PROFILE)"
else
  cp "$PROFILE" "$PROFILE.bak"
  grep -vE '^[[:space:]]*export[[:space:]]+(NEB_HOME|NEB_WORKSPACE)=' "$PROFILE" > "$PROFILE.tmp"
  { printf 'export NEB_HOME="%s"\n' "$NEB_HOME_VAL"; printf 'export NEB_WORKSPACE="%s"\n' "$WS"; } >> "$PROFILE.tmp"
  mv "$PROFILE.tmp" "$PROFILE"
  ok "shell profile actualizado ($PROFILE, backup .bak)"
fi

bold "Listo"
info "NEB_HOME=$NEB_HOME_VAL"
info "NEB_WORKSPACE=$WS"
[ "$DRY_RUN" -eq 1 ] && info "(dry-run: no se escribio nada)"
