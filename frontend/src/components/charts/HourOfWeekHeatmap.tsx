"use client";
import ReactECharts from "echarts-for-react";
import { COLORS, axisCommon, tooltipCommon } from "@/lib/echarts-theme";

const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// 7 (dow) x 24 (hour) heatmap. grid: [{dow,hour,value}]. dow 0=Sunday.
export function HourOfWeekHeatmap({ grid, palette = "blue", height = 200, max }: {
  grid: { dow: number; hour: number; value: number }[];
  palette?: "blue" | "util"; height?: number; max?: number;
}) {
  const data = (grid ?? []).map((g) => [g.hour, g.dow, g.value]);
  const vmax = max ?? Math.max(1, ...(grid ?? []).map((g) => g.value));

  const now = new Date();
  const curHour = now.getHours();
  const curDow = now.getDay();

  const inRange =
    palette === "util"
      ? ["#16a34a", "#a3e635", "#f59e0b", "#ef4444"] // green→red (idle→heavy)
      : ["#0f2747", "#1d4ed8", "#3b82f6", "#93c5fd"]; // dark→light blue (test volume)

  const option: any = {
    grid: { left: 38, right: 12, top: 8, bottom: 36, containLabel: true },
    tooltip: {
      ...tooltipCommon,
      formatter: (p: any) => `${DOW[p.value[1]]} ${String(p.value[0]).padStart(2, "0")}:00<br/><b>${p.value[2]}</b>`,
    },
    xAxis: {
      type: "category", data: Array.from({ length: 24 }, (_, i) => i),
      ...axisCommon, splitArea: { show: false },
      axisLabel: { ...axisCommon.axisLabel, interval: 0, fontSize: 9 },
    },
    yAxis: { type: "category", data: DOW, ...axisCommon, splitArea: { show: false } },
    visualMap: {
      min: 0, max: vmax, calculable: false, show: false,
      inRange: { color: inRange },
    },
    series: [{
      type: "heatmap", data,
      itemStyle: { borderColor: COLORS.bg, borderWidth: 1 },
      emphasis: { itemStyle: { borderColor: "#fff", borderWidth: 1 } },
      markPoint: {
        symbol: "rect", symbolSize: [14, 14], silent: true,
        itemStyle: { color: "transparent", borderColor: "#f59e0b", borderWidth: 2 },
        data: [{ coord: [curHour, curDow] }],
      },
    }],
  };
  if (!data.length) {
    return <div className="flex items-center justify-center text-sm text-text-muted" style={{ height }}>Accruing history…</div>;
  }
  return <ReactECharts option={option} style={{ height, width: "100%" }} opts={{ renderer: "canvas" }} notMerge lazyUpdate />;
}
