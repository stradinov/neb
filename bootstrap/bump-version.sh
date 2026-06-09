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

if [ -f "$PLUGIN_JSON" ] && [ -n "$PYTHON" ]; then
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
elif [ -f "$PLUGIN_JSON" ]; then
  info "AVISO: sin Python (python3/python/py) — plugin.json.version NO sincronizado a $NEW. Hacelo a mano."
fi

bold "Listo"
info "Siguiente: completar changelog.d/$NEW.md y correr 'py $SCRIPT_DIR/assemble-changelog.py'"
