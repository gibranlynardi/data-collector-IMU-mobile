"use client";
import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { DeviceInfo } from "@/lib/ws_client";
import { roleHex } from "@/lib/roleColors";

interface Sample { acc: number[]; gyro: number[]; ts: number }

interface Props {
  samples: Record<string, Sample>;
  devices: DeviceInfo[];
  maxPoints?: number;
}

// X / Y / Z line colors — shared by ACC and GYRO (the named grids disambiguate them).
const AXES = ["X", "Y", "Z"];
const COLORS = ["#58a6ff", "#3fb950", "#f78166"];

// ── One node: its own ECharts instance (ACC top grid + GYRO bottom grid) ──────
function NodeChartCard({
  deviceId, role, isOnline, samples, maxPoints,
}: {
  deviceId: string; role: string; isOnline: boolean;
  samples: Record<string, Sample>; maxPoints: number;
}) {
  const elRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const lastTsRef = useRef<number>(-1);
  const buffers = useRef<{ acc: number[][]; gyro: number[][] }>({
    acc: [[], [], []],
    gyro: [[], [], []],
  });

  // Init once per card. Deps are stable (deviceId fixed per slot) → no re-init churn.
  useEffect(() => {
    if (!elRef.current) return;
    const chart = echarts.init(elRef.current, "dark");
    chartRef.current = chart;
    chart.setOption({
      backgroundColor: "transparent",
      animation: false,
      grid: [
        { left: 40, right: 12, top: 18, bottom: "54%" },   // ACC
        { left: 40, right: 12, top: "56%", bottom: 18 },   // GYRO
      ],
      xAxis: [
        { gridIndex: 0, type: "category", data: [], axisLabel: { show: false }, axisTick: { show: false }, splitLine: { show: false } },
        { gridIndex: 1, type: "category", data: [], axisLabel: { show: false }, axisTick: { show: false }, splitLine: { show: false } },
      ],
      yAxis: [
        { gridIndex: 0, name: "ACC g", nameTextStyle: { fontSize: 9, color: "#8b949e" }, scale: true, axisLabel: { fontSize: 8 }, splitLine: { lineStyle: { opacity: 0.12 } } },
        { gridIndex: 1, name: "GYR °/s", nameTextStyle: { fontSize: 9, color: "#8b949e" }, scale: true, axisLabel: { fontSize: 8 }, splitLine: { lineStyle: { opacity: 0.12 } } },
      ],
      series: [
        ...AXES.map((a, i) => ({
          name: `acc${a}`, type: "line", xAxisIndex: 0, yAxisIndex: 0,
          data: [], showSymbol: false, lineStyle: { color: COLORS[i], width: 1 },
        })),
        ...AXES.map((a, i) => ({
          name: `gyr${a}`, type: "line", xAxisIndex: 1, yAxisIndex: 1,
          data: [], showSymbol: false, lineStyle: { color: COLORS[i], width: 1 },
        })),
      ],
    });

    const observer = new ResizeObserver(() => chartRef.current?.resize());
    observer.observe(elRef.current);
    return () => { observer.disconnect(); chart.dispose(); chartRef.current = null; };
  }, [deviceId]);

  // Push one frame per NEW sample (ts-dedup) for THIS device.
  useEffect(() => {
    const sample = samples[deviceId];
    const chart = chartRef.current;
    if (!sample || !chart) return;
    if (sample.ts === lastTsRef.current) return;   // skip duplicate frames
    lastTsRef.current = sample.ts;

    const { acc, gyro } = sample;
    const buf = buffers.current;
    acc.forEach((v, i) => { buf.acc[i].push(v); if (buf.acc[i].length > maxPoints) buf.acc[i].shift(); });
    gyro.forEach((v, i) => { buf.gyro[i].push(v); if (buf.gyro[i].length > maxPoints) buf.gyro[i].shift(); });

    const labels = buf.acc[0].map((_, idx) => idx);
    chart.setOption({
      xAxis: [{ data: labels }, { data: labels }],
      series: [
        ...buf.acc.map((d) => ({ data: d })),
        ...buf.gyro.map((d) => ({ data: d })),
      ],
    });
  }, [samples, deviceId, maxPoints]);

  const hasData = !!samples[deviceId];

  return (
    <div
      className={`rounded bg-[#161b22] border border-[#30363d] border-l-2 flex flex-col overflow-hidden ${isOnline ? "" : "opacity-50"}`}
      style={{ height: 200, borderLeftColor: roleHex(role) }}
    >
      {/* Header: node identity + X/Y/Z legend */}
      <div className="flex items-center justify-between px-2 py-1 border-b border-[#30363d] shrink-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: roleHex(role) }} />
          <span className="text-xs font-bold text-white truncate">{role}</span>
          <span className="text-[10px] text-gray-500 font-mono truncate">{deviceId.slice(0, 8)}</span>
          {!isOnline && <span className="text-[10px] text-red-400">offline</span>}
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono">
          {AXES.map((a, i) => (
            <span key={a} style={{ color: COLORS[i] }}>{a}</span>
          ))}
        </div>
      </div>
      {/* Chart body (ECharts needs a definite height — flex-1 inside the fixed-height card) */}
      <div className="relative flex-1 min-h-0">
        <div ref={elRef} className="w-full h-full" />
        {!hasData && (
          <div className="absolute inset-0 flex items-center justify-center text-[11px] text-gray-600 italic pointer-events-none">
            waiting for data…
          </div>
        )}
      </div>
    </div>
  );
}

// ── Container: one card per node, responsive small-multiples grid ─────────────
export default function RealtimeChart({ samples, devices, maxPoints = 200 }: Props) {
  if (devices.length === 0) {
    return (
      <div className="w-full h-full rounded bg-[#161b22] border border-[#30363d] flex items-center justify-center">
        <p className="text-xs text-gray-600 italic">No nodes streaming — connect a node to see live signals</p>
      </div>
    );
  }
  return (
    <div className="w-full h-full overflow-y-auto pr-1">
      <div
        className="grid gap-3"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", alignContent: "start" }}
      >
        {devices.map((d) => (
          <NodeChartCard
            key={d.device_id}
            deviceId={d.device_id}
            role={d.role}
            isOnline={d.is_online}
            samples={samples}
            maxPoints={maxPoints}
          />
        ))}
      </div>
    </div>
  );
}
