"use client";
import ReactECharts from "echarts-for-react";
import { COLORS } from "@/lib/echarts-theme";

// ECG-style heartbeat pulse. alive=steady pulse, late=weak, stale=flatline.
// Pure visual generated from beat state; phase offset by index for variety.
function ecg(beat: string, idx: number): number[] {
  const n = 60;
  if (beat === "stale") return Array(n).fill(0);
  const amp = beat === "alive" ? 1 : 0.4;
  const period = beat === "alive" ? 15 : 24;
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const pos = (i + idx * 3) % period;
    // spike near start of each period (QRS-like)
    let v = 0;
    if (pos === 2) v = -0.2 * amp;
    else if (pos === 3) v = 1.0 * amp;
    else if (pos === 4) v = -0.4 * amp;
    else if (pos === 5) v = 0.15 * amp;
    out.push(v);
  }
  return out;
}

export function HeartbeatLine({ beat, idx = 0, height = 26 }: { beat: string; idx?: number; height?: number }) {
  const color = beat === "alive" ? COLORS.healthy : beat === "late" ? COLORS.warning : COLORS.critical;
  const data = ecg(beat, idx);
  const option = {
    grid: { left: 0, right: 0, top: 2, bottom: 2 },
    xAxis: { type: "category", show: false, data: data.map((_, i) => i) },
    yAxis: { type: "value", show: false, min: -0.6, max: 1.1 },
    series: [{
      type: "line", data, smooth: false, symbol: "none",
      lineStyle: { color, width: 1.5 },
    }],
    tooltip: { show: false },
    animation: beat !== "stale",
  };
  return (
    <div className={beat === "stale" ? "hb-stale" : ""}>
      <ReactECharts option={option} style={{ height, width: "100%" }} opts={{ renderer: "svg" }} />
    </div>
  );
}
