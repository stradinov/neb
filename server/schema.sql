-- Bitácora de relevo — esquema del backend CENTRAL de referencia (Neb, REQ B).
-- MariaDB >= 10.5 (verificado en 10.5.29). InnoDB + utf8mb4.
-- El central es la AUTORIDAD del lock y el corpus buscable; no lleva columnas de outbox
-- (esas son solo del cliente SQLite local, hooks/logbook-schema.sql).
-- Aplicar: mysql <db> < schema.sql   (ver server/INSTALL.md).

SET NAMES utf8mb4;

-- Un trabajo relevable publicado al catálogo compartido.
--   mode='req'         → con requerimiento: relevo cross-dev, lock atómico, transcript.
--   mode='exploratory' → sin REQ: visibilidad + búsqueda del corpus. NO relevable cross-dev
--                        (claude_session_id solo vale en su máquina origen); sin lock.
-- Unicidad por modo: índices parciales no existen en MariaDB → se usa la columna generada
-- identity_key (req=project+req_slug, expl=claude_session_id) con UNIQUE.
CREATE TABLE IF NOT EXISTS work (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  mode                ENUM('req','exploratory') NOT NULL DEFAULT 'req',
  project             VARCHAR(255) NULL,                 -- estable cross-máquina (git remote host/owner/repo); NULL en exploratory
  req_slug            VARCHAR(255) NULL,                 -- NULL en exploratory
  owner               VARCHAR(128) NULL,                 -- username del SO del owner vigente
  lock_state          ENUM('owned','released','takeover_requested') NULL,  -- NULL/irrelevante en exploratory
  takeover_by         VARCHAR(128) NULL,
  locked_at           DATETIME     NULL,
  req_state           VARCHAR(64)  NULL,                 -- ENUM del requerimiento (vocabulary.md); ortogonal a lock_state
  branch              VARCHAR(255) NULL,
  head_commit         VARCHAR(64)  NULL,
  repo_path           VARCHAR(1024) NULL,                -- ruta local en la máquina origen (informativa)
  change_md           VARCHAR(1024) NULL,                -- path del registro (change MD); B propaga este puntero al relevo
  payload_json        LONGTEXT     NULL,                 -- plan, archivos, próximos pasos, "Pendiente de entrega", "Trabajo en vuelo"
  payload_version     INT          NOT NULL DEFAULT 0,   -- concurrencia optimista
  origin_dev          VARCHAR(128) NULL,
  origin_machine      VARCHAR(255) NULL,
  claude_session_id   VARCHAR(128) NULL,                 -- válido SOLO en su máquina origen (no para --resume cross-machine)
  claude_session_name VARCHAR(255) NULL,
  transcript_path     VARCHAR(1024) NULL,                -- ruta del .jsonl en origen; el contenido va en la tabla transcript
  created_at          DATETIME     NOT NULL,
  updated_at          DATETIME     NOT NULL,
  archived_at         DATETIME     NULL,                 -- NULL = activo; se archiva al cerrar (no se borra: corpus de auditoría)
  -- Identidad por modo. CHAR(31) = separador de unidad, evita colisión por contenido.
  identity_key        VARCHAR(600)
                      AS (CASE mode
                            WHEN 'req' THEN CONCAT_WS(CHAR(31), 'req', project, req_slug)
                            ELSE             CONCAT_WS(CHAR(31), 'expl', claude_session_id)
                          END) STORED,
  PRIMARY KEY (id),
  UNIQUE KEY uq_identity (identity_key),
  KEY idx_active (archived_at),
  KEY idx_project_req (project, req_slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Historial de relevo (append-only). Alimenta el corpus de auditoría (REQ D).
CREATE TABLE IF NOT EXISTS event (
  id         BIGINT       NOT NULL AUTO_INCREMENT,
  work_id    BIGINT       NOT NULL,
  ts         DATETIME     NOT NULL,
  dev        VARCHAR(128) NOT NULL,
  action     ENUM('publish','claim','release','forced_release','request_takeover','rename','archive') NOT NULL,
  prev_owner VARCHAR(128) NULL,                          -- en forced_release/claim: a quién se le quitó/tenía el mando
  machine    VARCHAR(255) NULL,
  note       VARCHAR(1024) NULL,                         -- en rename: old→new
  PRIMARY KEY (id),
  KEY idx_event_work (work_id, ts),
  CONSTRAINT fk_event_work FOREIGN KEY (work_id) REFERENCES work(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Transcript buscable, incremental por (session_id, byte_from/to) determinista → idempotente.
-- content = JSONL crudo (reproducibilidad); text_plain = texto indexable (excluye tool_result; sin secretos de outputs).
-- ROW_FORMAT=COMPRESSED: el corpus crece; el JSONL comprime bien.
CREATE TABLE IF NOT EXISTS transcript (
  id          BIGINT       NOT NULL AUTO_INCREMENT,
  session_id  VARCHAR(128) NOT NULL,
  work_id     BIGINT       NOT NULL,
  byte_from   BIGINT       NOT NULL,
  byte_to     BIGINT       NOT NULL,
  content     LONGTEXT     NOT NULL,                     -- JSONL crudo del fragmento
  text_plain  LONGTEXT     NULL,                         -- texto extraído (user/assistant), sin tool_result ni líneas estructurales
  created_at  DATETIME     NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_fragment (session_id, byte_from, byte_to),
  KEY idx_transcript_work (work_id),
  FULLTEXT KEY ft_text_plain (text_plain),
  CONSTRAINT fk_transcript_work FOREIGN KEY (work_id) REFERENCES work(id) ON DELETE CASCADE
) ENGINE=InnoDB ROW_FORMAT=COMPRESSED DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
