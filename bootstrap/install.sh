#!/usr/bin/env bash
set -euo pipefail

# install.sh — corre una sola vez por máquina/usuario.
# Idempotente: detecta lo que ya existe y solo agrega lo que falta.

REPO_URL="${REPO_URL:-github.com/<org>/neb.git}"
GUIDE_DIR="${NEB_HOME:-$HOME/.claude/neb}"

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
info()  { printf "  %s\n" "$*"; }
warn()  { printf "  \033[33m%s\033[0m\n" "$*"; }
ok()    { printf "  \033[32m%s\033[0m\n" "$*"; }

bold "neb bootstrap"

# 1. Verificar dependencias
bold "Dependencias"
for cmd in git bash; do
  if command -v "$cmd" >/dev/null 2>&1; then
    ok "$cmd OK"
  else
    warn "$cmd NO encontrado — instálalo antes de continuar"
    exit 1
  fi
done

if command -v jq >/dev/null 2>&1; then
  ok "jq OK"
else
  warn "jq NO encontrado. El hook save-approved-plan.sh lo requiere para parsear JSON."
  warn "Instálalo con uno de:  scoop install jq  |  choco install jq  |  https://jqlang.github.io/jq/download/"
  warn "El bootstrap continúa, pero el hook no funcionará hasta que instales jq."
fi

# 2. Repo presente o clonar
bold "Repo en $GUIDE_DIR"
if [ -d "$GUIDE_DIR/.git" ]; then
  info "Ya existe — git pull"
  git -C "$GUIDE_DIR" pull --ff-only || warn "pull falló (¿offline o sin remoto?)"
elif [ -d "$GUIDE_DIR" ]; then
  warn "Existe pero no es un repo git. Saltando clone."
else
  info "Clonando desde $REPO_URL"
  git clone "https://$REPO_URL" "$GUIDE_DIR"
fi

# 3. Carpeta global de approved-plans
bold "Carpeta global de approved-plans"
mkdir -p "$HOME/.claude/approved-plans"
ok "$HOME/.claude/approved-plans/ listo"

# 4. Variable de entorno
bold "Variable NEB_HOME"
SHELL_RC=""
case "${SHELL:-}" in
  */zsh)  SHELL_RC="$HOME/.zshrc" ;;
  */bash) SHELL_RC="$HOME/.bashrc" ;;
  *)      SHELL_RC="$HOME/.bashrc" ;;
esac

# NEB_HOME es la variable canónica que apunta al checkout local del repo.
if [ -f "$SHELL_RC" ] && grep -qE "NEB_HOME" "$SHELL_RC"; then
  ok "NEB_HOME ya está exportada en $SHELL_RC"
else
  echo "" >> "$SHELL_RC"
  echo "# neb" >> "$SHELL_RC"
  echo "export NEB_HOME=\"$GUIDE_DIR\"" >> "$SHELL_RC"
  ok "Añadida NEB_HOME a $SHELL_RC (re-abrir terminal o source)"
fi

# 5. personal/<usuario>.md
bold "Archivo personal"
USER_NAME="${USER:-${USERNAME:-unknown}}"
mkdir -p "$GUIDE_DIR/personal"
PERSONAL_FILE="$GUIDE_DIR/personal/${USER_NAME}.md"
if [ -f "$PERSONAL_FILE" ]; then
  ok "$PERSONAL_FILE ya existe"
else
  cp "$GUIDE_DIR/templates/personal.md.template" "$PERSONAL_FILE"
  sed -i "s/<USUARIO>/$USER_NAME/g" "$PERSONAL_FILE" 2>/dev/null || true
  ok "Creado $PERSONAL_FILE desde plantilla"
fi

# 6. ~/CLAUDE.md
bold "Imports en ~/CLAUDE.md"
HOME_CLAUDE="$HOME/CLAUDE.md"
IMPORTS=(
  "@~/.claude/neb/general/startup.md"
  "@~/.claude/neb/workflow/index.md"
  "@~/.claude/neb/methodology/index.md"
  "@~/.claude/neb/personal/${USER_NAME}.md"
)

if [ ! -f "$HOME_CLAUDE" ]; then
  {
    for line in "${IMPORTS[@]}"; do echo "$line"; done
    echo ""
    echo "# CLAUDE.md (home)"
    echo ""
  } > "$HOME_CLAUDE"
  ok "Creado $HOME_CLAUDE con imports"
else
  MISSING=()
  for line in "${IMPORTS[@]}"; do
    if grep -qF "$line" "$HOME_CLAUDE"; then
      info "Ya presente: $line"
    else
      MISSING+=("$line")
    fi
  done
  if [ ${#MISSING[@]} -gt 0 ]; then
    tmp=$(mktemp)
    {
      for line in "${MISSING[@]}"; do echo "$line"; done
      cat "$HOME_CLAUDE"
    } > "$tmp"
    mv "$tmp" "$HOME_CLAUDE"
    for line in "${MISSING[@]}"; do
      ok "Añadido al header: $line"
    done
  fi
fi

# 7. Skills
bold "Skills de Claude Code"
if [ -f "$GUIDE_DIR/bootstrap/install-skills.sh" ]; then
  bash "$GUIDE_DIR/bootstrap/install-skills.sh"
else
  warn "install-skills.sh no encontrado — saltando"
fi

# 8. Agents
bold "Subagentes de Claude Code"
if [ -f "$GUIDE_DIR/bootstrap/install-agents.sh" ]; then
  bash "$GUIDE_DIR/bootstrap/install-agents.sh"
else
  warn "install-agents.sh no encontrado — saltando"
fi

# 9. Hook pre-push de CHANGELOG
bold "Hook pre-push changelog"
HOOK_SRC="$GUIDE_DIR/hooks/pre-push-changelog"
HOOK_DST="$GUIDE_DIR/.git/hooks/pre-push"
MARKER="managed-by: neb/hooks/pre-push-changelog"

if [ ! -f "$HOOK_SRC" ]; then
  warn "hooks/pre-push-changelog no encontrado — saltando"
elif [ ! -d "$GUIDE_DIR/.git" ]; then
  warn ".git/ no encontrado en $GUIDE_DIR — saltando hook install"
elif [ ! -f "$HOOK_DST" ]; then
  cp "$HOOK_SRC" "$HOOK_DST"
  chmod +x "$HOOK_DST"
  ok "Hook pre-push instalado en .git/hooks/pre-push"
elif grep -qF "$MARKER" "$HOOK_DST" 2>/dev/null; then
  cp "$HOOK_SRC" "$HOOK_DST"
  chmod +x "$HOOK_DST"
  ok "Hook pre-push actualizado (idempotente)"
else
  warn "Ya existe .git/hooks/pre-push sin marker de esta metodología."
  warn "Para instalar el hook, hacer backup y luego:"
  warn "  cp $HOOK_SRC $HOOK_DST && chmod +x $HOOK_DST"
fi

bold "Listo"
info "Próximo paso: bash $GUIDE_DIR/bootstrap/link-into-project.sh <ruta-proyecto>"
