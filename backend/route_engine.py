"""
MeshNet AI — Layer 3: IBM Bob AI Core Routing Logic
backend/route_engine.py

Implements AODV-inspired (Ad hoc On-demand Distance Vector) routing
on top of NetworkX using Dijkstra's shortest-path algorithm weighted
by link quality, battery state, and disaster scenario multipliers.

This is the "IBM Bob AI Core Routing Logic" described in Section 2 of
the project specification.  It sits between the simulation graph
(Layer 2) and the backend API (Layer 4) and answers queries like:

    "What is the best path from node A to node B in a flood scenario,
     given current signal strengths and battery levels?"

Usage
-----
    from route_engine import RouteEngine, RouteQuery, RouteResult
    engine = RouteEngine(api_base="http://localhost:4000")
    result = engine.query(RouteQuery(source="cmd-hq", target="med-01", scenario="flood"))
    print(result)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx

from config import MeshConfig
from graph_builder import MeshGraphBuilder

log = logging.getLogger(__name__)


# ─── Data contracts ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RouteQuery:
    """Input parameters for a routing query."""
    source: str                      # source node ID
    target: str                      # destination node ID
    scenario: str = "earthquake"     # flood | war_zone | earthquake
    max_hops: Optional[int] = None   # override config MAX_HOPS when set


@dataclass
class RouteResult:
    """
    Output of a successful (or failed) routing computation.

    Fields
    ------
    found : bool
        True when a path was found within the hop limit.
    path : list[str]
        Ordered list of node IDs from source to target (empty on failure).
    hops : int
        Number of relay hops (len(path) - 1).
    total_weight : float
        Cumulative edge weight along the path (lower = better).
    estimated_latency_ms : float
        Rough latency estimate: 10 ms base + 3 ms per hop.
    reason : str
        Human-readable explanation, populated on failure.
    scenario : str
        The disaster scenario this result was computed for.
    computed_at : float
        Unix timestamp of when the computation completed.
    """

    found: bool
    path: list[str] = field(default_factory=list)
    hops: int = 0
    total_weight: float = 0.0
    estimated_latency_ms: float = 0.0
    reason: str = ""
    scenario: str = "earthquake"
    computed_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "found":                self.found,
            "path":                 self.path,
            "hops":                 self.hops,
            "totalWeight":          round(self.total_weight, 4),
            "estimatedLatencyMs":   round(self.estimated_latency_ms, 2),
            "reason":               self.reason,
            "scenario":             self.scenario,
            "computedAt":           self.computed_at,
        }


# ─── Routing Engine ───────────────────────────────────────────────────────────

class RouteEngine:
    """
    IBM Bob AI Core Routing Logic.

    Rebuilds the mesh graph on every query (or optionally caches it
    for `cache_ttl_s` seconds) and runs Dijkstra's algorithm to find
    the lowest-weight path that stays within the hop limit.

    Parameters
    ----------
    api_base : str
        Express backend URL used to fetch live topology.
    cfg : MeshConfig
        Configuration snapshot.
    cache_ttl_s : float
        How long to cache the topology graph in seconds (0 = no cache).
    """

    def __init__(
        self,
        api_base: str = "http://localhost:4000",
        cfg: Optional[MeshConfig] = None,
        cache_ttl_s: float = 5.0,
    ) -> None:
        self._api_base   = api_base
        self._cfg        = cfg or MeshConfig.from_env()
        self._cache_ttl  = cache_ttl_s
        self._graph_cache: dict[str, tuple[nx.DiGraph, float]] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def query(self, q: RouteQuery) -> RouteResult:
        """
        Compute the optimal mesh route from q.source → q.target.

        Algorithm
        ---------
        1.  Fetch (or reuse cached) topology graph for the given scenario.
        2.  Check that both source and target nodes exist in the graph.
        3.  Run Dijkstra's shortest-path algorithm (scipy-free, pure NetworkX).
        4.  Validate that the resulting hop count ≤ MAX_HOPS.
        5.  Annotate and return the RouteResult.

        Returns
        -------
        RouteResult
            `found=False` with a `reason` string on any failure.
        """
        max_hops = q.max_hops or self._cfg.max_hops
        G = self._get_graph(q.scenario)

        # ── Guard: empty graph ────────────────────────────────────────────────
        if G.number_of_nodes() == 0:
            return RouteResult(
                found=False,
                reason="Mesh graph is empty — backend topology unavailable",
                scenario=q.scenario,
            )

        # ── Guard: nodes must exist ───────────────────────────────────────────
        for node_id, role in ((q.source, "source"), (q.target, "target")):
            if node_id not in G.nodes:
                return RouteResult(
                    found=False,
                    reason=f"{role.capitalize()} node '{node_id}' not found in mesh graph",
                    scenario=q.scenario,
                )

        # ── Dijkstra ──────────────────────────────────────────────────────────
        try:
            raw_path: list[str] = nx.dijkstra_path(G, q.source, q.target, weight="weight")
            total_w: float      = nx.dijkstra_path_length(G, q.source, q.target, weight="weight")
        except nx.NetworkXNoPath:
            return RouteResult(
                found=False,
                reason=f"No path exists between '{q.source}' and '{q.target}'",
                scenario=q.scenario,
            )
        except nx.NodeNotFound as exc:
            return RouteResult(
                found=False,
                reason=str(exc),
                scenario=q.scenario,
            )

        hops = len(raw_path) - 1

        # ── Guard: TTL / hop limit ────────────────────────────────────────────
        if hops > max_hops:
            return RouteResult(
                found=False,
                reason=(
                    f"Path exceeds max hops ({hops} > {max_hops}) — "
                    "packet would be dropped by AODV TTL"
                ),
                path=raw_path,
                hops=hops,
                total_weight=total_w,
                scenario=q.scenario,
            )

        latency = 10.0 + hops * 3.0  # rough BLE/Wi-Fi relay latency estimate

        log.info(
            "Route %s→%s via %d hops, weight=%.2f, scenario=%s",
            q.source, q.target, hops, total_w, q.scenario,
        )

        return RouteResult(
            found=True,
            path=raw_path,
            hops=hops,
            total_weight=total_w,
            estimated_latency_ms=latency,
            scenario=q.scenario,
        )

    def describe_path(self, result: RouteResult, G: Optional[nx.DiGraph] = None) -> str:
        """
        Return a human-readable path description for logging / UI tooltips.

        Example output:
            cmd-hq → ramos-phone → med-01  (2 hops, weight=4.20)
        """
        if not result.found or not result.path:
            return f"No route — {result.reason}"
        arrow = " → ".join(result.path)
        return f"{arrow}  ({result.hops} hop{'s' if result.hops != 1 else ''}, weight={result.total_weight:.2f})"

    # ── Private ───────────────────────────────────────────────────────────────

    def _get_graph(self, scenario: str) -> nx.DiGraph:
        """Return cached graph or rebuild from the backend topology."""
        now = time.time()
        cached = self._graph_cache.get(scenario)
        if cached and (now - cached[1]) < self._cache_ttl:
            return cached[0]

        builder = MeshGraphBuilder(
            api_base=self._api_base,
            scenario=scenario,
            cfg=self._cfg,
        )
        G = builder.build()
        self._graph_cache[scenario] = (G, now)
        return G
