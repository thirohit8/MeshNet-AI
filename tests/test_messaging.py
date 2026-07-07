"""
MeshNet-AI — tests/test_messaging.py
======================================
Unit tests for messaging.py — no Android runtime required.

Kivy is stubbed so these tests run on any plain Python 3 install.
"""
import sys, os, json, time, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Stub Kivy modules so messaging.py imports without a display ───────────────
kivy_stub  = types.ModuleType("kivy")
clock_stub = types.ModuleType("kivy.clock")
utils_stub = types.ModuleType("kivy.utils")

class _ClockStub:
    """Synchronously executes Clock.schedule_once callbacks in tests."""
    @staticmethod
    def schedule_once(cb, delay=0):
        try:
            cb(delay)
        except Exception:
            pass  # swallow any GUI-only errors

clock_stub.Clock    = _ClockStub()
utils_stub.platform = "linux"   # non-Android → log dir falls back to ./logs/

kivy_stub.clock = clock_stub
kivy_stub.utils = utils_stub
sys.modules.setdefault("kivy",       kivy_stub)
sys.modules.setdefault("kivy.clock", clock_stub)
sys.modules.setdefault("kivy.utils", utils_stub)
# ─────────────────────────────────────────────────────────────────────────────

import pytest
from messaging import (
    encrypt_payload, decrypt_payload,
    SOSPacket, HandshakeLogger, BroadcastEngine,
)


# ── Crypto round-trip ──────────────────────────────────────────────────────────

def test_encrypt_decrypt_roundtrip():
    original   = '{"test": "MeshNet-AI", "unicode": "\U0001f6f0"}'
    ciphertext = encrypt_payload(original)
    assert ciphertext != original
    assert decrypt_payload(ciphertext) == original

def test_ciphertext_is_ascii():
    ct = encrypt_payload("hello world")
    ct.encode("ascii")   # must not raise


# ── SOSPacket ─────────────────────────────────────────────────────────────────

def test_packet_fields():
    p = SOSPacket(
        scenario    = "Flood",
        message     = "HELP",
        origin_node = "NODE-A1",
        path        = ["NODE-A1", "NODE-B2"],
    )
    assert p.packet_id.startswith("SOS-")
    assert p.scenario    == "Flood"
    assert p.origin_node == "NODE-A1"
    assert len(p.path)   == 2

def test_packet_to_dict_keys():
    p = SOSPacket("Earthquake", "MSG", "N1", ["N1", "N2"])
    d = p.to_dict()
    for key in ("packet_id", "scenario", "message", "origin_node", "path", "created_at"):
        assert key in d


# ── HandshakeLogger ────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_logger(tmp_path):
    log_file = str(tmp_path / "handshake_log.enc")
    return HandshakeLogger(log_path=log_file)

def test_logger_append_and_read(tmp_logger):
    p = SOSPacket("War Zone", "SOS", "N1", ["N1", "N2", "N3"])
    tmp_logger.append(p)
    records = tmp_logger.read_all()
    assert len(records) == 1
    assert records[0]["packet_id"] == p.packet_id

def test_logger_multiple_records(tmp_logger):
    for i in range(5):
        tmp_logger.append(SOSPacket("Flood", f"MSG{i}", "N1", ["N1"]))
    assert tmp_logger.record_count() == 5

def test_logger_clear(tmp_logger):
    tmp_logger.append(SOSPacket("Flood", "MSG", "N1", ["N1"]))
    tmp_logger.clear()
    assert tmp_logger.record_count() == 0

def test_logger_file_does_not_exist_returns_empty(tmp_path):
    logger = HandshakeLogger(log_path=str(tmp_path / "nonexistent.enc"))
    assert logger.read_all() == []


# ── BroadcastEngine ────────────────────────────────────────────────────────────

def test_broadcast_completes(tmp_logger):
    """Broadcast over a 3-node path must finish and log the packet."""
    engine = BroadcastEngine(tmp_logger)
    engine.HOP_DELAY_SECONDS = 0.0   # eliminate sleep delay in tests

    p = SOSPacket("Flood", "TEST", "N1", ["N1", "N2", "N3"])
    t = engine.broadcast(p)
    t.join(timeout=5)
    assert not t.is_alive(), "Broadcast thread did not terminate"

def test_broadcast_logs_on_success(tmp_logger):
    """A completed broadcast must create exactly one log record."""
    engine = BroadcastEngine(tmp_logger)
    engine.HOP_DELAY_SECONDS = 0.0

    p = SOSPacket("Flood", "TEST", "N1", ["N1", "N2"])
    t = engine.broadcast(p)
    t.join(timeout=5)
    assert tmp_logger.record_count() == 1

def test_broadcast_abort_does_not_log(tmp_logger):
    """An aborted broadcast must NOT write to the log."""
    engine = BroadcastEngine(tmp_logger)
    engine.HOP_DELAY_SECONDS = 0.5   # give abort time to fire

    p = SOSPacket("Earthquake", "ABORT_TEST", "N1",
                  ["N1", "N2", "N3", "N4", "N5"])
    t = engine.broadcast(p)
    engine.abort()
    t.join(timeout=10)
    assert tmp_logger.record_count() == 0
