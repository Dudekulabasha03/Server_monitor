"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fleetApi } from "@/lib/api";
import { formatTemp } from "@/lib/utils";
import { Thermometer, Wind, AlertTriangle } from "lucide-react";

function tempColor(t: number | null): string {
  if (t === null || t === undefined) return "text-slate-400";
  if (t >= 85) return "text-red-400";
  if (t >= 75) return "text-yellow-400";
  return "text-green-400";
}
function tempBg(t: number | null): string {
  if (t === null || t === undefined) return "bg-slate-700";
  if (t >= 85) return "bg-red-500";
  if (t >= 75) return "bg-yellow-500";
  if (t >= 60) return "bg-orange-400";
  return "bg-green-500";
}

export default function ThermalPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["thermal"],
    queryFn: fleetApi.getThermal,
    refetchInterval: 15_000,
  });
  const [region, setRegion] = useState("");
  const [family, setFamily] = useState("");

  if (isLoading || !data) {
    return <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" /></div>;
  }

  const allServers = data.servers ?? [];
  const servers = allServers.filter((srv: any) =>
    (!region || srv.datacenter === region) &&
    (!family || (srv.model || "").toLowerCase().includes(family.toLowerCase()))
  );
  // recompute summary on filtered set
  const ftemps = servers.map((r: any) => r.cpu_temp_max).filter((t: any) => t != null);
  const finlets = servers.map((r: any) => r.inlet_temp).filter((t: any) => t != null);
  const s = {
    avg_cpu_temp: ftemps.length ? Math.round(ftemps.reduce((a: number, b: number) => a + b, 0) / ftemps.length * 10) / 10 : null,
    max_cpu_temp: ftemps.length ? Math.max(...ftemps) : null,
    avg_inlet_temp: finlets.length ? Math.round(finlets.reduce((a: number, b: number) => a + b, 0) / finlets.length * 10) / 10 : null,
    hot_count: ftemps.filter((t: number) => t >= 75 && t < 85).length,
    critical_count: ftemps.filter((t: number) => t >= 85).length,
  };
  const bands = {
    cool: ftemps.filter((t: number) => t < 60).length,
    warm: ftemps.filter((t: number) => t >= 60 && t < 75).length,
    hot: ftemps.filter((t: number) => t >= 75 && t < 85).length,
    crit: ftemps.filter((t: number) => t >= 85).length,
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold">Thermal Monitoring</h1>
        <p className="text-sm text-text-muted">CPU, inlet & outlet temperatures · {servers.length} servers</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <select value={region} onChange={(e) => setRegion(e.target.value)} className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
          <option value="">All Regions</option><option>Santa Clara</option><option>Plano</option><option>Dallas</option><option>Bangalore</option>
        </select>
        <select value={family} onChange={(e) => setFamily(e.target.value)} className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
          <option value="">All Families</option><option>Milan</option><option>Genoa</option><option value="Turin Classic">Turin Classic</option><option value="Turin Dense">Turin Dense</option><option>Turin</option>
        </select>
        <div className="flex gap-2 text-xs ml-auto">
          <span className="px-2 py-1 rounded bg-green-400/10 text-green-400">&lt;60°C: {bands.cool}</span>
          <span className="px-2 py-1 rounded bg-orange-400/10 text-orange-400">60-75: {bands.warm}</span>
          <span className="px-2 py-1 rounded bg-yellow-400/10 text-yellow-400">75-85: {bands.hot}</span>
          <span className="px-2 py-1 rounded bg-red-400/10 text-red-400">&gt;85: {bands.crit}</span>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card"><p className="metric-label">Avg CPU Temp</p><p className={`metric-value ${tempColor(s.avg_cpu_temp)}`}>{formatTemp(s.avg_cpu_temp)}</p></div>
        <div className="card"><p className="metric-label">Max CPU Temp</p><p className={`metric-value ${tempColor(s.max_cpu_temp)}`}>{formatTemp(s.max_cpu_temp)}</p></div>
        <div className="card"><p className="metric-label">Avg Inlet Temp</p><p className={`metric-value ${tempColor(s.avg_inlet_temp)}`}>{formatTemp(s.avg_inlet_temp)}</p></div>
        <div className="card"><p className="metric-label">Hot / Critical</p><p className="metric-value"><span className="text-yellow-400">{s.hot_count}</span> <span className="text-text-muted">/</span> <span className="text-red-400">{s.critical_count}</span></p></div>
      </div>

      {/* Heatmap grid */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-secondary mb-4 flex items-center gap-2"><Thermometer size={15} /> Health Thermal Heatmap (CPU max)</h3>
        <div className="grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-10 gap-2">
          {servers.map((srv: any) => (
            <div key={srv.id} className="group relative">
              <div className={`${tempBg(srv.cpu_temp_max)} rounded-lg aspect-square flex flex-col items-center justify-center text-white text-xs font-bold cursor-pointer hover:ring-2 ring-white/50`}>
                <span>{srv.cpu_temp_max ? Math.round(srv.cpu_temp_max) : "—"}</span>
              </div>
              <div className="absolute z-10 bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block bg-surface-2 border border-border rounded px-2 py-1 text-xs whitespace-nowrap">
                {srv.hostname}: {formatTemp(srv.cpu_temp_max)}
              </div>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-4 mt-4 text-xs text-text-muted">
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-500" /> &lt;60°C</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-orange-400" /> 60-75°C</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-yellow-500" /> 75-85°C</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-500" /> &gt;85°C</span>
        </div>
      </div>

      {/* Hottest table */}
      <div className="card p-0 overflow-x-auto">
        <h3 className="text-sm font-semibold text-text-secondary p-4 pb-2 flex items-center gap-2"><AlertTriangle size={15} /> Hottest Servers</h3>
        <table className="w-full">
          <thead><tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
            <th className="px-4 py-2">Server</th><th className="px-4 py-2">Rack</th><th className="px-4 py-2">CPU Max</th><th className="px-4 py-2">CPU Avg</th><th className="px-4 py-2">Inlet</th><th className="px-4 py-2">Outlet</th><th className="px-4 py-2">Fans</th>
          </tr></thead>
          <tbody>
            {(data.hottest ?? []).map((r: any) => (
              <tr key={r.id} className="border-b border-surface-2 hover:bg-surface-2/40">
                <td className="px-4 py-2 text-sm font-mono">{r.hostname}</td>
                <td className="px-4 py-2 text-sm text-text-muted">{r.rack ?? "—"}</td>
                <td className={`px-4 py-2 text-sm font-bold ${tempColor(r.cpu_temp_max)}`}>{formatTemp(r.cpu_temp_max)}</td>
                <td className="px-4 py-2 text-sm">{formatTemp(r.cpu_temp_avg)}</td>
                <td className="px-4 py-2 text-sm">{formatTemp(r.inlet_temp)}</td>
                <td className="px-4 py-2 text-sm">{formatTemp(r.outlet_temp)}</td>
                <td className="px-4 py-2 text-sm">{r.fan_failed_count > 0 ? <span className="text-red-400">{r.fan_failed_count} failed</span> : <span className="text-green-400">{r.fan_count} OK</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
