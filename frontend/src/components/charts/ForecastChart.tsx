"use client";
import ReactECharts from "echarts-for-react";
import { axisCommon, tooltipCommon, gridCommon, toPairs, COLORS } from "@/lib/echarts-theme";

// Solid actual + dashed forecast + optional capacity line + exhaustion marker.
export function ForecastChart({ data, unit = "", cap, height = 240 }: {
  data: { actual: any[]; forecast: any[]; slope_per_hour: number; exhaustion: string | null };
  unit?: string; cap?: number; height?: number;
}) {
  const option: any = {
    grid: gridCommon,
    legend: { top: 0, textStyle: { color: COLORS.text, fontSize: 10 } },
    tooltip: { trigger: "axis", ...tooltipCommon, valueFormatter: (v: number) => `${v?.toFixed?.(1) ?? v}${unit}` },
    xAxis: { type: "time", ...axisCommon },
    yAxis: { type: "value", scale: true, ...axisCommon },
    series: [
      { name: "Actual", type: "line", data: toPairs(data.actual), showSymbol: false, smooth: true, lineStyle: { color: COLORS.info, width: 1.8 } },
      {
        name: "Forecast", type: "line", data: toPairs(data.forecast), showSymbol: false, smooth: true,
        lineStyle: { color: COLORS.warning, width: 1.8, type: "dashed" },
        markLine: cap != null ? {
          silent: true, symbol: "none",
          data: [{ yAxis: cap, lineStyle: { color: COLORS.critical, type: "solid", width: 1.5 }, label: { formatter: `Limit ${cap}${unit}`, color: COLORS.critical, fontSize: 9 } }],
        } : undefined,
      },
    ],
  };
  return (
    <div>
      <ReactECharts option={option} style={{ height, width: "100%" }} opts={{ renderer: "canvas" }} notMerge lazyUpdate />
      {data.exhaustion && (
        <p className="text-xs text-red-400 mt-1">⚠ Projected to reach limit: {new Date(data.exhaustion).toLocaleString()}</p>
      )}
    </div>
  );
}
