#!/usr/bin/env bash
set -euo pipefail

# init-stack-subproject.sh <nombre-stack> [--overlay-base self-applied|none] [--core] [--dry-run]
# Inicializa un stack nuevo con los 6 archivos mínimos desde las plantillas en
# stacks/stack-authoring/templates/.
#
# Destino (importante):
#   - Por DEFECTO el stack se crea en el OVERLAY del adoptante
#     ($NEB_WORKSPACE/<overlay>/stacks/<nombre>), nunca dentro del núcleo neb.
#   - El MAINTAINER del framework usa --core para crear en neb/stacks/<nombre>
#     (el stack se publicará al núcleo vía git subtree push).
#   - --dry-run muestra el destino y lo que se crearía, sin escribir nada.
#
# Pre-condición: NEB_HOME apunta al checkout de neb (núcleo); NEB_WORKSPACE a la
# raíz de gobernanza (donde vive el overlay). Si no están seteadas, se derivan.

STACK_NAME="${1:-}"
OVERLAY_BASE="none"
TARGET="overlay"   # overlay (default, adoptante) | core (maintainer, --core)
DRY_RUN=0

if [ -z "$STACK_NAME" ]; then
  echo "Uso: $0 <nombre-stack> [--overlay-base self-applied|none] [--core] [--dry-run]"
  echo "  Ejemplo (adoptante): $0 node-api                 # → \$NEB_WORKSPACE/<overlay>/stacks/node-api"
  echo "  Ejemplo (maintainer): $0 react-native --core      # → neb/stacks/react-native"
  echo "  Ejemplo (dry-run): $0 my-stack --dry-run          # muestra el destino sin escribir"
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
TEMPLATES_DIR="$GUIDE_DIR/stacks/stack-authoring/templates"

# Resolver el directorio destino del stack según el TARGET.
if [ "$TARGET" = "core" ]; then
  STACK_DIR="$GUIDE_DIR/stacks/$STACK_NAME"
else
  # Overlay del adoptante: descubrir el dir de overlay bajo $NEB_WORKSPACE
  # (mismo patrón que setup-workspace.sh); fallback a "<workspace>/overlay".
  WS="${NEB_WORKSPACE:-$(dirname "$GUIDE_DIR")}"
  OVERLAY_DIR=""
  for _o in "$WS"/*/overlays/detect-stack.local.sh; do
    [ -f "$_o" ] || continue
    OVERLAY_DIR="$(dirname "$(dirname "$_o")")"
    break
  done
  if [ -z "$OVERLAY_DIR" ]; then
    OVERLAY_DIR="$WS/overlay"
    warn "No encontré un overlay preexistente bajo $WS — uso el fallback $OVERLAY_DIR (se creará). Si no es el destino esperado, montá tu overlay (wakeup/setup-workspace) o usá --core."
  fi
  STACK_DIR="$OVERLAY_DIR/stacks/$STACK_NAME"
fi

# Validar nombre (kebab-case, sin espacios, sin caracteres especiales)
if ! echo "$STACK_NAME" | grep -qE '^[a-z][a-z0-9-]+$'; then
  echo "Error: el nombre del stack debe ser kebab-case (solo letras minúsculas, números y guiones)."
  echo "  Ejemplo válido: react-native, python-ml, my-stack"
  exit 1
fi

# Verificar que el stack no existe ya
if [ -d "$STACK_DIR" ]; then
  warn "El directorio ya existe: $STACK_DIR"
  warn "Verificando artefactos faltantes..."
fi

# Verificar que existen los templates
if [ ! -d "$TEMPLATES_DIR" ]; then
  echo "Error: directorio de templates no encontrado: $TEMPLATES_DIR"
  echo "  Verificar que NEB_HOME apunte al checkout de neb: $GUIDE_DIR"
  exit 1
fi

bold "Inicializando stack"
bold "  Nombre      : $STACK_NAME"
bold "  Destino     : $([ "$TARGET" = "core" ] && echo 'núcleo (neb/stacks) — se publica al framework' || echo 'overlay del adoptante')"
bold "  Overlay base: $OVERLAY_BASE"
bold "  Path        : $STACK_DIR"

if [ "$DRY_RUN" -eq 1 ]; then
  echo ""
  bold "[dry-run] No se escribe nada. Se crearía:"
  info "$STACK_DIR/ con: index.md, deployment.md, conventions.md, troubleshooting.md, roles.md, skills.md"
  exit 0
fi

TODAY="$(date +%Y-%m-%d 2>/dev/null || echo "YYYY-MM-DD")"

mkdir -p "$STACK_DIR"

# Función para crear archivo desde template si no existe
create_from_template() {
  local TEMPLATE="$1"
  local DEST="$2"

  if [ ! -f "$DEST" ]; then
    cp "$TEMPLATE" "$DEST"
    # Sustituir placeholders
    sed -i "s/{{STACK_NAME}}/$STACK_NAME/g" "$DEST" 2>/dev/null || true
    sed -i "s/{{STACK_BASE}}/$OVERLAY_BASE/g" "$DEST" 2>/dev/null || true
    sed -i "s/{{FECHA}}/$TODAY/g" "$DEST" 2>/dev/null || true
    ok "Creado $(basename "$DEST")"
  else
    info "Ya existe: $(basename "$DEST")"
  fi
}

create_from_template "$TEMPLATES_DIR/index.md.template"         "$STACK_DIR/index.md"
create_from_template "$TEMPLATES_DIR/deployment.md.template"    "$STACK_DIR/deployment.md"
create_from_template "$TEMPLATES_DIR/conventions.md.template"   "$STACK_DIR/conventions.md"
create_from_template "$TEMPLATES_DIR/troubleshooting.md.template" "$STACK_DIR/troubleshooting.md"
create_from_template "$TEMPLATES_DIR/roles.md.template"         "$STACK_DIR/roles.md"
create_from_template "$TEMPLATES_DIR/skills.md.template"        "$STACK_DIR/skills.md"

bold "Listo — $STACK_DIR"
echo ""

if [ "$TARGET" = "overlay" ]; then
  bold "Checklist de acoples (overlay del adoptante):"
  info ""
  info "  1. <overlay>/overlays/detect-stack.local.sh"
  info "     - En detect_stack_local(): devolver \"$STACK_NAME\" según el path/contenido del proyecto"
  info "     - En get_private_stack_imports(): imprimir los @-imports de stacks/$STACK_NAME/index.md"
  info ""
  info "  2. stacks/$STACK_NAME/roles.md"
  info "     - Definir el rol principal del stack; heredar revisores del overlay o definir propios"
  info ""
  info "  3. Si el stack define revisores propios (subagentes):"
  info "     - Crear <overlay>/agents/<nombre>.md y registrarlo en tu instalador local de agents"
  info ""
  info "El stack NO se publica al núcleo neb. Vive solo en tu overlay."
else
  bold "Checklist de acoples (núcleo — se publica al framework):"
  info ""
  info "  1. stacks/index.md"
  info "     - Agregar fila en 'Disponibles': $STACK_NAME — descripción"
  info "     - Agregar fila en tabla 'Heurística de detección' con la prioridad correcta"
  info ""
  info "  2. bootstrap/link-into-project.sh función detect_stack"
  info "     - Agregar chequeo para el stack (overlay por path o heurística estructural)"
  info "     - Mantener sincronía con stacks/index.md (mismo commit)"
  info ""
  info "  3. process/roles-invocation.md"
  info "     - Agregar fila en tabla 'Default por stack'"
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
    info "  7. general/stack-detection.md paso 0 (overlay por path)"
    info "     - Agregar mención del overlay si tiene prioridad máxima"
    info ""
  fi
  info "Ver procedimiento completo en methodology/stacks.md y convenciones en stacks/stack-authoring/conventions.md."
fi
