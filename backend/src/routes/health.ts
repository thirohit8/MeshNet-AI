/**
 * health.ts — Express + Python bridge health check
 * backend/src/routes/health.ts
 *
 * GET /api/health
 *   Reports liveness of both the Express layer (Layer 4) and the
 *   Python AI routing engine (Layer 3 / FastAPI on port 5050).
 *
 *   Response shape:
 *   {
 *     status:       "ok" | "degraded",   // degraded when Python is down
 *     nodeId:       string,
 *     uptime:       number,              // Express process uptime (s)
 *     timestamp:    string,              // ISO-8601
 *     python: {
 *       status:     "ok" | "unreachable",
 *       url:        string,              // PYTHON_ROUTER_URL
 *       nodeCount?: number,             // from Python /health
 *       edgeCount?: number,
 *       uptime?:    number,             // Python process uptime (s)
 *       error?:     string,             // only when unreachable
 *     }
 *   }
 */

import { Router } from "express";

export const healthRouter = Router();

const PYTHON_ROUTER_URL =
  process.env.PYTHON_ROUTER_URL ?? "http://localhost:5050";

healthRouter.get("/", async (_req, res) => {
  // ── Express layer (always available if this handler runs) ─────────────────
  const expressHealth = {
    status:    "ok" as const,
    nodeId:    process.env.NODE_ID ?? "unknown",
    uptime:    Math.floor(process.uptime()),
    timestamp: new Date().toISOString(),
  };

  // ── Python AI routing engine probe ────────────────────────────────────────
  let python: Record<string, unknown>;
  try {
    const upstream = await fetch(`${PYTHON_ROUTER_URL}/health`, {
      signal: AbortSignal.timeout(3_000),   // 3 s — fast liveness check
    });

    if (upstream.ok) {
      const data = await upstream.json() as {
        status?: string;
        nodeCount?: number;
        edgeCount?: number;
        uptime?: number;
      };
      python = {
        status:    "ok",
        url:       PYTHON_ROUTER_URL,
        nodeCount: data.nodeCount,
        edgeCount: data.edgeCount,
        uptime:    data.uptime,
      };
    } else {
      python = {
        status: "unreachable",
        url:    PYTHON_ROUTER_URL,
        error:  `HTTP ${upstream.status}`,
      };
    }
  } catch (err) {
    python = {
      status: "unreachable",
      url:    PYTHON_ROUTER_URL,
      error:  err instanceof Error ? err.message : "Unknown error",
    };
  }

  const overallStatus = python.status === "ok" ? "ok" : "degraded";

  res.status(overallStatus === "ok" ? 200 : 207).json({
    ...expressHealth,
    status: overallStatus,
    python,
  });
});
