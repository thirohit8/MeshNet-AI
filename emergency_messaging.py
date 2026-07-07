"""
MeshNet-AI — emergency_messaging.py
=====================================
Offline Emergency Messaging CLI Interface.

This module is the standalone CLI entry-point for the broadcast engine.
It wraps the production ``messaging.BroadcastEngine`` and
``messaging.HandshakeLogger`` with a synchronous console harness so the
broadcast simulation can be run directly from a terminal (or from
launcher.py) without importing the full Kivy/KivyMD stack.

Architecture
------------
                    emergency_messaging.py   (this file)
                           │
                           ▼
              messaging.BroadcastEngine / HandshakeLogger
                           │
               (threaded hop-by-hop simulation, 1 s/hop)
                           │
                           ▼
                  logs/handshake_log.enc
              (XOR-encrypted, base64-encoded JSON array)

Usage
-----
    python3 emergency_messaging.py                  # broadcasts on mock topology
    python3 emergency_messaging.py --scenario Flood
    python3 emergency_messaging.py --read-log        # decrypt and print all logs
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from datetime import datetime

# ── Production engine imports ─────────────────────────────────────────────────
# Defer Kivy import guard: messaging.py imports kivy.clock, which requires
# a display connection on some systems.  We mock Clock for CLI use.
import os

# Kivy environment variable — suppress display initialisation in pure CLI mode
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")
# Prevent Kivy from trying to open a window in headless/terminal mode
os.environ.setdefault("DISPLAY", ":0")

from messaging import BroadcastEngine, HandshakeLogger, SOSPacket
from core_router import MeshNetRouter
from nodes_mock import simulated_network
import config


# ── Console broadcast harness ─────────────────────────────────────────────────

class ConsoleBroadcast:
    """
    Synchronous console wrapper around BroadcastEngine.

    Because BroadcastEngine schedules GUI callbacks via ``kivy.clock``,
    which is unavailable in a headless terminal, this class replaces
    those callbacks with thread-safe ``print()`` calls.
    """

    def __init__(self, scenario: str = "Flood") -> None:
        self.scenario   = scenario
        self._done      = threading.Event()
        self._success   = False
        self._hs_logger = HandshakeLogger()
        self._engine    = BroadcastEngine(self._hs_logger)

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self, message: str = "") -> bool:
        """
        Build a routing path for *scenario*, construct an SOSPacket, and
        simulate the hop-by-hop broadcast in the foreground.

        Returns True if all hops succeeded.
        """
        # Resolve routing path
        router = MeshNetRouter(simulated_network, self.scenario)
        result = router.compute_full_result()

        if not result.optimal_path:
            print("[CRITICAL] No stable route found — broadcast aborted.")
            return False

        path = result.optimal_path
        if not message:
            message = (
                f"[{self.scenario.upper()}] EMERGENCY SOS — MeshNet-AI node. "
                f"Path quality: {result.path_quality:.2%}. "
                f"HQ anchor: {result.hq_anchor or 'none'}."
            )

        packet = SOSPacket(
            scenario    = self.scenario,
            message     = message,
            origin_node = path[0],
            path        = path,
        )

        self._print_header(packet, result)
        self._done.clear()

        # Patch Clock.schedule_once to a direct call in this headless context
        self._engine.broadcast(
            packet,
            on_hop      = self._on_hop,
            on_complete = self._on_complete,
        )

        # Block until broadcast thread finishes (or times out after 60 s)
        self._done.wait(timeout=60.0)
        self._print_footer()
        return self._success

    def read_logs(self) -> None:
        """Decrypt and pretty-print all stored handshake log entries."""
        records = self._hs_logger.read_all()
        if not records:
            print("[INFO] No handshake log entries found.")
            return

        print(f"\n{'='*60}")
        print(f"  MeshNet-AI — Encrypted Handshake Log  ({len(records)} records)")
        print(f"{'='*60}")
        for i, rec in enumerate(records, 1):
            print(f"\n  [{i}] Packet   : {rec.get('packet_id', 'N/A')}")
            print(f"       Scenario  : {rec.get('scenario', 'N/A')}")
            print(f"       Origin    : {rec.get('origin_node', 'N/A')}")
            print(f"       Timestamp : {rec.get('created_at', 'N/A')}")
            hops = rec.get("path", [])
            print(f"       Hops ({len(hops):2d}) : {' → '.join(hops)}")
            print(f"       Message   : {rec.get('message', '')[:80]}")
        print()

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _print_header(packet: SOSPacket, result) -> None:
        print()
        print("=" * 60)
        print("   MeshNet-AI  |  OFFLINE DISASTER MESSAGING ENGINE")
        print("=" * 60)
        print(f"  Packet ID  : {packet.packet_id}")
        print(f"  Scenario   : {packet.scenario}")
        print(f"  Origin     : {packet.origin_node}")
        print(f"  Path hops  : {len(packet.path)}")
        print(f"  Quality    : {result.path_quality:.2%}")
        print(f"  HQ anchor  : {result.hq_anchor or 'none'}")
        print(f"  Message    : {packet.message[:70]}")
        print("=" * 60)
        print(f"  [BROADCAST START]  {datetime.now().strftime('%H:%M:%S')}")
        print("-" * 60)

    def _on_hop(self, hop_idx: int, node_id: str, status: str) -> None:
        """Called from the broadcast thread — print directly (no Kivy Clock)."""
        if status == "TX":
            print(f"  -> Hop #{hop_idx + 1:02d}  TX  →  {node_id}")
        else:
            print(f"     Hop #{hop_idx + 1:02d}  RX  ✔  {node_id}")

    def _on_complete(self, packet: SOSPacket, success: bool) -> None:
        self._success = success
        self._done.set()

    def _print_footer(self) -> None:
        print("-" * 60)
        if self._success:
            total = self._hs_logger.record_count()
            print(
                f"  [SUCCESS] SOS broadcast complete.  "
                f"Total logs stored: {total}"
            )
        else:
            print("  [ABORTED] Broadcast was interrupted.")
        print("=" * 60)
        print()


# ── Monkey-patch Clock for headless mode ──────────────────────────────────────
# BroadcastEngine uses kivy.clock.Clock.schedule_once to dispatch callbacks
# onto the main thread.  In CLI mode there is no Kivy event loop, so we
# replace it with a direct synchronous call.

def _patch_clock() -> None:
    """Replace kivy.clock.Clock.schedule_once with a direct-call stub."""
    try:
        from kivy import clock as _kivy_clock

        class _DirectClock:
            @staticmethod
            def schedule_once(callback, delay=0):
                callback(delay)

        _kivy_clock.Clock = _DirectClock()
        # Also patch the already-imported reference inside messaging.py
        import messaging
        messaging.Clock = _DirectClock()
    except Exception:
        pass   # If Kivy is unavailable, the broadcast thread will handle it


# ── Entry point ───────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="emergency_messaging",
        description="MeshNet-AI — Offline Emergency Messaging CLI",
    )
    parser.add_argument(
        "--scenario",
        default="Flood",
        choices=config.scenario_names(),
        help="Disaster scenario to simulate (default: Flood)",
    )
    parser.add_argument(
        "--message",
        default="",
        help="Custom SOS message text (auto-generated if omitted)",
    )
    parser.add_argument(
        "--read-log",
        action="store_true",
        help="Decrypt and display all stored handshake log entries, then exit",
    )
    return parser.parse_args()


if __name__ == "__main__":
    _patch_clock()
    args = _parse_args()

    harness = ConsoleBroadcast(scenario=args.scenario)

    if args.read_log:
        harness.read_logs()
        sys.exit(0)

    success = harness.run(message=args.message)
    sys.exit(0 if success else 1)
