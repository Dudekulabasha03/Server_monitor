"use client";
import ReactECharts from "echarts-for-react";
import { axisCommon, tooltipCommon, gridCommon, COLORS } from "@/lib/echarts-theme";

// Scatter: power (x) vs temperature (y) — reveals cooling/efficiency correlation.
export function CorrelationChart({ points, height = 260 }: {
  points: { power: number; temp: number }[]; height?: number;
}) {
  const data = (points ?? []).map((p) => [p.power, p.temp]);
  const option: any = {
    grid: gridCommon,
    tooltip: { ...tooltipCommon, formatter: (p: any) => `Power: ${p.value[0]}W<br/>Temp: ${p.value[1]}°C` },
    xAxis: { type: "value", name: "Power (W)", scale: true, nameTextStyle: { color: COLORS.text, fontSize: 9 }, ...axisCommon },
    yAxis: { type: "value", name: "Temp (°C)", scale: true, nameTextStyle: { color: COLORS.text, fontSize: 9 }, ...axisCommon },
    series: [{
      type: "scatter", symbolSize: 5, data,
      itemStyle: { color: COLORS.cyan, opacity: 0.45 },
    }],
  };
  if (!data.length) {
    return <div className="flex items-center justify-center text-sm text-text-muted" style={{ height }}>No correlation data</div>;
  }
  return <ReactECharts option={option} style={{ height, width: "100%" }} opts={{ renderer: "canvas" }} notMerge lazyUpdate />;
}
