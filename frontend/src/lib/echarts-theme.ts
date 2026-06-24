// Shared ECharts config helpers for the dark NOC theme.
export const COLORS = {
  bg: "#0f172a",
  surface: "#1e293b",
  grid: "#334155",
  text: "#94a3b8",
  textBright: "#f1f5f9",
  healthy: "#22c55e",
  warning: "#f59e0b",
  critical: "#ef4444",
  info: "#3b82f6",
  purple: "#a855f7",
  cyan: "#06b6d4",
};

export const SERIES_PALETTE = ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7", "#06b6d4", "#ef4444", "#ec4899"];

export const axisCommon = {
  axisLine: { lineStyle: { color: COLORS.grid } },
  axisLabel: { color: COLORS.text, fontSize: 10 },
  splitLine: { lineStyle: { color: COLORS.grid, opacity: 0.3 } },
};

export const tooltipCommon = {
  backgroundColor: COLORS.surface,
  borderColor: COLORS.grid,
  textStyle: { color: COLORS.textBright, fontSize: 11 },
  axisPointer: { lineStyle: { color: COLORS.grid } },
};

export const gridCommon = { left: 44, right: 16, top: 24, bottom: 28, containLabel: true };

// Threshold band markArea for a metric (green/yellow/red zones)
export function thresholdBands(warn: number, crit: number, max: number) {
  return {
    silent: true,
    data: [
      [{ yAxis: 0, itemStyle: { color: "rgba(34,197,94,0.06)" } }, { yAxis: warn }],
      [{ yAxis: warn, itemStyle: { color: "rgba(245,158,11,0.08)" } }, { yAxis: crit }],
      [{ yAxis: crit, itemStyle: { color: "rgba(239,68,68,0.10)" } }, { yAxis: max }],
    ],
  };
}

export function thresholdLines(warn: number, crit: number) {
  return {
    silent: true,
    symbol: "none",
    label: { color: COLORS.text, fontSize: 9, position: "insideEndTop" },
    data: [
      { yAxis: warn, lineStyle: { color: COLORS.warning, type: "dashed", opacity: 0.6 }, label: { formatter: "WARN" } },
      { yAxis: crit, lineStyle: { color: COLORS.critical, type: "dashed", opacity: 0.6 }, label: { formatter: "CRIT" } },
    ],
  };
}

// Convert [{t, v}] -> [[ms, v]] for time-axis charts
export function toPairs(series: { t: string; v: number }[]) {
  return (series ?? []).map((p) => [new Date(p.t).getTime(), p.v]);
}
