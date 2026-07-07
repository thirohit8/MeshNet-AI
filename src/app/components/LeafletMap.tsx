/**
 * LeafletMap.tsx
 * ─────────────────────────────────────────────────────────────────────────────
 * Real-map Leaflet layer for NodeMapCanvas.
 *
 * Features
 * ────────
 *  • OpenStreetMap tiles served from /public/tiles/{z}/{x}/{y}.png  (offline)
 *  • Falls back to tile.openstreetmap.org when the local bundle is absent
 *  • BLE-active edges rendered as green animated Polylines
 *  • Inactive edges rendered as grey dashed Polylines
 *  • AI route overlay as orange bold Polyline with blinking packet dot
 *  • Custom SVG DivIcon per node — colour-coded by BLE/relay status
 *  • Click-to-select node → fires onNodeClick
 *  • broadcast-active mode forces every marker green
 *  • Map auto-fits to node bounds on first load
 *
 * Tile URL strategy (tries local first, falls back to OSM CDN):
 *   /tiles/{z}/{x}/{y}.png  ← run scripts/download-tiles.mjs once
 *   https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png  ← live fallback
 *
 * Attribution: © OpenStreetMap contributors  (required by tile licence)
 */

import { useEffect, useRef, useMemo } from "react";
import type { ReactNode } from "react";
import L from "leaflet";
import type { CloudantNode } from "../hooks/useCloudantNodes";

// ── Fix Leaflet's default icon paths broken by Vite bundling ─────────────────
delete (L.Icon.Default.prototype as Record<string, unknown>)._getIconUrl;

// ── Colour palette ────────────────────────────────────────────────────────────
const C_ON    = "#22C55E";
const C_OFF   = "#4B5563";
const C_RELAY = "#5B8DD9";
const C_ROUTE = "#F97316";

// ── Node SVG icon factory ─────────────────────────────────────────────────────

function makeIcon(ble: boolean, isRelay: boolean, isSelected: boolean): L.DivIcon {
  const r      = isRelay ? 11 : 8;
  const size   = (r + (isSelected ? 10 : 6)) * 2;
  const cx     = size / 2;
  const fill   = ble ? (isRelay ? C_RELAY : C_ON) : C_OFF;
  const ring   = isSelected ? C_ROUTE : (ble ? fill : C_OFF);
  const rOuter = r + (isSelected ? 8 : 4);

  const svg = `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"
    xmlns="http://www.w3.org/2000/svg">
    ${isRelay ? `<circle cx="${cx}" cy="${cx}" r="${rOuter}"
      fill="none" stroke="${ring}" stroke-width="${isSelected ? 2.5 : 1.5}" opacity="0.7"/>` : ""}
    ${isSelected ? `<circle cx="${cx}" cy="${cx}" r="${rOuter + 4}"
      fill="none" stroke="${C_ROUTE}" stroke-width="2" opacity="0.5"/>` : ""}
    <circle cx="${cx}" cy="${cx}" r="${r}"
      fill="${fill}25" stroke="${fill}" stroke-width="${isSelected ? 3 : 2.5}"
      ${ble ? `filter="drop-shadow(0 0 4px ${fill}99)"` : ""}/>
    <circle cx="${cx}" cy="${cx}" r="${r * 0.36}" fill="${fill}"/>
  </svg>`;

  return L.divIcon({
    html: svg,
    className: "",
    iconSize:    [size, size],
    iconAnchor:  [cx, cx],
    popupAnchor: [0, -(r + 6)],
  });
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  nodes:            CloudantNode[];
  activeRoutePath?: string[];
  broadcastActive?: boolean;
  onNodeClick?:     (node: CloudantNode) => void;
  selectedNodeId?:  string | null;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function LeafletMap({
  nodes,
  activeRoutePath = [],
  broadcastActive = false,
  onNodeClick,
  selectedNodeId,
}: Props): ReactNode {
  const divRef       = useRef<HTMLDivElement>(null);
  const mapRef       = useRef<L.Map | null>(null);
  const markersRef   = useRef<Map<string, L.Marker>>(new Map());
  const edgesRef     = useRef<L.Polyline[]>([]);
  const routeRef     = useRef<L.Polyline | null>(null);
  const packetRef    = useRef<L.CircleMarker | null>(null);
  const packetRafRef = useRef<number>(0);
  const fittedRef    = useRef(false);

  // Effective nodes: broadcast forces all BLE on
  const effective = useMemo(
    () => broadcastActive ? nodes.map((n) => ({ ...n, bluetooth_status: true })) : nodes,
    [nodes, broadcastActive],
  );

  // ── Initialise map — deferred via ResizeObserver so we wait for real size ───
  // The old approach (useEffect + clientHeight guard) fired at 0px and never
  // retried. Now we watch the container and init as soon as it has pixels.
  useEffect(() => {
    const el = divRef.current;
    if (!el) return;

    function tryInit() {
      if (mapRef.current) return;           // already initialised
      if (!divRef.current) return;
      if (divRef.current.clientHeight < 10) return;  // still no size

      const map = L.map(divRef.current, {
        zoomControl:        true,
        attributionControl: true,
        center:             [14.5995, 120.9842],  // Manila
        zoom:               13,
        maxZoom:            17,
      });

      // Tile layer: local offline → OSM CDN fallback
      const localTile = L.tileLayer("/tiles/{z}/{x}/{y}.png", {
        minZoom:       12,
        maxZoom:       17,
        maxNativeZoom: 17,
        attribution:   '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        errorTileUrl:  "",
      });

      const osmTile = L.tileLayer(
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
          minZoom:     1,
          maxZoom:     19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        },
      );

      // Probe local tile — use OSM CDN if local bundle is absent
      const probe = new Image();
      probe.onload  = () => { localTile.addTo(map); };
      probe.onerror = () => { osmTile.addTo(map); };
      probe.src     = "/tiles/15/27394/15037.png";

      mapRef.current = map;
      ro.disconnect();  // stop observing once map is live
    }

    // Watch for the first time the container has real dimensions
    const ro = new ResizeObserver(tryInit);
    ro.observe(el);
    tryInit();  // also try immediately in case size is already available

    return () => {
      ro.disconnect();
      cancelAnimationFrame(packetRafRef.current);
      mapRef.current?.remove();
      mapRef.current = null;
      fittedRef.current = false;
    };
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Update markers whenever nodes/selection changes ─────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const seen = new Set<string>();

    for (const node of effective) {
      seen.add(node.node_id);
      const ble      = node.bluetooth_status;
      const isRelay  = node.role === "relay";
      const isSel    = node.node_id === selectedNodeId;
      const icon     = makeIcon(ble, isRelay, isSel);
      const latlng   = L.latLng(node.latitude, node.longitude);

      let marker = markersRef.current.get(node.node_id);
      if (!marker) {
        marker = L.marker(latlng, { icon })
          .addTo(map)
          .bindTooltip(
            `<b>${node.label}</b><br/>
             ${node.role} · ${ble ? "BLE ON" : "BLE OFF"}<br/>
             Battery ${node.battery_percentage}% · Signal ${node.signal}%`,
            { direction: "top", offset: [0, -4], className: "meshnet-tip" },
          );
        const captured = node;
        marker.on("click", () => onNodeClick?.(captured));
        markersRef.current.set(node.node_id, marker);
      } else {
        marker.setLatLng(latlng);
        marker.setIcon(icon);
        marker.setTooltipContent(
          `<b>${node.label}</b><br/>
           ${node.role} · ${ble ? "BLE ON" : "BLE OFF"}<br/>
           Battery ${node.battery_percentage}% · Signal ${node.signal}%`,
        );
        marker.off("click");
        const captured = node;
        marker.on("click", () => onNodeClick?.(captured));
      }
    }

    // Remove stale markers
    for (const [id, marker] of markersRef.current) {
      if (!seen.has(id)) {
        marker.remove();
        markersRef.current.delete(id);
      }
    }

    // Auto-fit bounds on first load
    if (!fittedRef.current && effective.length > 0) {
      const latlngs = effective.map((n) => L.latLng(n.latitude, n.longitude));
      map.fitBounds(L.latLngBounds(latlngs), { padding: [48, 48], maxZoom: 16 });
      fittedRef.current = true;
    }
  }, [effective, selectedNodeId, onNodeClick]);

  // ── Draw BLE edges between nearby nodes ─────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    edgesRef.current.forEach((p) => p.remove());
    edgesRef.current = [];

    const MAX_DEG = 0.006;
    for (let i = 0; i < effective.length; i++) {
      for (let j = i + 1; j < effective.length; j++) {
        const a = effective[i];
        const b = effective[j];
        if (Math.abs(a.latitude  - b.latitude)  > MAX_DEG) continue;
        if (Math.abs(a.longitude - b.longitude) > MAX_DEG) continue;

        const bothBle = a.bluetooth_status && b.bluetooth_status;
        edgesRef.current.push(
          L.polyline(
            [L.latLng(a.latitude, a.longitude), L.latLng(b.latitude, b.longitude)],
            {
              color:     bothBle ? C_ON : C_OFF,
              weight:    bothBle ? 2 : 1,
              opacity:   bothBle ? 0.55 : 0.2,
              dashArray: bothBle ? "8, 5" : "4, 7",
            },
          ).addTo(map),
        );
      }
    }
  }, [effective]);

  // ── AI route overlay + animated packet dot ───────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    routeRef.current?.remove();   routeRef.current = null;
    packetRef.current?.remove();  packetRef.current = null;
    cancelAnimationFrame(packetRafRef.current);

    if (activeRoutePath.length < 2) return;

    const nodeById = new Map(effective.map((n) => [n.node_id, n]));
    const routeLatLngs: L.LatLng[] = [];
    for (const id of activeRoutePath) {
      const n = nodeById.get(id);
      if (n) routeLatLngs.push(L.latLng(n.latitude, n.longitude));
    }
    if (routeLatLngs.length < 2) return;

    routeRef.current = L.polyline(routeLatLngs, {
      color: C_ROUTE, weight: 4, opacity: 0.9,
    }).addTo(map);

    packetRef.current = L.circleMarker(routeLatLngs[0], {
      radius: 6, color: "#FFFFFF", fillColor: "#FFFFFF", fillOpacity: 0.95, weight: 2,
    }).addTo(map);

    let t = 0;
    const totalSegs = routeLatLngs.length - 1;
    const SPEED = 0.008;

    function tick() {
      t = (t + SPEED) % 1;
      const globalT = t * totalSegs;
      const segIdx  = Math.floor(globalT) % totalSegs;
      const localT  = globalT - Math.floor(globalT);
      const a = routeLatLngs[segIdx];
      const b = routeLatLngs[segIdx + 1];
      packetRef.current?.setLatLng([
        a.lat + (b.lat - a.lat) * localT,
        a.lng + (b.lng - a.lng) * localT,
      ]);
      packetRafRef.current = requestAnimationFrame(tick);
    }
    packetRafRef.current = requestAnimationFrame(tick);

    return () => { cancelAnimationFrame(packetRafRef.current); };
  }, [activeRoutePath, effective]);

  // ── Tooltip styles + Leaflet z-index fix ─────────────────────────────────────
  useEffect(() => {
    const id = "meshnet-tip-style";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `
      .meshnet-tip {
        background: #0F2040 !important;
        border: 1px solid rgba(91,141,217,0.35) !important;
        color: #E8EEF7 !important;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px !important;
        line-height: 1.5;
        border-radius: 6px !important;
        padding: 5px 8px !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.5) !important;
      }
      .meshnet-tip::before { display: none !important; }
      .leaflet-attribution-flag { display: none !important; }
      .leaflet-pane         { z-index: 400 !important; }
      .leaflet-tile-pane    { z-index: 200 !important; }
      .leaflet-overlay-pane { z-index: 400 !important; }
      .leaflet-marker-pane  { z-index: 600 !important; }
      .leaflet-tooltip-pane { z-index: 650 !important; }
      .leaflet-popup-pane   { z-index: 700 !important; }
      .leaflet-control      { z-index: 800 !important; }
    `;
    document.head.appendChild(style);
  }, []);

  // ── Invalidate map size on container resize ───────────────────────────────────
  useEffect(() => {
    const el = divRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      mapRef.current?.invalidateSize();
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div
      ref={divRef}
      style={{
        position: "relative",
        width:    "100%",
        height:   "100%",
        minHeight: 320,
      }}
    />
  );
}
