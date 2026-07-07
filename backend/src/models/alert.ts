export type AlertType = "sos" | "medical" | "safe" | "hazard" | "supply" | "locate";
export type AlertSeverity = "critical" | "high" | "medium" | "low";

export interface Alert {
  id: string;
  type: AlertType;
  severity: AlertSeverity;
  fromNodeId: string;
  fromLabel: string;
  message?: string;
  lat?: number;
  lng?: number;
  createdAt: string;
  expiresAt?: string;
  ttl: number;           // hops remaining before dropping
  acknowledged: boolean;
}
