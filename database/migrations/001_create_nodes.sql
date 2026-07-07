-- Migration 001 — nodes and edges tables
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS nodes (
  id                 TEXT PRIMARY KEY,
  label              TEXT NOT NULL,
  name               TEXT NOT NULL,
  device             TEXT NOT NULL CHECK (device IN ('smartphone', 'laptop')),
  role               TEXT NOT NULL DEFAULT 'peer' CHECK (role IN ('peer', 'relay')),
  signal             INTEGER NOT NULL DEFAULT 80,
  -- battery_percentage: 0-100; nodes under 20% are flagged as critical
  battery_percentage INTEGER NOT NULL DEFAULT 100 CHECK (battery_percentage BETWEEN 0 AND 100),
  -- bluetooth_status: 1 = BLE scanning active (green dot), 0 = BLE off (grey dot)
  bluetooth_status   INTEGER NOT NULL DEFAULT 0 CHECK (bluetooth_status IN (0, 1)),
  os                 TEXT,
  lat                REAL,
  lng                REAL,
  last_seen          TEXT NOT NULL DEFAULT (datetime('now')),
  registered         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS edges (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  node_a      TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  node_b      TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  protocol    TEXT NOT NULL CHECK (protocol IN ('wifi', 'bluetooth')),
  quality     INTEGER NOT NULL DEFAULT 80,
  observed_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (node_a, node_b, protocol)
);
