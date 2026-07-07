# MeshNet-AI — Offline Tile Cache

This directory holds the pre-downloaded map tile datasets used by the offline
map module (`mapview_module.py`).  **No internet connection is used at runtime.**

---

## Directory Layout

```
tiles/
├── standard/          ← OpenStreetMap-style vector raster tiles
│   └── {z}/
│       └── {x}/
│           └── {y}.png
└── satellite/         ← High-resolution satellite raster tiles
    └── {z}/
        └── {x}/
            └── {y}.png
```

Tile coordinates follow the **XYZ (Slippy Map)** scheme used by OSM and
most web mapping APIs:

| Parameter | Meaning                    |
|-----------|----------------------------|
| `z`       | Zoom level  (1 – 18)       |
| `x`       | Tile column (west → east)  |
| `y`       | Tile row    (north → south)|

---

## Downloading Tiles for Offline Use

### Option A — MOBAC (Mobile Atlas Creator)

1. Install **MOBAC** from https://mobac.sourceforge.io/
2. Select your map area using the selection tool.
3. Choose atlas format **"OsmDroid ZIP"** (produces {z}/{x}/{y}.png layout).
4. Extract the ZIP into `tiles/standard/` or `tiles/satellite/`.

### Option B — `tile-dl` CLI tool

```bash
pip install tile-dl
# Standard (OpenStreetMap)
tile-dl --zoom 10-16 --bbox -118.35,33.95,-118.10,34.15 \
        --url "https://tile.openstreetmap.org/{z}/{x}/{y}.png" \
        --output tiles/standard/

# Satellite (Esri WorldImagery — check licence)
tile-dl --zoom 10-16 --bbox -118.35,33.95,-118.10,34.15 \
        --url "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" \
        --output tiles/satellite/
```

> **Note:** Tile providers have individual Terms of Service.  Pre-download
> tiles only for areas and zoom levels you have the right to cache.

### Option C — QTiles QGIS Plugin

Generate tiles from your own GIS data (shapefiles, GeoTIFF) entirely offline.

---

## Storage Estimates

| Zoom range | Approx. tiles (50 km × 50 km) | Size (PNG) |
|------------|-------------------------------|------------|
| 10 – 14    | ~3 000                        | ~45 MB     |
| 10 – 16    | ~18 000                       | ~270 MB    |
| 10 – 18    | ~72 000                       | ~1.1 GB    |

---

## Android Deployment

The tile directory is bundled into the APK via `buildozer.spec`:

```ini
source.include_patterns = assets/*,tiles/**
```

At runtime, `mapview_module._tiles_root()` resolves to:

```
<app_storage_path>/tiles/
```

Alternatively, copy the `tiles/` directory to the device's external storage
and update `TILES_ROOT` in `mapview_module.py` accordingly.
