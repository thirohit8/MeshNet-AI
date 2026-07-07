/**
 * useCloudantNodes — Paul's IBM Cloudant integration hook
 *
 * Pulls mesh node configurations from IBM Cloudant (mesh_nodes_db).
 * Uses the IBM Cloud Databases REST API v5 / Cloudant HTTP API.
 *
 * Expected document shape in Cloudant:
 * {
 *   node_id:            string,   // e.g. "cmd-hq"
 *   label:              string,   // display name e.g. "CMD·HQ"
 *   latitude:           number,
 *   longitude:          number,
 *   battery_percentage: number,   // 0–100
 *   bluetooth_status:   boolean,  // true = BLE scanning active → green dot
 *   signal:             number,   // 0–100 RSSI-normalised
 *   device:             "smartphone" | "laptop",
 *   role:               "peer" | "relay",
 *   last_seen:          string,   // ISO timestamp
 * }
 *
 * Environment variables (set in .env.local):
 *   VITE_CLOUDANT_URL      — https://<instance>.cloudantnosqldb.appdomain.cloud
 *   VITE_CLOUDANT_API_KEY  — IAM API key (Bearer token)
 *   VITE_CLOUDANT_DB       — database name (default: mesh_nodes_db)
 *
 * Falls back to the local backend REST API (/api/mesh/topology) when
 * Cloudant credentials are not configured, so dev works offline.
 */

import { useState, useEffect, useCallback } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CloudantNode {
  node_id: string;
  label: string;
  latitude: number;
  longitude: number;
  battery_percentage: number;
  /** true  → BLE scanning active → render as GREEN dot
   *  false → BLE off / unreachable → render as GREY dot */
  bluetooth_status: boolean;
  signal: number;
  device: "smartphone" | "laptop";
  role: "peer" | "relay";
  last_seen: string;
}

interface UseCloudantNodesResult {
  nodes: CloudantNode[];
  loading: boolean;
  error: string | null;
  source: "cloudant" | "local-backend" | "seed";
  refresh: () => void;
}

// ─── Seed fallback — mirrors database/seeds/nodes.json ───────────────────────

const SEED_NODES: CloudantNode[] = [
  {
    node_id: "cmd-hq",
    label: "CMD·HQ",
    latitude: 14.5995,
    longitude: 120.9842,
    battery_percentage: 82,
    bluetooth_status: true,
    signal: 91,
    device: "laptop",
    role: "relay",
    last_seen: new Date().toISOString(),
  },
  {
    node_id: "ramos-phone",
    label: "Ramos",
    latitude: 14.6015,
    longitude: 120.9825,
    battery_percentage: 67,
    bluetooth_status: true,
    signal: 87,
    device: "smartphone",
    role: "relay",
    last_seen: new Date().toISOString(),
  },
  {
    node_id: "chen-laptop",
    label: "Chen",
    latitude: 14.5978,
    longitude: 120.9871,
    battery_percentage: 91,
    bluetooth_status: false,
    signal: 72,
    device: "laptop",
    role: "relay",
    last_seen: new Date().toISOString(),
  },
  {
    node_id: "med-01",
    label: "MED·01",
    latitude: 14.6002,
    longitude: 120.9858,
    battery_percentage: 55,
    bluetooth_status: true,
    signal: 91,
    device: "smartphone",
    role: "peer",
    last_seen: new Date().toISOString(),
  },
  {
    node_id: "torres-phone",
    label: "Torres",
    latitude: 14.5989,
    longitude: 120.9810,
    battery_percentage: 38,
    bluetooth_status: false,
    signal: 64,
    device: "smartphone",
    role: "peer",
    last_seen: new Date().toISOString(),
  },
];

// ─── IBM Cloudant fetch ───────────────────────────────────────────────────────

async function fetchFromCloudant(
  baseUrl: string,
  apiKey: string,
  dbName: string
): Promise<CloudantNode[]> {
  // IBM Cloudant HTTP API v2 — _all_docs with include_docs=true
  const url = `${baseUrl}/${dbName}/_all_docs?include_docs=true`;

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${apiKey}`,
      Accept: "application/json",
    },
  });

  if (!res.ok) {
    throw new Error(`Cloudant HTTP ${res.status}: ${res.statusText}`);
  }

  const data = await res.json() as {
    rows: Array<{ doc: Record<string, unknown> }>;
  };

  // Map Cloudant docs → CloudantNode, skip design docs
  return data.rows
    .map((row) => row.doc)
    .filter((doc) => doc && !String(doc._id ?? "").startsWith("_design"))
    .map((doc) => ({
      node_id:            String(doc.node_id ?? doc._id ?? "unknown"),
      label:              String(doc.label ?? doc.node_id ?? "Node"),
      latitude:           Number(doc.latitude ?? 0),
      longitude:          Number(doc.longitude ?? 0),
      battery_percentage: Number(doc.battery_percentage ?? 80),
      bluetooth_status:   Boolean(doc.bluetooth_status ?? false),
      signal:             Number(doc.signal ?? 80),
      device:             (doc.device as "smartphone" | "laptop") ?? "smartphone",
      role:               (doc.role as "peer" | "relay") ?? "peer",
      last_seen:          String(doc.last_seen ?? new Date().toISOString()),
    }));
}

// ─── Local backend fallback ───────────────────────────────────────────────────

async function fetchFromLocalBackend(apiBase: string): Promise<CloudantNode[]> {
  const res = await fetch(`${apiBase}/api/mesh/topology`);
  if (!res.ok) throw new Error(`Backend HTTP ${res.status}`);

  const data = await res.json() as {
    nodes: Array<{
      id: string;
      label: string;
      lat?: number;
      lng?: number;
      battery?: number;
      signal: number;
      device: string;
      role: string;
      lastSeen: string;
      protocol?: string[];
    }>;
  };

  return data.nodes.map((n) => ({
    node_id:            n.id,
    label:              n.label,
    latitude:           n.lat ?? 0,
    longitude:          n.lng ?? 0,
    battery_percentage: n.battery ?? 80,
    bluetooth_status:   Array.isArray(n.protocol)
                          ? n.protocol.includes("bluetooth")
                          : true,
    signal:             n.signal,
    device:             (n.device as "smartphone" | "laptop") ?? "smartphone",
    role:               (n.role as "peer" | "relay") ?? "peer",
    last_seen:          n.lastSeen,
  }));
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useCloudantNodes(
  pollIntervalMs = 10_000
): UseCloudantNodesResult {
  const [nodes, setNodes] = useState<CloudantNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<UseCloudantNodesResult["source"]>("seed");

  const cloudantUrl = import.meta.env.VITE_CLOUDANT_URL as string | undefined;
  const cloudantKey = import.meta.env.VITE_CLOUDANT_API_KEY as string | undefined;
  const cloudantDb  = (import.meta.env.VITE_CLOUDANT_DB as string | undefined) ?? "mesh_nodes_db";
  const apiBase     = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:4000";

  // Guard against un-replaced .env.local placeholders — a URL containing
  // angle brackets or the literal string "your-instance" is not a real URL.
  const cloudantUrlValid =
    !!cloudantUrl &&
    !cloudantUrl.includes("<") &&
    !cloudantUrl.includes("your-instance");

  const load = useCallback(async () => {
    try {
      // Priority 1 — IBM Cloudant (when real credentials are present)
      if (cloudantUrlValid && cloudantKey && !cloudantKey.includes("<")) {
        const data = await fetchFromCloudant(cloudantUrl!, cloudantKey, cloudantDb);
        setNodes(data);
        setSource("cloudant");
        setError(null);
        return;
      }

      // Priority 2 — local backend
      const data = await fetchFromLocalBackend(apiBase);
      setNodes(data);
      setSource("local-backend");
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);

      // Priority 3 — seed fallback so the map always renders something
      if (nodes.length === 0) {
        setNodes(SEED_NODES);
        setSource("seed");
      }
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cloudantUrlValid, cloudantKey, cloudantDb, apiBase]);

  useEffect(() => {
    load();
    const id = setInterval(load, pollIntervalMs);
    return () => clearInterval(id);
  }, [load, pollIntervalMs]);

  return { nodes, loading, error, source, refresh: load };
}
