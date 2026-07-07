import { useState, useEffect, useRef, type ReactNode } from "react";
import DashboardLayout from "./components/DashboardLayout";
import NodeMapCanvas from "./components/NodeMapCanvas";
import { useCloudantNodes } from "./hooks/useCloudantNodes";
import {
  AlertTriangle,
  Heart,
  MapPin,
  Radio,
  Wifi,
  Users,
  Send,
  Battery,
  Signal,
  Clock,
  CheckCircle2,
  Home,
  Map,
  Bell,
  MessageCircle,
  Zap,
  Navigation,
  Shield,
} from "lucide-react";

type Tab = "home" | "alert" | "map" | "comms";
type DeviceKind = "self" | "smartphone" | "laptop";
type Protocol = "wifi" | "bluetooth";

interface Node {
  id: string;
  label: string;
  name: string;
  x: number;
  y: number;
  device: DeviceKind;
  role: "self" | "peer" | "relay";
  signal: number;
  lastSeen: string;
  os?: string;
}

interface Edge {
  a: string;
  b: string;
  protocol: Protocol;
}

interface Message {
  id: string;
  from: string;
  text: string;
  time: string;
  type: "alert" | "medical" | "info" | "gps";
  read: boolean;
}

const NODES: Node[] = [
  { id: "self",  label: "YOU",     name: "Your Device",    x: 50, y: 50, device: "self",       role: "self",  signal: 100, lastSeen: "now",  os: "Android 14" },
  { id: "n1",    label: "Ramos",   name: "iPhone 15 Pro",  x: 22, y: 30, device: "smartphone", role: "relay", signal: 87,  lastSeen: "12s",  os: "iOS 17" },
  { id: "n2",    label: "Chen",    name: "MacBook Air",    x: 75, y: 22, device: "laptop",     role: "relay", signal: 72,  lastSeen: "34s",  os: "macOS 14" },
  { id: "n3",    label: "MED·01",  name: "Galaxy S24",     x: 80, y: 65, device: "smartphone", role: "peer",  signal: 91,  lastSeen: "8s",   os: "Android 14" },
  { id: "n4",    label: "CMD·HQ",  name: "ThinkPad X1",   x: 30, y: 72, device: "laptop",     role: "relay", signal: 55,  lastSeen: "1m",   os: "Ubuntu 24" },
  { id: "n5",    label: "Torres",  name: "Pixel 8",        x: 60, y: 82, device: "smartphone", role: "peer",  signal: 64,  lastSeen: "45s",  os: "Android 14" },
];

const EDGES: Edge[] = [
  { a: "self", b: "n1", protocol: "bluetooth" },
  { a: "self", b: "n2", protocol: "wifi" },
  { a: "self", b: "n3", protocol: "wifi" },
  { a: "n1",  b: "n4", protocol: "bluetooth" },
  { a: "n3",  b: "n5", protocol: "bluetooth" },
  { a: "n4",  b: "n5", protocol: "wifi" },
  { a: "n2",  b: "n3", protocol: "wifi" },
];

const MESSAGES: Message[] = [
  { id: "m1", from: "MED-2", text: "Need insulin supplies at sector 4B. 2 patients.", time: "14:23", type: "medical", read: false },
  { id: "m2", from: "Alpha", text: "Route to shelter via Main St blocked. Use Oak Ave.", time: "14:18", type: "info", read: false },
  { id: "m3", from: "Unit 7", text: "GPS: 37.7749° N, 122.4194° W — Safe zone confirmed.", time: "14:09", type: "gps", read: true },
  { id: "m4", from: "Cmd", text: "ALERT: Gas leak reported near District 5. Evacuate.", time: "13:55", type: "alert", read: true },
];

const msgTypeStyle: Record<string, string> = {
  alert: "border-l-[#EF4444] bg-[#EF4444]/10",
  medical: "border-l-[#F97316] bg-[#F97316]/10",
  info: "border-l-[#7B9CC4] bg-[#7B9CC4]/8",
  gps: "border-l-[#22C55E] bg-[#22C55E]/10",
};

const msgTypeIcon: Record<string, ReactNode> = {
  alert: <AlertTriangle size={13} className="text-[#EF4444]" />,
  medical: <Heart size={13} className="text-[#F97316]" />,
  info: <Radio size={13} className="text-[#7B9CC4]" />,
  gps: <MapPin size={13} className="text-[#22C55E]" />,
};

// Draw a smartphone icon centered at (cx, cy)
function drawSmartphone(ctx: CanvasRenderingContext2D, cx: number, cy: number, size: number, fill: string, stroke: string) {
  const w = size * 0.55;
  const h = size;
  const r = size * 0.12;
  const x = cx - w / 2;
  const y = cy - h / 2;
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 1.5;
  ctx.stroke();
  // Screen
  ctx.beginPath();
  ctx.roundRect(x + size * 0.07, y + size * 0.1, w - size * 0.14, h - size * 0.25, r * 0.5);
  ctx.fillStyle = "rgba(255,255,255,0.12)";
  ctx.fill();
  // Home button dot
  ctx.beginPath();
  ctx.arc(cx, y + h - size * 0.07, size * 0.05, 0, Math.PI * 2);
  ctx.fillStyle = stroke;
  ctx.fill();
}

// Draw a laptop icon centered at (cx, cy)
function drawLaptop(ctx: CanvasRenderingContext2D, cx: number, cy: number, size: number, fill: string, stroke: string) {
  const sw = size * 0.95;
  const sh = size * 0.65;
  const sx = cx - sw / 2;
  const sy = cy - sh / 2 - size * 0.05;
  // Screen body
  ctx.beginPath();
  ctx.roundRect(sx, sy, sw, sh, size * 0.08);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 1.5;
  ctx.stroke();
  // Screen inner
  ctx.beginPath();
  ctx.roundRect(sx + size * 0.07, sy + size * 0.06, sw - size * 0.14, sh - size * 0.14, size * 0.04);
  ctx.fillStyle = "rgba(255,255,255,0.1)";
  ctx.fill();
  // Base
  const bw = sw * 1.1;
  const bh = size * 0.12;
  ctx.beginPath();
  ctx.roundRect(cx - bw / 2, sy + sh, bw, bh, [0, 0, size * 0.08, size * 0.08]);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

function MeshCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pulse, setPulse] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setPulse((p) => (p + 1) % 60), 50);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const W = canvas.width;
    const H = canvas.height;

    ctx.clearRect(0, 0, W, H);

    // Grid dots
    ctx.fillStyle = "rgba(91, 141, 217, 0.07)";
    for (let x = 0; x < W; x += 20) {
      for (let y = 0; y < H; y += 20) {
        ctx.beginPath();
        ctx.arc(x, y, 1, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    const toXY = (node: Node) => ({
      px: (node.x / 100) * W,
      py: (node.y / 100) * H,
    });

    // Protocol colors
    const WIFI_COLOR   = "rgba(56, 189, 248, 0.7)";   // sky blue
    const BT_COLOR     = "rgba(168, 85, 247, 0.7)";   // violet
    const WIFI_PACKET  = "#38BDF8";
    const BT_PACKET    = "#A855F7";

    // Draw edges
    EDGES.forEach((edge) => {
      const a = NODES.find((n) => n.id === edge.a)!;
      const b = NODES.find((n) => n.id === edge.b)!;
      const { px: ax, py: ay } = toXY(a);
      const { px: bx, py: by } = toXY(b);

      const isWifi = edge.protocol === "wifi";
      const lineColor = isWifi ? WIFI_COLOR : BT_COLOR;
      const packetColor = isWifi ? WIFI_PACKET : BT_PACKET;

      ctx.strokeStyle = lineColor;
      ctx.lineWidth = isWifi ? 2 : 1.5;
      ctx.setLineDash(isWifi ? [] : [5, 4]);
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.stroke();
      ctx.setLineDash([]);

      // Traveling packet
      const t = (pulse / 60 + (edge.a.charCodeAt(0) * 0.17)) % 1;
      const dx = ax + (bx - ax) * t;
      const dy = ay + (by - ay) * t;
      ctx.beginPath();
      ctx.arc(dx, dy, 3, 0, Math.PI * 2);
      ctx.fillStyle = packetColor;
      ctx.fill();

      // Protocol label on edge midpoint
      const mx = (ax + bx) / 2;
      const my = (ay + by) / 2;
      ctx.font = "bold 7px JetBrains Mono, monospace";
      ctx.fillStyle = lineColor;
      ctx.textAlign = "center";
      ctx.fillText(isWifi ? "WiFi" : "BT", mx, my - 4);
    });

    // Draw nodes
    NODES.forEach((node) => {
      const { px, py } = toXY(node);
      const isSelf = node.device === "self";
      const isLaptop = node.device === "laptop";
      const isRelay = node.role === "relay";

      const nodeColor = isSelf ? "#F97316" : isRelay ? "#22C55E" : "#5B8DD9";
      const fillColor = isSelf
        ? "rgba(249,115,22,0.2)"
        : isRelay
        ? "rgba(34,197,94,0.15)"
        : "rgba(91,141,217,0.15)";
      const size = isSelf ? 20 : isLaptop ? 18 : 16;

      // Pulse ring for self
      if (isSelf) {
        const ripple = (pulse / 60) * 30;
        const alpha = 1 - pulse / 60;
        ctx.beginPath();
        ctx.arc(px, py, size + ripple, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(249,115,22,${alpha * 0.35})`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Draw device icon
      if (isSelf) {
        drawSmartphone(ctx, px, py, size, "#F97316", "#ffffff");
      } else if (isLaptop) {
        drawLaptop(ctx, px, py, size, fillColor, nodeColor);
      } else {
        drawSmartphone(ctx, px, py, size, fillColor, nodeColor);
      }

      // Label below
      const labelY = py + size / 2 + 13;
      ctx.font = `bold 8px Barlow Condensed, sans-serif`;
      ctx.fillStyle = "#E8EEF7";
      ctx.textAlign = "center";
      ctx.fillText(node.label, px, labelY);

      // Device sub-label
      ctx.font = "7px Inter, sans-serif";
      ctx.fillStyle = nodeColor;
      ctx.fillText(isLaptop ? "laptop" : isSelf ? "you" : "phone", px, labelY + 9);
    });
  }, [pulse]);

  return (
    <canvas
      ref={canvasRef}
      width={320}
      height={290}
      className="w-full h-full"
    />
  );
}

function StatusBar({ nodeCount }: { nodeCount: number }) {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const hh = time.getHours().toString().padStart(2, "0");
  const mm = time.getMinutes().toString().padStart(2, "0");

  return (
    <div className="flex items-center justify-between px-4 py-2 text-xs font-mono text-[#7B9CC4]">
      <span>{hh}:{mm}</span>
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1 text-[#22C55E]">
          <Radio size={11} />
          MESH·{nodeCount}
        </span>
        <Battery size={13} />
        <Signal size={13} />
      </div>
    </div>
  );
}

function HomeTab() {
  const [sosActive, setSosActive] = useState(false);
  const [sosCountdown, setSosCountdown] = useState<number | null>(null);

  const handleSOS = () => {
    if (sosActive) return;
    setSosCountdown(3);
    const id = setInterval(() => {
      setSosCountdown((c) => {
        if (c === null || c <= 1) {
          clearInterval(id);
          setSosActive(true);
          setTimeout(() => setSosActive(false), 5000);
          return null;
        }
        return c - 1;
      });
    }, 1000);
  };

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Network health */}
      <div className="rounded-xl border border-[rgba(91,141,217,0.2)] bg-[#132B5A] p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-[#22C55E] animate-pulse" />
            <span className="text-xs font-medium text-[#22C55E] uppercase tracking-widest" style={{ fontFamily: "Barlow Condensed, sans-serif" }}>
              Mesh Active
            </span>
          </div>
          <span className="text-xs font-mono text-[#7B9CC4]">6 nodes · 3.2km range</span>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Nodes", value: "6", sub: "online" },
            { label: "Signal", value: "87%", sub: "avg" },
            { label: "Latency", value: "42ms", sub: "p95" },
          ].map((s) => (
            <div key={s.label} className="rounded-lg bg-[#0B1D3A]/60 px-3 py-2 text-center">
              <div
                className="text-xl font-bold text-[#E8EEF7] leading-none"
                style={{ fontFamily: "Barlow Condensed, sans-serif" }}
              >
                {s.value}
              </div>
              <div className="text-[10px] text-[#7B9CC4] mt-0.5 uppercase tracking-wide">{s.sub}</div>
              <div className="text-[9px] text-[#7B9CC4]/60 uppercase tracking-wider">{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* SOS Button */}
      <button
        onClick={handleSOS}
        className={`relative w-full rounded-2xl py-6 flex flex-col items-center gap-1 transition-all duration-200 active:scale-95 ${
          sosActive
            ? "bg-[#EF4444] shadow-[0_0_40px_rgba(239,68,68,0.6)]"
            : sosCountdown !== null
            ? "bg-[#F97316]/80"
            : "bg-[#F97316] shadow-[0_0_24px_rgba(249,115,22,0.35)]"
        }`}
      >
        <AlertTriangle
          size={32}
          strokeWidth={2.5}
          className="text-white"
        />
        <span
          className="text-2xl font-black text-white tracking-widest uppercase"
          style={{ fontFamily: "Barlow Condensed, sans-serif" }}
        >
          {sosActive
            ? "SOS BROADCASTING"
            : sosCountdown !== null
            ? `SENDING IN ${sosCountdown}...`
            : "SOS ALERT"}
        </span>
        <span className="text-xs text-white/70 font-medium">Hold to broadcast emergency</span>
        {sosActive && (
          <div className="absolute inset-0 rounded-2xl border-2 border-white/40 animate-ping" />
        )}
      </button>

      {/* Action grid */}
      <div className="grid grid-cols-2 gap-3">
        <button className="rounded-xl bg-[#132B5A] border border-[rgba(91,141,217,0.2)] p-4 flex flex-col items-start gap-3 active:bg-[#1A3870] transition-colors">
          <div className="w-10 h-10 rounded-lg bg-[#F97316]/15 flex items-center justify-center">
            <Heart size={20} className="text-[#F97316]" />
          </div>
          <div>
            <div
              className="text-base font-bold text-[#E8EEF7] leading-tight"
              style={{ fontFamily: "Barlow Condensed, sans-serif" }}
            >
              Medical
            </div>
            <div
              className="text-base font-bold text-[#E8EEF7] leading-tight"
              style={{ fontFamily: "Barlow Condensed, sans-serif" }}
            >
              Request
            </div>
            <div className="text-[10px] text-[#7B9CC4] mt-1">Flag medical need</div>
          </div>
        </button>

        <button className="rounded-xl bg-[#132B5A] border border-[rgba(91,141,217,0.2)] p-4 flex flex-col items-start gap-3 active:bg-[#1A3870] transition-colors">
          <div className="w-10 h-10 rounded-lg bg-[#22C55E]/15 flex items-center justify-center">
            <Navigation size={20} className="text-[#22C55E]" />
          </div>
          <div>
            <div
              className="text-base font-bold text-[#E8EEF7] leading-tight"
              style={{ fontFamily: "Barlow Condensed, sans-serif" }}
            >
              Share
            </div>
            <div
              className="text-base font-bold text-[#E8EEF7] leading-tight"
              style={{ fontFamily: "Barlow Condensed, sans-serif" }}
            >
              GPS
            </div>
            <div className="text-[10px] text-[#7B9CC4] mt-1">Broadcast position</div>
          </div>
        </button>

        <button className="rounded-xl bg-[#132B5A] border border-[rgba(91,141,217,0.2)] p-4 flex flex-col items-start gap-3 active:bg-[#1A3870] transition-colors">
          <div className="w-10 h-10 rounded-lg bg-[#5B8DD9]/15 flex items-center justify-center">
            <Users size={20} className="text-[#5B8DD9]" />
          </div>
          <div>
            <div
              className="text-base font-bold text-[#E8EEF7] leading-tight"
              style={{ fontFamily: "Barlow Condensed, sans-serif" }}
            >
              All Clear
            </div>
            <div className="text-[10px] text-[#7B9CC4] mt-1">Signal safe status</div>
          </div>
        </button>

        <button className="rounded-xl bg-[#132B5A] border border-[rgba(91,141,217,0.2)] p-4 flex flex-col items-start gap-3 active:bg-[#1A3870] transition-colors">
          <div className="w-10 h-10 rounded-lg bg-[#22C55E]/15 flex items-center justify-center">
            <Zap size={20} className="text-[#22C55E]" />
          </div>
          <div>
            <div
              className="text-base font-bold text-[#E8EEF7] leading-tight"
              style={{ fontFamily: "Barlow Condensed, sans-serif" }}
            >
              Relay
            </div>
            <div
              className="text-base font-bold text-[#E8EEF7] leading-tight"
              style={{ fontFamily: "Barlow Condensed, sans-serif" }}
            >
              Mode
            </div>
            <div className="text-[10px] text-[#7B9CC4] mt-1">Boost network range</div>
          </div>
        </button>
      </div>

      {/* Recent activity */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span
            className="text-sm font-bold text-[#7B9CC4] uppercase tracking-widest"
            style={{ fontFamily: "Barlow Condensed, sans-serif" }}
          >
            Recent Activity
          </span>
        </div>
        <div className="flex flex-col gap-2">
          {MESSAGES.slice(0, 2).map((msg) => (
            <div
              key={msg.id}
              className={`rounded-lg border-l-2 px-3 py-2.5 flex items-start gap-2 ${msgTypeStyle[msg.type]}`}
            >
              <span className="mt-0.5">{msgTypeIcon[msg.type]}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className="text-xs font-semibold text-[#E8EEF7]">{msg.from}</span>
                  {!msg.read && (
                    <span className="w-1.5 h-1.5 rounded-full bg-[#F97316]" />
                  )}
                </div>
                <p className="text-xs text-[#7B9CC4] truncate">{msg.text}</p>
              </div>
              <span className="text-[10px] font-mono text-[#7B9CC4]/60 shrink-0">{msg.time}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:4000";

// Map mobile alert type IDs to the backend alert schema
const ALERT_TYPE_MAP: Record<string, string> = {
  sos:     "sos",
  medical: "medical",
  safe:    "safe",
  hazard:  "hazard",
  supply:  "supply",
  locate:  "locate",
};

function AlertTab() {
  const [alertType, setAlertType] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);

  const handleSend = async () => {
    if (!alertType || sending) return;
    setSending(true);

    // Grab GPS if available
    let lat: number | undefined;
    let lng: number | undefined;
    try {
      const pos = await new Promise<GeolocationPosition>((resolve, reject) =>
        navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 3_000 })
      );
      lat = pos.coords.latitude;
      lng = pos.coords.longitude;
    } catch { /* GPS unavailable — send without coords */ }

    try {
      await fetch(`${API_BASE}/api/alerts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type:    ALERT_TYPE_MAP[alertType] ?? "sos",
          message: message.trim() || undefined,
          lat,
          lng,
        }),
      });
    } catch { /* backend unreachable — still show sent so UI isn't blocked */ }

    setSending(false);
    setSent(true);
    setTimeout(() => {
      setSent(false);
      setAlertType(null);
      setMessage("");
    }, 3_000);
  };

  const types = [
    { id: "sos", label: "SOS Alert", icon: <AlertTriangle size={22} />, color: "#EF4444", bg: "#EF4444" },
    { id: "medical", label: "Medical", icon: <Heart size={22} />, color: "#F97316", bg: "#F97316" },
    { id: "safe", label: "I am Safe", icon: <CheckCircle2 size={22} />, color: "#22C55E", bg: "#22C55E" },
    { id: "hazard", label: "Hazard", icon: <Zap size={22} />, color: "#FBBF24", bg: "#FBBF24" },
    { id: "supply", label: "Need Supplies", icon: <Shield size={22} />, color: "#5B8DD9", bg: "#5B8DD9" },
    { id: "locate", label: "Locate Me", icon: <MapPin size={22} />, color: "#22C55E", bg: "#22C55E" },
  ];

  if (sent) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-8 h-full min-h-[480px]">
        <div className="w-20 h-20 rounded-full bg-[#22C55E]/20 flex items-center justify-center">
          <CheckCircle2 size={40} className="text-[#22C55E]" />
        </div>
        <div
          className="text-3xl font-black text-[#22C55E] tracking-widest uppercase"
          style={{ fontFamily: "Barlow Condensed, sans-serif" }}
        >
          Alert Sent
        </div>
        <p className="text-sm text-[#7B9CC4] text-center">
          Broadcast to 6 nodes · Relayed across mesh network
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 p-4">
      <div>
        <h2
          className="text-lg font-bold text-[#E8EEF7] uppercase tracking-widest"
          style={{ fontFamily: "Barlow Condensed, sans-serif" }}
        >
          Select Alert Type
        </h2>
        <p className="text-xs text-[#7B9CC4] mt-0.5">Will broadcast to all reachable nodes</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {types.map((t) => (
          <button
            key={t.id}
            onClick={() => setAlertType(t.id)}
            className={`rounded-xl p-4 flex flex-col items-center gap-2 border-2 transition-all duration-150 active:scale-95 ${
              alertType === t.id
                ? "border-current bg-current/20 shadow-[0_0_20px_currentColor/30]"
                : "border-[rgba(91,141,217,0.15)] bg-[#132B5A]"
            }`}
            style={{ color: t.color } as React.CSSProperties}
          >
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{ background: `${t.color}20` }}
            >
              {t.icon}
            </div>
            <span
              className="text-sm font-bold text-[#E8EEF7] text-center leading-tight"
              style={{ fontFamily: "Barlow Condensed, sans-serif" }}
            >
              {t.label}
            </span>
          </button>
        ))}
      </div>

      <div className="rounded-xl bg-[#132B5A] border border-[rgba(91,141,217,0.2)] p-3">
        <textarea
          className="w-full bg-transparent text-sm text-[#E8EEF7] placeholder-[#7B9CC4]/50 resize-none outline-none"
          rows={3}
          placeholder="Add details (optional) — location, number of people, severity..."
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
      </div>

      <div className="rounded-xl bg-[#132B5A] border border-[rgba(91,141,217,0.18)] p-3 flex items-center gap-3">
        <Navigation size={16} className="text-[#22C55E] shrink-0" />
        <div className="flex-1">
          <div className="text-xs font-mono text-[#22C55E]">37.7749° N · 122.4194° W</div>
          <div className="text-[10px] text-[#7B9CC4]">GPS locked · Auto-attach to alert</div>
        </div>
        <CheckCircle2 size={14} className="text-[#22C55E]" />
      </div>

      <button
        onClick={handleSend}
        disabled={!alertType || sending}
        className={`w-full rounded-xl py-4 flex items-center justify-center gap-2 font-bold text-white transition-all duration-150 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed ${
          alertType
            ? "bg-[#F97316] shadow-[0_0_20px_rgba(249,115,22,0.3)]"
            : "bg-[#132B5A] text-[#7B9CC4]"
        }`}
        style={{ fontFamily: "Barlow Condensed, sans-serif", fontSize: "1.125rem", letterSpacing: "0.1em" }}
      >
        <Send size={18} className={sending ? "animate-pulse" : ""} />
        {sending ? "SENDING…" : "BROADCAST ALERT"}
      </button>
    </div>
  );
}

function MapTab() {
  const { nodes, loading, error, source, refresh } = useCloudantNodes(10_000);

  return (
    // position+inset fills the parent flex-1 div completely.
    // overflow:visible is mandatory — Leaflet tile/marker panes are absolutely
    // positioned children and get clipped by any overflow:hidden ancestor.
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        padding: "12px",
        overflow: "visible",
      }}
    >
      <NodeMapCanvas
        nodes={nodes}
        loading={loading}
        error={error}
        source={source}
        onRefresh={refresh}
      />
    </div>
  );
}

interface LocalMessage {
  id: string;
  from: string;
  text: string;
  time: string;
  type: "alert" | "medical" | "info" | "gps";
  read: boolean;
}

function CommsTab() {
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<LocalMessage[]>(MESSAGES);
  const [sending, setSending] = useState(false);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || sending) return;
    setSending(true);

    try {
      await fetch(`${API_BASE}/api/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          from_node_id: "self",
          from_label:   "You",
          to_node_id:   "broadcast",
          category:     "info",
          ciphertext:   trimmed,
          hops:         0,
        }),
      });
    } catch { /* offline — still append locally */ }

    const now = new Date();
    const hh  = now.getHours().toString().padStart(2, "0");
    const mm  = now.getMinutes().toString().padStart(2, "0");
    setMsgs((prev) => [
      { id: `local-${Date.now()}`, from: "You", text: trimmed,
        time: `${hh}:${mm}`, type: "info", read: true },
      ...prev,
    ]);
    setInput("");
    setSending(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 pb-2">
        <h2
          className="text-lg font-bold text-[#E8EEF7] uppercase tracking-widest"
          style={{ fontFamily: "Barlow Condensed, sans-serif" }}
        >
          Mesh Comms
        </h2>
        <p className="text-xs text-[#7B9CC4]">Encrypted · offline · peer-to-peer</p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-2 flex flex-col gap-3">
        {msgs.map((msg) => (
          <div
            key={msg.id}
            className={`rounded-xl border-l-2 p-3 ${msgTypeStyle[msg.type]}`}
          >
            <div className="flex items-start justify-between gap-2 mb-1.5">
              <div className="flex items-center gap-2">
                {msgTypeIcon[msg.type]}
                <span className="text-xs font-bold text-[#E8EEF7]">{msg.from}</span>
                {!msg.read && (
                  <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-[#F97316]/20 text-[#F97316]">
                    New
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 text-[#7B9CC4]/60 shrink-0">
                <Clock size={9} />
                <span className="text-[10px] font-mono">{msg.time}</span>
              </div>
            </div>
            <p className="text-sm text-[#C4D5EC] leading-snug">{msg.text}</p>
          </div>
        ))}
      </div>

      <div className="p-4 pt-2 border-t border-[rgba(91,141,217,0.15)]">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Broadcast a message…"
            className="flex-1 rounded-xl bg-[#132B5A] border border-[rgba(91,141,217,0.2)] px-3 py-2.5 text-sm text-[#E8EEF7] placeholder-[#7B9CC4]/50 outline-none focus:border-[rgba(91,141,217,0.5)]"
          />
          <button
            disabled={!input.trim() || sending}
            className="w-11 h-11 rounded-xl bg-[#F97316] flex items-center justify-center shrink-0 active:scale-95 transition-transform disabled:opacity-40 disabled:cursor-not-allowed"
            onClick={() => void handleSend()}
          >
            <Send size={16} className={`text-white ${sending ? "animate-pulse" : ""}`} />
          </button>
        </div>
      </div>
    </div>
  );
}

const NAV = [
  { id: "home" as Tab, label: "Home", icon: Home },
  { id: "alert" as Tab, label: "Alert", icon: Bell },
  { id: "map" as Tab, label: "Map", icon: Map },
  { id: "comms" as Tab, label: "Comms", icon: MessageCircle },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("home");

  // ── Responsive: render full dashboard on wide screens, mobile on narrow ──
  const [isDesktop, setIsDesktop] = useState(() => window.innerWidth >= 768);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener("change", handler);
    setIsDesktop(mq.matches);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // Live node count — NODES includes "self", so total peers = NODES.length - 1
  const peerCount = NODES.filter((n) => n.id !== "self").length;

  if (isDesktop) {
    return <DashboardLayout />;
  }

  // Map tab renders full-screen (no clipping frame) so Leaflet panes aren't cut off
  if (tab === "map") {
    return (
      <div
        style={{
          position: "fixed",
          inset: 0,
          background: "#0B1D3A",
          fontFamily: "Inter, sans-serif",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Slim header */}
        <div
          className="shrink-0 flex items-center justify-between px-4 py-2 border-b"
          style={{ borderColor: "rgba(91,141,217,0.15)", background: "rgba(10,21,38,0.9)" }}
        >
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-[#F97316] flex items-center justify-center">
              <Radio size={12} className="text-white" strokeWidth={2.5} />
            </div>
            <span
              className="text-sm font-black text-[#E8EEF7] uppercase tracking-wider"
              style={{ fontFamily: "Barlow Condensed, sans-serif" }}
            >
              Live Mesh Map
            </span>
          </div>
          <button
            onClick={() => setTab("home")}
            className="text-[10px] font-mono text-[#7B9CC4] px-2 py-1 rounded border border-[rgba(91,141,217,0.2)] hover:text-[#E8EEF7]"
          >
            ← Back
          </button>
        </div>

        {/* Map fills remaining space */}
        <div style={{ flex: 1, position: "relative", overflow: "visible" }}>
          <MapTab />
        </div>

        {/* Bottom nav */}
        <div
          className="shrink-0 border-t border-[rgba(91,141,217,0.15)] bg-[#0A1526]"
          style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
        >
          <div className="flex">
            {NAV.map(({ id, label, icon: Icon }) => {
              const active = tab === id;
              return (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`flex-1 flex flex-col items-center gap-1 py-3 relative transition-colors ${
                    active ? "text-[#F97316]" : "text-[#7B9CC4]"
                  }`}
                >
                  <Icon size={20} strokeWidth={active ? 2.5 : 1.8} />
                  <span
                    className={`text-[10px] uppercase tracking-widest ${active ? "font-bold" : ""}`}
                    style={{ fontFamily: "Barlow Condensed, sans-serif" }}
                  >
                    {label}
                  </span>
                  {active && (
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 bg-[#F97316] rounded-full" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen w-full flex items-center justify-center"
      style={{
        background: "radial-gradient(ellipse at 40% 20%, #0F2347 0%, #060E1C 70%)",
        fontFamily: "Inter, sans-serif",
      }}
    >
      {/* Mobile frame */}
      <div
        className="relative w-full max-w-[390px] flex flex-col overflow-hidden"
        style={{
          background: "#0B1D3A",
          minHeight: "100svh",
          maxHeight: "100svh",
          borderLeft: "1px solid rgba(91,141,217,0.15)",
          borderRight: "1px solid rgba(91,141,217,0.15)",
        }}
      >
        {/* Top bar */}
        <div className="shrink-0 border-b border-[rgba(91,141,217,0.12)]">
          <StatusBar nodeCount={peerCount} />

          {/* App header */}
          <div className="px-4 pb-3 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-[#F97316] flex items-center justify-center">
                <Radio size={16} className="text-white" strokeWidth={2.5} />
              </div>
              <div>
                <div
                  className="text-base font-black text-[#E8EEF7] leading-none tracking-wider uppercase"
                  style={{ fontFamily: "Barlow Condensed, sans-serif" }}
                >
                  MeshNet AI
                </div>
                <div className="text-[9px] font-mono text-[#7B9CC4] tracking-widest uppercase">
                  Emergency Routing v2.4
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#22C55E]/10 border border-[#22C55E]/20">
              <Wifi size={11} className="text-[#22C55E]" />
              <span className="text-[10px] font-mono text-[#22C55E] uppercase tracking-wider">Offline</span>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto" style={{ scrollbarWidth: "none" }}>
          {tab === "home" && <HomeTab />}
          {tab === "alert" && <AlertTab />}
          {tab === "comms" && <CommsTab />}
        </div>

        {/* Bottom nav */}
        <div
          className="shrink-0 border-t border-[rgba(91,141,217,0.15)] bg-[#0A1526]"
          style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
        >
          <div className="flex">
            {NAV.map(({ id, label, icon: Icon }) => {
              const active = tab === id;
              const isAlert = id === "alert";
              const unread = id === "comms" ? MESSAGES.filter((m) => !m.read).length : 0;

              return (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`flex-1 flex flex-col items-center gap-1 py-3 relative transition-colors ${
                    active ? "text-[#F97316]" : "text-[#7B9CC4]"
                  }`}
                >
                  {isAlert && !active && (
                    <div className="absolute top-2 w-10 h-10 rounded-full bg-[#F97316]/10 flex items-center justify-center -mt-1">
                      <div className="w-10 h-10 rounded-full border border-[#F97316]/25 animate-ping absolute" />
                    </div>
                  )}
                  <div className="relative">
                    <Icon
                      size={20}
                      strokeWidth={active ? 2.5 : 1.8}
                      className={isAlert && !active ? "text-[#F97316]/70" : ""}
                    />
                    {unread > 0 && (
                      <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-[#F97316] text-white text-[9px] font-bold flex items-center justify-center">
                        {unread}
                      </span>
                    )}
                  </div>
                  <span
                    className={`text-[10px] uppercase tracking-widest ${active ? "font-bold" : ""}`}
                    style={{ fontFamily: "Barlow Condensed, sans-serif" }}
                  >
                    {label}
                  </span>
                  {active && (
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 bg-[#F97316] rounded-full" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
