"use client";
import type { SessionState, DeviceInfo } from "@/lib/ws_client";

const STATE_COLOR: Record<SessionState, string> = {
  IDLE:       "bg-gray-500/15 text-gray-300",
  PREFLIGHT:  "bg-yellow-500/15 text-yellow-300",
  READY:      "bg-cyan-500/15 text-cyan-300",
  RECORDING:  "bg-red-500/20 text-red-300",
  FINALIZING: "bg-orange-500/15 text-orange-300",
  VALIDATING: "bg-purple-500/15 text-purple-300",
  ERROR:      "bg-red-700/25 text-red-400",
};

interface Props {
  state: SessionState;
  sessionId?: string;
  devices: DeviceInfo[];
  isWsConnected: boolean;
  backendIp?: string;
}

export default function StatusBanner({ state, sessionId, devices, isWsConnected, backendIp }: Props) {
  const online = devices.filter(d => d.is_online);
  const totalPackets = devices.reduce((s, d) => s + d.packets, 0);

  return (
    <div className={`glass-rail border-b border-white/10 flex items-center justify-between px-4 py-2 text-sm ${STATE_COLOR[state]}`}>
      <div className="flex items-center gap-4">
        <span className="font-bold tracking-widest">
          {state === "RECORDING" && <span className="animate-pulse mr-1">●</span>}
          {state}
        </span>
        {sessionId && (
          <span className="text-xs opacity-60">SID: {sessionId.slice(0, 10)}…</span>
        )}
      </div>

      <div className="flex items-center gap-6 text-xs">
        {backendIp && (
          <span className="opacity-60">
            Backend: {backendIp} · {isWsConnected ? "connected" : "disconnected"}
          </span>
        )}
        <span>
          <span className={isWsConnected ? "text-green-400" : "text-red-400"}>
            {isWsConnected ? "● WS" : "○ WS"}
          </span>
        </span>
        <span>
          {online.length}/{devices.length} device{devices.length !== 1 ? "s" : ""} online
        </span>
        {state === "RECORDING" && (
          <span className="tabular-nums">{totalPackets.toLocaleString()} pkts</span>
        )}
        {devices.map(d => (
          <span key={d.device_id} className={d.is_online ? "text-green-400" : "text-gray-500"}>
            {d.role}: {d.is_online ? "✓" : "✗"}
          </span>
        ))}
      </div>
    </div>
  );
}
