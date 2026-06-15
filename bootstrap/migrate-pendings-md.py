#!/usr/bin/env python3
"""
migrate-pendings-md.py — migrador one-shot del pendings.md (Markdown plano) al backend
SQLite neb.db (REQ neb-pendings-sqlite). Reusa los módulos de hooks/lib/ (pendings.py +
_db_shared.py): NO reimplementa create/classify/_ensure_sentinel ni el patrón de escritura.

Qué hace:
  • Parsea el pendings.md (formato canónico de workflow/pendings.md, tolerando variaciones):
      - Secciones  "## <area> — <tema> — <fecha>"  → un `topic` (slug = el área).
      - Ítems       "NNN. **[slug] ... — <Estado>.**"  → un `pending` por ítem ACTIVO.
      - Sub-ítems   "- **(a) ...**" / "- ✅ **(a)** ..."  → un `pending` propio por sub-ítem
                    ACTIVO, ligado al padre vía `pending_link` (related | depends).
  • Solo migra ACTIVOS: el header del ítem/sub-ítem con "CERRADO/DESCARTADO/RESUELTO/✅…"
    se OMITE; pero un ítem cerrado con sub-ítems activos SÍ aporta esos sub-ítems.
  • context_origin del pending = el texto íntegro del ítem/sub-ítem (snapshot autocontenido).
  • status = 'open'; work_ref / session_ref = None (no se infieren aquí).
  • Asocia cada pending a su topic (vía pendings.classify, que cae al sentinel si no matchea).

Contrato CLI:
  py bootstrap/migrate-pendings-md.py [--from <path>] [--db <path>] [--apply]
    --from <path>  pendings.md a leer (default: ~/.claude/pendings.md). SOLO LECTURA.
    --db   <path>  neb.db destino (default: resolve_db_path(~)). En DRY-RUN no se abre/escribe.
    --apply        ejecuta la migración dentro de una transacción (with_write_tx),
                   idempotente (no duplica: chequeo por context_origin existente).
                   SIN --apply = DRY-RUN: parsea, simula el mapeo y REPORTA sin tocar nada.

Idempotencia (--apply): antes de crear un pending se busca uno con el MISMO context_origin;
si existe, se reusa su id (no se duplica) y solo se re-asegura topic + link. Re-correr el
migrador no crea filas nuevas.

Seguridad: NUNCA escribe en el pendings.md. En DRY-RUN no abre ninguna DB. Tests con tempfile.

Nota PII: este script (que viaja al repo público) usa ejemplos GENÉRICOS (alpha/beta) en
docstrings y tests. Los nombres reales de cliente que vivan en el pendings.md del dev se
migran como datos LOCALES a su neb.db (no se publica) — el código no los hardcodea.
"""

import argparse
import os
import re
import sys

# Reusa la infra de hooks/lib (misma técnica que bootstrap/migrate-neb-db.py).
_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "lib")
sys.path.insert(0, _LIB)

import _db_shared          # noqa: E402
import pendings            # noqa: E402

_SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "hooks", "logbook-schema.sql")


# =========================================================================== heurística de estado

# Marcadores de estado CERRADO/terminal en el header de un ítem o sub-ítem → se OMITE.
# El header es la PRIMERA línea (la que trae "NNN." o "(a)"); buscamos estos tokens ahí.
# Insensible a mayúsculas/acentos vía pendings.normalize (espejo del matcher de B).
_CLOSED_TOKENS = (
    "cerrado", "cerrada", "descartado", "descartada",
    "resuelto", "resuelta", "obsoleto", "obsoleta",
)


def _is_closed_header(header_line):
    """True si la PRIMERA línea del ítem/sub-ítem marca estado terminal (se omite).

    Reglas (juicio sobre el texto del header, no sobre el cuerpo completo):
      • Contiene un token de cierre ('cerrado', 'descartado', 'resuelto', ...) → cerrado.
      • Empieza con '✅' (check de cierre del dev) → cerrado.
    El '✅' inline a mitad de línea NO cierra por sí solo (marca un sub-paso hecho dentro
    de un ítem que puede seguir activo); solo el de cabecera o un token explícito cierran.
    """
    norm = pendings.normalize(header_line)
    # '✅' al inicio del contenido (tras el número/viñeta) = cierre del ítem.
    stripped = header_line.lstrip()
    # quitar "NNN." o "- " de viñeta para ver el primer glifo real de contenido
    stripped = re.sub(r"^\d+\.\s*", "", stripped)
    stripped = re.sub(r"^[-*]\s*", "", stripped)
    if stripped.startswith("✅"):   # ✅
        return True
    return any(tok in norm for tok in _CLOSED_TOKENS)


# =========================================================================== parser

# Encabezado de sección: "## <texto>". El área (slug del topic) = primer segmento antes de " — ".
_SECTION_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")

# Línea de ítem numerado: "NNN. ..." (puede traer "✅" antes o después del número).
_ITEM_RE = re.compile(r"^(?P<num>\d+)\.\s+(?P<rest>.*\S)\s*$")

# Línea de sub-ítem: "- **(a) ...**" / "- ✅ **(a)** ..." / "- **(a.1) ...**".
# Captura la etiqueta "(a)" / "(g.1)" para nombrar el link. Sangría variable (4 u 8 espacios).
_SUBITEM_RE = re.compile(
    r"^(?P<indent>\s+)[-*]\s+(?:✅\s*)?\*\*\((?P<label>[a-z](?:\.\d+)?)\)")

# Sub-ítem que es prerequisito/bloqueante del padre → relación 'depends' (juicio del texto).
_DEPENDS_RE = re.compile(
    r"prerequisit|prerrequisit|prereq|bloquea|bloquean|depende|dependen|requiere|requieren|"
    r"bloqueante|antes de|previo",
    re.IGNORECASE)

# Slug del ítem: "**[algun-slug] ...". Solo informativo (título legible para el reporte).
_SLUG_RE = re.compile(r"\*\*\[(?P<slug>[^\]]+)\]")


def _slugify_area(title):
    """Área de la sección → slug kebab-case del topic. El área es el primer segmento del
    título antes de ' — ' (em dash) o ' - ', recortando además un paréntesis descriptivo
    al final ('(cross-proyecto, 7 sincronizados)').
      'neb — Fase 9 — 2026-06-15'                          → 'neb'
      'site_monitor — caídas'                              → 'site-monitor'
      'stats-kpi-snapshot (cross-proyecto, ...) — 2026...' → 'stats-kpi-snapshot'
      'Sesiones pausadas'                                  → 'sesiones-pausadas'
    """
    head = re.split(r"\s+[—-]\s+", title.strip(), maxsplit=1)[0]
    head = re.sub(r"\s*\(.*?\)\s*$", "", head)   # quita paréntesis descriptivo al final
    s = pendings.normalize(head)                 # minúsculas + sin acentos
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "sin-area"


def _item_title(text):
    """Título legible de un ítem para el reporte. Prefiere el slug '[xxx]'; si no, los
    primeros ~70 caracteres del texto (1ª línea)."""
    m = _SLUG_RE.search(text)
    if m:
        return m.group("slug")
    first = text.strip().splitlines()[0] if text.strip() else ""
    # quitar viñeta/numeración del header
    first = re.sub(r"^\d+\.\s*", "", first)
    first = re.sub(r"^[-*]\s*", "", first)
    first = first.replace("✅", "").strip()
    # quitar el ** de apertura de negrita y la etiqueta de sub-ítem "(a)"/"(g.1)"
    first = re.sub(r"^\*\*\s*", "", first)
    first = re.sub(r"^\([a-z](?:\.\d+)?\)\s*", "", first)
    # quitar el ** de cierre de la negrita inicial (deja el texto plano)
    first = first.replace("**", "")
    first = first.strip("* ").strip()
    return (first[:70] + "...") if len(first) > 70 else first


class ParsedItem:
    """Un ítem (o sub-ítem) parseado. `text` = bloque íntegro (header + cuerpo) → context_origin."""
    __slots__ = ("kind", "label", "text", "header", "active", "topic_slug",
                 "title", "depends_on_parent")

    def __init__(self, kind, text, header, topic_slug):
        self.kind = kind                # 'item' | 'subitem'
        self.text = text.rstrip()
        self.header = header
        self.topic_slug = topic_slug
        self.active = not _is_closed_header(header)
        self.title = _item_title(text)
        self.label = None               # '(a)' etc. para sub-ítems
        self.depends_on_parent = bool(_DEPENDS_RE.search(text))


def parse(md_text):
    """Parsea el contenido del pendings.md. Devuelve dict:
      {'topics':   [slug, ...]            # secciones detectadas, en orden, sin duplicar
       'units':    [ {item, subitems}... ]  # cada ítem con sus sub-ítems anidados
       'unparsed': [str, ...] }           # líneas/bloques que no se pudieron clasificar

    Estructura de cada unit:
      {'item': ParsedItem|None, 'subitems': [ParsedItem, ...]}
    Un bloque suelto bajo una sección sin ítem numerado (p.ej. el '>' de quote) va a unparsed.
    """
    lines = md_text.splitlines()
    topics, seen_topics = [], set()
    units = []
    unparsed = []

    cur_topic = None                 # slug de la sección activa
    cur_unit = None                  # unit en construcción
    # buffers de líneas del bloque actual (ítem o sub-ítem) para reconstruir el texto íntegro
    buf_lines = []
    buf_kind = None                  # 'item' | 'subitem'
    buf_header = None
    buf_subitem_obj = None           # ParsedItem del sub-ítem en construcción

    def flush_buffer():
        """Cierra el bloque (ítem o sub-ítem) acumulado y lo materializa en la unit."""
        nonlocal buf_lines, buf_kind, buf_header, buf_subitem_obj, cur_unit
        if not buf_kind:
            buf_lines = []
            return
        text = "\n".join(buf_lines)
        if buf_kind == "item":
            obj = ParsedItem("item", text, buf_header, cur_topic)
            cur_unit = {"item": obj, "subitems": []}
            units.append(cur_unit)
        else:  # subitem
            obj = buf_subitem_obj
            obj.text = text.rstrip()
            obj.active = not _is_closed_header(buf_header)
            obj.title = _item_title(text)
            obj.depends_on_parent = bool(_DEPENDS_RE.search(text))
            if cur_unit is None:
                # sub-ítem sin ítem padre (raro) → unit huérfana con item=None
                cur_unit = {"item": None, "subitems": []}
                units.append(cur_unit)
            cur_unit["subitems"].append(obj)
        buf_lines = []
        buf_kind = None
        buf_header = None
        buf_subitem_obj = None

    for raw in lines:
        sec = _SECTION_RE.match(raw)
        if sec:
            flush_buffer()
            cur_unit = None
            slug = _slugify_area(sec.group("title"))
            cur_topic = slug
            if slug not in seen_topics:
                seen_topics.add(slug)
                topics.append(slug)
            continue

        if cur_topic is None:
            # antes de la primera sección (p.ej. el título "# Pendientes del dev"): ignorar
            if raw.strip() and not raw.startswith("#"):
                unparsed.append(raw.strip())
            continue

        sub = _SUBITEM_RE.match(raw)
        if sub:
            flush_buffer()
            buf_kind = "subitem"
            buf_header = raw.strip()
            buf_lines = [raw]
            obj = ParsedItem("subitem", raw, raw.strip(), cur_topic)
            obj.label = sub.group("label")
            buf_subitem_obj = obj
            continue

        itm = _ITEM_RE.match(raw)
        if itm and not raw.startswith(" "):
            flush_buffer()
            buf_kind = "item"
            buf_header = raw.strip()
            buf_lines = [raw]
            continue

        # línea de continuación (cuerpo del ítem/sub-ítem) o ruido
        if buf_kind:
            buf_lines.append(raw)
        elif raw.strip():
            # bloque dentro de una sección sin ítem numerado (quote '>', viñeta no-(x), etc.)
            unparsed.append(raw.strip())

    flush_buffer()
    return {"topics": topics, "units": units, "unparsed": unparsed}


# =========================================================================== plan de migración

class MigrationPlan:
    """Resultado de simular el mapeo. Inmutable a efectos del reporte; --apply lo ejecuta."""
    def __init__(self):
        self.topics = []                 # [slug, ...]
        self.pendings = []               # [ {text, title, topic, kind, label, active} ... ] activos
        self.links = []                  # [ {child_title, parent_title, relation} ... ]
        self.omitted = []                # [ {title, topic, kind} ... ] (cerrados)
        self.unparsed = []               # [str, ...]
        self.by_section = []             # [ {topic, items:[{title, active, kind, label}...]} ]


def build_plan(parsed):
    """Convierte el parse en un plan de migración (qué pendings/topics/links se crearían).
    NO toca la DB. Aplica la regla: solo activos; sub-ítems activos de un ítem cerrado SÍ entran."""
    plan = MigrationPlan()
    plan.topics = list(parsed["topics"])
    plan.unparsed = list(parsed["unparsed"])

    section_acc = {}   # slug -> list de entradas del reporte (en orden de aparición)

    for unit in parsed["units"]:
        item = unit["item"]
        subs = unit["subitems"]
        topic = (item.topic_slug if item else
                 (subs[0].topic_slug if subs else "sin-area"))
        entries = section_acc.setdefault(topic, [])

        # solo ligamos a un padre que TAMBIÉN se migra (ítem activo). Si el ítem padre está
        # cerrado, sus sub-ítems activos migran igual pero sin link en el plan (el contexto del
        # sub-ítem es autocontenido). En --apply, si el padre cerrado ya existe de una corrida
        # previa, apply_migration sí lo liga; el plan reporta el caso conservador.
        parent_title = item.title if (item is not None and item.active) else None

        if item is not None:
            entries.append({"title": item.title, "active": item.active,
                            "kind": "item", "label": None})
            if item.active:
                plan.pendings.append({"text": item.text, "title": item.title,
                                      "topic": topic, "kind": "item",
                                      "label": None, "active": True})
            else:
                plan.omitted.append({"title": item.title, "topic": topic, "kind": "item"})

        for sub in subs:
            lbl = f"({sub.label})" if sub.label else ""
            entries.append({"title": f"{lbl} {sub.title}".strip(), "active": sub.active,
                            "kind": "subitem", "label": sub.label})
            if sub.active:
                plan.pendings.append({"text": sub.text, "title": sub.title,
                                      "topic": topic, "kind": "subitem",
                                      "label": sub.label, "active": True})
                if parent_title is not None:
                    relation = "depends" if sub.depends_on_parent else "related"
                    plan.links.append({"child_title": sub.title,
                                       "parent_title": parent_title,
                                       "relation": relation})
            else:
                plan.omitted.append({"title": sub.title, "topic": topic, "kind": "subitem"})

    plan.by_section = [{"topic": slug, "items": section_acc.get(slug, [])}
                       for slug in plan.topics]
    # secciones sin ítems numerados (solo bullets/quotes) igual aparecen en by_section vacías
    for slug, entries in section_acc.items():
        if slug not in plan.topics:
            plan.by_section.append({"topic": slug, "items": entries})
    return plan


# =========================================================================== reporte (dry-run)

def render_report(plan, src_path):
    """Texto del reporte de DRY-RUN. Resumen + desglose por sección."""
    out = []
    total_items = sum(1 for s in plan.by_section for e in s["items"] if e["kind"] == "item")
    total_subs = sum(1 for s in plan.by_section for e in s["items"] if e["kind"] == "subitem")
    active = len(plan.pendings)
    omitted = len(plan.omitted)
    out.append(f"[migrate-pendings] DRY-RUN sobre: {src_path}")
    out.append(f"[migrate-pendings] (no se escribe nada; --apply para ejecutar)\n")
    out.append("RESUMEN")
    out.append(f"  Secciones (topics) detectadas : {len(plan.topics)}")
    out.append(f"  Ítems numerados               : {total_items}")
    out.append(f"  Sub-ítems                     : {total_subs}")
    out.append(f"  Total unidades                : {total_items + total_subs}")
    out.append(f"  ACTIVOS (se crearían pending) : {active}")
    out.append(f"  CERRADOS (omitidos)           : {omitted}")
    out.append(f"  pending_link (a crear)        : {len(plan.links)}")
    out.append(f"  No clasificados por el parser : {len(plan.unparsed)}")
    out.append("")
    out.append("TOPICS (secciones)")
    for slug in plan.topics:
        out.append(f"  - {slug}")
    out.append("")
    out.append("DESGLOSE POR SECCIÓN")
    for sec in plan.by_section:
        n_act = sum(1 for e in sec["items"] if e["active"])
        n_tot = len(sec["items"])
        out.append(f"  ## {sec['topic']}  ({n_act} activos / {n_tot})")
        for e in sec["items"]:
            mark = "ACTIVO " if e["active"] else "omitido"
            kind = "  >>" if e["kind"] == "subitem" else "   "
            out.append(f"    [{mark}]{kind} {e['title']}")
    if plan.links:
        out.append("")
        out.append("LINKS pending↔pending (sub-ítem → ítem padre)")
        for lk in plan.links:
            out.append(f"  ({lk['relation']}) {lk['child_title']}  →  {lk['parent_title']}")
    if plan.unparsed:
        out.append("")
        out.append("NO CLASIFICADOS (revisar manualmente)")
        for u in plan.unparsed:
            snippet = u if len(u) <= 100 else u[:100] + "…"
            out.append(f"  - {snippet}")
    return "\n".join(out)


# =========================================================================== --apply (escritura)

_MIGRATED_NOTE = "[migrate] importado desde pendings.md"


def _find_existing_pending(con, context_origin):
    """id del pending con ESTE context_origin exacto, o None. Base de la idempotencia."""
    row = con.execute("SELECT id FROM pending WHERE context_origin=?",
                      (context_origin,)).fetchone()
    return row[0] if row else None


def _ensure_topic(con, slug):
    """Crea el topic <slug> (status='active', keywords = el propio slug tokenizado) si no
    existe. Devuelve su id. Idempotente (uq_topic_slug)."""
    name = slug.replace("-", " ").strip().capitalize() or slug
    keywords = slug.replace("-", ", ")
    con.execute(
        "INSERT OR IGNORE INTO topic (slug, name, description, keywords, status) "
        "VALUES (?,?,?,?, 'active')",
        (slug, name, f"Sección migrada del pendings.md: {slug}", keywords))
    return con.execute("SELECT id FROM topic WHERE slug=?", (slug,)).fetchone()[0]


def _link(con, a_id, b_id, relation):
    """Inserta la arista pending_link(a,b,relation) si no existe (PK compuesta → idempotente)."""
    con.execute(
        "INSERT OR IGNORE INTO pending_link (a, b, relation) VALUES (?,?,?)",
        (a_id, b_id, relation))


def apply_migration(con, parsed):
    """Ejecuta la migración DENTRO de la transacción del caller (with_write_tx).
    NO commitea (el wrapper lo hace). Idempotente por context_origin.
    Devuelve dict de conteos {pendings_created, pendings_reused, topics, links}."""
    pendings._ensure_sentinel(con)
    counts = {"pendings_created": 0, "pendings_reused": 0, "topics": 0, "links": 0}
    seen_topics = set()

    # 1) asegurar topics (las secciones)
    for slug in parsed["topics"]:
        _ensure_topic(con, slug)
        if slug not in seen_topics:
            seen_topics.add(slug)
            counts["topics"] += 1

    # 2) crear pendings (ítems + sub-ítems activos) y ligar sub-ítem → padre
    for unit in parsed["units"]:
        item = unit["item"]
        subs = unit["subitems"]
        topic = (item.topic_slug if item else
                 (subs[0].topic_slug if subs else "sin-area"))
        _ensure_topic(con, topic)
        if topic not in seen_topics:
            seen_topics.add(topic)
            counts["topics"] += 1

        parent_id = None
        if item is not None and item.active:
            parent_id = _create_or_reuse(con, item.text, counts)
            _classify_to_topic(con, parent_id, topic)
        elif item is not None and not item.active:
            # ítem cerrado: no se crea pending, pero puede ser ancla de sub-ítems activos.
            # buscamos si YA existe (de una corrida previa) para poder ligar; si no, los
            # sub-ítems quedan sin padre (link omitido) — el contexto del sub-ítem es autocontenido.
            parent_id = _find_existing_pending(con, item.text)

        for sub in subs:
            if not sub.active:
                continue
            child_id = _create_or_reuse(con, sub.text, counts)
            _classify_to_topic(con, child_id, topic)
            if parent_id is not None:
                relation = "depends" if sub.depends_on_parent else "related"
                _link(con, child_id, parent_id, relation)
                counts["links"] += 1
    return counts


def _create_or_reuse(con, context_origin, counts):
    """Crea el pending (type='task') o reusa el existente con el mismo context_origin."""
    existing = _find_existing_pending(con, context_origin)
    if existing is not None:
        counts["pendings_reused"] += 1
        return existing
    pid = pendings.create(con, "task", context_origin)
    pendings.add_note(con, pid, _MIGRATED_NOTE)
    counts["pendings_created"] += 1
    return pid


def _classify_to_topic(con, pending_id, topic_slug):
    """Asocia el pending a SU topic de sección de forma explícita (is_primary=1) y además
    corre el keyword-match automático (classify) para temas adicionales. Idempotente.

    classify() con manage_tx=False NO abre su propia transacción (el caller ya está en
    with_write_tx) — evita 'transaction within a transaction'."""
    tid = _ensure_topic(con, topic_slug)
    # asociación directa al topic de la sección (fuente explícita)
    con.execute(
        "INSERT INTO pending_topic (pending_id, topic_id, priority_band, priority_score, is_primary) "
        "VALUES (?,?, 'medium', 0.0, 1) "
        "ON CONFLICT(pending_id, topic_id) DO UPDATE SET is_primary=1",
        (pending_id, tid))
    # match automático por keywords (replace=False para no borrar la asociación de sección)
    pendings.classify(con, pending_id, replace=False, manage_tx=False)


# =========================================================================== main

def _utf8_stdout():
    """En Windows la consola suele ser cp1252 y el reporte trae glifos del pendings.md real
    (—, →, ✅, ↳). Reconfiguramos stdout/stderr a UTF-8 con reemplazo para no abortar por
    UnicodeEncodeError. No-op si la plataforma ya es UTF-8 o no soporta reconfigure."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def run(src_path, db_path, do_apply):
    """Núcleo testeable. Devuelve (plan, counts|None). counts solo en --apply."""
    _utf8_stdout()
    if not os.path.isfile(src_path):
        print(f"[migrate-pendings] ERROR: no existe {src_path}", file=sys.stderr)
        return None, None
    with open(src_path, encoding="utf-8") as f:
        md_text = f.read()
    parsed = parse(md_text)
    plan = build_plan(parsed)

    if not do_apply:
        print(render_report(plan, src_path))
        return plan, None

    # --apply: escritura idempotente dentro de una transacción.
    con = _db_shared._connect(db_path, _SCHEMA)
    if con is None:
        print(f"[migrate-pendings] ERROR: no se pudo abrir la DB {db_path}", file=sys.stderr)
        return plan, None
    try:
        counts = _db_shared.with_write_tx(con, lambda c: apply_migration(c, parsed))
    finally:
        con.close()
    print(f"[migrate-pendings] APPLY OK sobre {db_path}")
    print(f"  pendings creados : {counts['pendings_created']}")
    print(f"  pendings reusados: {counts['pendings_reused']} (idempotencia)")
    print(f"  topics asegurados: {counts['topics']}")
    print(f"  links creados    : {counts['links']}")
    return plan, counts


def main(argv):
    p = argparse.ArgumentParser(
        description="Migra el pendings.md (Markdown) al backend SQLite neb.db (idempotente).")
    p.add_argument("--from", dest="src",
                   default=os.path.join(os.path.expanduser("~"), ".claude", "pendings.md"),
                   help="pendings.md a leer (default: ~/.claude/pendings.md). SOLO LECTURA.")
    p.add_argument("--db", dest="db", default=None,
                   help="neb.db destino (default: resolve_db_path(~)). DRY-RUN no lo abre.")
    p.add_argument("--apply", action="store_true",
                   help="ejecuta la migración (sin él = DRY-RUN, solo reporta).")
    args = p.parse_args(argv)
    db_path = args.db or _db_shared.resolve_db_path(os.path.expanduser("~"))
    plan, _ = run(args.src, db_path, args.apply)
    return 0 if plan is not None else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:                       # defensivo, igual que el resto de bootstrap
        print(f"[migrate-pendings] ERROR inesperado: {e}", file=sys.stderr)
        sys.exit(1)
