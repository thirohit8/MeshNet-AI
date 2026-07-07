-- Migration 003 — messages and routing tables

CREATE TABLE IF NOT EXISTS messages (
  id            TEXT PRIMARY KEY,
  from_node_id  TEXT NOT NULL REFERENCES nodes(id),
  from_label    TEXT NOT NULL,
  to_node_id    TEXT NOT NULL,
  category      TEXT NOT NULL CHECK (category IN ('alert','medical','info','gps')),
  ciphertext    TEXT NOT NULL,
  hops          INTEGER NOT NULL DEFAULT 0,
  read          INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_to      ON messages(to_node_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);

CREATE TABLE IF NOT EXISTS routes (
  destination   TEXT NOT NULL,
  next_hop      TEXT NOT NULL,
  hop_count     INTEGER NOT NULL,
  seq_number    INTEGER NOT NULL DEFAULT 0,
  updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (destination, next_hop)
);
