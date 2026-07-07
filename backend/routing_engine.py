"""
MeshNet AI — routing_engine.py
================================
AI-powered, battery-prioritised Dijkstra routing with AES-256-GCM
end-to-end payload encryption for the offline device-chain mesh.

This module is the direct implementation of the IBM Bob AI routing
specification:

    "Write a Python function using a modified Dijkstra's Shortest Path
     Algorithm that calculates the optimal data packet routing from a
     custom Node ID to the Rescue Camp Node (Node #100).  The path must
     prioritize nodes with higher battery percentages and dynamically
     encrypt the text payload using AES-256 before hopping to the next
     node."

Design decisions
----------------
* AES-256-GCM (via ``cryptography``) instead of Fernet:
    - Fernet uses AES-128-CBC + HMAC-SHA256.  AES-256-GCM is the
      field-deployment standard, provides authenticated encryption (no
      separate HMAC needed), and the key size matches the spec.
    - A fresh 96-bit random IV is prepended to every ciphertext, so
      repeated encryptions of the same payload produce different outputs
      (semantic security).

* Battery-cost edge weight:
    - Edge cost = base_distance_cost + battery_penalty
    - battery_penalty = (100 - min(battery_a, battery_b)) / 10
    - This makes Dijkstra prefer paths through nodes with *higher*
      battery — weaker-battery nodes become "more expensive" to route
      through, reducing risk of a relay dying mid-transmission.

* Hop-by-hop re-encryption:
    - ``route_and_encrypt`` returns a ``HopPacket`` per relay node so
      the payload is re-encrypted at every hop boundary.  Each hop uses
      the same session key so only the final destination (rescue portal)
      can decrypt the payload with ``decrypt_emergency_payload``.

Usage
-----
    from routing_engine import RoutingEngine, encrypt_emergency_payload, decrypt_emergency_payload

    # One-time session key — share out-of-band with rescue base camp
    key = RoutingEngine.generate_key()

    engine = RoutingEngine(mesh_graph, session_key=key)
    result = engine.calculate_ai_routing_path(source_node_id=42)

    if result["status"] == "Success":
        for hop in result["encrypted_hops"]:
            print(hop)

Integration
-----------
    from simulation import build_offline_mesh, load_from_db
    from routing_engine import RoutingEngine

    nodes  = load_from_db()
    graph  = build_offline_mesh(nodes, max_range_meters=100)
    engine = RoutingEngine(graph)
    result = engine.calculate_ai_routing_path(source_node_id=1)
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass, field
from typing import Any, Optional

import networkx as nx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import PACKET_LOSS_RATE

log = logging.getLogger(__name__)

# Rescue camp node ID — spec §: "target=Node #100 (Rescue Camp)"
_RESCUE_NODE_ID: int = 100

# AES-256 requires a 32-byte (256-bit) key
_AES_KEY_BYTES: int = 32

# GCM nonce length (96-bit is the recommended standard)
_GCM_NONCE_BYTES: int = 12


# ─── Key management ───────────────────────────────────────────────────────────

def generate_session_key() -> bytes:
    """
    Generate a cryptographically random 256-bit AES session key.

    The returned bytes object must be shared securely (out-of-band) with
    the rescue base camp node before a transmission begins — it is the
    only key that can decrypt the final ciphertext.

    Returns
    -------
    bytes
        32 random bytes suitable for AES-256-GCM.
    """
    return os.urandom(_AES_KEY_BYTES)


# ─── Payload encryption / decryption ─────────────────────────────────────────

def encrypt_emergency_payload(message_text: str, session_key: bytes) -> bytes:
    """
    Encrypt an SOS message so intermediate relay devices cannot read it.

    Uses AES-256-GCM authenticated encryption.  A fresh 96-bit random
    nonce is prepended to the ciphertext so that every call produces a
    different output even for identical plaintext.

    Parameters
    ----------
    message_text : str
        The plaintext SOS payload (e.g. "SOS: 3 injured at Barangay 892").
    session_key : bytes
        32-byte AES-256 session key shared with the rescue base camp.

    Returns
    -------
    bytes
        ``nonce (12 bytes) || ciphertext+tag`` — safe to transmit over
        the mesh without exposing the plaintext to relay nodes.
    """
    aesgcm = AESGCM(session_key)
    nonce = os.urandom(_GCM_NONCE_BYTES)
    ciphertext = aesgcm.encrypt(nonce, message_text.encode(), None)
    return nonce + ciphertext


def decrypt_emergency_payload(encrypted_payload: bytes, session_key: bytes) -> str:
    """
    Decrypt a payload at the Rescue Team Base Camp Node.

    Parameters
    ----------
    encrypted_payload : bytes
        Output of ``encrypt_emergency_payload`` — ``nonce || ciphertext+tag``.
    session_key : bytes
        The same 32-byte AES-256 session key used for encryption.

    Returns
    -------
    str
        Original plaintext SOS message.

    Raises
    ------
    cryptography.exceptions.InvalidTag
        If the ciphertext has been tampered with or the wrong key is used.
    """
    aesgcm = AESGCM(session_key)
    nonce = encrypted_payload[:_GCM_NONCE_BYTES]
    ciphertext = encrypted_payload[_GCM_NONCE_BYTES:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode()


# ─── Data contracts ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HopPacket:
    """
    Represents an encrypted data packet at a single relay hop.

    Fields
    ------
    hop_index : int
        0-based position in the path (0 = source node).
    node_id : Any
        ID of the relay node holding this packet.
    encrypted_payload : bytes
        AES-256-GCM encrypted payload at this hop.
    """
    hop_index: int
    node_id: Any
    encrypted_payload: bytes

    def __repr__(self) -> str:
        return (
            f"HopPacket(hop={self.hop_index}, "
            f"node={self.node_id!r}, "
            f"payload_bytes={len(self.encrypted_payload)})"
        )


# ─── Routing Engine ───────────────────────────────────────────────────────────

class RoutingEngine:
    """
    AI-powered battery-prioritised Dijkstra routing with AES-256-GCM
    end-to-end payload encryption.

    Parameters
    ----------
    mesh_graph : nx.Graph
        The offline mesh graph built by ``simulation.build_offline_mesh``.
        Node attributes must include a ``battery`` key (int 0-100).
    session_key : bytes | None
        32-byte AES-256-GCM session key.  If ``None``, a fresh key is
        generated automatically via ``generate_session_key()``.
    rescue_node_id : int | str
        ID of the rescue camp target node (default: 100).
    packet_loss_rate : float
        Per-hop probability of a single transmission attempt being dropped
        (default: from config.py).
    max_retries : int
        Number of retransmission attempts per hop before giving up (default: 1).
        BLE mesh protocols automatically retry failed hops; setting this to 3
        models the real-world ARQ (Automatic Repeat reQuest) behaviour where
        the effective per-hop drop rate drops to loss_rate^max_retries.
    """

    def __init__(
        self,
        mesh_graph: nx.Graph,
        session_key: Optional[bytes] = None,
        rescue_node_id: Any = _RESCUE_NODE_ID,
        packet_loss_rate: float = PACKET_LOSS_RATE,
        max_retries: int = 1,
    ) -> None:
        self._graph = mesh_graph
        self._session_key = session_key or generate_session_key()
        self._rescue_node_id = rescue_node_id
        self._packet_loss_rate = packet_loss_rate
        self._max_retries = max_retries

    # ── Class helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def generate_key() -> bytes:
        """Convenience alias for ``generate_session_key()``."""
        return generate_session_key()

    # ── Public API ────────────────────────────────────────────────────────────

    def calculate_ai_routing_path(
        self,
        source_node_id: Any,
        message: str = "",
        rescue_node_id: Optional[Any] = None,
    ) -> dict:
        """
        Compute the optimal battery-prioritised path from *source_node_id*
        to the rescue camp node and encrypt the payload at every hop.

        Algorithm
        ---------
        1.  Build a battery-aware weight graph:
                edge_cost = distance_cost + battery_penalty
                battery_penalty = (100 - min(battery_a, battery_b)) / 10
            Lower-battery relays become more expensive so Dijkstra avoids
            routing through nodes that may die mid-transmission.
        2.  Run ``nx.dijkstra_path`` on the weighted graph.
        3.  Encrypt ``message`` with AES-256-GCM once per hop, producing
            a ``HopPacket`` list so each relay re-transmits a freshly
            encrypted blob.

        Parameters
        ----------
        source_node_id : int | str
            Originating node — the citizen sending the SOS.
        message : str
            Plaintext SOS payload to encrypt and route.
        rescue_node_id : int | str | None
            Override the default rescue target (node 100).

        Returns
        -------
        dict
            On success::

                {
                    "status":          "Success",
                    "path_taken":      [node_id, ...],
                    "total_hops":      int,
                    "total_weight":    float,
                    "encrypted_hops":  [HopPacket, ...],
                    "session_key":     bytes,   # share securely with rescue camp
                }

            On failure::

                {
                    "status":  "Failed",
                    "message": str,
                }
        """
        target = rescue_node_id if rescue_node_id is not None else self._rescue_node_id

        # ── Guard: graph not empty ────────────────────────────────────────────
        if self._graph.number_of_nodes() == 0:
            return {
                "status":  "Failed",
                "message": "Mesh graph is empty — no nodes loaded.",
            }

        # ── Guard: source and target must exist ───────────────────────────────
        for node_id, role in ((source_node_id, "source"), (target, "rescue target")):
            if node_id not in self._graph:
                return {
                    "status":  "Failed",
                    "message": (
                        f"Mesh chain broken — {role} node {node_id!r} not found. "
                        "Searching for alternative physical paths."
                    ),
                }

        # ── Build battery-aware weighted view ─────────────────────────────────
        weighted = self._build_battery_weighted_graph()

        # ── Dijkstra ──────────────────────────────────────────────────────────
        try:
            optimal_path: list = nx.dijkstra_path(
                weighted, source_node_id, target, weight="weight"
            )
            total_weight: float = nx.dijkstra_path_length(
                weighted, source_node_id, target, weight="weight"
            )
        except nx.NetworkXNoPath:
            return {
                "status":  "Failed",
                "message": (
                    f"Mesh chain broken — no path from node {source_node_id!r} "
                    f"to rescue camp (node {target!r}). "
                    "Searching for alternative physical paths."
                ),
            }
        except nx.NodeNotFound as exc:
            return {"status": "Failed", "message": str(exc)}

        # ── Per-hop packet-loss simulation with retransmission (ARQ) ─────────
        # Each relay hop has an independent chance of dropping the packet
        # (modelling real BLE/Wi-Fi interference).  The engine simulates
        # BLE Automatic Repeat reQuest: each hop is attempted up to
        # max_retries times before the packet is declared lost.
        # Effective per-hop drop = loss_rate ^ max_retries.
        hops_count = len(optimal_path) - 1
        for hop_idx in range(hops_count):
            hop_delivered = False
            for attempt in range(self._max_retries):
                if random.random() >= self._packet_loss_rate:
                    hop_delivered = True
                    break
            if not hop_delivered:
                log.warning(
                    "Simulated packet drop at hop %d/%d after %d attempts (loss_rate=%.0f%%)",
                    hop_idx + 1, hops_count, self._max_retries,
                    self._packet_loss_rate * 100,
                )
                return {
                    "status":   "Dropped",
                    "message":  (
                        f"Packet dropped at hop {hop_idx + 1}/{hops_count} "
                        f"after {self._max_retries} attempt(s) "
                        f"(simulated {self._packet_loss_rate * 100:.0f}% per-hop loss rate). "
                        "Caller should retry or reroute."
                    ),
                    "path_taken":   optimal_path,
                    "drop_hop":     hop_idx + 1,
                    "total_hops":   hops_count,
                    "total_weight": round(total_weight, 4),
                }

        # ── Hop-by-hop payload encryption ─────────────────────────────────────
        hops = self._encrypt_hops(optimal_path, message)

        log.info(
            "AI route %r→%r: %d hops, weight=%.2f",
            source_node_id, target, len(optimal_path) - 1, total_weight,
        )

        return {
            "status":         "Success",
            "path_taken":     optimal_path,
            "total_hops":     len(optimal_path) - 1,
            "total_weight":   round(total_weight, 4),
            "encrypted_hops": hops,
            "session_key":    self._session_key,  # share out-of-band with rescue camp
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_battery_weighted_graph(self) -> nx.Graph:
        """
        Return a copy of the mesh graph with battery-penalised edge weights.

        For every edge (u, v) the new weight is:

            base_cost     = original distance weight / 10   (normalise to 0-10)
            battery_min   = min(battery_u, battery_v)       (weakest link)
            bat_penalty   = (100 - battery_min) / 10        (0 best, 10 worst)
            new_weight    = base_cost + bat_penalty + 1     (floor at 1)

        This makes Dijkstra favour paths through high-battery nodes.
        """
        weighted = self._graph.__class__()
        weighted.add_nodes_from(self._graph.nodes(data=True))

        for u, v, edge_data in self._graph.edges(data=True):
            base_dist = edge_data.get("weight", edge_data.get("distance", 10.0))
            base_cost = base_dist / 10.0

            bat_u = self._graph.nodes[u].get("battery", 100)
            bat_v = self._graph.nodes[v].get("battery", 100)
            bat_penalty = (100 - min(bat_u, bat_v)) / 10.0

            new_weight = base_cost + bat_penalty + 1.0
            weighted.add_edge(u, v, **{**edge_data, "weight": new_weight})

        return weighted

    def _encrypt_hops(self, path: list, message: str) -> list[HopPacket]:
        """
        Encrypt the payload once per relay node along the path.

        Each hop re-encrypts the payload with a fresh nonce so that
        relay nodes only ever see their own encrypted blob — not the
        complete transmission history.

        Parameters
        ----------
        path : list
            Ordered list of node IDs from source to rescue camp.
        message : str
            Plaintext SOS payload (may be empty string).

        Returns
        -------
        list[HopPacket]
            One packet per node in path.
        """
        if not message:
            return []

        packets: list[HopPacket] = []
        for idx, node_id in enumerate(path):
            encrypted = encrypt_emergency_payload(message, self._session_key)
            packets.append(HopPacket(
                hop_index=idx,
                node_id=node_id,
                encrypted_payload=encrypted,
            ))

        return packets
