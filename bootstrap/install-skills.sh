#!/usr/bin/env bash
set -euo pipefail

# install-skills.sh — instala los skills de neb en ~/.claude/skills/
# Idempotente: si el target ya existe y apunta al guide, no hace nada.
# Invocado por install.sh o directamente tras un git pull del guide.

GUIDE_DIR="${NEB_HOME:-$HOME/.claude/neb}"
SKILLS_SRC="$GUIDE_DIR/skills"
SKILLS_DST="$HOME/.claude/skills"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
info() { printf "  %s\n" "$*"; }
warn() { printf "  \033[33m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m%s\033[0m\n" "$*"; }

bold "neb skills installer"

if [ ! -d "$SKILLS_SRC" ]; then
  warn "No se encontró $SKILLS_SRC — ¿el guide está actualizado?"
  exit 1
fi

mkdir -p "$SKILLS_DST"

install_skill() {
  local name="$1"
  local src="$SKILLS_SRC/$name"
  local dst="$SKILLS_DST/$name"

  if [ ! -d "$src" ]; then
    warn "Skill '$name' no encontrado en $src — saltando"
    return
  fi

  if [ -L "$dst" ]; then
    # Es symlink — verificar que apunte al guide
    local target
    target=$(readlink "$dst" 2>/dev/null || echo "")
    if [ "$target" = "$src" ]; then
      ok "$name ya enlazado (symlink OK)"
      return
    else
      warn "$name symlink apunta a '$target' (esperado: $src) — reemplazando"
      rm "$dst"
    fi
  elif [ -d "$dst" ]; then
    # Es directorio real — puede ser copia previa
    warn "$name existe como directorio en $dst"
    warn "Si es una copia antigua, elimínala manualmente y vuelve a correr este script."
    return
  fi

  # Intentar symlink (funciona en Linux/WSL/macOS y en Windows con permisos de admin)
  if ln -s "$src" "$dst" 2>/dev/null; then
    ok "$name → symlink creado"
  else
    # Fallback: copia recursiva (Windows sin permisos de admin)
    cp -r "$src" "$dst"
    ok "$name → copiado (symlink falló; re-correr este script tras git pull para sincronizar)"
    warn "Para habilitar symlinks en Windows: activar 'Developer Mode' o correr como administrador."
  fi
}

bold "Instalando skills del núcleo"
for _s in "$SKILLS_SRC"/*/; do
  [ -d "$_s" ] && [ -f "${_s}SKILL.md" ] || continue
  install_skill "$(basename "$_s")"
done

# Extension point del overlay: instalador propio del adoptante (opcional).
# El overlay provee <overlay>/bootstrap/install-skills.local.sh autónomo con sus skills.
_WS="${NEB_WORKSPACE:-$(dirname "$GUIDE_DIR")}"
for _local in "$_WS"/*/bootstrap/install-skills.local.sh; do
  [ -f "$_local" ] || continue
  bold "Instalando skills del overlay"
  bash "$_local" || warn "install-skills.local.sh del overlay falló (continúo)"
  break
done

bold "Listo"
info "Skills instalados en $SKILLS_DST"
info "Para verificar: ls -la $SKILLS_DST"
