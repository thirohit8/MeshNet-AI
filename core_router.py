"""
MeshNet-AI — core_router.py
============================
Scenario-aware P2P routing controller.

This module bridges the legacy disaster scenario configuration in ``config.py``
with the production ``routing.RoutingEngine``.  It is the authoritative entry
point for CLI tools (dashboard_offline.py, launcher.py) that need a fully-
resolved routing result for a named disaster scenario.

Class hierarchy
---------------
MeshNetRouter
    Uses:
      • config.SCENARIOS        — scenario range / max-hop parameters
      • routing.RoutingEngine   — filter → score → sort → path pipeline
      • nodes_mock.simulated_network / mock_topology()

Usage
-----
    from core_router import MeshNetRouter, build_safe_routes
    router = MeshNetRouter(simulated_network, "Flood")
    routes = router.calculate_safe_routes()   # legacy dict list
    result = router.compute_full_result()     # RoutingResult dataclass
"""

from __future__ import annotations

import logging
from typing import Optional

import config
from nodes_mock import simulated_network, get_active_nodes, mock_topology
from routing import RoutingEngine, MeshNode, RoutingResult

logger = logging.getLogger(__name__)


# ── MeshNetRouter ─────────────────────────────────────────────────────────────

class MeshNetRouter:
    """
    Scenario-aware routing controller.

    Parameters
    ----------
    network      : list of node dicts (``simulated_network`` format)
    disaster_type: one of "Flood", "Earthquake", "War Zone"
                   (also accepts legacy "War_Zone" key)
    """

    # Normalise legacy underscore key to the canonical spaced form
    _KEY_NORMALISE: dict[str, str] = {
        "War_Zone" : "War Zone",
        "war_zone" : "War Zone",
        "war zone" : "War Zone",
        "flood"    : "Flood",
        "earthquake": "Earthquake",
    }

    def __init__(
        self,
        network      : list[dict],
        disaster_type: str,
    ) -> None:
        self.network       = network
        self.disaster_type = self._KEY_NORMALISE.get(disaster_type, disaster_type)
        self._engine       = RoutingEngine()

        # Resolve scenario config — fallback to safe defaults if unknown
        try:
            self._scenario_cfg = config.get_scenario(self.disaster_type)
        except KeyError:
            logger.warning(
                "[ROUTER] Unknown disaster type '%s'; using Flood defaults.",
                disaster_type,
            )
            self._scenario_cfg = config.SCENARIOS["Flood"]

        self.disaster_range: int = self._scenario_cfg["range_km"]
        self.max_hops      : int = self._scenario_cfg["max_hops"]

    # ── Public API ─────────────────────────────────────────────────────────────

    def calculate_safe_routes(self) -> list[dict]:
        """
        Legacy interface — returns a list of route-summary dicts.

        Each dict contains:
          node_id, device, battery, priority_status,
          routing_score, allowed_range_km, hop_limit
        """
        # Convert dict topology → MeshNode objects for the routing engine
        mesh_nodes = self._dict_to_mesh_nodes()
        result     = self._engine.compute(mesh_nodes)

        safe_routes: list[dict] = []
        for node in result.stable_nodes:
            priority = "HIGH" if node.has_weather_hq_signal else (
                "MEDIUM" if node.routing_score >= 0.55 else "NORMAL"
            )
            safe_routes.append({
                "node_id"        : node.node_id,
                "device"         : node.device_type,
                "battery"        : int(node.battery_level),
                "priority_status": priority,
                "routing_score"  : round(node.routing_score, 4),
                "allowed_range_km": self.disaster_range,
                "hop_limit"      : self.max_hops,
            })

        logger.info(
            "[ROUTER] Scenario=%s  stable=%d  range=%d km  max_hops=%d",
            self.disaster_type, len(safe_routes),
            self.disaster_range, self.max_hops,
        )
        return safe_routes

    def compute_full_result(self) -> RoutingResult:
        """
        Return the complete ``RoutingResult`` dataclass from the engine,
        with the hop chain truncated to this scenario's max_hops.
        """
        mesh_nodes = self._dict_to_mesh_nodes()
        result     = self._engine.compute(mesh_nodes)

        # Truncate path to the scenario hop limit
        result.optimal_path = result.optimal_path[: self.max_hops]
        return result

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _dict_to_mesh_nodes(self) -> list[MeshNode]:
        """Convert the dict-based network topology into MeshNode objects."""
        nodes: list[MeshNode] = []
        for d in self.network:
            nodes.append(
                MeshNode(
                    node_id              = d["node_id"],
                    battery_level        = float(d["battery_level"]),
                    is_active            = bool(d["is_active"]),
                    device_type          = d.get("device_type", "unknown").lower(),
                    has_weather_hq_signal= bool(d.get("has_weather_hq_signal", False)),
                    lat                  = float(d.get("lat", 0.0)),
                    lon                  = float(d.get("lon", 0.0)),
                )
            )
        return nodes


# ── Convenience factory ───────────────────────────────────────────────────────

def build_safe_routes(disaster_type: str = "Flood") -> list[dict]:
    """
    One-shot helper — build safe routes using the default mock topology.

    Parameters
    ----------
    disaster_type : scenario name (default "Flood")

    Returns
    -------
    list of route-summary dicts (see MeshNetRouter.calculate_safe_routes)
    """
    router = MeshNetRouter(simulated_network, disaster_type)
    return router.calculate_safe_routes()


# ── Module self-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("   MeshNet-AI — Core Router  |  Scenario Self-Test")
    print("=" * 60)

    for scenario in config.scenario_names():
        print(f"\n  Scenario: {scenario}")
        print(f"  Range   : {config.SCENARIOS[scenario]['range_km']} km")
        print(f"  MaxHops : {config.SCENARIOS[scenario]['max_hops']}")
        print("  " + "-" * 54)

        router = MeshNetRouter(simulated_network, scenario)
        routes = router.calculate_safe_routes()

        # Full result for path quality
        result = router.compute_full_result()

        print(
            f"  Stable nodes : {len(routes)}"
            f"  |  Path hops: {len(result.optimal_path)}"
            f"  |  Quality  : {result.path_quality:.3f}"
            f"  |  HQ anchor: {result.hq_anchor or 'none'}"
        )
        print()
        fmt = "    {:<12} {:<12} {:>6}%  {:>7}  score={}"
        print(fmt.format("NODE ID", "DEVICE", "BATT", "PRIORITY", "SCORE"))
        print("    " + "-" * 52)
        for r in routes:
            star = "★ " if r["priority_status"] == "HIGH" else "  "
            print(fmt.format(
                star + r["node_id"],
                r["device"],
                r["battery"],
                r["priority_status"],
                r["routing_score"],
            ))
