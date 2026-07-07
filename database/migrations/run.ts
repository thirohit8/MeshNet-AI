#!/usr/bin/env ts-node
// Runs all SQLite-compatible migration files in numeric order.
// Usage: npx ts-node migrations/run.ts
//
// Files that target PostgreSQL/Supabase only must include the line:
//   -- SUPABASE_ONLY
// as one of their first 5 lines. The runner skips those files so they
// are never executed against the local SQLite database.

import Database from "better-sqlite3";
import fs from "fs";
import path from "path";

const DB_PATH = process.env.DB_PATH ?? path.join(__dirname, "..", "meshnet.db");
const db = new Database(DB_PATH);

db.pragma("journal_mode = WAL");
db.pragma("foreign_keys = ON");

db.exec(`
  CREATE TABLE IF NOT EXISTS _migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
  )
`);

const applied = new Set<string>(
  (db.prepare("SELECT filename FROM _migrations").all() as { filename: string }[]).map(
    (r) => r.filename
  )
);

// ── Helper: detect Supabase-only files ───────────────────────────────────────
// A file is skipped when its first 5 lines contain "-- SUPABASE_ONLY".
function isSupabaseOnly(filePath: string): boolean {
  const firstLines = fs.readFileSync(filePath, "utf8").split("\n").slice(0, 5);
  return firstLines.some((l) => l.trim() === "-- SUPABASE_ONLY");
}

const migrationsDir = __dirname;
const files = fs
  .readdirSync(migrationsDir)
  .filter((f) => f.endsWith(".sql"))
  .sort();

let count = 0;
for (const file of files) {
  const filePath = path.join(migrationsDir, file);

  if (isSupabaseOnly(filePath)) {
    console.log(`  skip  ${file} (Supabase/PostgreSQL — not applied to SQLite)`);
    continue;
  }

  if (applied.has(file)) {
    console.log(`  skip  ${file} (already applied)`);
    continue;
  }

  const sql = fs.readFileSync(filePath, "utf8");
  db.exec(sql);
  db.prepare("INSERT INTO _migrations (filename) VALUES (?)").run(file);
  console.log(`  apply ${file}`);
  count++;
}

console.log(`\nDone — ${count} migration(s) applied. DB: ${DB_PATH}`);
db.close();
