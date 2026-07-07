-- MeshNet AI — canonical schema
-- SQLite 3.x

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── Nodes ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS nodes (
  id          TEXT PRIMARY KEY,              -- public-key-derived node identity
  label       TEXT NOT NULL,                 -- short display name e.g. "CMD·HQ"
  name        TEXT NOT NULL,                 -- device model e.g. "ThinkPad X1"
  device      TEXT NOT NULL CHECK (device IN ('smartphone', 'laptop')),
  role        TEXT NOT NULL DEFAULT 'peer' CHECK (role IN ('peer', 'relay')),
  signal      INTEGER NOT NULL DEFAULT 80,   -- 0–100 RSSI-normalised
  os          TEXT,
  lat         REAL,
  lng         REAL,
  last_seen   TEXT NOT NULL DEFAULT (datetime('now')),
  registered  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Edges (mesh links) ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS edges (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  node_a      TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  node_b      TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  protocol    TEXT NOT NULL CHECK (protocol IN ('wifi', 'bluetooth')),
  quality     INTEGER NOT NULL DEFAULT 80,   -- 0–100
  observed_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (node_a, node_b, protocol)
);

-- ── Alerts ────────────────────────────────────────────────────────────────────
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

-- ── Messages ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
  id            TEXT PRIMARY KEY,
  from_node_id  TEXT NOT NULL REFERENCES nodes(id),
  from_label    TEXT NOT NULL,
  to_node_id    TEXT NOT NULL,               -- node id or 'broadcast'
  category      TEXT NOT NULL CHECK (category IN ('alert','medical','info','gps')),
  ciphertext    TEXT NOT NULL,               -- AES-GCM encrypted payload (base64)
  hops          INTEGER NOT NULL DEFAULT 0,
  read          INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_to      ON messages(to_node_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);

-- ── Signal flicker events ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signal_events (
  id           TEXT    PRIMARY KEY,
  node_id      TEXT    NOT NULL,
  node_label   TEXT    NOT NULL,
  prev_signal  INTEGER NOT NULL DEFAULT 0,
  curr_signal  INTEGER NOT NULL DEFAULT 0,
  scenario     TEXT    NOT NULL DEFAULT 'earthquake',
  burst        INTEGER NOT NULL DEFAULT 0,
  detected_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_signal_events_node  ON signal_events(node_id);
CREATE INDEX IF NOT EXISTS idx_signal_events_ts    ON signal_events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_events_burst ON signal_events(burst);

-- ── Routing table (AODV) ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS routes (
  destination   TEXT NOT NULL,
  next_hop      TEXT NOT NULL,
  hop_count     INTEGER NOT NULL,
  seq_number    INTEGER NOT NULL DEFAULT 0,
  updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (destination, next_hop)
);
