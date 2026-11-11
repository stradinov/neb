#!/usr/bin/env python3
"""
usage-tracker.py — gasto de tokens por REQ o por ventana de días, leído de los transcripts de Claude Code.

Uso:
  usage-tracker.py report [--days N] [--req <slug>] [--write <change MD>] [--projects <dir>]
  usage-tracker.py plugins [--days N] [--projects <dir>] [--settings <settings.json>]
  usage-tracker.py apply <plugin@marketplace> disable|name-only [--settings <settings.json>]

  --days N     ventana: transcripts modificados en los últimos N días (por defecto 14 sin --req/--write).
  --req SLUG   solo las llamadas atribuidas al REQ SLUG (slug = nombre del change MD sin la fecha).
  --write MD   reemplaza el bloque entre <!-- usage-tracker-start --> y <!-- usage-tracker-end --> de MD con
               el gasto de su REQ (el slug sale del nombre de MD si no se da --req). Sin marcadores no escribe.
  --projects   raíz de los transcripts (por defecto <dir de config>/projects).

El dir de config es `CLAUDE_CONFIG_DIR` si está definida; si no, ~/.claude (supuesto R26).

Qué cuenta (formato del transcript: supuesto R21 de methodology/platform-assumptions.md):
  - Hilo principal `<proyecto>/<sesión>.jsonl` y subagentes `<proyecto>/<sesión>/subagents/**/agent-*.jsonl`
    (incluye agentes de workflow), con el `agentType` de su `.meta.json`.
  - Una llamada por `message.id` (el transcript repite el id en una línea por bloque), sin `<synthetic>`;
    dedupe global, el archivo más viejo gana (las copias de --resume y forks no suman dos veces).
  - Atribución: una llamada del hilo principal va al último REQ cuyo change MD (`changes/AAAA-MM-DD-<slug>.md`)
    o `active_*.md` la sesión creó o editó (Write/Edit) hasta ese momento; las previas al primer toque, al
    primer REQ tocado; sin toques, «sin REQ». Una llamada de subagente va al REQ vigente en el hilo principal
    a su misma hora.

plugins (solo lectura) — auditoría de los plugins activos: peso fijo contra uso real.
  --days N     ventana de uso (por defecto 90); --settings, el settings de usuario (por defecto
               <dir de config>/settings.json); `installed_plugins.json` y `known_marketplaces.json` se leen
               de `plugins/` junto a ese archivo (supuesto R26); --projects, como en report.
  Inventario: `enabledPlugins` en `true` del settings de usuario; `neb@*` se lee pero no sale en el reporte.
  No ve plugins activados solo en settings de proyecto, local o administrados. Peso: caracteres de `description` de
  `skills/*/SKILL.md`, `agents/*.md` y `commands/*.md`. Componentes que se pierden al desactivar: MCP, hooks y
  LSP (de los archivos del plugin, de su `plugin.json` y de su entrada en el marketplace). Uso, con dedupe por
  bloque (`tool_use.id` o el `uuid` de la línea `user`): `mcp__plugin_<nombre>_*`, `Agent`/`Task` con
  `subagent_type` `<nombre>:*`, `Skill` con `skill` `<nombre>:*` y `<command-name>` en líneas `user`
  (calificado, o sin calificar si coincide con un solo comando o skill de los plugins activos). [asumido] las
  copias de --resume y los forks conservan `tool_use.id` y `uuid`; si no, una copia contaría dos veces (el
  veredicto solo distingue cero de no cero).
  Clasificación: con señal medible y cero usos → desactivar; con usos, skills y cero cargas de skill →
  name-only; sin señal medible (solo LSP o hooks) → no auditable.

apply (la única escritura) — `disable` pone `enabledPlugins.<id> = false`; `name-only` pone
  `skillOverrides["<nombre>:<skill>"] = "name-only"` por cada skill del plugin. Relee el archivo justo antes,
  escribe a un temporal en el mismo directorio (con el modo del original; si el settings es un enlace, en su
  destino), verifica que parsea y que el resto de las claves no cambió, y reemplaza. El contenido ajeno queda
  igual; el formato se reescribe con la sangría detectada. Rechaza `neb@*` y los plugins que no están en
  `true`; tras name-only avisa que R24 está sin verificar. Solo se corre con OK del dev desde el menú de
  /neb-usage plugins.

Salida: exit 0 con el reporte; exit 1 si `apply` no pudo escribir; exit 2 ante argumentos inválidos.
"""

import argparse
import bisect
import json
import os
import re
import statistics
import sys
import shutil
import tempfile
import time
from collections import defaultdict
from datetime import datetime


HERE = os.path.dirname(os.path.abspath(__file__))
PRICING_PATH = os.path.join(os.path.dirname(HERE), "pricing.yml")
START = "<!-- usage-tracker-start -->"
END = "<!-- usage-tracker-end -->"
NO_REQ = "sin REQ"
MAIN = "hilo principal"
BIG_CONTEXT = 300_000
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
CHANGE_RE = re.compile(r"[\\/]changes[\\/]\d{4}-\d{2}-\d{2}-([^\\/]+)\.md$", re.IGNORECASE)
ACTIVE_RE = re.compile(r"[\\/]active_[^_\\/]+_([^\\/]+)\.md$")
TRANSCRIPT_RE = re.compile(r"[\\/]\.claude[\\/]projects[\\/].+\.jsonl$")
CITED_CHANGE_RE = re.compile(r"changes[\\/]\d{4}-\d{2}-\d{2}-([A-Za-z0-9][A-Za-z0-9._-]*?)\.md")
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})-[^\\/]+\.md$")


# --------------------------------------------------------------------------- lectura del transcript

def _ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def read_transcript(path):
    """Eventos del transcript en orden: ('call', dict) por message.id nuevo, ('tool', dict) por tool_use,
    ('boundary', dict) por compact_boundary. No deduplica entre archivos (eso lo hace measure())."""
    events = []
    seen_ids = set()
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return events
    with f:
        for line in f:
            if '"assistant"' not in line and "compact_boundary" not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("subtype") == "compact_boundary":
                meta = o.get("compactMetadata") or {}
                events.append(("boundary", {"ts": _ts(o.get("timestamp")), "trigger": meta.get("trigger"),
                                            "pre_tokens": meta.get("preTokens")}))
                continue
            if o.get("type") != "assistant":
                continue
            msg = o.get("message") or {}
            model = msg.get("model") or "unknown"
            if model == "<synthetic>":
                continue
            ts = _ts(o.get("timestamp"))
            mid = msg.get("id") or o.get("requestId")
            u = msg.get("usage")
            if u and mid not in seen_ids:
                seen_ids.add(mid)
                cc = u.get("cache_creation") or {}
                cw = int(u.get("cache_creation_input_tokens") or 0)
                cw1 = int(cc.get("ephemeral_1h_input_tokens") or 0)
                cw5 = int(cc.get("ephemeral_5m_input_tokens") or 0)
                if cw1 + cw5 != cw:          # sin desglose por TTL: todo a 5 min (tarifa base de escritura)
                    cw5, cw1 = cw - cw1, cw1
                events.append(("call", {"id": mid, "ts": ts, "model": model,
                                        "in": int(u.get("input_tokens") or 0), "cw5": cw5, "cw1": cw1,
                                        "cr": int(u.get("cache_read_input_tokens") or 0),
                                        "out": int(u.get("output_tokens") or 0)}))
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    events.append(("tool", {"id": mid, "ts": ts, "name": block.get("name"),
                                            "input": block.get("input") or {}}))
    return events


def agent_type(path):
    meta = path[:-len(".jsonl")] + ".meta.json"
    try:
        with open(meta, encoding="utf-8") as f:
            return json.load(f).get("agentType") or "desconocido"
    except (OSError, ValueError):
        return "desconocido"


# --------------------------------------------------------------------------- atribución

_active_cache = {}


def req_of_path(file_path):
    """Slug del REQ al que pertenece un archivo editado, o None. El change MD da el slug por su nombre; un
    active_*.md, por la ruta `changes/AAAA-MM-DD-<slug>.md` de su campo `Draft changes MD` o `Change MD`
    (el nombre varía entre plantillas); si no la tiene, por la primera que cite; si no cita ninguna o el
    archivo ya no existe, por su nombre de archivo."""
    if not isinstance(file_path, str):
        return None
    m = CHANGE_RE.search(file_path)
    if m:
        return m.group(1)
    m = ACTIVE_RE.search(file_path)
    if not m:
        return None
    if file_path not in _active_cache:
        slug = m.group(1)
        try:
            with open(file_path, encoding="utf-8") as f:
                text = f.read()
            # Primero la línea del campo del registro (`Draft changes MD`, `Change MD`); si no, la primera cita.
            field = [ln for ln in text.splitlines() if "change md" in ln.lower() or "changes md" in ln.lower()]
            cited = next((m for m in (CITED_CHANGE_RE.search(ln) for ln in field) if m), None) \
                or CITED_CHANGE_RE.search(text)
            if cited:
                slug = cited.group(1)
        except (OSError, UnicodeDecodeError):
            pass
        _active_cache[file_path] = slug
    return _active_cache[file_path]


def attribute_main(events):
    """Asigna 'req' a cada llamada del hilo principal (la llamada que edita el registro ya cuenta para su
    REQ). Devuelve la línea de tiempo de cambios de REQ [(ts, req)] para atribuir subagentes."""
    current = first = None
    calls, switches = [], []
    for kind, e in events:
        if kind == "call":
            e["req"] = current
            calls.append(e)
        elif kind == "tool" and e["name"] in EDIT_TOOLS:
            req = req_of_path(e["input"].get("file_path") or e["input"].get("notebook_path"))
            if req and req != current:
                current = req
                first = first or req
                if calls and calls[-1]["id"] == e["id"]:
                    calls[-1]["req"] = req
                if e["ts"] is not None:
                    switches.append((e["ts"], req))
    for c in calls:
        if c["req"] is None:
            c["req"] = first or NO_REQ
    return switches


def req_at(timeline, ts):
    """REQ vigente a la hora ts: el último cambio anterior; antes del primero, el primer REQ tocado."""
    if not timeline:
        return NO_REQ
    if ts is None:
        return timeline[0][1]
    i = bisect.bisect_right([t for t, _ in timeline], ts) - 1
    return timeline[max(i, 0)][1]


# --------------------------------------------------------------------------- recorrido

def session_files(projects, cutoff=None, must_contain=None):
    """[(mtime, ruta, sesión, es_principal)] de los transcripts con mtime >= cutoff. Con must_contain (una
    cadena o una lista), solo las sesiones cuyo hilo principal contiene alguna (y sus subagentes)."""
    out = []
    if isinstance(must_contain, str):
        must_contain = [must_contain]
    needles = [n.encode("utf-8") for n in must_contain or [] if n]
    try:
        proj_dirs = [e.path for e in os.scandir(projects) if e.is_dir()]
    except OSError:
        return out
    for pdir in proj_dirs:
        try:
            entries = list(os.scandir(pdir))
        except OSError:
            continue
        for e in entries:
            if not (e.is_file() and e.name.endswith(".jsonl")):
                continue
            try:
                mtime = e.stat().st_mtime
            except OSError:
                continue
            sid = e.name[:-len(".jsonl")]
            sub_dir = os.path.join(pdir, sid, "subagents")
            subs = []
            for dp, _dn, fn in os.walk(sub_dir):
                for name in fn:
                    if name.startswith("agent-") and name.endswith(".jsonl"):
                        p = os.path.join(dp, name)
                        try:
                            subs.append((os.path.getmtime(p), p))
                        except OSError:
                            pass
            if cutoff is not None and mtime < cutoff:     # mismo corte por archivo que la línea base
                continue
            if needles and not _contains(e.path, needles):
                continue
            out.append((mtime, e.path, sid, True))
            out.extend((m, p, sid, False) for m, p in subs if cutoff is None or m >= cutoff)
    return out


def _contains(path, needles):
    keep = max(len(n) for n in needles)
    try:
        with open(path, "rb") as f:
            tail = b""
            while True:
                chunk = f.read(1 << 22)
                if not chunk:
                    return False
                window = tail + chunk
                if any(n in window for n in needles):
                    return True
                tail = window[-keep:]
    except OSError:
        return False


def measure(files):
    """Llamadas únicas de los archivos (dedupe global, el más viejo gana), atribuidas y etiquetadas.
    Devuelve (calls, stats) con stats = compactaciones y relecturas tras compactar del hilo principal."""
    seen = set()
    timelines = {}
    calls = []
    stats = {"compactions": [], "rereads": [], "sessions": set()}   # [(req, trigger)], [req]
    ordered = sorted(files, key=lambda x: (not x[3], x[0]))   # hilos principales primero (definen la línea de tiempo)
    for _mtime, path, sid, is_main in ordered:
        events = read_transcript(path)
        if is_main:
            timeline = timelines[sid] = attribute_main(events)
            after = False
            for kind, e in events:
                if kind == "boundary":
                    stats["compactions"].append((req_at(timeline, e["ts"]), e["trigger"] or "?"))
                    after = True
                elif kind == "tool" and after and e["name"] == "Read" \
                        and TRANSCRIPT_RE.search(str(e["input"].get("file_path") or "")):
                    stats["rereads"].append(req_at(timeline, e["ts"]))
            agent = MAIN
        else:
            agent = agent_type(path)
            for kind, e in events:
                if kind == "call":
                    e["req"] = req_at(timelines.get(sid, []), e["ts"])
        for kind, e in events:
            if kind != "call" or e["id"] in seen:
                continue
            seen.add(e["id"])
            e["agent"], e["session"] = agent, sid
            calls.append(e)
            stats["sessions"].add(sid)
    return calls, stats


# --------------------------------------------------------------------------- precios

def load_pricing(path=PRICING_PATH):
    """pricing.yml → {modelo: {campo: float}}. pyyaml si está; si no, parser plano de dos niveles."""
    if not os.path.isfile(path):
        return {}
    try:
        import yaml  # type: ignore
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        pass
    prices, current = {}, None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].rstrip()
            if not line:
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


def cost(call, prices):
    """USD a precio de API, o None si el modelo no tiene precio."""
    p = prices.get(call["model"])
    if not p:
        return None
    inp = p.get("input_per_mtok", 0)
    usd = (call["in"] * inp
           + call["out"] * p.get("output_per_mtok", 0)
           + call["cw5"] * p.get("cache_write_per_mtok", inp * 1.25)
           + call["cw1"] * p.get("cache_write_1h_per_mtok", inp * 2)
           + call["cr"] * p.get("cache_read_per_mtok", inp * 0.1)) / 1_000_000
    above = p.get("long_context_above_tokens")
    if above and call["in"] + call["cw5"] + call["cw1"] + call["cr"] > above:
        usd *= p.get("long_context_multiplier", 1)
    return usd


# --------------------------------------------------------------------------- reporte

def summarize(calls, prices):
    def blank():
        return {"calls": 0, "in": 0, "out": 0, "cw": 0, "cr": 0, "usd": 0.0, "partial": False}
    by_agent, by_model, by_req = defaultdict(blank), defaultdict(blank), defaultdict(blank)
    total = blank()
    for c in calls:
        usd = cost(c, prices)
        for acc in (by_agent[c["agent"]], by_model[c["model"]], by_req[c["req"]], total):
            acc["calls"] += 1
            acc["in"] += c["in"]
            acc["out"] += c["out"]
            acc["cw"] += c["cw5"] + c["cw1"]
            acc["cr"] += c["cr"]
            if usd is None:
                acc["partial"] = True
            else:
                acc["usd"] += usd
    main = [c["in"] + c["cw5"] + c["cw1"] + c["cr"] for c in calls if c["agent"] == MAIN]
    signals = {
        "big_pct": (sum(1 for x in main if x > BIG_CONTEXT) / len(main)) if main else 0.0,
        "median_ctx": int(statistics.median(main)) if main else 0,
    }
    return total, by_agent, by_model, by_req, signals


def _fmt(n):
    if n >= 1_000_000:
        return "%.2fM" % (n / 1_000_000)
    if n >= 1_000:
        return "%.1fK" % (n / 1_000)
    return str(n)


def _usd(acc):
    return "$%.2f%s" % (acc["usd"], " *(parcial)*" if acc["partial"] else "")


def _row(label, acc):
    return "| %s | %s | %s · %s · %s · %s | %s |" % (
        label, acc["calls"], _fmt(acc["in"]), _fmt(acc["out"]), _fmt(acc["cw"]), _fmt(acc["cr"]), _usd(acc))


def _signals_line(signals, stats):
    by_trigger = defaultdict(int)
    for _req, trigger in stats["compactions"]:
        by_trigger[trigger] += 1
    comp = ", ".join("%s %d" % (k, v) for k, v in sorted(by_trigger.items())) or "0"
    return ("Llamadas del hilo principal con más de 300k de contexto: %.0f %% (mediana %s) · compactaciones: %s · "
            "relecturas del transcript tras compactar: %d" % (
                signals["big_pct"] * 100, _fmt(signals["median_ctx"]), comp, len(stats["rereads"])))


def render_block(calls, stats, prices):
    """Bloque para el change MD: por tipo de agente, total, señales y modelos."""
    total, by_agent, by_model, _by_req, signals = summarize(calls, prices)
    lines = ["| Agente | Llamadas | Tokens (in · out · cache_w · cache_r) | USD (precio de API) |", "|---|---|---|---|"]
    order = sorted(by_agent, key=lambda a: (a != MAIN, -by_agent[a]["usd"]))
    lines += [_row("`%s`" % a if a != MAIN else a, by_agent[a]) for a in order]
    lines.append(_row("**Total**", total).replace(_usd(total), "**%s**" % _usd(total)))
    models = " · ".join("`%s` %s" % (m, _usd(by_model[m])) for m in sorted(by_model, key=lambda m: -by_model[m]["usd"]))
    lines += ["", _signals_line(signals, stats), "", "Modelos: " + (models or "—")]
    if total["partial"]:
        lines.append("Hay modelos sin precio en `hooks/pricing.yml`: el total es parcial.")
    return "\n".join(lines)


def render_report(calls, stats, prices, title, show_reqs):
    total, by_agent, by_model, by_req, signals = summarize(calls, prices)
    out = ["# %s" % title, "",
           "Sesiones: %d · llamadas únicas: %d · %s a precio de API" % (len(stats["sessions"]), total["calls"], _usd(total)),
           "", _signals_line(signals, stats), "", "## Por tipo de agente", "",
           "| Agente | Llamadas | Tokens (in · out · cache_w · cache_r) | USD |", "|---|---|---|---|"]
    out += [_row(a, by_agent[a]) for a in sorted(by_agent, key=lambda a: (a != MAIN, -by_agent[a]["usd"]))]
    out += ["", "## Por modelo", "", "| Modelo | Llamadas | Tokens (in · out · cache_w · cache_r) | USD |", "|---|---|---|---|"]
    out += [_row("`%s`" % m, by_model[m]) for m in sorted(by_model, key=lambda m: -by_model[m]["usd"])]
    if show_reqs:
        out += ["", "## Por REQ (15 de mayor gasto)", "",
                "| REQ | Llamadas | Tokens (in · out · cache_w · cache_r) | USD |", "|---|---|---|---|"]
        for r in sorted(by_req, key=lambda r: -by_req[r]["usd"])[:15]:
            out.append(_row(r if r == NO_REQ else "`%s`" % r, by_req[r]))
        if total["usd"]:
            out += ["", "Sin REQ atribuido: %.0f %% del gasto." % (100 * by_req[NO_REQ]["usd"] / total["usd"])]
    if total["partial"]:
        missing = sorted(m for m in by_model if by_model[m]["partial"])
        out += ["", "Modelos sin precio en `hooks/pricing.yml` (total parcial): " + ", ".join(missing)]
    return "\n".join(out)


def write_block(path, block):
    """Reemplaza el contenido entre marcadores; True si escribió. Fuera de los marcadores no cambia nada."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            content = f.read()
    except OSError as e:
        print("usage-tracker: no se pudo leer %s: %s" % (path, e), file=sys.stderr)
        return False
    i, j = content.find(START), content.find(END)
    if i < 0 or j < i:
        print("usage-tracker: %s no tiene los marcadores %s / %s; no se escribió" % (path, START, END), file=sys.stderr)
        return False
    nl = "\r\n" if "\r\n" in content else "\n"
    new = content[:i + len(START)] + nl + block.replace("\n", nl) + nl + content[j:]
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    return True


# --------------------------------------------------------------------------- plugins: inventario y peso

def claude_dir():
    """Dir de configuración de Claude Code: `CLAUDE_CONFIG_DIR` o ~/.claude (supuesto R26)."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
PLUGINS_DAYS = 90
NEB_PREFIX = "neb@"
COMMAND_RE = re.compile(r"<command-name>/?([^<\s]+)</command-name>")
DISABLE, NAME_ONLY, NOT_AUDITABLE, IN_USE = "desactivar", "name-only", "no auditable", "en uso"
USE_KINDS = ("mcp", "agent", "skill", "command")      # skill = cargas de skill (por Skill o por comando)
USE_LABELS = {"mcp": "MCP", "agent": "agentes", "skill": "skills", "command": "comandos"}
COMPONENT_KEYS = (("mcp", "mcpServers"), ("hooks", "hooks"), ("lsp", "lspServers"))


def _load_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _unquote(v):
    if len(v) >= 2 and v[0] == v[-1] == '"':
        try:
            return json.loads(v)
        except ValueError:
            return v[1:-1]
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    return v


def _frontmatter(path):
    """{clave: texto} de las claves de primer nivel del frontmatter YAML de un .md: escalares (también los que
    siguen en líneas indentadas), bloques `>` (une con espacios) y `|` (une con saltos)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}
    out, key, style, parts = {}, None, None, []

    def flush():
        if key is None:
            return
        if style and style[0] == "|":
            val = "\n".join(p.strip() for p in parts)
        else:
            val = " ".join(p.strip() for p in parts if p.strip())
        out[key] = _unquote(val.strip())

    for ln in lines[1:end]:
        m = re.match(r"([A-Za-z0-9_-]+):(?:\s+(.*))?$", ln)
        if m and not ln[:1].isspace():
            flush()
            key, rest = m.group(1), (m.group(2) or "").strip()
            if rest[:1] in (">", "|") and len(rest) <= 2:
                style, parts = rest, []
            else:
                style, parts = None, ([rest] if rest else [])
        elif key is not None:
            parts.append(ln)
    flush()
    return out


def _resolve(value, root):
    """Valor de una clave de componentes: un objeto tal cual; una ruta (o lista de rutas) relativa a root, su JSON."""
    values = value if isinstance(value, list) else [value]
    out = []
    for v in values:
        if isinstance(v, dict):
            out.append(v)
        elif isinstance(v, str) and root:
            d = _load_json(os.path.join(root, v))
            if d:
                out.append(d)
    return out


def _names(kind, d):
    """Servidores MCP / eventos de hooks / servidores LSP de un objeto de declaración."""
    if kind == "mcp":
        d = d["mcpServers"] if isinstance(d.get("mcpServers"), dict) else d
        return {k for k, v in d.items() if isinstance(v, dict)}
    if kind == "hooks":
        d = d["hooks"] if isinstance(d.get("hooks"), dict) else d
        return {k for k, v in d.items() if isinstance(v, list)}
    d = d["lspServers"] if isinstance(d.get("lspServers"), dict) else d
    return {k for k, v in d.items() if isinstance(v, dict)}


def scan_plugin(pid, root, entry=None):
    """Componentes y peso de un plugin instalado en root. entry = su entrada del marketplace.json (puede
    declarar MCP, hooks o LSP, p. ej. un plugin `strict: false` sin plugin.json)."""
    name = pid.split("@", 1)[0]
    p = {"id": pid, "name": name, "root": root, "skills": {}, "agents": {}, "commands": {},
         "mcp": set(), "hooks": set(), "lsp": set(), "custom_paths": [],
         "missing": not (root and os.path.isdir(root))}
    if not p["missing"]:
        sdir = os.path.join(root, "skills")
        for d in sorted(os.listdir(sdir)) if os.path.isdir(sdir) else []:
            f = os.path.join(sdir, d, "SKILL.md")
            if os.path.isfile(f):
                fm = _frontmatter(f)
                p["skills"][fm.get("name") or d] = len(fm.get("description", ""))
        for kind in ("agents", "commands"):
            kdir = os.path.join(root, kind)
            for fn in sorted(os.listdir(kdir)) if os.path.isdir(kdir) else []:
                if fn.endswith(".md"):
                    fm = _frontmatter(os.path.join(kdir, fn))
                    nm = (fm.get("name") if kind == "agents" else None) or fn[:-3]
                    p[kind][nm] = len(fm.get("description", ""))
        for kind, rel in (("mcp", ".mcp.json"), ("hooks", os.path.join("hooks", "hooks.json")), ("lsp", ".lsp.json")):
            d = _load_json(os.path.join(root, rel))
            if d:
                p[kind] |= _names(kind, d)
    manifest = _load_json(os.path.join(root, ".claude-plugin", "plugin.json")) if not p["missing"] else None
    for decl in (manifest, entry):
        for kind, key in COMPONENT_KEYS:
            if decl and key in decl:
                for d in _resolve(decl[key], root):
                    p[kind] |= _names(kind, d)
    p["custom_paths"] = sorted(k for k in ("skills", "agents", "commands") if manifest and k in manifest)
    p["weight"] = {k: sum(p[k].values()) for k in ("skills", "agents", "commands")}
    p["weight"]["total"] = sum(p["weight"].values())
    return p


def _market_entry(markets, mkt, name):
    loc = (markets.get(mkt) or {}).get("installLocation") if isinstance(markets.get(mkt), dict) else None
    data = _load_json(os.path.join(loc, ".claude-plugin", "marketplace.json")) if loc else None
    for e in (data or {}).get("plugins") or []:
        if isinstance(e, dict) and e.get("name") == name:
            return e
    return None


def _plugins_dir(settings_path):
    return os.path.join(os.path.dirname(os.path.abspath(settings_path)), "plugins")


def locate_plugin(settings_path, pid):
    """scan_plugin() de pid según `installed_plugins.json` (instalación de usuario primero) y su marketplace."""
    pdir = _plugins_dir(settings_path)
    installed = (_load_json(os.path.join(pdir, "installed_plugins.json")) or {}).get("plugins") or {}
    markets = _load_json(os.path.join(pdir, "known_marketplaces.json")) or {}
    entries = installed.get(pid) or []
    if isinstance(entries, dict):
        entries = [entries]
    entries = [e for e in entries if isinstance(e, dict)]
    inst = next((e for e in entries if e.get("scope") == "user"), entries[0] if entries else {})
    name, _, mkt = pid.partition("@")
    return scan_plugin(pid, inst.get("installPath"), _market_entry(markets, mkt, name))


def plugin_inventory(settings_path):
    """Plugins con `enabledPlugins` en true en el settings de usuario (neb incluido; lo excluye el reporte)."""
    settings = _load_json(settings_path) or {}
    ep = settings.get("enabledPlugins") if isinstance(settings.get("enabledPlugins"), dict) else {}
    return [locate_plugin(settings_path, pid) for pid, on in ep.items() if on is True]


# --------------------------------------------------------------------------- plugins: uso en los transcripts

def _plugin_events(path, plugins, bare):
    """(nombre, tipo, ts, llave de dedupe) por cada uso de un plugin en el transcript."""
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    with f:
        for n, line in enumerate(f):
            is_cmd = "<command-name>" in line
            if not is_cmd and not ('"tool_use"' in line and ("mcp__plugin_" in line or '"Skill"' in line
                                                             or '"subagent_type"' in line)):
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            msg = o.get("message") or {}
            ts = _ts(o.get("timestamp"))
            content = msg.get("content")
            if o.get("type") == "user" and is_cmd:
                texts = [content] if isinstance(content, str) else [
                    b.get("text") or "" for b in content or [] if isinstance(b, dict) and b.get("type") == "text"]
                for t in texts:
                    for m in COMMAND_RE.finditer(t):
                        cmd = m.group(1)
                        plugin, sep, sub = cmd.partition(":")
                        if sep and plugin in plugins:
                            kind = "skill" if sub in plugins[plugin]["skills"] else "command"
                        elif not sep and len(bare.get(cmd, ())) == 1:
                            plugin, kind = bare[cmd][0]
                        else:
                            continue
                        yield plugin, kind, ts, ("u", o.get("uuid") or (path, n), cmd)
            elif o.get("type") == "assistant" and isinstance(content, list):
                for b in content:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    tool, inp = b.get("name") or "", b.get("input") or {}
                    key = ("t", b.get("id") or (msg.get("id"), tool, json.dumps(inp, sort_keys=True)))
                    plugin = kind = None
                    if tool.startswith("mcp__plugin_"):
                        rest = tool[len("mcp__plugin_"):]
                        hits = [nm for nm in plugins if rest.startswith(nm + "_")]
                        plugin, kind = (max(hits, key=len) if hits else None), "mcp"
                    elif tool in ("Agent", "Task") and isinstance(inp.get("subagent_type"), str):
                        plugin, kind = inp["subagent_type"].partition(":")[0] if ":" in inp["subagent_type"] else None, "agent"
                    elif tool == "Skill" and isinstance(inp.get("skill"), str) and ":" in inp["skill"]:
                        plugin, _, sub = inp["skill"].partition(":")
                        in_cmds = plugin in plugins and sub in plugins[plugin]["commands"]
                        kind = "command" if in_cmds and sub not in plugins[plugin]["skills"] else "skill"
                    if plugin in plugins:
                        yield plugin, kind, ts, key


def plugin_usage(projects, plugins, cutoff):
    """({nombre: {tipo: [usos, último ts]}}, transcripts leídos) en la ventana; cada uso cuenta una vez aunque
    el bloque se repita en copias del transcript (--resume, forks)."""
    by_name = {p["name"]: p for p in plugins}
    bare = defaultdict(list)
    for p in plugins:
        bare_kinds = [("skill", s) for s in p["skills"]] + [("command", c) for c in p["commands"]]
        for kind, nm in bare_kinds:
            if (p["name"], kind) not in bare[nm]:
                bare[nm].append((p["name"], kind))
    usage = {p["name"]: {k: [0, None] for k in USE_KINDS} for p in plugins}
    seen = set()
    files = session_files(projects, cutoff=cutoff)
    for _mtime, path, _sid, _main in files:
        for plugin, kind, ts, key in _plugin_events(path, by_name, bare):
            if (ts is not None and ts < cutoff) or key in seen:
                continue
            seen.add(key)
            u = usage[plugin][kind]
            u[0] += 1
            if ts is not None and (u[1] is None or ts > u[1]):
                u[1] = ts
    return usage, len(files)


def classify(p, u):
    if not (p["skills"] or p["agents"] or p["commands"] or p["mcp"]):
        return NOT_AUDITABLE
    if sum(v[0] for v in u.values()) == 0:
        return DISABLE
    if p["skills"] and u["skill"][0] == 0:
        return NAME_ONLY
    return IN_USE


def project_overrides(cwd, user_settings):
    """{id: (archivo, valor)} de `enabledPlugins` en `.claude/settings.json` y `settings.local.json` del cwd
    (el local gana); se omite el archivo si es el mismo settings de usuario (cwd = home)."""
    out = {}
    for fn in ("settings.json", "settings.local.json"):
        path = os.path.join(cwd, ".claude", fn)
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(user_settings)):
            continue
        d = _load_json(path) or {}
        for pid, v in (d.get("enabledPlugins") or {}).items() if isinstance(d.get("enabledPlugins"), dict) else []:
            out[pid] = (path, v)
    return out


def _date(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "—"


def _components(p):
    parts = []
    if p["mcp"]:
        parts.append("MCP " + ", ".join("`%s`" % s for s in sorted(p["mcp"])))
    if p["hooks"]:
        parts.append("hooks " + ", ".join(sorted(p["hooks"])))
    if p["lsp"]:
        parts.append("LSP " + ", ".join("`%s`" % s for s in sorted(p["lsp"])))
    return "; ".join(parts) or "—"


def render_plugins(plugins, usage, days, nfiles, settings_path, overrides):
    audited = [p for p in plugins if not p["id"].startswith(NEB_PREFIX)]
    verdict = {p["id"]: classify(p, usage[p["name"]]) for p in audited}
    grand = sum(p["weight"]["total"] for p in audited) or 1
    audited.sort(key=lambda p: -p["weight"]["total"])
    out = ["# Plugins activos: peso contra uso (últimos %g días)" % days, "",
           "Desde %s · transcripts leídos: %d · settings: `%s` · `neb@*` excluido" % (
               _date(time.time() - days * 86400), nfiles, settings_path), "",
           "| Plugin | Peso fijo (caracteres de descripción) | Skills · agentes · comandos | "
           "Se pierde también al desactivar | Usos (MCP · agentes · skills · comandos) | Último uso | Veredicto |",
           "|---|---|---|---|---|---|---|"]
    for p in audited:
        u = usage[p["name"]]
        last = " · ".join("%s %s" % (USE_LABELS[k], _date(u[k][1])) for k in USE_KINDS if u[k][1]) or "—"
        out.append("| `%s` | %s (%.0f %%) | %d · %d · %d | %s | %s | %s | %s |" % (
            p["id"], "{:,}".format(p["weight"]["total"]), 100 * p["weight"]["total"] / grand,
            len(p["skills"]), len(p["agents"]), len(p["commands"]), _components(p),
            " · ".join(str(u[k][0]) for k in USE_KINDS), last, verdict[p["id"]]))
    dis = [p for p in audited if verdict[p["id"]] == DISABLE]
    nam = sorted((p for p in audited if verdict[p["id"]] == NAME_ONLY), key=lambda p: -p["weight"]["skills"])
    noa = [p for p in audited if verdict[p["id"]] == NOT_AUDITABLE]
    out += ["", "## Candidatos", ""]
    if not dis and not nam:
        out.append("Sin candidatos en la ventana.")
    for p in dis:
        extra = _components(p)
        out.append("- **Desactivar** `%s`: %s caracteres; cero usos en %g días. %s" % (
            p["id"], "{:,}".format(p["weight"]["total"]), days,
            "Se pierde también: %s." % extra if extra != "—" else "Sin MCP, hooks ni LSP."))
    for p in nam:
        u = usage[p["name"]]
        out.append("- **name-only** `%s`: %d skills, %s caracteres de descripciones de skills; "
                   "%d usos y cero cargas de skill en %g días." % (
                       p["id"], len(p["skills"]), "{:,}".format(p["weight"]["skills"]),
                       sum(v[0] for v in u.values()), days))
    if noa:
        out += ["", "No auditables (sin señal medible en el transcript; nunca candidatos): " + ", ".join(
            "`%s` (%s)" % (p["id"], _components(p)) for p in noa)]
    notes = []
    for p in audited:
        if p["id"] in overrides:
            path, v = overrides[p["id"]]
            notes.append("`%s` está declarado `%s` en `%s`: ese valor gana al del settings de usuario." % (
                p["id"], json.dumps(v), path))
        if p["missing"]:
            notes.append("`%s`: no se encontró su `installPath` en `installed_plugins.json`; no se midió su peso." % p["id"])
        if p["custom_paths"]:
            notes.append("`%s`: su `plugin.json` declara rutas propias de %s, que no se leen; su peso puede "
                         "quedar corto." % (p["id"], ", ".join(p["custom_paths"])))
    if notes:
        out += ["", "## Avisos", ""] + ["- " + n for n in notes]
    out += ["", "## Límites de la medición", "",
            "- El peso cuenta la `description` del frontmatter de `skills/*/SKILL.md`, `agents/*.md` y "
            "`commands/*.md`. `[asumido]` Claude Code recorta el listado de skills a un tope, así que el costo real "
            "puede ser menor que el peso.",
            "- Solo se ven los plugins en `true` del settings de usuario: no los activados solo en un settings de "
            "proyecto, local o administrado.",
            "- Un comando sin calificar (`/x`) cuenta solo si `x` coincide con un único comando o skill de los "
            "plugins activos.",
            "- Un plugin sin skills, agentes, comandos ni MCP (solo LSP o hooks) no deja rastro medible: "
            "«no auditable»."]
    return "\n".join(out)


# --------------------------------------------------------------------------- apply: la única escritura

def _indent_of(text):
    m = re.search(r"\n([ \t]+)\S", text)
    if not m:
        return 2
    return "\t" if m.group(1).startswith("\t") else len(m.group(1))


def _dumps(data, indent):
    return json.dumps(data, indent=indent, ensure_ascii=False)


def update_json(path, mutate, dumps=_dumps):
    """Relee path justo antes, aplica mutate(data) → [(clave, subclave, valor)], escribe a un temporal del mismo
    directorio, verifica que parsea, que trae los cambios y que nada más cambió, y reemplaza.
    Devuelve (cambios, None) o (None, motivo); con motivo, el archivo quedó intacto."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            raw = f.read()
    except OSError as e:
        return None, "no se pudo leer %s: %s" % (path, e)
    bom = raw.startswith("\ufeff")
    text = raw[1:] if bom else raw
    try:
        data, before = json.loads(text), json.loads(text)
    except ValueError as e:
        return None, "%s no es JSON válido (%s); no se tocó" % (path, e)
    if not isinstance(data, dict):
        return None, "%s no es un objeto JSON; no se tocó" % path
    try:
        changes = mutate(data)
    except ValueError as e:
        return None, str(e)
    nl = "\r\n" if "\r\n" in text else "\n"
    out = dumps(data, _indent_of(text)).replace("\n", nl) + (nl if text.endswith("\n") else "")
    path = os.path.realpath(path)          # un settings enlazado (dotfiles) se escribe en su destino
    fd, tmp = tempfile.mkstemp(prefix=".neb-usage-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(("\ufeff" if bom else "") + out)
        with open(tmp, encoding="utf-8-sig") as f:
            check = json.load(f)
        touched = defaultdict(dict)
        for key, sub, value in changes:
            touched[key][sub] = value
        for key in set(before) | set(check):
            want = before.get(key)
            if key in touched:
                want = dict(want or {})
                want.update(touched[key])
            if check.get(key) != want:
                raise ValueError("la clave `%s` no quedó como se esperaba" % key)
        shutil.copymode(path, tmp)         # mkstemp crea con 0600 en POSIX
        os.replace(tmp, path)
    except (OSError, ValueError) as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None, "no se escribió %s: %s" % (path, e)
    return changes, None


def cli_apply(argv):
    ap = argparse.ArgumentParser(prog="usage-tracker.py apply")
    ap.add_argument("plugin", help="id del plugin, <nombre>@<marketplace>")
    ap.add_argument("action", choices=["disable", "name-only"])
    ap.add_argument("--settings", default=os.path.join(claude_dir(), "settings.json"))
    a = ap.parse_args(argv)
    if "@" not in a.plugin:
        print("usage-tracker: el id va como <nombre>@<marketplace> (columna Plugin de `plugins`)", file=sys.stderr)
        return 2
    if a.plugin.startswith(NEB_PREFIX):
        print("usage-tracker: neb no se audita ni se aplica desde aquí", file=sys.stderr)
        return 2
    ep = (_load_json(a.settings) or {}).get("enabledPlugins")
    if not (isinstance(ep, dict) and ep.get(a.plugin) is True):
        print("usage-tracker: `%s` no está en `true` en `enabledPlugins` de %s" % (a.plugin, a.settings), file=sys.stderr)
        return 2
    skills = []
    if a.action == "name-only":
        skills = sorted(locate_plugin(a.settings, a.plugin)["skills"])
        if not skills:
            print("usage-tracker: `%s` no tiene skills que pasar a name-only" % a.plugin, file=sys.stderr)
            return 2

    def mutate(data):
        key = "enabledPlugins" if a.action == "disable" else "skillOverrides"
        if not isinstance(data.setdefault(key, {}), dict):
            raise ValueError("`%s` no es un objeto en %s; no se tocó" % (key, a.settings))
        if a.action == "disable":
            changes = [(key, a.plugin, False)]
        else:
            changes = [(key, "%s:%s" % (a.plugin.split("@")[0], s), "name-only") for s in skills]
        for k, sub, value in changes:
            data[k][sub] = value
        return changes

    changes, err = update_json(a.settings, mutate)
    if err:
        print("usage-tracker: " + err, file=sys.stderr)
        return 1
    print("Actualizado `%s`:" % a.settings)
    print("\n".join("- `%s.%s` = %s" % (k, s, json.dumps(v)) for k, s, v in changes))
    if a.action == "name-only":
        print("\nQue `skillOverrides` reconozca el nombre calificado está sin verificar (supuesto R24): "
              "en la sesión nueva, revisa que esos skills se listen sin descripción.")
    print("\nRige al abrir una sesión nueva (supuesto R25). Para revertir: %s." % (
        "volver `enabledPlugins.%s` a `true`" % a.plugin if a.action == "disable"
        else "borrar esas claves de `skillOverrides`"))
    ov = project_overrides(os.getcwd(), a.settings).get(a.plugin)
    if ov:
        print("Aviso: `%s` declara `%s` = %s, y ese valor gana al del settings de usuario." % (
            ov[0], a.plugin, json.dumps(ov[1])))
    return 0


def cli_plugins(argv):
    ap = argparse.ArgumentParser(prog="usage-tracker.py plugins")
    ap.add_argument("--days", type=float, default=PLUGINS_DAYS)
    ap.add_argument("--projects", default=os.path.join(claude_dir(), "projects"))
    ap.add_argument("--settings", default=os.path.join(claude_dir(), "settings.json"))
    a = ap.parse_args(argv)
    if _load_json(a.settings) is None:
        print("usage-tracker: no se pudo leer %s como JSON" % a.settings, file=sys.stderr)
        return 2
    plugins = plugin_inventory(a.settings)
    usage, nfiles = plugin_usage(a.projects, plugins, time.time() - a.days * 86400)
    print(render_plugins(plugins, usage, a.days, nfiles, a.settings, project_overrides(os.getcwd(), a.settings)))
    return 0


# --------------------------------------------------------------------------- CLI

def active_names(projects, req):
    """Nombres de los active_*.md de los dirs de memoria que resuelven al REQ (una sesión que solo editó
    uno de ellos no tiene por qué mencionar el slug)."""
    names = []
    try:
        dirs = [os.path.join(e.path, "memory") for e in os.scandir(projects) if e.is_dir()]
    except OSError:
        return names
    for d in dirs:
        try:
            files = [e.path for e in os.scandir(d) if e.name.startswith("active_") and e.name.endswith(".md")]
        except OSError:
            continue
        names += [os.path.basename(p) for p in files if req_of_path(p) == req]
    return names


def _cutoff_from_change_md(path):
    m = DATE_RE.search(path or "")
    if not m:
        return None
    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).timestamp() - 86400


def cli_report(argv):
    ap = argparse.ArgumentParser(prog="usage-tracker.py report")
    ap.add_argument("--days", type=float)
    ap.add_argument("--req")
    ap.add_argument("--write")
    ap.add_argument("--projects", default=os.path.join(claude_dir(), "projects"))
    a = ap.parse_args(argv)
    req = a.req
    if a.write and not req:
        m = CHANGE_RE.search(os.path.abspath(a.write))
        if not m:
            print("usage-tracker: --write espera un change MD `changes/AAAA-MM-DD-<slug>.md` o --req", file=sys.stderr)
            return 2
        req = m.group(1)
    if a.days is not None:
        cutoff = time.time() - a.days * 86400
    elif req:
        cutoff = _cutoff_from_change_md(a.write)
    else:
        cutoff = time.time() - 14 * 86400
    needles = [req] + active_names(a.projects, req) if req else None
    files = session_files(a.projects, cutoff=cutoff, must_contain=needles)
    calls, stats = measure(files)
    prices = load_pricing()
    if req:
        calls = [c for c in calls if c["req"] == req]
        stats["sessions"] = {c["session"] for c in calls}
        stats["compactions"] = [x for x in stats["compactions"] if x[0] == req]
        stats["rereads"] = [x for x in stats["rereads"] if x == req]
    if a.write:
        if not write_block(a.write, render_block(calls, stats, prices)):
            return 1
        print("usage-tracker: bloque de uso actualizado en %s" % a.write)
    title = ("Uso del REQ `%s`" % req) if req else ("Uso de los últimos %g días" % (a.days if a.days is not None else 14))
    print(render_report(calls, stats, prices, title, show_reqs=not req))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    commands = {"report": cli_report, "plugins": cli_plugins, "apply": cli_apply}
    if not argv or argv[0] not in commands:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    return commands[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
