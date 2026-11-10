#!/usr/bin/env python3
"""
usage-tracker.py — gasto de tokens por REQ o por ventana de días, leído de los transcripts de Claude Code.

Uso:
  usage-tracker.py report [--days N] [--req <slug>] [--write <change MD>] [--projects <dir>]

  --days N     ventana: transcripts modificados en los últimos N días (por defecto 14 sin --req/--write).
  --req SLUG   solo las llamadas atribuidas al REQ SLUG (slug = nombre del change MD sin la fecha).
  --write MD   reemplaza el bloque entre <!-- usage-tracker-start --> y <!-- usage-tracker-end --> de MD con
               el gasto de su REQ (el slug sale del nombre de MD si no se da --req). Sin marcadores no escribe.
  --projects   raíz de los transcripts (por defecto ~/.claude/projects).

Qué cuenta (formato del transcript: supuesto R21 de methodology/platform-assumptions.md):
  - Hilo principal `<proyecto>/<sesión>.jsonl` y subagentes `<proyecto>/<sesión>/subagents/**/agent-*.jsonl`
    (incluye agentes de workflow), con el `agentType` de su `.meta.json`.
  - Una llamada por `message.id` (el transcript repite el id en una línea por bloque), sin `<synthetic>`;
    dedupe global, el archivo más viejo gana (las copias de --resume y forks no suman dos veces).
  - Atribución: una llamada del hilo principal va al último REQ cuyo change MD (`changes/AAAA-MM-DD-<slug>.md`)
    o `active_*.md` la sesión creó o editó (Write/Edit) hasta ese momento; las previas al primer toque, al
    primer REQ tocado; sin toques, «sin REQ». Una llamada de subagente va al REQ vigente en el hilo principal
    a su misma hora.

Salida: exit 0 con el reporte; exit 2 ante argumentos inválidos.
"""

import argparse
import bisect
import json
import os
import re
import statistics
import sys
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
    ap.add_argument("--projects", default=os.path.join(os.path.expanduser("~"), ".claude", "projects"))
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
    if not argv or argv[0] != "report":
        print(__doc__.strip(), file=sys.stderr)
        return 2
    return cli_report(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
