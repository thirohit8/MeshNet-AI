#!/usr/bin/env ts-node
/**
 * seed_mesh_nodes.ts — Load mesh_nodes CSV into local SQLite (dev)
 * database/seeds/seed_mesh_nodes.ts
 *
 * Reads database/seeds/mesh_nodes.csv and upserts all 100 rows into
 * the mesh_nodes table in the local SQLite database.
 *
 * Usage
 * -----
 *   npx ts-node database/seeds/seed_mesh_nodes.ts
 *   DB_PATH=/custom/path.db npx ts-node database/seeds/seed_mesh_nodes.ts
 *
 * Prerequisites
 * -------------
 *   Run migrations first: npx ts-node database/migrations/run.ts
 *   (Migration 005 creates the mesh_nodes table)
 */

import Database from "better-sqlite3";
import fs from "fs";
import path from "path";

// ─── Config ───────────────────────────────────────────────────────────────────

const DB_PATH  = process.env.DB_PATH  ?? path.resolve(__dirname, "..", "meshnet.db");
const CSV_PATH = process.env.CSV_PATH ?? path.resolve(__dirname, "mesh_nodes.csv");

// ─── SQLite: create mesh_nodes table if migration 005 hasn't run yet ─────────

const db = new Database(DB_PATH);
db.pragma("journal_mode = WAL");
db.pragma("foreign_keys = ON");

db.exec(`
  CREATE TABLE IF NOT EXISTS mesh_nodes (
    node_id             INTEGER PRIMARY KEY,
    citizen_name        TEXT    NOT NULL,
    latitude            REAL    NOT NULL,
    longitude           REAL    NOT NULL,
    battery_percentage  INTEGER NOT NULL DEFAULT 100,
    bluetooth_status    INTEGER NOT NULL DEFAULT 0,
    is_rescue_team      INTEGER NOT NULL DEFAULT 0,
    signal              INTEGER NOT NULL DEFAULT 80,
    device              TEXT    NOT NULL DEFAULT 'smartphone',
    role                TEXT    NOT NULL DEFAULT 'peer',
    os                  TEXT,
    last_seen           TEXT    NOT NULL DEFAULT (datetime('now')),
    registered          TEXT    NOT NULL DEFAULT (datetime('now'))
  )
`);

// ─── Parse CSV ────────────────────────────────────────────────────────────────

const csv = fs.readFileSync(CSV_PATH, "utf8");
const lines = csv.trim().split("\n");
const headers = lines[0].split(",");

interface CsvRow {
  node_id:            number;
  citizen_name:       string;
  latitude:           number;
  longitude:          number;
  battery_percentage: number;
  bluetooth_status:   number;  // SQLite: 0|1
  is_rescue_team:     number;  // SQLite: 0|1
  signal:             number;
  device:             string;
  role:               string;
  os:                 string;
}

function parseRow(line: string): CsvRow {
  // Handle names with commas (e.g. "Dela Cruz, Jr") — not in this dataset
  // but defensive split on commas outside quotes
  const parts = line.split(",");
  const get = (col: string) => parts[headers.indexOf(col)]?.trim() ?? "";

  return {
    node_id:            parseInt(get("node_id"),            10),
    citizen_name:       get("citizen_name"),
    latitude:           parseFloat(get("latitude")),
    longitude:          parseFloat(get("longitude")),
    battery_percentage: parseInt(get("battery_percentage"), 10),
    bluetooth_status:   get("bluetooth_status") === "true" ? 1 : 0,
    is_rescue_team:     get("is_rescue_team")   === "true" ? 1 : 0,
    signal:             parseInt(get("signal"), 10),
    device:             get("device"),
    role:               get("role"),
    os:                 get("os"),
  };
}

const rows: CsvRow[] = lines.slice(1).filter(Boolean).map(parseRow);

// ─── Upsert ───────────────────────────────────────────────────────────────────

const upsert = db.prepare(`
  INSERT INTO mesh_nodes
    (node_id, citizen_name, latitude, longitude, battery_percentage,
     bluetooth_status, is_rescue_team, signal, device, role, os)
  VALUES
    (@node_id, @citizen_name, @latitude, @longitude, @battery_percentage,
     @bluetooth_status, @is_rescue_team, @signal, @device, @role, @os)
  ON CONFLICT(node_id) DO UPDATE SET
    citizen_name       = excluded.citizen_name,
    latitude           = excluded.latitude,
    longitude          = excluded.longitude,
    battery_percentage = excluded.battery_percentage,
    bluetooth_status   = excluded.bluetooth_status,
    is_rescue_team     = excluded.is_rescue_team,
    signal             = excluded.signal,
    device             = excluded.device,
    role               = excluded.role,
    os                 = excluded.os
`);

const insertAll = db.transaction((data: CsvRow[]) => {
  for (const row of data) upsert.run(row);
});

insertAll(rows);

// ─── Summary ──────────────────────────────────────────────────────────────────

const stats = db.prepare(`
  SELECT
    COUNT(*)                                        AS total,
    SUM(bluetooth_status)                           AS ble_active,
    SUM(is_rescue_team)                             AS rescue_portals,
    SUM(CASE WHEN role = 'relay' THEN 1 ELSE 0 END) AS relay_nodes,
    ROUND(AVG(battery_percentage), 1)               AS avg_battery
  FROM mesh_nodes
`).get() as {
  total: number; ble_active: number; rescue_portals: number;
  relay_nodes: number; avg_battery: number;
};

console.log(`\n✓ mesh_nodes seeded — ${stats.total} rows`);
console.log(`  BLE active   : ${stats.ble_active}`);
console.log(`  Relay nodes  : ${stats.relay_nodes}`);
console.log(`  Rescue portal: ${stats.rescue_portals} (node #100)`);
console.log(`  Avg battery  : ${stats.avg_battery}%`);
console.log(`  DB           : ${DB_PATH}\n`);

db.close();
