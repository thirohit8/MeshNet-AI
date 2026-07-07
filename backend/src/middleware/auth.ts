import { Request, Response, NextFunction } from "express";

const MESH_SECRET = process.env.MESH_SECRET ?? "";

// Shared-secret auth for node-to-node API calls.
// Production: replace with Ed25519 public-key signatures per node.
export function requireMeshAuth(req: Request, res: Response, next: NextFunction) {
  // Fail closed: if the secret is not configured, deny all requests.
  // This prevents an accidental open relay if the env var is missing.
  if (!MESH_SECRET) {
    res.status(503).json({ error: "Mesh auth not configured — set MESH_SECRET env var" });
    return;
  }

  const token = req.headers["x-mesh-secret"];
  if (token !== MESH_SECRET) {
    res.status(401).json({ error: "Unauthorized — invalid mesh secret" });
    return;
  }
  next();
}
