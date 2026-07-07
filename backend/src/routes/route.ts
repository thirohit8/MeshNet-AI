/**
 * route.ts — Express → Python AI routing bridge
 * backend/src/routes/route.ts
 *
 * This file is the Layer 4 → Layer 3 bridge: it proxies routing queries
 * from the frontend / other Express handlers to the Python FastAPI engine
 * (api_server.py / uvicorn on PYTHON_ROUTER_URL, default port 5050).
 *
 * Endpoints
 * ---------
 * POST /api/route
 *   Standard RouteEngine query (source, target, scenario).
 *   Proxies to Python POST /api/route.
 *
 * GET  /api/route/topology?scenario=earthquake
 *   Returns the weighted simulation graph for the frontend map overlay.
 *   Proxies to Python GET /api/simulation/topology.
 *
 * POST /api/route/ai-route
 *   Battery-prioritised Dijkstra + AES-256-GCM hop encryption.
 *   Proxies to Python POST /api/simulation/ai-route.
 *   Body: { source_node_id, message?, max_range_meters?, rescue_node_id? }
 *
 * All three routes return 503 with a structured error body when the Python
 * service is unreachable so the frontend can show a meaningful fallback.
 */

import { Router, Request, Response } from "express";

export const routeRouter = Router();

const PYTHON_ROUTER_URL =
  process.env.PYTHON_ROUTER_URL ?? "http://localhost:5050";

const VALID_SCENARIOS = new Set(["flood", "war_zone", "earthquake"]);

// ── Shared proxy helper ────────────────────────────────────────────────────────

async function proxyToPython(
  res: Response,
  upstreamUrl: string,
  init: RequestInit,
): Promise<void> {
  try {
    const upstream = await fetch(upstreamUrl, {
      ...init,
      signal: AbortSignal.timeout(10_000),
    });
    const data = await upstream.json();
    res.status(upstream.ok ? 200 : upstream.status).json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    res.status(503).json({
      error:  "Python AI routing service unreachable",
      detail: msg,
      hint:   `Ensure uvicorn is running: uvicorn api_server:app --port 5050 (PYTHON_ROUTER_URL=${PYTHON_ROUTER_URL})`,
    });
  }
}

// ── POST /api/route ── standard RouteEngine query ─────────────────────────────

routeRouter.post("/", async (req: Request, res: Response) => {
  const { source, target, scenario = "earthquake", max_hops } = req.body as {
    source?:   string;
    target?:   string;
    scenario?: string;
    max_hops?: number;
  };

  if (!source || !target) {
    res.status(400).json({ error: "source and target node IDs are required" });
    return;
  }
  if (!VALID_SCENARIOS.has(scenario)) {
    res.status(422).json({
      error: `Invalid scenario '${scenario}'. Use: flood, war_zone, earthquake`,
    });
    return;
  }

  await proxyToPython(res, `${PYTHON_ROUTER_URL}/api/route`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ source, target, scenario, max_hops }),
  });
});

// ── GET /api/route/topology ── weighted simulation graph for map overlay ───────

routeRouter.get("/topology", async (req: Request, res: Response) => {
  const scenario = (req.query.scenario as string | undefined) ?? "earthquake";

  if (!VALID_SCENARIOS.has(scenario)) {
    res.status(422).json({ error: `Invalid scenario '${scenario}'` });
    return;
  }

  await proxyToPython(
    res,
    `${PYTHON_ROUTER_URL}/api/simulation/topology?scenario=${encodeURIComponent(scenario)}`,
    { method: "GET" },
  );
});

// ── POST /api/route/ai-route ── battery-prioritised Dijkstra + AES-256-GCM ────
//
// Bridges Express (Layer 4) → Python RoutingEngine (Layer 2/3).
// The Python side loads the offline mesh from SQLite, runs the AI routing
// algorithm, and returns the encrypted HopPacket chain.
//
// Body (JSON):
//   source_node_id   : number  — citizen node ID (1–99)
//   message          : string  — plaintext SOS payload (optional)
//   max_range_meters : number  — BLE/WiFi radius in metres (default: 100)
//   rescue_node_id   : number  — override rescue target (default: 100)

routeRouter.post("/ai-route", async (req: Request, res: Response) => {
  const {
    source_node_id,
    message        = "",
    max_range_meters = 100,
    rescue_node_id,
  } = req.body as {
    source_node_id?:  number;
    message?:         string;
    max_range_meters?: number;
    rescue_node_id?:  number;
  };

  if (source_node_id === undefined || typeof source_node_id !== "number") {
    res.status(400).json({ error: "source_node_id (number) is required" });
    return;
  }

  await proxyToPython(res, `${PYTHON_ROUTER_URL}/api/simulation/ai-route`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({
      source_node_id,
      message,
      max_range_meters,
      rescue_node_id,
    }),
  });
});
