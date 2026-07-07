/**
 * FlickerAlertBanner — zero-delay signal-flicker alert pop-up
 * src/app/components/FlickerAlertBanner.tsx
 *
 * Renders the split second a signal-flicker event arrives on the SSE
 * stream.  Stacks at the top of the viewport so it overlays everything
 * and is impossible to miss on the rescue dashboard.
 *
 * Features
 * --------
 * • Auto-dismiss after 8 seconds (configurable via `autoDismissMs`)
 * • Manual dismiss via ✕ button
 * • Countdown progress bar so operators know how long the alert stays
 * • Shows node ID, previous signal (dead) → current signal (alive),
 *   scenario, and "HIGH-PRIORITY BURST INITIATED" confirmation
 */

import { useEffect, useRef, useState } from "react";
import { Zap, X, Radio, Signal } from "lucide-react";
import type { FlickerAlert } from "../hooks/useSignalStream";

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  alert:          FlickerAlert | null;
  onDismiss:      () => void;
  autoDismissMs?: number;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function FlickerAlertBanner({
  alert,
  onDismiss,
  autoDismissMs = 8_000,
}: Props) {
  const [progress, setProgress] = useState(100);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef    = useRef<ReturnType<typeof setTimeout>  | null>(null);

  // Reset and start countdown when a new alert arrives
  useEffect(() => {
    if (!alert) {
      setProgress(100);
      return;
    }

    setProgress(100);
    const step  = 100 / (autoDismissMs / 50);

    intervalRef.current = setInterval(() => {
      setProgress((p) => Math.max(0, p - step));
    }, 50);

    timerRef.current = setTimeout(() => {
      onDismiss();
    }, autoDismissMs);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (timerRef.current)    clearTimeout(timerRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alert?.id]);

  if (!alert) return null;

  const signalColor = alert.currSignal > 60
    ? "#22C55E"
    : alert.currSignal > 30
    ? "#F97316"
    : "#EF4444";

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="fixed top-0 left-0 right-0 z-50 flex flex-col gap-0 shadow-2xl"
      style={{
        background: "linear-gradient(135deg, #1A0A00 0%, #1C0505 100%)",
        borderBottom: "2px solid #EF4444",
        boxShadow: "0 0 40px rgba(239,68,68,0.45), 0 4px 20px rgba(0,0,0,0.6)",
      }}
    >
      {/* Progress bar */}
      <div className="h-0.5 w-full bg-[#EF4444]/20">
        <div
          className="h-full bg-[#EF4444] transition-none"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Content */}
      <div className="flex items-start gap-4 px-5 py-3">

        {/* Icon */}
        <div
          className="shrink-0 w-11 h-11 rounded-xl flex items-center justify-center mt-0.5"
          style={{ background: "rgba(239,68,68,0.18)", border: "1px solid rgba(239,68,68,0.4)" }}
        >
          <Zap size={22} className="text-[#EF4444]" />
        </div>

        {/* Body */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="text-sm font-black text-[#EF4444] uppercase tracking-widest"
              style={{ fontFamily: "Barlow Condensed, sans-serif" }}
            >
              SIGNAL FLICKER DETECTED
            </span>
            <span
              className="text-[10px] px-2 py-0.5 rounded-full font-mono uppercase tracking-wider border border-[#EF4444]/40"
              style={{ background: "rgba(239,68,68,0.15)", color: "#EF4444" }}
            >
              HIGH-PRIORITY BURST
            </span>
          </div>

          <div className="flex items-center gap-4 mt-1.5 flex-wrap">
            {/* Node */}
            <span className="text-xs font-mono text-[#E8EEF7]">
              {alert.nodeLabel}
              <span className="text-[#7B9CC4] ml-1">({alert.nodeId})</span>
            </span>

            {/* Signal transition */}
            <div className="flex items-center gap-1.5">
              <Signal size={11} className="text-[#7B9CC4]" />
              <span className="text-xs font-mono">
                <span className="text-[#EF4444]">{alert.prevSignal}%</span>
                <span className="text-[#7B9CC4] mx-1">→</span>
                <span style={{ color: signalColor }}>{alert.currSignal}%</span>
              </span>
            </div>

            {/* Scenario */}
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-mono uppercase"
              style={{ background: "rgba(91,141,217,0.15)", color: "#7B9CC4" }}
            >
              {alert.scenario.replace("_", " ")}
            </span>
          </div>

          <div className="flex items-center gap-1.5 mt-1.5">
            <Radio size={10} className="text-[#22C55E] animate-pulse shrink-0" />
            <span className="text-[10px] font-mono text-[#22C55E]">
              Buffered logs flushed · Cloud sync initiated · Dashboard notified
            </span>
          </div>
        </div>

        {/* Dismiss */}
        <button
          onClick={onDismiss}
          className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center mt-0.5 transition-colors"
          style={{
            background: "rgba(239,68,68,0.12)",
            border: "1px solid rgba(239,68,68,0.25)",
          }}
          aria-label="Dismiss alert"
        >
          <X size={13} className="text-[#EF4444]" />
        </button>
      </div>
    </div>
  );
}
