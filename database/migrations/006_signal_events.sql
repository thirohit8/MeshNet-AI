-- Migration 006 — signal_events table (SQLite / local dev)
-- MeshNet AI — Layer 4: Signal Flicker Detection
--
-- Tracks signal transitions (0 → ≥1 bar) on mesh nodes.
-- Created by this migration so the schema is fully tracked.
-- (backend/src/db.ts also auto-creates this table on startup as a guard.)
--
-- Populated by: POST /api/signal/report  (backend/src/routes/signal.ts)
-- Queried by:   GET  /api/signal/events
-- Streamed via: GET  /api/signal/stream  (SSE — rescue dashboard)

CREATE TABLE IF NOT EXISTS signal_events (
  id           TEXT    PRIMARY KEY,
  node_id      TEXT    NOT NULL,
  node_label   TEXT    NOT NULL,
  prev_signal  INTEGER NOT NULL DEFAULT 0,
  curr_signal  INTEGER NOT NULL DEFAULT 0,
  scenario     TEXT    NOT NULL DEFAULT 'earthquake',
  -- 0 = event detected; 1 = high-priority burst has been dispatched
  burst        INTEGER NOT NULL DEFAULT 0
                       CHECK (burst IN (0, 1)),
  detected_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_signal_events_node  ON signal_events (node_id);
CREATE INDEX IF NOT EXISTS idx_signal_events_ts    ON signal_events (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_events_burst ON signal_events (burst);
