-- Bitácora de relevo — esquema del backend SQLite local (Neb).
-- Backend por defecto (universal, sin infra) y outbox del cliente cuando hay central.
-- El DDL del backend central (MySQL de referencia) vive en el repositorio dedicado del backend central.
-- WAL: una escritura interrumpida (corte de luz/kill) se revierte sola al reabrir — por eso SQLite y no archivos planos.
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Un trabajo relevable. Modo 'req' = con requerimiento (relevo cross-dev, lock);
-- modo 'exploratory' = sin REQ (registro liviano para localizar y reanudar con --resume local).
CREATE TABLE IF NOT EXISTS work (
  id              INTEGER PRIMARY KEY,
  mode            TEXT NOT NULL DEFAULT 'req',        -- 'req' | 'exploratory'
  project         TEXT,                               -- estable cross-máquina (git remote); NULL en exploratory
  req_slug        TEXT,                               -- NULL en exploratory
  -- ownership (lock sobre el work). owner = username del SO; ver workflow/logbook.md "Identidad del owner".
  owner           TEXT,                               -- NULL = libre
  lock_state      TEXT NOT NULL DEFAULT 'owned',      -- owned | released | takeover_requested
  takeover_by     TEXT,
  locked_at       TEXT,                               -- ISO8601
  -- estado del REQ + punteros (derivados de la memoria del proyecto, que es la fuente de verdad)
  req_state       TEXT,                               -- ENUM del requerimiento (vocabulary.md); ortogonal a lock_state
  branch          TEXT,
  head_commit     TEXT,
  repo_path       TEXT,
  change_md       TEXT,
  payload_json    TEXT,                               -- plan, archivos, próximos pasos, "Pendiente de entrega", "Trabajo en vuelo"
  payload_version INTEGER NOT NULL DEFAULT 0,         -- concurrencia optimista en el sync al central
  -- contexto de la sesión origen
  origin_dev      TEXT,
  origin_machine  TEXT,
  claude_session_id   TEXT,                           -- válido SOLO en su máquina origen (no para --resume cross-machine)
  claude_session_name TEXT,
  transcript_path TEXT,                               -- ruta del .jsonl local; el contenido NO se copia aquí
  -- ciclo de vida
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  archived_at     TEXT,                               -- NULL = activo; se archiva al cerrar (no se borra: corpus de auditoría)
  -- outbox hacia el central (solo local; el central es la autoridad y no los lleva)
  dirty           INTEGER NOT NULL DEFAULT 1,         -- pendiente de push
  synced_at       TEXT,
  remote_id       INTEGER,
  conflict        INTEGER NOT NULL DEFAULT 0          -- 1 = publish rechazado por el central (409); reconciliar (claim/forzar) antes de re-publicar. Corta el reintento ciego del outbox
);

-- Identidad por modo: índices únicos parciales (un solo work por REQ / por sesión exploratoria).
CREATE UNIQUE INDEX IF NOT EXISTS uq_work_req
  ON work(project, req_slug) WHERE mode='req';
CREATE UNIQUE INDEX IF NOT EXISTS uq_work_exploratory
  ON work(claude_session_id) WHERE mode='exploratory';
CREATE INDEX IF NOT EXISTS idx_work_dirty   ON work(dirty);
CREATE INDEX IF NOT EXISTS idx_work_active  ON work(archived_at);

-- Historial de relevo (append-only). Acumula el volumen; alimenta el corpus de auditoría (REQ futuro).
CREATE TABLE IF NOT EXISTS event (
  id        INTEGER PRIMARY KEY,
  work_id   INTEGER NOT NULL REFERENCES work(id) ON DELETE CASCADE,
  ts        TEXT NOT NULL,
  dev       TEXT NOT NULL,
  action    TEXT NOT NULL,                            -- publish|claim|release|forced_release|request_takeover|rename|archive (REQ A solo emite publish|claim|release|forced_release en local)
  prev_owner TEXT,                                    -- en forced_release: a quién se le quitó el mando
  machine   TEXT,
  note      TEXT,
  dirty     INTEGER NOT NULL DEFAULT 1,
  synced_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_work ON event(work_id, ts);

-- Cursor de captura incremental del transcript, POR (sesión, work) para soportar N:M
-- (una sesión toca varios works; un work, varias sesiones). Vive en SQLite, no en archivo .offset:
-- el avance del cursor se confirma en la misma transacción que el delta → no se corrompe ante corte.
CREATE TABLE IF NOT EXISTS transcript_cursor (
  session_id  TEXT NOT NULL,
  work_id     INTEGER NOT NULL REFERENCES work(id) ON DELETE CASCADE,
  synced_byte INTEGER NOT NULL DEFAULT 0,             -- hasta qué byte del .jsonl ya se procesó/empujó
  updated_at  TEXT NOT NULL,
  PRIMARY KEY (session_id, work_id)
);

-- ===========================================================================
-- Pendings (REQ neb-pendings-sqlite, nucleo). Reusa la infra del logbook.
-- Enums en INGLES (la capa de presentacion traduce al mostrar).
-- ===========================================================================

-- Un pendiente del dev. type='task' = algo por hacer; type='session' = sesion pausada
-- (referencia un work exploratory por session_ref → contexto via su transcript local).
CREATE TABLE IF NOT EXISTS pending (
  id               INTEGER PRIMARY KEY,                 -- autoincrement (reemplaza grep max+1)
  type             TEXT NOT NULL DEFAULT 'task',        -- 'task' | 'session'
  context_origin   TEXT NOT NULL,                       -- snapshot INMUTABLE (legible en frio); la evolucion va a pending_note
  status           TEXT NOT NULL DEFAULT 'open',        -- 'open' | 'obsolete'
  obsolete_cause   TEXT,                                -- 'no-longer-applies' | 'resolved-otherwise'; NULL si status='open'
  work_ref         INTEGER REFERENCES work(id) ON DELETE SET NULL,   -- vinculo pending↔work (logbook); NULL = sin work
  session_ref      INTEGER REFERENCES work(id) ON DELETE SET NULL,   -- type='session' → work exploratory
  created_at       TEXT NOT NULL,
  last_reviewed_at TEXT,                                -- ultima vez que el recomendador lo evaluo (delta en B/C)
  archived_at      TEXT                                 -- NULL = activo; se setea al pasar a obsolete (no se borra)
);
-- Vista activa rapida (status='open' AND archived_at IS NULL): indice parcial.
CREATE INDEX IF NOT EXISTS idx_pending_active   ON pending(status) WHERE archived_at IS NULL;
-- FKs con indice (evita scans en on_work_archived / cierre del work ligado).
-- Parciales (WHERE ... IS NOT NULL): el grueso de pendings no liga work/session, asi que el
-- indice solo cubre las filas relevantes (mas chico, y on_work_archived solo busca work_ref no-NULL).
CREATE INDEX IF NOT EXISTS idx_pending_work     ON pending(work_ref)    WHERE work_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pending_session  ON pending(session_ref) WHERE session_ref IS NOT NULL;

-- Bitacora append-only de la evolucion del pending (no reescribe context_origin).
CREATE TABLE IF NOT EXISTS pending_note (
  id          INTEGER PRIMARY KEY,
  pending_id  INTEGER NOT NULL REFERENCES pending(id) ON DELETE CASCADE,
  note        TEXT NOT NULL,
  ts          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pending_note_pending ON pending_note(pending_id, ts);

-- Grafo pending↔pending (agrupar relacionados; el disparador "bloqueo" usa relation='blocks').
CREATE TABLE IF NOT EXISTS pending_link (
  a         INTEGER NOT NULL REFERENCES pending(id) ON DELETE CASCADE,
  b         INTEGER NOT NULL REFERENCES pending(id) ON DELETE CASCADE,
  relation  TEXT NOT NULL,                              -- 'related' | 'depends' | 'blocks'
  PRIMARY KEY (a, b, relation)
);
CREATE INDEX IF NOT EXISTS idx_pending_link_b ON pending_link(b);

-- Catalogo de temas (formaliza las secciones por proyecto del pendings.md).
-- topic NO lleva peso de prioridad: el peso vive en compas.md (Sub-entrega C).
CREATE TABLE IF NOT EXISTS topic (
  id           INTEGER PRIMARY KEY,
  slug         TEXT NOT NULL,                           -- estable, kebab-case
  name         TEXT NOT NULL,
  description  TEXT,
  keywords     TEXT,                                    -- CSV; alimenta el matching automatico (B)
  status       TEXT NOT NULL DEFAULT 'active',          -- 'active' | 'archived'
  parent_id    INTEGER REFERENCES topic(id) ON DELETE SET NULL  -- jerarquia
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_topic_slug   ON topic(slug);
CREATE INDEX IF NOT EXISTS idx_topic_parent       ON topic(parent_id);

-- Grafo explicito curado entre temas (ademas de la jerarquia parent_id y de los keywords compartidos).
CREATE TABLE IF NOT EXISTS topic_link (
  topic_a   INTEGER NOT NULL REFERENCES topic(id) ON DELETE CASCADE,
  topic_b   INTEGER NOT NULL REFERENCES topic(id) ON DELETE CASCADE,
  relation  TEXT NOT NULL,                              -- 'related' | 'depends'
  PRIMARY KEY (topic_a, topic_b, relation)
);
CREATE INDEX IF NOT EXISTS idx_topic_link_b ON topic_link(topic_b);

-- Puente N:M pending↔topic. La PRIORIDAD vive AQUI (prioridad POR TEMA, persistida).
CREATE TABLE IF NOT EXISTS pending_topic (
  pending_id      INTEGER NOT NULL REFERENCES pending(id) ON DELETE CASCADE,
  topic_id        INTEGER NOT NULL REFERENCES topic(id)   ON DELETE CASCADE,
  priority_band   TEXT,                                  -- 'high' | 'medium' | 'low' (recomendado; NULL = sin clasificar aun)
  priority_score  REAL,                                  -- score fino opcional (criterio externo/roadmap)
  is_primary      INTEGER NOT NULL DEFAULT 0,            -- 1 = tema principal del pending
  PRIMARY KEY (pending_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_pending_topic_topic ON pending_topic(topic_id);
