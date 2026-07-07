"""
MeshNet AI — Python Network Brain
backend/config.py

Environment configuration for the mesh network simulation.
All physical range values are in metres; tweak them per field
measurements before any live deployment.

Usage:
    from config import MAX_RANGE_FLOOD, TOTAL_SIMULATED_NODES, ...
    or
    from config import MeshConfig  # typed dataclass for IDE support
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


# ──────────────────────────────────────────────────────────────────────────────
# Disaster-scenario communication ranges
# ──────────────────────────────────────────────────────────────────────────────
# These represent the effective Bluetooth / Wi-Fi Direct radius in each
# scenario.  Physical obstacles, water absorption, and RF interference
# are already factored into the conservative estimates below.

MAX_RANGE_FLOOD: int = int(os.getenv("MESH_RANGE_FLOOD", 150))
# Device communication radius in metres during floods.
# Water attenuates 2.4 GHz signals; elevated devices can reach 150 m.

MAX_RANGE_WAR_ZONE: int = int(os.getenv("MESH_RANGE_WAR_ZONE", 30))
# Device communication radius due to electronic interference / jamming.
# 30 m conservative estimate for active RF countermeasures in conflict zones.
# (Override via MESH_RANGE_WAR_ZONE env var if field measurements differ.)

MAX_RANGE_EARTHQUAKE: int = int(os.getenv("MESH_RANGE_EARTHQUAKE", 300))
# Device communication radius in open post-quake fields.
# 300 m covers the full 1 km Manila disaster zone at adequate density.
# Rubble-free areas allow maximum BLE / Wi-Fi Direct propagation.

TOTAL_SIMULATED_NODES: int = int(os.getenv("MESH_TOTAL_NODES", 100))
# Total virtual devices loaded into the simulation database.


# ──────────────────────────────────────────────────────────────────────────────
# Network topology defaults
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_BATTERY_MIN: int = 20    # % — nodes below this are considered critical
DEFAULT_SIGNAL_THRESHOLD: int = 40  # % RSSI — links below this are unreliable
MAX_HOPS: int = 7                   # AODV maximum hop count before TTL expiry
PACKET_LOSS_RATE: float = 0.05      # 5 % simulated packet loss per hop


# ──────────────────────────────────────────────────────────────────────────────
# IBM Cloudant / backend API
# ──────────────────────────────────────────────────────────────────────────────

CLOUDANT_URL: str = os.getenv("CLOUDANT_URL", "")
CLOUDANT_API_KEY: str = os.getenv("CLOUDANT_API_KEY", "")
CLOUDANT_DB: str = os.getenv("CLOUDANT_DB", "mesh_nodes_db")

BACKEND_API_URL: str = os.getenv("BACKEND_API_URL", "http://localhost:4000")

# Request timeout in seconds for all outbound HTTP calls
HTTP_TIMEOUT: int = int(os.getenv("HTTP_TIMEOUT", 10))


# ──────────────────────────────────────────────────────────────────────────────
# Cryptography
# ──────────────────────────────────────────────────────────────────────────────

# Shared secret for node-to-node HMAC verification.
# Override via environment variable — never hard-code in production.
NODE_SHARED_SECRET: str = os.getenv(
    "MESH_NODE_SECRET", "CHANGE-ME-before-deployment"
)

# AES-GCM key size in bits (256 is the standard for field deployments)
AES_KEY_BITS: int = 256


# ──────────────────────────────────────────────────────────────────────────────
# Typed dataclass — use this when you want IDE autocomplete & type safety
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MeshConfig:
    """
    Immutable snapshot of the active mesh configuration.
    Pass instances of this class into simulation functions instead of
    reading globals, to make testing and parameterisation easier.

    Example
    -------
    >>> cfg = MeshConfig.from_env()
    >>> print(cfg.range_for_scenario("flood"))
    50
    """

    # Scenario ranges
    max_range_flood: int = MAX_RANGE_FLOOD
    max_range_war_zone: int = MAX_RANGE_WAR_ZONE
    max_range_earthquake: int = MAX_RANGE_EARTHQUAKE

    # Simulation
    total_simulated_nodes: int = TOTAL_SIMULATED_NODES
    default_battery_min: int = DEFAULT_BATTERY_MIN
    default_signal_threshold: int = DEFAULT_SIGNAL_THRESHOLD
    max_hops: int = MAX_HOPS
    packet_loss_rate: float = PACKET_LOSS_RATE

    # Connectivity
    cloudant_url: str = field(default_factory=lambda: CLOUDANT_URL)
    cloudant_api_key: str = field(default_factory=lambda: CLOUDANT_API_KEY)
    cloudant_db: str = field(default_factory=lambda: CLOUDANT_DB)
    backend_api_url: str = field(default_factory=lambda: BACKEND_API_URL)
    http_timeout: int = HTTP_TIMEOUT

    # Security
    node_shared_secret: str = field(default_factory=lambda: NODE_SHARED_SECRET)
    aes_key_bits: int = AES_KEY_BITS

    # ── Helpers ──────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "MeshConfig":
        """Construct a MeshConfig by reading current environment variables."""
        return cls()

    def range_for_scenario(self, scenario: str) -> int:
        """
        Return the effective communication range (metres) for a given scenario.

        Parameters
        ----------
        scenario : str
            One of 'flood', 'war_zone', or 'earthquake'.

        Returns
        -------
        int
            Range in metres.

        Raises
        ------
        ValueError
            If an unknown scenario string is passed.
        """
        _map = {
            "flood":      self.max_range_flood,
            "war_zone":   self.max_range_war_zone,
            "earthquake": self.max_range_earthquake,
        }
        if scenario not in _map:
            raise ValueError(
                f"Unknown scenario '{scenario}'. "
                f"Valid options: {list(_map.keys())}"
            )
        return _map[scenario]

    def summary(self) -> str:
        """Return a human-readable configuration summary for logging."""
        return (
            f"MeshNet AI Config\n"
            f"  Ranges     : flood={self.max_range_flood}m  "
            f"war_zone={self.max_range_war_zone}m  "
            f"earthquake={self.max_range_earthquake}m\n"
            f"  Nodes      : {self.total_simulated_nodes} simulated\n"
            f"  Max hops   : {self.max_hops}\n"
            f"  Packet loss: {self.packet_loss_rate * 100:.0f}%\n"
            f"  Cloudant DB: {self.cloudant_db or '(not configured)'}\n"
            f"  Backend API: {self.backend_api_url}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Quick self-test — run `python config.py` to verify the setup
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = MeshConfig.from_env()
    print(cfg.summary())
    print()
    for scenario in ("flood", "war_zone", "earthquake"):
        print(f"  range_for_scenario('{scenario}') -> {cfg.range_for_scenario(scenario)} m")
