import { Router, Request, Response } from "express";
import { v4 as uuidv4 } from "uuid";
import type { Alert, AlertType, AlertSeverity } from "../models/alert";
import { alertStmts, type AlertRow } from "../db";

export const alertsRouter = Router();

const VALID_TYPES = new Set<AlertType>(["sos", "medical", "safe", "hazard", "supply", "locate"]);

const severityMap: Record<AlertType, AlertSeverity> = {
  sos:     "critical",
  medical: "high",
  hazard:  "high",
  supply:  "medium",
  locate:  "medium",
  safe:    "low",
};

// ─── Helper: AlertRow → Alert ─────────────────────────────────────────────────

function rowToAlert(r: AlertRow): Alert {
  return {
    id:           r.id,
    type:         r.type as AlertType,
    severity:     r.severity as AlertSeverity,
    fromNodeId:   r.from_node_id,
    fromLabel:    r.from_label,
    message:      r.message ?? undefined,
    lat:          r.lat ?? undefined,
    lng:          r.lng ?? undefined,
    ttl:          r.ttl,
    acknowledged: Boolean(r.acknowledged),
    createdAt:    r.created_at,
    expiresAt:    r.expires_at ?? undefined,
  };
}

// ─── GET /api/alerts ──────────────────────────────────────────────────────────

alertsRouter.get("/", (_req: Request, res: Response) => {
  const rows = alertStmts.getAll.all() as AlertRow[];
  res.json(rows.map(rowToAlert));
});

// ─── POST /api/alerts ─────────────────────────────────────────────────────────

alertsRouter.post("/", (req: Request, res: Response) => {
  const { type, fromNodeId, fromLabel, message, lat, lng } = req.body as Partial<Alert>;

  // SosInputPortal sends without fromNodeId / fromLabel — use sensible defaults
  const resolvedFromNodeId = fromNodeId ?? "dashboard";
  const resolvedFromLabel  = fromLabel  ?? "Dashboard";

  if (!type) {
    res.status(400).json({ error: "type is required" });
    return;
  }

  if (!VALID_TYPES.has(type as AlertType)) {
    res.status(400).json({
      error: `Invalid alert type '${type}'. Allowed: ${[...VALID_TYPES].join(", ")}`,
    });
    return;
  }

  const alertType = type as AlertType;
  const row: AlertRow = {
    id:           uuidv4(),
    type:         alertType,
    severity:     severityMap[alertType],
    from_node_id: resolvedFromNodeId,
    from_label:   resolvedFromLabel,
    message:      message ?? null,
    lat:          lat ?? null,
    lng:          lng ?? null,
    ttl:          7,
    acknowledged: 0,
    created_at:   new Date().toISOString(),
    expires_at:   null,
  };

  alertStmts.insert.run(row);
  res.status(201).json(rowToAlert(row));
});

// ─── PATCH /api/alerts/:id/acknowledge ────────────────────────────────────────

alertsRouter.patch("/:id/acknowledge", (req: Request, res: Response) => {
  const info = alertStmts.acknowledge.run(req.params.id);
  if (info.changes === 0) {
    res.status(404).json({ error: "Alert not found" });
    return;
  }
  res.json({ acknowledged: true });
});
