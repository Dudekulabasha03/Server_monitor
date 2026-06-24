"use client";
import ReactECharts from "echarts-for-react";
import { axisCommon, tooltipCommon, COLORS } from "@/lib/echarts-theme";

const SEV_Y: Record<string, number> = { info: 1, warning: 2, critical: 3, emergency: 3 };
const SEV_COLOR: Record<string, string> = { info: COLORS.info, warning: COLORS.warning, critical: COLORS.critical, emergency: COLORS.critical };

// Scatter-on-time timeline of alert events; y = severity tier.
export function AlertTimeline({ alerts, height = 180 }: { alerts: any[]; height?: number }) {
  const data = (alerts ?? []).map((a) => ({
    value: [new Date(a.fired_at).getTime(), SEV_Y[a.severity] ?? 1],
    itemStyle: { color: SEV_COLOR[a.severity] ?? COLORS.info },
    name: a.title, message: a.message, severity: a.severity,
  }));

  const option: any = {
    grid: { left: 70, right: 16, top: 16, bottom: 28 },
    tooltip: {
      ...tooltipCommon,
      formatter: (p: any) => `${new Date(p.value[0]).toLocaleString()}<br/><b>${p.data.name}</b><br/>${p.data.message ?? ""}`,
    },
    xAxis: { type: "time", ...axisCommon },
    yAxis: {
      type: "value", min: 0, max: 4, interval: 1, ...axisCommon,
      axisLabel: { ...axisCommon.axisLabel, formatter: (v: number) => ({ 1: "Info", 2: "Warn", 3: "Crit" } as any)[v] ?? "" },
    },
    series: [{ type: "scatter", symbolSize: 14, data }],
  };
  if (!data.length) {
    return <div className="flex items-center justify-center text-sm text-text-muted" style={{ height }}>No alert events in range</div>;
  }
  return <ReactECharts option={option} style={{ height, width: "100%" }} opts={{ renderer: "canvas" }} notMerge lazyUpdate />;
}
