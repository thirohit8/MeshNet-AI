-- Migration 005b — mesh_nodes table (SQLite / local dev)
-- MeshNet AI — Layer 4: Virtual Environment (100 simulated disaster-zone citizens)
--
-- SQLite-compatible version of migration 005.
-- The Supabase/PostgreSQL version is in 005_mesh_nodes.sql (SUPABASE_ONLY).
--
-- Table name : mesh_nodes
-- Row count  : 100 seeded via: cd database && npm run seed:mesh
-- Node #100  : is_rescue_team = 1  (rescue camp portal)
-- Coordinates: within 1 km of Manila (14.5995°N, 120.9842°E)

CREATE TABLE IF NOT EXISTS mesh_nodes (
  -- Integer PK 1–100 matching the simulation node serial number
  node_id             INTEGER PRIMARY KEY,

  citizen_name        TEXT    NOT NULL,
  latitude            REAL    NOT NULL,
  longitude           REAL    NOT NULL,

  battery_percentage  INTEGER NOT NULL DEFAULT 100
                              CHECK (battery_percentage BETWEEN 1 AND 100),

  -- 1 = BLE scanning active (reachable), 0 = offline
  bluetooth_status    INTEGER NOT NULL DEFAULT 0
                              CHECK (bluetooth_status IN (0, 1)),

  -- 1 only for Node #100 — rescue camp command portal
  is_rescue_team      INTEGER NOT NULL DEFAULT 0
                              CHECK (is_rescue_team IN (0, 1)),

  -- Extra telemetry used by the routing engine and map canvas
  signal              INTEGER NOT NULL DEFAULT 80
                              CHECK (signal BETWEEN 0 AND 100),
  device              TEXT    NOT NULL DEFAULT 'smartphone'
                              CHECK (device IN ('smartphone', 'laptop')),
  role                TEXT    NOT NULL DEFAULT 'peer'
                              CHECK (role   IN ('peer', 'relay')),
  os                  TEXT,
  last_seen           TEXT    NOT NULL DEFAULT (datetime('now')),
  registered          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mesh_nodes_bluetooth ON mesh_nodes (bluetooth_status);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_rescue    ON mesh_nodes (is_rescue_team);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_battery   ON mesh_nodes (battery_percentage);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_last_seen ON mesh_nodes (last_seen DESC);
