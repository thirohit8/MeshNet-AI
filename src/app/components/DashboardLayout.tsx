/**
 * DashboardLayout — Master dashboard layout for MeshNet AI
 *
 * Desktop two-column layout:
 *  LEFT  (380px) — Emergency SOS Input Portal + Disaster Control Panel
 *  RIGHT (flex)  — IBM Cloudant Node Map Canvas + Route strip + Activity log
 *
 * On narrow screens (< 768px) the layout stacks vertically and defers
 * to the existing mobile App.tsx tab navigation.
 *
 * Layer integration:
 *  Layer 1 → calls Layer 3 (/api/route) via useRouting hook
 *  Layer 4 data → loaded by useCloudantNodes (IBM Cloudant / local backend / seed)
 *  Signal flicker alerts → delivered via SSE through useSignalStream
 */

import SosInputPortal, { type SosPayload } from "./SosInputPortal";
import NodeMapCanvas from "./NodeMapCanvas";
import DisasterControlPanel, { type Scenario } from "./DisasterControlPanel";
import FlickerAlertBanner from "./FlickerAlertBanner";
import { useCloudantNodes, type CloudantNode } from "../hooks/useCloudantNodes";
import { useRouting } from "../hooks/useRouting";
import { useSignalStream } from "../hooks/useSignalStream";
import { Radio, Wifi, WifiOff, Database, AlertTriangle, Route, Signal, Zap } from "lucide-react";
import { useState } from "react";

// ─── Activity log ─────────────────────────────────────────────────────────────

interface LogEntry {
  id: string;
  time: string;
  type: string;
  message: string;
}

function makeEntry(type: string, message: string): LogEntry {
  const id = (typeof crypto !== "undefined" && crypto.randomUUID)
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return {
    id,
    time: new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    type,
    message,
  };
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function DashboardLayout() {
  const { nodes, loading, error, source, refresh } = useCloudantNodes(10_000);
  const { result: routeResult, loading: routeLoading, error: routeError, query: queryRoute } = useRouting();
  const { latestFlicker, flickerHistory, connected: sseConnected, dismiss: dismissFlicker } = useSignalStream();

  const [log, setLog] = useState<LogEntry[]>([
    makeEntry("system", "Dashboard initialized — IBM Cloudant sync active"),
  ]);

  // Disaster scenario state
  const [scenario,         setScenario]         = useState<Scenario>("earthquake");
  // Broadcast-active: true = all BLE nodes forced green on map
  const [broadcastActive,  setBroadcastActive]  = useState(false);
  // Clicked node for route source selection
  const [selectedNodeId,   setSelectedNodeId]   = useState<string | null>(null);

  const appendLog = (type: string, message: string) => {
    setLog((prev) => [makeEntry(type, message), ...prev].slice(0, 40));
  };

  // ── HQ Broadcast ──────────────────────────────────────────────────────────

  const handleBroadcast = () => {
    setBroadcastActive(true);
    appendLog(
      "broadcast",
      `DISASTER PROTOCOL BROADCASTED — Scenario: ${scenario.toUpperCase()} — All device radios forced into active BLE scanning mode`
    );
    // Reset broadcast visual after 10 s (nodes will naturally stay green
    // once the backend pushes updated bluetooth_status: true back)
    setTimeout(() => setBroadcastActive(false), 10_000);
  };

  // ── SOS sent ──────────────────────────────────────────────────────────────

  const handleSosSent = (payload: SosPayload) => {
    appendLog(
      payload.type,
      `SOS [${payload.type.toUpperCase()}] sent${payload.message ? `: "${payload.message}"` : ""}`
    );

    // Auto-query AI route: clicked node → last relay; fallback to first→last relay
    const relayNodes = nodes.filter((n) => n.role === "relay");
    const srcNode = selectedNodeId
      ? nodes.find((n) => n.node_id === selectedNodeId)
      : relayNodes[0];
    const tgtNode = relayNodes[relayNodes.length - 1];

    if (srcNode && tgtNode && srcNode.node_id !== tgtNode.node_id) {
      const scenarioMap: Record<string, Scenario> = {
        flood: "flood", war_zone: "war_zone", fire: "earthquake",
        medical: "earthquake", sos: "earthquake", evacuation: "earthquake",
      };
      queryRoute({
        source: srcNode.node_id,
        target: tgtNode.node_id,
        scenario: scenarioMap[payload.type] ?? scenario,
      }).then(() => {
        if (routeResult?.found) {
          appendLog("route", `Route found: ${routeResult.path.join(" → ")} (${routeResult.hops} hops)`);
        }
      });
    }
  };

  // ── Node click → select as route source ──────────────────────────────────

  const handleNodeClick = (node: CloudantNode) => {
    setSelectedNodeId((prev) => (prev === node.node_id ? null : node.node_id));
    appendLog("node", `Selected node: ${node.label} (${node.node_id}) — Signal ${node.signal}%`);
  };

  // ── Flicker alert → log entry ─────────────────────────────────────────────

  if (latestFlicker && log[0]?.id !== `flicker-${latestFlicker.id}`) {
    setLog((prev) => [
      {
        id:      `flicker-${latestFlicker.id}`,
        time:    new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        type:    "flicker",
        message: `FLICKER: ${latestFlicker.nodeLabel} — ${latestFlicker.prevSignal}% → ${latestFlicker.currSignal}% — HIGH-PRIORITY BURST`,
      },
      ...prev,
    ].slice(0, 40));
  }

  // Active BLE nodes count
  const bleActive = broadcastActive
    ? nodes.length
    : nodes.filter((n) => n.bluetooth_status).length;

  // Active route path (array of node_ids from routeResult)
  const activeRoutePath = routeResult?.found ? routeResult.path : [];

  return (
    <>
      {/* ── Signal-flicker alert pop-up (zero-delay, overlays everything) ── */}
      <FlickerAlertBanner
        alert={latestFlicker}
        onDismiss={dismissFlicker}
      />

      <div
        className="flex flex-col h-full min-h-screen"
        style={{
          background: "radial-gradient(ellipse at 30% 10%, #0F2347 0%, #060E1C 70%)",
          fontFamily: "Inter, sans-serif",
          // Push content below the flicker banner when it's visible
          paddingTop: latestFlicker ? "68px" : "0",
          transition: "padding-top 0.15s",
        }}
      >
        {/* ── Top bar ──────────────────────────────────────────────────────── */}
        <header
          className="shrink-0 flex items-center justify-between px-6 py-3 border-b"
          style={{ borderColor: "rgba(91,141,217,0.15)", background: "rgba(10,21,38,0.8)" }}
        >
          {/* Brand */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#F97316] flex items-center justify-center">
              <Radio size={16} className="text-white" strokeWidth={2.5} />
            </div>
            <div>
              <div
                className="text-base font-black text-[#E8EEF7] tracking-wider uppercase leading-none"
                style={{ fontFamily: "Barlow Condensed, sans-serif" }}
              >
                MeshNet AI
              </div>
              <div className="text-[9px] font-mono text-[#7B9CC4] tracking-widest uppercase">
                Emergency Routing · Command Dashboard
              </div>
            </div>
          </div>

          {/* Status pills */}
          <div className="flex items-center gap-3">
            {/* SSE stream status */}
            <div
              className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-mono uppercase border"
              style={{
                background:  sseConnected ? "rgba(34,197,94,0.1)"  : "rgba(239,68,68,0.08)",
                borderColor: sseConnected ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.2)",
                color:       sseConnected ? "#22C55E" : "#EF4444",
              }}
            >
              <Signal size={9} />
              {sseConnected ? "Stream live" : "Stream offline"}
            </div>

            {/* Flicker count */}
            {flickerHistory.length > 0 && (
              <div
                className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-mono uppercase border"
                style={{
                  background:  "rgba(239,68,68,0.1)",
                  borderColor: "rgba(239,68,68,0.25)",
                  color:       "#EF4444",
                }}
              >
                <Zap size={9} />
                {flickerHistory.length} flicker{flickerHistory.length !== 1 ? "s" : ""}
              </div>
            )}

            {/* Cloudant data source */}
            <div
              className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-mono uppercase border"
              style={{
                background: "rgba(91,141,217,0.1)",
                borderColor: "rgba(91,141,217,0.25)",
                color: "#7B9CC4",
              }}
            >
              <Database size={9} />
              {source === "cloudant"
                ? "IBM Cloudant"
                : source === "local-backend"
                ? "Local API"
                : "Seed Data"}
            </div>

            {/* AI Routing status pill */}
            <div
              className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-mono uppercase border"
              style={{
                background: routeResult?.found
                  ? "rgba(34,197,94,0.1)"
                  : routeLoading
                  ? "rgba(249,115,22,0.1)"
                  : "rgba(91,141,217,0.1)",
                borderColor: routeResult?.found
                  ? "rgba(34,197,94,0.25)"
                  : routeLoading
                  ? "rgba(249,115,22,0.25)"
                  : "rgba(91,141,217,0.25)",
                color: routeResult?.found ? "#22C55E" : routeLoading ? "#F97316" : "#7B9CC4",
              }}
            >
              <Route size={9} />
              {routeLoading
                ? "Routing…"
                : routeResult?.found
                ? `${routeResult.hops} hop route`
                : routeError
                ? "Router offline"
                : "AI Router"}
            </div>

            {/* Nodes online */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#22C55E]/10 border border-[#22C55E]/20">
              <div className="w-1.5 h-1.5 rounded-full bg-[#22C55E] animate-pulse" />
              <span className="text-[10px] font-mono text-[#22C55E] uppercase tracking-wider">
                {nodes.length} nodes
              </span>
            </div>

            {/* BLE count */}
            <div
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border"
              style={{
                background: bleActive > 0 ? "rgba(34,197,94,0.08)" : "rgba(75,85,99,0.15)",
                borderColor: bleActive > 0 ? "rgba(34,197,94,0.2)" : "rgba(75,85,99,0.3)",
              }}
            >
              {bleActive > 0 ? (
                <Wifi size={10} className="text-[#22C55E]" />
              ) : (
                <WifiOff size={10} className="text-[#4B5563]" />
              )}
              <span
                className="text-[10px] font-mono uppercase tracking-wider"
                style={{ color: bleActive > 0 ? "#22C55E" : "#4B5563" }}
              >
                {bleActive} BLE
              </span>
            </div>
          </div>
        </header>

        {/* ── Main grid ────────────────────────────────────────────────────── */}
        <div className="flex flex-1" style={{ overflow: "visible" }}>

          {/* LEFT — SOS Input Portal + Disaster Control Panel */}
          <aside
            className="shrink-0 flex flex-col border-r overflow-y-auto"
            style={{
              width: 360,
              minWidth: 320,
              borderColor: "rgba(91,141,217,0.15)",
              background: "rgba(11,29,58,0.6)",
              padding: "1.25rem",
              gap: "1.5rem",
              scrollbarWidth: "none",
            }}
          >
            {/* Disaster scenario + HQ broadcast */}
            <DisasterControlPanel
              activeScenario={scenario}
              onScenarioChange={(s) => {
                setScenario(s);
                appendLog("scenario", `Scenario changed to: ${s.replace("_", " ").toUpperCase()}`);
              }}
              onBroadcast={handleBroadcast}
            />

            {/* Divider */}
            <div className="border-t" style={{ borderColor: "rgba(91,141,217,0.12)" }} />

            {/* SOS Input Portal */}
            <SosInputPortal onSend={handleSosSent} />
          </aside>

          {/* RIGHT — Map + Route result + Activity log */}
          <main className="flex-1 flex flex-col gap-0" style={{ overflow: "visible" }}>

            {/* Selected node hint */}
            {selectedNodeId && (
              <div
                className="shrink-0 px-4 py-1.5 flex items-center gap-2 text-[10px] font-mono border-b"
                style={{
                  background: "rgba(249,115,22,0.06)",
                  borderColor: "rgba(249,115,22,0.2)",
                  color: "#F97316",
                }}
              >
                <Route size={10} />
                Route source: <strong>{selectedNodeId}</strong> — Send SOS to auto-route from this node
                <button
                  onClick={() => setSelectedNodeId(null)}
                  className="ml-auto text-[#7B9CC4] hover:text-[#E8EEF7]"
                  title="Clear selection"
                >
                  ✕
                </button>
              </div>
            )}

            {/* Map panel — overflow-hidden removed; Leaflet tile panes are
                absolutely positioned and get clipped by overflow:hidden.
                height:0 flex trick replaced with an explicit min-height so
                Leaflet always gets a measurable pixel box. */}
            <div
              className="flex-1 p-4"
              style={{ minHeight: 340, overflow: "visible" }}
            >
              <NodeMapCanvas
                nodes={nodes}
                loading={loading}
                error={error}
                source={source}
                onRefresh={refresh}
                activeRoutePath={activeRoutePath}
                broadcastActive={broadcastActive}
                onNodeClick={handleNodeClick}
              />
            </div>

            {/* Route result strip */}
            {routeResult && (
              <div
                className="shrink-0 border-t px-4 py-2 flex items-center gap-3"
                style={{
                  borderColor: "rgba(91,141,217,0.12)",
                  background: routeResult.found
                    ? "rgba(34,197,94,0.06)"
                    : "rgba(239,68,68,0.06)",
                }}
              >
                <Route
                  size={12}
                  style={{ color: routeResult.found ? "#22C55E" : "#EF4444", flexShrink: 0 }}
                />
                <div className="flex-1 min-w-0">
                  {routeResult.found ? (
                    <span className="text-[10px] font-mono text-[#22C55E] truncate block">
                      {routeResult.path.join(" → ")}
                      &nbsp;·&nbsp;
                      <span className="text-[#7B9CC4]">
                        {routeResult.hops} hop{routeResult.hops !== 1 ? "s" : ""}
                        &nbsp;·&nbsp;
                        ~{Math.round(routeResult.estimatedLatencyMs)} ms
                        &nbsp;·&nbsp;
                        scenario: {routeResult.scenario}
                      </span>
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono text-[#EF4444]">
                      No route: {routeResult.reason}
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Activity log strip */}
            <div
              className="shrink-0 border-t overflow-hidden"
              style={{
                borderColor: "rgba(91,141,217,0.12)",
                background: "rgba(6,14,28,0.7)",
                height: 120,
              }}
            >
              <div className="flex items-center gap-2 px-4 py-1.5 border-b" style={{ borderColor: "rgba(91,141,217,0.1)" }}>
                <AlertTriangle size={10} className="text-[#7B9CC4]" />
                <span className="text-[9px] font-mono uppercase tracking-widest text-[#7B9CC4]">
                  Activity Log
                </span>
                <span className="ml-auto text-[9px] font-mono text-[#7B9CC4]/40">
                  {log.length} entries
                </span>
              </div>
              <div
                className="overflow-y-auto px-4 py-1.5 flex flex-col gap-1"
                style={{ height: 84, scrollbarWidth: "none" }}
              >
                {log.map((entry) => (
                  <div key={entry.id} className="flex items-baseline gap-2 text-[10px] font-mono">
                    <span className="text-[#7B9CC4]/50 shrink-0">{entry.time}</span>
                    <span
                      className="uppercase shrink-0"
                      style={{
                        color:
                          entry.type === "sos" || entry.type === "war_zone"
                            ? "#EF4444"
                            : entry.type === "flicker"
                            ? "#EF4444"
                            : entry.type === "broadcast"
                            ? "#F97316"
                            : entry.type === "medical"
                            ? "#F97316"
                            : entry.type === "flood"
                            ? "#38BDF8"
                            : entry.type === "route"
                            ? "#22C55E"
                            : entry.type === "node"
                            ? "#7B9CC4"
                            : entry.type === "scenario"
                            ? "#A855F7"
                            : "#7B9CC4",
                      }}
                    >
                      [{entry.type}]
                    </span>
                    <span className="text-[#C4D5EC] truncate">{entry.message}</span>
                  </div>
                ))}
              </div>
            </div>
          </main>
        </div>
      </div>
    </>
  );
}
