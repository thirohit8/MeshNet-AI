"""
MeshNet AI — Layer 2: Simulation Graph Builder
backend/graph_builder.py

Builds a weighted, directed NetworkX graph from live node + edge data
fetched from the backend REST API (Layer 4 → Layer 2 data flow).

Each edge weight encodes signal quality, hop penalty, and battery state
so that the routing engine (Layer 3) can compute the optimal path.

Usage
-----
    from graph_builder import MeshGraphBuilder
    builder = MeshGraphBuilder(api_base="http://localhost:4000")
    G = builder.build()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
import requests

from config import MeshConfig

log = logging.getLogger(__name__)


# ─── Edge weight formula ──────────────────────────────────────────────────────

def _edge_weight(quality: int, battery: int, scenario: str, cfg: MeshConfig) -> float:
    """
    Compute a dimensionless routing weight for a mesh link.

    Lower weight  = preferred route.
    Higher weight = degraded / less preferred route.

    Formula
    -------
    base_cost = (100 - quality) / 10          # 0 (perfect) … 10 (no signal)
    battery_penalty = max(0, (20 - battery) / 10) if battery < 20 else 0
    scenario_multiplier: flood=1.4, war_zone=1.8, earthquake=1.0

    The scenario multiplier reflects that some environments have more
    interference / attenuation per hop.
    """
    base = (100 - max(0, min(quality, 100))) / 10.0

    # Battery penalty kicks in when a relay node is critically low
    bat_penalty = max(0.0, (cfg.default_battery_min - battery) / 10.0) if battery < cfg.default_battery_min else 0.0

    _multiplier = {
        "flood":      1.4,
        "war_zone":   1.8,
        "earthquake": 1.0,
    }.get(scenario, 1.0)

    return (base + bat_penalty) * _multiplier + 1.0  # minimum weight = 1


# ─── Graph builder ────────────────────────────────────────────────────────────

@dataclass
class MeshGraphBuilder:
    """
    Fetches mesh topology from the Node.js backend API and assembles a
    NetworkX DiGraph suitable for routing queries.

    Parameters
    ----------
    api_base : str
        Base URL of the Express backend (default: http://localhost:4000).
    scenario : str
        Active disaster scenario used for edge weighting.
    cfg : MeshConfig
        Typed configuration snapshot; defaults to MeshConfig.from_env().
    """

    api_base: str = "http://localhost:4000"
    scenario: str = "earthquake"
    cfg: MeshConfig = field(default_factory=MeshConfig.from_env)

    # ── Public ────────────────────────────────────────────────────────────────

    def build(self) -> nx.DiGraph:
        """
        Fetch topology from the backend and return a populated DiGraph.

        Nodes carry the full MeshNode metadata as attributes.
        Edges carry `weight`, `protocol`, and `quality`.

        Returns
        -------
        nx.DiGraph
            Empty graph if the backend is unreachable.
        """
        topology = self._fetch_topology()
        G: nx.DiGraph = nx.DiGraph()

        for n in topology.get("nodes", []):
            G.add_node(
                n["id"],
                label=n.get("label", n["id"]),
                role=n.get("role", "peer"),
                battery=n.get("batteryPercentage", 100),
                signal=n.get("signal", 80),
                lat=n.get("lat"),
                lng=n.get("lng"),
                bluetooth=n.get("bluetoothStatus", False),
            )

        for e in topology.get("edges", []):
            quality = e.get("quality", 80)
            battery_a = G.nodes[e["a"]].get("battery", 100) if e["a"] in G.nodes else 100
            battery_b = G.nodes[e["b"]].get("battery", 100) if e["b"] in G.nodes else 100
            w = _edge_weight(quality, min(battery_a, battery_b), self.scenario, self.cfg)

            # Add both directions — mesh links are bidirectional
            G.add_edge(e["a"], e["b"], weight=w, protocol=e.get("protocol", "wifi"), quality=quality)
            G.add_edge(e["b"], e["a"], weight=w, protocol=e.get("protocol", "wifi"), quality=quality)

        log.info(
            "Graph built — %d nodes, %d directed edges (scenario=%s)",
            G.number_of_nodes(),
            G.number_of_edges(),
            self.scenario,
        )
        return G

    # ── Private ───────────────────────────────────────────────────────────────

    def _fetch_topology(self) -> dict[str, Any]:
        url = f"{self.api_base}/api/mesh/topology"
        try:
            resp = requests.get(url, timeout=self.cfg.http_timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            log.warning("Could not fetch topology from %s: %s", url, exc)
            return {"nodes": [], "edges": []}
