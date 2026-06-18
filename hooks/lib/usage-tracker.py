#!/usr/bin/env python3
"""
usage-tracker.py — agrega tokens/costo del turno actual al Reporte de cierre del REQ activo.

Argumentos posicionales:
  1. session_id      — UUID de la sesión Claude
  2. encoded_cwd     — CWD sanitizado (path → guiones, ej. C--Users-foo-repo)
  3. guide_dir       — Path al checkout de methodology
  4. home_dir        — HOME del dev

Salida: exit 0 siempre (hook defensivo — errores a stderr, no bloquean al dev).
"""

import json
import os
import re
import sys

from _db_shared import find_active_reqs, resolve_memory_dir

# ---------------------------------------------------------------------------
# Helpers de path
# ---------------------------------------------------------------------------

def posix_to_win(path):
    """Convierte ruta POSIX de Git Bash (/c/Users/foo) a Windows (C:\\Users\\foo).
    No-op en Linux/Mac o si la ruta ya está en formato Windows."""
    if sys.platform == "win32" and path and re.match(r"^/[a-zA-Z]/", path):
        drive = path[1].upper()
        rest  = path[2:].replace("/", "\\")
        return f"{drive}:\\{rest}"
    return path

# ---------------------------------------------------------------------------
# Argumentos
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 5:
        return

    session_id   = sys.argv[1]
    encoded_cwd  = sys.argv[2]
    guide_dir    = posix_to_win(sys.argv[3])
    home_dir_raw = sys.argv[4]
    # Si home_dir es POSIX (/c/Users/alex) en Windows, convertir; si ya es Windows, usar tal cual.
    home_dir     = posix_to_win(home_dir_raw) if home_dir_raw else os.path.expanduser("~")

    projects_dir = os.path.join(home_dir, ".claude", "projects", encoded_cwd)
    jsonl_path   = os.path.join(projects_dir, f"{session_id}.jsonl")
    offset_path  = os.path.join(projects_dir, f"{session_id}.usage-offset")
    state_path   = os.path.join(projects_dir, f"{session_id}.usage-state.json")
    pricing_path = os.path.join(guide_dir, "hooks", "pricing.yml")
    # memory_dir respeta autoMemoryDirectory (user scope); jsonl/offset/state NO se mueven
    # con ese setting — son archivos de sesión, viven bajo projects/<encoded_cwd> (por cwd).
    # usage-tracker solo recibe encoded_cwd (no el cwd crudo) → resuelve user scope; los
    # scopes project/local de autoMemoryDirectory los respeta logbook.py (caso raro).
    memory_dir   = resolve_memory_dir(home_dir, "", encoded_cwd)

    # -----------------------------------------------------------------------
    # 1. Verificar JSONL y memoria
    # -----------------------------------------------------------------------
    if not os.path.isfile(jsonl_path):
        return
    if not os.path.isdir(memory_dir):
        return

    # -----------------------------------------------------------------------
    # 2. Encontrar REQ activo — con N REQ activos, atribuir el costo del turno al de
    #    mtime más reciente (el tocado en esta sesión); atribución única, no duplica.
    # -----------------------------------------------------------------------
    reqs = find_active_reqs(memory_dir)
    if not reqs:
        return
    active = max(reqs, key=lambda d: d.get("mtime", 0))
    project_path = active.get("project_path", "")
    draft_rel    = active.get("draft", "")
    if not project_path or not draft_rel:
        return

    draft_path = os.path.join(project_path, draft_rel)
    if not os.path.isfile(draft_path):
        return

    # -----------------------------------------------------------------------
    # 3. Leer offset — procesar solo líneas nuevas
    # -----------------------------------------------------------------------
    last_line = 0
    if os.path.isfile(offset_path):
        try:
            last_line = int(open(offset_path).read().strip())
        except (ValueError, OSError):
            last_line = 0

    # -----------------------------------------------------------------------
    # 4. Leer nuevas líneas del JSONL
    # -----------------------------------------------------------------------
    new_entries = []
    total_lines = 0
    with open(jsonl_path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            total_lines = i + 1
            if i < last_line:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("type") == "assistant":
                    new_entries.append(entry)
            except json.JSONDecodeError:
                pass

    if not new_entries:
        # Actualizar offset aunque no haya assistant entries nuevas
        _write(offset_path, str(total_lines))
        return

    _write(offset_path, str(total_lines))

    # -----------------------------------------------------------------------
    # 5. Cargar estado acumulado
    # -----------------------------------------------------------------------
    state = {}
    if os.path.isfile(state_path):
        try:
            state = json.loads(open(state_path, encoding="utf-8").read())
        except (json.JSONDecodeError, OSError):
            state = {}

    # -----------------------------------------------------------------------
    # 6. Acumular tokens por modelo
    # -----------------------------------------------------------------------
    for entry in new_entries:
        model  = entry.get("model", "unknown")
        usage  = entry.get("usage") or {}
        inp    = int(usage.get("input_tokens", 0))
        out    = int(usage.get("output_tokens", 0))
        cw     = int(usage.get("cache_creation_input_tokens", 0))
        cr     = int(usage.get("cache_read_input_tokens", 0))

        if model not in state:
            state[model] = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}

        state[model]["input"]       += inp
        state[model]["output"]      += out
        state[model]["cache_write"] += cw
        state[model]["cache_read"]  += cr

    _write(state_path, json.dumps(state, indent=2))

    # -----------------------------------------------------------------------
    # 7. Cargar pricing
    # -----------------------------------------------------------------------
    prices = load_pricing(pricing_path)

    # -----------------------------------------------------------------------
    # 8. Construir tabla de uso
    # -----------------------------------------------------------------------
    rows = []
    total_cost = 0.0
    total_inp = total_out = total_cw = total_cr = 0
    has_missing_price = False

    for model, tok in sorted(state.items()):
        inp = tok["input"]
        out = tok["output"]
        cw  = tok["cache_write"]
        cr  = tok["cache_read"]
        total_inp += inp; total_out += out; total_cw += cw; total_cr += cr

        tok_str = f"{_fmt(inp)} · {_fmt(out)} · {_fmt(cw)} · {_fmt(cr)}"

        if model in prices:
            p = prices[model]
            cost = (inp * p.get("input_per_mtok", 0) +
                    out * p.get("output_per_mtok", 0) +
                    cw  * p.get("cache_write_per_mtok", 0) +
                    cr  * p.get("cache_read_per_mtok", 0)) / 1_000_000
            total_cost += cost
            cost_str = f"${cost:.4f}"
        else:
            cost_str = "— (modelo sin pricing)"
            has_missing_price = True

        rows.append(f"| `{model}` | {tok_str} | {cost_str} |")

    total_tok_str  = f"{_fmt(total_inp)} · {_fmt(total_out)} · {_fmt(total_cw)} · {_fmt(total_cr)}"
    total_cost_str = f"**${total_cost:.4f}**" if not has_missing_price else f"**${total_cost:.4f}** *(parcial — modelos sin pricing: ver arriba)*"
    rows.append(f"| **Total** | {total_tok_str} | {total_cost_str} |")

    table_header = (
        "| Modelo | Tokens (in · out · cache_w · cache_r) | Costo USD |\n"
        "|---|---|---|"
    )
    table_body = "\n".join(rows)
    new_block = f"{table_header}\n{table_body}"

    # -----------------------------------------------------------------------
    # 9. Actualizar draft — reemplazar entre marcadores
    # -----------------------------------------------------------------------
    update_draft(draft_path, new_block)

    if has_missing_price:
        print(f"[usage-tracker] WARNING: uno o más modelos sin entrada en pricing.yml. Actualizar {pricing_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_pricing(pricing_path):
    """Lee pricing.yml. Intenta pyyaml; si no está disponible, usa parser manual simple."""
    if not os.path.isfile(pricing_path):
        return {}
    try:
        import yaml  # type: ignore
        with open(pricing_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        pass
    # Fallback: parser manual para YAML plano de dos niveles
    prices = {}
    current = None
    with open(pricing_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            if not line.startswith(" ") and line.endswith(":"):
                current = line[:-1].strip()
                prices[current] = {}
            elif current and ":" in line:
                k, _, v = line.strip().partition(":")
                try:
                    prices[current][k.strip()] = float(v.strip())
                except ValueError:
                    pass
    return prices


def update_draft(draft_path, new_block):
    """Reemplaza el contenido entre marcadores usage-tracker en el draft."""
    START = "<!-- usage-tracker-start -->"
    END   = "<!-- usage-tracker-end -->"
    try:
        content = open(draft_path, encoding="utf-8").read()
    except OSError as e:
        print(f"[usage-tracker] ERROR leyendo draft: {e}", file=sys.stderr)
        return

    if START not in content or END not in content:
        # Marcadores no presentes — draft usa template anterior, no actualizar
        return

    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END),
        re.DOTALL
    )
    new_content = pattern.sub(f"{START}\n{new_block}\n{END}", content)
    _write(draft_path, new_content)


def _fmt(n):
    """Formatea número de tokens legible (ej. 1234567 → 1.23M)."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def _write(path, content):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        print(f"[usage-tracker] ERROR escribiendo {path}: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[usage-tracker] ERROR inesperado: {e}", file=sys.stderr)
    sys.exit(0)
