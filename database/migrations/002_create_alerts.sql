-- Migration 002 — alerts table

CREATE TABLE IF NOT EXISTS alerts (
  id             TEXT PRIMARY KEY,
  type           TEXT NOT NULL CHECK (type IN ('sos','medical','safe','hazard','supply','locate')),
  severity       TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low')),
  from_node_id   TEXT NOT NULL REFERENCES nodes(id),
  from_label     TEXT NOT NULL,
  message        TEXT,
  lat            REAL,
  lng            REAL,
  ttl            INTEGER NOT NULL DEFAULT 7,
  acknowledged   INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_type    ON alerts(type);
