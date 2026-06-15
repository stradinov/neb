#!/usr/bin/env bash
set -euo pipefail

# bump-version.sh [--patch|--minor|--major] [--dry-run]
# Bumpea VERSION (SemVer), crea el fragment changelog.d/<nueva>.md y sincroniza
# .claude-plugin/plugin.json.version. Default: --minor.
#
# Tras correrlo: completar el fragment y `py bootstrap/assemble-changelog.py`.
# Pure shell + un python inline para editar plugin.json sin romper su formato.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEB="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="$NEB/VERSION"
PLUGIN_JSON="$NEB/.claude-plugin/plugin.json"

LEVEL="minor"
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --patch) LEVEL="patch"; shift ;;
    --minor) LEVEL="minor"; shift ;;
    --major) LEVEL="major"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opcion desconocida: $1" >&2; exit 1 ;;
  esac
done

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
info() { printf "  %s\n" "$*"; }
ok()   { printf "  \033[32m%s\033[0m\n" "$*"; }

# Resolver de Python: primer interprete que existe Y corre (rechaza el stub python3
# del Microsoft Store en Windows, que existe en PATH pero no ejecuta).
neb_python() {
  local c
  for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c '' >/dev/null 2>&1; then
      printf '%s\n' "$c"; return 0
    fi
  done
  return 1
}
PYTHON="$(neb_python || true)"

# Sin Python no se puede sincronizar plugin.json.version. Abortar ruidoso y temprano
# —antes de escribir VERSION o crear el fragment— en vez de degradar a un aviso
# "hacelo a mano" que se ignora (causa raíz de la deriva de versión histórica). El
# gate 5 del pre-push es el backstop; aquí se previene la desincronía en origen.
if [ -f "$PLUGIN_JSON" ] && [ -z "$PYTHON" ]; then
  echo "ERROR: no se encontró Python ejecutable (python3/python/py) y existe $PLUGIN_JSON." >&2
  echo "       Sin Python no se puede sincronizar plugin.json.version; el plugin quedaria" >&2
  echo "       desincronizado y 'claude plugin update' lo bloquearia. Instala Python y reintenta." >&2
  exit 1
fi

[ -f "$VERSION_FILE" ] || { echo "No existe $VERSION_FILE" >&2; exit 1; }
CUR="$(tr -d '[:space:]' < "$VERSION_FILE")"
if ! echo "$CUR" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "VERSION malformada: '$CUR' (esperado X.Y.Z)" >&2; exit 1
fi
IFS=. read -r MA MI PA <<< "$CUR"
case "$LEVEL" in
  patch) PA=$((PA + 1)) ;;
  minor) MI=$((MI + 1)); PA=0 ;;
  major) MA=$((MA + 1)); MI=0; PA=0 ;;
esac
NEW="$MA.$MI.$PA"
TODAY="$(date +%Y-%m-%d 2>/dev/null || echo 'YYYY-MM-DD')"

bold "Bump $LEVEL: $CUR → $NEW"

# Aviso si plugin.json.version diverge de VERSION (no bloquea; el bump las unifica)
if [ -f "$PLUGIN_JSON" ] && [ -n "$PYTHON" ]; then
  PJV="$("$PYTHON" -c "import json,io;print(json.load(io.open('$PLUGIN_JSON',encoding='utf-8')).get('version',''))" 2>/dev/null || echo '')"
  [ -n "$PJV" ] && [ "$PJV" != "$CUR" ] && info "AVISO: plugin.json.version ($PJV) != VERSION ($CUR) estaban desincronizados; el bump unifica en $NEW."
fi

if [ "$DRY_RUN" -eq 1 ]; then
  info "[dry-run] VERSION → $NEW"
  info "[dry-run] crearia changelog.d/$NEW.md"
  info "[dry-run] plugin.json.version → $NEW"
  exit 0
fi

echo "$NEW" > "$VERSION_FILE"
ok "VERSION → $NEW"

FRAG="$NEB/changelog.d/$NEW.md"
if [ ! -f "$FRAG" ]; then
  cat > "$FRAG" <<EOF
## [$NEW] - $TODAY

### Added

### Changed

### Fixed
EOF
  ok "changelog.d/$NEW.md (completar antes de assemble)"
else
  info "changelog.d/$NEW.md ya existe"
fi

if [ -f "$PLUGIN_JSON" ]; then
  # PYTHON garantizado por el check de arranque cuando plugin.json existe.
  "$PYTHON" - "$PLUGIN_JSON" "$NEW" <<'PY'
import json, sys
path, new = sys.argv[1], sys.argv[2]
with open(path, encoding='utf-8') as f:
    data = json.load(f)
data['version'] = new
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write('\n')
PY
  ok "plugin.json.version → $NEW"
fi

bold "Listo"
info "Siguiente: completar changelog.d/$NEW.md y correr 'py $SCRIPT_DIR/assemble-changelog.py'"
