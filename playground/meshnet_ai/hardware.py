"""
MeshNet-AI — hardware.py
========================
Android hardware integration layer.

Provides HardwareManager, which:
  • Detects platform and requests Bluetooth / Wi-Fi adapter state.
  • Exposes observable properties consumed by the GUI.
  • Falls back gracefully on desktop (for development / CI).

Android Java bridge calls use ``jnius.autoclass``; they are guarded by a
platform check so the module imports cleanly on any OS.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum, auto
from typing import Callable, Optional

from kivy.utils import platform
from kivy.event import EventDispatcher
from kivy.properties import BooleanProperty, StringProperty

logger = logging.getLogger(__name__)


# ── Enumerations ──────────────────────────────────────────────────────────────

class AdapterState(Enum):
    """Mirrors android.bluetooth.BluetoothAdapter state constants."""
    UNKNOWN    = auto()
    OFF        = auto()
    ON         = auto()
    TURNING_ON = auto()
    TURNING_OFF= auto()


class WifiState(Enum):
    """Mirrors android.net.wifi.WifiManager state constants."""
    UNKNOWN    = auto()
    DISABLED   = auto()
    ENABLED    = auto()
    ENABLING   = auto()
    DISABLING  = auto()


# ── HardwareManager ───────────────────────────────────────────────────────────

class HardwareManager(EventDispatcher):
    """
    Centralised hardware state manager.

    Observable Kivy properties
    --------------------------
    bt_state   : str — human-readable Bluetooth adapter state
    wifi_state : str — human-readable Wi-Fi adapter state
    bt_enabled : bool
    wifi_enabled: bool
    """

    bt_state    = StringProperty("UNKNOWN")
    wifi_state  = StringProperty("UNKNOWN")
    bt_enabled  = BooleanProperty(False)
    wifi_enabled= BooleanProperty(False)

    # Android state-code → AdapterState mapping
    _BT_STATE_MAP: dict[int, AdapterState] = {
        10: AdapterState.OFF,
        11: AdapterState.TURNING_ON,
        12: AdapterState.ON,
        13: AdapterState.TURNING_OFF,
    }
    _WIFI_STATE_MAP: dict[int, WifiState] = {
        0: WifiState.DISABLING,
        1: WifiState.DISABLED,
        2: WifiState.ENABLING,
        3: WifiState.ENABLED,
        4: WifiState.UNKNOWN,
    }

    def __init__(self, **kwargs):
        self.register_event_type("on_bt_state_change")
        self.register_event_type("on_wifi_state_change")
        super().__init__(**kwargs)

        self._bt_adapter   = None   # android BluetoothAdapter JNI proxy
        self._wifi_manager = None   # android WifiManager JNI proxy
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False

    # ── Public API ────────────────────────────────────────────────────────────

    def initialise(self) -> None:
        """
        Detect platform, acquire adapter handles, start polling thread.
        Safe to call multiple times (idempotent guard via _running flag).
        """
        if self._running:
            return

        if platform == "android":
            self._init_android_adapters()
        else:
            logger.info("[HW] Non-Android platform — using stub hardware state.")
            self.bt_state    = "STUB_ON"
            self.wifi_state  = "STUB_ON"
            self.bt_enabled  = True
            self.wifi_enabled= True

        self._running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="hw-poll",
        )
        self._poll_thread.start()
        logger.info("[HW] HardwareManager initialised.")

    def shutdown(self) -> None:
        """Signal the polling thread to stop."""
        self._running = False
        logger.info("[HW] HardwareManager shut down.")

    def enable_bluetooth(self) -> None:
        """Request the OS to enable Bluetooth (Android only)."""
        if platform != "android" or self._bt_adapter is None:
            logger.warning("[HW] enable_bluetooth: no Android adapter available.")
            return
        try:
            self._bt_adapter.enable()
            logger.info("[HW] Bluetooth enable requested.")
        except Exception as exc:                          # jnius JVM exceptions
            logger.error("[HW] enable_bluetooth error: %s", exc)

    def enable_wifi(self) -> None:
        """Request the OS to enable Wi-Fi (Android API ≤ 28 only)."""
        if platform != "android" or self._wifi_manager is None:
            logger.warning("[HW] enable_wifi: no Android WifiManager available.")
            return
        try:
            self._wifi_manager.setWifiEnabled(True)
            logger.info("[HW] Wi-Fi enable requested.")
        except Exception as exc:
            logger.error("[HW] enable_wifi error: %s", exc)

    # ── Default event handlers (must exist for EventDispatcher) ───────────────

    def on_bt_state_change(self, state: str) -> None:   # noqa: D401
        pass

    def on_wifi_state_change(self, state: str) -> None:
        pass

    # ── Android initialisation ────────────────────────────────────────────────

    def _init_android_adapters(self) -> None:
        """
        Use pyjnius ``autoclass`` to obtain references to Android system
        services.  All JNI calls are wrapped in try/except so a missing
        permission or API level mismatch does not crash the app.
        """
        try:
            from jnius import autoclass          # type: ignore

            # ── Bluetooth ────────────────────────────────────────────────────
            BluetoothAdapter = autoclass(
                "android.bluetooth.BluetoothAdapter"
            )
            self._bt_adapter = BluetoothAdapter.getDefaultAdapter()
            if self._bt_adapter is None:
                logger.warning("[HW] Device has no Bluetooth adapter.")
            else:
                logger.info("[HW] Bluetooth adapter acquired.")

            # ── Wi-Fi ────────────────────────────────────────────────────────
            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )
            Context = autoclass("android.content.Context")
            activity = PythonActivity.mActivity
            self._wifi_manager = activity.getSystemService(
                Context.WIFI_SERVICE
            )
            if self._wifi_manager is None:
                logger.warning("[HW] Could not acquire WifiManager.")
            else:
                logger.info("[HW] WifiManager acquired.")

        except Exception as exc:
            logger.error("[HW] Android adapter init failed: %s", exc)

    # ── Polling loop ──────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        """
        Background thread that samples adapter state every 3 seconds and
        updates Kivy properties (which are thread-safe via Clock scheduling).
        """
        import time
        from kivy.clock import Clock

        while self._running:
            bt_s, wifi_s = self._read_adapter_states()

            def _update(dt, b=bt_s, w=wifi_s):
                if b != self.bt_state:
                    self.bt_state   = b
                    self.bt_enabled = b in ("ON", "STUB_ON")
                    self.dispatch("on_bt_state_change", b)
                if w != self.wifi_state:
                    self.wifi_state   = w
                    self.wifi_enabled = w in ("ENABLED", "STUB_ON")
                    self.dispatch("on_wifi_state_change", w)

            Clock.schedule_once(_update, 0)
            time.sleep(3)

    def _read_adapter_states(self) -> tuple[str, str]:
        """Return (bt_state_str, wifi_state_str) from live adapters or stubs."""
        bt_str   = self.bt_state
        wifi_str = self.wifi_state

        if platform == "android":
            # ── Bluetooth state ───────────────────────────────────────────────
            if self._bt_adapter is not None:
                try:
                    code     = self._bt_adapter.getState()
                    bt_state = self._BT_STATE_MAP.get(
                        code, AdapterState.UNKNOWN
                    )
                    bt_str = bt_state.name
                except Exception as exc:
                    logger.debug("[HW] BT state read error: %s", exc)

            # ── Wi-Fi state ───────────────────────────────────────────────────
            if self._wifi_manager is not None:
                try:
                    code      = self._wifi_manager.getWifiState()
                    wifi_state= self._WIFI_STATE_MAP.get(
                        code, WifiState.UNKNOWN
                    )
                    wifi_str = wifi_state.name
                except Exception as exc:
                    logger.debug("[HW] Wi-Fi state read error: %s", exc)

        return bt_str, wifi_str
