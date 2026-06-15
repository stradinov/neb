#!/usr/bin/env python3
"""
pendings.py — backend de pendientes del dev (REQ neb-pendings-sqlite, nucleo / Sub-entrega A).

Pendings persistidos en la misma DB SQLite del logbook (reusa la infra de _db_shared):
  • create / add_note / archive / revive — CRUD + maquina de estados reversible.
  • on_work_archived — disparador "al cerrar el work ligado" (lo usa el gancho de cli_archive).
  • resolve_session_context — para pendings type='session' (lee el transcript local del work).

Enums en INGLES (la capa de presentacion, Sub-entrega C, traduce al mostrar):
  pending.status         : 'open' | 'obsolete'
  pending.obsolete_cause : 'no-longer-applies' | 'resolved-otherwise'  (NULL si status='open')

Filosofía defensiva (igual que logbook.py): el __main__ traga excepciones y sale 0.
Contrato transaccional: las funciones de logica NO commitean — el caller controla la
transaccion (en modo CLI lo hace _with_write_tx; en el gancho lo hace cli_archive).
"""

import json
import os
import re
import sqlite3
import sys
import unicodedata

from _db_shared import (
    resolve_db_path, _connect, begin_immediate,
    now_iso, posix_to_win, _whoami,
    with_write_tx as _with_write_tx, _safe_rollback,
)


_OBSOLETE_CAUSES = ("no-longer-applies", "resolved-otherwise")


# --------------------------------------------------------------------------- conexión CLI

def _db_for_cli():
    home  = os.path.expanduser("~")
    guide = posix_to_win(os.environ.get("NEB_HOME", "")) or os.path.join(home, ".claude", "neb")
    return _connect(resolve_db_path(home),
                    os.path.join(guide, "hooks", "logbook-schema.sql"))


# _with_write_tx / _safe_rollback se movieron a _db_shared (fuente única del patrón de escritura;
# los comandos CLI del logbook los reusan para simetría transaccional). Aquí se importan arriba.


# --------------------------------------------------------------------------- CRUD + estados

def create(con, ptype, context_origin, work_ref=None, session_ref=None):
    """Crea un pending. ptype ∈ {'task','session'}. context_origin = snapshot inmutable
    (no se reescribe nunca; la evolucion va a pending_note). status nace 'open'.
    Devuelve el id autoincrement (reemplaza grep máx+1)."""
    if ptype not in ("task", "session"):
        raise ValueError(f"type invalido: {ptype!r}")
    ts = now_iso()
    cur = con.execute(
        "INSERT INTO pending (type, context_origin, status, work_ref, session_ref, "
        "created_at, last_reviewed_at) VALUES (?,?, 'open', ?,?,?, NULL)",
        (ptype, context_origin, work_ref, session_ref, ts))
    return cur.lastrowid


def add_note(con, pending_id, note):
    """Agrega una entrada fechada a la bitácora. NO toca context_origin."""
    con.execute("INSERT INTO pending_note (pending_id, note, ts) VALUES (?,?,?)",
                (pending_id, note, now_iso()))


def archive(con, pending_id, cause, note=None):
    """open -> obsolete con causa auditable. Reversible (revive). No borra.
    cause ∈ {'no-longer-applies','resolved-otherwise'}."""
    if cause not in _OBSOLETE_CAUSES:
        raise ValueError(f"obsolete_cause invalida: {cause!r}")
    ts = now_iso()
    n = con.execute(
        "UPDATE pending SET status='obsolete', obsolete_cause=?, archived_at=? "
        "WHERE id=? AND status='open'", (cause, ts, pending_id)).rowcount
    if n:
        add_note(con, pending_id, note or f"[archive] obsoleto: {cause}")
    return n  # 0 = ya estaba obsolete / no existe (idempotente)


def revive(con, pending_id, note=None):
    """obsolete -> open. Limpia obsolete_cause + archived_at y deja nota de reactivacion."""
    ts = now_iso()
    n = con.execute(
        "UPDATE pending SET status='open', obsolete_cause=NULL, archived_at=NULL, "
        "last_reviewed_at=? WHERE id=? AND status='obsolete'", (ts, pending_id)).rowcount
    if n:
        add_note(con, pending_id, note or "[revive] reactivado")
    return n


def on_work_archived(con, work_id, dev, machine):
    """Disparador 'al cerrar el work ligado': auto-archiva (sin confirmacion) los pendings
    open vinculados a este work con causa 'resolved-otherwise'. SEGURO porque es reversible
    (revive) y auditable (pending_note). Usa la conexion del caller (cli_archive) y un
    SAVEPOINT propio — NO commitea (el caller controla la transaccion)."""
    con.execute("SAVEPOINT pend_on_archive")
    try:
        rows = con.execute(
            "SELECT id FROM pending WHERE work_ref=? AND status='open'", (work_id,)).fetchall()
        for (pid,) in rows:
            con.execute(
                "UPDATE pending SET status='obsolete', obsolete_cause='resolved-otherwise', "
                "archived_at=? WHERE id=? AND status='open'", (now_iso(), pid))
            con.execute("INSERT INTO pending_note (pending_id, note, ts) VALUES (?,?,?)",
                        (pid, f"[auto] work {work_id} archivado -> obsoleto (resolved-otherwise)",
                         now_iso()))
        con.execute("RELEASE SAVEPOINT pend_on_archive")
    except Exception:
        con.execute("ROLLBACK TO SAVEPOINT pend_on_archive")
        con.execute("RELEASE SAVEPOINT pend_on_archive")
        raise   # lo captura el try/except best-effort del gancho en cli_archive


def resolve_session_context(con, pending_id):
    """Para un pending type='session': devuelve el transcript_path (.jsonl local) del work
    exploratory referenciado por session_ref, para leerlo como contexto. NO hace --resume.
    Devuelve dict {work_id, transcript_path, summary} o None si no resoluble.
    El transcript sobrevive a archivar la sesion en el harness (es un archivo local)."""
    row = con.execute(
        "SELECT session_ref FROM pending WHERE id=? AND type='session'", (pending_id,)).fetchone()
    if not row or row[0] is None:
        return None
    w = con.execute(
        "SELECT id, transcript_path, payload_json FROM work WHERE id=?", (row[0],)).fetchone()
    if not w:
        return None
    summary = ""
    try:
        summary = (json.loads(w[2]) or {}).get("summary", "") if w[2] else ""
    except (ValueError, TypeError):
        pass
    return {"work_id": w[0], "transcript_path": posix_to_win(w[1] or ""), "summary": summary}


# =========================================================================== Sub-entrega B: temas y matching
# FTS5 on-demand (fuera del executescript del hook) + fallback LIKE con la misma
# interfaz; classify/reclassify (keyword-match context_origin ↔ topic.keywords);
# triage_pass (pre-filtro determinista + agrupación por topic compartido, NO O(N²)).
# Enums SIEMPRE en INGLES: topic.status='active', pending.status='open'.

# --------------------------------------------------------------------------- normalización + tokenización

def normalize(s):
    """Minúsculas + sin acentos. Espejo de 'unicode61 remove_diacritics 2' del FTS5.
    Contrato: idempotente; normalize(normalize(x)) == normalize(x).
    Entrada None/"" -> "". No quita puntuación (eso lo hace la tokenización)."""
    if not s:
        return ""
    s = s.lower()
    # NFKD descompone á -> a + combining acute; filtramos las marcas combinantes (Mn).
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s


_TOKEN_RE = re.compile(r"[a-z0-9]+")  # tras normalize: solo ascii alfanumérico


def _tokens(text):
    """Conjunto de tokens normalizados de un texto libre (context_origin)."""
    return set(_TOKEN_RE.findall(normalize(text)))


def _topic_tokens(keywords_csv):
    """Tokens de la columna keywords (CSV). 'catálogo, Pedidos' -> {'catalogo','pedidos'}.
    Multi-palabra por celda ('pedido por catalogo') -> aporta cada token suelto."""
    out = set()
    for cell in (keywords_csv or "").split(","):
        out |= _tokens(cell)
    return out


# --------------------------------------------------------------------------- FTS5 on-demand + fallback LIKE

FTS_OFFSET_TOPIC = 1_000_000_000  # separa el espacio de rowid pending vs topic en neb_fts

# DDL de la tabla virtual FTS5 — SIN triggers persistentes (decisión de diseño, BLOQUEANTE 2).
# Una sola sentencia: se ejecuta con con.execute (NO executescript) para no forzar el COMMIT
# implícito que executescript dispara, lo que cerraría una transacción de escritura abierta
# por el caller (_with_write_tx). neb_fts se sincroniza por BACKFILL/REBUILD on-demand en
# _ensure_fts, no por triggers AFTER INSERT/UPDATE/DELETE sobre pending/topic.
_FTS_CREATE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS neb_fts USING fts5("
    "  kind UNINDEXED,"          # 'pending' | 'topic'
    "  ref_id UNINDEXED,"        # pending.id o topic.id (sin offset)
    "  body,"                    # context_origin (pending) | keywords+name (topic)
    "  tokenize = 'unicode61 remove_diacritics 2'"
    ")"
)


def _fts5_available(con):
    """True si el SQLite embebido tiene el módulo FTS5 compilado."""
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp._neb_fts_probe USING fts5(x)")
        con.execute("DROP TABLE IF EXISTS temp._neb_fts_probe")
        return True
    except sqlite3.Error:
        return False


def _ensure_fts(con):
    """Garantiza neb_fts SINCRONIZADA con pending/topic para ESTA conexión, vía REBUILD
    idempotente on-demand (NO triggers). True si FTS5 utilizable; False -> usar LIKE.

    Por qué REBUILD on-demand y no triggers persistentes (BLOQUEANTE 2): los triggers
    AFTER INSERT/UPDATE/DELETE sobre pending/topic acoplaban TODA escritura cruda
    (create(), cli_create, el hook de captura del logbook) a FTS5. Si FTS5 fallaba o
    no estaba compilado, esas escrituras —incl. el logbook, ajeno a los pendings— se
    perdían silenciosamente. Sin triggers, la única ruta que toca FTS5 es el matching
    de B (classify/reclassify/triage_pass), que llama esto justo antes de consultar.

    Idempotente y defensivo: nunca re-lanza (no debe tumbar al caller ni al hook).
    NO se llama desde _connect (que corre executescript en cada Stop del hook)."""
    if not _fts5_available(con):
        return False
    try:
        con.execute(_FTS_CREATE)   # NO executescript: evita el COMMIT implícito que cerraría la tx del caller
        # REBUILD idempotente: re-sembrar desde la verdad (pending/topic). Barato a esta escala
        # y elimina la deriva que los triggers debían cubrir (inserciones crudas sin tocar FTS).
        con.execute("DELETE FROM neb_fts")
        con.execute(
            "INSERT INTO neb_fts(rowid, kind, ref_id, body) "
            "SELECT id, 'pending', id, context_origin FROM pending")
        con.execute(
            "INSERT INTO neb_fts(rowid, kind, ref_id, body) "
            "SELECT id + ?, 'topic', id, COALESCE(keywords,'')||' '||COALESCE(name,'') FROM topic",
            (FTS_OFFSET_TOPIC,))
        return True
    except sqlite3.Error as e:
        print(f"[logbook] FTS5 no disponible, usando LIKE: {e}", file=sys.stderr)
        return False


def _candidate_topics_fts(con, pending_text):
    """Ruta FTS5. Construye una MATCH query OR de los tokens del pending y la corre contra
    los rows kind='topic' de neb_fts. Devuelve [(topic_id, score)] donde score = nº de tokens
    que matchearon (proxy de relevancia; -bm25 se reserva para C)."""
    toks = _tokens(pending_text)
    if not toks:
        return []
    match_expr = " OR ".join(sorted(toks))   # 'catalogo OR pedidos OR ...'
    rows = con.execute(
        "SELECT f.ref_id, t.keywords, t.name "
        "FROM neb_fts f JOIN topic t ON t.id = f.ref_id "
        "WHERE f.kind='topic' AND f.body MATCH ? AND t.status='active'",
        (match_expr,)).fetchall()
    out = []
    for tid, kw, name in rows:
        score = len(toks & (_topic_tokens(kw) | _tokens(name)))
        if score > 0:
            out.append((tid, score))
    return out


def _candidate_topics_like(con, pending_text):
    """Ruta sin FTS5. Devuelve [(topic_id, keywords, name)] de topics activos cuyos
    keywords comparten >=1 token con el texto del pending. Pre-filtro LIKE por token
    (acota el corpus) + verificación exacta por intersección de tokens en Python."""
    toks = _tokens(pending_text)
    if not toks:
        return []
    # Pre-filtro: traer solo topics activos cuyo keywords/name LIKE alguno de los tokens.
    clauses = " OR ".join(["LOWER(keywords) LIKE ? OR LOWER(name) LIKE ?"] * len(toks))
    params = []
    for t in toks:
        like = f"%{t}%"
        params += [like, like]
    rows = con.execute(
        f"SELECT id, keywords, name FROM topic "
        f"WHERE status='active' AND ({clauses})", params).fetchall()
    # Verificación exacta por token (evita falsos positivos de substring: 'pedido' vs 'expedido').
    out = []
    for tid, kw, name in rows:
        if toks & (_topic_tokens(kw) | _tokens(name)):
            out.append((tid, kw, name))
    return out


# --------------------------------------------------------------------------- sentinel 'sin-clasificar'

SENTINEL_SLUG = "sin-clasificar"


def _ensure_sentinel(con):
    """Crea el topic sentinel 'sin-clasificar' (status='active') si no existe. Idempotente.
    Devuelve su topic_id. status en INGLES por la decisión de enums; slug/name en español (dominio).
    El sentinel nunca matchea (keywords vacías -> _topic_tokens('') = ∅): es destino explícito
    solo en la rama 'sin match' de classify."""
    con.execute(
        "INSERT OR IGNORE INTO topic (slug, name, description, keywords, status) "
        "VALUES (?, 'Sin clasificar', 'Pendientes sin tema inferido (fallback de matching)', '', 'active')",
        (SENTINEL_SLUG,))
    row = con.execute("SELECT id FROM topic WHERE slug=?", (SENTINEL_SLUG,)).fetchone()
    return row[0]


# --------------------------------------------------------------------------- derivación de prioridad (placeholder de B)

_DEFAULT_BAND  = "medium"   # banda por defecto del sentinel y de matches sin señal
_DEFAULT_SCORE = 0.0


def _derive_priority(con, topic_id, match_score):
    """Banda/score placeholder de B (C los recalcula vía compas.md). Monótona en match_score:
    más tokens compartidos -> banda más alta. NO consulta compas.md (eso es C)."""
    if match_score >= 3:
        return ("high", float(match_score))
    if match_score == 2:
        return ("medium", float(match_score))
    return ("low", float(match_score))


# --------------------------------------------------------------------------- classify / reclassify

def classify(con, pending_id, replace=True, manage_tx=True):
    """Asocia un pending a topics por keyword-match. Sin match -> sentinel 'sin-clasificar'.
    Queries de topic SIEMPRE con status='active' (INGLES). Devuelve los topic_id asignados.

    manage_tx=True (default, modo CLI): abre begin_immediate + commit/rollback propios.
    manage_tx=False (gancho de A): el caller controla la transacción (p.ej. cli_archive con
    su SAVEPOINT) — classify NO abre BEGIN IMMEDIATE ni commitea (evita 'transaction within a
    transaction')."""
    row = con.execute(
        "SELECT context_origin, status FROM pending WHERE id=?", (pending_id,)).fetchone()
    if not row:
        return []
    context_origin, _pstatus = row
    # (no clasificamos obsoletos; el caller normalmente filtra, pero guardamos por robustez)
    use_fts = _ensure_fts(con)
    sentinel_id = _ensure_sentinel(con)

    if use_fts:
        matches = _candidate_topics_fts(con, context_origin)   # [(topic_id, score)]
    else:
        cands = _candidate_topics_like(con, context_origin)    # [(topic_id, kw, name)]
        toks = _tokens(context_origin)
        matches = [(tid, len(toks & (_topic_tokens(kw) | _tokens(nm))))
                   for (tid, kw, nm) in cands]

    # excluir el sentinel de los matches reales (sus keywords son vacías, no debería aparecer)
    matches = [(tid, sc) for (tid, sc) in matches if tid != sentinel_id and sc > 0]

    if manage_tx:
        begin_immediate(con)
    try:
        if replace:
            con.execute("DELETE FROM pending_topic WHERE pending_id=?", (pending_id,))
        assigned = []
        if matches:
            best_tid = max(matches, key=lambda m: m[1])[0]
            for tid, score in matches:
                band, pscore = _derive_priority(con, tid, score)
                con.execute(
                    "INSERT INTO pending_topic (pending_id, topic_id, priority_band, priority_score, is_primary) "
                    "VALUES (?,?,?,?,?) "
                    "ON CONFLICT(pending_id, topic_id) DO UPDATE SET "
                    "priority_band=excluded.priority_band, priority_score=excluded.priority_score, "
                    "is_primary=excluded.is_primary",
                    (pending_id, tid, band, pscore, 1 if tid == best_tid else 0))
                assigned.append(tid)
        else:
            con.execute(
                "INSERT INTO pending_topic (pending_id, topic_id, priority_band, priority_score, is_primary) "
                "VALUES (?,?,?,?,1) "
                "ON CONFLICT(pending_id, topic_id) DO UPDATE SET is_primary=1",
                (pending_id, sentinel_id, _DEFAULT_BAND, _DEFAULT_SCORE))
            assigned.append(sentinel_id)
        con.execute("UPDATE pending SET last_reviewed_at=? WHERE id=?", (now_iso(), pending_id))
        if manage_tx:
            con.execute("COMMIT")
        return assigned
    except sqlite3.Error:
        if manage_tx:
            _safe_rollback(con)   # defensivo: si BEGIN IMMEDIATE falló (locked) no hay tx que revertir
        raise


def reclassify(con, since=None, manage_tx=True):
    """Re-clasifica solo el delta (pendings open nunca revisados o revisados antes de `since`).
    since=None -> delta = pendings con last_reviewed_at IS NULL (nuevos)."""
    if since is None:
        rows = con.execute(
            "SELECT id FROM pending WHERE status='open' AND archived_at IS NULL "
            "AND last_reviewed_at IS NULL").fetchall()
    else:
        rows = con.execute(
            "SELECT id FROM pending WHERE status='open' AND archived_at IS NULL "
            "AND (last_reviewed_at IS NULL OR last_reviewed_at < ?)", (since,)).fetchall()
    result = {}
    for (pid,) in rows:
        result[pid] = classify(con, pid, replace=True, manage_tx=manage_tx)
    return result


# --------------------------------------------------------------------------- triage_pass (agrupación NO O(N²))

def triage_pass(con):
    """Pase de triage: reclassify del delta + agrupar por topic compartido (no O(N^2)) +
    listar sin clasificar. Pre-filtro 100% SQL; el LLM (skill, C) solo ve los grupos resultantes.
    Devuelve {'classified': int, 'groups': [[pending_id,...]], 'unclassified': [pending_id,...]}.

    SIEMPRE corre dentro de _with_write_tx (cli_triage abre la tx), así que fuerza
    manage_tx=False en reclassify/classify para NO anidar otro BEGIN IMMEDIATE
    ('cannot start a transaction within a transaction')."""
    sentinel_id = _ensure_sentinel(con)
    reclass = reclassify(con, manage_tx=False)   # delta; la tx la maneja el caller (_with_write_tx)
    classified = len(reclass)

    # Agrupación por topic compartido. SQL self-join acotado por topic_id (indexado),
    # excluyendo el sentinel -> NO genera el producto cartesiano de todos los pendings.
    rows = con.execute(
        "SELECT a.pending_id, b.pending_id "
        "FROM pending_topic a "
        "JOIN pending_topic b ON a.topic_id = b.topic_id AND a.pending_id < b.pending_id "
        "WHERE a.topic_id != ?", (sentinel_id,)).fetchall()

    # Union-Find sobre las aristas (pending_id <-> pending_id) -> componentes conexas = grupos.
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    for a, b in rows:
        union(a, b)
    groups_map = {}
    for node in list(parent):
        groups_map.setdefault(find(node), []).append(node)
    groups = [sorted(g) for g in groups_map.values() if len(g) > 1]

    unclassified = [r[0] for r in con.execute(
        "SELECT pending_id FROM pending_topic WHERE topic_id=?", (sentinel_id,)).fetchall()]
    return {"classified": classified, "groups": groups, "unclassified": unclassified}


# =========================================================================== Sub-entrega C: recomendador + priorización
# Jerarquía de fuentes de prioridad (mayor a menor):
#   1. Criterio explícito del prompt (efímero) -> rank_by_external_criterion
#   2. compas.md (peso por tema vía objetivos; FUENTE ÚNICA del peso) -> parse_compas
#   3. Señales intrínsecas del pending (work/fase, bloqueo, urgencia, recencia)
#   4. Si insuficiente -> infer_objectives (propone, el skill pregunta, write_compas escribe)
# PERSISTENCIA en INGLES (high|medium|low); el español (alta|media|baja) es SOLO presentación.
# Reusa normalize() de B (NO la redefine).

COMPAS_NAME = "compas.md"

# Mapeo presentación (español) <-> persistencia (inglés). El núcleo DEVUELVE español
# (band/by_topic) para que el skill lo muestre; el caller TRADUCE a inglés antes de
# escribir pending_topic.priority_band (band_to_db).
_BAND_ES_TO_EN = {"alta": "high", "media": "medium", "baja": "low"}
_BAND_EN_TO_ES = {v: k for k, v in _BAND_ES_TO_EN.items()}


def band_to_db(band_es):
    """Traduce la banda de presentación (español) al enum de persistencia (inglés).
    Lo usa el caller (skill/triage) antes de escribir pending_topic.priority_band."""
    return _BAND_ES_TO_EN.get(band_es, "low")


def _band(score):
    """Banda de presentación (español) a partir del score 0..100.
    score>=67 -> alta ; 34..66 -> media ; <34 -> baja."""
    if score >= 67:
        return "alta"
    if score >= 34:
        return "media"
    return "baja"


# --------------------------------------------------------------------------- parse_compas (fuente única de pesos)

def _field_value(body, label):
    """Valor de una línea '- **Label:** valor' dentro de un bloque. Espejo de logbook._field
    (no se importa logbook para no acoplar el módulo)."""
    pat = re.compile(r"^[\s\-*]*" + re.escape(label) + r"\s*:\s*\**\s*(.+?)\s*$", re.MULTILINE)
    m = pat.search(body or "")
    return m.group(1).strip() if m else ""


def _compas_int(raw, default=0):
    """Parse defensivo a int en [0,100] con clamp. No numérico -> default."""
    try:
        v = int(re.search(r"-?\d+", str(raw)).group(0))
    except (AttributeError, ValueError, TypeError):
        return default
    return max(0, min(100, v))


def parse_compas(home=None):
    """Parsea ~/.claude/compas.md (fuente única del peso de cada tema). Defensivo:
    archivo ausente/ilegible -> {'objectives': [], 'topic_weight': {}, 'exists': False}.
    Salida:
      {'objectives': [{'name','weight','topics':[slug...],'roadmap':str|None}...],
       'topic_weight': {slug: int},   # max sobre los objetivos que cubren el tema
       'exists': bool}"""
    home = home or os.path.expanduser("~")
    path = os.path.join(home, ".claude", COMPAS_NAME)
    if not os.path.isfile(path):
        return {"objectives": [], "topic_weight": {}, "exists": False}
    try:
        with open(path, encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        return {"objectives": [], "topic_weight": {}, "exists": False}
    objectives = []
    # secciones "## Objetivo: <nombre>" hasta el próximo "## " o EOF
    for m in re.finditer(r"^##\s+Objetivo:\s*(.+?)\s*$(.*?)(?=^##\s|\Z)",
                         txt, re.MULTILINE | re.DOTALL):
        name = m.group(1).strip()
        body = m.group(2)
        weight = _compas_int(_field_value(body, "Peso"), default=0)
        temas_raw = _field_value(body, "Temas")
        topics = [normalize(t) for t in temas_raw.split(",") if t.strip()] if temas_raw else []
        roadmap = _field_value(body, "Roadmap")
        roadmap = None if (not roadmap or roadmap.strip() in ("—", "-", "")) else roadmap.strip()
        objectives.append({"name": name, "weight": weight, "topics": topics, "roadmap": roadmap})
    topic_weight = {}
    for o in objectives:
        for t in o["topics"]:
            topic_weight[t] = max(topic_weight.get(t, 0), o["weight"])
    return {"objectives": objectives, "topic_weight": topic_weight, "exists": True}


# --------------------------------------------------------------------------- helpers de recomendación

def _pending_topics(con, pending_id):
    """[(slug, is_primary), ...] de los temas del pending (pending_topic JOIN topic)."""
    return [(r[0], r[1]) for r in con.execute(
        "SELECT t.slug, pt.is_primary FROM pending_topic pt "
        "JOIN topic t ON t.id = pt.topic_id WHERE pt.pending_id=?", (pending_id,)).fetchall()]


def _roadmap_for_topics(compas, topics):
    """Si algún objetivo que cubre uno de los temas del pending declara roadmap, devuelve
    ese proyecto (el del objetivo de mayor peso); si no, None."""
    p_slugs = {t[0] for t in topics}
    best = None
    for o in compas["objectives"]:
        if o["roadmap"] and (p_slugs & set(o["topics"])):
            if best is None or o["weight"] > best[0]:
                best = (o["weight"], o["roadmap"])
    return best[1] if best else None


def _compas_rationale(compas, topics, base):
    p_slugs = [t[0] for t in topics]
    if base > 0:
        return f"compas.md: peso {base} para tema(s) {', '.join(p_slugs)}."
    return f"Sin peso en compas.md para {', '.join(p_slugs) or '(sin tema)'}; señales intrínsecas."


_URGENCY_RE = re.compile(r"urgente|cr[ií]tico|bloqueante|\bP1\b|\bP2\b", re.IGNORECASE)


def _apply_intrinsic_signals(con, pending_id, base):
    """Modula el score base ± con señales intrínsecas del pending:
      • work ligado en fase activa (work.req_state) -> +
      • bloqueo: este pending BLOQUEA a otro (pending_link.relation='blocks' saliente) -> +
      • marcadores de urgencia en context_origin (urgente/crítico/bloqueante/P1/P2) -> +
      • recencia: nunca revisado (last_reviewed_at IS NULL) -> + leve
    Clamp a [0,100]."""
    score = float(base)
    row = con.execute(
        "SELECT context_origin, work_ref, last_reviewed_at FROM pending WHERE id=?",
        (pending_id,)).fetchone()
    if not row:
        return max(0.0, min(100.0, score))
    context_origin, work_ref, last_reviewed_at = row
    # bloqueo saliente: el pending es origen de una arista 'blocks'
    blocks = con.execute(
        "SELECT count(*) FROM pending_link WHERE a=? AND relation='blocks'",
        (pending_id,)).fetchone()[0]
    if blocks:
        score += 20.0
    # work ligado en fase no terminal -> trabajo en curso, sube
    if work_ref is not None:
        wr = con.execute("SELECT req_state, archived_at FROM work WHERE id=?", (work_ref,)).fetchone()
        if wr and wr[1] is None:           # work no archivado
            score += 10.0
    # urgencia textual en el snapshot inmutable
    if context_origin and _URGENCY_RE.search(context_origin):
        score += 15.0
    # recencia: nunca evaluado por el recomendador
    if last_reviewed_at is None:
        score += 5.0
    return max(0.0, min(100.0, score))


def _scores_by_topic(con, pending_id, topics, score):
    """Prioridad POR TEMA: cada tema del pending hereda el score del pending (presentación).
    by_topic[slug] = {'band': <español>, 'score': float}. El peso por-tema individual de
    compas se refleja vía el max que ya fijó el score base; aquí desglosamos por tema con
    el peso específico de cada uno cuando difiere (para que dos temas del mismo pending
    puedan rankear distinto)."""
    out = {}
    compas = parse_compas(_scores_by_topic._home)
    for slug, _is_primary in topics:
        tw = compas["topic_weight"].get(slug, 0)
        # el tema con su propio peso compas (si existe) modula su sub-score; sin peso usa el score global
        sub = float(tw) if tw > 0 else float(score)
        out[slug] = {"band": _band(sub), "score": sub}
    return out


_scores_by_topic._home = None   # inyectado por recommend_priority (evita re-parsear compas)


def _unclassified_result(pending_id):
    return {"pending_id": pending_id, "band": "baja", "score": 0,
            "source": "unclassified", "by_topic": {},
            "rationale": "Sin tema clasificado; clasificar manualmente o ampliar keywords"}


# --------------------------------------------------------------------------- recommend_priority

def recommend_priority(con, pending_id, prompt_criterion=None, home=None):
    """Recomienda la prioridad de UN pending aplicando la jerarquía
    prompt > compas.md > señales intrínsecas. NO escribe pending_topic: devuelve el
    resultado para que el caller persista (traduciendo band a inglés vía band_to_db).
    Salida:
      {'pending_id', 'band' (alta|media|baja, SOLO presentación), 'score' (0..100),
       'source' ('prompt'|'compas'|'intrinsic'|'unclassified'),
       'by_topic' {slug: {'band','score'}}, 'rationale'}"""
    _scores_by_topic._home = home          # inyecta el home para el desglose por tema
    topics = _pending_topics(con, pending_id)
    if prompt_criterion:
        ext = rank_by_external_criterion(con, [pending_id], prompt_criterion, home=home)
        base = ext["scores"].get(pending_id, 0.0)
        source = "prompt"
        rationale = f"Criterio del prompt: {ext['rationale']}"
    else:
        if not topics or all(t[0] == SENTINEL_SLUG for t in topics):
            return _unclassified_result(pending_id)
        compas = parse_compas(home)
        base = max((compas["topic_weight"].get(t[0], 0) for t in topics), default=0)
        source = "compas" if base > 0 else "intrinsic"
        rationale = _compas_rationale(compas, topics, base)
        rm = _roadmap_for_topics(compas, topics)        # proyecto o None
        if rm:
            base = _roadmap_fine_order(con, pending_id, rm, base, home)
    score = _apply_intrinsic_signals(con, pending_id, base)   # modula ±
    by_topic = _scores_by_topic(con, pending_id, topics, score)
    return {"pending_id": pending_id, "band": _band(score), "score": score,
            "source": source, "by_topic": by_topic, "rationale": rationale}


# --------------------------------------------------------------------------- rank_by_external_criterion

_ROADMAP_HINT_RE = re.compile(r"roadmap", re.IGNORECASE)


def rank_by_external_criterion(con, pending_ids, criterion, home=None):
    """Rankea una lista de pendings según un criterio externo (texto libre del prompt o
    referencia a un roadmap). El criterio es EFÍMERO (manda en esta consulta) pero NO se
    escribe a compas.md (eso lo decide el dev vía write_compas). Salida:
      {'order': [pending_id...], 'scores': {pending_id: float}, 'rationale': str}"""
    crit_tokens = _tokens(criterion)
    # ¿el criterio referencia un roadmap? heurística: contiene 'roadmap' + un proyecto detectable
    project = None
    if _ROADMAP_HINT_RE.search(criterion or ""):
        project = _detect_roadmap_project(criterion, home)
    scores = {}
    for pid in pending_ids:
        topics = _pending_topics(con, pid)
        if project:
            base = _roadmap_fine_order(con, pid, project, 50.0, home)
        else:
            # texto libre: matchea los tokens del criterio contra tema(s) + context_origin
            base = _criterion_text_score(con, pid, crit_tokens, topics)
        scores[pid] = base
    order = sorted(pending_ids, key=lambda p: scores.get(p, 0.0), reverse=True)
    if project:
        rationale = f"orden fino por roadmap '{project}' (frontmatter priority/subsystems)"
    else:
        rationale = f"match de tokens del criterio ({', '.join(sorted(crit_tokens)) or 'ninguno'})"
    return {"order": order, "scores": scores, "rationale": rationale}


def _detect_roadmap_project(criterion, home):
    """Si el criterio cita un proyecto cuyo dir existe bajo el roadmap_dir, lo devuelve.
    Token-match contra los subdirectorios del repo roadmap. None si no resoluble."""
    roadmap_dir = os.environ.get("NEB_ROADMAP_DIR") or os.path.join(
        home or os.path.expanduser("~"), "roadmap")
    if not os.path.isdir(roadmap_dir):
        return None
    crit_tokens = _tokens(criterion)
    try:
        for entry in os.listdir(roadmap_dir):
            if entry in crit_tokens or normalize(entry) in crit_tokens:
                if os.path.isdir(os.path.join(roadmap_dir, entry)):
                    return entry
    except OSError:
        return None
    return None


def _criterion_text_score(con, pending_id, crit_tokens, topics):
    """Score 0..100 por número de tokens del criterio que matchean el tema o el
    context_origin del pending (ruta determinista; no abre FTS para no acoplar a B aquí)."""
    if not crit_tokens:
        return 0.0
    topic_toks = set()
    for slug, _ in topics:
        topic_toks |= _tokens(slug)
    ctx = con.execute("SELECT context_origin FROM pending WHERE id=?", (pending_id,)).fetchone()
    body_toks = _tokens(ctx[0]) if ctx else set()
    hits = len(crit_tokens & (topic_toks | body_toks))
    if hits == 0:
        return 0.0
    # cada match aporta hasta saturar; normalizado al nº de tokens del criterio
    return min(100.0, 100.0 * hits / max(1, len(crit_tokens)))


# --------------------------------------------------------------------------- _roadmap_fine_order (CIERRA HUECO #5)

def _read_roadmap_initiatives(project_dir):
    """Lee las iniciativas del roadmap de un proyecto. Prefiere el frontmatter de cada
    initiatives/INIT-*/initiative.md ('si diverge, gana el frontmatter'); si no hay
    initiatives/, cae a parsear la tabla maestra de roadmap.md (columna Subsistemas, CSV).
    Devuelve [{'priority','subsystems':[...],'id'}] ORDENADA alta>media>baja, luego por id."""
    inits = []
    inits_dir = os.path.join(project_dir, "initiatives")
    if os.path.isdir(inits_dir):
        try:
            names = sorted(os.listdir(inits_dir))
        except OSError:
            names = []
        for name in names:
            md = os.path.join(inits_dir, name, "initiative.md")
            if not os.path.isfile(md):
                continue
            fm = _read_frontmatter(md)
            if not fm:
                continue
            inits.append({
                "id": fm.get("id", name),
                "priority": (fm.get("priority") or "").strip().lower(),
                "subsystems": _yaml_list(fm.get("subsystems", "")),
            })
    if not inits:
        inits = _read_roadmap_master_table(os.path.join(project_dir, "roadmap.md"))
    _PR_ORDER = {"alta": 0, "media": 1, "baja": 2}
    inits.sort(key=lambda it: (_PR_ORDER.get(it["priority"], 9), str(it["id"])))
    return inits


def _read_frontmatter(md_path):
    """Extrae el bloque YAML '---...---' del tope de un .md como dict plano de strings.
    Parser mínimo (clave: valor); listas YAML '[a, b]' quedan como string crudo."""
    try:
        with open(md_path, encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        return {}
    m = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n", txt, re.DOTALL)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
        if mm:
            out[mm.group(1).strip()] = mm.group(2).strip()
    return out


def _yaml_list(raw):
    """'[catálogo, pedidos]' o 'catálogo, pedidos' -> ['catálogo','pedidos'] (sin normalizar;
    el caller normaliza por token)."""
    raw = (raw or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [c.strip() for c in raw.split(",") if c.strip()]


def _read_roadmap_master_table(roadmap_md):
    """Fallback: parsea la tabla maestra de roadmap.md
    (| ID | Nombre | Prioridad | Estado | Owner | status-since | Subsistemas |).
    Devuelve [{'id','priority','subsystems':[...]}]. La celda Subsistemas es CSV acentuado."""
    try:
        with open(roadmap_md, encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        return []
    out = []
    for line in txt.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        idc, _name, prio = cells[0], cells[1], cells[2]
        subs = cells[6]
        # saltar la fila de cabecera y la fila de separación '---'
        if idc.lower() in ("id", "") or set(idc) <= set("-: "):
            continue
        out.append({"id": idc, "priority": prio.strip().lower(),
                    "subsystems": [c.strip() for c in subs.split(",") if c.strip()]})
    return out


def _roadmap_fine_order(con, pending_id, project, base_score, home=None):
    """Afina el score usando el orden del roadmap REAL de <project>. Empareja el/los tema(s)
    del pending con los SUBSISTEMAS de las iniciativas vía normalize() + token-match dentro
    del CSV de 'Subsistemas' (roadmap real: 'catálogo, pedidos'). Default ~/roadmap,
    override NEB_ROADMAP_DIR. Roadmap ausente -> devuelve base_score (no afina)."""
    roadmap_dir = os.environ.get("NEB_ROADMAP_DIR") or os.path.join(
        home or os.path.expanduser("~"), "roadmap")
    inits = _read_roadmap_initiatives(os.path.join(roadmap_dir, project))
    if not inits:
        return base_score
    p_tokens = {normalize(t[0]) for t in _pending_topics(con, pending_id)}
    best = None
    for it in inits:                              # ya ordenadas: alta>media>baja, luego id
        sub_tokens = {normalize(s) for s in it["subsystems"]}
        if p_tokens & sub_tokens:
            best = it
            break
    if best is None:
        return base_score
    bonus = {"alta": 15.0, "media": 8.0, "baja": 3.0}.get(best["priority"], 0.0)
    return min(100.0, base_score + bonus)


# --------------------------------------------------------------------------- infer_objectives + write_compas

def infer_objectives(con, home=None):
    """Cuando compas.md no existe o la cobertura es insuficiente (>50% de pendings activos
    sin peso compas), agrupa los temas de los pendings activos en una PROPUESTA de objetivos
    (clustering simple por tema/proyecto). NO inventa pesos ni escribe compas.md: devuelve la
    propuesta para que el skill la presente al dev (AskUserQuestion) y, con OK, write_compas.
    Salida: {'proposed': [{'name','topics':[...],'suggested_weight'}...], 'reason': str}."""
    compas = parse_compas(home)
    # temas distintos de los pendings activos (excluye el sentinel)
    rows = con.execute(
        "SELECT DISTINCT t.slug FROM pending p "
        "JOIN pending_topic pt ON pt.pending_id = p.id "
        "JOIN topic t ON t.id = pt.topic_id "
        "WHERE p.status='open' AND p.archived_at IS NULL AND t.slug != ?",
        (SENTINEL_SLUG,)).fetchall()
    slugs = sorted({r[0] for r in rows})
    # razón: ausencia o cobertura insuficiente
    if not compas["exists"]:
        reason = "compas.md ausente"
    else:
        total = con.execute(
            "SELECT count(*) FROM pending WHERE status='open' AND archived_at IS NULL"
        ).fetchone()[0]
        covered = 0
        if total:
            for (pid,) in con.execute(
                    "SELECT id FROM pending WHERE status='open' AND archived_at IS NULL").fetchall():
                tps = _pending_topics(con, pid)
                if any(compas["topic_weight"].get(t[0], 0) > 0 for t in tps):
                    covered += 1
        uncovered = total - covered
        reason = f"cobertura insuficiente ({uncovered}/{total} sin peso)"
    # propuesta: un objetivo por tema (clustering trivial; el dev consolida al confirmar)
    proposed = [{"name": f"Atender {s}", "topics": [s], "suggested_weight": 50} for s in slugs]
    return {"proposed": proposed, "reason": reason}


def write_compas(home, objectives):
    """Materializa ~/.claude/compas.md con los objetivos confirmados por el dev.
    objectives = [(name, weight, [topics], roadmap_or_None), ...].
    SOLO se invoca tras OK explícito del dev (lo dispara el skill, no un test ni el núcleo
    autónomamente). Devuelve el path escrito."""
    home = home or os.path.expanduser("~")
    base = os.path.join(home, ".claude")
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, COMPAS_NAME)
    today = now_iso()[:10]
    lines = [
        "# compas.md — Brújula de priorización personal",
        "",
        "<!-- Artefacto LOCAL, NO versionado, mantenido por Claude (REQ neb-pendings-sqlite).",
        "     Fuente ÚNICA del peso de cada tema: los `topic` de la DB no llevan peso.",
        "     El recomendador parsea este archivo en CADA pase de /pendings-review.",
        "     Jerarquía de fuentes de prioridad (mayor a menor):",
        "       1. Criterio explícito del prompt (efímero, no se escribe aquí)",
        "       2. Este compas.md (peso por tema vía objetivos)",
        "       3. Señales intrínsecas del pending (work/fase, bloqueo, urgencia, recencia)",
        "       4. Si insuficiente: Claude infiere objetivos, pregunta y ESCRIBE aquí.",
        "     Editar a mano es válido; Claude respeta lo que encuentre y solo propone deltas. -->",
        "",
        "---",
        "version: 1",
        f"updated_at: {today}",
        f"owner: {_whoami()}",
        "---",
        "",
    ]
    for obj in objectives:
        name, weight, topics, roadmap = (list(obj) + [None, None, None, None])[:4]
        lines.append(f"## Objetivo: {name}")
        lines.append(f"- **Peso:** {int(weight) if weight is not None else 0}")
        lines.append(f"- **Temas:** {', '.join(topics or [])}")
        lines.append(f"- **Roadmap:** {roadmap or '—'}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


# =========================================================================== CLI mínimo (/pendings)
# Subcomandos paralelos a logbook.py (mismo estilo defensivo). De A:
#   create | note | archive | revive | show | list
# De B/C (priorización + pase): rank | infer-objectives | write-compas | triage | remember-session.
# El verbo para marcar obsoleto es 'archive' (con causa), NO 'obsolete'.

def cli_create(args):
    if len(args) < 2:
        print("uso: create <task|session> <context...>"); return
    ptype = args[0]
    context = " ".join(args[1:])
    con = _db_for_cli()
    if con is None:
        return
    pid = _with_write_tx(con, lambda c: create(c, ptype, context))
    con.close()
    print(pid)


def cli_note(args):
    if len(args) < 2:
        print("uso: note <id> <texto...>"); return
    pid = int(args[0])
    note = " ".join(args[1:])
    con = _db_for_cli()
    if con is None:
        return
    _with_write_tx(con, lambda c: add_note(c, pid, note))
    con.close()
    print(f"note OK (pending {pid}).")


def cli_archive(args):
    if len(args) < 2:
        print("uso: archive <id> <no-longer-applies|resolved-otherwise> [nota...]"); return
    pid = int(args[0])
    cause = args[1]
    note = " ".join(args[2:]) or None
    con = _db_for_cli()
    if con is None:
        return
    n = _with_write_tx(con, lambda c: archive(c, pid, cause, note))
    con.close()
    print(f"archive {'OK' if n else 'no-op'} (pending {pid}).")


def cli_revive(args):
    if not args:
        print("uso: revive <id> [nota...]"); return
    pid = int(args[0])
    note = " ".join(args[1:]) or None
    con = _db_for_cli()
    if con is None:
        return
    n = _with_write_tx(con, lambda c: revive(c, pid, note))
    con.close()
    print(f"revive {'OK' if n else 'no-op'} (pending {pid}).")


def cli_show(args):
    if not args:
        print("uso: show <id>"); return
    con = _db_for_cli()
    if con is None:
        return
    cur = con.execute("SELECT * FROM pending WHERE id=?", (args[0],))
    r = cur.fetchone()
    cols = [c[0] for c in cur.description] if r else []
    notes = [dict(zip(("note", "ts"), n))
             for n in con.execute("SELECT note, ts FROM pending_note WHERE pending_id=? ORDER BY id",
                                  (args[0],))]
    con.close()
    if not r:
        print(f"pending {args[0]} no encontrado"); return
    print(json.dumps({**dict(zip(cols, r)), "notes": notes}, ensure_ascii=False, indent=2, default=str))


def cli_list(_args):
    con = _db_for_cli()
    if con is None:
        print("[]"); return
    rows = con.execute(
        "SELECT id, type, context_origin, status, work_ref, session_ref, created_at "
        "FROM pending WHERE status='open' AND archived_at IS NULL "
        "ORDER BY created_at DESC").fetchall()
    con.close()
    print(json.dumps([
        {"id": r[0], "type": r[1], "context_origin": r[2], "status": r[3],
         "work_ref": r[4], "session_ref": r[5], "created_at": r[6]} for r in rows
    ], ensure_ascii=False, indent=2))


def cli_triage(_args):
    """Pase de triage: reclassify del delta + agrupación por tema + recomendación de prioridad
    por pending (presentación en español). El skill traduce los enums al mostrar."""
    con = _db_for_cli()
    if con is None:
        print("{}"); return
    tp = _with_write_tx(con, lambda c: triage_pass(c))
    # recomendación por pending activo (lectura, no escribe)
    items = []
    for (pid, ptype, ctx, status) in con.execute(
            "SELECT id, type, context_origin, status FROM pending "
            "WHERE status='open' AND archived_at IS NULL ORDER BY created_at DESC").fetchall():
        rec = recommend_priority(con, pid)
        items.append({"id": pid, "type": ptype, "status": status,
                      "context_origin": ctx, "band": rec["band"], "score": rec["score"],
                      "source": rec["source"], "rationale": rec["rationale"],
                      "by_topic": rec["by_topic"]})
    con.close()
    print(json.dumps({"classified": tp["classified"], "groups": tp["groups"],
                      "unclassified": tp["unclassified"], "items": items},
                     ensure_ascii=False, indent=2, default=str))


def cli_rank(args):
    """rank "<criterio>"  |  rank --roadmap <proyecto>
    Rankea los pendings activos por criterio externo (prompt > compas > intrínsecas)."""
    if not args:
        print('uso: rank "<criterio>" | rank --roadmap <proyecto>'); return
    if args[0] == "--roadmap" and len(args) >= 2:
        criterion = f"roadmap {args[1]}"
    else:
        criterion = " ".join(args)
    con = _db_for_cli()
    if con is None:
        print("{}"); return
    pids = [r[0] for r in con.execute(
        "SELECT id FROM pending WHERE status='open' AND archived_at IS NULL").fetchall()]
    res = rank_by_external_criterion(con, pids, criterion)
    con.close()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))


def cli_infer_objectives(_args):
    """Propone objetivos para compas.md (NO escribe). El skill los presenta y confirma."""
    con = _db_for_cli()
    if con is None:
        print("{}"); return
    out = infer_objectives(con)
    con.close()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


def cli_write_compas(args):
    """write-compas <json>  — escribe ~/.claude/compas.md con los objetivos confirmados.
    <json> = [["nombre", peso, ["tema",...], "roadmap|null"], ...]. Lo invoca el skill
    SOLO tras OK explícito del dev (no se autoejecuta)."""
    if not args:
        print('uso: write-compas \'[["nombre",90,["alpha"],null], ...]\''); return
    try:
        raw = json.loads(" ".join(args))
    except ValueError as e:
        print(f"JSON inválido: {e}"); return
    objectives = [(o[0], o[1], o[2], (o[3] if len(o) > 3 else None)) for o in raw]
    path = write_compas(None, objectives)
    print(f"compas.md escrito: {path}")


def cli_remember_session(args):
    """remember-session <session_work_id> [context...]  — crea un pending type='session'
    que referencia un work exploratory del logbook. Al recuperarlo, el contexto = el
    transcript local (resolve_session_context)."""
    if not args:
        print("uso: remember-session <work_id> [context...]"); return
    try:
        sref = int(args[0])
    except ValueError:
        print("work_id debe ser entero"); return
    context = " ".join(args[1:]) or f"Sesión pausada (work {sref})"
    con = _db_for_cli()
    if con is None:
        return
    pid = _with_write_tx(con, lambda c: create(c, "session", context, session_ref=sref))
    con.close()
    print(pid)


def cli_main(argv):
    cmd, rest = argv[0], argv[1:]
    if cmd == "create":
        cli_create(rest)
    elif cmd == "note":
        cli_note(rest)
    elif cmd == "archive":
        cli_archive(rest)
    elif cmd == "revive":
        cli_revive(rest)
    elif cmd == "show":
        cli_show(rest)
    elif cmd == "list":
        cli_list(rest)
    elif cmd == "triage":
        cli_triage(rest)
    elif cmd == "rank":
        cli_rank(rest)
    elif cmd == "infer-objectives":
        cli_infer_objectives(rest)
    elif cmd == "write-compas":
        cli_write_compas(rest)
    elif cmd == "remember-session":
        cli_remember_session(rest)
    else:
        print(f"subcomando desconocido: {cmd}")


_USAGE = ("uso: pendings.py <create|note|archive|revive|show|list|"
          "triage|rank|infer-objectives|write-compas|remember-session> ...")


if __name__ == "__main__":
    try:
        if len(sys.argv) >= 2:
            cli_main(sys.argv[1:])
        else:
            print(_USAGE)
    except Exception as e:
        print(f"[logbook] ERROR inesperado (pendings): {e}", file=sys.stderr)
    sys.exit(0)
