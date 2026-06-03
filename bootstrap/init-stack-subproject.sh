#!/usr/bin/env bash
set -euo pipefail

# init-stack-subproject.sh <nombre-stack> [--overlay-base self-applied|none]
# Inicializa un stack nuevo bajo stacks/<nombre>/ con los 6 archivos mínimos
# desde las plantillas en stacks/stack-authoring/templates/.
#
# Pre-condición: ejecutar desde la raíz del repo neb,
#                o setear NEB_HOME para localizar el repo.

STACK_NAME="${1:-}"
OVERLAY_BASE="none"

if [ -z "$STACK_NAME" ]; then
  echo "Uso: $0 <nombre-stack> [--overlay-base self-applied|none]"
  echo "  Ejemplo: $0 node-api --overlay-base none"
  echo "  Ejemplo: $0 react-native --overlay-base none"
  echo "  Ejemplo: $0 my-workflow-stack --overlay-base self-applied"
  exit 1
fi

# Parsear flag opcional
shift
while [ $# -gt 0 ]; do
  case "$1" in
    --overlay-base)
      OVERLAY_BASE="${2:-none}"
      shift 2
      ;;
    *)
      echo "Argumento desconocido: $1"
      exit 1
      ;;
  esac
done

GUIDE_DIR="${NEB_HOME:-$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/.claude/neb")}"
TEMPLATES_DIR="$GUIDE_DIR/stacks/stack-authoring/templates"
STACK_DIR="$GUIDE_DIR/stacks/$STACK_NAME"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
info() { printf "  %s\n" "$*"; }
ok()   { printf "  \033[32m%s\033[0m\n" "$*"; }
warn() { printf "  \033[33m%s\033[0m\n" "$*"; }

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
  echo "  Verificar que GUIDE_DIR apunte al repo neb: $GUIDE_DIR"
  exit 1
fi

bold "Inicializando stack"
bold "  Nombre      : $STACK_NAME"
bold "  Overlay base: $OVERLAY_BASE"
bold "  Path        : $STACK_DIR"

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
bold "Checklist de acoples pendientes (completar manualmente):"
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
info "     - Entrada nueva + bump minor (o major si rompe imports)"
info ""
if [ "$OVERLAY_BASE" != "none" ]; then
  info "  7. general/stack-detection.md paso 0 (overlay por path)"
  info "     - Agregar mención del overlay si tiene prioridad máxima"
  info ""
fi
info "Ver procedimiento completo en methodology/stacks.md y convenciones en stacks/stack-authoring/conventions.md."
