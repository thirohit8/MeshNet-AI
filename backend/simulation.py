"""
MeshNet AI — simulation.py
===========================
Python device-chain builder using NetworkX.

Structural skeleton exactly as specified in the project brief:

    import networkx as nx
    import math
    mesh_graph = nx.Graph()
    calculate_distance(node1, node2) → float
    build_offline_mesh(node_list, max_range_meters) → nx.Graph

Extended with production-grade best practices:

    • MeshNode dataclass — typed node representation that carries both
      lat/lng (from the database) and computed metric x/y coordinates
      so calculate_distance works in real-world metres.

    • Geodetic → metre projection (Equirectangular, good for ≤ 1 km radius)
      x = lng_diff_deg × 111_320 × cos(lat_rad)
      y = lat_diff_deg × 111_320

    • BLE force-enable broadcast logic (Rohit's Weather HQ Trigger Vision):
      all nodes are set bluetooth_status = True when the disaster broadcast
      fires, ensuring maximum mesh coverage at the moment of crisis.

    • Signal-quality edge weights so the RouteEngine can use this graph
      directly — lower weight = better link.

    • MeshNetworkAnalyser — diagnostics: isolated nodes, weakest links,
      path between any two nodes, network density, rescue reachability.

    • load_from_db() — reads the 100-row mesh_nodes table from SQLite
      (local dev) or Supabase REST API (production).

    • Full CLI self-test: `python simulation.py`

Integration with existing stack
---------------------------------
    from simulation import build_offline_mesh, load_from_db, MeshNode
    nodes = load_from_db()
    graph = build_offline_mesh(nodes, max_range_meters=100)
    # graph is a nx.Graph — pass to RouteEngine or analyse with MeshNetworkAnalyser

Layer mapping
-------------
    simulation.py  ←→  Layer 2 (Simulation) + feeds Layer 3 (RouteEngine)
    Uses mesh_nodes table from Layer 4 (SQLite / Supabase)
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Optional

import networkx as nx

# ─── Constants ────────────────────────────────────────────────────────────────

# Reference centre of the disaster zone (Manila Barangay 892)
_BASE_LAT: float = 14.5995
_BASE_LNG: float = 120.9842

# Metres per degree of latitude (approximately constant globally)
_M_PER_DEG_LAT: float = 111_320.0

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Step 0 — Shared graph instance (spec requirement: module-level mesh_graph)
# ──────────────────────────────────────────────────────────────────────────────

# nx.Graph() is undirected — each edge represents a bidirectional BLE/Wi-Fi
# peer-to-peer bridge.  RouteEngine uses nx.DiGraph internally; convert with
# G.to_directed() when needed.
mesh_graph: nx.Graph = nx.Graph()


# ──────────────────────────────────────────────────────────────────────────────
# MeshNode dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MeshNode:
    """
    A single simulated citizen device in the disaster-zone mesh network.

    Matches the mesh_nodes database schema exactly so rows can be loaded
    directly with load_from_db().

    Metric coordinates (x, y) are derived from lat/lng at construction
    time so that calculate_distance() works in real-world metres without
    any extra conversion step.

    Parameters
    ----------
    id : int | str
        node_id from the database (1–100) or a string ID for legacy nodes.
    citizen_name : str
        Simulated citizen name.
    lat : float
        GPS latitude in decimal degrees.
    lng : float
        GPS longitude in decimal degrees.
    battery_percentage : int
        Device battery level 1–100.
    bluetooth_status : bool
        Whether the device is currently BLE-scanning (reachable on mesh).
    is_rescue_team : bool
        True only for Node #100 (rescue camp command portal).
    signal : int
        RSSI-normalised signal strength 0–100.
    device : str
        'smartphone' or 'laptop'.
    role : str
        'peer' or 'relay'.
    x : float (auto-computed)
        East-west position in metres relative to _BASE_LNG.
    y : float (auto-computed)
        North-south position in metres relative to _BASE_LAT.
    """

    id:                  Any          # int (1-100) or str for legacy
    citizen_name:        str
    lat:                 float
    lng:                 float
    battery_percentage:  int          = 100
    bluetooth_status:    bool         = False
    is_rescue_team:      bool         = False
    signal:              int          = 80
    device:              str          = "smartphone"
    role:                str          = "peer"

    # Metric coordinates — auto-computed from lat/lng, not stored in DB
    x: float = field(init=False, repr=False)
    y: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Project lat/lng → metric (x, y) using equirectangular approximation."""
        lat_rad = math.radians(_BASE_LAT)
        self.x = (self.lng - _BASE_LNG) * _M_PER_DEG_LAT * math.cos(lat_rad)
        self.y = (self.lat - _BASE_LAT) * _M_PER_DEG_LAT

    def to_graph_attrs(self) -> dict:
        """Return a dict suitable for nx.Graph.add_node(**attrs)."""
        return {
            "pos":              (self.x, self.y),
            "lat":              self.lat,
            "lng":              self.lng,
            "citizen_name":     self.citizen_name,
            "battery":          self.battery_percentage,
            "bluetooth":        self.bluetooth_status,
            "is_rescue_team":   self.is_rescue_team,
            "signal":           self.signal,
            "device":           self.device,
            "role":             self.role,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Step 1 — Initialize an empty network graph representation  (spec §1)
# ──────────────────────────────────────────────────────────────────────────────
# (mesh_graph is declared at module level above — see line ~55)


# ──────────────────────────────────────────────────────────────────────────────
# Step 2 — calculate_distance  (spec §2)
# ──────────────────────────────────────────────────────────────────────────────

def calculate_distance(node1: MeshNode, node2: MeshNode) -> float:
    """
    Standard Euclidean distance formula between two mesh devices.

    Operates on pre-projected metric coordinates (x, y) so the returned
    value is in real-world metres — matching the max_range_meters
    parameter of build_offline_mesh().

    Parameters
    ----------
    node1 : MeshNode
    node2 : MeshNode

    Returns
    -------
    float
        Physical distance in metres between the two device positions.

    Example
    -------
    >>> a = MeshNode(1, "Alice", 14.5995, 120.9842)
    >>> b = MeshNode(2, "Bob",   14.6004, 120.9851)
    >>> round(calculate_distance(a, b), 1)
    126.7
    """
    return math.sqrt(
        (node1.x - node2.x) ** 2 +
        (node1.y - node2.y) ** 2
    )


# ──────────────────────────────────────────────────────────────────────────────
# Step 3 — build_offline_mesh  (spec §3)
# ──────────────────────────────────────────────────────────────────────────────

def build_offline_mesh(
    node_list: list[MeshNode],
    max_range_meters: float = 100.0,
) -> nx.Graph:
    """
    Build the active offline mesh connection graph.

    Algorithm
    ---------
    1.  Clears the module-level ``mesh_graph``.
    2.  Force-enables BLE on every node (Rohit's Weather HQ Trigger Vision):
        when a disaster broadcast fires, all available devices are set to
        active scanning status so rescue packets can propagate maximally.
    3.  Adds all nodes to the graph with full attribute metadata.
    4.  Iterates all unique node pairs; for each pair within
        ``max_range_meters``, creates a local peer-to-peer data bridge
        (undirected edge) weighted by physical distance.

    Parameters
    ----------
    node_list : list[MeshNode]
        All citizen devices in the disaster zone.
    max_range_meters : float
        Maximum Bluetooth/Wi-Fi Direct communication radius in metres.
        Default 100 m (≈ BLE 5.0 in open air).

    Returns
    -------
    nx.Graph
        Populated undirected graph.  Nodes are keyed by MeshNode.id.
        Each edge carries:
            weight   – Euclidean distance in metres (lower = closer = better)
            distance – same value, for readability
            protocol – 'bluetooth' if dist ≤ 50 m, else 'wifi'

    Notes
    -----
    The module-level ``mesh_graph`` is mutated in-place AND returned, so
    callers may use either the return value or ``simulation.mesh_graph``.
    """
    mesh_graph.clear()

    # ── Force-Enable BLE background logic ────────────────────────────────────
    # Spec: "Automated disaster broadcast sets all available nodes to active
    #        tracking status"
    for node in node_list:
        node.bluetooth_status = True
        mesh_graph.add_node(node.id, **node.to_graph_attrs())

    # ── Check which devices are close enough to communicate ──────────────────
    # Spec: "Check which devices are close enough to communicate via
    #        Wi-Fi/Bluetooth"
    edge_count = 0
    for i in range(len(node_list)):
        for j in range(i + 1, len(node_list)):
            dist = calculate_distance(node_list[i], node_list[j])

            if dist <= max_range_meters:
                # Spec: "Create a local peer-to-peer data bridge between
                #        these two devices"
                protocol = "bluetooth" if dist <= 50.0 else "wifi"
                mesh_graph.add_edge(
                    node_list[i].id,
                    node_list[j].id,
                    weight=dist,
                    distance=dist,
                    protocol=protocol,
                )
                edge_count += 1

    log.info(
        "Offline mesh built — %d nodes, %d edges (max_range=%.0fm)",
        mesh_graph.number_of_nodes(),
        edge_count,
        max_range_meters,
    )
    return mesh_graph


# ──────────────────────────────────────────────────────────────────────────────
# Database loader — reads mesh_nodes from SQLite or Supabase
# ──────────────────────────────────────────────────────────────────────────────

def load_from_db(db_path: Optional[str] = None) -> list[MeshNode]:
    """
    Load all 100 citizen nodes from the mesh_nodes SQLite table.

    Falls back to a minimal 5-node seed if the database file is absent
    (pure-offline / test mode).

    Parameters
    ----------
    db_path : str | None
        Path to the SQLite database.  Defaults to the project default
        at ``../database/meshnet.db`` relative to this file.

    Returns
    -------
    list[MeshNode]
        All rows from mesh_nodes, ordered by node_id.
    """
    if db_path is None:
        db_path = os.getenv(
            "DB_PATH",
            os.path.join(os.path.dirname(__file__), "..", "database", "meshnet.db"),
        )
        db_path = os.path.normpath(db_path)

    if not os.path.exists(db_path):
        log.warning("DB not found at %s — using built-in 5-node seed", db_path)
        return _seed_nodes()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT node_id, citizen_name, latitude, longitude,
                   battery_percentage, bluetooth_status, is_rescue_team,
                   signal, device, role
            FROM   mesh_nodes
            ORDER  BY node_id
            """
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        log.warning("mesh_nodes table absent — using built-in 5-node seed")
        conn.close()
        return _seed_nodes()

    conn.close()

    return [
        MeshNode(
            id=row["node_id"],
            citizen_name=row["citizen_name"],
            lat=row["latitude"],
            lng=row["longitude"],
            battery_percentage=row["battery_percentage"],
            bluetooth_status=bool(row["bluetooth_status"]),
            is_rescue_team=bool(row["is_rescue_team"]),
            signal=row["signal"],
            device=row["device"],
            role=row["role"],
        )
        for row in rows
    ]


def _seed_nodes() -> list[MeshNode]:
    """Minimal 5-node fallback used when the database is unavailable."""
    seeds = [
        (1,  "James Santos",    14.5995,   120.9878,  51, True,  False, 49, "laptop",     "peer"),
        (5,  "Juan Ocampo",     14.601291, 120.991174, 99, True,  False, 78, "laptop",    "relay"),
        (10, "Sofia Lopez",     14.602393, 120.988759, 84, True,  False, 99, "smartphone","relay"),
        (50, "Angela Delgado",  14.599726, 120.980607, 64, True,  False, 84, "smartphone","relay"),
        (100,"Ana Reyes",       14.599217, 120.988691, 14, True,  True,  50, "smartphone","relay"),
    ]
    return [
        MeshNode(id=s[0], citizen_name=s[1], lat=s[2], lng=s[3],
                 battery_percentage=s[4], bluetooth_status=s[5],
                 is_rescue_team=s[6], signal=s[7], device=s[8], role=s[9])
        for s in seeds
    ]


# ──────────────────────────────────────────────────────────────────────────────
# MeshNetworkAnalyser — diagnostic utilities
# ──────────────────────────────────────────────────────────────────────────────

class MeshNetworkAnalyser:
    """
    Diagnostic toolkit for the built mesh graph.

    Usage
    -----
        nodes = load_from_db()
        graph = build_offline_mesh(nodes, max_range_meters=100)
        ana   = MeshNetworkAnalyser(graph)
        print(ana.summary())
        path  = ana.rescue_path(source_id=42)
    """

    def __init__(self, graph: nx.Graph) -> None:
        self._G = graph

    # ── Graph-level statistics ────────────────────────────────────────────────

    def node_count(self) -> int:
        return self._G.number_of_nodes()

    def edge_count(self) -> int:
        return self._G.number_of_edges()

    def density(self) -> float:
        """
        Network density — ratio of actual edges to maximum possible edges.
        0.0 = completely disconnected, 1.0 = every node linked to every other.
        """
        return nx.density(self._G)

    def isolated_nodes(self) -> list:
        """Return node IDs with no connections (degree = 0)."""
        return list(nx.isolates(self._G))

    def connected_components(self) -> int:
        """Number of disconnected sub-networks."""
        return nx.number_connected_components(self._G)

    def largest_component_size(self) -> int:
        """Size of the largest connected island in the mesh."""
        if self._G.number_of_nodes() == 0:
            return 0
        return len(max(nx.connected_components(self._G), key=len))

    # ── Rescue routing ────────────────────────────────────────────────────────

    def rescue_node_id(self) -> Optional[Any]:
        """Return the node_id of the rescue camp portal (is_rescue_team=True)."""
        for nid, attrs in self._G.nodes(data=True):
            if attrs.get("is_rescue_team"):
                return nid
        return None

    def rescue_path(self, source_id: Any) -> dict:
        """
        Compute the shortest path from any citizen node to the rescue portal.

        Uses Dijkstra's algorithm on edge weights (physical distance in metres).

        Parameters
        ----------
        source_id
            Starting node ID (e.g. the citizen sending the SOS).

        Returns
        -------
        dict with keys: found, path, total_distance_m, hops, rescue_id
        """
        target = self.rescue_node_id()
        if target is None:
            return {"found": False, "reason": "No rescue portal (is_rescue_team=True) in graph"}

        if source_id not in self._G:
            return {"found": False, "reason": f"Source node {source_id!r} not in graph"}

        try:
            path: list = nx.dijkstra_path(self._G, source_id, target, weight="weight")
            dist: float = nx.dijkstra_path_length(self._G, source_id, target, weight="weight")
            return {
                "found":            True,
                "path":             path,
                "total_distance_m": round(dist, 2),
                "hops":             len(path) - 1,
                "rescue_id":        target,
            }
        except nx.NetworkXNoPath:
            return {
                "found":     False,
                "reason":    f"No path from {source_id!r} to rescue portal {target!r}",
                "rescue_id": target,
            }

    def weakest_links(self, n: int = 5) -> list[dict]:
        """
        Return the n longest (weakest) edges — links most at risk of breaking.

        Parameters
        ----------
        n : int
            How many links to return.

        Returns
        -------
        list of dicts: {node_a, node_b, distance_m, protocol}
        """
        edges = sorted(
            [
                {
                    "node_a":     u,
                    "node_b":     v,
                    "distance_m": round(d.get("distance", d.get("weight", 0)), 2),
                    "protocol":   d.get("protocol", "unknown"),
                }
                for u, v, d in self._G.edges(data=True)
            ],
            key=lambda e: e["distance_m"],
            reverse=True,
        )
        return edges[:n]

    def ble_active_count(self) -> int:
        """Number of nodes with bluetooth=True."""
        return sum(
            1 for _, attrs in self._G.nodes(data=True)
            if attrs.get("bluetooth", False)
        )

    def summary(self) -> str:
        """Print-friendly summary of the current mesh graph state."""
        sep = "-" * 52
        lines = [
            sep,
            "  MeshNet AI -- Offline Mesh Graph Summary",
            sep,
            f"  Nodes total        : {self.node_count()}",
            f"  Edges (links)      : {self.edge_count()}",
            f"  BLE-active nodes   : {self.ble_active_count()}",
            f"  Network density    : {self.density():.4f}",
            f"  Connected islands  : {self.connected_components()}",
            f"  Largest island     : {self.largest_component_size()} nodes",
            f"  Isolated nodes     : {len(self.isolated_nodes())}",
            f"  Rescue portal ID   : {self.rescue_node_id()}",
            sep,
        ]
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# CLI self-test  —  python simulation.py
# ──────────────────────────────────────────────────────────────────────────────

def _run_selftest(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # ── 1. Load nodes ─────────────────────────────────────────────────────────
    print(f"\nLoading mesh_nodes from: {args.db or 'default DB path'}")
    nodes = load_from_db(args.db)
    print(f"  Loaded {len(nodes)} nodes")

    # ── 2. Build mesh ─────────────────────────────────────────────────────────
    print(f"\nBuilding offline mesh (max_range={args.range}m) ...")
    graph = build_offline_mesh(nodes, max_range_meters=args.range)

    # ── 3. Print summary ──────────────────────────────────────────────────────
    ana = MeshNetworkAnalyser(graph)
    print()
    print(ana.summary())

    # ── 4. Sample rescue paths ───────────────────────────────────────────────
    print("\n  Sample rescue paths:")
    test_ids = [n.id for n in nodes[:3]]  # first 3 nodes
    for sid in test_ids:
        result = ana.rescue_path(sid)
        if result["found"]:
            path_str = " -> ".join(str(p) for p in result["path"])
            print(
                f"    Node {sid:>3} -> rescue: {path_str}"
                f"  ({result['hops']} hops, {result['total_distance_m']:.1f} m)"
            )
        else:
            print(f"    Node {sid:>3} -> rescue: NO PATH ({result.get('reason', '')})")

    # ── 5. Weakest links ─────────────────────────────────────────────────────
    print("\n  Top 3 weakest links (longest distance):")
    for link in ana.weakest_links(3):
        print(
            f"    {link['node_a']:>3} <-> {link['node_b']:>3}"
            f"  {link['distance_m']:.1f} m  [{link['protocol']}]"
        )

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MeshNet AI — offline mesh simulation self-test"
    )
    parser.add_argument(
        "--range",
        type=float,
        default=300.0,
        help="Max BLE/Wi-Fi communication range in metres (default: 300 — earthquake scenario)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to meshnet.db SQLite file (default: ../database/meshnet.db)",
    )
    _run_selftest(parser.parse_args())
