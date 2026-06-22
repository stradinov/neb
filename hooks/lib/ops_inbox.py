#!/usr/bin/env python3
"""ops_inbox.py — helper determinístico del hook ops-capture (pieza 2a).

Separa la lógica testeable del hook: resolver el directorio del inbox, nombrar el
archivo, leer el transcript JSONL, y el GATE de actividad operativa (extraer los
fragmentos que parecen operativos). Si no hay fragmentos, el hook NO invoca el
modelo — ahorra costo/latencia en cada SessionEnd.

Lectura en **streaming con ventana**: `extract_operational_excerpts_from_file`
recorre el transcript línea por línea (RAM O(max_excerpts), no materializa el
archivo completo — relevante para transcripts grandes) y, si hay más hits que el
tope, conserva los primeros N/2 y los últimos N/2 con una marca del medio omitido
(no se pierde el final de la sesión, sin cargar todo a memoria).

Agnóstico de dominio: el vocabulario de señales es genérico; el overlay lo amplía
vía env `NEB_OPS_SIGNALS_EXTRA` (regex extra). NO contiene credenciales ni reglas
de dominio. NO llama a `datetime`/`random` (el caller pasa el timestamp).
"""
import json
import os
import re
from collections import deque

INBOX_ENV = "NEB_OPS_INBOX_DIR"
DEFAULT_INBOX_SUBPATH = (".claude", "ops-inbox")

# Señales operativas genéricas (agnósticas de dominio). El overlay amplía con
# NEB_OPS_SIGNALS_EXTRA (uno o más regex unidos por '|').
_BASE_SIGNALS = [
    r"\bssh\b", r"\bscp\b", r"\brsync\b", r"\bsftp\b",
    r"\bmysql\b", r"\bmysqldump\b", r"\bpsql\b",
    r"\bsystemctl\b", r"\bservice\s+\S+\s+(restart|reload|stop|start|status)\b",
    r"\bdeploy(ment)?\b", r"\bbackup\b", r"\brestore\b", r"\brollback\b",
    r"\bec2-user@", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    r"\.pem\b", r"\.ppk\b", r"\bcron(tab)?\b", r"\bvhost\b", r"\bcertbot\b",
    r"\bGRANT\b", r"\bALTER\s+TABLE\b", r"\bCREATE\s+(TABLE|INDEX|USER|DATABASE)\b",
    r"\bDROP\s+(TABLE|DATABASE|USER|INDEX)\b", r"\bsudo\b", r"\baws\s+\w",
]

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

# Marca insertada en el medio cuando se trunca por la ventana (formato con {n}).
TRUNCATION_MARK = "[... {n} fragmentos operativos del medio omitidos por límite de ventana ...]"


def resolve_inbox_dir(env=None, home=None):
    """Directorio del inbox: `NEB_OPS_INBOX_DIR` si está, si no `~/.claude/ops-inbox/`."""
    env = os.environ if env is None else env
    home = os.path.expanduser("~") if home is None else home
    configured = env.get(INBOX_ENV)
    if configured:
        return os.path.expanduser(configured)
    return os.path.join(home, *DEFAULT_INBOX_SUBPATH)


def _sanitize(token):
    token = _SAFE.sub("-", str(token if token is not None else "")).strip("-")
    return token or "unknown"


def inbox_filename(project, session_id, stamp):
    """Nombre del archivo de inbox. `stamp` lo provee el caller (p.ej. 'YYYYMMDD-HHMMSS')."""
    return f"{_sanitize(stamp)}-{_sanitize(project)}-{_sanitize(session_id)}.inbox.md"


def _compile_signals(env=None):
    env = os.environ if env is None else env
    patterns = list(_BASE_SIGNALS)
    extra = env.get("NEB_OPS_SIGNALS_EXTRA")
    if extra:
        patterns.append(extra)
    return re.compile("|".join(patterns), re.IGNORECASE)


def _flatten_event_text(evt):
    """Texto plausible de un evento del transcript (estructura tolerante)."""
    chunks = []

    def walk(x):
        if isinstance(x, str):
            chunks.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(evt)
    return " ".join(c for c in chunks if c)


def iter_event_texts(transcript_path):
    """Generador **streaming**: yield el texto de cada línea del transcript JSONL,
    sin acumular el archivo en memoria. Una línea no-JSON se usa tal cual.
    Defensivo: si no se puede abrir, no produce nada."""
    try:
        f = open(transcript_path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                evt = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                yield raw
                continue
            text = _flatten_event_text(evt)
            if text:
                yield text


def transcript_text_lines(transcript_path):
    """Lista completa de líneas de texto legible (materializa todo). Útil para
    tests/usos que necesiten la lista; el hook usa la variante streaming."""
    return list(iter_event_texts(transcript_path))


def extract_operational_excerpts(lines, env=None, max_excerpts=60):
    """GATE sobre una lista ya materializada: las líneas que matchean una señal
    operativa (hasta `max_excerpts`, recorte simple). Vacío ⇒ el hook no invoca el
    modelo. (La variante de archivo con ventana es `extract_operational_excerpts_from_file`.)"""
    rx = _compile_signals(env)
    hits = []
    for ln in lines:
        if rx.search(ln):
            hits.append(ln.strip())
            if len(hits) >= max_excerpts:
                break
    return hits


def extract_operational_excerpts_from_file(transcript_path, env=None, max_excerpts=60):
    """GATE en **streaming con ventana**: recorre el transcript línea por línea
    (RAM O(max_excerpts), no materializa el archivo) y devuelve los fragmentos con
    señal operativa. Si el total de hits supera `max_excerpts`, conserva los
    primeros N/2 y los últimos N/2 (vía `deque`) e inserta `TRUNCATION_MARK` con el
    número de fragmentos del medio omitidos — así no se pierde el final de la
    sesión ni se carga todo a memoria. Vacío ⇒ el hook no invoca el modelo."""
    rx = _compile_signals(env)
    head_cap = max(1, max_excerpts // 2)
    tail_cap = max(1, max_excerpts - head_cap)
    head = []
    tail = deque(maxlen=tail_cap)
    total = 0
    for text in iter_event_texts(transcript_path):
        if not rx.search(text):
            continue
        total += 1
        line = text.strip()
        if len(head) < head_cap:
            head.append(line)
        else:
            tail.append(line)
    if total <= max_excerpts:
        return head + list(tail)
    omitted = total - len(head) - len(tail)
    result = list(head)
    if omitted > 0:
        result.append(TRUNCATION_MARK.format(n=omitted))
    result.extend(tail)
    return result


def write_inbox(inbox_dir, filename, content):
    """Escribe el archivo de inbox (crea el dir). Devuelve el path."""
    os.makedirs(inbox_dir, exist_ok=True)
    path = os.path.join(inbox_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
