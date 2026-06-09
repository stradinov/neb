#!/usr/bin/env bash
set -euo pipefail

# ── DEPRECADO (v2.0.0): modelo "clone" ──────────────────────────────────────
# Los agentes de neb se auto-descubren del PLUGIN instalado; no hace falta copiarlos
# a ~/.claude/agents. Este script (modelo clone legacy) NO es necesario. Se conserva
# para referencia. Adopcion vigente: docs/user-guide.md (/plugin install).
# ────────────────────────────────────────────────────────────────────────────

# install-agents.sh — instala los agentes de neb en ~/.claude/agents/
# Idempotente: si el target ya existe y apunta al guide, no hace nada.
# Invocado por install.sh o directamente tras un git pull del guide.

GUIDE_DIR="${NEB_HOME:-$HOME/.claude/neb}"
AGENTS_SRC="$GUIDE_DIR/agents"
AGENTS_DST="$HOME/.claude/agents"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
info() { printf "  %s\n" "$*"; }
warn() { printf "  \033[33m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m%s\033[0m\n" "$*"; }

bold "neb agents installer"

if [ ! -d "$AGENTS_SRC" ]; then
  warn "No se encontró $AGENTS_SRC — ¿el guide está actualizado?"
  exit 1
fi

mkdir -p "$AGENTS_DST"

install_agent() {
  local name="$1"
  local src="$AGENTS_SRC/${name}.md"
  local dst="$AGENTS_DST/${name}.md"

  if [ ! -f "$src" ]; then
    warn "Agente '$name' no encontrado en $src — saltando"
    return
  fi

  if [ -L "$dst" ]; then
    local target
    target=$(readlink "$dst" 2>/dev/null || echo "")
    if [ "$target" = "$src" ]; then
      ok "$name ya enlazado (symlink OK)"
      return
    else
      warn "$name symlink apunta a '$target' (esperado: $src) — reemplazando"
      rm "$dst"
    fi
  elif [ -f "$dst" ]; then
    warn "$name existe como archivo en $dst"
    warn "Si es una copia antigua, elimínala manualmente y vuelve a correr este script."
    return
  fi

  if ln -s "$src" "$dst" 2>/dev/null; then
    ok "$name → symlink creado"
  else
    cp "$src" "$dst"
    ok "$name → copiado (symlink falló; re-correr este script tras git pull para sincronizar)"
    warn "Para habilitar symlinks en Windows: activar 'Developer Mode' o correr como administrador."
  fi
}

bold "Instalando agentes del núcleo"
for _a in "$AGENTS_SRC"/*.md; do
  [ -f "$_a" ] || continue
  install_agent "$(basename "$_a" .md)"
done

# Extension point del overlay: instalador propio del adoptante (opcional).
# El overlay provee <overlay>/bootstrap/install-agents.local.sh autónomo con sus agentes.
_WS="${NEB_WORKSPACE:-$(dirname "$GUIDE_DIR")}"
for _local in "$_WS"/*/bootstrap/install-agents.local.sh; do
  [ -f "$_local" ] || continue
  bold "Instalando agentes del overlay"
  bash "$_local" || warn "install-agents.local.sh del overlay falló (continúo)"
  break
done

bold "Listo"
info "Agentes instalados en $AGENTS_DST"
info "Para verificar: ls -la $AGENTS_DST"

bold "Auditoría de cobertura mínima por stack (Fase 4 / Fase 7)"
check_stack() {
  local stack="$1"; shift
  local required=("$@")
  local missing=()
  for agent in "${required[@]}"; do
    [ -f "$AGENTS_DST/${agent}.md" ] || missing+=("$agent")
  done
  if [ ${#missing[@]} -eq 0 ]; then
    ok "$stack — cobertura OK"
  else
    warn "$stack — GAP: falta(n) ${missing[*]}"
  fi
}

check_stack "self-applied"          "qa-process-engineer"
check_stack "stack-authoring"       "qa-process-engineer"
check_stack "skill-authoring"       "skill-qa-engineer"
check_stack "research"              "fact-check-reviewer"
