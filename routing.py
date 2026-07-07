"""
MeshNet-AI — routing.py
=======================
Advanced P2P mesh routing engine.

Algorithm overview
------------------
1. **Filter** — discard nodes with battery ≤ 15 % or inactive flag.
2. **Score** — each surviving node receives a composite routing weight:

        score = W_bat  * normalised_battery
              + W_hq   * weather_hq_bonus
              + W_type * device_type_bonus

   where:
       W_bat  = 0.35   (battery health contribution)
       W_hq   = 0.50   (Weather-HQ signal — absolute preference)
       W_type = 0.15   (device capability tier)

3. **Sort** — descending by score → best relay nodes first.
4. **Path** — a greedy shortest-path is built from the sorted list,
   returning an ordered sequence of node_ids representing the optimal
   hop chain.

All results are returned as plain Python dataclasses so the GUI and
messaging layers can consume them without importing routing internals.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Routing weight constants ──────────────────────────────────────────────────
W_BATTERY    = 0.35   # battery health weight
W_WEATHER_HQ = 0.50   # absolute Weather-HQ signal weight
W_DEVICE     = 0.15   # device capability tier weight

BATTERY_THRESHOLD = 15.0   # percent — nodes at or below this are filtered out

# ── Device-type capability tiers ─────────────────────────────────────────────
DEVICE_TYPE_TIER: dict[str, float] = {
    "gateway"    : 1.0,   # dedicated mesh gateway
    "relay"      : 0.85,  # purpose-built relay node
    "smartphone" : 0.70,  # common mobile device
    "tablet"     : 0.65,
    "iot"        : 0.40,  # resource-constrained sensor node
    "unknown"    : 0.30,
}


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class MeshNode:
    """
    Represents a single peer in the mesh network.

    Fields
    ------
    node_id          : unique string identifier (MAC address, UUID, etc.)
    battery_level    : float  0–100 %
    is_active        : bool   — False if the node is unreachable / sleeping
    device_type      : str    — see DEVICE_TYPE_TIER for recognised values
    has_weather_hq_signal : bool — node is relaying a Weather HQ feed
    lat              : float  — WGS-84 latitude  (used for map rendering)
    lon              : float  — WGS-84 longitude
    """
    node_id              : str
    battery_level        : float
    is_active            : bool
    device_type          : str   = "unknown"
    has_weather_hq_signal: bool  = False
    lat                  : float = 0.0
    lon                  : float = 0.0

    # Computed by the router — not set by caller
    routing_score        : float = field(default=0.0, init=False, repr=False)


@dataclass
class RoutingResult:
    """
    Output produced by RoutingEngine.compute().

    Attributes
    ----------
    stable_nodes     : filtered + scored list, descending by routing_score
    optimal_path     : ordered node_id chain representing the best hop route
    hq_anchor        : node_id of the highest-scoring Weather-HQ node (or None)
    path_quality     : aggregate score of the selected path  (0.0 – 1.0)
    rejected_count   : number of nodes filtered out
    """
    stable_nodes   : list[MeshNode]
    optimal_path   : list[str]
    hq_anchor      : Optional[str]
    path_quality   : float
    rejected_count : int


# ── Routing engine ────────────────────────────────────────────────────────────

class RoutingEngine:
    """
    Stateless routing engine.  Call ``compute(nodes)`` with a list of
    MeshNode objects; get back a RoutingResult.

    Example
    -------
    >>> engine = RoutingEngine()
    >>> result = engine.compute(mock_topology())
    >>> print(result.optimal_path)
    """

    # ── Public API ─────────────────────────────────────────────────────────────

    def compute(self, nodes: list[MeshNode]) -> RoutingResult:
        """
        Run the full routing pipeline on *nodes*.

        Returns
        -------
        RoutingResult
        """
        original_count = len(nodes)

        # Step 1 – filter
        stable = self._filter_stable(nodes)
        rejected = original_count - len(stable)
        logger.info(
            "[ROUTING] %d/%d nodes passed stability filter.",
            len(stable), original_count
        )

        if not stable:
            logger.warning("[ROUTING] No stable nodes — returning empty result.")
            return RoutingResult(
                stable_nodes=[],
                optimal_path=[],
                hq_anchor=None,
                path_quality=0.0,
                rejected_count=rejected,
            )

        # Step 2 – score
        for node in stable:
            node.routing_score = self._score_node(node)

        # Step 3 – sort
        stable.sort(key=lambda n: n.routing_score, reverse=True)

        # Step 4 – build path
        path = self._build_path(stable)

        # Identify Weather-HQ anchor
        hq_anchor = next(
            (n.node_id for n in stable if n.has_weather_hq_signal), None
        )

        # Aggregate path quality
        path_quality = self._path_quality(stable, path)

        result = RoutingResult(
            stable_nodes=stable,
            optimal_path=path,
            hq_anchor=hq_anchor,
            path_quality=path_quality,
            rejected_count=rejected,
        )
        logger.info(
            "[ROUTING] Path computed: %d hops | quality=%.3f | HQ_anchor=%s",
            len(path), path_quality, hq_anchor,
        )
        return result

    # ── Step implementations ──────────────────────────────────────────────────

    @staticmethod
    def _filter_stable(nodes: list[MeshNode]) -> list[MeshNode]:
        """
        Return nodes that are:
          • is_active == True
          • battery_level > BATTERY_THRESHOLD (strict >)
        """
        return [
            n for n in nodes
            if n.is_active and n.battery_level > BATTERY_THRESHOLD
        ]

    @staticmethod
    def _score_node(node: MeshNode) -> float:
        """
        Compute composite routing score in [0, 1].

        Formula:
            score = W_BATTERY * (battery / 100)
                  + W_WEATHER_HQ * (1 if has_weather_hq_signal else 0)
                  + W_DEVICE * device_tier
        """
        bat_norm     = max(0.0, min(node.battery_level / 100.0, 1.0))
        hq_bonus     = 1.0 if node.has_weather_hq_signal else 0.0
        device_tier  = DEVICE_TYPE_TIER.get(
            node.device_type.lower(), DEVICE_TYPE_TIER["unknown"]
        )
        score = (
            W_BATTERY    * bat_norm
            + W_WEATHER_HQ * hq_bonus
            + W_DEVICE     * device_tier
        )
        return round(score, 4)

    @staticmethod
    def _build_path(sorted_nodes: list[MeshNode]) -> list[str]:
        """
        Greedy hop-chain construction.

        Strategy
        --------
        • Always start from the highest-scored node.
        • Append the next node whose geographic distance to the current
          tail is minimised (nearest-neighbour greedy).
        • If no coordinate data is available (lat=lon=0), fall back to
          score-rank order.

        Returns an ordered list of node_ids.
        """
        if not sorted_nodes:
            return []

        remaining = list(sorted_nodes)
        path      = [remaining.pop(0)]   # best-scored node is the source

        while remaining:
            tail = path[-1]
            # Use geo-distance if coordinates are meaningful
            use_geo = any(
                (n.lat != 0.0 or n.lon != 0.0) for n in remaining
            )
            if use_geo:
                next_node = min(
                    remaining,
                    key=lambda n: _haversine(tail.lat, tail.lon, n.lat, n.lon),
                )
            else:
                # No coordinates — pick next in score-rank order
                next_node = remaining[0]

            path.append(next_node)
            remaining.remove(next_node)

        return [n.node_id for n in path]

    @staticmethod
    def _path_quality(stable: list[MeshNode], path: list[str]) -> float:
        """
        Compute mean routing score of path nodes normalised to [0, 1].
        """
        score_map = {n.node_id: n.routing_score for n in stable}
        scores    = [score_map[nid] for nid in path if nid in score_map]
        return round(sum(scores) / len(scores), 4) if scores else 0.0


# ── Haversine helper ──────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Return the great-circle distance in **kilometres** between two WGS-84
    coordinates using the Haversine formula.
    """
    R    = 6_371.0          # Earth's mean radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a    = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


# ── Mock topology factory (used for demo / unit testing) ─────────────────────

def mock_topology() -> list[MeshNode]:
    """
    Return a realistic 12-node mock mesh topology spread across a
    hypothetical disaster zone.  Includes edge cases:
    • 3 nodes below battery threshold
    • 1 inactive node
    • 2 Weather-HQ carriers
    """
    return [
        MeshNode("NODE-A1", battery_level=87.0, is_active=True,
                 device_type="gateway",    has_weather_hq_signal=True,
                 lat=34.0522, lon=-118.2437),
        MeshNode("NODE-B2", battery_level=62.0, is_active=True,
                 device_type="relay",      has_weather_hq_signal=False,
                 lat=34.0600, lon=-118.2500),
        MeshNode("NODE-C3", battery_level=11.0, is_active=True,   # ← FILTERED
                 device_type="smartphone", has_weather_hq_signal=False,
                 lat=34.0450, lon=-118.2300),
        MeshNode("NODE-D4", battery_level=76.0, is_active=True,
                 device_type="smartphone", has_weather_hq_signal=True,
                 lat=34.0700, lon=-118.2600),
        MeshNode("NODE-E5", battery_level=45.0, is_active=False,  # ← FILTERED
                 device_type="tablet",     has_weather_hq_signal=False,
                 lat=34.0550, lon=-118.2350),
        MeshNode("NODE-F6", battery_level=93.0, is_active=True,
                 device_type="gateway",    has_weather_hq_signal=False,
                 lat=34.0480, lon=-118.2550),
        MeshNode("NODE-G7", battery_level=33.0, is_active=True,
                 device_type="iot",        has_weather_hq_signal=False,
                 lat=34.0620, lon=-118.2420),
        MeshNode("NODE-H8", battery_level=8.0,  is_active=True,   # ← FILTERED
                 device_type="smartphone", has_weather_hq_signal=False,
                 lat=34.0510, lon=-118.2460),
        MeshNode("NODE-I9", battery_level=55.0, is_active=True,
                 device_type="relay",      has_weather_hq_signal=False,
                 lat=34.0590, lon=-118.2480),
        MeshNode("NODE-J10",battery_level=70.0, is_active=True,
                 device_type="tablet",     has_weather_hq_signal=False,
                 lat=34.0530, lon=-118.2510),
        MeshNode("NODE-K11",battery_level=19.0, is_active=True,
                 device_type="iot",        has_weather_hq_signal=False,
                 lat=34.0640, lon=-118.2390),
        MeshNode("NODE-L12",battery_level=82.0, is_active=True,
                 device_type="smartphone", has_weather_hq_signal=False,
                 lat=34.0560, lon=-118.2530),
    ]
