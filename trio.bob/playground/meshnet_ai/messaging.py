"""
MeshNet-AI — messaging.py
=========================
Offline Emergency Messaging Engine
-----------------------------------
Provides:

  BroadcastEngine   — hop-by-hop SOS packet propagation simulation.
                      Each hop introduces a 1-second transmission delay
                      to visualise localised radio-wave propagation.

  HandshakeLogger   — encrypted JSON log of every successful route.
                      Uses base64 + a symmetric XOR byte-stream cipher
                      (zero external dependencies, runs fully offline).

Thread safety
-------------
BroadcastEngine.broadcast() is designed to run in a worker thread.
All GUI callbacks are scheduled via kivy.clock.Clock.schedule_once so
they are dispatched on the main thread.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from kivy.clock import Clock
from kivy.utils import platform

logger = logging.getLogger(__name__)

# ── Storage paths ─────────────────────────────────────────────────────────────

def _log_dir() -> str:
    """Return the platform-appropriate directory for handshake logs."""
    if platform == "android":
        try:
            from android.storage import app_storage_path   # type: ignore
            return os.path.join(app_storage_path(), "logs")
        except ImportError:
            pass
    # Desktop / CI fallback: logs/ next to this file
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


LOG_FILE = os.path.join(_log_dir(), "handshake_log.enc")

# ── XOR stream cipher (lightweight offline obfuscation) ──────────────────────
# Key is stored in the APK; in production this would be derived from a device
# hardware identifier or a user-supplied passphrase via PBKDF2.
_CIPHER_KEY = b"MeshNetAI-OfflineKey-2025"


def _xor_cipher(data: bytes, key: bytes) -> bytes:
    """Apply repeating-key XOR to *data*.  Encryption == decryption."""
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


def encrypt_payload(plaintext: str) -> str:
    """
    Encrypt *plaintext* with XOR cipher, then base64-encode.
    Returns an ASCII-safe ciphertext string safe for JSON storage.
    """
    raw       = plaintext.encode("utf-8")
    ciphered  = _xor_cipher(raw, _CIPHER_KEY)
    encoded   = base64.b64encode(ciphered)
    return encoded.decode("ascii")


def decrypt_payload(ciphertext: str) -> str:
    """Reverse of encrypt_payload — returns the original plaintext."""
    decoded  = base64.b64decode(ciphertext.encode("ascii"))
    raw      = _xor_cipher(decoded, _CIPHER_KEY)
    return raw.decode("utf-8")


# ── Packet dataclass ──────────────────────────────────────────────────────────

class SOSPacket:
    """
    Immutable SOS broadcast packet.

    Attributes
    ----------
    packet_id   : unique identifier (timestamp-based)
    scenario    : disaster scenario label (e.g. "Flood", "Earthquake")
    message     : freeform emergency text
    origin_node : node_id of the originating device
    path        : ordered list of node_ids representing the hop route
    created_at  : UTC ISO-8601 timestamp
    """

    __slots__ = (
        "packet_id", "scenario", "message",
        "origin_node", "path", "created_at",
    )

    def __init__(
        self,
        scenario    : str,
        message     : str,
        origin_node : str,
        path        : list[str],
    ) -> None:
        self.packet_id   = f"SOS-{int(time.time() * 1000)}"
        self.scenario    = scenario
        self.message     = message
        self.origin_node = origin_node
        self.path        = list(path)
        self.created_at  = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "packet_id"  : self.packet_id,
            "scenario"   : self.scenario,
            "message"    : self.message,
            "origin_node": self.origin_node,
            "path"       : self.path,
            "created_at" : self.created_at,
        }


# ── Broadcast engine ──────────────────────────────────────────────────────────

class BroadcastEngine:
    """
    Simulates hop-by-hop SOS packet propagation through the mesh.

    Each hop:
      1. Logs a "TRANSMITTING → NODE-X" event via *on_hop_callback*.
      2. Sleeps for HOP_DELAY_SECONDS to simulate RF propagation latency.
      3. Logs a "RECEIVED @ NODE-X" event.

    On completion, the full route is persisted to the encrypted log.

    Usage
    -----
    engine = BroadcastEngine(handshake_logger)
    engine.broadcast(packet, on_hop=gui_callback, on_complete=done_callback)
    """

    HOP_DELAY_SECONDS: float = 1.0   # propagation delay per hop

    def __init__(self, logger_inst: HandshakeLogger) -> None:
        self._logger      = logger_inst
        self._active      = False
        self._abort_event = threading.Event()

    # ── Public API ─────────────────────────────────────────────────────────────

    def broadcast(
        self,
        packet      : SOSPacket,
        on_hop      : Optional[Callable[[int, str, str], None]] = None,
        on_complete : Optional[Callable[[SOSPacket, bool], None]] = None,
    ) -> threading.Thread:
        """
        Launch the propagation simulation in a daemon thread.

        Parameters
        ----------
        packet      : SOSPacket to propagate
        on_hop      : called on the GUI thread with (hop_index, node_id, status)
                      where status is "TX" or "RX"
        on_complete : called on the GUI thread with (packet, success: bool)

        Returns
        -------
        The worker thread (already started).
        """
        self._abort_event.clear()
        t = threading.Thread(
            target=self._run,
            args=(packet, on_hop, on_complete),
            daemon=True,
            name=f"broadcast-{packet.packet_id}",
        )
        t.start()
        return t

    def abort(self) -> None:
        """Signal the running broadcast to stop after the current hop."""
        self._abort_event.set()
        logger.info("[MSG] Broadcast abort requested.")

    # ── Worker ────────────────────────────────────────────────────────────────

    def _run(
        self,
        packet      : SOSPacket,
        on_hop      : Optional[Callable[[int, str, str], None]],
        on_complete : Optional[Callable[[SOSPacket, bool], None]],
    ) -> None:
        self._active = True
        success = True
        logger.info(
            "[MSG] Broadcasting %s over %d hops.",
            packet.packet_id, len(packet.path)
        )

        for idx, node_id in enumerate(packet.path):
            if self._abort_event.is_set():
                logger.warning("[MSG] Broadcast aborted at hop %d.", idx)
                success = False
                break

            # ── TX event ──────────────────────────────────────────────────────
            if on_hop:
                _idx, _nid = idx, node_id
                Clock.schedule_once(
                    lambda dt, i=_idx, n=_nid: on_hop(i, n, "TX"), 0
                )
            logger.debug("[MSG] Hop %d → TX to %s", idx, node_id)

            # ── Propagation delay ─────────────────────────────────────────────
            time.sleep(self.HOP_DELAY_SECONDS)

            if self._abort_event.is_set():
                success = False
                break

            # ── RX event ──────────────────────────────────────────────────────
            if on_hop:
                Clock.schedule_once(
                    lambda dt, i=_idx, n=_nid: on_hop(i, n, "RX"), 0
                )
            logger.debug("[MSG] Hop %d → RX at  %s", idx, node_id)

        # ── Persist result ────────────────────────────────────────────────────
        if success:
            self._logger.append(packet)

        # ── Completion callback ───────────────────────────────────────────────
        if on_complete:
            Clock.schedule_once(
                lambda dt: on_complete(packet, success), 0
            )

        self._active = False
        logger.info(
            "[MSG] Broadcast %s finished. success=%s",
            packet.packet_id, success,
        )


# ── Handshake logger ──────────────────────────────────────────────────────────

class HandshakeLogger:
    """
    Append-only encrypted JSON log file.

    Each record stored on disk is:
    {
        "ts"     : "<UTC ISO timestamp>",
        "payload": "<base64(XOR(json_serialised_packet))>"
    }

    The entire file is a JSON array of such records, rewritten atomically
    on every append to prevent corruption on sudden power loss.

    Thread safety: a threading.Lock serialises all write operations.
    """

    def __init__(self, log_path: str = LOG_FILE) -> None:
        self._path = log_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def append(self, packet: SOSPacket) -> None:
        """Encrypt and append *packet* to the handshake log."""
        with self._lock:
            records = self._load_raw()
            plaintext = json.dumps(packet.to_dict(), ensure_ascii=False)
            records.append({
                "ts"     : datetime.now(tz=timezone.utc).isoformat(),
                "payload": encrypt_payload(plaintext),
            })
            self._save_raw(records)
        logger.info("[LOG] Appended record for %s.", packet.packet_id)

    def read_all(self) -> list[dict]:
        """
        Decrypt and return all stored packet dicts.
        Returns empty list if the log does not exist or is corrupt.
        """
        with self._lock:
            records = self._load_raw()

        results = []
        for rec in records:
            try:
                plain = decrypt_payload(rec["payload"])
                results.append(json.loads(plain))
            except Exception as exc:
                logger.warning("[LOG] Failed to decrypt record: %s", exc)
        return results

    def clear(self) -> None:
        """Wipe the entire log file (irreversible)."""
        with self._lock:
            self._save_raw([])
        logger.info("[LOG] Handshake log cleared.")

    def record_count(self) -> int:
        """Return the number of stored records without decrypting them."""
        with self._lock:
            return len(self._load_raw())

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_raw(self) -> list[dict]:
        """Load the raw (still encrypted) JSON array from disk."""
        if not os.path.exists(self._path):
            return []
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("[LOG] Failed to load log: %s", exc)
            return []

    def _save_raw(self, records: list[dict]) -> None:
        """Atomically write *records* to disk (write-then-rename pattern)."""
        tmp_path = self._path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(records, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except OSError as exc:
            logger.error("[LOG] Failed to save log: %s", exc)
            try:
                os.remove(tmp_path)
            except OSError:
                pass
