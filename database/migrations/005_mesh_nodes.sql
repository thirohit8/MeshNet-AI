-- Migration 005 — mesh_nodes virtual environment table (Supabase/PostgreSQL)
-- SUPABASE_ONLY
-- MeshNet AI — Layer 4: Virtual Environment (100 simulated disaster-zone citizens)
--
-- Spec: Section 2 — "Create the virtual environment profiles"
--
-- Table name : mesh_nodes
-- Row count  : 100 (serial node_id 1–100)
-- Node #100  : is_rescue_team = TRUE  (rescue camp portal)
-- Coordinates: ≤ 1 km radius around Manila (14.5995°N, 120.9842°E)
--
-- ── Apply to Supabase ─────────────────────────────────────────────────────────
--   Option A (recommended): Paste into Supabase → SQL Editor → New query → Run
--   Option B (psql):  psql $SUPABASE_DB_URL -f database/migrations/005_mesh_nodes.sql
--
-- ── Apply to local SQLite (dev) ───────────────────────────────────────────────
--   npx ts-node database/migrations/run.ts
--   (run.ts picks up .sql files alphabetically — 005 runs after 004)
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Table definition ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mesh_nodes (
  -- Primary key: serial integer 1–100 matching the simulation node number
  node_id             SERIAL      PRIMARY KEY,  -- PostgreSQL: auto-increment
  -- For SQLite, use: node_id INTEGER PRIMARY KEY AUTOINCREMENT

  -- Citizen identity (fake name for simulation purposes)
  citizen_name        TEXT        NOT NULL,

  -- GPS coordinates within 1 km radius of Manila disaster zone
  -- Base: 14.5995°N, 120.9842°E  (Barangay 892, Manila)
  latitude            FLOAT       NOT NULL CHECK (latitude  BETWEEN 14.58 AND 14.62),
  longitude           FLOAT       NOT NULL CHECK (longitude BETWEEN 120.97 AND 121.00),

  -- Device telemetry
  battery_percentage  INTEGER     NOT NULL DEFAULT 100 CHECK (battery_percentage BETWEEN 1 AND 100),

  -- TRUE  = device is BLE-scanning and reachable on the mesh
  -- FALSE = device is offline / out of Bluetooth range
  bluetooth_status    BOOLEAN     NOT NULL DEFAULT FALSE,

  -- TRUE only for Node #100 — the rescue camp command portal
  -- All SOS routing paths converge on this node
  is_rescue_team      BOOLEAN     NOT NULL DEFAULT FALSE,

  -- Extra telemetry fields (used by the routing engine + map canvas)
  signal              INTEGER     NOT NULL DEFAULT 80 CHECK (signal BETWEEN 0 AND 100),
  device              TEXT        NOT NULL DEFAULT 'smartphone' CHECK (device IN ('smartphone','laptop')),
  role                TEXT        NOT NULL DEFAULT 'peer'       CHECK (role   IN ('peer','relay')),
  os                  TEXT,
  last_seen           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  registered          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_mesh_nodes_bluetooth ON mesh_nodes (bluetooth_status);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_rescue    ON mesh_nodes (is_rescue_team);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_battery   ON mesh_nodes (battery_percentage);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_last_seen ON mesh_nodes (last_seen DESC);

-- ── Supabase Realtime ─────────────────────────────────────────────────────────
-- Add mesh_nodes to the existing realtime publication (created in migration 004).
-- Clients can subscribe to INSERT/UPDATE on this table for live map updates.

DO $$
BEGIN
  -- Add mesh_nodes to the existing publication if it exists
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'meshnet_realtime') THEN
    ALTER PUBLICATION meshnet_realtime ADD TABLE mesh_nodes;
  END IF;
END
$$;

-- ── Row Level Security ────────────────────────────────────────────────────────

ALTER TABLE mesh_nodes ENABLE ROW LEVEL SECURITY;

-- Anonymous Supabase clients (frontend) can read all node rows
CREATE POLICY "mesh_nodes: public read"
  ON mesh_nodes FOR SELECT USING (TRUE);

-- Only the service_role key (backend) may insert / update / delete
CREATE POLICY "mesh_nodes: service_role write"
  ON mesh_nodes FOR ALL USING (auth.role() = 'service_role');

-- ── Convenience view: active_nodes ───────────────────────────────────────────
-- Returns only BLE-active nodes — used by the routing engine's graph builder.

CREATE OR REPLACE VIEW active_nodes AS
  SELECT * FROM mesh_nodes
  WHERE bluetooth_status = TRUE
  ORDER BY node_id;

COMMENT ON VIEW active_nodes IS
  'BLE-active mesh nodes — only these participate in routing graph construction.';

COMMENT ON TABLE mesh_nodes IS
  'Virtual environment simulation table. 100 rows represent citizens in a 1 km disaster zone around Manila. Node #100 is the rescue camp portal (is_rescue_team=TRUE).';
