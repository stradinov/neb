#!/usr/bin/env bash
set -euo pipefail

# setup-workspace.sh — configura o repara el entorno de gobernanza de Neb.
#
# Idempotente: seguro de correr varias veces. Cubre tres escenarios:
#   - Adoptante nuevo: completa el scaffolding (overlay + personal/ + changes/) y la env var.
#   - Migración (dev con versión antigua tras traer neb/): corrige NEB_HOME y avisa de imports rotos.
#   - Reset: reconfigura sin duplicar.
#
# Debe correrse DESDE la raíz del repo de gobernanza (el que contiene neb/ como subtree).
# Modelo de variable: NEB_HOME = el checkout de neb (= <raíz>/neb). La raíz de gobernanza
# se deriva como dirname(NEB_HOME); el overlay vive como hermano de neb/.
#
# Uso:
#   bash neb/bootstrap/setup-workspace.sh [--overlay <nombre>] [--dry-run]
#     --overlay <nombre>   nombre del dir de overlay a crear si no hay ninguno (default: overlay)
#     --dry-run            muestra lo que haría sin escribir nada
#
# NO toca settings.json ni regenera tu CLAUDE.md: eso se maneja aparte (ver README/wakeup).

OVERLAY_NAME="overlay"
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --overlay) OVERLAY_NAME="${2:?--overlay requiere un nombre}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opción desconocida: $1" >&2; exit 1 ;;
  esac
done

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m%s\033[0m\n" "$*"; }
info() { printf "  %s\n" "$*"; }
warn() { printf "  \033[33m%s\033[0m\n" "$*"; }
run()  { if [ "$DRY_RUN" -eq 1 ]; then info "[dry-run] $*"; else eval "$@"; fi; }

# 1. Ubicar la raíz del repo de gobernanza (debe contener neb/ como subtree)
ROOT="$(pwd)"
if [ ! -f "$ROOT/neb/general/startup.md" ]; then
  if [ -f "$ROOT/general/startup.md" ]; then
    echo "Estás dentro de neb/. Corré el script desde la raíz del repo de gobernanza (el padre de neb/)." >&2
  else
    echo "No encuentro neb/ aquí. Corré setup-workspace.sh desde la raíz de tu repo de gobernanza (debe contener neb/ como subtree de Neb)." >&2
    echo "Si aún no agregaste neb/: git subtree add --prefix neb/ <url-neb> main --squash" >&2
  fi
  exit 1
fi
bold "Repo de gobernanza: $ROOT"

# 2. NEB_HOME = el checkout de neb (= <raíz>/neb), variable canónica
NEB_HOME_VAL="$ROOT/neb"
info "NEB_HOME → $NEB_HOME_VAL"

# 3. Scaffolding idempotente: overlay (hermano de neb/), personal/, changes/
bold "Overlay privado"
_existing_overlay=""
for _o in "$ROOT"/*/overlays/detect-stack.local.sh; do
  [ -f "$_o" ] || continue
  _existing_overlay="$(basename "$(dirname "$(dirname "$_o")")")"
  break
done
if [ -n "$_existing_overlay" ]; then
  ok "Overlay preexistente: $_existing_overlay/ (lo conservo, no creo otro)"
else
  run "mkdir -p \"$ROOT/$OVERLAY_NAME/overlays\""
  if [ "$DRY_RUN" -eq 0 ]; then
    cat > "$ROOT/$OVERLAY_NAME/overlays/detect-stack.local.sh" <<'OV'
#!/usr/bin/env bash
# detect-stack.local.sh — overlay privado: detección de stacks de dominio.
# Sourced por neb/bootstrap/link-into-project.sh (descubrimiento genérico, sin nombre fijo).
# Sobreescribí estas funciones para tus stacks privados.

detect_stack_local()        { echo "unknown"; }   # devolvé el nombre de tu stack según $PROJECT
get_private_stack_imports() { :; }                 # imprimí los @-imports de tu stack privado
# get_framework_imports()   { ... }                # (opcional) override de los imports base
OV
  fi
  ok "Creado $OVERLAY_NAME/overlays/detect-stack.local.sh (stub editable)"
  info "Tus stacks/agents/skills propios viven bajo $OVERLAY_NAME/ — los creás al definir tu primer stack."
fi
[ -d "$ROOT/personal" ] && ok "personal/ ya existe" || { run "mkdir -p \"$ROOT/personal\""; run "touch \"$ROOT/personal/.gitkeep\""; ok "Creado personal/"; }
[ -d "$ROOT/changes" ]  && ok "changes/ ya existe"  || { run "mkdir -p \"$ROOT/changes\"";  run "touch \"$ROOT/changes/.gitkeep\"";  ok "Creado changes/"; }

# 4. Setear NEB_HOME en el shell profile (idempotente, con backup, portable BSD/GNU)
bold "Variable de entorno NEB_HOME (shell profile)"
PROFILE=""
for cand in "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile"; do
  [ -f "$cand" ] && { PROFILE="$cand"; break; }
done
if [ -z "$PROFILE" ]; then
  warn "No encontré un shell profile (~/.bashrc, etc.). Agregá manualmente: export NEB_HOME=\"$NEB_HOME_VAL\""
elif grep -q '^[[:space:]]*export[[:space:]]\+NEB_HOME=' "$PROFILE"; then
  if grep -qF "export NEB_HOME=\"$NEB_HOME_VAL\"" "$PROFILE"; then
    ok "NEB_HOME ya correcto en $PROFILE"
  else
    run "cp \"$PROFILE\" \"$PROFILE.bak\""
    # reescritura portable (sin sed -i, que difiere GNU vs BSD): filtrar + append
    run "grep -v '^[[:space:]]*export[[:space:]]\\+NEB_HOME=' \"$PROFILE\" > \"$PROFILE.tmp\" && printf 'export NEB_HOME=\"%s\"\\n' \"$NEB_HOME_VAL\" >> \"$PROFILE.tmp\" && mv \"$PROFILE.tmp\" \"$PROFILE\""
    ok "Actualizado NEB_HOME en $PROFILE (backup .bak)"
  fi
else
  run "printf '\\nexport NEB_HOME=\"%s\"\\n' \"$NEB_HOME_VAL\" >> \"$PROFILE\""
  ok "Agregado NEB_HOME a $PROFILE"
fi
info "Para esta sesión: export NEB_HOME=\"$NEB_HOME_VAL\""

# 5. Verificar ~/CLAUDE.md (no destructivo: NO sobreescribe contenido propio)
bold "~/CLAUDE.md (verificación, sin sobreescribir)"
_imp() { echo "@$(echo "$1" | sed "s|^$HOME/|~/|")"; }
NEB_IMPORT="$(_imp "$NEB_HOME_VAL")/general/startup.md"
if [ ! -f "$HOME/CLAUDE.md" ]; then
  warn "No existe ~/CLAUDE.md. Imports mínimos sugeridos (revisá antes de usar):"
  info "  $NEB_IMPORT"
  info "  $(_imp "$NEB_HOME_VAL")/workflow/index.md"
elif grep -qF "$NEB_IMPORT" "$HOME/CLAUDE.md"; then
  ok "~/CLAUDE.md ya importa neb/general/startup.md desde NEB_HOME"
else
  warn "~/CLAUDE.md existe pero no importa $NEB_IMPORT"
  warn "Puede apuntar a una ruta vieja (caso migración). Revisá los imports a mano — no lo edito."
fi

bold "Listo"
info "Pendiente (no automatizado aquí): NEB_HOME en ~/.claude/settings.json y reapuntar hooks a \$NEB_HOME/hooks — ver wakeup / migración (F5)."
[ "$DRY_RUN" -eq 1 ] && info "(fue --dry-run: no se escribió nada)"
