"use client";
import { useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import ReactECharts from "echarts-for-react";
import { fleetApi } from "@/lib/api";
import { Activity, Play, Pause, Radio } from "lucide-react";

const METRICS = [
  { key: "cpu", label: "CPU %", unit: "%" },
  { key: "memory", label: "Memory %", unit: "%" },
  { key: "power", label: "Power (W)", unit: "W" },
  { key: "temperature", label: "Temperature °C", unit: "°C" },
  { key: "load", label: "Load (1m)", unit: "" },
];
const PALETTE = ["#22d3ee", "#e879f9", "#f59e0b", "#22c55e", "#ef4444", "#a78bfa", "#38bdf8", "#fb7185", "#34d399", "#f472b6"];
const MAX_POINTS = 30;

export default function LiveMonitorPage() {
  return (
    <Suspense fallback={<div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400" /></div>}>
      <LiveMonitorInner />
    </Suspense>
  );
}

function LiveMonitorInner() {
  const sp = useSearchParams();
  const [hosts, setHosts] = useState<string[]>([]);
  const [hostInput, setHostInput] = useState("");
  const [metric, setMetric] = useState("cpu");
  const [running, setRunning] = useState(false);
  const [series, setSeries] = useState<Record<string, { t: string; v: number | null }[]>>({});
  const [latest, setLatest] = useState<Record<string, any>>({});
  const [info, setInfo] = useState<{ source?: string; unit?: string; reachable?: number; total?: number }>({});
  const timer = useRef<any>(null);

  // Seed from URL (?servers=a,b,c&metric=power) — lets Ask Helios deep-link here.
  useEffect(() => {
    const s = sp.get("servers");
    const m = sp.get("metric");
    if (m) setMetric(m);
    if (s) {
      const list = s.split(",").map((x) => x.trim()).filter(Boolean);
      setHosts(list);
      if (list.length) setRunning(true);
    }
  }, [sp]);

  const poll = async () => {
    if (!hosts.length) return;
    try {
      const d = await fleetApi.liveSample(hosts, metric);
      setInfo({ source: d.source, unit: d.unit, reachable: d.reachable, total: d.total });
      const t = new Date(d.t).toLocaleTimeString();
      const lt: Record<string, any> = {};
      setSeries((prev) => {
        const next = { ...prev };
        for (const s of d.samples) {
          lt[s.hostname] = s;
          const arr = (next[s.hostname] ?? []).concat({ t, v: s.value });
          next[s.hostname] = arr.slice(-MAX_POINTS);
        }
        return next;
      });
      setLatest(lt);
    } catch { /* keep streaming */ }
  };

  useEffect(() => {
    if (running && hosts.length) {
      poll();
      timer.current = setInterval(poll, 5000);
      return () => clearInterval(timer.current);
    }
    clearInterval(timer.current);
  }, [running, hosts, metric]);

  const addHosts = () => {
    const list = hostInput.split(/[\s,;\n]+/).map((x) => x.trim()).filter(Boolean);
    if (list.length) { setHosts((p) => Array.from(new Set([...p, ...list]))); setHostInput(""); }
  };

  const m = METRICS.find((x) => x.key === metric)!;
  const times = Object.values(series)[0]?.map((p) => p.t) ?? [];
  const option = {
    backgroundColor: "transparent",
    grid: { left: 48, right: 16, top: 30, bottom: 30 },
    tooltip: { trigger: "axis", backgroundColor: "rgba(15,23,42,0.95)", borderColor: "#1e293b", textStyle: { color: "#e2e8f0", fontSize: 11 } },
    legend: { top: 0, textStyle: { color: "#94a3b8", fontSize: 10 }, type: "scroll" },
    xAxis: { type: "category", data: times, axisLabel: { color: "#94a3b8", fontSize: 9 }, axisLine: { lineStyle: { color: "#334155" } } },
    yAxis: { type: "value", name: m.unit, nameTextStyle: { color: "#94a3b8", fontSize: 9 }, axisLabel: { color: "#94a3b8", fontSize: 10 }, splitLine: { lineStyle: { color: "rgba(51,65,85,0.4)" } } },
    series: Object.entries(series).map(([host, pts], i) => ({
      name: host, type: "line", smooth: true, showSymbol: false, connectNulls: false,
      data: pts.map((p) => p.v),
      lineStyle: { width: 2.5, color: PALETTE[i % PALETTE.length], shadowColor: PALETTE[i % PALETTE.length] + "88", shadowBlur: 8 },
      itemStyle: { color: PALETTE[i % PALETTE.length] },
    })),
  };

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2">
          <Radio size={18} className="text-cyan-400" /> Live Monitor — Server Comparison
        </h1>
        <p className="text-sm text-text-muted">Live SSH/BMC sampling every 5s · compare power, temperature, CPU &amp; memory across servers.</p>
      </div>

      {/* Controls */}
      <div className="card p-3 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-64">
          <label className="text-xs text-text-muted mb-1 block">Servers (comma/space separated)</label>
          <div className="flex gap-2">
            <input value={hostInput} onChange={(e) => setHostInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addHosts()}
              placeholder="volcano-9a44, titanite-d534…"
              className="flex-1 bg-surface-2 border border-surface-2 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-cyan-500" />
            <button onClick={addHosts} className="px-3 py-1.5 text-xs bg-surface-2 hover:bg-surface-2/80 rounded">Add</button>
          </div>
        </div>
        <div>
          <label className="text-xs text-text-muted mb-1 block">Metric</label>
          <select value={metric} onChange={(e) => { setMetric(e.target.value); setSeries({}); }}
            className="bg-surface-2 border border-surface-2 rounded px-2 py-1.5 text-sm focus:outline-none">
            {METRICS.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
          </select>
        </div>
        <button onClick={() => setRunning((r) => !r)} disabled={!hosts.length}
          className={`px-3 py-1.5 text-sm rounded flex items-center gap-1 font-semibold disabled:opacity-40 ${running ? "bg-red-700 hover:bg-red-600" : "bg-green-700 hover:bg-green-600"}`}>
          {running ? <><Pause size={13} /> Stop</> : <><Play size={13} /> Start</>}
        </button>
      </div>

      {/* Selected hosts */}
      {hosts.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {hosts.map((h, i) => (
            <span key={h} className="text-xs rounded-full px-2 py-1 flex items-center gap-1.5 border border-surface-2"
              style={{ color: PALETTE[i % PALETTE.length] }}>
              <span className="w-2 h-2 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
              {h}
              {latest[h] && <span className="text-text-muted">{latest[h].value == null ? "N/A" : `${latest[h].value}${info.unit ?? ""}`}</span>}
              <button onClick={() => { setHosts((p) => p.filter((x) => x !== h)); setSeries((p) => { const n = { ...p }; delete n[h]; return n; }); }}
                className="text-text-muted hover:text-red-400">×</button>
            </span>
          ))}
        </div>
      )}

      {/* Live chart */}
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-text-secondary flex items-center gap-2">
            {running && <span className="relative flex h-2 w-2"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" /><span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400" /></span>}
            {m.label} — live {info.source ? `(${info.source.toUpperCase()})` : ""}
          </h3>
          {info.total != null && <span className="text-xs text-text-muted">{info.reachable}/{info.total} reachable</span>}
        </div>
        {hosts.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-text-muted">
            <Activity size={36} className="mb-3 opacity-30" />
            <p>Add servers and press Start to stream a live comparison.</p>
          </div>
        ) : (
          <ReactECharts style={{ height: 320 }} opts={{ renderer: "canvas" }} option={option} notMerge={false} />
        )}
        <p className="text-[11px] text-text-muted/60 mt-2">
          CPU/Memory/Load via live SSH (default DB creds) · Power/Temperature via BMC Redfish · N/A = host unreachable.
        </p>
      </div>
    </div>
  );
}
