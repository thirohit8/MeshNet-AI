#!/usr/bin/env ts-node
// Loads seed data into the SQLite DB for local development.
// Usage: npx ts-node seeds/run.ts
// Safe to re-run — uses INSERT OR REPLACE.

import Database from "better-sqlite3";
import path from "path";
import nodes from "./nodes.json";
import alerts from "./alerts.json";

const DB_PATH = process.env.DB_PATH ?? path.join(__dirname, "..", "meshnet.db");
const db = new Database(DB_PATH);
db.pragma("foreign_keys = ON");

// ── Nodes ──────────────────────────────────────────────────────────────────────
const insertNode = db.prepare(`
  INSERT OR REPLACE INTO nodes (id, label, name, device, role, signal, battery_percentage, bluetooth_status, os, lat, lng)
  VALUES (@id, @label, @name, @device, @role, @signal, @battery_percentage, @bluetooth_status, @os, @lat, @lng)
`);
db.transaction((rows: typeof nodes) => rows.forEach((r) => insertNode.run(r)))(nodes);
console.log(`  seeded ${nodes.length} nodes`);

// ── Edges ──────────────────────────────────────────────────────────────────────
const edges = [
  { node_a: "cmd-hq",      node_b: "ramos-phone",  protocol: "bluetooth", quality: 87 },
  { node_a: "cmd-hq",      node_b: "chen-laptop",   protocol: "wifi",      quality: 72 },
  { node_a: "cmd-hq",      node_b: "med-01",        protocol: "wifi",      quality: 91 },
  { node_a: "ramos-phone", node_b: "torres-phone",  protocol: "bluetooth", quality: 64 },
  { node_a: "med-01",      node_b: "torres-phone",  protocol: "bluetooth", quality: 70 },
  { node_a: "chen-laptop", node_b: "med-01",        protocol: "wifi",      quality: 80 },
];
const insertEdge = db.prepare(`
  INSERT OR REPLACE INTO edges (node_a, node_b, protocol, quality)
  VALUES (@node_a, @node_b, @protocol, @quality)
`);
db.transaction((rows: typeof edges) => rows.forEach((r) => insertEdge.run(r)))(edges);
console.log(`  seeded ${edges.length} edges`);

// ── Alerts ─────────────────────────────────────────────────────────────────────
const insertAlert = db.prepare(`
  INSERT OR REPLACE INTO alerts (id, type, severity, from_node_id, from_label, message, lat, lng, ttl, acknowledged)
  VALUES (@id, @type, @severity, @from_node_id, @from_label, @message, @lat, @lng, @ttl, @acknowledged)
`);
db.transaction((rows: typeof alerts) => rows.forEach((r) => insertAlert.run(r)))(alerts);
console.log(`  seeded ${alerts.length} alerts`);

console.log(`\nDone. DB: ${DB_PATH}`);
db.close();
