#!/usr/bin/env bash
set -euo pipefail

# init-profile-subproject.sh <nombre-profile> [--overlay-base self-applied|none] [--core] [--dry-run]
# Inicializa un profile nuevo con los 6 archivos mínimos desde las plantillas en
# profiles/profile-authoring/templates/.
#
# Destino (importante):
#   - Por DEFECTO el profile se crea en el OVERLAY del adoptante
#     ($NEB_WORKSPACE/<overlay>/profiles/<nombre>), nunca dentro del núcleo neb.
#   - El MAINTAINER del framework usa --core para crear en neb/profiles/<nombre>
#     (el profile se publicará al núcleo vía git subtree push).
#   - --dry-run muestra el destino y lo que se crearía, sin escribir nada.
#
# Pre-condición: NEB_HOME apunta al checkout de neb (núcleo); NEB_WORKSPACE a la
# raíz de gobernanza (donde vive el overlay). Si no están seteadas, se derivan.

PROFILE_NAME="${1:-}"
OVERLAY_BASE="none"
TARGET="overlay"   # overlay (default, adoptante) | core (maintainer, --core)
DRY_RUN=0

if [ -z "$PROFILE_NAME" ]; then
  echo "Uso: $0 <nombre-profile> [--overlay-base self-applied|none] [--core] [--dry-run]"
  echo "  Ejemplo (adoptante): $0 node-api                 # → \$NEB_WORKSPACE/<overlay>/profiles/node-api"
  echo "  Ejemplo (maintainer): $0 react-native --core      # → neb/profiles/react-native"
  echo "  Ejemplo (dry-run): $0 my-profile --dry-run          # muestra el destino sin escribir"
  exit 1
fi

# Parsear flags opcionales
shift
while [ $# -gt 0 ]; do
  case "$1" in
    --overlay-base)
      OVERLAY_BASE="${2:-none}"
      shift 2
      ;;
    --core)
      TARGET="core"
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    *)
      echo "Argumento desconocido: $1"
      exit 1
      ;;
  esac
done

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
info() { printf "  %s\n" "$*"; }
ok()   { printf "  \033[32m%s\033[0m\n" "$*"; }
warn() { printf "  \033[33m%s\033[0m\n" "$*"; }

GUIDE_DIR="${NEB_HOME:-$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/.claude/neb")}"
TEMPLATES_DIR="$GUIDE_DIR/profiles/profile-authoring/templates"

# Resolver el directorio destino del profile según el TARGET.
if [ "$TARGET" = "core" ]; then
  PROFILE_DIR="$GUIDE_DIR/profiles/$PROFILE_NAME"
else
  # Overlay del adoptante: descubrir el dir de overlay bajo $NEB_WORKSPACE
  # (mismo patrón que setup-workspace.sh); fallback a "<workspace>/overlay".
  WS="${NEB_WORKSPACE:-$(dirname "$GUIDE_DIR")}"
  OVERLAY_DIR=""
  for _o in "$WS"/*/overlays/detect-profile.local.sh; do
    [ -f "$_o" ] || continue
    OVERLAY_DIR="$(dirname "$(dirname "$_o")")"
    break
  done
  if [ -z "$OVERLAY_DIR" ]; then
    OVERLAY_DIR="$WS/overlay"
    warn "No encontré un overlay preexistente bajo $WS — uso el fallback $OVERLAY_DIR (se creará). Si no es el destino esperado, montá tu overlay (wakeup/setup-workspace) o usá --core."
  fi
  PROFILE_DIR="$OVERLAY_DIR/profiles/$PROFILE_NAME"
fi

# Validar nombre (kebab-case, sin espacios, sin caracteres especiales)
if ! echo "$PROFILE_NAME" | grep -qE '^[a-z][a-z0-9-]+$'; then
  echo "Error: el nombre del profile debe ser kebab-case (solo letras minúsculas, números y guiones)."
  echo "  Ejemplo válido: react-native, python-ml, my-profile"
  exit 1
fi

# Verificar que el profile no existe ya
if [ -d "$PROFILE_DIR" ]; then
  warn "El directorio ya existe: $PROFILE_DIR"
  warn "Verificando artefactos faltantes..."
fi

# Verificar que existen los templates
if [ ! -d "$TEMPLATES_DIR" ]; then
  echo "Error: directorio de templates no encontrado: $TEMPLATES_DIR"
  echo "  Verificar que NEB_HOME apunte al checkout de neb: $GUIDE_DIR"
  exit 1
fi

bold "Inicializando profile"
bold "  Nombre      : $PROFILE_NAME"
bold "  Destino     : $([ "$TARGET" = "core" ] && echo 'núcleo (neb/profiles) — se publica al framework' || echo 'overlay del adoptante')"
bold "  Overlay base: $OVERLAY_BASE"
bold "  Path        : $PROFILE_DIR"

if [ "$DRY_RUN" -eq 1 ]; then
  echo ""
  bold "[dry-run] No se escribe nada. Se crearía:"
  info "$PROFILE_DIR/ con: index.md, deployment.md, conventions.md, troubleshooting.md, roles.md, skills.md"
  exit 0
fi

TODAY="$(date +%Y-%m-%d 2>/dev/null || echo "YYYY-MM-DD")"

mkdir -p "$PROFILE_DIR"

# Función para crear archivo desde template si no existe
create_from_template() {
  local TEMPLATE="$1"
  local DEST="$2"

  if [ ! -f "$DEST" ]; then
    cp "$TEMPLATE" "$DEST"
    # Sustituir placeholders
    sed -i "s/{{PROFILE_NAME}}/$PROFILE_NAME/g" "$DEST" 2>/dev/null || true
    sed -i "s/{{PROFILE_BASE}}/$OVERLAY_BASE/g" "$DEST" 2>/dev/null || true
    sed -i "s/{{FECHA}}/$TODAY/g" "$DEST" 2>/dev/null || true
    ok "Creado $(basename "$DEST")"
  else
    info "Ya existe: $(basename "$DEST")"
  fi
}

create_from_template "$TEMPLATES_DIR/index.md.template"         "$PROFILE_DIR/index.md"
create_from_template "$TEMPLATES_DIR/deployment.md.template"    "$PROFILE_DIR/deployment.md"
create_from_template "$TEMPLATES_DIR/conventions.md.template"   "$PROFILE_DIR/conventions.md"
create_from_template "$TEMPLATES_DIR/troubleshooting.md.template" "$PROFILE_DIR/troubleshooting.md"
create_from_template "$TEMPLATES_DIR/roles.md.template"         "$PROFILE_DIR/roles.md"
create_from_template "$TEMPLATES_DIR/skills.md.template"        "$PROFILE_DIR/skills.md"

bold "Listo — $PROFILE_DIR"
echo ""

if [ "$TARGET" = "overlay" ]; then
  bold "Checklist de acoples (overlay del adoptante):"
  info ""
  info "  1. <overlay>/overlays/detect-profile.local.sh"
  info "     - En detect_profile_local(): devolver \"$PROFILE_NAME\" según el path/contenido del proyecto"
  info "     - En get_private_profile_imports(): imprimir los @-imports de profiles/$PROFILE_NAME/index.md"
  info ""
  info "  2. profiles/$PROFILE_NAME/roles.md"
  info "     - Definir el rol principal del profile; heredar revisores del overlay o definir propios"
  info ""
  info "  3. Si el profile define revisores propios (subagentes):"
  info "     - Crear <overlay>/agents/<nombre>.md y registrarlo en tu instalador local de agents"
  info ""
  info "El profile NO se publica al núcleo neb. Vive solo en tu overlay."
else
  bold "Checklist de acoples (núcleo — se publica al framework):"
  info ""
  info "  1. profiles/index.md"
  info "     - Agregar fila en 'Disponibles': $PROFILE_NAME — descripción"
  info "     - Agregar fila en tabla 'Heurística de detección' con la prioridad correcta"
  info ""
  info "  2. general/profile-detection.md paso 0 (si es overlay por path)"
  info "     - Registrar la regla de path; mantener sincronía con profiles/index.md (mismo commit)"
  info ""
  info "  3. process/roles-invocation.md"
  info "     - Agregar fila en tabla 'Default por profile'"
  info "     - Agregar fila en matriz 'Cobertura mínima por fase'"
  info ""
  info "  4. process/delivery.md"
  info "     - Agregar fila en tabla 'Pre-ejecución de Fase 7 (gate de subagente)'"
  info ""
  info "  5. process/execution.md"
  info "     - Agregar fila en tabla 'Cierre de Fase 4 (gate de subagente)'"
  info ""
  info "  6. CHANGELOG.md"
  info "     - Fragment en changelog.d/<version>.md + bump minor (o major si rompe imports)"
  info ""
  if [ "$OVERLAY_BASE" != "none" ]; then
    info "  7. general/profile-detection.md paso 0 (overlay por path)"
    info "     - Agregar mención del overlay si tiene prioridad máxima"
    info ""
  fi
  info "Ver procedimiento completo en methodology/profiles.md y convenciones en profiles/profile-authoring/conventions.md."
fi
