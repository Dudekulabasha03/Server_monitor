"use client";
import ReactECharts from "echarts-for-react";
import { axisCommon, tooltipCommon, gridCommon, toPairs, SERIES_PALETTE, COLORS } from "@/lib/echarts-theme";

// Multi-metric overlay (temperatures, or server-compare). Each line config-driven.
export function MultiLineChart({
  lines, unit = "", height = 240, dashedFrom,
}: {
  lines: { name: string; series: { t: string; v: number }[]; color?: string; dashed?: boolean }[];
  unit?: string; height?: number; dashedFrom?: number;
}) {
  const option: any = {
    grid: gridCommon,
    legend: { top: 0, textStyle: { color: COLORS.text, fontSize: 10 }, type: "scroll" },
    tooltip: { trigger: "axis", ...tooltipCommon, valueFormatter: (v: number) => `${v?.toFixed?.(1) ?? v}${unit}` },
    xAxis: { type: "time", ...axisCommon },
    yAxis: { type: "value", scale: true, ...axisCommon },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 14, bottom: 2, borderColor: COLORS.grid, fillerColor: "rgba(59,130,246,0.15)", textStyle: { color: COLORS.text, fontSize: 9 } }],
    series: lines.map((l, i) => ({
      name: l.name, type: "line", showSymbol: false, smooth: true, data: toPairs(l.series),
      lineStyle: { color: l.color ?? SERIES_PALETTE[i % SERIES_PALETTE.length], width: 1.6, type: l.dashed ? "dashed" : "solid" },
      itemStyle: { color: l.color ?? SERIES_PALETTE[i % SERIES_PALETTE.length] },
    })),
  };
  return <ReactECharts option={option} style={{ height, width: "100%" }} opts={{ renderer: "canvas" }} notMerge lazyUpdate />;
}
