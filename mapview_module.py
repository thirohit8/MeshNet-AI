"""
MeshNet-AI — mapview_module.py
===============================
Offline map rendering module built on ``kivy_garden.mapview``.

Provides:
  OfflineMapView         — MapView subclass locked to offline tile sources.
  OfflineTileProvider    — MapSource-compatible provider that reads tiles
                           from local device storage.
  NodeMarker             — Custom MapMarker representing a mesh peer.
  PathLayer              — MapLayer that draws the optimised routing path
                           as polylines on top of the map.
  MapManager             — High-level controller consumed by the GUI.

Tile directory layout expected on device
-----------------------------------------
<tiles_root>/
    standard/                     ← OpenStreetMap-style vector raster tiles
        {zoom}/
            {x}/
                {y}.png
    satellite/                    ← High-res satellite raster tiles
        {zoom}/
            {x}/
                {y}.png

The tile root defaults to:
  Android : <app_storage>/tiles/
  Desktop : ./tiles/  (relative to main.py)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from kivy.graphics import Color, Line, Ellipse
from kivy.uix.widget import Widget
from kivy.utils import platform
from kivy.properties import BooleanProperty, StringProperty, ListProperty

# kivy_garden.mapview — installed via garden or pip
try:
    from kivy_garden.mapview import (          # type: ignore
        MapView,
        MapSource,
        MapMarker,
        MapLayer,
    )
    _MAPVIEW_AVAILABLE = True
except ImportError:
    # Graceful stub so the module imports even without garden during CI
    _MAPVIEW_AVAILABLE = False
    from kivy.uix.floatlayout import FloatLayout as MapView      # type: ignore stub
    from kivy.uix.widget import Widget as MapLayer               # type: ignore stub
    from kivy.uix.widget import Widget as MapMarker              # type: ignore stub
    MapSource = None                                             # type: ignore stub

logger = logging.getLogger(__name__)


# ── Storage root ───────────────────────────────────────────────────────────────

def _tiles_root() -> str:
    if platform == "android":
        try:
            from android.storage import app_storage_path   # type: ignore
            return os.path.join(app_storage_path(), "tiles")
        except ImportError:
            pass
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiles")


TILES_ROOT = _tiles_root()


# ── Colour constants ───────────────────────────────────────────────────────────
_COLOR_PATH_NORMAL = (0.0, 0.85, 0.85, 0.9)      # cyan
_COLOR_PATH_HQ     = (1.0, 0.75, 0.0,  0.95)     # amber — Weather-HQ route
_COLOR_NODE_ACTIVE = (0.15, 0.9, 0.4,  1.0)      # green
_COLOR_NODE_HQ     = (1.0, 0.7, 0.0,   1.0)      # amber
_COLOR_NODE_LOW    = (0.9, 0.2, 0.2,   1.0)      # red  (< 30 % battery)


# ── Offline tile provider ──────────────────────────────────────────────────────

class OfflineTileProvider:
    """
    Builds a ``MapSource`` that resolves tiles from local storage.

    Parameters
    ----------
    mode : "standard" | "satellite"
    """

    _TILE_SIZE    = 256
    _MIN_ZOOM     = 1
    _MAX_ZOOM     = 18
    _ATTRIBUTION  = "© MeshNet-AI Offline Cache"

    def __init__(self, mode: str = "standard") -> None:
        self.mode     = mode
        self.tile_dir = os.path.join(TILES_ROOT, mode)

    def get_map_source(self) -> Optional[object]:
        """Return a configured MapSource or None if mapview unavailable."""
        if not _MAPVIEW_AVAILABLE or MapSource is None:
            logger.warning("[MAP] kivy_garden.mapview not available.")
            return None

        # MapSource accepts a url pattern or a cache_key / tile_url callable.
        # We pass a file:// URL pattern that Mapview will resolve per tile.
        url_pattern = (
            f"file://{self.tile_dir}/{{z}}/{{x}}/{{y}}.png"
        )
        source = MapSource(
            url          = url_pattern,
            cache_key    = f"offline_{self.mode}",
            tile_size    = self._TILE_SIZE,
            min_zoom     = self._MIN_ZOOM,
            max_zoom     = self._MAX_ZOOM,
            attribution  = self._ATTRIBUTION,
        )
        logger.info("[MAP] OfflineTileProvider built for mode=%s", self.mode)
        return source

    def tile_exists(self, z: int, x: int, y: int) -> bool:
        """Check whether a specific tile is present in local cache."""
        path = os.path.join(self.tile_dir, str(z), str(x), f"{y}.png")
        return os.path.isfile(path)


# ── Node marker ───────────────────────────────────────────────────────────────

if _MAPVIEW_AVAILABLE:
    class NodeMarker(MapMarker):                    # type: ignore[misc]
        """
        Custom MapMarker for a mesh peer.

        Extra properties
        ----------------
        node_id      : str
        battery_level: float
        is_hq        : bool   — carries Weather-HQ signal
        """
        node_id       = StringProperty("")
        battery_level = ListProperty([100.0])    # wrapped in list for Kivy compat
        is_hq         = BooleanProperty(False)

        def __init__(self, node_id: str, lat: float, lon: float,
                     battery: float = 100.0, is_hq: bool = False, **kwargs):
            super().__init__(lat=lat, lon=lon, **kwargs)
            self.node_id          = node_id
            self.battery_level[0] = battery
            self.is_hq            = is_hq

            # Colour-code the marker
            if is_hq:
                self.source = "assets/marker_hq.png"
            elif battery < 30.0:
                self.source = "assets/marker_low.png"
            else:
                self.source = "assets/marker_active.png"

else:
    class NodeMarker(Widget):    # type: ignore[no-redef]
        """Stub NodeMarker used when kivy_garden.mapview is absent."""
        def __init__(self, node_id="", lat=0.0, lon=0.0,
                     battery=100.0, is_hq=False, **kwargs):
            super().__init__(**kwargs)
            self.node_id = node_id


# ── Path layer ────────────────────────────────────────────────────────────────

if _MAPVIEW_AVAILABLE:
    class PathLayer(MapLayer):                      # type: ignore[misc]
        """
        Draws an optimised routing path as a polyline on the map.

        Usage
        -----
        layer = PathLayer()
        layer.set_path(coord_list, is_hq_route=True)
        map_view.add_layer(layer)
        """

        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self._coords: list[tuple[float, float]] = []
            self._is_hq  = False

        def set_path(
            self,
            coords : list[tuple[float, float]],   # [(lat, lon), …]
            is_hq  : bool = False,
        ) -> None:
            """Update the drawn path."""
            self._coords = coords
            self._is_hq  = is_hq
            self.canvas.clear()
            self._draw()

        def reposition(self) -> None:
            """Called by MapView on zoom/pan — redraw in screen coordinates."""
            self.canvas.clear()
            self._draw()

        def _draw(self) -> None:
            if len(self._coords) < 2:
                return
            mapview = self.parent
            if mapview is None:
                return

            color = _COLOR_PATH_HQ if self._is_hq else _COLOR_PATH_NORMAL
            points: list[float] = []
            for lat, lon in self._coords:
                sx, sy = mapview.get_window_xy_from(lat, lon, mapview.zoom)
                points += [sx, sy]

            with self.canvas:
                Color(*color)
                Line(points=points, width=3.0, joint="round", cap="round")

                # Draw node dots at each waypoint
                dot_r = 8
                for lat, lon in self._coords:
                    sx, sy = mapview.get_window_xy_from(lat, lon, mapview.zoom)
                    Color(*color)
                    Ellipse(
                        pos =(sx - dot_r / 2, sy - dot_r / 2),
                        size=(dot_r, dot_r),
                    )

else:
    class PathLayer(Widget):     # type: ignore[no-redef]
        """Stub PathLayer."""
        def set_path(self, coords, is_hq=False):
            pass
        def reposition(self):
            pass


# ── Map manager ───────────────────────────────────────────────────────────────

class MapManager:
    """
    High-level controller that wires OfflineTileProvider, NodeMarker,
    and PathLayer together, and exposes a clean API to the GUI.

    Parameters
    ----------
    map_widget : the MapView instance (or stub) created in meshnet.kv
    """

    def __init__(self, map_widget) -> None:
        self._map         = map_widget
        self._mode        = "standard"
        self._markers: list[NodeMarker] = []
        self._path_layer: Optional[PathLayer] = None

        self._std_provider = OfflineTileProvider("standard")
        self._sat_provider = OfflineTileProvider("satellite")

        if _MAPVIEW_AVAILABLE:
            self._apply_source(self._std_provider)
            self._path_layer = PathLayer()
            self._map.add_layer(self._path_layer)

    # ── Public API ────────────────────────────────────────────────────────────

    def toggle_satellite(self, enable: bool) -> None:
        """
        Switch between standard vector tiles and satellite raster tiles.
        ``enable=True`` → satellite mode.
        """
        provider = self._sat_provider if enable else self._std_provider
        self._mode = "satellite" if enable else "standard"
        if _MAPVIEW_AVAILABLE:
            self._apply_source(provider)
        logger.info("[MAP] Map mode switched to: %s", self._mode)

    def update_nodes(self, nodes: list) -> None:
        """
        Refresh peer markers on the map.
        *nodes* is a list of routing.MeshNode objects.
        """
        if not _MAPVIEW_AVAILABLE:
            return
        # Remove stale markers
        for m in self._markers:
            self._map.remove_marker(m)
        self._markers.clear()

        for node in nodes:
            marker = NodeMarker(
                node_id  = node.node_id,
                lat      = node.lat,
                lon      = node.lon,
                battery  = node.battery_level,
                is_hq    = node.has_weather_hq_signal,
            )
            self._map.add_marker(marker)
            self._markers.append(marker)

        logger.info("[MAP] Updated %d node markers.", len(self._markers))

    def draw_path(self, nodes: list, path: list[str], is_hq: bool = False) -> None:
        """
        Draw the optimised routing path on the map.

        Parameters
        ----------
        nodes : list of routing.MeshNode (for coordinate lookup)
        path  : ordered list of node_id strings from RoutingResult
        is_hq : True if the path carries a Weather-HQ signal
        """
        if not _MAPVIEW_AVAILABLE or self._path_layer is None:
            return

        coord_map = {n.node_id: (n.lat, n.lon) for n in nodes}
        coords    = [coord_map[nid] for nid in path if nid in coord_map]
        self._path_layer.set_path(coords, is_hq=is_hq)
        logger.info(
            "[MAP] Path drawn: %d waypoints, HQ=%s", len(coords), is_hq
        )

    def center_on_path(self, nodes: list, path: list[str]) -> None:
        """Pan/zoom the map to frame the routing path."""
        if not _MAPVIEW_AVAILABLE or not path:
            return
        coord_map = {n.node_id: (n.lat, n.lon) for n in nodes}
        coords = [coord_map[nid] for nid in path if nid in coord_map]
        if not coords:
            return
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        centre_lat = (min(lats) + max(lats)) / 2
        centre_lon = (min(lons) + max(lons)) / 2
        self._map.center_on(centre_lat, centre_lon)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _apply_source(self, provider: OfflineTileProvider) -> None:
        src = provider.get_map_source()
        if src is not None:
            self._map.map_source = src
