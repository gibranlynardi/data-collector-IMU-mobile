"use client";
import { useEffect, useRef } from "react";
import * as echarts from "echarts";

interface Sample { acc: number[]; gyro: number[]; ts: number; }

interface Props {
  samples: Record<string, Sample>;
  maxPoints?: number;
}

// Rolling buffer per axis.
const AXES = ["X", "Y", "Z"];
const COLORS = ["#58a6ff", "#3fb950", "#f78166"];

export default function RealtimeChart({ samples, maxPoints = 200 }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const buffers = useRef<{ acc: number[][]; gyro: number[][] }>({
    acc: [[], [], []],
    gyro: [[], [], []],
  });

  useEffect(() => {
    if (!chartRef.current) return;
    chartInstance.current = echarts.init(chartRef.current, "dark");
    chartInstance.current.setOption({
      backgroundColor: "transparent",
      animation: false,
      grid: [
        { left: 50, right: 20, top: 24, bottom: "52%" },
        { left: 50, right: 20, top: "52%", bottom: 24 },
      ],
      xAxis: [
        { gridIndex: 0, type: "category", data: [], axisLabel: { show: false }, splitLine: { show: false } },
        { gridIndex: 1, type: "category", data: [], axisLabel: { fontSize: 9 }, splitLine: { show: false } },
      ],
      yAxis: [
        { gridIndex: 0, name: "Acc (g)", nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 9 } },
        { gridIndex: 1, name: "Gyro (°/s)", nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 9 } },
      ],
      legend: { top: 4, textStyle: { fontSize: 9 }, data: [...AXES.map(a => `Acc ${a}`), ...AXES.map(a => `Gyro ${a}`)] },
      series: [
        ...AXES.map((a, i) => ({
          name: `Acc ${a}`, type: "line", xAxisIndex: 0, yAxisIndex: 0,
          data: [], showSymbol: false, lineStyle: { color: COLORS[i], width: 1 },
        })),
        ...AXES.map((a, i) => ({
          name: `Gyro ${a}`, type: "line", xAxisIndex: 1, yAxisIndex: 1,
          data: [], showSymbol: false, lineStyle: { color: COLORS[i], width: 1, type: "dashed" },
        })),
      ],
    });

    const observer = new ResizeObserver(() => chartInstance.current?.resize());
    observer.observe(chartRef.current);
    return () => { observer.disconnect(); chartInstance.current?.dispose(); };
  }, []);

  useEffect(() => {
    const firstDevice = Object.values(samples)[0];
    if (!firstDevice || !chartInstance.current) return;

    const { acc, gyro } = firstDevice;
    const buf = buffers.current;

    acc.forEach((v, i) => { buf.acc[i].push(v); if (buf.acc[i].length > maxPoints) buf.acc[i].shift(); });
    gyro.forEach((v, i) => { buf.gyro[i].push(v); if (buf.gyro[i].length > maxPoints) buf.gyro[i].shift(); });

    const labels = buf.acc[0].map((_, idx) => idx);
    chartInstance.current.setOption({
      xAxis: [{ data: labels }, { data: labels }],
      series: [
        ...buf.acc.map((d) => ({ data: d })),
        ...buf.gyro.map((d) => ({ data: d })),
      ],
    });
  }, [samples, maxPoints]);

  return (
    <div className="w-full h-full rounded bg-[#161b22] border border-[#30363d] overflow-hidden">
      <div ref={chartRef} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}
