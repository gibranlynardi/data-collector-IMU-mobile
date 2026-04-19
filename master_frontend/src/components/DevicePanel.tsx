"use client";
import { useEffect, useRef } from "react";
import type { DeviceInfo } from "@/lib/ws_client";

interface Sample { acc: number[]; gyro: number[]; ts: number }

interface Props {
  devices: DeviceInfo[];
  quorum: { connected: number; roles: string[] };
  liveSamples: Record<string, Sample>;
  isRecording: boolean;
}

const ROLE_COLOR: Record<string, string> = {
  chest:       "bg-blue-900 border-blue-600",
  waist:       "bg-purple-900 border-purple-600",
  thigh_left:  "bg-green-900 border-green-600",
  thigh_right: "bg-teal-900 border-teal-600",
  ankle_left:  "bg-yellow-900 border-yellow-600",
  ankle_right: "bg-orange-900 border-orange-600",
  wrist_left:  "bg-pink-900 border-pink-600",
  wrist_right: "bg-rose-900 border-rose-600",
};

function MiniSparkline({ deviceId, samples }: { deviceId: string; samples: Record<string, Sample> }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const bufRef = useRef<number[]>([]);

  useEffect(() => {
    const sample = samples[deviceId];
    if (!sample) return;
    const avm = Math.sqrt(sample.acc.reduce((s, v) => s + v * v, 0));
    bufRef.current.push(avm);
    if (bufRef.current.length > 60) bufRef.current.shift();

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);

    const data = bufRef.current;
    if (data.length < 2) return;
    const min = Math.min(...data);
    const max = Math.max(...data) || 1;

    ctx.strokeStyle = "#58a6ff";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    data.forEach((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((v - min) / (max - min + 0.001)) * height;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  }, [samples, deviceId]);

  return <canvas ref={canvasRef} width={120} height={32} className="w-full h-8" />;
}

export default function DevicePanel({ devices, quorum, liveSamples, isRecording }: Props) {
  // Derive from devices directly — quorum counter can lag on reconnect.
  const onlineCount = devices.filter(d => d.is_online).length;
  const allOnline = devices.length > 0 && onlineCount === devices.length;

  return (
    <div>
      {/* Quorum indicator */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Devices</h3>
        <span className={`text-xs font-bold px-2 py-0.5 rounded ${
          onlineCount === 0
            ? "bg-red-950 text-red-400"
            : allOnline
            ? "bg-green-950 text-green-400"
            : "bg-yellow-950 text-yellow-400"
        }`}>
          {onlineCount}/{devices.length} online
        </span>
      </div>

      {devices.length === 0 && (
        <p className="text-xs text-gray-600 italic">No devices connected</p>
      )}

      <div className="space-y-2">
        {devices.map(d => {
          const colorClass = ROLE_COLOR[d.device_role] ?? "bg-gray-900 border-gray-600";
          return (
            <div
              key={d.device_id}
              className={`rounded border px-2 py-2 ${colorClass} ${!d.is_online ? "opacity-40" : ""}`}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${d.is_online ? "bg-green-400" : "bg-red-400"}`} />
                  <span className="text-xs font-bold text-white">{d.device_role}</span>
                </div>
                <span className="text-xs text-gray-400 font-mono">{d.device_id.slice(0, 8)}</span>
              </div>

              {/* Mini sparkline — acc vector magnitude */}
              <MiniSparkline deviceId={d.device_id} samples={liveSamples} />

              <div className="flex justify-between mt-1 text-xs text-gray-500">
                <span>{d.packets?.toLocaleString() ?? 0} pkts</span>
                {(d.offline_intervals ?? 0) > 0 && (
                  <span className="text-orange-400">⚠ {d.offline_intervals} gap(s)</span>
                )}
                {isRecording && d.substate === "RECORDING" && (
                  <span className="text-green-400">● live</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
