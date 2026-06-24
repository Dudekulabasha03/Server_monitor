"use client";
import ReactECharts from "echarts-for-react";
import { axisCommon, tooltipCommon, gridCommon, toPairs, COLORS } from "@/lib/echarts-theme";

// Actual line + expected band (upper/lower) + flagged anomaly points.
export function AnomalyChart({ data, unit = "", height = 240 }: {
  data: { actual: any[]; upper: any[]; lower: any[]; anomalies: any[]; anomaly_score: number };
  unit?: string; height?: number;
}) {
  const lower = toPairs(data.lower);
  const upperDelta = toPairs(data.upper).map((p, i) => [p[0], p[1] - (lower[i]?.[1] ?? 0)]);

  const option: any = {
    grid: gridCommon,
    tooltip: { trigger: "axis", ...tooltipCommon },
    xAxis: { type: "time", ...axisCommon },
    yAxis: { type: "value", scale: true, ...axisCommon },
    series: [
      // Band base (transparent) + band height (shaded) via stacked areas
      { name: "lband", type: "line", stack: "band", data: lower, lineStyle: { opacity: 0 }, symbol: "none", silent: true, areaStyle: { color: "transparent" } },
      { name: "band", type: "line", stack: "band", data: upperDelta, lineStyle: { opacity: 0 }, symbol: "none", silent: true, areaStyle: { color: "rgba(59,130,246,0.12)" } },
      { name: "Actual", type: "line", data: toPairs(data.actual), showSymbol: false, smooth: true, lineStyle: { color: COLORS.cyan, width: 1.8 } },
      { name: "Anomaly", type: "scatter", symbolSize: 9, data: (data.anomalies ?? []).map((a) => [new Date(a.t).getTime(), a.v]), itemStyle: { color: COLORS.critical, borderColor: "#fff", borderWidth: 1 } },
    ],
  };
  return <ReactECharts option={option} style={{ height, width: "100%" }} opts={{ renderer: "canvas" }} notMerge lazyUpdate />;
}
