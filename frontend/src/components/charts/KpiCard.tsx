"use client";
import ReactECharts from "echarts-for-react";
import { ArrowUp, ArrowDown, Minus } from "lucide-react";
import { COLORS } from "@/lib/echarts-theme";

export function KpiCard({
  label, value, unit, change, dir, spark, color = COLORS.info, suffix,
}: {
  label: string; value: number | string | null; unit?: string;
  change?: number | null; dir?: "up" | "down" | "flat"; spark?: number[];
  color?: string; suffix?: string;
}) {
  const Arrow = dir === "up" ? ArrowUp : dir === "down" ? ArrowDown : Minus;
  const arrowColor = dir === "up" ? "text-red-400" : dir === "down" ? "text-green-400" : "text-text-muted";

  const sparkOption = {
    grid: { left: 0, right: 0, top: 2, bottom: 2 },
    xAxis: { type: "category", show: false, data: (spark ?? []).map((_, i) => i) },
    yAxis: { type: "value", show: false, scale: true },
    series: [{
      type: "line", data: spark ?? [], smooth: true, symbol: "none",
      lineStyle: { color, width: 1.5 },
      areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: color + "44" }, { offset: 1, color: color + "00" }] } },
    }],
    tooltip: { show: false },
  };

  return (
    <div className="glass-card">
      <p className="metric-label">{label}</p>
      <div className="flex items-end justify-between gap-2 mt-1">
        <p className="text-2xl font-bold tabular-nums text-text-primary">
          {value ?? "—"}<span className="text-sm text-text-muted ml-0.5">{unit}</span>
        </p>
        {change != null && (
          <span className={`flex items-center text-xs ${arrowColor}`}>
            <Arrow size={12} />{Math.abs(change)}{suffix ?? ""}
          </span>
        )}
      </div>
      {spark && spark.length > 1 && (
        <div className="h-8 mt-1 -mx-1">
          <ReactECharts option={sparkOption} style={{ height: "100%", width: "100%" }} opts={{ renderer: "svg" }} />
        </div>
      )}
    </div>
  );
}
