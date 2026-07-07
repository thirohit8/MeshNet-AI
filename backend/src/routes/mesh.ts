import { Router, Request, Response } from "express";
import { v4 as uuidv4 } from "uuid";
import type { MeshNode, MeshEdge, MeshTopology } from "../models/node";
import { db, nodeStmts, edgeStmts, type NodeRow, type EdgeRow } from "../db";

export const meshRouter = Router();

// ─── Helper: NodeRow → MeshNode ───────────────────────────────────────────────

function rowToNode(r: NodeRow): MeshNode {
  return {
    id:                r.id,
    label:             r.label,
    name:              r.name,
    device:            r.device,
    role:              r.role,
    signal:            r.signal,
    batteryPercentage: r.battery_percentage,
    bluetoothStatus:   Boolean(r.bluetooth_status),
    lastSeen:          r.last_seen,
    os:                r.os ?? undefined,
    lat:               r.lat ?? undefined,
    lng:               r.lng ?? undefined,
  };
}

function rowToEdge(r: EdgeRow): MeshEdge {
  return { a: r.node_a, b: r.node_b, protocol: r.protocol, quality: r.quality };
}

// ─── GET /api/mesh/topology ───────────────────────────────────────────────────

meshRouter.get("/topology", (_req: Request, res: Response) => {
  const nodes  = (nodeStmts.getAll.all() as NodeRow[]).map(rowToNode);
  const edges  = (edgeStmts.getAll.all() as EdgeRow[]).map(rowToEdge);
  const topology: MeshTopology = { nodes, edges, updatedAt: new Date().toISOString() };
  res.json(topology);
});

// ─── POST /api/mesh/register ──────────────────────────────────────────────────

meshRouter.post("/register", (req: Request, res: Response) => {
  const {
    id, label, name, device, role,
    signal, batteryPercentage, bluetoothStatus,
    os, lat, lng,
  } = req.body as Partial<MeshNode>;

  if (!id || !label || !device) {
    res.status(400).json({ error: "id, label, and device are required" });
    return;
  }

  const row: NodeRow = {
    id,
    label,
    name:               name ?? label,
    device,
    role:               role ?? "peer",
    signal:             signal ?? 80,
    battery_percentage: batteryPercentage ?? 100,
    bluetooth_status:   bluetoothStatus ? 1 : 0,
    os:                 os ?? null,
    lat:                lat ?? null,
    lng:                lng ?? null,
    last_seen:          new Date().toISOString(),
    registered:         new Date().toISOString(),
  };

  nodeStmts.upsert.run(row);
  res.status(201).json({ registered: true, node: rowToNode(row) });
});

// ─── PATCH /api/mesh/nodes/:id/heartbeat ──────────────────────────────────────

meshRouter.patch("/nodes/:id/heartbeat", (req: Request, res: Response) => {
  const existing = nodeStmts.getById.get(req.params.id) as NodeRow | undefined;
  if (!existing) { res.status(404).json({ error: "Node not found" }); return; }

  const { signal, batteryPercentage, bluetoothStatus, lat, lng } = req.body as Partial<MeshNode>;

  nodeStmts.heartbeat.run({
    id:                existing.id,
    signal:            signal            ?? existing.signal,
    battery_percentage: batteryPercentage ?? existing.battery_percentage,
    bluetooth_status:  bluetoothStatus !== undefined ? (bluetoothStatus ? 1 : 0) : existing.bluetooth_status,
    lat:               lat ?? null,
    lng:               lng ?? null,
    last_seen:         new Date().toISOString(),
  });

  res.json({ updated: true });
});

// ─── POST /api/mesh/edges ─────────────────────────────────────────────────────
// Called by the Python simulation seed endpoint and peer nodes on discovery.

meshRouter.post("/edges", (req: Request, res: Response) => {
  const { a, b, protocol, quality } = req.body as Partial<MeshEdge>;

  if (!a || !b || !protocol) {
    res.status(400).json({ error: "a, b, and protocol are required" });
    return;
  }

  if (!["wifi", "bluetooth"].includes(protocol)) {
    res.status(400).json({ error: "protocol must be 'wifi' or 'bluetooth'" });
    return;
  }

  edgeStmts.upsert.run({
    node_a:   a,
    node_b:   b,
    protocol,
    quality:  quality ?? 80,
  });

  res.status(201).json({ registered: true, edge: { a, b, protocol, quality: quality ?? 80 } });
});
