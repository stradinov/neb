#!/usr/bin/env python3
"""
seed-pendings-taxonomy.py — siembra en neb.db la taxonomía curada de pendientes (ejes cliente/tópico),
los slugs, las bandas y los grupos de un pase de triage (REQ pendings-taxonomia-cliente-topico).
Reusa hooks/lib (pendings.curate, pendings.backfill_slugs, _db_shared.with_write_tx): NO reimplementa.

Entradas — NUNCA hardcodeadas aquí (este script viaja al repo público; los nombres viven en los JSON):
  --catalog <taxonomy.json>   {"cliente": [{"slug","name","keywords"}...], "topico": [...]}
  --from    <triage.json>     {"items": [{"id","slug","cliente","topico","grupo","prioridad","veredicto_final"}...]}

Contrato CLI:
  py bootstrap/seed-pendings-taxonomy.py --from T.json --catalog C.json [--db P]           # DRY-RUN (default)
  py bootstrap/seed-pendings-taxonomy.py --from T.json --catalog C.json [--db P] --apply   # escribe
  py bootstrap/seed-pendings-taxonomy.py [--db P] --rollback <respaldo.bak-...>            # restauración lógica
    --force        re-cura pendientes que ya tenían curaduría y re-activa temas del catálogo archivados
    --backup-dir   dónde dejar el respaldo (default: junto a la DB)

Qué hace --apply (UNA transacción with_write_tx, después de un respaldo verificado; el plan se
calcula DENTRO de la transacción, así una curaduría hecha por otra sesión un instante antes no se pisa):
  1. Raíces 'cliente'/'topico' + hijos del catálogo: INSERT ... ON CONFLICT(slug) DO UPDATE parent_id,
     name, keywords — un tema viejo con el mismo slug se REUSA (conserva id e historial) y se re-parenta;
     su status solo cambia a 'active' con --force (sin --force, los items que usan un tema del catálogo
     archivado se saltan y se reportan). Todo tema activo que no sea sentinel/raíz/hijo del catálogo
     pasa a status='archived' (sus filas pending_topic se conservan; las lecturas filtran active).
     Si el catálogo cambió (keywords, nombres, ejes), las sugerencias del matching (curated=0) de los
     pendientes abiertos sin curar se borran para que el siguiente `PD triage` las recalcule con el
     catálogo nuevo; lo curado no se toca. Así, afinar keywords = editar taxonomy.json + --apply.
  2. Por cada item vivo del dataset cuyo id exista con status='open' y SIN curaduría previa (o con
     --force): filas curated=1 vía pendings.curate (cliente is_primary=0, tópico is_primary=1) con
     banda P0/P1->high, P2->medium, P3->low; el score se HEREDA de la fila primaria previa cuando su
     banda coincide (así el score que el pase escribió no cambia) y si no, 95/75/50/20; una prioridad
     desconocida cura SIN banda (compas aplica) y se reporta; borra sus sugerencias (curated=0) sobre
     temas activos; slug del dataset (inválido -> se reporta; colisión con otro pendiente -> se reporta
     y se salta el slug, no aborta). Items obsoletos, inexistentes, con veredicto de cierre o con eje
     desconocido: se saltan y se reportan.
  3. pending_link 'related' en estrella por grupo (a = miembro, b = menor id), INSERT OR IGNORE,
     solo entre pendientes open del dataset.
  4. pendings.backfill_slugs para el resto (tags [slug] únicos; los repetidos quedan NULL).

Respaldo (--apply): sqlite3.connect(db) PLANO (sin _connect: no migra nada) + Connection.backup() a
  <db>.bak-pre-taxonomy-<stamp> — snapshot consistente aunque haya otras conexiones (WAL). Se verifica
  con PRAGMA integrity_check y count(*) de las tablas de pendings (estricto) y de las del logbook
  (aviso: el hook puede escribirlas entre el backup y el conteo); si algo falla, aborta sin tocar la DB.
  Se toma ANTES de abrir la DB con _connect (que sí migra columnas). Nunca es copia de archivo
  (con -wal/-shm sueltos sería inconsistente).
Rollback (--rollback <bak>): ATTACH del respaldo y, en una with_write_tx, restaura pending.slug y
  pending.last_reviewed_at, pending_topic, topic, topic_link y pending_link desde el respaldo;
  work/event/transcript_* quedan intactos. Pendientes creados después del respaldo conservan su fila
  y sus notas, pero pierden temas, slug y vínculos creados después del respaldo (el siguiente
  `PD triage` los vuelve a sugerir). Un respaldo tomado ANTES de la migración (sin `slug`/`curated`)
  también sirve: esas columnas se restauran a NULL / 0.
Idempotencia: una segunda corrida no cambia nada (digest de las tablas sembradas antes/después) — los
  pendientes ya curados se saltan salvo --force.
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

# Reusa la infra de hooks/lib (misma técnica que bootstrap/migrate-pendings-md.py).
_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "lib")
sys.path.insert(0, _LIB)

import _db_shared          # noqa: E402
import pendings            # noqa: E402

_SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "hooks", "logbook-schema.sql")

# Prioridad del pase -> (priority_band EN, priority_score por defecto). El score real se hereda de la
# fila primaria previa cuando la banda coincide (ver apply_plan); este mapa es el fallback.
BAND_BY_PRIORITY = {"P0": ("high", 95.0), "P1": ("high", 75.0), "P2": ("medium", 50.0), "P3": ("low", 20.0)}
ALIVE_VERDICTS = ("vigente", "requiere_verificacion")   # veredicto_final que sigue vivo en el dataset
PENDING_TABLES = ("pending", "pending_note", "pending_link", "topic", "topic_link", "pending_topic")
LOGBOOK_TABLES = ("work", "event", "transcript_cursor", "transcript_local")
ALL_TABLES = LOGBOOK_TABLES + PENDING_TABLES
SEED_TABLES = ("pending", "pending_topic", "topic", "topic_link", "pending_link")   # lo que toca el seed/rollback
AXIS_NAMES = {"cliente": "Cliente", "topico": "Tópico"}


def _stamp():
    # microsegundos: dos --apply en el mismo segundo no colisionan en el nombre del respaldo
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-%fZ")


def _require_db(db_path):
    """Un --db con typo NO debe crear una DB vacía (sqlite3.connect la crearía en silencio)."""
    if not os.path.isfile(db_path):
        raise RuntimeError(f"no existe la DB {db_path}")


# =========================================================================== entradas

def load_catalog(path):
    """Valida y normaliza taxonomy.json: dos ejes no vacíos, slugs kebab-case únicos, sin cruzar ejes,
    sin raíces ni sentinel como hijos. Devuelve {'cliente': [{slug,name,keywords}], 'topico': [...]}."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    cat = {}
    for axis in pendings.AXIS_ROOTS:
        entries = data.get(axis)
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"catálogo sin eje {axis!r}")
        seen = set()
        out = []
        for e in entries:
            slug = (e or {}).get("slug")
            if (not slug or not pendings._SLUG_RE.match(slug)
                    or slug in pendings.AXIS_ROOTS or slug == pendings.SENTINEL_SLUG):
                raise ValueError(f"slug inválido en el catálogo ({axis}): {slug!r}")
            if slug in seen:
                raise ValueError(f"slug repetido en el catálogo: {slug!r}")
            seen.add(slug)
            out.append({"slug": slug, "name": e.get("name") or slug, "keywords": e.get("keywords") or ""})
        cat[axis] = out
    both = {e["slug"] for e in cat["cliente"]} & {e["slug"] for e in cat["topico"]}
    if both:
        raise ValueError(f"slug presente en ambos ejes: {sorted(both)}")
    return cat


def load_dataset(path):
    """Lee el dataset del pase (lista `items` o lista cruda). Cada item: id entero + campos del pase."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("dataset sin lista 'items'")
    out = []
    for it in items:
        try:
            pid = int(it["id"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"item sin id entero: {str(it)[:120]!r}")
        out.append({"id": pid, "slug": it.get("slug"), "cliente": it.get("cliente"),
                    "topico": it.get("topico"), "grupo": it.get("grupo") or None,
                    "prioridad": it.get("prioridad"),
                    "veredicto": it.get("veredicto_final") or "vigente"})
    return out


# =========================================================================== estado de la DB

def _col_exists(con, table, col, schema="main"):
    return col in {r[1] for r in con.execute(f"PRAGMA {schema}.table_info({table})").fetchall()}


def digest(con):
    """Huella de las tablas que toca el seed (pending: id, slug, last_reviewed_at). Mide '0 cambios'
    de verdad (un rowcount de upsert idéntico no distingue escritura de no-cambio)."""
    h = hashlib.sha256()
    slug_col = "slug" if _col_exists(con, "pending", "slug") else "NULL"
    cur_col = "curated" if _col_exists(con, "pending_topic", "curated") else "0"
    queries = [f"SELECT id, {slug_col}, last_reviewed_at FROM pending ORDER BY id",
               f"SELECT pending_id, topic_id, priority_band, priority_score, is_primary, {cur_col} "
               "FROM pending_topic ORDER BY pending_id, topic_id",
               "SELECT id, slug, name, description, keywords, status, parent_id FROM topic ORDER BY id",
               "SELECT a, b, relation FROM pending_link ORDER BY a, b, relation"]
    if _db_shared._table_exists(con, "topic_link"):     # ausente en un respaldo muy viejo: cuenta como vacía
        queries.append("SELECT topic_a, topic_b, relation FROM topic_link ORDER BY topic_a, topic_b, relation")
    for sql in queries:
        for row in con.execute(sql):
            h.update(repr(row).encode("utf-8"))
    return h.hexdigest()


def _db_state(con):
    has_slug = _col_exists(con, "pending", "slug")
    has_cur = _col_exists(con, "pending_topic", "curated")
    status = dict(con.execute("SELECT id, status FROM pending").fetchall())
    slugs = dict(con.execute("SELECT id, slug FROM pending").fetchall()) if has_slug else {}
    # curado = ≥1 fila curated=1 sobre un tema ACTIVO (mismo predicado que pendings._HAS_CURATED_SQL)
    curated = ({r[0] for r in con.execute(
        "SELECT DISTINCT pt.pending_id FROM pending_topic pt JOIN topic t ON t.id = pt.topic_id "
        "WHERE pt.curated=1 AND t.status='active'")} if has_cur else set())
    topics = {r[1]: {"id": r[0], "status": r[2], "parent_id": r[3]}
              for r in con.execute("SELECT id, slug, status, parent_id FROM topic").fetchall()}
    links = {(r[0], r[1]) for r in con.execute("SELECT a, b FROM pending_link").fetchall()}
    return {"status": status, "slugs": slugs, "curated": curated, "topics": topics, "links": links,
            "migrated": has_slug and has_cur}


def build_plan(con, catalog, dataset, force=False):
    """Simula la siembra sin escribir. Devuelve el plan (listas/conteos) que --apply ejecuta y que el
    DRY-RUN reporta. En --apply se construye DENTRO de la transacción."""
    st = _db_state(con)
    cat_slugs = {axis: [e["slug"] for e in catalog[axis]] for axis in pendings.AXIS_ROOTS}
    all_cat = set(cat_slugs["cliente"]) | set(cat_slugs["topico"])
    plan = {"migrated": st["migrated"],
            "topics_create": [], "topics_reparent": [], "topics_reactivate": [], "topics_archive": [],
            "curate": [], "sin_banda": [],
            "skipped": {"missing": [], "obsolete": [], "cerrable": [], "curated": [],
                        "axis_unknown": [], "axis_archived": []},
            "slugs_set": [], "slugs_collide": [], "slugs_invalid": [],
            "groups": 0, "links_new": 0, "backfill": 0}
    for axis in pendings.AXIS_ROOTS:
        root = st["topics"].get(axis)
        if root is None:
            plan["topics_create"].append(axis)
        for slug in cat_slugs[axis]:
            t = st["topics"].get(slug)
            if t is None:
                plan["topics_create"].append(slug)
                continue
            if root is None or t["parent_id"] != root["id"]:
                plan["topics_reparent"].append(slug)
            if t["status"] != "active":
                plan["topics_reactivate"].append(slug)     # solo se ejecuta con --force
    for slug, t in st["topics"].items():
        if (t["status"] == "active" and slug not in all_cat and slug not in pendings.AXIS_ROOTS
                and slug != pendings.SENTINEL_SLUG):
            plan["topics_archive"].append(slug)
    # sin --force, un tema del catálogo que sigue archivado NO es curable: sus items se saltan
    unusable = set() if force else set(plan["topics_reactivate"])

    used_slugs = {s: pid for pid, s in st["slugs"].items() if s}
    alive_open = []
    for it in dataset:
        pid = it["id"]
        s = st["status"].get(pid)
        if s is None:
            plan["skipped"]["missing"].append(pid)
            continue
        if s != "open":
            plan["skipped"]["obsolete"].append(pid)
            continue
        if it["veredicto"] not in ALIVE_VERDICTS:
            plan["skipped"]["cerrable"].append(pid)
            continue
        alive_open.append(it)
        if it["cliente"] not in cat_slugs["cliente"] or it["topico"] not in cat_slugs["topico"]:
            plan["skipped"]["axis_unknown"].append(pid)
            continue
        if it["cliente"] in unusable or it["topico"] in unusable:
            plan["skipped"]["axis_archived"].append(pid)
            continue
        if pid in st["curated"] and not force:
            plan["skipped"]["curated"].append(pid)
            continue
        plan["curate"].append(pid)
        if it["prioridad"] not in BAND_BY_PRIORITY:
            plan["sin_banda"].append(pid)
        slug = it["slug"]
        if slug and not pendings._SLUG_RE.match(slug):
            plan["slugs_invalid"].append((pid, slug))
        elif slug:
            owner = used_slugs.get(slug)
            if owner is None or owner == pid:
                if st["slugs"].get(pid) != slug:
                    plan["slugs_set"].append((pid, slug))
                used_slugs[slug] = pid
            else:
                plan["slugs_collide"].append((pid, slug, owner))
    # grupos: entre todos los open vivos del dataset (también los ya curados: el vínculo es del grupo)
    groups = {}
    for it in alive_open:
        if it["grupo"]:
            groups.setdefault(it["grupo"], []).append(it["id"])
    for members in groups.values():
        if len(members) < 2:
            continue
        plan["groups"] += 1
        b = min(members)
        plan["links_new"] += sum(1 for a in members if a != b and (a, b) not in st["links"])
    # backfill: el mismo criterio que ejecuta --apply (pendings.backfill_slugs en modo conteo),
    # excluyendo lo que el paso 2 ya va a asignar
    plan["backfill"] = pendings.backfill_slugs(
        con, dry_run=True, skip_ids={p for p, _ in plan["slugs_set"]},
        reserved={s for _, s in plan["slugs_set"]})
    return plan


# =========================================================================== --apply

def _previous_primary(con, pid):
    """(priority_band, priority_score) de la fila primaria previa con banda (prefiere curada)."""
    return con.execute(
        "SELECT priority_band, priority_score FROM pending_topic WHERE pending_id=? AND is_primary=1 "
        "AND priority_band IS NOT NULL ORDER BY curated DESC, topic_id LIMIT 1", (pid,)).fetchone()


def apply_plan(con, catalog, dataset, plan, force=False):
    """Ejecuta el plan DENTRO de la transacción del caller (with_write_tx). NO commitea.
    Devuelve conteos reales."""
    counts = {"topics_upserted": 0, "topics_archived": 0, "suggestions_reset": 0, "curated": 0,
              "sin_banda": 0, "slugs_set": 0, "slugs_collided": len(plan["slugs_collide"]),
              "slugs_invalid": len(plan["slugs_invalid"]), "links_new": 0, "backfilled": 0}
    pendings._ensure_sentinel(con)
    catalog_before = sorted(con.execute("SELECT slug, name, keywords, status, parent_id FROM topic").fetchall())
    # 1. raíces + hijos + archivo de lo que sobra
    root_ids = {}
    for axis in pendings.AXIS_ROOTS:
        con.execute(
            "INSERT OR IGNORE INTO topic (slug, name, description, keywords, status, parent_id) "
            "VALUES (?, ?, ?, '', 'active', NULL)",
            (axis, AXIS_NAMES[axis], f"Raíz del eje {axis} (contenedor; no es un tema)"))
        root_ids[axis] = con.execute("SELECT id FROM topic WHERE slug=?", (axis,)).fetchone()[0]
    status_clause = ", status='active'" if force else ""
    for axis in pendings.AXIS_ROOTS:
        for e in catalog[axis]:
            con.execute(
                "INSERT INTO topic (slug, name, description, keywords, status, parent_id) "
                "VALUES (?,?,?,?, 'active', ?) "
                "ON CONFLICT(slug) DO UPDATE SET parent_id=excluded.parent_id, name=excluded.name, "
                f"keywords=excluded.keywords{status_clause}",
                (e["slug"], e["name"], f"Eje {axis}", e["keywords"], root_ids[axis]))
            counts["topics_upserted"] += 1
    keep = ([e["slug"] for a in pendings.AXIS_ROOTS for e in catalog[a]]
            + list(pendings.AXIS_ROOTS) + [pendings.SENTINEL_SLUG])
    counts["topics_archived"] = con.execute(
        f"UPDATE topic SET status='archived' WHERE status='active' AND slug NOT IN ({','.join('?' * len(keep))})",
        keep).rowcount
    if sorted(con.execute("SELECT slug, name, keywords, status, parent_id FROM topic").fetchall()) != catalog_before:
        # el catálogo cambió (keywords/nombres/ejes): las sugerencias del matching sobre pendientes
        # abiertos sin curar quedan obsoletas -> se borran para que el siguiente triage las recalcule
        # (reclassify solo re-sugiere a quien no tiene sugerencia vigente). Las filas curadas no se tocan.
        counts["suggestions_reset"] = con.execute(
            "DELETE FROM pending_topic WHERE curated=0 AND pending_id IN "
            "(SELECT p.id FROM pending p WHERE p.status='open' AND p.archived_at IS NULL "
            " AND NOT EXISTS (SELECT 1 FROM pending_topic q JOIN topic t ON t.id = q.topic_id "
            "                 WHERE q.pending_id = p.id AND q.curated=1 AND t.status='active')) "
            "AND topic_id IN (SELECT id FROM topic WHERE status='active')").rowcount
    # 2. curaduría por item
    by_id = {it["id"]: it for it in dataset}
    slug_for = dict(plan["slugs_set"])
    for pid in plan["curate"]:
        it = by_id[pid]
        band_en, score = BAND_BY_PRIORITY.get(it["prioridad"], (None, None))
        if band_en is None:
            counts["sin_banda"] += 1                       # curado sin banda: compas aplica
        else:
            prev = _previous_primary(con, pid)
            if prev and prev[0] == band_en and prev[1] is not None:
                score = prev[1]                            # el score del pase no cambia
        pendings.curate(con, pid, cliente=it["cliente"], topico=it["topico"],
                        band=(pendings._BAND_EN_TO_ES[band_en] if band_en else None), score=score)
        counts["curated"] += 1
        slug = slug_for.get(pid)
        if slug:
            taken = con.execute("SELECT id FROM pending WHERE slug=? AND id!=?", (slug, pid)).fetchone()
            if taken:                                 # carrera improbable: el plan ya lo filtró
                plan["slugs_collide"].append((pid, slug, taken[0]))
                counts["slugs_collided"] += 1
            else:
                con.execute("UPDATE pending SET slug=? WHERE id=?", (slug, pid))
                counts["slugs_set"] += 1
    # 3. grupos -> pending_link 'related' en estrella (a = miembro, b = menor id)
    st = _db_state(con)
    groups = {}
    for it in dataset:
        if it["grupo"] and st["status"].get(it["id"]) == "open" and it["veredicto"] in ALIVE_VERDICTS:
            groups.setdefault(it["grupo"], []).append(it["id"])
    for members in groups.values():
        if len(members) < 2:
            continue
        b = min(members)
        for a in members:
            if a != b:
                counts["links_new"] += con.execute(
                    "INSERT OR IGNORE INTO pending_link (a, b, relation) VALUES (?,?,'related')",
                    (a, b)).rowcount
    # 4. backfill del resto
    counts["backfilled"] = pendings.backfill_slugs(con)
    return counts


def backup_db(db_path, dst_path):
    """Respaldo con la API backup de SQLite sobre una conexión PLANA (sin _connect: no migra).
    Verifica integrity_check y count(*) contra el origen: estricto en las tablas de pendings;
    en las del logbook solo avisa (el hook puede escribirlas entre el backup y el conteo). Aborta
    (RuntimeError) sin tocar nada si el destino existe o la verificación falla — y borra el
    respaldo fallido para que --rollback no lo encuentre."""
    _require_db(db_path)
    if os.path.exists(dst_path):
        raise RuntimeError(f"ya existe el respaldo {dst_path}; no se sobreescribe")
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(dst_path)
        try:
            src.backup(dst)
            ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise RuntimeError(f"integrity_check del respaldo: {ok}")
            for t in ALL_TABLES:
                if not _db_shared._table_exists(src, t):
                    continue
                a = src.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                b = dst.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                if a != b and t in PENDING_TABLES:
                    raise RuntimeError(f"conteo distinto en {t}: origen {a} vs respaldo {b}")
                if a != b:
                    print(f"[seed-taxonomy] aviso: {t} cambió durante el respaldo ({b} -> {a}); "
                          "el seed no la toca", file=sys.stderr)
        finally:
            dst.close()
    except Exception:
        src.close()
        for suffix in ("", "-wal", "-shm", "-journal"):
            try:
                os.remove(dst_path + suffix)
            except OSError:
                pass
        raise
    finally:
        try:
            src.close()
        except sqlite3.ProgrammingError:
            pass
    return dst_path


def rollback(db_path, bak_path):
    """Restauración LÓGICA de las tablas del seed desde el respaldo (ATTACH), en una transacción:
    pending.slug + pending.last_reviewed_at, pending_topic, topic, topic_link y pending_link.
    work/event/transcript_* no se tocan. Devuelve conteos restaurados."""
    _require_db(db_path)
    if not os.path.isfile(bak_path):
        raise RuntimeError(f"no existe el respaldo {bak_path}")
    con = _db_shared._connect(db_path, _SCHEMA)
    if con is None:
        raise RuntimeError(f"no se pudo abrir la DB {db_path}")
    try:
        con.execute("ATTACH DATABASE ? AS bak", (bak_path,))     # fuera de la transacción (SQLite lo exige)
        bak_slug = _col_exists(con, "pending", "slug", schema="bak")
        bak_cur = _col_exists(con, "pending_topic", "curated", schema="bak")
        bak_tl = con.execute("SELECT 1 FROM bak.sqlite_master WHERE type='table' AND name='topic_link'").fetchone() is not None

        def _restore(c):
            c.execute("DELETE FROM pending_link")
            c.execute("DELETE FROM pending_topic")
            c.execute("DELETE FROM topic_link")
            c.execute("DELETE FROM topic")
            n_topic = c.execute(
                "INSERT INTO topic (id, slug, name, description, keywords, status, parent_id) "
                "SELECT id, slug, name, description, keywords, status, parent_id FROM bak.topic").rowcount
            n_tl = (c.execute("INSERT INTO topic_link (topic_a, topic_b, relation) "
                              "SELECT topic_a, topic_b, relation FROM bak.topic_link").rowcount
                    if bak_tl else 0)                      # respaldo sin la tabla: queda vacía
            n_pt = c.execute(
                "INSERT INTO pending_topic (pending_id, topic_id, priority_band, priority_score, is_primary, curated) "
                f"SELECT pending_id, topic_id, priority_band, priority_score, is_primary, {'curated' if bak_cur else '0'} "
                "FROM bak.pending_topic").rowcount
            n_link = c.execute(
                "INSERT INTO pending_link (a, b, relation) SELECT a, b, relation FROM bak.pending_link").rowcount
            slug_expr = "(SELECT b.slug FROM bak.pending b WHERE b.id = pending.id)" if bak_slug else "NULL"
            c.execute(f"UPDATE pending SET slug = {slug_expr}, "
                      "last_reviewed_at = (SELECT b.last_reviewed_at FROM bak.pending b WHERE b.id = pending.id)")
            return {"topic": n_topic, "topic_link": n_tl, "pending_topic": n_pt, "pending_link": n_link}

        counts = _db_shared.with_write_tx(con, _restore)
        con.execute("DETACH DATABASE bak")
    finally:
        con.close()
    return counts


# =========================================================================== reporte

def render_report(plan, db_path, apply=False, counts=None, backup=None, changed=None):
    out = []
    mode = "APPLY" if apply else "DRY-RUN (no se escribe nada; --apply para ejecutar)"
    out.append(f"[seed-taxonomy] {mode} sobre: {db_path}")
    if not plan["migrated"]:
        out.append("  (DB sin migrar: el plan asume slug NULL y curated=0; --apply migra antes de sembrar)")
    sk = plan["skipped"]
    out.append("TEMAS")
    out.append(f"  a crear (raíces + hijos) : {len(plan['topics_create'])}")
    out.append(f"  a re-parentar (reusados) : {len(plan['topics_reparent'])}  {plan['topics_reparent']}")
    out.append(f"  archivados del catálogo  : {len(plan['topics_reactivate'])}  {plan['topics_reactivate']}"
               + ("  (se re-activan: --force)" if plan['topics_reactivate'] else ""))
    out.append(f"  a archivar               : {len(plan['topics_archive'])}  {plan['topics_archive']}")
    out.append("PENDIENTES")
    out.append(f"  a curar                  : {len(plan['curate'])}  (sin banda por prioridad desconocida: {len(plan['sin_banda'])})")
    out.append(f"  saltados: ya curados {len(sk['curated'])} · obsoletos {len(sk['obsolete'])} · "
               f"inexistentes {len(sk['missing'])} · cerrables aún open {len(sk['cerrable'])} · "
               f"eje desconocido {len(sk['axis_unknown'])} · eje archivado (usa --force) {len(sk['axis_archived'])}")
    for key in ("cerrable", "axis_unknown", "axis_archived", "missing"):
        if sk[key]:
            out.append(f"    {key}: {sk[key][:30]}{' …' if len(sk[key]) > 30 else ''}")
    if plan["sin_banda"]:
        out.append(f"    sin banda: {plan['sin_banda'][:30]}")
    out.append(f"  slugs a asignar          : {len(plan['slugs_set'])}")
    out.append(f"  slugs en colisión        : {len(plan['slugs_collide'])}  {plan['slugs_collide'][:10]}")
    out.append(f"  slugs inválidos          : {len(plan['slugs_invalid'])}  {plan['slugs_invalid'][:10]}")
    out.append(f"  grupos (≥2 open)         : {plan['groups']}  -> vínculos nuevos: {plan['links_new']}")
    out.append(f"  backfill desde tag       : {plan['backfill']}")
    if apply and counts is not None:
        out.append("EJECUTADO")
        for k, v in counts.items():
            out.append(f"  {k:18s}: {v}")
        out.append(f"  respaldo               : {backup}")
        out.append(f"  hubo cambios           : {'sí' if changed else 'no (idempotente)'}")
    return "\n".join(out)


# =========================================================================== main

def _utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def run(db_path, catalog_path, dataset_path, apply=False, force=False, backup_dir=None):
    """Núcleo testeable. DRY-RUN abre la DB con sqlite3.connect plano (sin _connect: no migra ni
    escribe). --apply: respaldo verificado -> _connect (migra) -> [plan + siembra] en UNA transacción
    -> reporte. Devuelve {'plan', 'counts'|None, 'backup'|None, 'changed'|None}."""
    _require_db(db_path)
    catalog = load_catalog(catalog_path)
    dataset = load_dataset(dataset_path)
    if not apply:
        con = sqlite3.connect(db_path)
        try:
            plan = build_plan(con, catalog, dataset, force)
        finally:
            con.close()
        print(render_report(plan, db_path))
        return {"plan": plan, "counts": None, "backup": None, "changed": None}
    bak_dir = backup_dir or os.path.dirname(os.path.abspath(db_path))
    bak = backup_db(db_path, os.path.join(bak_dir, f"{os.path.basename(db_path)}.bak-pre-taxonomy-{_stamp()}"))
    con = _db_shared._connect(db_path, _SCHEMA)
    if con is None:
        raise RuntimeError(f"no se pudo abrir la DB {db_path} (respaldo intacto en {bak})")
    try:
        def _seed(c):
            before = digest(c)
            plan = build_plan(c, catalog, dataset, force)      # dentro de la tx: nadie cura en medio
            counts = apply_plan(c, catalog, dataset, plan, force)
            return before, plan, counts
        before, plan, counts = _db_shared.with_write_tx(con, _seed)
        after = digest(con)
    finally:
        con.close()
    changed = before != after
    print(render_report(plan, db_path, apply=True, counts=counts, backup=bak, changed=changed))
    return {"plan": plan, "counts": counts, "backup": bak, "changed": changed}


def main(argv):
    _utf8_stdout()
    p = argparse.ArgumentParser(
        description="Siembra la taxonomía curada (ejes cliente/tópico), slugs, bandas y grupos en neb.db.")
    p.add_argument("--from", dest="src", help="triage.json del pase (items con id, slug, cliente, topico, grupo, prioridad)")
    p.add_argument("--catalog", dest="catalog", help="taxonomy.json (ejes cliente/topico con slug, name, keywords)")
    p.add_argument("--db", dest="db", default=None, help="neb.db destino (default: resolve_db_path(~)); debe existir")
    p.add_argument("--apply", action="store_true", help="ejecuta (sin él = DRY-RUN)")
    p.add_argument("--force", action="store_true", help="re-cura pendientes ya curados y re-activa temas archivados del catálogo")
    p.add_argument("--backup-dir", dest="backup_dir", default=None, help="carpeta del respaldo (default: junto a la DB)")
    p.add_argument("--rollback", dest="rollback", default=None, help="respaldo .bak-pre-taxonomy-* a restaurar")
    args = p.parse_args(argv)
    db_path = args.db or _db_shared.resolve_db_path(os.path.expanduser("~"))
    if args.rollback:
        counts = rollback(db_path, args.rollback)
        print(f"[seed-taxonomy] ROLLBACK OK sobre {db_path} desde {args.rollback}: {counts}")
        return 0
    if not args.src or not args.catalog:
        p.error("--from y --catalog son obligatorios (salvo --rollback)")
    run(db_path, args.catalog, args.src, apply=args.apply, force=args.force, backup_dir=args.backup_dir)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:                       # defensivo, igual que el resto de bootstrap
        print(f"[seed-taxonomy] ERROR: {e}", file=sys.stderr)
        sys.exit(1)
