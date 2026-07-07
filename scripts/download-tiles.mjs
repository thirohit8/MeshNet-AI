/**
 * scripts/download-tiles.mjs
 * ─────────────────────────────────────────────────────────────────────────────
 * Downloads OpenStreetMap tiles for Manila Metro + building-level core into
 * public/tiles/{z}/{x}/{y}.png so the Leaflet map works fully offline.
 *
 * Tile source: tile.openstreetmap.org  (free, attribution required)
 *
 * Two-region strategy (keeps bundle size manageable):
 *
 *   Region A — Manila Metro  (z13–z16)
 *     Covers the full NCR: Caloocan → Makati → Pasay → Pasig → Quezon City
 *     Bounding box: 14.48–14.72 N, 120.94–121.12 E
 *     Good for city-wide situational awareness and patrol routing.
 *
 *   Region B — Intramuros–Makati–BGC core  (z17, building-level detail)
 *     Covers the dense urban core where most seed-node operations occur.
 *     Bounding box: 14.55–14.63 N, 120.97–121.04 E
 *     Shows individual buildings, alleys, and park footprints.
 *
 * Tile count: ~2 930 tiles  ≈ 43 MB  (~10 min on a 500 kbps link)
 *
 * Usage (run once, then commit public/tiles/ or bundle into the APK):
 *   node scripts/download-tiles.mjs
 *
 * Already-cached tiles are skipped — re-run any time to fetch new tiles.
 * To cover a different deployment city, change REGIONS below and re-run.
 */

import fs from "fs";
import path from "path";
import https from "https";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR   = path.resolve(__dirname, "../public/tiles");

// ── Tile math ─────────────────────────────────────────────────────────────────

function lon2tile(lon, zoom) {
  return Math.floor(((lon + 180) / 360) * Math.pow(2, zoom));
}
function lat2tile(lat, zoom) {
  const r = (lat * Math.PI) / 180;
  return Math.floor(
    ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) *
      Math.pow(2, zoom),
  );
}

// ── Regions ───────────────────────────────────────────────────────────────────
// Each entry: { label, minLat, maxLat, minLon, maxLon, zooms }
// Change these to target a different city for field deployment.

const REGIONS = [
  {
    label:  "Manila Metro (z13-16, city-wide)",
    minLat: 14.48,
    maxLat: 14.72,
    minLon: 120.94,
    maxLon: 121.12,
    zooms:  [13, 14, 15, 16],
  },
  {
    label:  "Intramuros-Makati-BGC core (z17, building-level)",
    minLat: 14.55,
    maxLat: 14.63,
    minLon: 120.97,
    maxLon: 121.04,
    zooms:  [17],
  },
];

// ── Download helper ───────────────────────────────────────────────────────────

const USER_AGENT =
  "MeshNetAI/1.0 offline-tile-downloader (+https://github.com/kingdavid28/MeshNet-AI)";

function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    const dir = path.dirname(dest);
    fs.mkdirSync(dir, { recursive: true });
    if (fs.existsSync(dest)) { resolve("cached"); return; }

    const file = fs.createWriteStream(dest);
    https
      .get(url, { headers: { "User-Agent": USER_AGENT } }, (res) => {
        if (res.statusCode === 200) {
          res.pipe(file);
          file.on("finish", () => { file.close(); resolve("ok"); });
        } else {
          file.close();
          try { fs.unlinkSync(dest); } catch (_) { /* ignore */ }
          reject(new Error(`HTTP ${res.statusCode} for ${url}`));
        }
      })
      .on("error", (err) => {
        try { fs.unlinkSync(dest); } catch (_) { /* ignore */ }
        reject(err);
      });
  });
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

// ── Pre-count total tiles ─────────────────────────────────────────────────────

function countTiles() {
  let n = 0;
  for (const region of REGIONS) {
    for (const z of region.zooms) {
      const xMin = lon2tile(region.minLon, z);
      const xMax = lon2tile(region.maxLon, z);
      const yMin = lat2tile(region.maxLat, z); // lat flipped in slippy tile system
      const yMax = lat2tile(region.minLat, z);
      n += (xMax - xMin + 1) * (yMax - yMin + 1);
    }
  }
  return n;
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  const total = countTiles();
  let downloaded = 0, cached = 0, errors = 0, done = 0;

  console.log("\n  MeshNet AI — Offline Tile Downloader");
  console.log("  ─────────────────────────────────────");
  for (const r of REGIONS) {
    console.log(`  ${r.label}`);
  }
  console.log(`\n  Total tiles to ensure: ${total}`);
  console.log("  (dots = new  ·  dashes = cached  !  = error)\n");

  for (const region of REGIONS) {
    console.log(`\n  [${region.label}]`);
    for (const z of region.zooms) {
      const xMin = lon2tile(region.minLon, z);
      const xMax = lon2tile(region.maxLon, z);
      const yMin = lat2tile(region.maxLat, z);
      const yMax = lat2tile(region.minLat, z);
      const zCount = (xMax - xMin + 1) * (yMax - yMin + 1);
      process.stdout.write(`  z${z} (${zCount} tiles) `);

      for (let x = xMin; x <= xMax; x++) {
        for (let y = yMin; y <= yMax; y++) {
          const url  = `https://tile.openstreetmap.org/${z}/${x}/${y}.png`;
          const dest = path.join(OUT_DIR, `${z}`, `${x}`, `${y}.png`);
          try {
            const result = await downloadFile(url, dest);
            if (result === "cached") {
              cached++;
              process.stdout.write("-");
            } else {
              downloaded++;
              process.stdout.write(".");
              // OSM tile usage policy: be polite — 200 ms between fresh downloads
              await sleep(200);
            }
          } catch (err) {
            errors++;
            process.stdout.write("!");
            process.stderr.write(`\n  ERROR z=${z} x=${x} y=${y}: ${err.message}\n`);
          }
          done++;
          // Progress percentage every 50 tiles
          if (done % 50 === 0) {
            process.stdout.write(` ${Math.round((done / total) * 100)}%\n  `);
          }
        }
      }
      console.log();
    }
  }

  const sizeMB = (downloaded * 15) / 1024;
  console.log("\n  ─────────────────────────────────────");
  console.log(`  Downloaded : ${downloaded} new tiles  (~${sizeMB.toFixed(0)} MB)`);
  console.log(`  Cached     : ${cached} tiles (already present)`);
  console.log(`  Errors     : ${errors}`);
  console.log(`  Output     : ${OUT_DIR}`);
  console.log("  ─────────────────────────────────────\n");

  if (errors > 0) {
    console.warn("  Some tiles failed. Re-run the script to retry missing ones.");
    process.exit(1);
  }
}

main().catch((err) => { console.error(err); process.exit(1); });
