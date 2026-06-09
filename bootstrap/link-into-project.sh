#!/usr/bin/env bash
set -euo pipefail

# ── DEPRECADO (v2.0.0): modelo "clone" ──────────────────────────────────────
# Neb se distribuye como PLUGIN de Claude Code. El arranque lo inyecta el hook
# SessionStart (no hace falta inyectar @imports en el CLAUDE.md del proyecto).
# Este script (modelo clone legacy) NO es necesario. Se conserva para referencia.
# Adopcion vigente: docs/user-guide.md (/plugin marketplace add + /plugin install).
# ────────────────────────────────────────────────────────────────────────────

# link-into-project.sh <ruta-proyecto>
# Engancha un proyecto al framework neb:
#  - Detecta el stack
#  - Crea/actualiza CLAUDE.md con imports
#  - Crea .claude/settings.json con hooks
#  - Crea changes/ versionada
#  - Añade .claude/personal.md a .gitignore

PROJECT="${1:-}"
if [ -z "$PROJECT" ] || [ ! -d "$PROJECT" ]; then
  echo "Uso: $0 <ruta-proyecto>"
  exit 1
fi

GUIDE_DIR="${NEB_HOME:-$HOME/.claude/neb}"
PROJECT="$(cd "$PROJECT" && pwd)"

# ---------------------------------------------------------------------------
# Private overlay hooks (stubs — overridden by sourcing detect-stack.local.sh)
# ---------------------------------------------------------------------------
detect_stack_local()   { echo "unknown"; }
get_private_stack_imports() { :; }          # prints nothing by default
get_framework_imports() {
  echo "@~/.claude/neb/general/startup.md"
  echo "@~/.claude/neb/workflow/index.md"
}

# Source the private overlay if present — generic discovery, no hardcoded name.
# NEB_WORKSPACE = the governance root (contains neb/ + your overlay). Fallbacks:
# dirname(NEB_HOME), then this script's grandparent dir.
_WS="${NEB_WORKSPACE:-$(dirname "${NEB_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}")}"
_ov_used=""
for _ov in "$_WS"/*/overlays/detect-stack.local.sh; do
  [ -f "$_ov" ] || continue          # no match → glob stays literal → skip
  if [ -n "$_ov_used" ]; then
    echo "  aviso: overlay múltiple; usando $_ov_used (ignorado: $_ov)" >&2
    break
  fi
  # shellcheck source=/dev/null
  source "$_ov"; _ov_used="$_ov"
done
unset _WS _ov _ov_used

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
info() { printf "  %s\n" "$*"; }
ok()   { printf "  \033[32m%s\033[0m\n" "$*"; }

bold "Linking $PROJECT"

# 1. Detectar stack
detect_stack() {
  # Overlay: stack-authoring — edición de un stack bajo el checkout de neb (neb/stacks/<X>/)
  if echo "$PROJECT" | grep -qE '/neb/stacks/[^/]+(/|$)'; then
    echo "stack-authoring"; return
  fi
  # Overlay: skill-authoring — edición de un skill bajo el checkout de neb (neb/skills/<X>/)
  if echo "$PROJECT" | grep -qE '/neb/skills/[^/]+(/|$)'; then
    echo "skill-authoring"; return
  fi
  # Stack self-applied — repo neb (indicadores estructurales)
  if [ -f "$PROJECT/methodology/principles.md" ] && [ -f "$PROJECT/process/plan-review.md" ] && [ -f "$PROJECT/general/index.md" ]; then
    echo "self-applied"; return
  fi
  # Fall through to private overlay detection
  local _priv
  _priv=$(detect_stack_local)
  if [ "$_priv" != "unknown" ]; then
    echo "$_priv"; return
  fi
  echo "unknown"
}

STACK=$(detect_stack)
bold "Stack detectado: $STACK"

if [ "$STACK" = "unknown" ]; then
  info "No se detectó un stack soportado. Saltando imports de stack."
fi

# 2. CLAUDE.md
bold "CLAUDE.md"
CLAUDE_FILE="$PROJECT/CLAUDE.md"
PROJECT_NAME="$(basename "$PROJECT")"

IMPORTS=()
while IFS= read -r _imp; do IMPORTS+=("$_imp"); done < <(get_framework_imports)

# Opt-out de stack: si el proyecto ya declaró `neb-stack: none` en su CLAUDE.md,
# respetar ese marcador y NO inyectar imports de stack (ver general/stack-detection.md
# "Opt-out de stack / Neb"). link-into-project.sh es el 2º consumidor de la detección.
OPT_OUT_STACK=0
if [ -f "$CLAUDE_FILE" ] && grep -qiE 'neb-stack:[[:space:]]*none' "$CLAUDE_FILE"; then
  OPT_OUT_STACK=1
  info "Opt-out detectado (neb-stack: none) — no se inyectan imports de stack."
fi

if [ "$STACK" != "unknown" ] && [ "$OPT_OUT_STACK" -eq 0 ]; then
  _priv=$(get_private_stack_imports "$STACK")
  if [ -n "$_priv" ]; then
    while IFS= read -r _imp; do IMPORTS+=("$_imp"); done <<< "$_priv"
  else
    IMPORTS+=("@~/.claude/neb/stacks/$STACK/index.md")
    if [ -f "$GUIDE_DIR/stacks/$STACK/servers.md" ]; then
      IMPORTS+=("@~/.claude/neb/stacks/$STACK/servers.md")
    fi
  fi
fi

if [ ! -f "$CLAUDE_FILE" ]; then
  {
    echo "# CLAUDE.md — $PROJECT_NAME"
    echo ""
    echo "## Metodología (no editar — proviene del framework neb)"
    echo ""
    for line in "${IMPORTS[@]}"; do echo "$line"; done
    echo ""
    echo "<!-- @./.claude/personal.md  (gitignored, descomentar si tienes uno) -->"
    echo ""
    echo "---"
    echo ""
    echo "## Proyecto $PROJECT_NAME"
    echo ""
    echo "<!-- Documenta aquí lo específico de este proyecto: stack, BD, módulos, convenciones particulares. -->"
    echo ""
  } > "$CLAUDE_FILE"
  ok "Creado $CLAUDE_FILE"
else
  MISSING=()
  for line in "${IMPORTS[@]}"; do
    if grep -qF "$line" "$CLAUDE_FILE"; then
      info "Ya presente: $line"
    else
      MISSING+=("$line")
    fi
  done
  if [ ${#MISSING[@]} -gt 0 ]; then
    tmp=$(mktemp)
    {
      for line in "${MISSING[@]}"; do echo "$line"; done
      cat "$CLAUDE_FILE"
    } > "$tmp"
    mv "$tmp" "$CLAUDE_FILE"
    for line in "${MISSING[@]}"; do
      ok "Añadido al header: $line"
    done
  fi
fi

# 3. .claude/settings.json
bold ".claude/settings.json"
mkdir -p "$PROJECT/.claude"
SETTINGS="$PROJECT/.claude/settings.json"
if [ -f "$SETTINGS" ]; then
  info "Ya existe — no se sobreescribe. Revisa manualmente si necesitas mergear hooks."
else
  cp "$GUIDE_DIR/templates/claude-settings.json.template" "$SETTINGS"
  ok "Creado $SETTINGS"
fi

# 4. changes/
bold "changes/ (carpeta versionada)"
if [ -d "$PROJECT/changes" ]; then
  ok "Ya existe"
else
  mkdir -p "$PROJECT/changes"
  touch "$PROJECT/changes/.gitkeep"
  ok "Creado $PROJECT/changes/ con .gitkeep"
fi

# 5. .gitignore
bold ".gitignore"
GITIGNORE="$PROJECT/.gitignore"
ENTRIES=(
  ".claude/personal.md"
  ".claude/settings.local.json"
)
[ -f "$GITIGNORE" ] || touch "$GITIGNORE"
for entry in "${ENTRIES[@]}"; do
  if grep -qxF "$entry" "$GITIGNORE"; then
    info "Ya presente en .gitignore: $entry"
  else
    echo "$entry" >> "$GITIGNORE"
    ok "Añadido a .gitignore: $entry"
  fi
done

bold "Listo"
info "Próximos pasos en $PROJECT:"
info "  - Revisar y commitear changes/.gitkeep, .claude/settings.json, CLAUDE.md, .gitignore"
info "  - Comenzar a guardar requerimientos en changes/<YYYY-MM-DD>-<nombre>.md"
