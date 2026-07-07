"""
MeshNet-AI — tests/test_routing.py
===================================
Unit tests for routing.py — runnable with plain ``python -m pytest``,
no Android runtime required.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from routing import (
    RoutingEngine, MeshNode, mock_topology,
    BATTERY_THRESHOLD, W_BATTERY, W_WEATHER_HQ, W_DEVICE,
    _haversine,
)


# ── _haversine ─────────────────────────────────────────────────────────────────

def test_haversine_same_point():
    assert _haversine(34.0, -118.0, 34.0, -118.0) == pytest.approx(0.0, abs=1e-6)

def test_haversine_known_distance():
    # LAX → JFK ≈ 3983 km
    d = _haversine(33.9425, -118.4081, 40.6413, -73.7781)
    assert 3900 < d < 4100


# ── filter_stable ──────────────────────────────────────────────────────────────

def test_filter_removes_low_battery():
    nodes  = [
        MeshNode("N1", battery_level=10.0, is_active=True),   # filtered
        MeshNode("N2", battery_level=16.0, is_active=True),   # kept
        MeshNode("N3", battery_level=15.0, is_active=True),   # filtered (not >)
    ]
    engine = RoutingEngine()
    stable = engine._filter_stable(nodes)
    assert len(stable) == 1
    assert stable[0].node_id == "N2"

def test_filter_removes_inactive():
    nodes = [MeshNode("N1", battery_level=80.0, is_active=False)]
    assert RoutingEngine._filter_stable(nodes) == []


# ── score_node ─────────────────────────────────────────────────────────────────

def test_score_hq_node_dominates():
    hq_node   = MeshNode("HQ",  battery_level=50.0, is_active=True,
                          device_type="unknown", has_weather_hq_signal=True)
    base_node = MeshNode("BASE",battery_level=99.0, is_active=True,
                          device_type="gateway", has_weather_hq_signal=False)
    hq_node.routing_score   = RoutingEngine._score_node(hq_node)
    base_node.routing_score = RoutingEngine._score_node(base_node)
    # HQ bonus (0.50) should make the HQ node win despite lower battery
    assert hq_node.routing_score > base_node.routing_score

def test_score_range():
    for node in mock_topology():
        s = RoutingEngine._score_node(node)
        assert 0.0 <= s <= 1.0, f"Score out of range for {node.node_id}: {s}"


# ── full compute pipeline ──────────────────────────────────────────────────────

def test_compute_filters_correctly():
    engine = RoutingEngine()
    result = engine.compute(mock_topology())
    # mock_topology has 12 nodes:
    #   NODE-C3  battery=11  (below threshold)  ← filtered
    #   NODE-E5  inactive                        ← filtered
    #   NODE-H8  battery=8   (below threshold)  ← filtered
    # Total filtered = 3
    assert result.rejected_count == 3
    assert len(result.stable_nodes) == 9

def test_compute_path_non_empty():
    engine = RoutingEngine()
    result = engine.compute(mock_topology())
    assert len(result.optimal_path) > 0

def test_compute_hq_anchor_set():
    engine = RoutingEngine()
    result = engine.compute(mock_topology())
    # mock topology has 2 HQ nodes
    assert result.hq_anchor is not None

def test_compute_path_quality_in_range():
    engine = RoutingEngine()
    result = engine.compute(mock_topology())
    assert 0.0 <= result.path_quality <= 1.0

def test_compute_empty_input():
    engine = RoutingEngine()
    result = engine.compute([])
    assert result.stable_nodes   == []
    assert result.optimal_path   == []
    assert result.path_quality   == 0.0
    assert result.rejected_count == 0
