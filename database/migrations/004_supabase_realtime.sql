-- Migration 004 — Supabase / PostgreSQL Realtime schema
-- SUPABASE_ONLY
-- MeshNet AI — Layer 4: Data Storage Layer
--
-- This migration targets PostgreSQL (Supabase) and adds:
--   1. All core tables mirrored from the SQLite schema (mesh-compatible types)
--   2. Supabase Realtime publication so the frontend can subscribe to
--      live INSERT / UPDATE events on nodes, alerts, and messages.
--   3. Row-Level Security (RLS) policies for production deployments.
--
-- Apply with:
--   psql $SUPABASE_DB_URL -f 004_supabase_realtime.sql
-- Or paste into the Supabase SQL editor (Dashboard → SQL Editor → New query).

-- ── Extensions ────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- uuid_generate_v4()
CREATE EXTENSION IF NOT EXISTS "pgcrypto";      -- gen_random_uuid()

-- ── Nodes ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS nodes (
  id                  TEXT        PRIMARY KEY,
  label               TEXT        NOT NULL,
  name                TEXT        NOT NULL,
  device              TEXT        NOT NULL CHECK (device IN ('smartphone', 'laptop')),
  role                TEXT        NOT NULL DEFAULT 'peer' CHECK (role IN ('peer', 'relay')),
  signal              INTEGER     NOT NULL DEFAULT 80,
  battery_percentage  INTEGER     NOT NULL DEFAULT 100 CHECK (battery_percentage BETWEEN 0 AND 100),
  bluetooth_status    BOOLEAN     NOT NULL DEFAULT FALSE,
  os                  TEXT,
  lat                 DOUBLE PRECISION,
  lng                 DOUBLE PRECISION,
  last_seen           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  registered          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Edges (mesh links) ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS edges (
  id          SERIAL      PRIMARY KEY,
  node_a      TEXT        NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  node_b      TEXT        NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  protocol    TEXT        NOT NULL CHECK (protocol IN ('wifi', 'bluetooth')),
  quality     INTEGER     NOT NULL DEFAULT 80 CHECK (quality BETWEEN 0 AND 100),
  observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (node_a, node_b, protocol)
);

-- ── Alerts ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alerts (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  type          TEXT        NOT NULL CHECK (type IN ('sos','medical','safe','hazard','supply','locate')),
  severity      TEXT        NOT NULL CHECK (severity IN ('critical','high','medium','low')),
  from_node_id  TEXT        NOT NULL REFERENCES nodes(id),
  from_label    TEXT        NOT NULL,
  message       TEXT,
  lat           DOUBLE PRECISION,
  lng           DOUBLE PRECISION,
  ttl           INTEGER     NOT NULL DEFAULT 7,
  acknowledged  BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_type    ON alerts (type);

-- ── Messages ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS messages (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  from_node_id  TEXT        NOT NULL REFERENCES nodes(id),
  from_label    TEXT        NOT NULL,
  to_node_id    TEXT        NOT NULL,    -- node id or 'broadcast'
  category      TEXT        NOT NULL CHECK (category IN ('alert','medical','info','gps')),
  ciphertext    TEXT        NOT NULL,    -- AES-GCM base64 payload
  hops          INTEGER     NOT NULL DEFAULT 0,
  read          BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_to      ON messages (to_node_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages (created_at DESC);

-- ── Routing table (AODV) ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS routes (
  destination  TEXT        NOT NULL,
  next_hop     TEXT        NOT NULL,
  hop_count    INTEGER     NOT NULL,
  seq_number   INTEGER     NOT NULL DEFAULT 0,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (destination, next_hop)
);

-- ── Supabase Realtime publication ─────────────────────────────────────────────
-- Enables postgres_changes so the frontend can subscribe to live updates.
-- See: https://supabase.com/docs/guides/realtime/postgres-changes

-- Create a dedicated publication for MeshNet tables
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication WHERE pubname = 'meshnet_realtime'
  ) THEN
    CREATE PUBLICATION meshnet_realtime
      FOR TABLE nodes, alerts, messages;
  END IF;
END
$$;

-- ── Row-Level Security ────────────────────────────────────────────────────────
-- Enable RLS on all tables.  By default all access is denied.
-- Replace the permissive policies below with fine-grained ones for production.

ALTER TABLE nodes    ENABLE ROW LEVEL SECURITY;
ALTER TABLE edges    ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts   ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE routes   ENABLE ROW LEVEL SECURITY;

-- Allow anon / authenticated Supabase clients to read all rows
CREATE POLICY "Allow read for all"
  ON nodes FOR SELECT USING (TRUE);

CREATE POLICY "Allow read for all"
  ON edges FOR SELECT USING (TRUE);

CREATE POLICY "Allow read for all"
  ON alerts FOR SELECT USING (TRUE);

CREATE POLICY "Allow read for all"
  ON messages FOR SELECT USING (TRUE);

-- Allow service_role (backend) to insert / update / delete
CREATE POLICY "Service role full access on nodes"
  ON nodes FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on edges"
  ON edges FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on alerts"
  ON alerts FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on messages"
  ON messages FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on routes"
  ON routes FOR ALL USING (auth.role() = 'service_role');

-- ── Helper function: upsert_node ─────────────────────────────────────────────
-- Convenience function called by the Express backend on each heartbeat.

CREATE OR REPLACE FUNCTION upsert_node(
  p_id                TEXT,
  p_label             TEXT,
  p_name              TEXT,
  p_device            TEXT,
  p_role              TEXT,
  p_signal            INTEGER,
  p_battery           INTEGER,
  p_bluetooth         BOOLEAN,
  p_os                TEXT DEFAULT NULL,
  p_lat               DOUBLE PRECISION DEFAULT NULL,
  p_lng               DOUBLE PRECISION DEFAULT NULL
) RETURNS nodes AS $$
DECLARE
  v_node nodes;
BEGIN
  INSERT INTO nodes (id, label, name, device, role, signal, battery_percentage, bluetooth_status, os, lat, lng)
  VALUES (p_id, p_label, p_name, p_device, p_role, p_signal, p_battery, p_bluetooth, p_os, p_lat, p_lng)
  ON CONFLICT (id) DO UPDATE SET
    label              = EXCLUDED.label,
    signal             = EXCLUDED.signal,
    battery_percentage = EXCLUDED.battery_percentage,
    bluetooth_status   = EXCLUDED.bluetooth_status,
    lat                = COALESCE(EXCLUDED.lat,  nodes.lat),
    lng                = COALESCE(EXCLUDED.lng,  nodes.lng),
    last_seen          = NOW()
  RETURNING * INTO v_node;
  RETURN v_node;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
