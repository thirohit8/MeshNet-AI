# MeshNet-AI — Offline Emergency Communication Platform

> **Production-ready Kivy/KivyMD application for Android.**  
> Operates entirely without internet or cellular networks using Bluetooth and Wi-Fi Direct mesh routing.

---

## Project Structure

```
meshnet_ai/
├── main.py               ← App entry point, MDApp subclass, permission bootstrap
├── hardware.py           ← Android BT/WiFi adapter integration (pyjnius JNI)
├── routing.py            ← P2P mesh routing engine (filter → score → path)
├── messaging.py          ← Hop-by-hop SOS broadcast + encrypted handshake log
├── mapview_module.py     ← Offline tile map, NodeMarker, PathLayer, MapManager
├── ui.py                 ← KivyMD split-screen dashboard, all widget classes
├── meshnet.kv            ← KV language styling rules
├── buildozer.spec        ← Full Android build configuration
├── assets/
│   ├── icon.png          ← 512×512 app icon (required before build)
│   ├── presplash.png     ← Splash screen image
│   ├── marker_active.png ← Green map marker for active peers
│   ├── marker_hq.png     ← Amber map marker for Weather-HQ peers
│   └── marker_low.png    ← Red map marker for low-battery peers
├── tiles/
│   ├── standard/         ← OSM-style vector raster tiles  {z}/{x}/{y}.png
│   └── satellite/        ← High-res satellite raster tiles {z}/{x}/{y}.png
├── logs/                 ← Encrypted handshake_log.enc written here
└── tests/
    ├── test_routing.py
    └── test_messaging.py
```

---

## Requirements

### Development machine
```
pip install kivy==2.3.0 kivymd==1.2.0 kivy-garden buildozer
garden install mapview
```

### Android build
```
pip install buildozer cython
sudo apt install -y openjdk-17-jdk build-essential git zip unzip
```

---

## Offline Tile Setup

Download map tiles before deploying to device.  
Recommended tool: [Mobile Atlas Creator](https://mobac.sourceforge.io/) or `wget` + tile mirror.

```
tiles/
  standard/13/1234/5678.png   ← zoom/x/y.png
  satellite/13/1234/5678.png
```

Copy to device storage:
```bash
adb push tiles/ /sdcard/Android/data/org.meshnetai/files/tiles/
```

---

## Build & Deploy

```bash
# Debug build + deploy + live logcat
cd meshnet_ai/
buildozer android debug deploy run logcat

# Release build (requires keystore)
buildozer android release
```

---

## Android Permissions Declared

| Permission | Purpose |
|---|---|
| `BLUETOOTH` | Discover and communicate with BT peers |
| `BLUETOOTH_ADMIN` | Enable/disable BT adapter |
| `BLUETOOTH_SCAN` / `BLUETOOTH_CONNECT` / `BLUETOOTH_ADVERTISE` | Android 12+ BT permissions |
| `ACCESS_WIFI_STATE` | Read Wi-Fi adapter state |
| `CHANGE_WIFI_STATE` | Enable Wi-Fi adapter (API ≤ 28) |
| `ACCESS_FINE_LOCATION` | Required for BT/Wi-Fi scanning on API 23+ |
| `READ_EXTERNAL_STORAGE` | Read offline map tiles |
| `WRITE_EXTERNAL_STORAGE` | Write encrypted handshake logs |
| `FOREGROUND_SERVICE` | Keep broadcast service alive |
| `WAKE_LOCK` | Prevent CPU sleep during broadcasts |

---

## Routing Algorithm

```
Input: list[MeshNode]
        ├─ node_id, battery_level, is_active
        ├─ device_type, has_weather_hq_signal
        └─ lat, lon

Step 1 — Filter:  battery > 15%  AND  is_active == True
Step 2 — Score:   score = 0.35 × (bat/100) + 0.50 × hq_flag + 0.15 × device_tier
Step 3 — Sort:    descending by score  (Weather-HQ nodes always rise to top)
Step 4 — Path:    greedy nearest-neighbour from highest-scored source node

Output: RoutingResult
         ├─ stable_nodes   (filtered + scored)
         ├─ optimal_path   (ordered node_id chain)
         ├─ hq_anchor      (highest-priority HQ node_id)
         └─ path_quality   (mean path score 0.0–1.0)
```

---

## Encryption Scheme

Handshake logs use a lightweight two-layer scheme:

1. **XOR stream cipher** with a repeating 24-byte key (`MeshNetAI-OfflineKey-2025`)
2. **Base64 encoding** for ASCII-safe JSON storage

> **Production upgrade path**: replace the static key with a PBKDF2-derived key
> from a user passphrase or hardware-bound device identifier.

---

## Disaster Scenarios

| Scenario | Max Hops | Battery Warn | Priority Nodes |
|---|---|---|---|
| Flood | 8 | 30% | gateway, relay |
| Earthquake | 10 | 25% | gateway, relay, smartphone |
| War Zone | 5 | 40% | gateway only |

---

## Running Tests

```bash
cd meshnet_ai/
pip install pytest
pytest tests/ -v
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     MeshNetApp (main.py)                 │
│  ┌───────────────────────┐  ┌────────────────────────┐  │
│  │   HardwareManager     │  │   MeshNetRootWidget     │  │
│  │   (hardware.py)       │  │   (ui.py)               │  │
│  │  ┌──────────────────┐ │  │  ┌─────────┬──────────┐ │  │
│  │  │ BT Adapter (JNI) │ │  │  │LeftPanel│RightPanel│ │  │
│  │  │ WiFi Mgr   (JNI) │ │  │  │  Peers  │  MapView │ │  │
│  │  └──────────────────┘ │  │  │  HopLog │  +Layers │ │  │
│  └───────────────────────┘  │  │  SOS Btn│          │ │  │
│                             │  └─────────┴──────────┘ │  │
│  ┌───────────────────────┐  │       │           │      │  │
│  │   RoutingEngine       │◄─┤       │           │      │  │
│  │   (routing.py)        │  │  ┌────▼────┐ ┌───▼───┐  │  │
│  └───────────────────────┘  │  │Broadcast│ │MapMgr │  │  │
│  ┌───────────────────────┐  │  │Engine   │ │Offline│  │  │
│  │   BroadcastEngine     │◄─┘  │(msg.py) │ │Tiles  │  │  │
│  │   HandshakeLogger     │     └─────────┘ └───────┘  │  │
│  │   (messaging.py)      │                             │  │
│  └───────────────────────┘                             │  │
└─────────────────────────────────────────────────────────┘
```
