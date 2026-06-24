"use client";
import ReactECharts from "echarts-for-react";

/**
 * Renders a chart from an AI-emitted spec:
 *   { "type": "bar"|"hbar"|"line"|"pie",
 *     "title": "...", "unit": "°C",
 *     "categories": ["a","b"], "series": [{"name":"CPU","data":[1,2]}] }
 * Pie uses: "data": [{"name":"Healthy","value":89}, ...]
 */
const PALETTE = ["#22d3ee", "#e879f9", "#f59e0b", "#22c55e", "#ef4444", "#a78bfa", "#38bdf8", "#fb7185"];
const AXIS = "#94a3b8";
const GRID = "rgba(51,65,85,0.4)";

export function ChartBlock({ spec }: { spec: any }) {
  if (!spec || !spec.type) return null;
  const t = spec.type;
  const title = spec.title;
  const unit = spec.unit || "";
  const cats: string[] = spec.categories || (spec.data || []).map((d: any) => d.name);
  const series = spec.series || [];

  const base: any = {
    backgroundColor: "transparent",
    grid: { left: t === "hbar" ? 110 : 44, right: 20, top: title ? 36 : 16, bottom: 36 },
    title: title ? { text: title, left: "center", textStyle: { color: "#e2e8f0", fontSize: 13, fontWeight: 600 } } : undefined,
    tooltip: { trigger: t === "pie" ? "item" : "axis", backgroundColor: "rgba(15,23,42,0.95)",
               borderColor: "#1e293b", textStyle: { color: "#e2e8f0", fontSize: 11 } },
    legend: series.length > 1 ? { top: title ? 8 : 0, right: 8, textStyle: { color: AXIS, fontSize: 10 } } : undefined,
  };

  let option: any;
  if (t === "pie") {
    option = {
      ...base,
      series: [{
        type: "pie", radius: ["42%", "70%"], center: ["50%", "55%"],
        data: (spec.data || []).map((d: any, i: number) => ({ ...d, itemStyle: { color: PALETTE[i % PALETTE.length] } })),
        label: { color: "#e2e8f0", fontSize: 11, formatter: "{b}: {c}" },
        emphasis: { itemStyle: { shadowBlur: 14, shadowColor: "rgba(34,211,238,0.4)" } },
      }],
    };
  } else if (t === "hbar") {
    option = {
      ...base,
      xAxis: { type: "value", axisLabel: { color: AXIS, fontSize: 10 }, splitLine: { lineStyle: { color: GRID } } },
      yAxis: { type: "category", data: cats, inverse: true, axisLabel: { color: AXIS, fontSize: 10 }, axisLine: { lineStyle: { color: "#334155" } } },
      series: series.map((s: any, i: number) => ({
        name: s.name, type: "bar", data: s.data, barWidth: "60%",
        itemStyle: { color: PALETTE[i % PALETTE.length], borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", color: AXIS, fontSize: 10, formatter: `{c}${unit}` },
      })),
    };
  } else {
    const isLine = t === "line";
    option = {
      ...base,
      xAxis: { type: "category", data: cats, boundaryGap: !isLine,
               axisLabel: { color: AXIS, fontSize: 10, rotate: cats.length > 8 ? 30 : 0 },
               axisLine: { lineStyle: { color: "#334155" } } },
      yAxis: { type: "value", name: unit, nameTextStyle: { color: AXIS, fontSize: 9 },
               axisLabel: { color: AXIS, fontSize: 10 }, splitLine: { lineStyle: { color: GRID } } },
      series: series.map((s: any, i: number) => ({
        name: s.name, type: isLine ? "line" : "bar", data: s.data, smooth: isLine,
        showSymbol: isLine, symbolSize: 6,
        barWidth: series.length > 1 ? undefined : "55%",
        itemStyle: { color: PALETTE[i % PALETTE.length], borderRadius: isLine ? 0 : [4, 4, 0, 0] },
        lineStyle: isLine ? { width: 3, color: PALETTE[i % PALETTE.length], shadowColor: PALETTE[i % PALETTE.length] + "88", shadowBlur: 10 } : undefined,
        areaStyle: isLine ? { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: PALETTE[i % PALETTE.length] + "55" }, { offset: 1, color: PALETTE[i % PALETTE.length] + "00" }] } } : undefined,
      })),
    };
  }

  const h = t === "hbar" ? Math.max(180, (cats.length || 1) * 28 + 70) : 280;
  return (
    <div className="my-3 rounded-xl border border-surface-2 bg-surface/50 p-2">
      <ReactECharts style={{ height: h }} opts={{ renderer: "canvas" }} option={option} />
    </div>
  );
}
