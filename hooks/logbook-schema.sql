-- Bitácora de relevo — esquema del backend SQLite local (Neb).
-- Backend por defecto (universal, sin infra) y outbox del cliente cuando hay central.
-- El DDL del backend central (MySQL de referencia) vive con el servidor de referencia (REQ central).
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
