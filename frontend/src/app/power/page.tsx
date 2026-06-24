"use client";
import { useQuery } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { formatWatts } from "@/lib/utils";
import { Zap, DollarSign, Gauge, TrendingUp } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useState } from "react";

export default function PowerPage() {
  const [rate, setRate] = useState(0.12);
  const { data, isLoading } = useQuery({
    queryKey: ["power", rate],
    queryFn: () => fleetApi.getPower(rate),
    refetchInterval: 15_000,
  });
  const { data: trend } = useQuery({
    queryKey: ["power-trend"],
    queryFn: () => fleetApi.getPowerTrend(24),
    refetchInterval: 60_000,
  });

  if (isLoading || !data) {
    return <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" /></div>;
  }

  const s = data.summary;
  const chartData = (trend ?? []).map((p: any) => ({ time: new Date(p.timestamp).toLocaleTimeString("en-US", { hour: "2-digit" }), watts: p.watts }));

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Power Monitoring</h1>
          <p className="text-sm text-text-muted">Consumption, capacity & cost across the fleet</p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-text-muted">$/kWh:</span>
          <input type="number" step="0.01" value={rate} onChange={(e) => setRate(parseFloat(e.target.value) || 0)}
            className="w-20 bg-surface border border-surface-2 rounded px-2 py-1 text-sm" />
        </div>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card flex items-center gap-3"><div className="bg-yellow-400/10 p-3 rounded-xl"><Zap size={20} className="text-yellow-400" /></div><div><p className="metric-label">Current Draw</p><p className="metric-value">{formatWatts(s.total_watts)}</p></div></div>
        <div className="card flex items-center gap-3"><div className="bg-blue-400/10 p-3 rounded-xl"><Gauge size={20} className="text-blue-400" /></div><div><p className="metric-label">Capacity</p><p className="metric-value">{formatWatts(s.total_capacity_watts)}</p></div></div>
        <div className="card flex items-center gap-3"><div className="bg-green-400/10 p-3 rounded-xl"><TrendingUp size={20} className="text-green-400" /></div><div><p className="metric-label">Est. Monthly</p><p className="metric-value">{s.monthly_kwh?.toLocaleString()} kWh</p></div></div>
        <div className="card flex items-center gap-3"><div className="bg-emerald-400/10 p-3 rounded-xl"><DollarSign size={20} className="text-emerald-400" /></div><div><p className="metric-label">Monthly Cost (PUE {s.pue})</p><p className="metric-value">${s.monthly_cost?.toLocaleString()}</p></div></div>
      </div>

      {/* Power summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card flex items-center gap-3"><div className="bg-blue-400/10 p-3 rounded-xl"><Gauge size={20} className="text-blue-400" /></div><div><p className="metric-label">Monthly Energy</p><p className="metric-value">{(s.monthly_kwh ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} kWh</p></div></div>
        <div className="card flex items-center gap-3"><div className="bg-blue-400/10 p-3 rounded-xl"><Gauge size={20} className="text-blue-400" /></div><div><p className="metric-label">Power Headroom</p><p className="metric-value">{s.fleet_headroom_pct !== null ? `${s.fleet_headroom_pct}%` : "—"}</p></div></div>
        <div className="card flex items-center gap-3"><div className="bg-yellow-400/10 p-3 rounded-xl"><TrendingUp size={20} className="text-yellow-400" /></div><div><p className="metric-label">Annual Cost Est.</p><p className="metric-value">${((s.monthly_cost ?? 0) * 12).toLocaleString()}</p></div></div>
      </div>

      {/* Trend */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-secondary mb-4">Health Power Trend (24h)</h3>
        {chartData.length === 0 ? (
          <p className="text-sm text-text-muted py-10 text-center">Accumulating power history…</p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData}>
              <defs><linearGradient id="pw" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f59e0b" stopOpacity={0.4} /><stop offset="100%" stopColor="#f59e0b" stopOpacity={0} /></linearGradient></defs>
              <XAxis dataKey="time" stroke="#64748b" fontSize={11} /><YAxis stroke="#64748b" fontSize={11} />
              <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #475569", borderRadius: 8 }} />
              <Area type="monotone" dataKey="watts" stroke="#f59e0b" fill="url(#pw)" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Per-server */}
      <div className="card p-0 overflow-x-auto">
        <h3 className="text-sm font-semibold text-text-secondary p-4 pb-2">Per-Server Power</h3>
        <table className="w-full">
          <thead><tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
            <th className="px-4 py-2">Server</th><th className="px-4 py-2">State</th><th className="px-4 py-2">Draw</th><th className="px-4 py-2">Capacity</th><th className="px-4 py-2">Headroom</th><th className="px-4 py-2">PSUs</th>
          </tr></thead>
          <tbody>
            {(data.servers ?? []).map((r: any) => (
              <tr key={r.id} className="border-b border-surface-2 hover:bg-surface-2/40">
                <td className="px-4 py-2 text-sm font-mono">{r.hostname}</td>
                <td className="px-4 py-2 text-sm">{r.power_state === "On" ? <span className="text-green-400">● On</span> : <span className="text-gray-400">○ {r.power_state ?? "—"}</span>}</td>
                <td className="px-4 py-2 text-sm font-bold text-yellow-400">{formatWatts(r.power_consumed_watts)}</td>
                <td className="px-4 py-2 text-sm">{formatWatts(r.power_capacity_watts)}</td>
                <td className="px-4 py-2 text-sm">{r.headroom_pct !== null ? `${r.headroom_pct}%` : "—"}</td>
                <td className="px-4 py-2 text-sm">{r.psu_failed_count > 0 ? <span className="text-red-400">{r.psu_failed_count} failed</span> : r.psu_count ? <span className="text-green-400">{r.psu_count} OK</span> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
