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
  pending.slug           : cita canonica persistida (NULL = resuelve por el tag [slug] de context_origin)
  pending_topic.curated  : 0 = sugerencia del matching | 1 = curado (seed / curate). El matching nunca pisa 1.
  topic.parent_id        : ejes curados = raices AXIS_ROOTS ('proyecto', 'topico') y sus hijos.

Filosofía defensiva (igual que logbook.py): el __main__ traga excepciones y sale 0.
Contrato transaccional: las funciones de logica NO commitean — el caller controla la
transaccion (en modo CLI lo hace _with_write_tx; en el gancho lo hace cli_archive).
"""

import collections
import json
import os
import re
import sqlite3
import sys
import unicodedata

from _db_shared import (
    resolve_db_path, _connect, INITIAL_SCHEMA_PATH, DbUnavailable, prepare_default_db, begin_immediate,
    now_iso, posix_to_win, _whoami,
    with_write_tx as _with_write_tx, _safe_rollback,
)
from neb_root import resolve_neb_root
import neb_paths


_OBSOLETE_CAUSES = ("no-longer-applies", "resolved-otherwise")

# Raíces de los ejes curados (topic.parent_id). Son contenedores, NO temas: nunca se sugieren por
# matching (su `name` tokenizable matchearía "proyecto"/"tópico" en medio corpus) ni se curan.
AXIS_ROOTS = ("proyecto", "topico")
# Raíz del eje antes del paso de base 3 (7.3.0): sigue en una base que no lo pasó (p. ej. un paso 2 detenido;
# el paso 3 tiene `espera`). Ahí 7.4.0 opera degradado: el eje proyecto queda vacío y los hijos de
# 'cliente' cuentan como temas sin eje. Como raíz (parent_id NULL) tampoco es un tema: no se sugiere y sus
# sugerencias se ignoran y se borran, igual que las de AXIS_ROOTS. Fuera de la raíz, el slug es libre.
LEGACY_AXIS_ROOT = "cliente"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
_IN_CHUNK = 500   # máximo de parámetros por `IN (...)` (SQLite viejos topan en 999 variables)


# --------------------------------------------------------------------------- conexión CLI

def _db_for_cli():
    # Esquema inicial del árbol de este módulo, con o sin NEB_HOME (6.48.0). Lanza UnmovedDb, antes de
    # crear nada, si la base sigue sin mudar, y crea la carpeta de datos si falta; puede lanzar DbUnavailable
    # (UnmovedDb lo es): lo atrapa cli_main una sola vez.
    return _connect(prepare_default_db(os.path.expanduser("~")), INITIAL_SCHEMA_PATH)


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
        _drop_suggestions(con, pending_id)
        add_note(con, pending_id, note or f"[archive] obsoleto: {cause}")
    return n  # 0 = ya estaba obsolete / no existe (idempotente)


def _drop_suggestions(con, pending_id):
    """Borra TODAS las sugerencias del matching (curated=0) de un pendiente que se vuelve obsoleto:
    nadie las lee (triage y rank solo miran abiertos) y eran la mayor parte de pending_topic. Lo
    curado (curated=1) se conserva. Si el pendiente se reactiva (revive), reclassify le regenera las
    sugerencias en el siguiente triage (entra al delta por no tener sugerencia vigente).
    Fuente única: la llaman archive() y on_work_archived() dentro de su transacción / SAVEPOINT.
    NO commitea. Devuelve el nº de filas borradas."""
    return con.execute(
        "DELETE FROM pending_topic WHERE pending_id=? AND curated=0", (pending_id,)).rowcount


def revive(con, pending_id, note=None):
    """obsolete -> open. Limpia obsolete_cause + archived_at y deja nota de reactivacion."""
    ts = now_iso()
    n = con.execute(
        "UPDATE pending SET status='open', obsolete_cause=NULL, archived_at=NULL, "
        "last_reviewed_at=? WHERE id=? AND status='obsolete'", (ts, pending_id)).rowcount
    if n:
        add_note(con, pending_id, note or "[revive] reactivado")
    return n


def on_work_archived(con, work_id):
    """Disparador 'al cerrar el work ligado': auto-archiva (sin confirmacion) los pendings
    open vinculados a este work con causa 'resolved-otherwise'. SEGURO porque es reversible
    (revive) y auditable (pending_note). Usa la conexion del caller (cli_archive) y un
    SAVEPOINT propio — NO commitea (el caller controla la transaccion). Como archive(), borra
    las sugerencias del matching de cada pendiente que vuelve obsoleto (_drop_suggestions)."""
    con.execute("SAVEPOINT pend_on_archive")
    try:
        rows = con.execute(
            "SELECT id FROM pending WHERE work_ref=? AND status='open'", (work_id,)).fetchall()
        for (pid,) in rows:
            con.execute(
                "UPDATE pending SET status='obsolete', obsolete_cause='resolved-otherwise', "
                "archived_at=? WHERE id=? AND status='open'", (now_iso(), pid))
            _drop_suggestions(con, pid)
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
# interfaz; classify/reclassify (keyword-match context_origin ↔ topic.keywords = SUGERENCIA
# para lo no curado); triage_pass (pre-filtro determinista + agrupación por pending_link
# entre abiertos con Union-Find, NO O(N²)).
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


# Palabras vacías que una keyword multi-palabra ('aviso al cliente', 'confirmar con') aportaría como
# tokens sueltos y que matchean cualquier texto. Se filtran del lado del TEMA (keywords + name); el
# texto del pendiente no se filtra: la intersección ya no las cuenta.
_STOPWORDS = frozenset(
    "a al ante bajo con contra de del desde en entre hacia hasta para por segun sin sobre tras "
    "el la los las un una unos unas y o u e que se su sus lo le les es son fue ser hay "
    "the of and or to in on for with by at".split())
_MIN_TOKEN_LEN = 3


def _match_tokens(text):
    """Tokens de un texto del lado del tema (keywords o name) con los que se puntúa el matching:
    sin stopwords ni tokens de menos de _MIN_TOKEN_LEN caracteres ('p1', 'ux', '7')."""
    return {t for t in _tokens(text) if len(t) >= _MIN_TOKEN_LEN and t not in _STOPWORDS}


def _topic_tokens(keywords_csv):
    """Tokens de la columna keywords (CSV). 'catálogo, Pedidos' -> {'catalogo','pedidos'}.
    Multi-palabra por celda ('pedido por catalogo') -> aporta cada token útil ('pedido', 'catalogo';
    'por' es stopword y no cuenta)."""
    out = set()
    for cell in (keywords_csv or "").split(","):
        out |= _match_tokens(cell)
    return out


# --------------------------------------------------------------------------- FTS5 on-demand + fallback LIKE

FTS_OFFSET_TOPIC = 1_000_000_000  # rowid de un tema en neb_fts (heredado de cuando convivía con pending)

# DDL de la tabla virtual FTS5 — SIN triggers persistentes (decisión de diseño, BLOQUEANTE 2).
# Una sola sentencia: se ejecuta con con.execute (NO executescript) para no forzar el COMMIT
# implícito que executescript dispara, lo que cerraría una transacción de escritura abierta
# por el caller (_with_write_tx). neb_fts se sincroniza por BACKFILL/REBUILD on-demand en
# _ensure_fts, no por triggers AFTER INSERT/UPDATE/DELETE sobre pending/topic.
_FTS_CREATE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS neb_fts USING fts5("
    "  kind UNINDEXED,"          # 'topic' (desde 7.3.0; hasta 7.2.x también 'pending')
    "  ref_id UNINDEXED,"        # topic.id (sin offset)
    "  body,"                    # keywords+name del tema
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
    """Garantiza neb_fts SINCRONIZADA con topic para ESTA conexión, vía REBUILD idempotente
    on-demand (NO triggers). True si FTS5 utilizable; False -> usar LIKE.

    Solo indexa TEMAS (kind='topic'): el matching consulta temas con el texto del pendiente como
    query, nunca cuerpos de pendientes, así que indexarlos era trabajo muerto (hasta 7.2.x se
    reindexaban todos en cada pase). El DELETE completo del rebuild borra también las filas
    kind='pending' que dejó una versión anterior; como reclassify solo reconstruye cuando el delta
    trae pendientes, triage_pass las limpia aparte con _drop_legacy_fts_rows.

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
        # REBUILD idempotente: re-sembrar desde la verdad (topic). Barato a esta escala y elimina
        # la deriva que los triggers debían cubrir (temas editados sin tocar FTS).
        con.execute("DELETE FROM neb_fts")
        con.execute(
            "INSERT INTO neb_fts(rowid, kind, ref_id, body) "
            "SELECT id + ?, 'topic', id, COALESCE(keywords,'')||' '||COALESCE(name,'') FROM topic",
            (FTS_OFFSET_TOPIC,))
        return True
    except sqlite3.Error as e:
        print(f"[logbook] FTS5 no disponible, usando LIKE: {e}", file=sys.stderr)
        return False


def _drop_legacy_fts_rows(con):
    """Borra de neb_fts las filas kind='pending' que indexaba 7.2.x, sin depender de que el delta
    de reclassify traiga pendientes (en una base madura casi todo está curado o con sugerencia
    vigente y el rebuild de _ensure_fts no corre). Sin neb_fts no hace nada; si FTS5 no está
    compilado la tabla no se puede tocar y se deja como está. Nunca re-lanza: corre dentro de la
    transacción de triage y no debe tumbarla."""
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='neb_fts'").fetchone() is None:
        return
    try:
        con.execute("DELETE FROM neb_fts WHERE kind='pending'")
    except sqlite3.Error as e:
        print(f"[logbook] no se pudieron limpiar las filas viejas de neb_fts: {e}", file=sys.stderr)


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
        "WHERE f.kind='topic' AND f.body MATCH ? AND t.status='active' AND t.slug NOT IN (?,?) "
        "AND NOT (t.slug = ? AND t.parent_id IS NULL)",
        (match_expr,) + AXIS_ROOTS + (LEGACY_AXIS_ROOT,)).fetchall()
    out = []
    for tid, kw, name in rows:
        score = len(toks & (_topic_tokens(kw) | _match_tokens(name)))
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
        f"WHERE status='active' AND slug NOT IN (?,?) AND NOT (slug = ? AND parent_id IS NULL) "
        f"AND ({clauses})",
        list(AXIS_ROOTS) + [LEGACY_AXIS_ROOT] + params).fetchall()
    # Verificación exacta por token (evita falsos positivos de substring: 'pedido' vs 'expedido').
    out = []
    for tid, kw, name in rows:
        if toks & (_topic_tokens(kw) | _match_tokens(name)):
            out.append((tid, kw, name))
    return out


# --------------------------------------------------------------------------- sentinel 'sin-clasificar'

SENTINEL_SLUG = "sin-clasificar"


def _ensure_sentinel(con):
    """Crea el topic sentinel 'sin-clasificar' (status='active') si no existe. Idempotente.
    Devuelve su topic_id. status en INGLES por la decisión de enums; slug/name en español (dominio).
    Sus keywords son vacías, pero su `name` sí participa del matching (FTS indexa keywords+name):
    por eso classify lo EXCLUYE por id de los matches — es destino explícito solo en la rama
    'sin match'. (Las raíces de AXIS_ROOTS se excluyen por slug en las rutas de candidatos, y la raíz
    LEGACY_AXIS_ROOT también.)"""
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

def _curated_topic_ids(con, pending_id):
    """topic_ids de las filas curadas (curated=1) sobre temas ACTIVOS del pending; [] si no está
    curado. Una curaduría que quedó sobre un tema archivado no cuenta: el pendiente vuelve al
    flujo de curación (mismo predicado que _HAS_CURATED_SQL)."""
    return [r[0] for r in con.execute(
        "SELECT pt.topic_id FROM pending_topic pt JOIN topic t ON t.id = pt.topic_id "
        "WHERE pt.pending_id=? AND pt.curated=1 AND t.status='active'", (pending_id,))]


# Ni el sentinel ni una raíz de eje (AXIS_ROOTS por slug; LEGACY_AXIS_ROOT solo como raíz), sobre el alias t.
# Sus parámetros: _NOT_ROOT_PARAMS.
_NOT_ROOT_SQL = "t.slug NOT IN (?,?,?) AND NOT (t.slug = ? AND t.parent_id IS NULL)"
# Sugerencia vigente = fila curated=0 sobre un tema activo que no sea el sentinel ni una raíz.
_HAS_SUGGESTION_SQL = (
    "EXISTS (SELECT 1 FROM pending_topic pt JOIN topic t ON t.id = pt.topic_id "
    "        WHERE pt.pending_id = p.id AND pt.curated = 0 AND t.status = 'active' "
    f"          AND {_NOT_ROOT_SQL})"
)
# Curado = ≥1 fila curated=1 sobre un tema ACTIVO (ver _curated_topic_ids).
_HAS_CURATED_SQL = (
    "EXISTS (SELECT 1 FROM pending_topic pt JOIN topic t ON t.id = pt.topic_id "
    "        WHERE pt.pending_id = p.id AND pt.curated = 1 AND t.status = 'active')"
)
_NOT_ROOT_PARAMS = (SENTINEL_SLUG,) + AXIS_ROOTS + (LEGACY_AXIS_ROOT,)
# Ids de las raíces de eje (parent_id NULL con slug de AXIS_ROOTS o LEGACY_AXIS_ROOT): lo que limpia
# _drop_root_suggestions. Sus parámetros: _AXIS_ROOT_PARAMS.
_AXIS_ROOT_PARAMS = AXIS_ROOTS + (LEGACY_AXIS_ROOT,)
_AXIS_ROOT_IDS_SQL = ("SELECT id FROM topic WHERE parent_id IS NULL AND slug IN "
                      f"({','.join('?' * len(_AXIS_ROOT_PARAMS))})")


def _drop_root_suggestions(con, manage_tx=False):
    """Borra las sugerencias (curated=0) sobre una raíz de eje (parent_id NULL con slug de AXIS_ROOTS o
    LEGACY_AXIS_ROOT), de cualquier pendiente; nunca una fila curated=1. Las deja un código anterior que
    sigue corriendo en una sesión abierta: 7.2.x (raíces 'cliente' y 'topico') no excluye la raíz
    'proyecto' de sus candidatos y la sugiere como tema. Sin filas así no escribe ni pide candado.
    manage_tx=True abre su propia transacción corta (reclassify en modo CLI); False: la del caller.
    Devuelve cuántas borró."""
    sel = f"SELECT 1 FROM pending_topic WHERE curated=0 AND topic_id IN ({_AXIS_ROOT_IDS_SQL}) LIMIT 1"
    if con.execute(sel, _AXIS_ROOT_PARAMS).fetchone() is None:
        return 0
    if manage_tx:
        begin_immediate(con)
    try:
        n = con.execute(f"DELETE FROM pending_topic WHERE curated=0 AND topic_id IN ({_AXIS_ROOT_IDS_SQL})",
                        _AXIS_ROOT_PARAMS).rowcount
        if manage_tx:
            con.execute("COMMIT")
        return n
    except sqlite3.Error:
        if manage_tx:
            _safe_rollback(con)
        raise


def _top_matches(con, matches):
    """Poda de las sugerencias que classify persiste: por cada eje curado (AXIS_ROOTS) solo las
    mejores SUGGESTIONS_PER_AXIS por score (desempate por slug, el mismo orden con que las lee
    _suggested_by_axis), que es todo lo que triage expone. Los temas sin eje (legado, sin raíz) se
    conservan TODOS: _effective_topics los cuenta todos para el peso de compas, y podarlos cambiaría
    la banda. Un texto largo matcheaba decenas de temas por ruido y cada uno quedaba como fila.
    Conserva el orden de entrada. classify elige la primaria (is_primary) ANTES de podar: si empata
    fuera del top de su eje y se poda, ninguna sugerencia queda primaria, y el orden de temas que
    muestra triage (is_primary DESC, slug) sale igual que cuando esa fila existía, porque tampoco
    contaba como tema efectivo."""
    if not matches:
        return matches
    info = {}
    tids = [tid for tid, _sc in matches]
    for i in range(0, len(tids), _IN_CHUNK):
        chunk = tids[i:i + _IN_CHUNK]
        for tid, slug, root in con.execute(
                "SELECT t.id, t.slug, r.slug FROM topic t LEFT JOIN topic r ON r.id = t.parent_id "
                f"WHERE t.id IN ({','.join('?' * len(chunk))})", chunk):
            info[tid] = (slug, root if root in AXIS_ROOTS else None)
    by_axis = {}
    for tid, sc in matches:
        slug, axis = info.get(tid, ("", None))
        if axis is not None:
            by_axis.setdefault(axis, []).append((-sc, slug, tid))
    keep = {tid for ranked in by_axis.values() for _k, _s, tid in sorted(ranked)[:SUGGESTIONS_PER_AXIS]}
    return [(tid, sc) for tid, sc in matches if info.get(tid, ("", None))[1] is None or tid in keep]


def classify(con, pending_id, replace=True, manage_tx=True, use_fts=None):
    """SUGIERE temas a un pending por keyword-match (filas curated=0). Sin match -> sentinel
    'sin-clasificar'. Queries de topic SIEMPRE con status='active' (INGLES). Devuelve los topic_id
    asignados. Persiste solo las mejores SUGGESTIONS_PER_AXIS por eje (más todas las de temas sin
    eje): ver _top_matches.

    Curaduría: si el pending ya tiene ≥1 fila curated=1, classify NO escribe nada y devuelve esas
    filas — la clasificación vigente es la curada (seed / curate), el matching es solo sugerencia
    para lo no curado. Con replace=True borra únicamente sus propias filas (curated=0) sobre temas
    ACTIVOS — las filas sobre temas archivados se conservan como historial, igual que en el seed;
    el upsert lleva `WHERE curated=0` para no pisar una fila curada sobre el mismo tema.

    manage_tx=True (default, modo CLI): abre begin_immediate + commit/rollback propios.
    manage_tx=False (gancho de A): el caller controla la transacción (p.ej. cli_archive con
    su SAVEPOINT) — classify NO abre BEGIN IMMEDIATE ni commitea (evita 'transaction within a
    transaction').
    use_fts: resultado de _ensure_fts ya calculado por el caller (reclassify lo hace UNA vez por
    pase: el rebuild de neb_fts es por corpus completo, no por pendiente); None -> se calcula aquí."""
    row = con.execute(
        "SELECT context_origin, status FROM pending WHERE id=?", (pending_id,)).fetchone()
    if not row:
        return []
    context_origin, _pstatus = row
    curated = _curated_topic_ids(con, pending_id)
    if curated:
        return curated                      # curado: la sugerencia no aplica, no se toca nada
    # (no clasificamos obsoletos; el caller normalmente filtra, pero guardamos por robustez)
    if use_fts is None:
        use_fts = _ensure_fts(con)
    sentinel_id = _ensure_sentinel(con)

    if use_fts:
        matches = _candidate_topics_fts(con, context_origin)   # [(topic_id, score)]
    else:
        cands = _candidate_topics_like(con, context_origin)    # [(topic_id, kw, name)]
        toks = _tokens(context_origin)
        matches = [(tid, len(toks & (_topic_tokens(kw) | _match_tokens(nm))))
                   for (tid, kw, nm) in cands]

    # excluir el sentinel de los matches reales (su name sí matchea; se excluye por id)
    matches = [(tid, sc) for (tid, sc) in matches if tid != sentinel_id and sc > 0]
    best_tid = max(matches, key=lambda m: m[1])[0] if matches else None   # primaria: antes de podar
    matches = _top_matches(con, matches)

    if manage_tx:
        begin_immediate(con)
    try:
        if replace:
            con.execute(
                "DELETE FROM pending_topic WHERE pending_id=? AND curated=0 "
                "AND topic_id IN (SELECT id FROM topic WHERE status='active')", (pending_id,))
        assigned = []
        if matches:
            for tid, score in matches:
                band, pscore = _derive_priority(con, tid, score)
                con.execute(
                    "INSERT INTO pending_topic (pending_id, topic_id, priority_band, priority_score, is_primary, curated) "
                    "VALUES (?,?,?,?,?,0) "
                    "ON CONFLICT(pending_id, topic_id) DO UPDATE SET "
                    "priority_band=excluded.priority_band, priority_score=excluded.priority_score, "
                    "is_primary=excluded.is_primary WHERE curated=0",
                    (pending_id, tid, band, pscore, 1 if tid == best_tid else 0))
                assigned.append(tid)
        else:
            con.execute(
                "INSERT INTO pending_topic (pending_id, topic_id, priority_band, priority_score, is_primary, curated) "
                "VALUES (?,?,?,?,1,0) "
                "ON CONFLICT(pending_id, topic_id) DO UPDATE SET is_primary=1 WHERE curated=0",
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
    """Re-sugiere solo el delta: pendings open SIN curaduría que (a) nunca fueron revisados,
    (b) no tienen sugerencia vigente (sus filas quedaron sobre temas archivados o solo en el
    sentinel — así un catálogo nuevo o keywords nuevas sí les llegan), o (c) fueron revisados
    antes de `since`. Los curados nunca entran al delta. Antes borra las sugerencias sobre raíces de eje
    (_drop_root_suggestions): un pendiente con otras sugerencias vigentes no entra al delta y la conservaría."""
    _drop_root_suggestions(con, manage_tx=manage_tx)
    sql = ("SELECT p.id FROM pending p WHERE p.status='open' AND p.archived_at IS NULL "
           f"AND NOT {_HAS_CURATED_SQL} "
           f"AND (p.last_reviewed_at IS NULL OR NOT {_HAS_SUGGESTION_SQL}")
    params = list(_NOT_ROOT_PARAMS)
    if since is not None:
        sql += " OR p.last_reviewed_at < ?"
        params.append(since)
    sql += ") ORDER BY p.id"
    rows = con.execute(sql, params).fetchall()
    result = {}
    use_fts = _ensure_fts(con) if rows else False   # un solo rebuild del índice por pase
    for (pid,) in rows:
        result[pid] = classify(con, pid, replace=True, manage_tx=manage_tx, use_fts=use_fts)
    return result


# --------------------------------------------------------------------------- triage_pass (agrupación NO O(N²))

def triage_pass(con):
    """Pase de triage: reclassify del delta + agrupar por `pending_link` (no O(N^2)) + listar
    los que esperan curaduría. Pre-filtro 100% SQL; el LLM (skill, C) solo ve el resultado.
    Devuelve {'classified': int, 'groups': [[pending_id,...]], 'suggested': [...], 'unclassified': [...]}:
      • groups       — componentes conexas del grafo pending_link (cualquier relation) SOLO entre
                       pendings open; con pocos valores por eje un tema compartido volvería a dar
                       un componente gigante, así que la agrupación es por vínculo explícito.
      • suggested    — open sin curaduría con ≥1 sugerencia vigente (curated=0 sobre tema activo
                       distinto del sentinel/raíces): el skill la presenta y cura con OK del dev.
      • unclassified — open sin curaduría y sin sugerencia (solo sentinel o sin filas).
      suggested ∩ unclassified = ∅ ; suggested ∪ unclassified = open sin curar.

    SIEMPRE corre dentro de _with_write_tx (cli_triage abre la tx), así que fuerza
    manage_tx=False en reclassify/classify para NO anidar otro BEGIN IMMEDIATE
    ('cannot start a transaction within a transaction')."""
    _ensure_sentinel(con)
    _drop_legacy_fts_rows(con)                   # filas 'pending' de 7.2.x, aunque el delta venga vacío
    reclass = reclassify(con, manage_tx=False)   # delta; la tx la maneja el caller (_with_write_tx)
    classified = len(reclass)

    # Aristas del grafo explícito, acotadas a pendings open en ambos extremos (un obsoleto no agrupa).
    rows = con.execute(
        "SELECT l.a, l.b FROM pending_link l "
        "JOIN pending pa ON pa.id = l.a AND pa.status='open' AND pa.archived_at IS NULL "
        "JOIN pending pb ON pb.id = l.b AND pb.status='open' AND pb.archived_at IS NULL").fetchall()

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
    groups = sorted((sorted(g) for g in groups_map.values() if len(g) > 1), key=lambda g: g[0])

    uncurated = ("SELECT p.id FROM pending p WHERE p.status='open' AND p.archived_at IS NULL "
                 f"AND NOT {_HAS_CURATED_SQL} AND {{cond}} {_HAS_SUGGESTION_SQL} ORDER BY p.id")
    suggested = [r[0] for r in con.execute(uncurated.format(cond=""), _NOT_ROOT_PARAMS)]
    unclassified = [r[0] for r in con.execute(uncurated.format(cond="NOT"), _NOT_ROOT_PARAMS)]
    return {"classified": classified, "groups": groups,
            "suggested": suggested, "unclassified": unclassified}


# =========================================================================== Sub-entrega C: recomendador + priorización
# Jerarquía de fuentes de prioridad (mayor a menor):
#   1. Criterio explícito del prompt (efímero) -> rank_by_external_criterion
#   2. Banda CURADA persistida (pending_topic.curated=1 con priority_band: pase del dev / curate)
#   3. compas.md (peso por TÓPICO vía objetivos + bonus por PROYECTO; FUENTE ÚNICA del peso) -> parse_compas
#   4. Señales intrínsecas del pending (work/fase, bloqueo, urgencia, recencia)
#   5. Si insuficiente -> infer_objectives (propone, el skill pregunta, write_compas escribe)
# PERSISTENCIA en INGLES (high|medium|low); el español (alta|media|baja) es SOLO presentación.
# Reusa normalize() de B (NO la redefine).
# Lectura por lotes: triage, rank, list e infer-objectives leen los temas de TODOS los pendientes
# involucrados en una sola consulta (_topic_rows) y parsean compas.md una vez por llamada; los helpers
# por pendiente aceptan esas filas ya leídas (`rows=`) y, sin ellas, consultan solo ese pendiente.

COMPAS_NAME = neb_paths.COMPAS_NAME
COMPAS_VERSION = 3


def compas_read_path(home=None):
    """Ruta de compas.md que se LEE: la de la carpeta de datos de Neb (`neb_paths.compas_path`) y, si ahí no
    hay archivo pero sí en `~/.claude/compas.md` (máquina que todavía no corrió la migración 8.0.0), esa.
    Si existen los dos manda el nuevo: el viejo es residuo. El respaldo a la ruta vieja sale en 9.0.0.
    Sin ninguno de los dos devuelve la nueva (parse_compas la verá ausente).
    La escritura (write_compas) va siempre a la nueva."""
    new = neb_paths.compas_path(home)
    if os.path.isfile(new):
        return new
    old = os.path.join(neb_paths.legacy_dir(home), COMPAS_NAME)
    return old if os.path.isfile(old) else new


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
    """Valor de una línea '- **Label:** valor' dentro de un bloque. Misma variante que
    `_db_shared._field` (no se importa para no acoplar el módulo; desde 6.7.1 ambas son idénticas).
    El valor va en la MISMA línea: los separadores son `[ \\t]*` (no `\\s*`) para que una línea con
    valor vacío devuelva '' en vez de capturar la línea siguiente, y la captura es `(.*?)` (no
    `(.+?)`: ante '- **Temas:**' sin espacio final, `\\**` retrocedía un asterisco y salía '*')."""
    pat = re.compile(r"^[ \t\-*]*" + re.escape(label) + r"[ \t]*:[ \t]*\**[ \t]*(.*?)[ \t]*$",
                     re.MULTILINE)
    m = pat.search(body or "")
    return m.group(1).strip() if m else ""


def _compas_int(raw, default=0):
    """Parse defensivo a int en [0,100] con clamp. No numérico -> default."""
    try:
        v = int(re.search(r"-?\d+", str(raw)).group(0))
    except (AttributeError, ValueError, TypeError):
        return default
    return max(0, min(100, v))


_EMPTY_COMPAS = {"objectives": [], "topic_weight": {}, "project_bonus": {}, "exists": False}


def _parse_project_bonus(raw):
    """'alpha=+15, beta=10' -> {'alpha': 15, 'beta': 10} (slugs normalizados, clamp 0..100).
    Entradas sin '=' o no numéricas se ignoran (defensivo, igual que _compas_int)."""
    out = {}
    for cell in (raw or "").split(","):
        if "=" not in cell:
            continue
        slug, val = cell.split("=", 1)
        slug = normalize(slug.strip())
        if slug:
            out[slug] = max(out.get(slug, 0), _compas_int(val, default=0))
    return out


def parse_compas(home=None):
    """Parsea `<datos>/compas.md` (fuente única del peso de cada tema; ruta en compas_read_path, que cae a
    `~/.claude/compas.md` mientras la migración 8.0.0 no lo mude). Defensivo:
    archivo ausente/ilegible -> {'objectives': [], 'topic_weight': {}, 'project_bonus': {}, 'exists': False}.
    Formato v3: por objetivo `- **Peso:**`, `- **Temas:**` (slugs del eje tópico) y la línea opcional
    `- **Proyectos:** alpha=+15, beta=+10` (bonus aditivo por proyecto). Las líneas de versiones
    anteriores (`- **Clientes:**`, `- **Roadmap:**`) no se reconocen: las reescribe la migración
    guiada 7.3.0 (paso `compas-proyectos`), cuyo aviso da el arranque.
    Salida:
      {'objectives': [{'name','weight','topics':[slug...],'projects':{slug:int}}...],
       'topic_weight': {slug: int},    # max sobre los objetivos que cubren el tema (eje tópico)
       'project_bonus': {slug: int},   # max sobre los objetivos que bonifican al proyecto (eje proyecto)
       'exists': bool}"""
    home = home or os.path.expanduser("~")
    path = compas_read_path(home)
    if not os.path.isfile(path):
        return dict(_EMPTY_COMPAS)
    try:
        with open(path, encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        return dict(_EMPTY_COMPAS)
    objectives = []
    # secciones "## Objetivo: <nombre>" hasta el próximo "## " o EOF
    for m in re.finditer(r"^##\s+Objetivo:\s*(.+?)\s*$(.*?)(?=^##\s|\Z)",
                         txt, re.MULTILINE | re.DOTALL):
        name = m.group(1).strip()
        body = m.group(2)
        weight = _compas_int(_field_value(body, "Peso"), default=0)
        temas_raw = _field_value(body, "Temas")
        # strip ANTES de normalize (normalize no recorta espacios): sin él, del 2º tema en adelante
        # quedaban como ' beta' y nunca ponderaban.
        topics = [normalize(t.strip()) for t in temas_raw.split(",") if t.strip()] if temas_raw else []
        projects = _parse_project_bonus(_field_value(body, "Proyectos"))
        objectives.append({"name": name, "weight": weight, "topics": topics, "projects": projects})
    topic_weight, project_bonus = {}, {}
    for o in objectives:
        for t in o["topics"]:
            topic_weight[t] = max(topic_weight.get(t, 0), o["weight"])
        for c, b in o["projects"].items():
            project_bonus[c] = max(project_bonus.get(c, 0), b)
    return {"objectives": objectives, "topic_weight": topic_weight,
            "project_bonus": project_bonus, "exists": True}


# --------------------------------------------------------------------------- lectura por lotes de pending_topic

# Fila de pending_topic JOIN topic (solo temas ACTIVOS) de un pendiente. axis = slug de la raíz
# ('proyecto' | 'topico') cuando el tema cuelga de un eje curado; None para temas sin raíz. axis_root = el tema
# es una raíz de eje (AXIS_ROOTS, o LEGACY_AXIS_ROOT sin padre): una fila sobre ella no cuenta como sugerencia.
_TopicRow = collections.namedtuple("_TopicRow", "slug is_primary axis curated band score topic_id axis_root")


def _topic_rows(con, pending_ids):
    """{pending_id: [_TopicRow...]} de los temas ACTIVOS de cada pendiente, en UNA consulta
    (por tramos de _IN_CHUNK ids) en vez de una por pendiente y por helper. Orden dentro de cada
    pendiente: is_primary DESC, slug (el de _pending_topics). Los temas archivados no se devuelven:
    quedan como historial. Un id sin filas mapea a []."""
    out = {pid: [] for pid in pending_ids}
    ids = list(out)
    for i in range(0, len(ids), _IN_CHUNK):
        chunk = ids[i:i + _IN_CHUNK]
        for pid, slug, prim, root, cur, band, score, tid, top in con.execute(
                "SELECT pt.pending_id, t.slug, pt.is_primary, r.slug, pt.curated, pt.priority_band, "
                "pt.priority_score, t.id, t.parent_id IS NULL FROM pending_topic pt "
                "JOIN topic t ON t.id = pt.topic_id "
                "LEFT JOIN topic r ON r.id = t.parent_id "
                f"WHERE t.status='active' AND pt.pending_id IN ({','.join('?' * len(chunk))}) "
                "ORDER BY pt.pending_id, pt.is_primary DESC, t.slug", chunk):
            out[pid].append(_TopicRow(slug, prim, (root if root in AXIS_ROOTS else None),
                                      cur, band, score, tid,
                                      slug in AXIS_ROOTS or (slug == LEGACY_AXIS_ROOT and bool(top))))
    return out


def _rows_for(con, pending_id, rows):
    """Las filas ya leídas por el caller (lote) o, sin ellas, las de este pendiente."""
    return rows if rows is not None else _topic_rows(con, [pending_id])[pending_id]


def _open_pending_ids(con):
    return [r[0] for r in con.execute(
        "SELECT id FROM pending WHERE status='open' AND archived_at IS NULL").fetchall()]


# --------------------------------------------------------------------------- helpers de recomendación

def _pending_topics(con, pending_id, rows=None):
    """[(slug, is_primary, axis), ...] de los temas ACTIVOS del pending (pending_topic JOIN topic).
    axis = slug de la raíz ('proyecto' | 'topico') cuando el tema cuelga de un eje curado; None para
    temas sin raíz (legado, tests). Los temas archivados no se devuelven: quedan como historial."""
    return [(r.slug, r.is_primary, r.axis) for r in _rows_for(con, pending_id, rows)]


def _curated_band(con, pending_id, rows=None):
    """(priority_band EN, priority_score) de la banda curada del pending: la fila curated=1 con
    banda, prefiriendo is_primary=1 (el tópico). None si el pending no tiene banda curada
    (sin curar, o curado sin banda -> compas aplica)."""
    cands = [r for r in _rows_for(con, pending_id, rows) if r.curated == 1 and r.band is not None]
    if not cands:
        return None
    best = min(cands, key=lambda r: (-r.is_primary, r.topic_id))
    return (best.band, best.score)


_CURATED_SCORE = {"high": 80.0, "medium": 50.0, "low": 20.0}   # score por defecto de una banda curada sin score

SUGGESTIONS_PER_AXIS = 3   # cuántas sugerencias por eje persiste classify y expone triage (por score)


def _suggested_by_axis(con, pending_id, rows=None):
    """Sugerencias del matching (curated=0, temas activos, sin sentinel/raíces) ordenadas por score
    (nº de tokens coincidentes) desc y agrupadas por eje: {'proyecto': [(slug, score)...],
    'topico': [...], None: [...]} — None = temas sin eje (legado). Score NULL va al final (como el
    ORDER BY ... DESC de SQLite); empates por slug."""
    out = {axis: [] for axis in AXIS_ROOTS}
    out[None] = []
    sug = [r for r in _rows_for(con, pending_id, rows)
           if r.curated == 0 and r.slug != SENTINEL_SLUG and not r.axis_root]
    sug.sort(key=lambda r: (r.score is None, -(r.score or 0.0), r.slug))
    for r in sug:
        out[r.axis].append((r.slug, r.score))
    return out


def _effective_topics(con, pending_id, rows=None):
    """Temas que CUENTAN para priorizar: los curados (activos) si los hay; si no, la MEJOR sugerencia
    por eje (por score del matching) más los temas sin eje (legado) y el sentinel. Un texto largo
    matchea decenas de temas por ruido; tomar el máximo de todos inflaba a 'alta' a cualquier
    pendiente sin curar que rozara un tópico de peso alto."""
    rows = _rows_for(con, pending_id, rows)
    topics = _pending_topics(con, pending_id, rows)        # (slug, is_primary, axis) activos
    cur_slugs = {r.slug for r in rows if r.curated == 1}
    if cur_slugs:
        return [t for t in topics if t[0] in cur_slugs]
    sug = _suggested_by_axis(con, pending_id, rows)
    keep = {sug[a][0][0] for a in AXIS_ROOTS if sug[a]} | {s for s, _ in sug[None]} | {SENTINEL_SLUG}
    return [t for t in topics if t[0] in keep]


def _compas_rationale(topics, base, bonus=0):
    p_slugs = [t[0] for t in topics]
    if base > 0:
        extra = f" (incluye bonus por proyecto +{bonus})" if bonus else ""
        return f"compas.md: peso {base} para tema(s) {', '.join(p_slugs)}{extra}."
    return f"Sin peso en compas.md para {', '.join(p_slugs) or '(sin tema)'}; señales intrínsecas."


_URGENCY_RE = re.compile(r"urgente|cr[ií]tico|bloqueante|\bP1\b|\bP2\b", re.IGNORECASE)


def _intrinsic_signals(con, pending_ids):
    """{pending_id: (context_origin, work_ref, last_reviewed_at, bloquea_a_otro, work_abierto)} en
    una consulta por tramo, para _apply_intrinsic_signals. Un id inexistente no aparece."""
    out = {}
    ids = list(pending_ids)
    for i in range(0, len(ids), _IN_CHUNK):
        chunk = ids[i:i + _IN_CHUNK]
        for pid, ctx, wref, rev, blocks, wopen in con.execute(
                "SELECT p.id, p.context_origin, p.work_ref, p.last_reviewed_at, "
                "EXISTS (SELECT 1 FROM pending_link l WHERE l.a = p.id AND l.relation='blocks'), "
                "EXISTS (SELECT 1 FROM work w WHERE w.id = p.work_ref AND w.archived_at IS NULL) "
                f"FROM pending p WHERE p.id IN ({','.join('?' * len(chunk))})", chunk):
            out[pid] = (ctx, wref, rev, bool(blocks), bool(wopen))
    return out


_NO_SIGNALS = object()   # centinela: "el caller no leyó las señales" (None = pendiente inexistente)


def _apply_intrinsic_signals(con, pending_id, base, signals=_NO_SIGNALS):
    """Modula el score base ± con señales intrínsecas del pending:
      • work ligado en fase activa (work no archivado) -> +
      • bloqueo: este pending BLOQUEA a otro (pending_link.relation='blocks' saliente) -> +
      • marcadores de urgencia en context_origin (urgente/crítico/bloqueante/P1/P2) -> +
      • recencia: nunca revisado (last_reviewed_at IS NULL) -> + leve
    Clamp a [0,100]. signals = la tupla de _intrinsic_signals ya leída (lote); sin ella se lee aquí."""
    score = float(base)
    if signals is _NO_SIGNALS:
        signals = _intrinsic_signals(con, [pending_id]).get(pending_id)
    if not signals:
        return max(0.0, min(100.0, score))
    context_origin, _work_ref, last_reviewed_at, blocks, work_open = signals
    if blocks:                         # bloqueo saliente: el pending es origen de una arista 'blocks'
        score += 20.0
    if work_open:                      # work ligado no archivado -> trabajo en curso, sube
        score += 10.0
    # urgencia textual en el snapshot inmutable
    if context_origin and _URGENCY_RE.search(context_origin):
        score += 15.0
    # recencia: nunca evaluado por el recomendador
    if last_reviewed_at is None:
        score += 5.0
    return max(0.0, min(100.0, score))


def _scores_by_topic(compas, topics, score):
    """Prioridad POR TEMA: cada tema del pending hereda el score del pending (presentación).
    by_topic[slug] = {'band': <español>, 'score': float}. El peso por-tema individual de
    compas se refleja vía el max que ya fijó el score base; aquí desglosamos por tema con
    el peso específico de cada uno cuando difiere (para que dos temas del mismo pending
    puedan rankear distinto)."""
    out = {}
    for slug, _is_primary, axis in topics:
        # el peso compas es por TÓPICO; un tema del eje proyecto (bonus) hereda el score global
        tw = compas["topic_weight"].get(slug, 0) if axis != "proyecto" else 0
        # el tema con su propio peso compas (si existe) modula su sub-score; sin peso usa el score global
        sub = float(tw) if tw > 0 else float(score)
        out[slug] = {"band": _band(sub), "score": sub}
    return out


def _unclassified_result(pending_id):
    return {"pending_id": pending_id, "band": "baja", "score": 0,
            "source": "unclassified", "by_topic": {},
            "rationale": "Sin tema clasificado; clasificar manualmente o ampliar keywords"}


# --------------------------------------------------------------------------- recommend_priority

def recommend_priority(con, pending_id, prompt_criterion=None, home=None, compas=None, rows=None,
                       signals=_NO_SIGNALS):
    """Recomienda la prioridad de UN pending aplicando la jerarquía
    prompt > banda curada > compas.md > señales intrínsecas. NO escribe pending_topic: devuelve
    el resultado para que el caller persista (traduciendo band a inglés vía band_to_db).

    Banda curada: si el pending tiene una fila curated=1 con priority_band (pase del dev o
    `curate --band`), esa banda ES la recomendación (source='curated'): se devuelve tal cual, sin
    compas ni señales intrínsecas, para que ningún pase automático la pise. compas.md aplica a los
    pendings sin banda curada, con el peso del eje TÓPICO + el bonus del eje PROYECTO (nunca un peso
    de `Temas:` sobre un proyecto, ni doble conteo).
    Lote (triage): compas = parse_compas ya leído una vez por llamada, rows = sus filas de
    _topic_rows, signals = su tupla de _intrinsic_signals. Sin ellos se leen aquí (compas a lo sumo
    una vez, y solo si hace falta).
    Salida:
      {'pending_id', 'band' (alta|media|baja, SOLO presentación), 'score' (0..100),
       'source' ('prompt'|'curated'|'compas'|'intrinsic'|'unclassified'),
       'by_topic' {slug: {'band','score'}}, 'rationale'}"""
    rows = _rows_for(con, pending_id, rows)
    topics = _effective_topics(con, pending_id, rows)
    if prompt_criterion:
        ext = rank_by_external_criterion(con, [pending_id], prompt_criterion)
        base = ext["scores"].get(pending_id, 0.0)
        source = "prompt"
        rationale = f"Criterio del prompt: {ext['rationale']}"
    else:
        cur = _curated_band(con, pending_id, rows)
        if cur:
            band_en, pscore = cur
            band_es = _BAND_EN_TO_ES.get(band_en, "baja")
            score = float(pscore) if pscore is not None else _CURATED_SCORE.get(band_en, 0.0)
            by_topic = {slug: {"band": band_es, "score": score} for slug, _p, _ax in topics}
            return {"pending_id": pending_id, "band": band_es, "score": score,
                    "source": "curated", "by_topic": by_topic,
                    "rationale": "Banda curada (pase del dev / curate); compas.md no aplica."}
        if not topics or all(t[0] == SENTINEL_SLUG for t in topics):
            return _unclassified_result(pending_id)
        if compas is None:
            compas = parse_compas(home)
        base = max((compas["topic_weight"].get(s, 0) for s, _p, ax in topics if ax != "proyecto"),
                   default=0)
        bonus = max((compas["project_bonus"].get(s, 0) for s, _p, ax in topics if ax == "proyecto"),
                    default=0)
        base = min(100, base + bonus)
        source = "compas" if base > 0 else "intrinsic"
        rationale = _compas_rationale(topics, base, bonus)
    score = _apply_intrinsic_signals(con, pending_id, base, signals)   # modula ±
    if compas is None:
        compas = parse_compas(home)
    by_topic = _scores_by_topic(compas, topics, score)
    return {"pending_id": pending_id, "band": _band(score), "score": score,
            "source": source, "by_topic": by_topic, "rationale": rationale}


# --------------------------------------------------------------------------- rank_by_external_criterion

def rank_by_external_criterion(con, pending_ids, criterion):
    """Rankea una lista de pendings según un criterio externo (texto libre del prompt): los tokens
    del criterio contra el/los tema(s) efectivo(s) y el context_origin de cada pendiente. El criterio
    es EFÍMERO (manda en esta consulta) pero NO se escribe a compas.md (eso lo decide el dev vía
    write_compas). Lee temas y textos de todos los pendientes en una consulta cada uno. Salida:
      {'order': [pending_id...], 'scores': {pending_id: float}, 'rationale': str}"""
    crit_tokens = _tokens(criterion)
    rows = _topic_rows(con, pending_ids)
    ctx = {}
    ids = list(pending_ids)
    for i in range(0, len(ids), _IN_CHUNK):
        chunk = ids[i:i + _IN_CHUNK]
        ctx.update(con.execute(
            f"SELECT id, context_origin FROM pending WHERE id IN ({','.join('?' * len(chunk))})",
            chunk).fetchall())
    scores = {}
    for pid in pending_ids:
        topics = _effective_topics(con, pid, rows[pid])
        scores[pid] = _criterion_text_score(crit_tokens, topics, ctx.get(pid))
    order = sorted(pending_ids, key=lambda p: scores.get(p, 0.0), reverse=True)
    rationale = f"match de tokens del criterio ({', '.join(sorted(crit_tokens)) or 'ninguno'})"
    return {"order": order, "scores": scores, "rationale": rationale}


def _criterion_text_score(crit_tokens, topics, context_origin):
    """Score 0..100 por número de tokens del criterio que matchean el tema o el
    context_origin del pending (ruta determinista; no abre FTS para no acoplar a B aquí)."""
    if not crit_tokens:
        return 0.0
    topic_toks = set()
    for slug, *_rest in topics:
        topic_toks |= _tokens(slug)
    body_toks = _tokens(context_origin) if context_origin else set()
    hits = len(crit_tokens & (topic_toks | body_toks))
    if hits == 0:
        return 0.0
    # cada match aporta hasta saturar; normalizado al nº de tokens del criterio
    return min(100.0, 100.0 * hits / max(1, len(crit_tokens)))


# --------------------------------------------------------------------------- infer_objectives + write_compas

def infer_objectives(con, home=None):
    """Cuando compas.md no existe o la cobertura es insuficiente (>50% de pendings activos
    sin peso compas), agrupa los temas de los pendings activos en una PROPUESTA de objetivos
    (clustering simple por tema). NO inventa pesos ni escribe compas.md: devuelve la
    propuesta para que el skill la presente al dev (AskUserQuestion) y, con OK, write_compas.
    Salida: {'proposed': [{'name','topics':[...],'suggested_weight'}...], 'reason': str}."""
    compas = parse_compas(home)
    # temas ACTIVOS distintos de los pendings activos, excluyendo el sentinel, las raíces y el eje
    # proyecto (los proyectos van como bonus, no como objetivo); también los hijos de la raíz 'cliente' de
    # una base que no pasó el paso 3 (son proyectos). Temas sin raíz (legado) sí se proponen.
    rows = con.execute(
        "SELECT DISTINCT t.slug FROM pending p "
        "JOIN pending_topic pt ON pt.pending_id = p.id "
        "JOIN topic t ON t.id = pt.topic_id "
        "LEFT JOIN topic r ON r.id = t.parent_id "
        "WHERE p.status='open' AND p.archived_at IS NULL AND t.status='active' "
        f"AND {_NOT_ROOT_SQL} AND COALESCE(r.slug,'') != 'proyecto' "
        "AND NOT (r.slug IS NOT NULL AND r.slug = ? AND r.parent_id IS NULL)",
        _NOT_ROOT_PARAMS + (LEGACY_AXIS_ROOT,)).fetchall()
    slugs = sorted({r[0] for r in rows})
    # razón: ausencia o cobertura insuficiente (un pending con banda curada no necesita compas)
    if not compas["exists"]:
        reason = "compas.md ausente"
    else:
        pids = _open_pending_ids(con)
        total = len(pids)
        covered = 0
        batch = _topic_rows(con, pids)
        for pid in pids:
            if _curated_band(con, pid, batch[pid]):
                covered += 1
                continue
            tps = _effective_topics(con, pid, batch[pid])
            if any(compas["topic_weight"].get(t[0], 0) > 0 for t in tps if t[2] != "proyecto"):
                covered += 1
        uncovered = total - covered
        reason = f"cobertura insuficiente ({uncovered}/{total} sin peso)"
    # propuesta: un objetivo por tema (clustering trivial; el dev consolida al confirmar)
    proposed = [{"name": f"Atender {s}", "topics": [s], "suggested_weight": 50} for s in slugs]
    return {"proposed": proposed, "reason": reason}


def _validate_objective(obj):
    """(name, weight, topics, projects) de un objetivo de 3 o 4 elementos
    [nombre, peso, [tópicos]] | [nombre, peso, [tópicos], {proyecto: bonus}]. ValueError con mensaje
    legible ante cualquier otra forma: en particular la de 5 elementos (anterior a 7.3.0, con el
    roadmap en el 4º lugar), que tomada a medias perdería los bonos por proyecto en silencio."""
    if not isinstance(obj, (list, tuple)) or len(obj) not in (3, 4):
        n = len(obj) if isinstance(obj, (list, tuple)) else "no es lista"
        hint = (" (forma anterior a 7.3.0 con roadmap: quita el 4º elemento)"
                if isinstance(obj, (list, tuple)) and len(obj) == 5 else "")
        raise ValueError(f"objetivo inválido ({n} elementos): {obj!r}; se espera "
                         f"[nombre, peso, [tópicos]] o [nombre, peso, [tópicos], {{proyecto: bonus}}]{hint}")
    name, weight, topics = obj[0], obj[1], obj[2]
    projects = obj[3] if len(obj) == 4 else None
    if not isinstance(topics, (list, tuple)):
        raise ValueError(f"objetivo {name!r}: el 3er elemento debe ser la lista de tópicos")
    bad = [t for t in topics if not isinstance(t, str)]
    if bad:
        raise ValueError(f"objetivo {name!r}: los tópicos deben ser texto (slugs); no lo son: {bad!r}")
    if projects is not None and not isinstance(projects, dict):
        raise ValueError(f"objetivo {name!r}: el 4º elemento debe ser un objeto {{proyecto: bonus}}")
    weight = 0 if weight is None else _as_int(weight, f"objetivo {name!r}: el peso")
    if projects is not None:
        projects = {c: _as_int(b, f"objetivo {name!r}: el bonus de {c!r}") for c, b in projects.items()}
    return name, weight, list(topics), projects


def _as_int(value, what):
    """Entero de un número o de un texto numérico ('60', '12.5'); ValueError legible con `what`
    ante cualquier otro tipo (null, objeto, lista, booleano) para que write-compas lo reporte como
    JSON en vez de reventar con TypeError al armar las líneas."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{what} debe ser numérico, no {value!r}")
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{what} debe ser numérico, no {value!r}") from None


def write_compas(home, objectives):
    """Materializa `<datos>/compas.md` (formato v3; `neb_paths.compas_path`) con los objetivos confirmados
    por el dev. Siempre escribe en la carpeta de datos, aunque se haya leído el residuo de `~/.claude/`: desde
    ese momento parse_compas lee el nuevo (el viejo lo retira la migración 8.0.0).
    objectives = [(name, weight, [topics][, {proyecto: bonus}]), ...] — el 4º elemento es opcional
    (bonus aditivo por proyecto, eje `proyecto`); sin él, la línea `Proyectos:` no se escribe.
    Cualquier otra forma (p. ej. la de 5 elementos con roadmap) es ValueError y no escribe nada.
    SOLO se invoca tras OK explícito del dev (lo dispara el skill, no un test ni el núcleo
    autónomamente). Devuelve el path escrito. ValueError si la carpeta de datos es un enlace (ensure_dir)."""
    parsed = [_validate_objective(o) for o in objectives]     # valida todo antes de tocar el archivo
    home = home or os.path.expanduser("~")
    path = neb_paths.compas_path(home)
    neb_paths.ensure_dir(os.path.dirname(path), root=neb_paths.data_dir(home))
    today = now_iso()[:10]
    lines = [
        "# compas.md — Brújula de priorización personal",
        "",
        "<!-- Artefacto LOCAL, NO versionado, mantenido por Claude (REQ neb-pendings-sqlite).",
        "     Fuente ÚNICA del peso de cada tema: los `topic` de la DB no llevan peso.",
        "     El recomendador parsea este archivo en CADA pase de /pendings-review.",
        "     Jerarquía de fuentes de prioridad (mayor a menor):",
        "       1. Criterio explícito del prompt (efímero, no se escribe aquí)",
        "       2. Banda curada del pendiente (pase del dev / curate) — este archivo no la pisa",
        "       3. Este compas.md (peso por tópico vía objetivos + bonus por proyecto)",
        "       4. Señales intrínsecas del pending (work/fase, bloqueo, urgencia, recencia)",
        "       5. Si insuficiente: Claude infiere objetivos, pregunta y ESCRIBE aquí.",
        "     `Temas:` = slugs del eje tópico; `Proyectos:` = slug=+bonus del eje proyecto (opcional).",
        "     Editar a mano es válido; Claude respeta lo que encuentre y solo propone deltas. -->",
        "",
        "---",
        f"version: {COMPAS_VERSION}",
        f"updated_at: {today}",
        f"owner: {_whoami()}",
        "---",
        "",
    ]
    for name, weight, topics, projects in parsed:
        lines.append(f"## Objetivo: {name}")
        lines.append(f"- **Peso:** {int(weight) if weight is not None else 0}")
        lines.append(f"- **Temas:** {', '.join(topics or [])}")
        if projects:
            cells = [f"{normalize(str(c))}=+{int(b)}" for c, b in dict(projects).items()]
            lines.append(f"- **Proyectos:** {', '.join(cells)}")
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


_ID_RE = re.compile(r"^(?:pd-|#)?(\d+)$", re.IGNORECASE)  # acepta 183 | #183 | PD-183


def resolve_pending_ref(con, ref):
    """Resuelve una cita de pendiente a fila(s) de la DB.

    `ref` numérico (`183`, `#183`, `PD-183`) → resuelve por id (rowid) — cita canónica.
    `ref` no numérico → 1º la columna `pending.slug` (kind 'slug', única por índice);
    2º el tag exacto `[slug]` en `context_origin` (citas históricas de pendings sin columna);
    3º substring libre. Devuelve (kind, rows) donde kind ∈ {'id','slug','slug-exact','slug-loose'}
    y rows es lista de sqlite3.Row. El id markdown histórico NO es clave (colisiona y se
    reasignó en la migración a neb.db)."""
    m = _ID_RE.match(str(ref).strip())
    if m:
        rows = con.execute("SELECT * FROM pending WHERE id=?", (int(m.group(1)),)).fetchall()
        return ("id", rows)
    slug = str(ref).strip().lstrip("[").rstrip("]")
    rows = con.execute("SELECT * FROM pending WHERE slug=?", (slug,)).fetchall()
    if rows:
        return ("slug", rows)
    rows = con.execute("SELECT * FROM pending WHERE context_origin LIKE ? ORDER BY id",
                       ("%[" + slug + "]%",)).fetchall()
    if rows:
        return ("slug-exact", rows)
    rows = con.execute("SELECT * FROM pending WHERE context_origin LIKE ? ORDER BY id",
                       ("%" + slug + "%",)).fetchall()
    return ("slug-loose", rows)


def cli_show(args):
    if not args:
        print("uso: show <id|#id|PD-id|[slug]|slug>"); return
    con = _db_for_cli()
    if con is None:
        return
    con.row_factory = sqlite3.Row
    kind, rows = resolve_pending_ref(con, args[0])
    if not rows:
        con.close()
        print(f"pending {args[0]} no encontrado "
              f"(cita por id de neb.db o por [slug]; el #NNN del markdown histórico no resuelve)")
        return
    if len(rows) > 1:
        # ambigüedad por slug/substring: lista candidatos para desambiguar por id
        cand = [{"id": r["id"], "status": r["status"],
                 "context_origin": (r["context_origin"] or "")[:120]} for r in rows]
        con.close()
        print(json.dumps({"ambiguous": True, "matched_by": kind,
                          "count": len(cand), "candidates": cand,
                          "hint": "varios match; reintenta con `show <id>`"},
                         ensure_ascii=False, indent=2))
        return
    r = rows[0]
    cols = r.keys()
    notes = [dict(zip(("note", "ts"), n))
             for n in con.execute("SELECT note, ts FROM pending_note WHERE pending_id=? ORDER BY id",
                                  (r["id"],))]
    con.close()
    print(json.dumps({**dict(zip(cols, r)), "matched_by": kind, "notes": notes},
                     ensure_ascii=False, indent=2, default=str))


def pending_axes(con, pending_id, rows=None):
    """Ejes del pending para presentación: {'proyecto': slug|None, 'topico': slug|None, 'curated': bool,
    'suggested_proyecto': slug|None, 'suggested_topico': slug|None, 'suggestions': [slug...]}.
    proyecto/topico salen de las filas curadas (activas); para un pendiente sin curar,
    suggested_* es la MEJOR sugerencia del matching por eje (por score) y suggestions trae hasta
    SUGGESTIONS_PER_AXIS por eje (más las de temas sin eje), ordenadas por score.
    rows = sus filas de _topic_rows ya leídas (lote); sin ellas se leen aquí."""
    rows = _rows_for(con, pending_id, rows)
    out = {"proyecto": None, "topico": None, "curated": False,
           "suggested_proyecto": None, "suggested_topico": None, "suggestions": []}
    for r in rows:
        if r.curated == 1:
            out["curated"] = True
            if r.axis in AXIS_ROOTS:
                out[r.axis] = r.slug
    if not out["curated"]:
        sug = _suggested_by_axis(con, pending_id, rows)
        for axis in AXIS_ROOTS:
            if sug[axis]:
                out[f"suggested_{axis}"] = sug[axis][0][0]
            out["suggestions"] += [s for s, _ in sug[axis][:SUGGESTIONS_PER_AXIS]]
        out["suggestions"] += [s for s, _ in sug[None][:SUGGESTIONS_PER_AXIS]]
    return out


def axis_catalog(con):
    """{'proyecto': [slug...], 'topico': [slug...]} — hijos ACTIVOS de cada raíz, ordenados. Es la
    vía de lectura del catálogo para el skill (qué valores admite `curate` / los filtros de `triage`)."""
    out = {axis: [] for axis in AXIS_ROOTS}
    for slug, axis in con.execute(
            "SELECT t.slug, r.slug FROM topic t JOIN topic r ON r.id = t.parent_id "
            "WHERE t.status='active' AND r.slug IN (?,?) ORDER BY t.slug", AXIS_ROOTS).fetchall():
        out[axis].append(slug)
    return out


def cli_list(_args):
    """Volcado plano de los pendings open (bajo nivel / debug). Sin filtros: los filtros por eje
    viven en `triage`, que es lo que consume el skill."""
    con = _db_for_cli()
    if con is None:
        print("[]"); return
    rows = con.execute(
        "SELECT id, type, context_origin, status, work_ref, session_ref, created_at, slug "
        "FROM pending WHERE status='open' AND archived_at IS NULL "
        "ORDER BY created_at DESC").fetchall()
    items = []
    batch = _topic_rows(con, [r[0] for r in rows])
    for r in rows:
        ax = pending_axes(con, r[0], batch[r[0]])
        items.append({"id": r[0], "slug": r[7], "type": r[1], "context_origin": r[2], "status": r[3],
                      "proyecto": ax["proyecto"], "topico": ax["topico"], "curated": ax["curated"],
                      "work_ref": r[4], "session_ref": r[5], "created_at": r[6]})
    con.close()
    print(json.dumps(items, ensure_ascii=False, indent=2))


def _parse_flags(args, flags):
    """Parser mínimo de `--flag valor` (repetible). Devuelve ({flag: [valores]}, [posicionales])."""
    values = {f: [] for f in flags}
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in flags:
            if i + 1 >= len(args):
                raise ValueError(f"falta el valor de {a}")
            values[a].append(args[i + 1])
            i += 2
        elif a.startswith("--"):
            raise ValueError(f"flag desconocido: {a}")
        else:
            positional.append(a)
            i += 1
    return values, positional


# Curado en el eje <raíz> con alguno de los slugs dados (filtros de triage, en SQL).
_CURATED_ON_AXIS_SQL = (
    "EXISTS (SELECT 1 FROM pending_topic pt JOIN topic t ON t.id = pt.topic_id "
    "        JOIN topic r ON r.id = t.parent_id "
    "        WHERE pt.pending_id = p.id AND pt.curated = 1 AND t.status = 'active' "
    "          AND r.slug = ? AND t.slug IN ({marks}))"
)


def cli_triage(args):
    """Pase de triage: reclassify del delta + agrupación por pending_link + recomendación de
    prioridad por pending (presentación en español). Filtros opcionales `--proyecto <slug>` /
    `--topico <slug>` (por ejes curados, repetibles; se aplican en SQL) acotan items, groups,
    suggested y unclassified al subconjunto filtrado. Lee compas.md una sola vez y los temas de
    todos los pendientes en una consulta. El skill traduce los enums al mostrar."""
    try:
        flags, _pos = _parse_flags(args, ("--proyecto", "--topico"))
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)); return
    want = {"proyecto": set(flags["--proyecto"]), "topico": set(flags["--topico"])}
    con = _db_for_cli()
    if con is None:
        print("{}"); return
    catalog = axis_catalog(con)
    unknown = sorted(set().union(*(want[axis] - set(catalog[axis]) for axis in AXIS_ROOTS)))
    if unknown:
        # un filtro que no es hijo activo del eje es error (no "sin pendientes"): JSON explícito
        con.close()
        print(json.dumps({"ok": False, "error": f"filtro desconocido: {unknown}", "catalog": catalog},
                         ensure_ascii=False)); return
    tp = _with_write_tx(con, lambda c: triage_pass(c))
    # recomendación por pending activo (lectura, no escribe)
    sql = ("SELECT p.id, p.type, p.context_origin, p.status, p.slug FROM pending p "
           "WHERE p.status='open' AND p.archived_at IS NULL")
    params = []
    for axis in AXIS_ROOTS:
        if want[axis]:
            sql += " AND " + _CURATED_ON_AXIS_SQL.format(marks=",".join("?" * len(want[axis])))
            params += [axis] + sorted(want[axis])
    pend = con.execute(sql + " ORDER BY p.created_at DESC", params).fetchall()
    ids = [r[0] for r in pend]
    batch = _topic_rows(con, ids)
    signals = _intrinsic_signals(con, ids)
    compas = parse_compas()
    items = []
    for (pid, ptype, ctx, status, slug) in pend:
        ax = pending_axes(con, pid, batch[pid])
        rec = recommend_priority(con, pid, compas=compas, rows=batch[pid], signals=signals.get(pid))
        items.append({"id": pid, "slug": slug, "type": ptype, "status": status,
                      "proyecto": ax["proyecto"], "topico": ax["topico"], "curated": ax["curated"],
                      "suggested_proyecto": ax["suggested_proyecto"], "suggested_topico": ax["suggested_topico"],
                      "suggestions": ax["suggestions"],
                      "context_origin": ctx, "band": rec["band"], "score": rec["score"],
                      "source": rec["source"], "rationale": rec["rationale"],
                      "by_topic": rec["by_topic"]})
    con.close()
    filtered = bool(want["proyecto"] or want["topico"])
    keep = set(ids)
    groups = [g for g in tp["groups"] if not filtered or (set(g) & keep)]
    print(json.dumps({"classified": tp["classified"], "groups": groups,
                      "suggested": [p for p in tp["suggested"] if not filtered or p in keep],
                      "unclassified": [p for p in tp["unclassified"] if not filtered or p in keep],
                      "catalog": catalog, "items": items},
                     ensure_ascii=False, indent=2, default=str))


def cli_rank(args):
    """rank "<criterio>"
    Rankea los pendings activos por un criterio externo en texto libre (efímero)."""
    if not args or args[0].startswith("--"):
        print('uso: rank "<criterio>"'); return
    criterion = " ".join(args)
    con = _db_for_cli()
    if con is None:
        print("{}"); return
    open_rows = con.execute(
        "SELECT id, slug FROM pending WHERE status='open' AND archived_at IS NULL").fetchall()
    res = rank_by_external_criterion(con, [r[0] for r in open_rows], criterion)
    # cita canónica por id para el skill (si el slug es NULL, se cita PD-<id>)
    res["slugs"] = {str(r[0]): r[1] for r in open_rows}
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
    """write-compas <json>  — escribe `<datos>/compas.md` (v3) con los objetivos confirmados.
    <json> = [["nombre", peso, ["topico",...]], ["nombre", peso, ["topico",...], {"proyecto": bonus}], ...]
    (el 4º elemento es opcional). Un error (JSON inválido, objetivo con otra forma —p. ej. la de 5
    elementos con roadmap, anterior a 7.3.0—) sale como {"ok": false, "error"} y no escribe nada.
    Lo invoca el skill SOLO tras OK explícito del dev (no se autoejecuta)."""
    if not args:
        print("uso: write-compas '[[\"nombre\",90,[\"alpha\"],{\"beta\":10}], ...]'"); return
    try:
        raw = json.loads(" ".join(args))
        if not isinstance(raw, list):
            raise ValueError("se espera una lista de objetivos")
        path = write_compas(None, raw)
    except (ValueError, TypeError) as e:   # json.JSONDecodeError es ValueError; TypeError: red de seguridad
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)); return
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


# =========================================================================== curaduría (ejes) + backfill de slug
# (el score por defecto de una banda curada es _CURATED_SCORE, compartido con recommend_priority)


def _axis_topic_id(con, axis, slug):
    """id del tema <slug> ACTIVO que cuelga de la raíz <axis>. ValueError si no existe (o si se
    intenta curar una raíz / el sentinel)."""
    if slug in AXIS_ROOTS or slug == SENTINEL_SLUG:
        raise ValueError(f"{slug!r} no es un tema curable")
    row = con.execute(
        "SELECT t.id FROM topic t JOIN topic r ON r.id = t.parent_id "
        "WHERE t.slug=? AND t.status='active' AND r.slug=?", (slug, axis)).fetchone()
    if not row:
        raise ValueError(f"{axis} desconocido o archivado: {slug!r}")
    return row[0]


def _resolve_one(con, ref):
    """id único de una cita EXACTA (id | PD-id | slug de la columna | tag [slug] exacto) para una
    ESCRITURA. ValueError si no resuelve, es ambigua o solo resuelve por substring (`slug-loose`):
    una cita parcial o mal tecleada no debe curar ni vincular al pendiente equivocado (eso lo
    admite solo `show`, que es lectura)."""
    kind, rows = resolve_pending_ref(con, ref)
    if not rows:
        raise ValueError(f"pendiente no encontrado: {ref!r}")
    if kind == "slug-loose":
        raise ValueError(f"cita no exacta: {ref!r} (usa PD-<id> o el slug completo)")
    if len(rows) > 1:
        raise ValueError(f"cita ambigua ({kind}): {ref!r} -> {[r[0] for r in rows]}")
    return rows[0][0]


def curate(con, pending_id, proyecto=None, topico=None, slug=None, band=None, related=None, score=None):
    """Escribe la clasificación CURADA de un pending (la que manda sobre el matching):
      • proyecto / topico: exactamente UNA fila curated=1 por eje (reemplaza la fila curada previa
        del mismo eje; borra las sugerencias curated=0 sobre temas activos); is_primary=1 solo en
        el tópico.
      • band ('alta'|'media'|'baja', presentación): se persiste en inglés en las filas curadas del
        pending; sin band, se conserva la banda curada previa si la había (NULL si no: compas aplica).
        score: priority_score explícito (p.ej. el del pase); sin él, 80/50/20 según la banda.
      • slug: cita canónica (kebab-case, única entre todos los pendings).
      • related: citas (id|slug) a vincular como pending_link 'related' (agrupación en triage).
    NO toca context_origin. NO commitea: el caller controla la transacción. Devuelve el estado final.
    Lanza ValueError con mensaje legible ante cualquier entrada inválida (el CLI lo emite como JSON)."""
    row = con.execute("SELECT id, slug FROM pending WHERE id=?", (pending_id,)).fetchone()
    if not row:
        raise ValueError(f"pendiente no encontrado: {pending_id}")
    if band is not None and band not in _BAND_ES_TO_EN:
        raise ValueError(f"banda inválida: {band!r} (alta|media|baja)")
    if slug is not None:
        if not _SLUG_RE.match(slug):
            raise ValueError(f"slug inválido: {slug!r} (kebab-case: a-z, 0-9, guiones)")
        taken = con.execute("SELECT id FROM pending WHERE slug=? AND id!=?", (slug, pending_id)).fetchone()
        if taken:
            raise ValueError(f"slug ya usado por PD-{taken[0]}: {slug!r}")
    axes = {}
    if proyecto is not None:
        axes["proyecto"] = _axis_topic_id(con, "proyecto", proyecto)
    if topico is not None:
        axes["topico"] = _axis_topic_id(con, "topico", topico)

    prev = _curated_band(con, pending_id)
    band_en = _BAND_ES_TO_EN[band] if band else (prev[0] if prev else None)
    if score is None:
        score = (_CURATED_SCORE.get(band_en) if band else (prev[1] if prev else None))
        if band_en and score is None:
            score = _CURATED_SCORE.get(band_en)

    for axis, tid in axes.items():
        # reemplazo por eje: fuera la fila curada previa del mismo eje (si es otro tema)
        con.execute(
            "DELETE FROM pending_topic WHERE pending_id=? AND curated=1 AND topic_id != ? AND topic_id IN "
            "(SELECT t.id FROM topic t JOIN topic r ON r.id = t.parent_id WHERE r.slug=?)",
            (pending_id, tid, axis))
        con.execute(
            "INSERT INTO pending_topic (pending_id, topic_id, priority_band, priority_score, is_primary, curated) "
            "VALUES (?,?,?,?,?,1) "
            "ON CONFLICT(pending_id, topic_id) DO UPDATE SET priority_band=excluded.priority_band, "
            "priority_score=excluded.priority_score, is_primary=excluded.is_primary, curated=1",
            (pending_id, tid, band_en, score, 1 if axis == "topico" else 0))
    if band is not None:
        # la banda es del PENDIENTE: se aplica a TODAS sus filas curadas (ambos ejes), no solo a
        # la del eje que se acaba de escribir — si no, la fila primaria (tópico) conservaría la
        # banda vieja y _curated_band la devolvería.
        n = con.execute("UPDATE pending_topic SET priority_band=?, priority_score=? "
                        "WHERE pending_id=? AND curated=1", (band_en, score, pending_id)).rowcount
        if n == 0:
            raise ValueError(f"PD-{pending_id} no está curado: indica --proyecto/--topico junto con --band")
    if axes:
        # las sugerencias del matching sobre temas activos quedan superadas por la curaduría
        con.execute(
            "DELETE FROM pending_topic WHERE pending_id=? AND curated=0 AND topic_id IN "
            "(SELECT id FROM topic WHERE status='active')", (pending_id,))
    if slug is not None:
        con.execute("UPDATE pending SET slug=? WHERE id=?", (slug, pending_id))
    links_added = 0
    for ref in (related or []):
        other = _resolve_one(con, ref)
        if other == pending_id:
            raise ValueError("un pendiente no se relaciona consigo mismo")
        links_added += con.execute(
            "INSERT OR IGNORE INTO pending_link (a, b, relation) VALUES (?,?,'related')",
            (pending_id, other)).rowcount
    con.execute("UPDATE pending SET last_reviewed_at=? WHERE id=?", (now_iso(), pending_id))
    ax = pending_axes(con, pending_id)
    cur = _curated_band(con, pending_id)
    return {"pending_id": pending_id,
            "slug": con.execute("SELECT slug FROM pending WHERE id=?", (pending_id,)).fetchone()[0],
            "proyecto": ax["proyecto"], "topico": ax["topico"],
            "band": (_BAND_EN_TO_ES.get(cur[0]) if cur else None), "links_added": links_added}


_TAG_RE = re.compile(r"^\s*(?:\d+\.\s*)?\**\s*\[([a-z0-9][a-z0-9\-]*)\]")


def _leading_tag(context_origin):
    """Tag `[slug]` al inicio del context_origin (tolera el prefijo `NN. ` y `**` del markdown
    migrado). None si no hay tag inicial."""
    m = _TAG_RE.match(context_origin or "")
    return m.group(1) if m else None


def backfill_slugs(con, dry_run=False, skip_ids=(), reserved=()):
    """Rellena pending.slug desde el tag `[slug]` inicial de context_origin para las filas sin slug,
    SOLO cuando ese tag es único en toda la tabla y no lo usa ya otro pendiente (los tags repetidos
    quedan NULL y siguen resolviendo por el fallback de resolve_pending_ref). Idempotente: una
    segunda corrida no cambia nada. NO commitea. Devuelve el nº de filas actualizadas.
    dry_run=True: solo cuenta (sirve para el DRY-RUN del seed, incluso en una DB sin migrar donde
    `slug` aún no existe); skip_ids / reserved: pendientes y slugs que otro paso va a asignar."""
    has_slug = "slug" in {r[1] for r in con.execute("PRAGMA table_info(pending)").fetchall()}
    if not has_slug and not dry_run:
        raise RuntimeError("pending.slug no existe: la DB no está migrada (abrir con _connect)")
    rows = con.execute(
        f"SELECT id, context_origin, {'slug' if has_slug else 'NULL'} FROM pending ORDER BY id").fetchall()
    counts = {}
    for _pid, ctx, _slug in rows:
        t = _leading_tag(ctx)
        if t:
            counts[t] = counts.get(t, 0) + 1
    taken = {s for _pid, _ctx, s in rows if s} | set(reserved)
    skip = set(skip_ids)
    n = 0
    for pid, ctx, slug in rows:
        if slug or pid in skip:
            continue
        t = _leading_tag(ctx)
        if not t or counts.get(t, 0) != 1 or t in taken:
            continue
        if dry_run:
            n += 1
        else:
            n += con.execute("UPDATE pending SET slug=? WHERE id=? AND slug IS NULL", (t, pid)).rowcount
        taken.add(t)
    return n


def cli_curate(args):
    """curate <id|PD-id|slug> [--proyecto <slug>] [--topico <slug>] [--slug <slug>]
    [--band alta|media|baja] [--relacionado <id|slug>]...  — SIEMPRE imprime JSON a stdout
    ({"ok": true, ...} | {"ok": false, "error": ...}) porque el wrapper del skill descarta stderr."""
    try:
        flags, pos = _parse_flags(args, ("--proyecto", "--topico", "--slug", "--band", "--relacionado"))
        if len(pos) != 1:
            raise ValueError("uso: curate <id|slug> [--proyecto p] [--topico t] [--slug s] "
                             "[--band alta|media|baja] [--relacionado ref]...")
        for f in ("--proyecto", "--topico", "--slug", "--band"):
            if len(flags[f]) > 1:
                raise ValueError(f"{f} solo admite un valor")
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)); return
    con = _db_for_cli()
    if con is None:
        print(json.dumps({"ok": False, "error": "DB inaccesible"})); return
    try:
        def _do(c):
            pid = _resolve_one(c, pos[0])
            return curate(c, pid,
                          proyecto=(flags["--proyecto"] or [None])[0],
                          topico=(flags["--topico"] or [None])[0],
                          slug=(flags["--slug"] or [None])[0],
                          band=(flags["--band"] or [None])[0],
                          related=flags["--relacionado"])
        out = _with_write_tx(con, _do)
        print(json.dumps({"ok": True, **out}, ensure_ascii=False))
    except ValueError as e:
        _safe_rollback(con)   # with_write_tx solo revierte OperationalError; aquí cerramos la tx abierta
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
    finally:
        con.close()


def cli_backfill_slugs(_args):
    """backfill-slugs — rellena pending.slug desde el tag [slug] inicial (solo tags únicos). JSON a stdout."""
    con = _db_for_cli()
    if con is None:
        print(json.dumps({"ok": False, "error": "DB inaccesible"})); return
    n = _with_write_tx(con, backfill_slugs)
    con.close()
    print(json.dumps({"ok": True, "backfilled": n}))


def cli_main(argv):
    # Windows: la consola cp1252 no puede imprimir Unicode (→, ↔, acentos) del context_origin;
    # reconfigurar stdout/stderr a UTF-8 (errors='replace') evita UnicodeEncodeError en list/show/triage.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        _dispatch(argv[0], argv[1:])
    except DbUnavailable as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False))


def _dispatch(cmd, rest):
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
    elif cmd == "curate":
        cli_curate(rest)
    elif cmd == "backfill-slugs":
        cli_backfill_slugs(rest)
    else:
        print(f"subcomando desconocido: {cmd}")


_USAGE = ("uso: pendings.py <create|note|archive|revive|show|list|"
          "triage|rank|infer-objectives|write-compas|remember-session|curate|backfill-slugs> ...")


if __name__ == "__main__":
    try:
        if len(sys.argv) >= 2:
            cli_main(sys.argv[1:])
        else:
            print(_USAGE)
    except Exception as e:
        print(f"[logbook] ERROR inesperado (pendings): {e}", file=sys.stderr)
    sys.exit(0)
