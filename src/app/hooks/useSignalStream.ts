/**
 * useSignalStream — SSE consumer for real-time signal-flicker alerts
 * src/app/hooks/useSignalStream.ts
 *
 * Opens a persistent Server-Sent Events connection to the Express backend
 * (GET /api/signal/stream).  Every time the Python signal monitor detects
 * a 0 → ≥1 bar flicker on any mesh node, the backend pushes a JSON event
 * down this stream and this hook surfaces it as a React state update.
 *
 * The rescue dashboard subscribes here and renders an alert pop-up
 * instantly — zero polling latency.
 *
 * Usage
 * -----
 *   const { latestFlicker, flickerHistory, connected } = useSignalStream();
 */

import { useState, useEffect, useRef, useCallback } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface FlickerAlert {
  id:          string;
  nodeId:      string;
  nodeLabel:   string;
  prevSignal:  number;
  currSignal:  number;
  scenario:    string;
  burst:       boolean;
  detectedAt:  string;
  /** Client-side receipt timestamp for display */
  receivedAt:  number;
}

interface UseSignalStreamResult {
  /** Most recently received flicker (null before first flicker). */
  latestFlicker:  FlickerAlert | null;
  /** Ordered newest-first, capped at MAX_HISTORY. */
  flickerHistory: FlickerAlert[];
  /** Whether the SSE connection is currently open. */
  connected: boolean;
  /** Manually clear the latestFlicker banner. */
  dismiss: () => void;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const MAX_HISTORY  = 20;
/** Reconnect delay on unexpected close (ms). */
const RECONNECT_MS = 3_000;

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useSignalStream(
  apiBase?: string
): UseSignalStreamResult {
  const base = apiBase
    ?? (import.meta.env.VITE_API_BASE_URL as string | undefined)
    ?? "http://localhost:4000";

  const [latestFlicker,  setLatestFlicker]  = useState<FlickerAlert | null>(null);
  const [flickerHistory, setFlickerHistory] = useState<FlickerAlert[]>([]);
  const [connected,      setConnected]      = useState(false);

  const esRef      = useRef<EventSource | null>(null);
  const timerRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
    }

    const es = new EventSource(`${base}/api/signal/stream`);
    esRef.current = es;

    es.onopen = () => {
      if (mountedRef.current) setConnected(true);
    };

    es.onmessage = (e: MessageEvent) => {
      if (!mountedRef.current) return;
      try {
        const raw = JSON.parse(e.data as string) as Record<string, unknown>;

        // Ignore heartbeat pings and connection acknowledgements
        if (raw.type === "connected") return;

        const alert: FlickerAlert = {
          id:         (raw.id as string)         ?? crypto.randomUUID(),
          nodeId:     (raw.nodeId as string)      ?? "unknown",
          nodeLabel:  (raw.nodeLabel as string)   ?? "Unknown Node",
          prevSignal: (raw.prevSignal as number)  ?? 0,
          currSignal: (raw.currSignal as number)  ?? 0,
          scenario:   (raw.scenario as string)    ?? "earthquake",
          burst:      Boolean(raw.burst),
          detectedAt: (raw.detectedAt as string)  ?? new Date().toISOString(),
          receivedAt: Date.now(),
        };

        setLatestFlicker(alert);
        setFlickerHistory((prev) =>
          [alert, ...prev].slice(0, MAX_HISTORY)
        );
      } catch {
        // Malformed event — ignore
      }
    };

    es.onerror = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      es.close();
      esRef.current = null;
      // Reconnect after delay
      timerRef.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, RECONNECT_MS);
    };
  }, [base]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      esRef.current?.close();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [connect]);

  const dismiss = useCallback(() => setLatestFlicker(null), []);

  return { latestFlicker, flickerHistory, connected, dismiss };
}
