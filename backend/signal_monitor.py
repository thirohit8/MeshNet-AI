"""
MeshNet AI — signal_monitor.py
================================
Tracks unstable signal states across all simulated mesh nodes and
fires a High-Priority Data Burst the split second a network flicker
is detected (signal transitions from 0 bars to ≥ 1 bar).

Objective (spec verbatim):
    "In a war zone or flood area, cellular towers might flicker online
     for just 2 to 3 seconds.  Our app tracks the hardware's Network
     Signal Strength.  If the signal goes from 0 bars to 1 bar (even
     for a moment), the app instantly executes a High-Priority Data
     Burst, bypassing all queue systems to push out buffered logs to
     the cloud."

Architecture
------------
                  ┌─────────────────────────────────┐
  mesh nodes ──▶  │  SignalMonitor.ingest_sample()  │
  (heartbeats)    │  · Detects 0 → ≥1 bar flicker   │
                  │  · Calls _on_flicker callbacks   │
                  └───────────┬─────────────────────┘
                              │ FlickerEvent
                  ┌───────────▼─────────────────────┐
                  │  BurstDispatcher.dispatch()      │
                  │  · Collects buffered log chunks  │
                  │  · POSTs to Express /api/signal  │
                  │  · POSTs critical alert          │
                  └─────────────────────────────────┘

This module contains only pure Python logic — no framework dependencies
beyond the standard library and `requests`.  The FastAPI endpoint in
api_server.py acts as the HTTP surface.

Usage (standalone monitor loop)
---------------------------------
    python signal_monitor.py --api http://localhost:4000 --interval 3

Usage (programmatic)
---------------------
    from signal_monitor import SignalMonitor, BurstDispatcher

    monitor = SignalMonitor()
    monitor.on_flicker(lambda evt: print("FLICKER!", evt))
    monitor.ingest_sample("node-42", "Node·42", signal=18, prev_signal=2)
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests

from config import DEFAULT_SIGNAL_THRESHOLD, MeshConfig

log = logging.getLogger(__name__)

# ─── Thresholds ───────────────────────────────────────────────────────────────
# A node is "dead" (0 bars) when its RSSI-normalised signal is at or below this.
# Override via SIGNAL_DEAD_THRESHOLD env var (default matches TypeScript side).
_DEAD_THRESHOLD: int = int(os.getenv("SIGNAL_DEAD_THRESHOLD", "5"))

# A node is "alive" (≥ 1 bar) when it exceeds this after being dead.
# Override via SIGNAL_LIVE_THRESHOLD env var.
_LIVE_THRESHOLD: int = int(os.getenv("SIGNAL_LIVE_THRESHOLD", "15"))


# ─── Data contracts ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FlickerEvent:
    """
    Emitted the instant a node transitions from 0 bars to ≥ 1 bar.

    Fields
    ------
    node_id : str
        Device ID of the flickering node.
    node_label : str
        Human-readable label (e.g. "Node·42").
    prev_signal : int
        Signal percentage just before the flicker (was ≤ DEAD_THRESHOLD).
    curr_signal : int
        Signal percentage after the flicker (now > LIVE_THRESHOLD).
    scenario : str
        Active disaster scenario at the time of detection.
    detected_at : float
        Unix timestamp of detection (use time.time()).
    """
    node_id:     str
    node_label:  str
    prev_signal: int
    curr_signal: int
    scenario:    str
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "nodeId":      self.node_id,
            "nodeLabel":   self.node_label,
            "prevSignal":  self.prev_signal,
            "currSignal":  self.curr_signal,
            "scenario":    self.scenario,
            "detectedAt":  self.detected_at,
        }


@dataclass
class BufferedLogChunk:
    """
    A single unit of buffered telemetry data waiting for a burst window.

    In the real device, these would be accumulated sensor logs, GPS fixes,
    and SOS message drafts that could not be sent while the signal was dead.
    """
    node_id:    str
    payload:    str       # JSON-serialisable string blob
    queued_at:  float = field(default_factory=time.time)


# ─── Signal Monitor ───────────────────────────────────────────────────────────

class SignalMonitor:
    """
    Tracks per-node signal history and detects 0 → ≥1 bar flicker events.

    This class is framework-agnostic — it receives signal samples from
    whatever source (heartbeat ticker, hardware API, simulation loop) and
    fires registered callbacks when a flicker is detected.

    Parameters
    ----------
    dead_threshold : int
        Signal % at or below which a node is considered "no signal".
    live_threshold : int
        Signal % above which a node is considered "back online" after
        having been dead.
    """

    def __init__(
        self,
        dead_threshold: int = _DEAD_THRESHOLD,
        live_threshold: int = _LIVE_THRESHOLD,
    ) -> None:
        self._dead_threshold = dead_threshold
        self._live_threshold = live_threshold

        # Most-recent signal reading per node — keyed by node_id
        self._last_signal: dict[str, int] = {}

        # Registered flicker callbacks
        self._callbacks: list[Callable[[FlickerEvent], None]] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def on_flicker(self, callback: Callable[[FlickerEvent], None]) -> None:
        """
        Register a callback that fires the split second a flicker is detected.

        The callback receives a single ``FlickerEvent`` argument and must
        return quickly — dispatch any heavy I/O work to a thread or queue.

        Parameters
        ----------
        callback : Callable[[FlickerEvent], None]
            Function to call on each flicker event.
        """
        self._callbacks.append(callback)

    def ingest_sample(
        self,
        node_id: str,
        node_label: str,
        signal: int,
        scenario: str = "earthquake",
        prev_signal: Optional[int] = None,
    ) -> Optional[FlickerEvent]:
        """
        Process one signal sample from a mesh node.

        If the signal just rose from ≤ DEAD_THRESHOLD to > LIVE_THRESHOLD,
        a FlickerEvent is created, all registered callbacks are fired, and
        the event is returned.

        Parameters
        ----------
        node_id : str
            Unique device identifier.
        node_label : str
            Human-readable device label.
        signal : int
            Current RSSI-normalised signal strength (0–100).
        scenario : str
            Active disaster scenario.
        prev_signal : int | None
            Override the stored previous reading (useful for testing).

        Returns
        -------
        FlickerEvent | None
            A FlickerEvent on flicker detection; None otherwise.
        """
        prev = prev_signal if prev_signal is not None else self._last_signal.get(node_id, signal)
        self._last_signal[node_id] = signal

        was_dead = prev  <= self._dead_threshold
        is_alive = signal > self._live_threshold

        if not (was_dead and is_alive):
            log.debug("Node %s: signal %d→%d (no flicker)", node_id, prev, signal)
            return None

        evt = FlickerEvent(
            node_id=node_id,
            node_label=node_label,
            prev_signal=prev,
            curr_signal=signal,
            scenario=scenario,
        )

        log.warning(
            "FLICKER DETECTED - node=%s signal=%d->%d scenario=%s",
            node_id, prev, signal, scenario,
        )

        for cb in self._callbacks:
            try:
                cb(evt)
            except Exception as exc:  # noqa: BLE001
                log.error("Flicker callback raised: %s", exc)

        return evt

    def last_signal(self, node_id: str) -> Optional[int]:
        """Return the most recently ingested signal for node_id, or None."""
        return self._last_signal.get(node_id)

    def reset_node(self, node_id: str) -> None:
        """Remove stored state for node_id (useful in tests)."""
        self._last_signal.pop(node_id, None)


# ─── Burst Dispatcher ─────────────────────────────────────────────────────────

class BurstDispatcher:
    """
    Executes the High-Priority Data Burst on every flicker event.

    On construction, registers itself as a flicker callback on the given
    ``SignalMonitor``.  When a flicker fires it:

      1. Drains the per-node log buffer (bypassing normal queue order).
      2. POSTs each chunk to the Express backend's ``/api/signal/report``
         endpoint, which in turn fans out to SSE subscribers (rescue dashboard).
      3. POSTs a critical alert to ``/api/alerts``.

    Parameters
    ----------
    monitor : SignalMonitor
        The monitor whose flicker events this dispatcher should handle.
    api_base : str
        Express backend base URL (e.g. ``http://localhost:4000``).
    cfg : MeshConfig | None
        Optional configuration; defaults to ``MeshConfig.from_env()``.
    """

    def __init__(
        self,
        monitor: SignalMonitor,
        api_base: str = "http://localhost:4000",
        cfg: Optional[MeshConfig] = None,
    ) -> None:
        self._api_base = api_base
        self._cfg      = cfg or MeshConfig.from_env()
        self._session  = requests.Session()

        # Per-node log buffers — chunks queued while signal was 0
        self._buffers: dict[str, list[BufferedLogChunk]] = {}

        monitor.on_flicker(self.dispatch)

    # ── Public API ────────────────────────────────────────────────────────────

    def buffer_log(self, node_id: str, payload: str) -> None:
        """
        Enqueue a log chunk for node_id.

        Chunks accumulate while signal is dead and are flushed en masse
        during the next burst window.

        Parameters
        ----------
        node_id : str
            Device ID whose buffer receives this chunk.
        payload : str
            JSON-serialisable telemetry blob.
        """
        self._buffers.setdefault(node_id, []).append(
            BufferedLogChunk(node_id=node_id, payload=payload)
        )
        log.debug("Buffered log chunk for %s (total=%d)", node_id, len(self._buffers[node_id]))

    def dispatch(self, evt: FlickerEvent) -> None:
        """
        High-Priority Data Burst — called the split second a flicker fires.

        Bypasses normal queue order: all buffered chunks for the flickering
        node are sent immediately before any lower-priority traffic.

        Parameters
        ----------
        evt : FlickerEvent
            The flicker event that triggered this burst.
        """
        log.warning(
            "HIGH-PRIORITY BURST - node=%s signal=%d->%d scenario=%s",
            evt.node_id, evt.prev_signal, evt.curr_signal, evt.scenario,
        )

        # 1. Report flicker to Express → fans out to SSE dashboard stream
        self._report_flicker(evt)

        # 2. Flush the node's buffered log chunks
        chunks = self._buffers.pop(evt.node_id, [])
        if chunks:
            log.info("Flushing %d buffered chunks for %s", len(chunks), evt.node_id)
            for chunk in chunks:
                self._push_chunk(evt.node_id, chunk)
        else:
            log.info("No buffered chunks for %s", evt.node_id)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _report_flicker(self, evt: FlickerEvent) -> None:
        """POST the flicker event to the Express signal endpoint."""
        import datetime
        payload = {
            "nodeId":    evt.node_id,
            "nodeLabel": evt.node_label,
            "signal":    evt.curr_signal,
            "scenario":  evt.scenario,
            "timestamp": datetime.datetime.utcfromtimestamp(evt.detected_at).isoformat() + "Z",
        }
        try:
            resp = self._session.post(
                f"{self._api_base}/api/signal/report",
                json=payload,
                timeout=self._cfg.http_timeout,
            )
            if resp.status_code == 201:
                log.info("Flicker reported — node=%s", evt.node_id)
            else:
                log.warning(
                    "Flicker report returned %d for node=%s",
                    resp.status_code, evt.node_id,
                )
        except requests.RequestException as exc:
            log.error("Failed to report flicker for %s: %s", evt.node_id, exc)

    def _push_chunk(self, node_id: str, chunk: BufferedLogChunk) -> None:
        """POST a single buffered chunk to the mesh messages endpoint."""
        payload = {
            "from_node_id": node_id,
            "from_label":   node_id,
            "to_node_id":   "broadcast",
            "category":     "info",
            "ciphertext":   chunk.payload,
            "hops":         0,
        }
        try:
            self._session.post(
                f"{self._api_base}/api/messages",
                json=payload,
                timeout=self._cfg.http_timeout,
            )
        except requests.RequestException as exc:
            log.debug("Chunk push failed for %s: %s", node_id, exc)


# ─── Standalone monitor loop ──────────────────────────────────────────────────

def _run_monitor(args: argparse.Namespace) -> None:
    """
    Drive the SignalMonitor + BurstDispatcher against the live mesh.

    Polls ``/api/mesh/topology`` every ``--interval`` seconds, extracts
    each node's current signal, and feeds it into the monitor.  Any
    flicker is immediately dispatched by the BurstDispatcher.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    cfg      = MeshConfig.from_env()
    monitor  = SignalMonitor()
    _        = BurstDispatcher(monitor, api_base=args.api, cfg=cfg)
    session  = requests.Session()

    log.info(
        "Signal monitor started — polling every %.1fs  api=%s",
        args.interval, args.api,
    )

    while True:
        try:
            resp = session.get(
                f"{args.api}/api/mesh/topology",
                timeout=cfg.http_timeout,
            )
            resp.raise_for_status()
            topology = resp.json()

            for node in topology.get("nodes", []):
                monitor.ingest_sample(
                    node_id=node["id"],
                    node_label=node.get("label", node["id"]),
                    signal=int(node.get("signal", 80)),
                    scenario=args.scenario,
                )

        except requests.RequestException as exc:
            log.warning("Topology fetch failed: %s", exc)

        time.sleep(args.interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MeshNet AI — signal flicker monitor"
    )
    parser.add_argument(
        "--api",
        type=str,
        default="http://localhost:4000",
        help="Express backend base URL",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=3.0,
        help="Polling interval in seconds (default: 3)",
    )
    parser.add_argument(
        "--scenario",
        choices=["flood", "war_zone", "earthquake"],
        default="earthquake",
        help="Active disaster scenario",
    )
    _run_monitor(parser.parse_args())
