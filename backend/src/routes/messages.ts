import { Router, Request, Response } from "express";
import { v4 as uuidv4 } from "uuid";
import type { MeshMessage } from "../models/message";
import { messageStmts, type MessageRow } from "../db";

export const messagesRouter = Router();

const VALID_CATEGORIES = new Set<MeshMessage["category"]>(["alert", "medical", "info", "gps"]);
const MAX_HOPS = 7;

// ─── Helper: MessageRow → MeshMessage ────────────────────────────────────────

function rowToMessage(r: MessageRow): MeshMessage {
  return {
    id:          r.id,
    fromNodeId:  r.from_node_id,
    fromLabel:   r.from_label,
    toNodeId:    r.to_node_id,
    category:    r.category as MeshMessage["category"],
    ciphertext:  r.ciphertext,
    createdAt:   r.created_at,
    read:        Boolean(r.read),
    hops:        r.hops,
  };
}

// ─── GET /api/messages?nodeId=xxx ─────────────────────────────────────────────

messagesRouter.get("/", (req: Request, res: Response) => {
  const { nodeId } = req.query;
  const rows = nodeId
    ? (messageStmts.getForNode.all(nodeId as string, nodeId as string) as MessageRow[])
    : (messageStmts.getAll.all() as MessageRow[]);
  res.json(rows.map(rowToMessage));
});

// ─── POST /api/messages ───────────────────────────────────────────────────────

messagesRouter.post("/", (req: Request, res: Response) => {
  const { fromNodeId, fromLabel, toNodeId, category, ciphertext, hops } =
    req.body as Partial<MeshMessage>;

  if (!fromNodeId || !fromLabel || !toNodeId || !ciphertext) {
    res.status(400).json({ error: "fromNodeId, fromLabel, toNodeId, and ciphertext are required" });
    return;
  }

  if (category && !VALID_CATEGORIES.has(category)) {
    res.status(400).json({
      error: `Invalid category '${category}'. Allowed: ${[...VALID_CATEGORIES].join(", ")}`,
    });
    return;
  }

  const hopCount = (hops ?? 0) + 1;
  if (hopCount > MAX_HOPS) {
    res.status(422).json({ error: `Packet exceeded max hops (${MAX_HOPS}) — dropped` });
    return;
  }

  const row: MessageRow = {
    id:           uuidv4(),
    from_node_id: fromNodeId,
    from_label:   fromLabel,
    to_node_id:   toNodeId,
    category:     category ?? "info",
    ciphertext,
    hops:         hopCount,
    read:         0,
    created_at:   new Date().toISOString(),
  };

  messageStmts.insert.run(row);
  res.status(201).json(rowToMessage(row));
});

// ─── PATCH /api/messages/:id/read ────────────────────────────────────────────

messagesRouter.patch("/:id/read", (req: Request, res: Response) => {
  const info = messageStmts.markRead.run(req.params.id);
  if (info.changes === 0) {
    res.status(404).json({ error: "Message not found" });
    return;
  }
  res.json({ read: true });
});
