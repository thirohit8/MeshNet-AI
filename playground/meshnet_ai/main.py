"""
MeshNet-AI — main.py
====================
Application entry point. Bootstraps the Kivy/KivyMD runtime,
registers the KV layout file, and launches the root widget.

Build with:
    buildozer android debug deploy run logcat
"""

import os
import sys

# ── Android-specific path bootstrap ──────────────────────────────────────────
# On Android, storagedir is set by Kivy's bootstrap.  We add it to sys.path so
# that all local modules (hardware, routing, messaging, …) can be imported.
try:
    from android.storage import app_storage_path          # type: ignore
    _STORAGE = app_storage_path()
except ImportError:
    # Desktop / CI fallback — resolve relative to this file's directory
    _STORAGE = os.path.dirname(os.path.abspath(__file__))

if _STORAGE not in sys.path:
    sys.path.insert(0, _STORAGE)

# ── Kivy environment variables — must be set BEFORE importing kivy ────────────
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

import kivy
kivy.require("2.3.0")

from kivy.lang import Builder
from kivy.utils import platform
from kivymd.app import MDApp

# Local modules
from ui import MeshNetRootWidget          # root widget built in ui.py
from hardware import HardwareManager      # Bluetooth / Wi-Fi initialisation

# ── Load declarative KV layout ────────────────────────────────────────────────
_KV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meshnet.kv")
Builder.load_file(_KV_FILE)


class MeshNetApp(MDApp):
    """
    Top-level MDApp subclass.

    Lifecycle
    ---------
    on_start   → request Android permissions, then initialise hardware
    on_stop    → gracefully shut down all background workers
    """

    # ── MDApp theming ─────────────────────────────────────────────────────────
    def build(self) -> MeshNetRootWidget:
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.accent_palette  = "Amber"
        self.title = "MeshNet-AI  |  Offline Emergency Mesh"
        self.icon  = "assets/icon.png"

        self._hw = HardwareManager()
        root = MeshNetRootWidget()
        return root

    # ── Android permission bootstrapping ─────────────────────────────────────
    def on_start(self) -> None:
        if platform == "android":
            self._request_android_permissions()
        # Hardware init runs on all platforms (graceful no-op on desktop)
        self._hw.initialise()

    def on_stop(self) -> None:
        self.root.shutdown()          # propagates to all sub-managers
        self._hw.shutdown()

    # ── Internal helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _request_android_permissions() -> None:
        """
        Request dangerous runtime permissions from the Android OS.
        The full permission *declarations* live in buildozer.spec.
        These are the additional run-time grants required on API 23+.
        """
        from android.permissions import (          # type: ignore
            request_permissions,
            Permission,
        )
        request_permissions(
            [
                Permission.BLUETOOTH,
                Permission.BLUETOOTH_ADMIN,
                Permission.ACCESS_WIFI_STATE,
                Permission.CHANGE_WIFI_STATE,
                Permission.ACCESS_FINE_LOCATION,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ]
        )


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    MeshNetApp().run()
