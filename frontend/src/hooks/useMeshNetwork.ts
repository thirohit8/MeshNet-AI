import { useState, useEffect, useCallback } from "react";

export interface MeshNode {
  id: string;
  label: string;
  name: string;
  device: "smartphone" | "laptop";
  role: "peer" | "relay";
  signal: number;
  lastSeen: string;
  protocol: ("wifi" | "bluetooth")[];
  os?: string;
}

export interface MeshEdge {
  a: string;
  b: string;
  protocol: "wifi" | "bluetooth";
}

interface MeshState {
  nodes: MeshNode[];
  edges: MeshEdge[];
  connected: boolean;
  nodeCount: number;
  avgSignal: number;
}

// In production this hook would interface with the native BLE/WiFi-Direct layer
// via a WebView bridge or Capacitor plugin. For now it polls the backend REST API.
export function useMeshNetwork(apiBase: string = "") {
  const [state, setState] = useState<MeshState>({
    nodes: [],
    edges: [],
    connected: false,
    nodeCount: 0,
    avgSignal: 0,
  });
  const [error, setError] = useState<string | null>(null);

  const fetchTopology = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/mesh/topology`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setState({
        nodes: data.nodes,
        edges: data.edges,
        connected: data.nodes.length > 0,
        nodeCount: data.nodes.length,
        avgSignal: data.nodes.length
          ? Math.round(data.nodes.reduce((s: number, n: MeshNode) => s + n.signal, 0) / data.nodes.length)
          : 0,
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }, [apiBase]);

  useEffect(() => {
    fetchTopology();
    const id = setInterval(fetchTopology, 5000);
    return () => clearInterval(id);
  }, [fetchTopology]);

  return { ...state, error, refresh: fetchTopology };
}
