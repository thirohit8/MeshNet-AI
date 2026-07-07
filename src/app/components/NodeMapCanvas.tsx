/**
 * NodeMapCanvas — Live mesh map  (Leaflet + real OpenStreetMap tiles)
 *
 * Features:
 *  • Real OpenStreetMap tiles from /public/tiles/ (offline bundle) or live CDN
 *  • BLE-active edges as green dashed polylines on the real map
 *  • AI route overlay as orange polyline with travelling packet marker
 *  • Custom SVG DivIcons — colour-coded by BLE / relay status
 *  • Click-to-select node → detail card below map
 *  • broadcast-active mode forces all markers green
 *  • Graceful loading / error states
 */

import { useState, useMemo } from "react";
import type { ReactNode } from "react";
import type { CloudantNode } from "../hooks/useCloudantNodes";
import { Bluetooth, Battery, Signal, RefreshCw, Database, Wifi } from "lucide-react";
import LeafletMap from "./LeafletMap";

// ─── Palette ──────────────────────────────────────────────────────────────────

const COLOR_ON    = "#22C55E";
const COLOR_OFF   = "#4B5563";
const COLOR_RELAY = "#5B8DD9";
const COLOR_ROUTE = "#F97316";

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  nodes:            CloudantNode[];
  loading:          boolean;
  error:            string | null;
  source:           "cloudant" | "local-backend" | "seed";
  onRefresh?:       () => void;
  activeRoutePath?: string[];
  broadcastActive?: boolean;
  onNodeClick?:     (node: CloudantNode) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function NodeMapCanvas({
  nodes,
  loading,
  error,
  source,
  onRefresh,
  activeRoutePath = [],
  broadcastActive = false,
  onNodeClick,
}: Props): ReactNode {
  const [selected, setSelected] = useState<CloudantNode | null>(null);

  const effectiveNodes = useMemo(
    () => broadcastActive ? nodes.map((n) => ({ ...n, bluetooth_status: true })) : nodes,
    [nodes, broadcastActive],
  );

  const bleActiveCount = effectiveNodes.filter((n) => n.bluetooth_status).length;

  const sourceBadge: { label: string; color: string } = {
    cloudant:        { label: "IBM Cloudant", color: "#5B8DD9" },
    "local-backend": { label: "Local Backend", color: "#F97316" },
    seed:            { label: "Seed Data",     color: "#7B9CC4" },
  }[source];

  function handleNodeClick(node: CloudantNode) {
    setSelected((prev) => (prev?.node_id === node.node_id ? null : node));
    onNodeClick?.(node);
  }

  return (
    /* h-full so the map fills 100% of the dashboard panel height.
       If the parent has no explicit height (mobile tab), the fixed
       minHeight on the Leaflet wrapper below acts as the floor. */
    <div className="flex flex-col gap-3" style={{ height: "100%" }}>

      {/* ── Toolbar ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h2
            className="text-sm font-black text-[#E8EEF7] uppercase tracking-widest leading-none"
            style={{ fontFamily: "Barlow Condensed, sans-serif" }}
          >
            Live Mesh Map
          </h2>
          <p className="text-[10px] text-[#7B9CC4] mt-0.5 font-mono">
            {effectiveNodes.length} node{effectiveNodes.length !== 1 ? "s" : ""}
            &nbsp;·&nbsp;{bleActiveCount} BLE active
            {activeRoutePath.length > 1 && (
              <span className="text-[#F97316]">
                &nbsp;·&nbsp;route: {activeRoutePath.length - 1} hop{activeRoutePath.length > 2 ? "s" : ""}
              </span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Source badge */}
          <div
            className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-full text-[9px] font-mono uppercase tracking-wider border"
            style={{
              background:  `${sourceBadge.color}12`,
              borderColor: `${sourceBadge.color}30`,
              color:        sourceBadge.color,
            }}
          >
            <Database size={9} />
            {sourceBadge.label}
          </div>

          {/* Live pill */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#22C55E]/10 border border-[#22C55E]/20">
            <div className={`w-1.5 h-1.5 rounded-full bg-[#22C55E] ${loading ? "animate-pulse" : ""}`} />
            <span className="text-[10px] font-mono text-[#22C55E] uppercase tracking-wider">
              {loading ? "Syncing" : "Live"}
            </span>
          </div>

          {/* Refresh */}
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="w-7 h-7 rounded-lg bg-[#132B5A] border border-[rgba(91,141,217,0.2)] flex items-center justify-center active:scale-90 transition-transform"
              title="Refresh nodes"
            >
              <RefreshCw size={12} className="text-[#7B9CC4]" />
            </button>
          )}
        </div>
      </div>

      {/* ── Leaflet map canvas ───────────────────────────────────────────────── */}
      {/* flex-1 so the map grows to fill available height in the dashboard.
          minHeight 300 ensures the map is always visible on narrow screens.
          overflow:visible is required — overflow:hidden clips Leaflet panes. */}
      <div
        className="rounded-2xl border border-[rgba(91,141,217,0.2)] relative"
        style={{ flex: 1, minHeight: 300, overflow: "visible" }}
      >
        <LeafletMap
          nodes={effectiveNodes}
          activeRoutePath={activeRoutePath}
          broadcastActive={broadcastActive}
          onNodeClick={handleNodeClick}
          selectedNodeId={selected?.node_id ?? null}
        />

        {/* Error overlay */}
        {error && !loading && (
          <div className="absolute bottom-3 left-3 right-3 z-[1000] rounded-lg px-3 py-2 text-[10px] font-mono text-[#F97316] bg-[#F97316]/10 border border-[#F97316]/25 pointer-events-none">
            ⚠ {error}
          </div>
        )}

        {/* Empty state */}
        {!loading && effectiveNodes.length === 0 && (
          <div className="absolute inset-0 z-[1000] flex flex-col items-center justify-center gap-2 pointer-events-none">
            <div className="text-[#7B9CC4] text-xs font-mono">No nodes loaded</div>
            {onRefresh && (
              <button
                onClick={onRefresh}
                className="pointer-events-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#132B5A] border border-[rgba(91,141,217,0.25)] text-[10px] font-mono text-[#7B9CC4] hover:text-[#E8EEF7]"
              >
                <RefreshCw size={10} /> Retry
              </button>
            )}
          </div>
        )}
      </div>

      {/* ── Legend ───────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-4 gap-2">
        {([
          { dot: COLOR_ON,    label: "BLE Active",  sub: "green dot"  },
          { dot: COLOR_OFF,   label: "BLE Off",     sub: "grey dot"   },
          { dot: COLOR_RELAY, label: "Relay Node",  sub: "large ring" },
          { dot: COLOR_ROUTE, label: "AI Route",    sub: "orange path"},
        ] as const).map((l) => (
          <div key={l.label} className="flex items-center gap-2">
            <div
              className="w-3.5 h-3.5 rounded-full shrink-0"
              style={{ background: `${l.dot}25`, border: `2px solid ${l.dot}` }}
            />
            <div>
              <div className="text-[9px] font-semibold text-[#E8EEF7] leading-none">{l.label}</div>
              <div className="text-[8px] text-[#7B9CC4]">{l.sub}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Selected node detail card ─────────────────────────────────────────── */}
      {selected && (
        <div
          className="rounded-xl border p-3 flex items-start gap-3"
          style={{
            background: "#0F2040",
            borderColor: selected.bluetooth_status
              ? "rgba(34,197,94,0.3)"
              : "rgba(75,85,99,0.3)",
          }}
        >
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 mt-0.5"
            style={{
              background: selected.bluetooth_status ? "rgba(34,197,94,0.12)" : "rgba(75,85,99,0.12)",
              border: `1px solid ${selected.bluetooth_status ? "rgba(34,197,94,0.35)" : "rgba(75,85,99,0.35)"}`,
            }}
          >
            <Bluetooth size={18} style={{ color: selected.bluetooth_status ? COLOR_ON : COLOR_OFF }} />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-bold text-[#E8EEF7]" style={{ fontFamily: "Barlow Condensed, sans-serif" }}>
                {selected.label}
              </span>
              <span
                className="text-[9px] px-1.5 py-0.5 rounded-full uppercase tracking-wider font-mono"
                style={{
                  background: selected.bluetooth_status ? "rgba(34,197,94,0.15)" : "rgba(75,85,99,0.15)",
                  color: selected.bluetooth_status ? COLOR_ON : COLOR_OFF,
                }}
              >
                {selected.bluetooth_status ? "BLE ON" : "BLE OFF"}
              </span>
              <span
                className="text-[9px] px-1.5 py-0.5 rounded-full uppercase"
                style={{ background: "rgba(91,141,217,0.12)", color: "#5B8DD9" }}
              >
                {selected.role}
              </span>
            </div>

            <div className="text-[10px] text-[#7B9CC4] mt-0.5 font-mono">{selected.node_id}</div>

            <div className="grid grid-cols-3 gap-2 mt-2">
              <div className="flex items-center gap-1.5">
                <Signal size={11} className="text-[#7B9CC4] shrink-0" />
                <div>
                  <div className="text-[10px] font-mono text-[#E8EEF7]">{selected.signal}%</div>
                  <div className="text-[8px] text-[#7B9CC4]">signal</div>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <Battery size={11} className="text-[#7B9CC4] shrink-0" />
                <div>
                  <div
                    className="text-[10px] font-mono"
                    style={{ color: selected.battery_percentage > 60 ? "#22C55E" : selected.battery_percentage > 30 ? "#F97316" : "#EF4444" }}
                  >
                    {selected.battery_percentage}%
                  </div>
                  <div className="text-[8px] text-[#7B9CC4]">battery</div>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <Wifi size={11} className="text-[#7B9CC4] shrink-0" />
                <div>
                  <div className="text-[10px] font-mono text-[#E8EEF7]">{selected.device}</div>
                  <div className="text-[8px] text-[#7B9CC4]">device</div>
                </div>
              </div>
            </div>

            <div className="mt-2 text-[9px] font-mono text-[#7B9CC4]/70">
              {selected.latitude.toFixed(4)}°N · {selected.longitude.toFixed(4)}°E · bat {selected.battery_percentage}%
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
