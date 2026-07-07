"""
backend/tests/test_simulation.py
=================================
Unit tests for simulation.py — the offline mesh device-chain builder.

Run with:
    cd backend
    python -m pytest tests/test_simulation.py -v
    # or, without pytest:
    python tests/test_simulation.py
"""

from __future__ import annotations

import math
import sys
import os

# Allow importing from backend/ regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import networkx as nx
from simulation import (
    MeshNode,
    MeshNetworkAnalyser,
    _BASE_LAT,
    _BASE_LNG,
    _M_PER_DEG_LAT,
    build_offline_mesh,
    calculate_distance,
    mesh_graph,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _node(nid: int, lat: float, lng: float, **kwargs) -> MeshNode:
    """Convenience factory for test nodes."""
    return MeshNode(
        id=nid,
        citizen_name=f"Test Citizen {nid}",
        lat=lat,
        lng=lng,
        **kwargs,
    )


# ─── Test: MeshNode coordinate projection ────────────────────────────────────

class TestMeshNodeProjection:
    def test_base_node_has_zero_xy(self):
        """Node at the base coordinate should project to (0, 0) ± rounding."""
        n = _node(1, _BASE_LAT, _BASE_LNG)
        assert abs(n.x) < 0.01, f"Expected x≈0, got {n.x}"
        assert abs(n.y) < 0.01, f"Expected y≈0, got {n.y}"

    def test_y_increases_northward(self):
        """Moving north should increase y."""
        south = _node(1, _BASE_LAT,       _BASE_LNG)
        north = _node(2, _BASE_LAT + 0.001, _BASE_LNG)
        assert north.y > south.y

    def test_x_increases_eastward(self):
        """Moving east should increase x."""
        west = _node(1, _BASE_LAT, _BASE_LNG)
        east = _node(2, _BASE_LAT, _BASE_LNG + 0.001)
        assert east.x > west.x

    def test_100m_north_approx_100m_y(self):
        """100 m north ≈ +0.000899° lat → y ≈ 100 m."""
        delta_deg = 100.0 / _M_PER_DEG_LAT          # ≈ 0.000899°
        n1 = _node(1, _BASE_LAT,            _BASE_LNG)
        n2 = _node(2, _BASE_LAT + delta_deg, _BASE_LNG)
        assert abs(n2.y - n1.y - 100.0) < 0.5


# ─── Test: calculate_distance ─────────────────────────────────────────────────

class TestCalculateDistance:
    def test_same_node_zero_distance(self):
        n = _node(1, _BASE_LAT, _BASE_LNG)
        assert calculate_distance(n, n) == 0.0

    def test_symmetric(self):
        a = _node(1, 14.5995, 120.9842)
        b = _node(2, 14.6004, 120.9851)
        assert calculate_distance(a, b) == calculate_distance(b, a)

    def test_euclidean_formula(self):
        """Verify the raw Euclidean formula matches manually."""
        a = _node(1, _BASE_LAT, _BASE_LNG)
        b = _node(2, _BASE_LAT, _BASE_LNG)
        # Force x/y directly for a known result
        b.x = 60.0
        b.y = 80.0
        expected = math.sqrt(60**2 + 80**2)  # 100.0
        assert abs(calculate_distance(a, b) - expected) < 0.01

    def test_known_distance_approx(self):
        """Two nodes ~141 m apart (100m E + 100m N) ≈ 141 m."""
        delta = 100.0 / _M_PER_DEG_LAT  # ~0.000899 deg
        cos_lat = math.cos(math.radians(_BASE_LAT))
        delta_lng = 100.0 / (_M_PER_DEG_LAT * cos_lat)
        a = _node(1, _BASE_LAT,           _BASE_LNG)
        b = _node(2, _BASE_LAT + delta,   _BASE_LNG + delta_lng)
        dist = calculate_distance(a, b)
        assert abs(dist - 141.4) < 2.0, f"Expected ≈141 m, got {dist:.1f}"


# ─── Test: build_offline_mesh ─────────────────────────────────────────────────

class TestBuildOfflineMesh:
    def _nearby_cluster(self, n: int = 4, sep_m: float = 40.0) -> list[MeshNode]:
        """Create n nodes in a tight cluster (sep_m metres apart on a line)."""
        delta = sep_m / _M_PER_DEG_LAT
        return [_node(i + 1, _BASE_LAT + i * delta, _BASE_LNG) for i in range(n)]

    def _distant_pair(self) -> list[MeshNode]:
        """Two nodes 300 m apart — outside any reasonable range."""
        delta = 300.0 / _M_PER_DEG_LAT
        return [
            _node(1, _BASE_LAT,         _BASE_LNG),
            _node(2, _BASE_LAT + delta, _BASE_LNG),
        ]

    def test_returns_nx_graph(self):
        nodes = self._nearby_cluster()
        G = build_offline_mesh(nodes, max_range_meters=200)
        assert isinstance(G, nx.Graph)

    def test_all_nodes_added(self):
        nodes = self._nearby_cluster(4)
        G = build_offline_mesh(nodes, max_range_meters=200)
        assert G.number_of_nodes() == 4

    def test_modifies_module_global(self):
        nodes = self._nearby_cluster(3)
        G = build_offline_mesh(nodes, max_range_meters=200)
        # Should be the same object as module-level mesh_graph
        assert G is mesh_graph

    def test_clears_previous_graph(self):
        nodes_a = self._nearby_cluster(3)
        build_offline_mesh(nodes_a, max_range_meters=200)
        nodes_b = self._nearby_cluster(2)
        G = build_offline_mesh(nodes_b, max_range_meters=200)
        assert G.number_of_nodes() == 2

    def test_all_ble_set_true(self):
        """Force-enable BLE broadcast: every node.bluetooth_status must be True."""
        nodes = self._nearby_cluster(4)
        nodes[0].bluetooth_status = False
        nodes[2].bluetooth_status = False
        build_offline_mesh(nodes, max_range_meters=200)
        for n in nodes:
            assert n.bluetooth_status is True, f"Node {n.id} BLE not enabled"

    def test_edges_within_range_connected(self):
        """Nodes closer than max_range must be connected."""
        nodes = self._nearby_cluster(4, sep_m=40.0)
        G = build_offline_mesh(nodes, max_range_meters=100)
        # Every adjacent pair is 40 m apart — all should be connected
        assert G.number_of_edges() >= 3

    def test_no_edges_outside_range(self):
        """Nodes 300 m apart must NOT be connected at 100 m range."""
        nodes = self._distant_pair()
        G = build_offline_mesh(nodes, max_range_meters=100)
        assert G.number_of_edges() == 0

    def test_edge_weight_equals_distance(self):
        """Edge weight should equal the Euclidean distance in metres."""
        nodes = self._nearby_cluster(2, sep_m=50.0)
        G = build_offline_mesh(nodes, max_range_meters=100)
        assert G.number_of_edges() == 1
        u, v, data = next(iter(G.edges(data=True)))
        expected = calculate_distance(nodes[0], nodes[1])
        assert abs(data["weight"] - expected) < 0.01

    def test_protocol_bluetooth_within_50m(self):
        """Links ≤ 50 m should be labelled 'bluetooth'."""
        nodes = self._nearby_cluster(2, sep_m=30.0)
        G = build_offline_mesh(nodes, max_range_meters=100)
        _, _, data = next(iter(G.edges(data=True)))
        assert data["protocol"] == "bluetooth"

    def test_protocol_wifi_beyond_50m(self):
        """Links > 50 m and ≤ max_range should be labelled 'wifi'."""
        nodes = self._nearby_cluster(2, sep_m=80.0)
        G = build_offline_mesh(nodes, max_range_meters=100)
        _, _, data = next(iter(G.edges(data=True)))
        assert data["protocol"] == "wifi"


# ─── Test: MeshNetworkAnalyser ────────────────────────────────────────────────

class TestMeshNetworkAnalyser:
    def _build_star(self) -> nx.Graph:
        """Node 100 (rescue) in the centre, 5 leaf nodes."""
        nodes = [
            _node(100, _BASE_LAT, _BASE_LNG, is_rescue_team=True),
        ]
        delta = 40.0 / _M_PER_DEG_LAT
        for i in range(1, 6):
            nodes.append(_node(i, _BASE_LAT + i * delta, _BASE_LNG))
        return build_offline_mesh(nodes, max_range_meters=200)

    def test_rescue_node_id(self):
        G = self._build_star()
        ana = MeshNetworkAnalyser(G)
        assert ana.rescue_node_id() == 100

    def test_rescue_path_found(self):
        G = self._build_star()
        ana = MeshNetworkAnalyser(G)
        result = ana.rescue_path(1)
        assert result["found"] is True
        assert result["path"][-1] == 100

    def test_rescue_path_not_found_when_isolated(self):
        """An isolated node cannot reach the rescue portal."""
        nodes = [
            _node(100, _BASE_LAT, _BASE_LNG, is_rescue_team=True),
            _node(1,   _BASE_LAT + 0.05, _BASE_LNG),  # 5.5 km away
        ]
        G = build_offline_mesh(nodes, max_range_meters=100)
        ana = MeshNetworkAnalyser(G)
        result = ana.rescue_path(1)
        assert result["found"] is False

    def test_density_zero_no_edges(self):
        """Completely disconnected graph has density 0."""
        nodes = [_node(i, _BASE_LAT + i * 0.05, _BASE_LNG) for i in range(3)]
        G = build_offline_mesh(nodes, max_range_meters=1)  # too small for edges
        ana = MeshNetworkAnalyser(G)
        assert ana.density() == 0.0

    def test_isolated_nodes_detected(self):
        nodes = [_node(i, _BASE_LAT + i * 0.05, _BASE_LNG) for i in range(3)]
        G = build_offline_mesh(nodes, max_range_meters=1)
        ana = MeshNetworkAnalyser(G)
        assert len(ana.isolated_nodes()) == 3

    def test_summary_contains_node_count(self):
        G = self._build_star()
        ana = MeshNetworkAnalyser(G)
        summary = ana.summary()
        assert "6" in summary  # 6 nodes in star

    def test_weakest_links_length(self):
        G = self._build_star()
        ana = MeshNetworkAnalyser(G)
        links = ana.weakest_links(3)
        assert len(links) <= 3
        # Sorted descending by distance
        distances = [l["distance_m"] for l in links]
        assert distances == sorted(distances, reverse=True)


# ─── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import traceback

    test_classes = [
        TestMeshNodeProjection,
        TestCalculateDistance,
        TestBuildOfflineMesh,
        TestMeshNetworkAnalyser,
    ]

    passed = 0
    failed = 0

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        for method_name in methods:
            label = f"{cls.__name__}.{method_name}"
            try:
                getattr(instance, method_name)()
                print(f"  PASS  {label}")
                passed += 1
            except Exception:
                print(f"  FAIL  {label}")
                traceback.print_exc()
                failed += 1

    print(f"\n{'-'*40}")
    print(f"  {passed} passed  |  {failed} failed")
    if failed:
        sys.exit(1)
