"use client";
import ReactECharts from "echarts-for-react";
import { COLORS, axisCommon, tooltipCommon } from "@/lib/echarts-theme";

// Heatmap: racks (x) × U position (y), colored by temperature.
export function RackHeatmap({ servers, height = 360 }: {
  servers: { rack: string | null; rack_unit: number | null; cpu_temp_max: number | null; hostname: string }[];
  height?: number;
}) {
  const racks = Array.from(new Set(servers.map((s) => s.rack).filter(Boolean))) as string[];
  racks.sort();
  const data: any[] = [];
  for (const s of servers) {
    if (!s.rack || s.rack_unit == null || s.cpu_temp_max == null) continue;
    data.push([racks.indexOf(s.rack), s.rack_unit, Math.round(s.cpu_temp_max), s.hostname]);
  }
  const maxU = Math.max(42, ...servers.map((s) => s.rack_unit ?? 0));

  const option: any = {
    grid: { left: 50, right: 16, top: 16, bottom: 60, containLabel: true },
    tooltip: {
      ...tooltipCommon,
      formatter: (p: any) => `${p.data[3]}<br/>Rack ${racks[p.data[0]]} · U${p.data[1]}<br/><b>${p.data[2]}°C</b>`,
    },
    xAxis: { type: "category", data: racks, ...axisCommon, axisLabel: { ...axisCommon.axisLabel, rotate: 45 } },
    yAxis: { type: "category", data: Array.from({ length: maxU }, (_, i) => `U${i + 1}`), ...axisCommon },
    visualMap: {
      min: 25, max: 90, calculable: true, orient: "horizontal", left: "center", bottom: 8,
      inRange: { color: ["#1e3a8a", "#22c55e", "#f59e0b", "#ef4444"] },
      textStyle: { color: COLORS.text, fontSize: 9 },
    },
    series: [{
      type: "heatmap", data,
      label: { show: false },
      itemStyle: { borderColor: COLORS.bg, borderWidth: 1 },
      emphasis: { itemStyle: { borderColor: "#fff", borderWidth: 1 } },
    }],
  };
  return <ReactECharts option={option} style={{ height, width: "100%" }} opts={{ renderer: "canvas" }} notMerge lazyUpdate />;
}
