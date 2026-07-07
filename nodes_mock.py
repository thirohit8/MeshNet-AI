"""
MeshNet-AI — nodes_mock.py
==========================
Mock network topology for algorithm testing, unit tests, and offline demos.

This module provides two views of the same topology:
  • ``MOCK_TOPOLOGY``    — list of fully-typed ``routing.MeshNode`` objects,
                          the canonical form consumed by the production engine.
  • ``simulated_network`` — legacy dict-based list kept for backward
                            compatibility with core_router.py / dashboard_offline.py.

Topology summary (12 nodes across a hypothetical disaster zone near Los Angeles)
---------------------------------------------------------------------------------
Node  | Device     | Battery | Active | HQ Signal | Fate
------+------------+---------+--------+-----------+---------------------------
A1    | gateway    |  87 %   |  Yes   | YES        | Stable — HQ anchor
B2    | relay      |  62 %   |  Yes   | No         | Stable
C3    | smartphone |  11 %   |  Yes   | No         | FILTERED (battery ≤ 15 %)
D4    | smartphone |  76 %   |  Yes   | YES        | Stable — HQ carrier
E5    | tablet     |  45 %   |  No    | No         | FILTERED (inactive)
F6    | gateway    |  93 %   |  Yes   | No         | Stable — highest raw battery
G7    | iot        |  33 %   |  Yes   | No         | Stable (low-tier)
H8    | smartphone |   8 %   |  Yes   | No         | FILTERED (battery ≤ 15 %)
I9    | relay      |  55 %   |  Yes   | No         | Stable
J10   | tablet     |  70 %   |  Yes   | No         | Stable
K11   | iot        |  19 %   |  Yes   | No         | Stable (marginal)
L12   | smartphone |  82 %   |  Yes   | No         | Stable
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Import the canonical MeshNode dataclass from routing.py.
# A local import guard prevents circular issues during early bootstrap.
from routing import MeshNode

# ── Canonical MeshNode topology ───────────────────────────────────────────────

MOCK_TOPOLOGY: list[MeshNode] = [
    MeshNode("NODE-A1",  battery_level=87.0, is_active=True,
             device_type="gateway",    has_weather_hq_signal=True,
             lat=34.0522, lon=-118.2437),

    MeshNode("NODE-B2",  battery_level=62.0, is_active=True,
             device_type="relay",      has_weather_hq_signal=False,
             lat=34.0600, lon=-118.2500),

    MeshNode("NODE-C3",  battery_level=11.0, is_active=True,   # ← FILTERED (batt ≤ 15 %)
             device_type="smartphone", has_weather_hq_signal=False,
             lat=34.0450, lon=-118.2300),

    MeshNode("NODE-D4",  battery_level=76.0, is_active=True,
             device_type="smartphone", has_weather_hq_signal=True,
             lat=34.0700, lon=-118.2600),

    MeshNode("NODE-E5",  battery_level=45.0, is_active=False,  # ← FILTERED (inactive)
             device_type="tablet",     has_weather_hq_signal=False,
             lat=34.0550, lon=-118.2350),

    MeshNode("NODE-F6",  battery_level=93.0, is_active=True,
             device_type="gateway",    has_weather_hq_signal=False,
             lat=34.0480, lon=-118.2550),

    MeshNode("NODE-G7",  battery_level=33.0, is_active=True,
             device_type="iot",        has_weather_hq_signal=False,
             lat=34.0620, lon=-118.2420),

    MeshNode("NODE-H8",  battery_level=8.0,  is_active=True,   # ← FILTERED (batt ≤ 15 %)
             device_type="smartphone", has_weather_hq_signal=False,
             lat=34.0510, lon=-118.2460),

    MeshNode("NODE-I9",  battery_level=55.0, is_active=True,
             device_type="relay",      has_weather_hq_signal=False,
             lat=34.0590, lon=-118.2480),

    MeshNode("NODE-J10", battery_level=70.0, is_active=True,
             device_type="tablet",     has_weather_hq_signal=False,
             lat=34.0530, lon=-118.2510),

    MeshNode("NODE-K11", battery_level=19.0, is_active=True,
             device_type="iot",        has_weather_hq_signal=False,
             lat=34.0640, lon=-118.2390),

    MeshNode("NODE-L12", battery_level=82.0, is_active=True,
             device_type="smartphone", has_weather_hq_signal=False,
             lat=34.0560, lon=-118.2530),
]

# ── Legacy dict-based topology (backward compat with core_router / dashboard) ─

simulated_network: list[dict] = [
    {
        "node_id"              : n.node_id,
        "device_type"          : n.device_type,
        "battery_level"        : int(n.battery_level),
        "is_active"            : n.is_active,
        "has_weather_hq_signal": n.has_weather_hq_signal,
        "lat"                  : n.lat,
        "lon"                  : n.lon,
    }
    for n in MOCK_TOPOLOGY
]


def get_active_nodes(network: list[dict]) -> list[dict]:
    """
    Filter a dict-based network topology to nodes that are:
      • is_active == True
      • battery_level > 15 %   (matches RoutingEngine.BATTERY_THRESHOLD)

    Parameters
    ----------
    network : list of node dicts (as in ``simulated_network``)

    Returns
    -------
    Filtered list of node dicts in original order.
    """
    return [
        node for node in network
        if node["is_active"] and node["battery_level"] > 15
    ]


def mock_topology() -> list[MeshNode]:
    """
    Return a fresh copy of the canonical 12-node mock topology.

    Routing scores are NOT pre-computed — the RoutingEngine sets them
    during ``compute()``.  This factory is the single source of truth
    for both the GUI and CLI tools.
    """
    # Return fresh MeshNode instances to avoid shared state between runs.
    return list(MOCK_TOPOLOGY)


# ── Module self-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    active = get_active_nodes(simulated_network)
    print(f"Total nodes in topology   : {len(simulated_network)}")
    print(f"Nodes passing stability   : {len(active)}")
    print()
    for n in active:
        hq = " ★ HQ" if n["has_weather_hq_signal"] else ""
        print(
            f"  {n['node_id']:<12}  {n['device_type']:<12} "
            f"  batt={n['battery_level']:3d}%{hq}"
        )
