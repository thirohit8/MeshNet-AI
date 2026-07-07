export type DeviceKind = "smartphone" | "laptop";
export type NodeRole  = "peer" | "relay";
export type Protocol  = "wifi" | "bluetooth";

export interface MeshNode {
  id: string;
  label: string;
  name: string;
  device: DeviceKind;
  role: NodeRole;
  signal: number;             // 0–100 RSSI-normalised
  lastSeen: string;           // ISO timestamp
  /** 0–100 — used to colour battery arc on the map and warn rescue teams */
  batteryPercentage: number;
  /** true = BLE scanning active → green dot on map
   *  false = BLE off / unreachable → grey dot          */
  bluetoothStatus: boolean;
  os?: string;
  lat?: number;
  lng?: number;
}

export interface MeshEdge {
  a: string;             // node id
  b: string;             // node id
  protocol: Protocol;
  quality: number;       // 0–100
}

export interface MeshTopology {
  nodes: MeshNode[];
  edges: MeshEdge[];
  updatedAt: string;
}
