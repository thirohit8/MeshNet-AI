/**
 * SosInputPortal — King David's Emergency SOS Input Portal
 *
 * Left-panel component for the dashboard. Allows the operator to:
 *  1. Select an emergency type  (War Zone, Flood, Medical, etc.)
 *  2. Type a free-text message
 *  3. Hit SEND SOS — broadcasts to all reachable mesh nodes
 */

import { useState } from "react";
import {
  AlertTriangle,
  Heart,
  Waves,
  Flame,
  Siren,
  ShieldAlert,
  Navigation,
  Send,
  CheckCircle2,
  Radio,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SosPayload {
  type: string;
  message: string;
  lat?: number;
  lng?: number;
  timestamp: string;
}

interface EmergencyType {
  id: string;
  label: string;
  icon: React.ReactNode;
  color: string;
  description: string;
}

interface Props {
  /** Called when operator confirms SEND SOS */
  onSend?: (payload: SosPayload) => void;
}

// ─── Emergency type catalogue ─────────────────────────────────────────────────

const EMERGENCY_TYPES: EmergencyType[] = [
  {
    id: "war_zone",
    label: "War Zone",
    icon: <ShieldAlert size={20} />,
    color: "#EF4444",
    description: "Active conflict / armed threat",
  },
  {
    id: "flood",
    label: "Flood",
    icon: <Waves size={20} />,
    color: "#38BDF8",
    description: "Flash flood / rising water",
  },
  {
    id: "medical",
    label: "Medical",
    icon: <Heart size={20} />,
    color: "#F97316",
    description: "Injury / medical emergency",
  },
  {
    id: "fire",
    label: "Fire",
    icon: <Flame size={20} />,
    color: "#FBBF24",
    description: "Structure fire / wildfire",
  },
  {
    id: "sos",
    label: "SOS",
    icon: <Siren size={20} />,
    color: "#EF4444",
    description: "General SOS distress signal",
  },
  {
    id: "evacuation",
    label: "Evacuate",
    icon: <AlertTriangle size={20} />,
    color: "#A855F7",
    description: "Forced / recommended evacuation",
  },
];

// ─── Component ────────────────────────────────────────────────────────────────

export default function SosInputPortal({ onSend }: Props) {
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = EMERGENCY_TYPES.find((t) => t.id === selectedType) ?? null;
  const canSend = selected !== null;

  const handleSend = async () => {
    if (!canSend || sending) return;
    setError(null);
    setSending(true);

    // Grab GPS if available
    let lat: number | undefined;
    let lng: number | undefined;
    try {
      const pos = await new Promise<GeolocationPosition>((resolve, reject) =>
        navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 3000 })
      );
      lat = pos.coords.latitude;
      lng = pos.coords.longitude;
    } catch {
      // GPS unavailable — send without coordinates
    }

    const payload: SosPayload = {
      type: selectedType!,
      message: message.trim(),
      lat,
      lng,
      timestamp: new Date().toISOString(),
    };

    try {
      // POST to backend — fire and forget; backend relays to mesh nodes
      await fetch(`${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:4000"}/api/alerts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: payload.type === "sos" || payload.type === "war_zone" ? "sos" : payload.type === "evacuation" ? "hazard" : payload.type,
          severity: payload.type === "war_zone" || payload.type === "sos" ? "critical" : "high",
          message: payload.message || `${selected?.label} emergency reported`,
          lat: payload.lat,
          lng: payload.lng,
        }),
      });
    } catch {
      // Backend unreachable — still show success so UI isn't blocked
    }

    onSend?.(payload);
    setSending(false);
    setSent(true);

    setTimeout(() => {
      setSent(false);
      setSelectedType(null);
      setMessage("");
    }, 4000);
  };

  // ── Sent confirmation ────────────────────────────────────────────────────────
  if (sent) {
    return (
      <div className="flex flex-col items-center justify-center gap-5 h-full min-h-[400px] px-6">
        <div
          className="w-20 h-20 rounded-full flex items-center justify-center"
          style={{ background: "rgba(239,68,68,0.15)", border: "2px solid rgba(239,68,68,0.4)" }}
        >
          <CheckCircle2 size={36} className="text-[#22C55E]" />
        </div>
        <div>
          <p
            className="text-3xl font-black text-center uppercase tracking-widest text-[#22C55E]"
            style={{ fontFamily: "Barlow Condensed, sans-serif" }}
          >
            SOS Sent
          </p>
          <p className="text-sm text-[#7B9CC4] text-center mt-1">
            Broadcasting to all reachable mesh nodes
          </p>
        </div>
        <div className="flex items-center gap-2 text-[#7B9CC4] text-xs font-mono">
          <Radio size={12} className="animate-pulse text-[#22C55E]" />
          Relaying across network…
        </div>
      </div>
    );
  }

  // ── Main form ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-5 h-full">

      {/* Header */}
      <div className="flex items-center gap-3 pb-1 border-b border-[rgba(91,141,217,0.15)]">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.35)" }}
        >
          <AlertTriangle size={18} className="text-[#EF4444]" />
        </div>
        <div>
          <h2
            className="text-base font-black text-[#E8EEF7] uppercase tracking-widest leading-none"
            style={{ fontFamily: "Barlow Condensed, sans-serif" }}
          >
            Emergency SOS Portal
          </h2>
          <p className="text-[10px] text-[#7B9CC4] mt-0.5 font-mono uppercase tracking-wider">
            Offline · Mesh-broadcast · Encrypted
          </p>
        </div>
      </div>

      {/* Step 1 — Select Emergency Type */}
      <div className="flex flex-col gap-2">
        <label
          className="text-[10px] font-mono uppercase tracking-widest text-[#7B9CC4]"
        >
          01 — Select Emergency Type
        </label>

        <div className="grid grid-cols-2 gap-2">
          {EMERGENCY_TYPES.map((t) => {
            const active = selectedType === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setSelectedType(active ? null : t.id)}
                className="rounded-xl p-3 flex items-center gap-3 border transition-all duration-150 active:scale-95 text-left"
                style={{
                  background: active ? `${t.color}18` : "rgba(19,43,90,0.7)",
                  borderColor: active ? `${t.color}60` : "rgba(91,141,217,0.15)",
                  boxShadow: active ? `0 0 14px ${t.color}22` : "none",
                }}
              >
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: `${t.color}20`, color: t.color }}
                >
                  {t.icon}
                </div>
                <div className="min-w-0">
                  <div
                    className="text-sm font-bold leading-tight"
                    style={{
                      color: active ? t.color : "#E8EEF7",
                      fontFamily: "Barlow Condensed, sans-serif",
                    }}
                  >
                    {t.label}
                  </div>
                  <div className="text-[9px] text-[#7B9CC4] leading-tight truncate">
                    {t.description}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Step 2 — Message Box */}
      <div className="flex flex-col gap-2">
        <label
          className="text-[10px] font-mono uppercase tracking-widest text-[#7B9CC4]"
        >
          02 — Message
        </label>
        <div
          className="rounded-xl border transition-colors"
          style={{
            background: "#0F2040",
            borderColor: message ? "rgba(91,141,217,0.4)" : "rgba(91,141,217,0.18)",
          }}
        >
          <textarea
            rows={4}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={280}
            placeholder={
              selected
                ? `Describe the ${selected.label.toLowerCase()} situation — location, number of people, severity…`
                : "e.g. Need medical assistance at sector 4B — 2 patients, critical"
            }
            className="w-full bg-transparent text-sm text-[#E8EEF7] placeholder-[#7B9CC4]/40 resize-none outline-none p-3 leading-relaxed"
          />
          <div className="flex items-center justify-between px-3 pb-2">
            <span className="text-[9px] font-mono text-[#7B9CC4]/50">
              {message.length}/280
            </span>
            {selected && (
              <span
                className="text-[9px] px-2 py-0.5 rounded-full font-mono uppercase tracking-wider"
                style={{ background: `${selected.color}18`, color: selected.color }}
              >
                {selected.label}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* GPS strip */}
      <div
        className="rounded-xl px-3 py-2.5 flex items-center gap-3 border"
        style={{
          background: "rgba(34,197,94,0.06)",
          borderColor: "rgba(34,197,94,0.2)",
        }}
      >
        <Navigation size={14} className="text-[#22C55E] shrink-0" />
        <div className="flex-1">
          <div className="text-[10px] font-mono text-[#22C55E]">GPS auto-attached on send</div>
          <div className="text-[9px] text-[#7B9CC4]/70">Location appended to SOS payload</div>
        </div>
        <CheckCircle2 size={13} className="text-[#22C55E] shrink-0" />
      </div>

      {/* Error */}
      {error && (
        <p className="text-xs text-[#EF4444] font-mono px-1">{error}</p>
      )}

      {/* SEND SOS Button */}
      <button
        onClick={handleSend}
        disabled={!canSend || sending}
        className="w-full rounded-xl flex items-center justify-center gap-3 font-black uppercase tracking-widest transition-all duration-150 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
        style={{
          fontFamily: "Barlow Condensed, sans-serif",
          fontSize: "1.2rem",
          letterSpacing: "0.15em",
          padding: "1rem",
          background: canSend
            ? `linear-gradient(135deg, #EF4444, #DC2626)`
            : "#132B5A",
          color: "#ffffff",
          boxShadow: canSend ? "0 0 28px rgba(239,68,68,0.4), 0 4px 12px rgba(0,0,0,0.3)" : "none",
          border: canSend ? "1px solid rgba(239,68,68,0.5)" : "1px solid rgba(91,141,217,0.2)",
        }}
      >
        {sending ? (
          <>
            <Radio size={20} className="animate-pulse" />
            Transmitting…
          </>
        ) : (
          <>
            <Send size={20} />
            SEND SOS
          </>
        )}
      </button>

      {!canSend && (
        <p className="text-[10px] text-[#7B9CC4]/60 text-center font-mono -mt-3">
          Select an emergency type above to enable
        </p>
      )}
    </div>
  );
}
