/**
 * signal.ts — Signal-flicker detection and high-priority burst dispatch
 * backend/src/routes/signal.ts
 *
 * Implements the full signal-flicker pipeline described in the spec:
 *
 *   "If the signal goes from 0 bars to 1 bar (even for a moment), the app
 *    instantly executes a High-Priority Data Burst, bypassing all queue
 *    systems to push out buffered logs to the cloud."
 *
 * Endpoints
 * ---------
 * POST /api/signal/report
 *   Called by device heartbeats or the Python monitor when a node's
 *   signal is sampled.  On flicker detection a SignalFlickerEvent is
 *   persisted, an alert is raised, and all SSE subscribers are notified.
 *
 * GET  /api/signal/events?limit=50
 *   Returns recent flicker events for the rescue dashboard log.
 *
 * GET  /api/signal/stream
 *   Server-Sent Events stream — rescue dashboard subscribes here and
 *   receives a real-time push the split second a flicker is detected.
 */

import { Router, Request, Response } from "express";
import { v4 as uuidv4 } from "uuid";
import type { SignalSample, SignalFlickerEvent } from "../models/signal";
import type { SignalEventRow } from "../db";
import { signalEventStmts, alertStmts } from "../db";

export const signalRouter = Router();

// ─── Configuration ────────────────────────────────────────────────────────────

/**
 * A node is considered "no signal" when its RSSI-normalised value is at or
 * below this threshold.  The spec describes 0 bars, which maps to a raw
 * signal ≤ DEAD_THRESHOLD.
 *
 * Override via env var SIGNAL_DEAD_THRESHOLD (default: 5).
 */
const DEAD_THRESHOLD = parseInt(process.env.SIGNAL_DEAD_THRESHOLD ?? "5", 10);

/**
 * A flicker is declared when the signal rises above LIVE_THRESHOLD after
 * having been below DEAD_THRESHOLD.  Maps to "1 bar" in the spec.
 *
 * Override via env var SIGNAL_LIVE_THRESHOLD (default: 15).
 */
const LIVE_THRESHOLD = parseInt(process.env.SIGNAL_LIVE_THRESHOLD ?? "15", 10);

// ─── In-memory last-seen signal per node ─────────────────────────────────────
// We only need the previous sample to detect a 0→1 transition.
// This is intentionally ephemeral — a restart resets it, which is acceptable
// because the persistent record is the signal_events table.

const _prevSignal = new Map<string, number>();

// ─── SSE subscriber registry ─────────────────────────────────────────────────
// Each entry is the Response object of a connected SSE client (dashboard tab).

const _sseClients = new Set<Response>();

function _broadcast(event: SignalFlickerEvent): void {
  const data = `data: ${JSON.stringify(event)}\n\n`;
  for (const client of _sseClients) {
    try {
      client.write(data);
    } catch {
      // Client disconnected mid-write — remove on next iteration.
      _sseClients.delete(client);
    }
  }
}

// ─── Helper: row → model ──────────────────────────────────────────────────────

function rowToEvent(r: SignalEventRow): SignalFlickerEvent {
  return {
    id:         r.id,
    nodeId:     r.node_id,
    nodeLabel:  r.node_label,
    prevSignal: r.prev_signal,
    currSignal: r.curr_signal,
    scenario:   r.scenario,
    burst:      Boolean(r.burst),
    detectedAt: r.detected_at,
  };
}

// ─── POST /api/signal/report ──────────────────────────────────────────────────

signalRouter.post("/report", (req: Request, res: Response) => {
  const { nodeId, nodeLabel, signal, scenario, timestamp } =
    req.body as Partial<SignalSample>;

  if (!nodeId || signal === undefined || signal === null) {
    res.status(400).json({ error: "nodeId and signal are required" });
    return;
  }

  if (typeof signal !== "number" || signal < 0 || signal > 100) {
    res.status(400).json({ error: "signal must be a number between 0 and 100" });
    return;
  }

  const label    = nodeLabel ?? nodeId;
  const scene    = scenario  ?? "earthquake";
  const prevSig  = _prevSignal.get(nodeId) ?? signal;  // first report: no transition

  _prevSignal.set(nodeId, signal);

  // ── Flicker detection: was dead, now alive ──────────────────────────────────
  const wasDown = prevSig <= DEAD_THRESHOLD;
  const isUp    = signal  >  LIVE_THRESHOLD;

  if (!wasDown || !isUp) {
    // No flicker — acknowledge the sample and exit
    res.json({ flicker: false, nodeId, signal });
    return;
  }

  // ── FLICKER DETECTED — high-priority path ──────────────────────────────────
  const flickerEvent: SignalFlickerEvent = {
    id:         uuidv4(),
    nodeId,
    nodeLabel:  label,
    prevSignal: prevSig,
    currSignal: signal,
    scenario:   scene,
    burst:      false,
    detectedAt: timestamp ?? new Date().toISOString(),
  };

  // 1. Persist the flicker event
  const row: SignalEventRow = {
    id:          flickerEvent.id,
    node_id:     flickerEvent.nodeId,
    node_label:  flickerEvent.nodeLabel,
    prev_signal: flickerEvent.prevSignal,
    curr_signal: flickerEvent.currSignal,
    scenario:    flickerEvent.scenario,
    burst:       0,
    detected_at: flickerEvent.detectedAt,
  };
  signalEventStmts.insert.run(row);

  // 2. Raise a critical alert so it appears in the alerts feed
  alertStmts.insert.run({
    id:           uuidv4(),
    type:         "sos",
    severity:     "critical",
    from_node_id: nodeId,
    from_label:   label,
    message:      `Signal flicker on ${label}: ${prevSig}% → ${signal}% — high-priority burst initiated`,
    lat:          null,
    lng:          null,
    ttl:          7,
    acknowledged: 0,
    created_at:   flickerEvent.detectedAt,
    expires_at:   null,
  });

  // 3. Mark burst as dispatched (synchronous — we own the queue)
  signalEventStmts.markBurst.run(flickerEvent.id);
  flickerEvent.burst = true;

  // 4. Push to all SSE subscribers — zero-delay, bypasses queue
  _broadcast(flickerEvent);

  res.status(201).json({ flicker: true, event: flickerEvent });
});

// ─── GET /api/signal/events ───────────────────────────────────────────────────

signalRouter.get("/events", (req: Request, res: Response) => {
  const limit = Math.min(
    parseInt((req.query.limit as string | undefined) ?? "50", 10),
    200
  );
  const rows = signalEventStmts.getRecent.all(limit) as SignalEventRow[];
  res.json(rows.map(rowToEvent));
});

// ─── GET /api/signal/stream  (Server-Sent Events) ────────────────────────────
//
// The rescue dashboard connects here once.  Every time a flicker is detected
// on any node, `_broadcast()` pushes a JSON event down this stream — the
// dashboard renders an alert pop-up instantly without polling.

signalRouter.get("/stream", (req: Request, res: Response) => {
  // SSE headers — disable buffering so each write reaches the client immediately
  res.setHeader("Content-Type",  "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection",    "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");  // disable nginx proxy buffering
  res.flushHeaders();

  // Send a heartbeat comment every 25 s to keep the connection alive through
  // proxies and load-balancers that close idle keep-alives after 30 s.
  const heartbeat = setInterval(() => {
    try { res.write(": ping\n\n"); } catch { /* client gone */ }
  }, 25_000);

  _sseClients.add(res);

  // Send connection acknowledgement
  res.write(`data: ${JSON.stringify({ type: "connected", clientCount: _sseClients.size })}\n\n`);

  req.on("close", () => {
    clearInterval(heartbeat);
    _sseClients.delete(res);
  });
});
