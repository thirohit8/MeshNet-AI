"""
MeshNet-AI — ui.py
==================
Native GUI layer — KivyMD split-screen dashboard.

Layout
------
MeshNetRootWidget (MDBoxLayout — horizontal)
├── LeftPanel  (MDCard — system monitor)
│   ├── StatusBar          — BT / Wi-Fi indicators + scenario selector
│   ├── PeerListView       — scrollable active-peer list
│   ├── HopLogView         — real-time hop-by-hop broadcast log
│   └── BroadcastSOSButton — prominent action button
└── RightPanel (MDCard — map + controls)
    ├── MapView            — offline tile map (kivy_garden.mapview)
    └── MapToolbar         — satellite toggle + centre-path button

All inter-module wiring happens here; no business logic lives in this file.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from kivy.clock import Clock
from kivy.properties import (
    BooleanProperty, StringProperty, ListProperty, ObjectProperty,
)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform


from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.list import (
    MDList, TwoLineIconListItem, IconLeftWidget,
)
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.toolbar import MDTopAppBar

# Local modules
from routing   import RoutingEngine, MeshNode, mock_topology
from messaging import BroadcastEngine, HandshakeLogger, SOSPacket
from mapview_module import MapManager

logger = logging.getLogger(__name__)

# ── Scenario configuration ────────────────────────────────────────────────────

SCENARIOS: dict[str, dict] = {
    "Flood": {
        "icon"                 : "water",
        "battery_threshold_warn": 30,
        "max_hops"             : 8,
        "priority_node_types"  : ["gateway", "relay"],
        "description"          : "Elevated terrain nodes preferred. "
                                 "Max 8 hops. Battery warn at 30 %.",
    },
    "Earthquake": {
        "icon"                 : "image-broken-variant",
        "battery_threshold_warn": 25,
        "max_hops"             : 10,
        "priority_node_types"  : ["gateway", "relay", "smartphone"],
        "description"          : "Wide coverage. Max 10 hops. "
                                 "Battery warn at 25 %.",
    },
    "War Zone": {
        "icon"                 : "shield-alert",
        "battery_threshold_warn": 40,
        "max_hops"             : 5,
        "priority_node_types"  : ["gateway"],
        "description"          : "Minimal footprint. Max 5 hops. "
                                 "Battery warn at 40 %. Encryption enforced.",
    },
}

SCENARIO_NAMES = list(SCENARIOS.keys())


# ── Peer list item ────────────────────────────────────────────────────────────

class PeerListItem(TwoLineIconListItem):
    """
    Single row in the peer list.

    Parameters
    ----------
    node  : MeshNode
    score : float routing score
    """

    def __init__(self, node: MeshNode, score: float, **kwargs):
        bat_str    = f"{node.battery_level:.0f}%"
        hq_flag    = " 🛰 HQ" if node.has_weather_hq_signal else ""
        score_str  = f"Score: {score:.3f}{hq_flag}"

        super().__init__(
            text       = f"{node.node_id}  [{node.device_type.upper()}]"
                         f"  🔋{bat_str}",
            secondary_text = score_str,
            **kwargs,
        )
        icon_name = "access-point-check" if node.is_active else "access-point-remove"
        self.add_widget(IconLeftWidget(icon=icon_name))


# ── Hop log panel ─────────────────────────────────────────────────────────────

class HopLogView(ScrollView):
    """
    Scrollable text log of hop-by-hop broadcast events.
    Updated from the main thread via append_log().
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._list = MDList()
        self.add_widget(self._list)
        self._count = 0

    def append_log(self, text: str) -> None:
        self._count += 1
        label = MDLabel(
            text         = f"[{self._count:03d}]  {text}",
            font_style   = "Caption",
            theme_text_color = "Secondary",
            size_hint_y  = None,
            height       = 28,
        )
        self._list.add_widget(label)
        # Auto-scroll to bottom
        Clock.schedule_once(
            lambda dt: setattr(self, "scroll_y", 0), 0.05
        )

    def clear_log(self) -> None:
        self._list.clear_widgets()
        self._count = 0


# ── Left panel ────────────────────────────────────────────────────────────────

class LeftPanel(MDCard):
    """
    System monitor panel (left half of dashboard).
    Contains: status bar, peer list, hop log, SOS button.
    """

    current_scenario = StringProperty(SCENARIO_NAMES[0])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation  = "vertical"
        self.padding      = "12dp"
        self.spacing      = "8dp"
        self.elevation    = 4
        self.radius       = [12, 12, 12, 12]

        # ── Header ───────────────────────────────────────────────────────────
        self._header = MDTopAppBar(
            title          = "System Monitor",
            size_hint_y    = None,
            height         = "56dp",
            elevation      = 0,
        )
        self.add_widget(self._header)

        # ── Status indicators row ─────────────────────────────────────────────
        self._status_row = MDBoxLayout(
            orientation = "horizontal",
            size_hint_y = None,
            height      = "40dp",
            spacing     = "16dp",
        )
        self._bt_label   = MDLabel(
            text             = "BT: --",
            theme_text_color = "Secondary",
            font_style       = "Caption",
        )
        self._wifi_label = MDLabel(
            text             = "WiFi: --",
            theme_text_color = "Secondary",
            font_style       = "Caption",
        )
        self._log_label = MDLabel(
            text             = "Logs: 0",
            theme_text_color = "Hint",
            font_style       = "Caption",
        )
        self._status_row.add_widget(self._bt_label)
        self._status_row.add_widget(self._wifi_label)
        self._status_row.add_widget(self._log_label)
        self.add_widget(self._status_row)

        # ── Scenario selector row ─────────────────────────────────────────────
        scenario_row = MDBoxLayout(
            orientation = "horizontal",
            size_hint_y = None,
            height      = "48dp",
            spacing     = "8dp",
        )
        self._scenario_label = MDLabel(
            text      = "Scenario:",
            size_hint_x = 0.35,
            font_style= "Button",
        )
        scenario_row.add_widget(self._scenario_label)

        for name in SCENARIO_NAMES:
            btn = MDFlatButton(
                text        = name,
                on_release  = lambda x, n=name: self.set_scenario(n),
            )
            scenario_row.add_widget(btn)
        self.add_widget(scenario_row)

        # ── Scenario description label ────────────────────────────────────────
        self._scenario_desc = MDLabel(
            text             = SCENARIOS[self.current_scenario]["description"],
            theme_text_color = "Hint",
            font_style       = "Caption",
            size_hint_y      = None,
            height           = "36dp",
        )
        self.add_widget(self._scenario_desc)

        # ── Section: Active peers ─────────────────────────────────────────────
        self.add_widget(MDLabel(
            text       = "Active Peers",
            font_style = "Subtitle1",
            size_hint_y= None,
            height     = "32dp",
        ))
        self._peer_scroll = ScrollView(size_hint_y=0.35)
        self._peer_list   = MDList()
        self._peer_scroll.add_widget(self._peer_list)
        self.add_widget(self._peer_scroll)

        # ── Section: Broadcast log ────────────────────────────────────────────
        self.add_widget(MDLabel(
            text       = "Broadcast Log",
            font_style = "Subtitle1",
            size_hint_y= None,
            height     = "32dp",
        ))
        self._hop_log = HopLogView(size_hint_y=0.30)
        self.add_widget(self._hop_log)

        # ── SOS broadcast button ──────────────────────────────────────────────
        self._sos_button = MDRaisedButton(
            text        = "  📡  BROADCAST SOS  ",
            font_style  = "H6",
            md_bg_color = (0.85, 0.1, 0.1, 1),
            size_hint_y = None,
            height      = "64dp",
            on_release  = self._on_sos_pressed,
        )
        self.add_widget(self._sos_button)

        # ── Internal state ────────────────────────────────────────────────────
        self._broadcasting = False
        self._broadcast_cb = None   # injected by MeshNetRootWidget

    # ── Public API ────────────────────────────────────────────────────────────

    def set_hardware_state(self, bt_state: str, wifi_state: str) -> None:
        self._bt_label.text   = f"BT: {bt_state}"
        self._wifi_label.text = f"WiFi: {wifi_state}"

    def set_log_count(self, count: int) -> None:
        self._log_label.text = f"Logs: {count}"

    def set_scenario(self, name: str) -> None:
        self.current_scenario       = name
        self._scenario_desc.text    = SCENARIOS[name]["description"]
        self._scenario_label.text   = f"Scenario: {name}"
        logger.info("[UI] Scenario set to: %s", name)

    def populate_peers(self, nodes: list[MeshNode]) -> None:
        """Refresh the peer list with routing-scored nodes."""
        self._peer_list.clear_widgets()
        for node in nodes:
            item = PeerListItem(node=node, score=node.routing_score)
            self._peer_list.add_widget(item)

    def log_hop(self, hop_idx: int, node_id: str, status: str) -> None:
        arrow = "→" if status == "TX" else "✔"
        text  = f"Hop {hop_idx + 1:02d} {arrow} {node_id}  [{status}]"
        self._hop_log.append_log(text)

    def set_broadcast_callback(self, cb) -> None:
        self._broadcast_cb = cb

    def set_broadcasting(self, active: bool) -> None:
        self._broadcasting = active
        self._sos_button.disabled = active
        self._sos_button.text = (
            "  ⏳  Broadcasting…  " if active else "  📡  BROADCAST SOS  "
        )

    # ── Internal handlers ─────────────────────────────────────────────────────

    def _on_sos_pressed(self, *_) -> None:
        if self._broadcasting:
            return
        if self._broadcast_cb:
            self._broadcast_cb(self.current_scenario)


# ── Right panel ───────────────────────────────────────────────────────────────

class RightPanel(MDCard):
    """
    Offline map panel (right half of dashboard).
    Hosts MapView and the satellite toggle toolbar.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding     = "8dp"
        self.spacing     = "6dp"
        self.elevation   = 4
        self.radius      = [12, 12, 12, 12]

        # ── Map toolbar ───────────────────────────────────────────────────────
        toolbar = MDBoxLayout(
            orientation = "horizontal",
            size_hint_y = None,
            height      = "48dp",
            spacing     = "12dp",
            padding     = ["8dp", "0dp"],
        )
        toolbar.add_widget(MDLabel(
            text       = "🗺  Offline Map",
            font_style = "Subtitle1",
            size_hint_x= 0.5,
        ))

        # Satellite toggle
        self._sat_label = MDLabel(
            text        = "Satellite",
            font_style  = "Caption",
            size_hint_x = None,
            width       = "70dp",
        )
        self._sat_switch = MDSwitch(
            size_hint_x = None,
            width       = "56dp",
        )
        self._sat_switch.bind(active=self._on_satellite_toggle)

        # Centre-path button
        self._centre_btn = MDIconButton(
            icon       = "crosshairs-gps",
            on_release = self._on_centre_pressed,
        )

        toolbar.add_widget(self._sat_label)
        toolbar.add_widget(self._sat_switch)
        toolbar.add_widget(self._centre_btn)
        self.add_widget(toolbar)

        # ── Map widget ────────────────────────────────────────────────────────
        try:
            from kivy_garden.mapview import MapView as _MapView  # type: ignore
            self._map_view = _MapView(
                lat        = 34.0522,
                lon        = -118.2437,
                zoom       = 13,
                size_hint  = (1, 1),
            )
        except ImportError:
            # Fallback placeholder when mapview garden package is absent
            from kivy.uix.label import Label
            self._map_view = Label(
                text             = "[Map not available — install kivy_garden.mapview]",
                color            = (0.5, 0.5, 0.5, 1),
                halign           = "center",
            )

        self.add_widget(self._map_view)

        # ── Internal state ────────────────────────────────────────────────────
        self._map_mgr   : Optional[MapManager] = None
        self._sat_toggle_cb  = None
        self._centre_cb      = None

    # ── Public API ────────────────────────────────────────────────────────────

    def init_map_manager(self) -> None:
        self._map_mgr = MapManager(self._map_view)

    def set_satellite_callback(self, cb) -> None:
        self._sat_toggle_cb = cb

    def set_centre_callback(self, cb) -> None:
        self._centre_cb = cb

    @property
    def map_manager(self) -> Optional[MapManager]:
        return self._map_mgr

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _on_satellite_toggle(self, switch, value: bool) -> None:
        if self._map_mgr:
            self._map_mgr.toggle_satellite(value)
        if self._sat_toggle_cb:
            self._sat_toggle_cb(value)
        mode_str = "Satellite 🛰" if value else "Standard 🗺"
        Snackbar(text=f"Map mode: {mode_str}", duration=1.5).open()

    def _on_centre_pressed(self, *_) -> None:
        if self._centre_cb:
            self._centre_cb()


# ── Root widget ───────────────────────────────────────────────────────────────

class MeshNetRootWidget(MDBoxLayout):
    """
    Top-level widget.  Wires all sub-components together and owns the
    RoutingEngine, BroadcastEngine, and HandshakeLogger instances.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.spacing     = "8dp"
        self.padding     = "8dp"

        # ── Engine instances ──────────────────────────────────────────────────
        self._routing_engine  = RoutingEngine()
        self._hs_logger       = HandshakeLogger()
        self._broadcast_engine= BroadcastEngine(self._hs_logger)

        # ── Panel widgets ─────────────────────────────────────────────────────
        self._left  = LeftPanel(size_hint_x=0.38)
        self._right = RightPanel(size_hint_x=0.62)
        self.add_widget(self._left)
        self.add_widget(self._right)

        # ── Wire callbacks ────────────────────────────────────────────────────
        self._left.set_broadcast_callback(self._on_broadcast_sos)
        self._right.set_satellite_callback(self._on_sat_toggle)
        self._right.set_centre_callback(self._on_centre_path)

        # ── State ─────────────────────────────────────────────────────────────
        self._current_result = None
        self._nodes          = []

        # ── Deferred init (map must be added to the window first) ─────────────
        Clock.schedule_once(self._post_init, 0.2)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _post_init(self, dt) -> None:
        """Called one frame after the widget tree is ready."""
        self._right.init_map_manager()
        self._refresh_topology()
        # Poll hardware state every 5 s and update status bar
        Clock.schedule_interval(self._poll_hardware, 5.0)
        # Refresh log count every 10 s
        Clock.schedule_interval(self._refresh_log_count, 10.0)
        self._refresh_log_count(0)
        logger.info("[UI] MeshNetRootWidget initialised.")

    def shutdown(self) -> None:
        """Called by MeshNetApp.on_stop()."""
        self._broadcast_engine.abort()

    # ── Routing & peer refresh ────────────────────────────────────────────────

    def _refresh_topology(self) -> None:
        """Compute a fresh routing result and push it to all UI elements."""
        self._nodes          = mock_topology()
        self._current_result = self._routing_engine.compute(self._nodes)

        # Update peer list
        self._left.populate_peers(self._current_result.stable_nodes)

        # Update map
        mgr = self._right.map_manager
        if mgr:
            mgr.update_nodes(self._current_result.stable_nodes)
            mgr.draw_path(
                self._nodes,
                self._current_result.optimal_path,
                is_hq=self._current_result.hq_anchor is not None,
            )

        logger.info(
            "[UI] Topology refreshed. %d stable nodes, %d-hop path.",
            len(self._current_result.stable_nodes),
            len(self._current_result.optimal_path),
        )

    # ── SOS broadcast ─────────────────────────────────────────────────────────

    def _on_broadcast_sos(self, scenario: str) -> None:
        """Triggered by LeftPanel SOS button — runs in main thread briefly."""
        if self._current_result is None or not self._current_result.optimal_path:
            Snackbar(text="⚠  No stable route available!", duration=2).open()
            return

        self._left.set_broadcasting(True)
        self._left._hop_log.clear_log()

        cfg     = SCENARIOS[scenario]
        max_hop = cfg["max_hops"]
        path    = self._current_result.optimal_path[:max_hop]

        packet = SOSPacket(
            scenario    = scenario,
            message     = (
                f"[{scenario.upper()}] EMERGENCY SOS — MeshNet-AI node. "
                f"Path quality: {self._current_result.path_quality:.2%}. "
                f"HQ anchor: {self._current_result.hq_anchor or 'none'}."
            ),
            origin_node = path[0] if path else "LOCAL",
            path        = path,
        )

        logger.info("[UI] SOS broadcast launched. Scenario=%s Hops=%d", scenario, len(path))

        self._broadcast_engine.broadcast(
            packet,
            on_hop      = self._on_hop_event,
            on_complete = self._on_broadcast_complete,
        )

    def _on_hop_event(self, hop_idx: int, node_id: str, status: str) -> None:
        """Runs on main thread (scheduled by BroadcastEngine)."""
        self._left.log_hop(hop_idx, node_id, status)

    def _on_broadcast_complete(self, packet: SOSPacket, success: bool) -> None:
        """Runs on main thread."""
        self._left.set_broadcasting(False)
        msg = (
            f"  SOS delivered!  Packet: {packet.packet_id}"
            if success
            else f"  Broadcast aborted.  Packet: {packet.packet_id}"
        )
        Snackbar(text=msg, duration=3).open()
        self._refresh_log_count(0)
        logger.info("[UI] Broadcast complete: success=%s", success)

    # ── Hardware polling ──────────────────────────────────────────────────────

    def _poll_hardware(self, dt) -> None:
        app = MDApp.get_running_app()
        if hasattr(app, "_hw"):
            self._left.set_hardware_state(
                app.hw.bt_state,
                app.hw.wifi_state,
            )

    # ── Map callbacks ─────────────────────────────────────────────────────────

    def _on_sat_toggle(self, enabled: bool) -> None:
        logger.info("[UI] Satellite mode: %s", enabled)

    def _on_centre_path(self) -> None:
        if self._current_result and self._right.map_manager:
            self._right.map_manager.center_on_path(
                self._nodes,
                self._current_result.optimal_path,
            )

    # ── Log count ─────────────────────────────────────────────────────────────

    def _refresh_log_count(self, dt) -> None:
        count = self._hs_logger.record_count()
        self._left.set_log_count(count)
