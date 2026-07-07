"""
MeshNet AI — Layer 2: Mesh Network Simulator
backend/mesh_simulator.py

Simulates dynamic mesh network conditions — signal drift, battery
depletion, node join/leave events — and pushes state deltas to the
Express backend via heartbeat PATCHes.

This module drives the "live" data that the routing engine queries
and that the dashboard map visualises.

Usage
-----
    python mesh_simulator.py                       # runs until Ctrl-C
    python mesh_simulator.py --nodes 20 --interval 2
"""

from __future__ import annotations

import argparse
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from config import MeshConfig

log = logging.getLogger(__name__)


# ─── Node state ───────────────────────────────────────────────────────────────

@dataclass
class SimulatedNode:
    """Runtime state for a single simulated mesh node."""

    id: str
    label: str
    lat: float
    lng: float
    battery: float        = 100.0
    signal: float         = 80.0
    bluetooth: bool       = True
    role: str             = "peer"
    device: str           = "smartphone"
    alive: bool           = True

    def tick(self, cfg: MeshConfig) -> None:
        """Advance node state by one simulation step."""
        # Battery drains slowly; BLE scanning costs more power
        drain = random.uniform(0.1, 0.4) + (0.2 if self.bluetooth else 0.0)
        self.battery = max(0.0, self.battery - drain)

        # Signal fluctuates ± 5 %
        self.signal = max(0.0, min(100.0, self.signal + random.uniform(-5, 5)))

        # BLE toggles off when battery is critically low
        if self.battery < cfg.default_battery_min:
            self.bluetooth = False

        # Node goes "silent" (unreachable) probabilistically at low battery
        if self.battery < 5.0 and random.random() < 0.05:
            self.alive = False

    def heartbeat_payload(self) -> dict:
        return {
            "signal":            round(self.signal),
            "batteryPercentage": round(self.battery),
            "bluetoothStatus":   self.bluetooth,
            "lat":               self.lat,
            "lng":               self.lng,
        }


# ─── Simulator ────────────────────────────────────────────────────────────────

class MeshSimulator:
    """
    Drives a fleet of SimulatedNodes, calling the Express heartbeat
    endpoint every `interval_s` seconds to reflect state changes.

    Parameters
    ----------
    node_count : int
        Number of nodes to simulate.
    interval_s : float
        Seconds between simulation ticks.
    api_base : str
        Express backend URL.
    scenario : str
        Active disaster scenario (affects battery drain multipliers).
    cfg : MeshConfig
        Configuration snapshot.
    """

    def __init__(
        self,
        node_count: int = 10,
        interval_s: float = 5.0,
        api_base: str = "http://localhost:4000",
        scenario: str = "earthquake",
        cfg: Optional[MeshConfig] = None,
    ) -> None:
        self._count     = node_count
        self._interval  = interval_s
        self._api_base  = api_base
        self._scenario  = scenario
        self._cfg       = cfg or MeshConfig.from_env()
        self._nodes: list[SimulatedNode] = []
        self._session   = requests.Session()

    # ── Public ────────────────────────────────────────────────────────────────

    def bootstrap(self) -> None:
        """Register all simulated nodes with the Express backend."""
        base_lat = 14.5995
        base_lng = 120.9842
        max_range = self._cfg.range_for_scenario(self._scenario)
        spread = max_range / 111_320

        for i in range(self._count):
            nid = f"sim-{i:03d}"
            node = SimulatedNode(
                id=nid,
                label=f"SIM·{i:03d}",
                lat=base_lat + random.uniform(-spread * 3, spread * 3),
                lng=base_lng + random.uniform(-spread * 3, spread * 3),
                battery=random.uniform(40.0, 100.0),
                signal=random.uniform(50.0, 100.0),
                bluetooth=random.random() > 0.25,
                role="relay" if i % 4 == 0 else "peer",
                device=random.choice(["smartphone", "laptop"]),
            )
            self._nodes.append(node)
            self._register_node(node)

        log.info("Bootstrapped %d simulated nodes", len(self._nodes))

    def run(self) -> None:
        """
        Run the simulation loop until interrupted.
        Ticks every `interval_s` seconds, sending heartbeats to the backend.
        """
        log.info(
            "Simulator running — %d nodes, %.1fs interval, scenario=%s",
            self._count, self._interval, self._scenario,
        )
        try:
            while True:
                self._tick()
                time.sleep(self._interval)
        except KeyboardInterrupt:
            log.info("Simulator stopped")

    # ── Private ───────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        alive_count = 0
        for node in self._nodes:
            if not node.alive:
                continue
            node.tick(self._cfg)
            self._send_heartbeat(node)
            alive_count += 1

        log.debug(
            "Tick — %d/%d nodes alive", alive_count, len(self._nodes)
        )

    def _register_node(self, node: SimulatedNode) -> None:
        payload = {
            "id":                node.id,
            "label":             node.label,
            "name":              f"Simulated {node.device.capitalize()} {node.id}",
            "device":            node.device,
            "role":              node.role,
            "signal":            round(node.signal),
            "batteryPercentage": round(node.battery),
            "bluetoothStatus":   node.bluetooth,
            "lat":               round(node.lat, 6),
            "lng":               round(node.lng, 6),
        }
        try:
            self._session.post(
                f"{self._api_base}/api/mesh/register",
                json=payload,
                timeout=self._cfg.http_timeout,
            )
        except requests.RequestException as exc:
            log.warning("Register failed for %s: %s", node.id, exc)

    def _send_heartbeat(self, node: SimulatedNode) -> None:
        try:
            self._session.patch(
                f"{self._api_base}/api/mesh/nodes/{node.id}/heartbeat",
                json=node.heartbeat_payload(),
                timeout=self._cfg.http_timeout,
            )
        except requests.RequestException as exc:
            log.debug("Heartbeat failed for %s: %s", node.id, exc)


# ─── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="MeshNet AI mesh simulator")
    parser.add_argument("--nodes",    type=int,   default=10,          help="Number of nodes to simulate")
    parser.add_argument("--interval", type=float, default=5.0,         help="Heartbeat interval in seconds")
    parser.add_argument("--api",      type=str,   default="http://localhost:4000", help="Express backend URL")
    parser.add_argument(
        "--scenario",
        choices=["flood", "war_zone", "earthquake"],
        default="earthquake",
        help="Disaster scenario",
    )
    args = parser.parse_args()

    sim = MeshSimulator(
        node_count=args.nodes,
        interval_s=args.interval,
        api_base=args.api,
        scenario=args.scenario,
    )
    sim.bootstrap()
    sim.run()
