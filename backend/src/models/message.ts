export type MessageCategory = "alert" | "medical" | "info" | "gps";

export interface MeshMessage {
  id: string;
  fromNodeId: string;
  fromLabel: string;
  toNodeId: string | "broadcast";
  category: MessageCategory;
  ciphertext: string;    // AES-GCM encrypted payload (base64)
  createdAt: string;
  read: boolean;
  hops: number;          // number of relay hops taken
}
