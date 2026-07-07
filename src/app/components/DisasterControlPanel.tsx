/**
 * DisasterControlPanel — Scenario selector + HQ Emergency Broadcast
 * src/app/components/DisasterControlPanel.tsx
 *
 * Implements the spec requirement:
 *   "Rohit's Vision: Forces all background devices to activate scanning
 *    mode instantly — Disaster Protocol Broadcasted"
 *
 * Features
 * --------
 * • Three disaster scenario buttons (Flood, War Zone, Earthquake)
 * • Active scenario highlighted with scenario-appropriate colour
 * • TRIGGER HQ EMERGENCY BROADCAST button:
 *     - POSTs a critical SOS alert to the backend
 *     - Calls onBroadcast() so the map activates all BLE nodes instantly
 *     - Shows animated "Broadcasting…" state + confirmation
 * • Scenario stats strip (communication range, battery threshold)
 */

import { useState } from "react";
import { Waves, ShieldAlert, Activity, Radio, Zap, CheckCircle2 } from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

export type Scenario = "flood" | "war_zone" | "earthquake";

interface ScenarioConfig {
  id:          Scenario;
  label:       string;
  icon:        React.ReactNode;
  color:       string;
  rangeM:      number;
  description: string;
}

interface Props {
  activeScenario:    Scenario;
  onScenarioChange:  (s: Scenario) => void;
  /** Called when the HQ broadcast fires — parent activates all BLE nodes */
  onBroadcast:       () => void;
}

// ─── Scenario catalogue ───────────────────────────────────────────────────────

const SCENARIOS: ScenarioConfig[] = [
  {
    id:          "flood",
    label:       "Flood",
    icon:        <Waves size={18} />,
    color:       "#38BDF8",
    rangeM:      50,
    description: "Water attenuation · 50 m BLE radius",
  },
  {
    id:          "war_zone",
    label:       "War Zone",
    icon:        <ShieldAlert size={18} />,
    color:       "#EF4444",
    rangeM:      30,
    description: "RF jamming · 30 m BLE radius",
  },
  {
    id:          "earthquake",
    label:       "Quake",
    icon:        <Activity size={18} />,
    color:       "#F97316",
    rangeM:      70,
    description: "Open field · 70 m BLE radius",
  },
];

// ─── Component ────────────────────────────────────────────────────────────────

export default function DisasterControlPanel({
  activeScenario,
  onScenarioChange,
  onBroadcast,
}: Props) {
  const [broadcasting, setBroadcasting] = useState(false);
  const [confirmed,    setConfirmed]    = useState(false);

  const active = SCENARIOS.find((s) => s.id === activeScenario)!;

  const handleBroadcast = async () => {
    if (broadcasting) return;
    setBroadcasting(true);

    // POST critical alert to the backend
    try {
      await fetch(
        `${(import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:4000"}/api/alerts`,
        {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            type:     "sos",
            severity: "critical",
            message:  `HQ EMERGENCY BROADCAST — Scenario: ${activeScenario.toUpperCase()} — All device radios forced into active BLE scanning mode`,
          }),
        }
      );
    } catch {
      // Backend unreachable — UI proceeds anyway (offline-first)
    }

    onBroadcast();
    setBroadcasting(false);
    setConfirmed(true);
    setTimeout(() => setConfirmed(false), 4_000);
  };

  return (
    <div className="flex flex-col gap-3">

      {/* Header */}
      <div>
        <h3
          className="text-[10px] font-mono uppercase tracking-widest text-[#7B9CC4]"
        >
          Disaster Scenario
        </h3>
        <p className="text-[9px] text-[#7B9CC4]/60 mt-0.5 font-mono">
          Affects routing weights + BLE communication range
        </p>
      </div>

      {/* Scenario buttons */}
      <div className="grid grid-cols-3 gap-2">
        {SCENARIOS.map((s) => {
          const isActive = s.id === activeScenario;
          return (
            <button
              key={s.id}
              onClick={() => onScenarioChange(s.id)}
              className="rounded-xl p-2.5 flex flex-col items-center gap-1.5 border transition-all duration-150 active:scale-95"
              style={{
                background:   isActive ? `${s.color}18` : "rgba(19,43,90,0.7)",
                borderColor:  isActive ? `${s.color}55` : "rgba(91,141,217,0.15)",
                boxShadow:    isActive ? `0 0 16px ${s.color}25` : "none",
              }}
              title={s.description}
            >
              <div style={{ color: isActive ? s.color : "#7B9CC4" }}>
                {s.icon}
              </div>
              <span
                className="text-[10px] font-bold uppercase tracking-wider leading-none"
                style={{ color: isActive ? s.color : "#7B9CC4",
                         fontFamily: "Barlow Condensed, sans-serif" }}
              >
                {s.label}
              </span>
              <span className="text-[8px] font-mono" style={{ color: isActive ? s.color : "#7B9CC4" }}>
                {s.rangeM} m
              </span>
            </button>
          );
        })}
      </div>

      {/* Active scenario info strip */}
      <div
        className="rounded-xl px-3 py-2 flex items-center gap-3 border"
        style={{
          background:  `${active.color}08`,
          borderColor: `${active.color}25`,
        }}
      >
        <div style={{ color: active.color }}>{active.icon}</div>
        <div className="flex-1">
          <div className="text-[10px] font-mono" style={{ color: active.color }}>
            {active.label} Protocol Active
          </div>
          <div className="text-[9px] text-[#7B9CC4] mt-0.5">{active.description}</div>
        </div>
        <div
          className="text-[10px] font-mono px-2 py-0.5 rounded-full"
          style={{ background: `${active.color}15`, color: active.color }}
        >
          {active.rangeM} m range
        </div>
      </div>

      {/* HQ Broadcast button */}
      <button
        onClick={handleBroadcast}
        disabled={broadcasting}
        className="w-full rounded-xl flex items-center justify-center gap-2.5 font-black uppercase tracking-widest transition-all duration-200 active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed"
        style={{
          fontFamily: "Barlow Condensed, sans-serif",
          fontSize: "0.95rem",
          letterSpacing: "0.12em",
          padding: "0.875rem 1rem",
          background: confirmed
            ? "linear-gradient(135deg, #16A34A, #15803D)"
            : "linear-gradient(135deg, #DC2626, #B91C1C)",
          color: "#ffffff",
          boxShadow: confirmed
            ? "0 0 24px rgba(22,163,74,0.4)"
            : "0 0 28px rgba(239,68,68,0.45), 0 4px 12px rgba(0,0,0,0.3)",
          border: confirmed
            ? "1px solid rgba(22,163,74,0.5)"
            : "1px solid rgba(239,68,68,0.5)",
        }}
      >
        {confirmed ? (
          <>
            <CheckCircle2 size={18} />
            ALL NODES ACTIVATED
          </>
        ) : broadcasting ? (
          <>
            <Radio size={18} className="animate-pulse" />
            BROADCASTING…
          </>
        ) : (
          <>
            <Zap size={18} />
            TRIGGER HQ EMERGENCY BROADCAST
          </>
        )}
      </button>

      {/* Broadcast hint */}
      {!confirmed && !broadcasting && (
        <p className="text-[9px] text-[#7B9CC4]/50 text-center font-mono -mt-1">
          Forces all device radios into active BLE scanning mode
        </p>
      )}
    </div>
  );
}
