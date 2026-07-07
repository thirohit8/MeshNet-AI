"""
backend/tests/test_signal_monitor.py
======================================
Unit tests for signal_monitor.py — signal-flicker detection and
high-priority burst dispatch.

Run with:
    cd backend
    python tests/test_signal_monitor.py
"""

from __future__ import annotations

import sys
import os
import time

# Allow importing from backend/ regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signal_monitor import (
    BurstDispatcher,
    BufferedLogChunk,
    FlickerEvent,
    SignalMonitor,
    _DEAD_THRESHOLD,
    _LIVE_THRESHOLD,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _monitor() -> SignalMonitor:
    """Fresh monitor with default thresholds."""
    return SignalMonitor()


# ─── Test: FlickerEvent ───────────────────────────────────────────────────────

class TestFlickerEvent:
    def test_to_dict_has_required_keys(self):
        evt = FlickerEvent(
            node_id="n1", node_label="Node 1",
            prev_signal=2, curr_signal=40, scenario="flood",
        )
        d = evt.to_dict()
        for key in ("nodeId", "nodeLabel", "prevSignal", "currSignal", "scenario", "detectedAt"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_values(self):
        evt = FlickerEvent(
            node_id="n1", node_label="Node 1",
            prev_signal=2, curr_signal=40, scenario="flood",
        )
        d = evt.to_dict()
        assert d["nodeId"]     == "n1"
        assert d["prevSignal"] == 2
        assert d["currSignal"] == 40
        assert d["scenario"]   == "flood"

    def test_detected_at_is_recent(self):
        before = time.time()
        evt = FlickerEvent(
            node_id="n1", node_label="Node 1",
            prev_signal=0, curr_signal=50, scenario="earthquake",
        )
        assert evt.detected_at >= before


# ─── Test: SignalMonitor — no flicker ─────────────────────────────────────────

class TestSignalMonitorNoFlicker:
    def test_stable_high_signal_no_flicker(self):
        """A node that has always been above threshold never flickers."""
        mon = _monitor()
        # Feed several steady high readings
        for sig in (80, 85, 90, 75, 82):
            evt = mon.ingest_sample("n1", "Node 1", signal=sig)
            assert evt is None

    def test_stable_low_signal_no_flicker(self):
        """A node stuck at 0 signal doesn't flicker — nothing to transition from."""
        mon = _monitor()
        for sig in (0, 0, 1, 0, 2):
            evt = mon.ingest_sample("n1", "Node 1", signal=sig)
            assert evt is None

    def test_signal_drops_from_high_to_low_no_flicker(self):
        """A drop (high → low) is not a flicker — only rises count."""
        mon = _monitor()
        mon.ingest_sample("n1", "Node 1", signal=80)
        evt = mon.ingest_sample("n1", "Node 1", signal=3)
        assert evt is None

    def test_below_dead_stays_below_dead_no_flicker(self):
        """Signal below dead threshold and rises only to dead threshold — no flicker."""
        mon = _monitor()
        mon.ingest_sample("n1", "Node 1", signal=_DEAD_THRESHOLD)   # at boundary
        evt = mon.ingest_sample("n1", "Node 1", signal=_LIVE_THRESHOLD)  # exactly at live boundary
        # LIVE_THRESHOLD is exclusive (signal > _LIVE_THRESHOLD), so equal = no flicker
        assert evt is None


# ─── Test: SignalMonitor — flicker detection ──────────────────────────────────

class TestSignalMonitorFlicker:
    def test_zero_to_above_live_threshold_is_flicker(self):
        mon = _monitor()
        mon.ingest_sample("n1", "Node 1", signal=0)        # dead
        evt = mon.ingest_sample("n1", "Node 1", signal=50) # alive
        assert evt is not None
        assert isinstance(evt, FlickerEvent)

    def test_flicker_captures_correct_prev_and_curr(self):
        mon = _monitor()
        mon.ingest_sample("n1", "Node 1", signal=3)        # below dead threshold
        evt = mon.ingest_sample("n1", "Node 1", signal=40)
        assert evt is not None
        assert evt.prev_signal == 3
        assert evt.curr_signal == 40

    def test_flicker_captures_node_id_and_label(self):
        mon = _monitor()
        mon.ingest_sample("node-42", "Node·42", signal=0)
        evt = mon.ingest_sample("node-42", "Node·42", signal=60)
        assert evt is not None
        assert evt.node_id    == "node-42"
        assert evt.node_label == "Node·42"

    def test_flicker_captures_scenario(self):
        mon = _monitor()
        mon.ingest_sample("n1", "Node 1", signal=0, scenario="flood")
        evt = mon.ingest_sample("n1", "Node 1", signal=60, scenario="flood")
        assert evt is not None
        assert evt.scenario == "flood"

    def test_prev_signal_override(self):
        """Caller can override prev_signal — useful when the prev reading
        came from a different source (e.g. hardware API)."""
        mon = _monitor()
        # No stored state for node-99 yet — provide prev_signal explicitly
        evt = mon.ingest_sample(
            "node-99", "Node·99",
            signal=45,
            prev_signal=2,  # caller asserts it was previously dead
        )
        assert evt is not None
        assert evt.prev_signal == 2
        assert evt.curr_signal == 45

    def test_multiple_independent_nodes(self):
        """Flicker on node A must not affect node B."""
        mon = _monitor()
        mon.ingest_sample("a", "A", signal=0)
        mon.ingest_sample("b", "B", signal=80)   # b starts high

        evt_a = mon.ingest_sample("a", "A", signal=50)  # flicker on a
        evt_b = mon.ingest_sample("b", "B", signal=70)  # b stays high, no flicker

        assert evt_a is not None
        assert evt_b is None

    def test_two_consecutive_flickers_same_node(self):
        """If a node drops back to 0 and rises again, a second flicker fires."""
        mon = _monitor()
        mon.ingest_sample("n1", "N1", signal=0)
        evt1 = mon.ingest_sample("n1", "N1", signal=50)
        assert evt1 is not None

        mon.ingest_sample("n1", "N1", signal=0)     # drops again
        evt2 = mon.ingest_sample("n1", "N1", signal=60)
        assert evt2 is not None

    def test_first_sample_never_flickers(self):
        """A brand-new node's first reading can never be a flicker
        (there's no 'previous' state to compare against)."""
        mon = _monitor()
        # First ingest: prev defaults to the same as curr — no transition
        evt = mon.ingest_sample("brand-new", "Brand New", signal=80)
        assert evt is None


# ─── Test: SignalMonitor — callbacks ─────────────────────────────────────────

class TestSignalMonitorCallbacks:
    def test_callback_fires_on_flicker(self):
        fired: list[FlickerEvent] = []
        mon = _monitor()
        mon.on_flicker(fired.append)

        mon.ingest_sample("n1", "N1", signal=0)
        mon.ingest_sample("n1", "N1", signal=50)

        assert len(fired) == 1
        assert fired[0].node_id == "n1"

    def test_callback_not_fired_without_flicker(self):
        fired: list[FlickerEvent] = []
        mon = _monitor()
        mon.on_flicker(fired.append)

        mon.ingest_sample("n1", "N1", signal=80)
        mon.ingest_sample("n1", "N1", signal=90)

        assert len(fired) == 0

    def test_multiple_callbacks_all_fired(self):
        results_a: list[FlickerEvent] = []
        results_b: list[FlickerEvent] = []
        mon = _monitor()
        mon.on_flicker(results_a.append)
        mon.on_flicker(results_b.append)

        mon.ingest_sample("n1", "N1", signal=0)
        mon.ingest_sample("n1", "N1", signal=50)

        assert len(results_a) == 1
        assert len(results_b) == 1

    def test_bad_callback_does_not_stop_other_callbacks(self):
        """A callback that raises must not prevent subsequent callbacks from firing."""
        good_results: list[FlickerEvent] = []

        def bad_cb(_evt: FlickerEvent) -> None:
            raise RuntimeError("I am broken")

        mon = _monitor()
        mon.on_flicker(bad_cb)
        mon.on_flicker(good_results.append)

        mon.ingest_sample("n1", "N1", signal=0)
        mon.ingest_sample("n1", "N1", signal=50)

        assert len(good_results) == 1


# ─── Test: SignalMonitor — state helpers ─────────────────────────────────────

class TestSignalMonitorState:
    def test_last_signal_returns_none_before_first_sample(self):
        mon = _monitor()
        assert mon.last_signal("unknown-node") is None

    def test_last_signal_updated_after_ingest(self):
        mon = _monitor()
        mon.ingest_sample("n1", "N1", signal=42)
        assert mon.last_signal("n1") == 42

    def test_reset_node_clears_state(self):
        mon = _monitor()
        mon.ingest_sample("n1", "N1", signal=80)
        mon.reset_node("n1")
        assert mon.last_signal("n1") is None

    def test_reset_unknown_node_is_safe(self):
        mon = _monitor()
        mon.reset_node("does-not-exist")   # must not raise


# ─── Test: BurstDispatcher — buffer management ───────────────────────────────

class TestBurstDispatcherBuffer:
    def test_buffer_log_accumulates_chunks(self):
        mon  = SignalMonitor()
        disp = BurstDispatcher(mon, api_base="http://localhost:1")  # unreachable is fine
        disp.buffer_log("n1", '{"msg":"a"}')
        disp.buffer_log("n1", '{"msg":"b"}')
        assert len(disp._buffers.get("n1", [])) == 2

    def test_dispatch_drains_buffer(self):
        """After a burst the buffer for the node must be empty."""
        dispatched_flushes: list[str] = []

        mon  = SignalMonitor()
        disp = BurstDispatcher(mon, api_base="http://localhost:1")

        # Stub out network calls so the test is pure-logic
        def _no_http(evt: FlickerEvent) -> None:
            chunks = disp._buffers.pop(evt.node_id, [])
            dispatched_flushes.extend(c.payload for c in chunks)

        disp._report_flicker = lambda _evt: None   # type: ignore[assignment]
        disp._push_chunk     = lambda _nid, _chunk: None  # type: ignore[assignment]

        # Manually buffer two chunks
        disp.buffer_log("n1", "chunk-1")
        disp.buffer_log("n1", "chunk-2")

        # Trigger a burst event directly
        evt = FlickerEvent(node_id="n1", node_label="N1",
                           prev_signal=0, curr_signal=50, scenario="earthquake")
        # Call dispatch with stubbed helpers
        original_dispatch = BurstDispatcher.dispatch
        # Patch push_chunk and report_flicker before calling dispatch
        disp._report_flicker = lambda _: None       # type: ignore[assignment]
        disp._push_chunk     = lambda _n, c: dispatched_flushes.append(c.payload)  # type: ignore[assignment]
        disp.dispatch(evt)

        assert "n1" not in disp._buffers
        assert set(dispatched_flushes) == {"chunk-1", "chunk-2"}

    def test_dispatch_with_empty_buffer_is_safe(self):
        """Dispatching with no queued chunks must not raise."""
        mon  = SignalMonitor()
        disp = BurstDispatcher(mon, api_base="http://localhost:1")
        disp._report_flicker = lambda _: None   # type: ignore[assignment]
        disp._push_chunk     = lambda _n, _c: None  # type: ignore[assignment]

        evt = FlickerEvent(node_id="empty-node", node_label="Empty",
                           prev_signal=0, curr_signal=50, scenario="earthquake")
        disp.dispatch(evt)   # should not raise

    def test_chunks_from_one_node_do_not_leak_to_another(self):
        """Buffers are strictly per-node — n2's chunks must not flush during n1's burst."""
        flushed: list[str] = []
        mon  = SignalMonitor()
        disp = BurstDispatcher(mon, api_base="http://localhost:1")
        disp._report_flicker = lambda _: None   # type: ignore[assignment]
        disp._push_chunk     = lambda _n, c: flushed.append(c.payload)  # type: ignore[assignment]

        disp.buffer_log("n1", "n1-chunk")
        disp.buffer_log("n2", "n2-chunk")

        evt = FlickerEvent(node_id="n1", node_label="N1",
                           prev_signal=0, curr_signal=50, scenario="earthquake")
        disp.dispatch(evt)

        assert flushed == ["n1-chunk"]           # only n1's chunk flushed
        assert len(disp._buffers.get("n2", [])) == 1  # n2's chunk still queued


# ─── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import traceback

    test_classes = [
        TestFlickerEvent,
        TestSignalMonitorNoFlicker,
        TestSignalMonitorFlicker,
        TestSignalMonitorCallbacks,
        TestSignalMonitorState,
        TestBurstDispatcherBuffer,
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
