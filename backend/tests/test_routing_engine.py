"""
backend/tests/test_routing_engine.py
======================================
Unit tests for routing_engine.py — battery-prioritised Dijkstra routing
with AES-256-GCM end-to-end payload encryption.

Run with:
    cd backend
    python -m pytest tests/test_routing_engine.py -v
    # or, without pytest:
    python tests/test_routing_engine.py
"""

from __future__ import annotations

import sys
import os

# Allow importing from backend/ regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import networkx as nx
from simulation import MeshNode, build_offline_mesh, _BASE_LAT, _BASE_LNG, _M_PER_DEG_LAT
from routing_engine import (
    RoutingEngine,
    HopPacket,
    decrypt_emergency_payload,
    encrypt_emergency_payload,
    generate_session_key,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _node(nid: int, lat: float, lng: float, battery: int = 80, **kwargs) -> MeshNode:
    return MeshNode(
        id=nid,
        citizen_name=f"Test Citizen {nid}",
        lat=lat,
        lng=lng,
        battery_percentage=battery,
        **kwargs,
    )


def _build_chain(n: int = 5, sep_m: float = 40.0, rescue_id: int = 100) -> nx.Graph:
    """
    Build a linear chain: nodes 1 → 2 → … → (n-1) → rescue_id.
    All nodes are within sep_m metres of their neighbours.
    """
    delta = sep_m / _M_PER_DEG_LAT
    nodes = [_node(i + 1, _BASE_LAT + i * delta, _BASE_LNG) for i in range(n - 1)]
    # Rescue node directly adjacent to the last peer node
    nodes.append(
        _node(rescue_id, _BASE_LAT + (n - 1) * delta, _BASE_LNG, is_rescue_team=True)
    )
    return build_offline_mesh(nodes, max_range_meters=sep_m * 1.5)


# ─── Test: Key generation ─────────────────────────────────────────────────────

class TestKeyGeneration:
    def test_key_is_32_bytes(self):
        key = generate_session_key()
        assert len(key) == 32

    def test_keys_are_unique(self):
        assert generate_session_key() != generate_session_key()

    def test_engine_generate_key_alias(self):
        key = RoutingEngine.generate_key()
        assert len(key) == 32


# ─── Test: encrypt / decrypt round-trip ──────────────────────────────────────

class TestEncryptDecrypt:
    def test_roundtrip(self):
        key = generate_session_key()
        msg = "SOS: 3 injured at Barangay 892"
        ct  = encrypt_emergency_payload(msg, key)
        assert decrypt_emergency_payload(ct, key) == msg

    def test_ciphertext_differs_from_plaintext(self):
        key = generate_session_key()
        msg = "Emergency"
        ct  = encrypt_emergency_payload(msg, key)
        assert ct != msg.encode()

    def test_nonce_prepended_12_bytes(self):
        """The first 12 bytes are the nonce; ciphertext follows."""
        key = generate_session_key()
        ct  = encrypt_emergency_payload("test", key)
        # Minimum length: 12 (nonce) + 0 (plaintext) + 16 (GCM tag) = 28
        assert len(ct) >= 28

    def test_same_message_produces_different_ciphertext(self):
        """Semantic security: fresh nonce each call."""
        key = generate_session_key()
        msg = "SOS"
        assert encrypt_emergency_payload(msg, key) != encrypt_emergency_payload(msg, key)

    def test_wrong_key_raises(self):
        from cryptography.exceptions import InvalidTag
        key1 = generate_session_key()
        key2 = generate_session_key()
        ct   = encrypt_emergency_payload("secret", key1)
        raised = False
        try:
            decrypt_emergency_payload(ct, key2)
        except InvalidTag:
            raised = True
        assert raised, "Expected InvalidTag when decrypting with a wrong key"


# ─── Test: RoutingEngine.calculate_ai_routing_path ───────────────────────────

class TestRoutingEngine:
    def test_success_path_found(self):
        graph  = _build_chain(n=5)
        engine = RoutingEngine(graph, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1)
        assert result["status"] == "Success"
        assert result["path_taken"][-1] == 100

    def test_path_starts_at_source(self):
        graph  = _build_chain(n=5)
        engine = RoutingEngine(graph, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1)
        assert result["path_taken"][0] == 1

    def test_total_hops_matches_path(self):
        graph  = _build_chain(n=5)
        engine = RoutingEngine(graph, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1)
        assert result["total_hops"] == len(result["path_taken"]) - 1

    def test_failed_source_not_in_graph(self):
        graph  = _build_chain(n=5)
        engine = RoutingEngine(graph, rescue_node_id=100)
        result = engine.calculate_ai_routing_path(source_node_id=999)
        assert result["status"] == "Failed"

    def test_failed_rescue_not_in_graph(self):
        graph  = _build_chain(n=3, rescue_id=100)
        engine = RoutingEngine(graph, rescue_node_id=999)
        result = engine.calculate_ai_routing_path(source_node_id=1)
        assert result["status"] == "Failed"

    def test_failed_empty_graph(self):
        engine = RoutingEngine(nx.Graph(), rescue_node_id=100)
        result = engine.calculate_ai_routing_path(source_node_id=1)
        assert result["status"] == "Failed"

    def test_failed_no_path(self):
        """Two disconnected sub-graphs — no path exists."""
        delta = 300.0 / _M_PER_DEG_LAT   # 300 m apart, well outside range
        nodes = [
            _node(1,   _BASE_LAT,         _BASE_LNG),
            _node(100, _BASE_LAT + delta, _BASE_LNG, is_rescue_team=True),
        ]
        graph  = build_offline_mesh(nodes, max_range_meters=50)
        engine = RoutingEngine(graph, rescue_node_id=100)
        result = engine.calculate_ai_routing_path(source_node_id=1)
        assert result["status"] == "Failed"
        assert "Mesh chain broken" in result["message"]

    def test_total_weight_positive(self):
        graph  = _build_chain(n=4)
        engine = RoutingEngine(graph, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1)
        assert result["total_weight"] > 0

    def test_session_key_returned(self):
        key    = generate_session_key()
        graph  = _build_chain(n=4)
        engine = RoutingEngine(graph, session_key=key, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1)
        assert result["session_key"] == key


# ─── Test: hop encryption ─────────────────────────────────────────────────────

class TestHopEncryption:
    def test_one_packet_per_hop_node(self):
        graph  = _build_chain(n=4)
        engine = RoutingEngine(graph, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(
            source_node_id=1, message="SOS: flood in Sector 7"
        )
        assert result["status"] == "Success"
        path   = result["path_taken"]
        hops   = result["encrypted_hops"]
        assert len(hops) == len(path)

    def test_hop_packets_are_hop_packet_instances(self):
        graph  = _build_chain(n=4)
        engine = RoutingEngine(graph, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1, message="SOS")
        for hop in result["encrypted_hops"]:
            assert isinstance(hop, HopPacket)

    def test_hop_node_ids_match_path(self):
        graph  = _build_chain(n=4)
        engine = RoutingEngine(graph, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1, message="SOS")
        path   = result["path_taken"]
        hops   = result["encrypted_hops"]
        for i, hop in enumerate(hops):
            assert hop.node_id == path[i]
            assert hop.hop_index == i

    def test_payload_decryptable_at_rescue_node(self):
        """The rescue camp can decrypt the last hop's payload."""
        msg    = "SOS: 3 injured at Barangay 892"
        key    = generate_session_key()
        graph  = _build_chain(n=4)
        engine = RoutingEngine(graph, session_key=key, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1, message=msg)
        last_hop = result["encrypted_hops"][-1]
        assert decrypt_emergency_payload(last_hop.encrypted_payload, key) == msg

    def test_each_hop_independently_decryptable(self):
        """Every hop's ciphertext decrypts to the original message."""
        msg    = "Emergency payload"
        key    = generate_session_key()
        graph  = _build_chain(n=4)
        engine = RoutingEngine(graph, session_key=key, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1, message=msg)
        for hop in result["encrypted_hops"]:
            assert decrypt_emergency_payload(hop.encrypted_payload, key) == msg

    def test_hop_payloads_are_unique(self):
        """Each hop re-encrypts with a fresh nonce — ciphertexts differ."""
        graph  = _build_chain(n=4)
        engine = RoutingEngine(graph, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1, message="SOS")
        payloads = [hop.encrypted_payload for hop in result["encrypted_hops"]]
        # All ciphertexts should be distinct (fresh nonces)
        assert len(set(payloads)) == len(payloads)

    def test_no_hops_when_message_empty(self):
        """Empty message -> no HopPackets generated."""
        graph  = _build_chain(n=4)
        engine = RoutingEngine(graph, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1, message="")
        assert result["encrypted_hops"] == []


# ─── Test: battery-priority routing ──────────────────────────────────────────

class TestBatteryPriorityRouting:
    def test_prefers_higher_battery_relay(self):
        """
        Three-node topology: source(1) → low-battery relay(2) → rescue(100)
                                       → high-battery relay(3) → rescue(100)
        The engine must choose the path through the high-battery relay.

        Topology (all within range):
            1 — 2 (battery=5%) — 100
            1 — 3 (battery=95%) — 100
        """
        delta = 30.0 / _M_PER_DEG_LAT  # 30 m spacing

        # Place nodes so 1-2-100 and 1-3-100 are both reachable
        n1  = _node(1,   _BASE_LAT,             _BASE_LNG,          battery=90)
        n2  = _node(2,   _BASE_LAT + delta,     _BASE_LNG,          battery=5)
        n3  = _node(3,   _BASE_LAT,             _BASE_LNG + delta,  battery=95)
        n100 = _node(100, _BASE_LAT + delta,     _BASE_LNG + delta,
                     battery=100, is_rescue_team=True)

        graph  = build_offline_mesh([n1, n2, n3, n100], max_range_meters=60)
        engine = RoutingEngine(graph, rescue_node_id=100, packet_loss_rate=0.0)
        result = engine.calculate_ai_routing_path(source_node_id=1)

        assert result["status"] == "Success"
        # Low-battery node 2 should NOT appear in the chosen path
        assert 2 not in result["path_taken"], (
            f"Engine routed through critically low-battery node 2: {result['path_taken']}"
        )


# ─── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import traceback

    test_classes = [
        TestKeyGeneration,
        TestEncryptDecrypt,
        TestRoutingEngine,
        TestHopEncryption,
        TestBatteryPriorityRouting,
    ]

    passed = 0
    failed = 0

    for cls in test_classes:
        instance = cls()
        methods  = [m for m in dir(instance) if m.startswith("test_")]
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

    print(f"\n{'-' * 40}")
    print(f"  {passed} passed  |  {failed} failed")
    if failed:
        sys.exit(1)
