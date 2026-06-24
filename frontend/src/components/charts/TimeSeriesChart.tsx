"use client";
import ReactECharts from "echarts-for-react";
import { axisCommon, tooltipCommon, gridCommon, thresholdBands, thresholdLines, toPairs, COLORS } from "@/lib/echarts-theme";

// Config-driven time-series line with threshold bands + cross markers + zoom.
export function TimeSeriesChart({
  series, name, color = COLORS.info, unit = "", warn, crit, max, height = 220, zoom = true,
}: {
  series: { t: string; v: number }[];
  name: string; color?: string; unit?: string;
  warn?: number; crit?: number; max?: number; height?: number; zoom?: boolean;
}) {
  const pairs = toPairs(series);
  const hasThresh = warn != null && crit != null && max != null;

  // Mark threshold-cross points
  const breaches = pairs.filter(([, v]) => crit != null && v >= crit).map(([t, v]) => ({ xAxis: t, yAxis: v }));

  const option: any = {
    grid: gridCommon,
    tooltip: { trigger: "axis", ...tooltipCommon, valueFormatter: (v: number) => `${v?.toFixed?.(1) ?? v}${unit}` },
    xAxis: { type: "time", ...axisCommon },
    yAxis: { type: "value", scale: true, name: unit, nameTextStyle: { color: COLORS.text, fontSize: 9 }, ...axisCommon },
    dataZoom: zoom ? [{ type: "inside" }, { type: "slider", height: 14, bottom: 4, borderColor: COLORS.grid, fillerColor: "rgba(59,130,246,0.15)", textStyle: { color: COLORS.text, fontSize: 9 } }] : undefined,
    series: [{
      name, type: "line", showSymbol: false, smooth: true, data: pairs,
      lineStyle: { color, width: 1.8 },
      areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: color + "33" }, { offset: 1, color: color + "00" }] } },
      markArea: hasThresh ? thresholdBands(warn!, crit!, max!) : undefined,
      markLine: hasThresh ? thresholdLines(warn!, crit!) : undefined,
      markPoint: breaches.length ? {
        symbol: "pin", symbolSize: 28, data: breaches.slice(0, 20),
        itemStyle: { color: COLORS.critical }, label: { formatter: "🔴", fontSize: 10 },
      } : undefined,
    }],
  };

  return <ReactECharts option={option} style={{ height, width: "100%" }} opts={{ renderer: "canvas" }} notMerge lazyUpdate />;
}
