"""
MeshNet AI — Layer 2 / Layer 3 Bridge: Python FastAPI Server
backend/api_server.py

Exposes the IBM Bob AI routing engine and mesh simulation over HTTP
so the Node.js Express backend (Layer 3) can proxy routing queries
without spawning a subprocess.

Endpoints
---------
GET  /health
    Liveness probe — returns JSON {status, nodeCount, uptime}.

POST /api/route
    Body: { source, target, scenario }
    Returns a RouteResult JSON object (see route_engine.RouteResult).

GET  /api/simulation/topology?scenario=earthquake
    Returns the current weighted graph as {nodes, edges} so the
    frontend can overlay routing weights on the map canvas.

POST /api/simulation/seed
    Seeds the backend Express API with a randomly generated mesh
    topology for offline development/testing.

Usage
-----
    # Install deps first:
    #   pip install -r requirements.txt
    #
    uvicorn api_server:app --reload --port 5050

    # Or with explicit host binding:
    uvicorn api_server:app --host 0.0.0.0 --port 5050
"""

from __future__ import annotations

import logging
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import MeshConfig
from graph_builder import MeshGraphBuilder
from route_engine import RouteEngine, RouteQuery
from routing_engine import RoutingEngine
from signal_monitor import BurstDispatcher, FlickerEvent, SignalMonitor
from simulation import (
    MeshNode,
    MeshNetworkAnalyser,
    build_offline_mesh,
    load_from_db,
)

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("meshnet.api")


# ─── App lifecycle ────────────────────────────────────────────────────────────

_start_time = time.time()
_cfg = MeshConfig.from_env()
_engine = RouteEngine(
    api_base=_cfg.backend_api_url,
    cfg=_cfg,
    cache_ttl_s=float(os.getenv("GRAPH_CACHE_TTL_S", 5.0)),
)

# ── Signal flicker monitor (shared instance) ──────────────────────────────────
_signal_monitor   = SignalMonitor()
_burst_dispatcher = BurstDispatcher(
    monitor=_signal_monitor,
    api_base=_cfg.backend_api_url,
    cfg=_cfg,
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    log.info("MeshNet AI Python router starting up — %s", _cfg.summary())
    yield
    log.info("MeshNet AI Python router shutting down")


app = FastAPI(
    title="MeshNet AI — Routing & Simulation Engine",
    description=(
        "Layer 2 (Simulation) + Layer 3 (IBM Bob AI Routing) Python service. "
        "Receives topology from the Node.js backend (Layer 4) and returns "
        "optimal mesh routes using NetworkX / AODV-Dijkstra."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / Response Models ────────────────────────────────────────────────

class RouteRequest(BaseModel):
    source:   str = Field(..., description="Source node ID")
    target:   str = Field(..., description="Target node ID")
    scenario: str = Field("earthquake", description="flood | war_zone | earthquake")
    max_hops: Optional[int] = Field(None, description="Override global MAX_HOPS")


class SimSeedRequest(BaseModel):
    node_count: int = Field(10, ge=2, le=200, description="Number of nodes to generate")
    scenario:   str = Field("earthquake", description="Disaster scenario")


class OfflineMeshRequest(BaseModel):
    max_range_meters: float = Field(100.0, ge=10.0, le=500.0,
                                    description="BLE/Wi-Fi max communication radius in metres")
    db_path: Optional[str] = Field(None, description="Override SQLite DB path (default: meshnet.db)")


class SignalReportRequest(BaseModel):
    node_id:    str   = Field(...,           description="Device node ID")
    node_label: str   = Field("",            description="Human-readable label")
    signal:     int   = Field(..., ge=0, le=100, description="RSSI-normalised signal 0–100")
    prev_signal: Optional[int] = Field(None, description="Previous reading (omit to use stored state)")
    scenario:   str   = Field("earthquake",  description="flood | war_zone | earthquake")


class AIRouteRequest(BaseModel):
    source_node_id: int = Field(..., description="Source citizen node ID (1–99)")
    message:        str = Field("", description="Plaintext SOS payload to encrypt and route")
    max_range_meters: float = Field(100.0, ge=10.0, le=500.0,
                                    description="BLE/Wi-Fi max communication radius in metres")
    rescue_node_id: Optional[int] = Field(None, description="Override rescue target (default: 100)")


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Liveness probe — used by the Node.js backend healthcheck."""
    builder = MeshGraphBuilder(api_base=_cfg.backend_api_url, cfg=_cfg)
    G = builder.build()
    return {
        "status":    "ok",
        "nodeCount": G.number_of_nodes(),
        "edgeCount": G.number_of_edges(),
        "uptime":    round(time.time() - _start_time, 1),
    }


@app.post("/api/route")
def compute_route(body: RouteRequest):
    """
    IBM Bob AI Core Routing Logic entry point.

    Accepts a source→target routing query with a disaster scenario
    and returns the optimal path computed by the RouteEngine.
    """
    if body.scenario not in ("flood", "war_zone", "earthquake"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid scenario '{body.scenario}'. Use: flood, war_zone, earthquake",
        )

    q = RouteQuery(
        source=body.source,
        target=body.target,
        scenario=body.scenario,
        max_hops=body.max_hops,
    )
    result = _engine.query(q)

    if not result.found:
        # Return 200 with found=false rather than a 4xx so callers can
        # distinguish "no path" from an API error
        return result.to_dict()

    return result.to_dict()


@app.get("/api/simulation/topology")
def simulation_topology(scenario: str = "earthquake"):
    """
    Return the live weighted topology graph as JSON for the frontend map.

    Nodes include battery, signal, role, and lat/lng.
    Edges include weight, protocol, and quality.
    """
    if scenario not in ("flood", "war_zone", "earthquake"):
        raise HTTPException(status_code=422, detail="Invalid scenario")

    builder = MeshGraphBuilder(
        api_base=_cfg.backend_api_url,
        scenario=scenario,
        cfg=_cfg,
    )
    G = builder.build()

    nodes = [
        {"id": nid, **attrs}
        for nid, attrs in G.nodes(data=True)
    ]
    edges = [
        {
            "source":   u,
            "target":   v,
            "weight":   round(data["weight"], 4),
            "protocol": data.get("protocol", "wifi"),
            "quality":  data.get("quality", 80),
        }
        for u, v, data in G.edges(data=True)
    ]

    return {
        "scenario":   scenario,
        "nodes":      nodes,
        "edges":      edges,
        "nodeCount":  len(nodes),
        "edgeCount":  len(edges),
        "generatedAt": time.time(),
    }


# ─── POST /api/simulation/offline-mesh ───────────────────────────────────────

@app.post("/api/simulation/offline-mesh")
def offline_mesh(body: OfflineMeshRequest):
    """
    Build the offline device-chain mesh from the 100-row mesh_nodes table.

    Uses simulation.py:
      1. Loads all citizen nodes from SQLite (mesh_nodes table).
      2. Force-enables BLE on every node (disaster broadcast trigger).
      3. Computes Euclidean distances between all node pairs.
      4. Creates peer-to-peer bridge edges for nodes within max_range_meters.

    Returns the graph as JSON plus diagnostic analytics.
    """
    nodes: list[MeshNode] = load_from_db(body.db_path)
    G = build_offline_mesh(nodes, max_range_meters=body.max_range_meters)
    ana = MeshNetworkAnalyser(G)

    graph_nodes = [
        {
            "id":             nid,
            "citizen_name":   attrs.get("citizen_name"),
            "lat":            attrs.get("lat"),
            "lng":            attrs.get("lng"),
            "battery":        attrs.get("battery"),
            "bluetooth":      attrs.get("bluetooth"),
            "is_rescue_team": attrs.get("is_rescue_team"),
            "signal":         attrs.get("signal"),
            "role":           attrs.get("role"),
            "degree":         G.degree(nid),
        }
        for nid, attrs in G.nodes(data=True)
    ]

    graph_edges = [
        {
            "node_a":     u,
            "node_b":     v,
            "distance_m": round(d.get("distance", d.get("weight", 0)), 2),
            "protocol":   d.get("protocol", "unknown"),
        }
        for u, v, d in G.edges(data=True)
    ]

    return {
        "nodeCount":          ana.node_count(),
        "edgeCount":          ana.edge_count(),
        "bleActiveCount":     ana.ble_active_count(),
        "density":            round(ana.density(), 6),
        "connectedIslands":   ana.connected_components(),
        "largestIslandSize":  ana.largest_component_size(),
        "isolatedNodes":      ana.isolated_nodes(),
        "rescuePortalId":     ana.rescue_node_id(),
        "maxRangeMeters":     body.max_range_meters,
        "nodes":              graph_nodes,
        "edges":              graph_edges,
    }


# ─── GET /api/simulation/rescue-path/{source_id} ─────────────────────────────

@app.get("/api/simulation/rescue-path/{source_id}")
def rescue_path(source_id: int, max_range_meters: float = 100.0):
    """
    Compute the shortest path from citizen node {source_id} to the
    rescue camp portal (Node #100) through the offline mesh.

    Returns path[], total_distance_m, hops, and found flag.
    """
    nodes = load_from_db()
    G     = build_offline_mesh(nodes, max_range_meters=max_range_meters)
    ana   = MeshNetworkAnalyser(G)
    return ana.rescue_path(source_id)


@app.post("/api/simulation/ai-route")
def ai_route(body: AIRouteRequest):
    """
    Battery-prioritised Dijkstra path-finding with AES-256-GCM hop encryption.

    Loads the offline mesh, runs the RoutingEngine to find the optimal
    path from *source_node_id* to the rescue camp (Node #100), and
    returns the path together with an encrypted HopPacket per relay node.

    The ``session_key`` in the response must be shared securely (out-of-band)
    with the rescue base camp to decrypt the final payload.
    """
    nodes = load_from_db()
    graph = build_offline_mesh(nodes, max_range_meters=body.max_range_meters)

    engine = RoutingEngine(graph, rescue_node_id=body.rescue_node_id or 100)
    result = engine.calculate_ai_routing_path(
        source_node_id=body.source_node_id,
        message=body.message,
    )

    if result["status"] == "Failed":
        raise HTTPException(status_code=404, detail=result["message"])

    return {
        "status":       result["status"],
        "pathTaken":    result["path_taken"],
        "totalHops":    result["total_hops"],
        "totalWeight":  result["total_weight"],
        "encryptedHops": [
            {
                "hopIndex":        hop.hop_index,
                "nodeId":          hop.node_id,
                "payloadBytes":    len(hop.encrypted_payload),
                "encryptedPayload": hop.encrypted_payload.hex(),
            }
            for hop in result["encrypted_hops"]
        ],
        # session_key is intentionally omitted from the API response —
        # share it with the rescue base camp through a secure channel.
    }


@app.post("/api/simulation/seed")
def simulation_seed(body: SimSeedRequest):
    """
    Generate a synthetic mesh topology and POST it to the Express backend.

    Useful for local development when no real devices are available.
    Creates nodes with random coordinates near Manila (14.5995°N, 120.9842°E)
    and connects them based on the scenario's communication range.
    """
    max_range = _cfg.range_for_scenario(body.scenario)
    api_base  = _cfg.backend_api_url
    registered: list[str] = []

    import math

    def _lat_lng_offset(metres: float) -> tuple[float, float]:
        """Convert metres to approximate degree offsets near the equator."""
        deg_per_m = 1 / 111_320
        return metres * deg_per_m, metres * deg_per_m

    base_lat = 14.5995
    base_lng = 120.9842
    spread   = max_range / 111_320  # metres → degrees

    node_ids: list[str] = []
    for i in range(body.node_count):
        nid   = f"sim-node-{i:03d}"
        label = f"SIM·{i:03d}"
        lat   = base_lat + random.uniform(-spread * 3, spread * 3)
        lng   = base_lng + random.uniform(-spread * 3, spread * 3)

        payload = {
            "id":                nid,
            "label":             label,
            "name":              f"Simulated Device {i}",
            "device":            random.choice(["smartphone", "laptop"]),
            "role":              "relay" if i % 4 == 0 else "peer",
            "signal":            random.randint(40, 100),
            "batteryPercentage": random.randint(15, 100),
            "bluetoothStatus":   random.random() > 0.3,
            "lat":               round(lat, 6),
            "lng":               round(lng, 6),
        }

        try:
            r = requests.post(
                f"{api_base}/api/mesh/register",
                json=payload,
                timeout=_cfg.http_timeout,
            )
            if r.status_code == 201:
                registered.append(nid)
                node_ids.append(nid)
        except requests.RequestException as exc:
            log.warning("Failed to register %s: %s", nid, exc)

    # Register edges between nodes within range
    edges_registered = 0
    for i, a in enumerate(node_ids):
        for b in node_ids[i + 1:]:
            try:
                r = requests.post(
                    f"{api_base}/api/mesh/edges",
                    json={
                        "a":        a,
                        "b":        b,
                        "protocol": random.choice(["wifi", "bluetooth"]),
                        "quality":  random.randint(40, 100),
                    },
                    timeout=_cfg.http_timeout,
                )
                if r.status_code == 201:
                    edges_registered += 1
            except requests.RequestException:
                pass

    return {
        "seeded":          len(registered),
        "edgesRegistered": edges_registered,
        "scenario":        body.scenario,
        "nodeCount":       body.node_count,
    }


# ─── POST /api/signal/report ─────────────────────────────────────────────────

@app.post("/api/signal/report")
def signal_report(body: SignalReportRequest):
    """
    Ingest one signal sample from a mesh node.

    If the signal just transitioned from ≤ DEAD_THRESHOLD to > LIVE_THRESHOLD,
    the High-Priority Data Burst fires immediately:
      - A FlickerEvent is returned in the response.
      - All buffered log chunks for the node are flushed via BurstDispatcher.
      - The Express backend's /api/signal/report is notified, which fans out
        to the SSE stream so the rescue dashboard shows an alert pop-up.

    Parameters (JSON body)
    ----------------------
    node_id     : str   — device ID
    node_label  : str   — human-readable label (optional)
    signal      : int   — current RSSI-normalised signal 0–100
    prev_signal : int   — override stored previous reading (optional)
    scenario    : str   — flood | war_zone | earthquake

    Returns
    -------
    { flicker: false } when no transition is detected.
    { flicker: true, event: FlickerEvent.to_dict() } when a burst fires.
    """
    label = body.node_label or body.node_id

    evt: FlickerEvent | None = _signal_monitor.ingest_sample(
        node_id=body.node_id,
        node_label=label,
        signal=body.signal,
        scenario=body.scenario,
        prev_signal=body.prev_signal,
    )

    if evt is None:
        return {"flicker": False, "nodeId": body.node_id, "signal": body.signal}

    return {"flicker": True, "event": evt.to_dict()}
