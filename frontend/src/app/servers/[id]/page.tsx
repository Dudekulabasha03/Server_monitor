"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { api } from "@/lib/api";
import { getStatusConfig, formatTemp, formatWatts, formatPct, healthScoreColor } from "@/lib/utils";
import { useParams } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Cpu, Thermometer, Zap, HardDrive, MemoryStick, Activity, RefreshCw } from "lucide-react";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { COLORS } from "@/lib/echarts-theme";

export default function ServerDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const { data, isLoading } = useQuery({
    queryKey: ["server-detail", id],
    queryFn: () => api.get(`/api/v1/servers/${id}`).then((r) => r.data),
    refetchInterval: 15_000,
  });
  const { data: healthHist } = useQuery({
    queryKey: ["health-hist", id],
    queryFn: () => fleetApi.getHealthHistory(id, 48),
    refetchInterval: 60_000,
  });
  const { data: serverRecos } = useQuery({
    queryKey: ["server-recos", id],
    queryFn: () => fleetApi.getServerRecommendations(id),
    refetchInterval: 60_000,
  });
  const { data: ts } = useQuery({
    queryKey: ["server-ts", id],
    queryFn: () => fleetApi.tsServer(id, "cpu_temp_max,power_consumed_watts,cpu_usage_avg,memory_usage_pct", "24h"),
    refetchInterval: 10_000,
  });

  const qc = useQueryClient();
  const [refreshNote, setRefreshNote] = useState<string | null>(null);
  const fullMut = useMutation({
    mutationFn: () => fleetApi.fullRefresh(id),
    onSuccess: () => { setRefreshNote("✓ Refreshed (BMC + PRISM + OS)"); qc.invalidateQueries({ queryKey: ["server-detail", id] }); setTimeout(() => setRefreshNote(null), 3500); },
    onError: () => { setRefreshNote("✗ Refresh failed"); setTimeout(() => setRefreshNote(null), 3500); },
  });
  const prismMut = useMutation({
    mutationFn: () => fleetApi.prismRefresh(id),
    onSuccess: () => { setRefreshNote("✓ PRISM refreshed"); qc.invalidateQueries({ queryKey: ["server-detail", id] }); setTimeout(() => setRefreshNote(null), 3500); },
    onError: () => { setRefreshNote("✗ PRISM failed"); setTimeout(() => setRefreshNote(null), 3500); },
  });

  if (isLoading || !data) {
    return <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" /></div>;
  }

  const srv = data.server;
  const snap = data.snapshot;
  const health = data.health_score;
  const comp = data.components ?? {};
  const sel = data.sel_events ?? [];
  const cfg = getStatusConfig(srv.status);
  const histData = (healthHist ?? []).map((h: any) => ({ t: new Date(h.timestamp).toLocaleTimeString("en-US", { hour: "2-digit" }), score: h.score }));

  return (
    <div className="space-y-6 animate-fade-in">
      <Link href="/operations" className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text-primary"><ArrowLeft size={14} /> Back to Operations</Link>

      {/* Header */}
      <div className="card flex items-center justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold">{srv.hostname}</h1>
            <span className={`px-2 py-0.5 rounded-full text-xs border ${cfg.color} ${cfg.bg} ${cfg.border}`}>{cfg.label}</span>
          </div>
          <p className="text-sm text-text-muted">{srv.fqdn ?? srv.bmc_ip} · {srv.family ? `${srv.family} · ` : ""}{srv.model ?? srv.vendor} · {srv.datacenter} Rack {srv.rack}/U{srv.rack_unit}</p>
          <p className="text-xs text-text-muted mt-0.5">
            {srv.cpu_count ? `${srv.cpu_count} ${srv.cpu_count === 1 ? "Socket" : "Sockets"}` : ""}{srv.cpu_cores_total ? ` · ${srv.cpu_cores_total} cores` : ""}{srv.cpu_threads_total ? ` · ${srv.cpu_threads_total} threads` : ""}{srv.microcode ? ` · ucode ${srv.microcode}` : ""}{srv.team ? ` · ${srv.team}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Per-server refresh actions */}
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-2">
              <button onClick={() => fullMut.mutate()} disabled={fullMut.isPending}
                title="Full refresh: BMC (Redfish) + PRISM hardware + OS (SSH)"
                className="flex items-center gap-1 bg-green-600/90 hover:bg-green-500 text-white rounded px-2.5 py-1 text-xs disabled:opacity-50">
                <RefreshCw size={12} className={fullMut.isPending ? "animate-spin" : ""} /> Full Refresh
              </button>
              <button onClick={() => prismMut.mutate()} disabled={prismMut.isPending}
                title="PRISM only: hardware inventory + OS IP"
                className="flex items-center gap-1 border border-blue-500/40 hover:bg-blue-400/10 text-blue-400 rounded px-2.5 py-1 text-xs disabled:opacity-50">
                <RefreshCw size={12} className={prismMut.isPending ? "animate-spin" : ""} /> PRISM
              </button>
            </div>
            {refreshNote && <span className="text-[11px] text-text-muted">{refreshNote}</span>}
          </div>
          <div className="text-right">
            <p className="metric-label">Health Score</p>
            <p className={`text-4xl font-bold ${healthScoreColor(srv.health_score)}`}>{srv.health_score ?? "—"}</p>
          </div>
        </div>
      </div>

      {/* Live metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="card"><p className="metric-label flex items-center gap-1"><Thermometer size={12} /> CPU Temp</p><p className="metric-value">{formatTemp(snap?.cpu_temp_max)}</p></div>
        <div className="card"><p className="metric-label flex items-center gap-1"><Cpu size={12} /> CPU Usage</p><p className="metric-value">{formatPct(snap?.cpu_usage_avg)}</p></div>
        <div className="card"><p className="metric-label flex items-center gap-1"><MemoryStick size={12} /> Memory</p><p className="metric-value">{formatPct(snap?.memory_usage_pct)}</p></div>
        <div className="card"><p className="metric-label flex items-center gap-1"><Zap size={12} /> Power</p><p className="metric-value">{formatWatts(snap?.power_consumed_watts)}</p></div>
        <div className="card"><p className="metric-label flex items-center gap-1"><HardDrive size={12} /> Disk</p><p className="metric-value">{formatPct(snap?.disk_usage_max_pct)}</p></div>
      </div>

      {/* Health trend + breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-text-secondary mb-2">CPU Temperature (24h)</h3>
          <TimeSeriesChart series={ts?.series?.cpu_temp_max ?? []} name="CPU Temp" unit="°C" color={COLORS.warning} warn={75} crit={85} max={100} height={180} zoom={false} />
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-text-secondary mb-4">Health Breakdown</h3>
          {health ? (
            <div className="space-y-2">
              {[["Hardware", health.hardware_score], ["Thermal", health.thermal_score], ["Power", health.power_score], ["Storage", health.storage_score], ["Network", health.network_score], ["Utilization", health.utilization_score]].map(([label, val]: any) => (
                <div key={label} className="flex items-center gap-3 text-xs">
                  <span className="w-20 text-text-muted">{label}</span>
                  <div className="flex-1 bg-surface-2 rounded-full h-2"><div className="h-2 rounded-full" style={{ width: `${val ?? 0}%`, background: val >= 90 ? "#22c55e" : val >= 70 ? "#f59e0b" : "#ef4444" }} /></div>
                  <span className="w-8 text-right">{val ?? "—"}</span>
                </div>
              ))}
              {(health.deductions ?? []).length > 0 && (
                <div className="mt-3 pt-3 border-t border-surface-2 space-y-1">
                  {health.deductions.map((d: any, i: number) => (
                    <p key={i} className="text-xs text-text-muted">• {d.reason} <span className="text-red-400">({d.points})</span></p>
                  ))}
                </div>
              )}
            </div>
          ) : <p className="text-sm text-text-muted">No health data yet</p>}
        </div>
      </div>

      {/* Per-server metric trends */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-text-secondary mb-2">Power Draw (24h)</h3>
          <TimeSeriesChart series={ts?.series?.power_consumed_watts ?? []} name="Power" unit="W" color={COLORS.info} height={180} zoom={false} />
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-text-secondary mb-2">CPU & Memory (24h)</h3>
          {(ts?.series?.cpu_usage_avg ?? []).length === 0 ? (
            <p className="text-sm text-text-muted py-12 text-center">OS agent required for CPU/memory</p>
          ) : (
            <TimeSeriesChart series={ts?.series?.cpu_usage_avg ?? []} name="CPU %" unit="%" color={COLORS.purple} warn={80} crit={95} max={100} height={180} zoom={false} />
          )}
        </div>
      </div>

      {/* Recommendations for this server */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-secondary mb-3">Recommendations</h3>
        <div className="space-y-2">
          {(serverRecos?.recommendations ?? []).map((r: any) => (
            <div key={r.id} className={`flex items-start gap-3 rounded-lg border p-3 ${r.severity === "critical" ? "border-red-400/30 bg-red-400/10" : r.severity === "warning" ? "border-yellow-400/30 bg-yellow-400/10" : "border-blue-400/30 bg-blue-400/10"}`}>
              <div className="flex-1">
                <p className="text-sm font-semibold text-text-primary">{r.title.replace(`: ${srv.hostname}`, "")}</p>
                <p className="text-xs text-text-secondary mt-0.5">{r.body}</p>
                {r.rationale && <p className="text-xs text-text-muted mt-1">↳ {r.rationale}</p>}
              </div>
              <span className="text-xs uppercase text-text-muted">{r.category}</span>
            </div>
          ))}
          {(serverRecos?.recommendations ?? []).length === 0 && <p className="text-sm text-green-400">✓ No recommendations — operating normally.</p>}
        </div>
      </div>

      {/* Processors (per-CPU microcode) */}
      <div className="card p-0 overflow-x-auto">
        <h3 className="text-sm font-semibold text-text-secondary p-4 pb-2 flex items-center gap-2"><Cpu size={14} /> Processors</h3>
        {(data.processors ?? []).length === 0 ? (
          <p className="px-4 pb-4 text-sm text-text-muted">No per-processor data (BMC didn&apos;t expose Processors detail, or not yet polled).</p>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
              <th className="px-4 py-2">Socket</th><th className="px-4 py-2">Model</th><th className="px-4 py-2">Cores</th><th className="px-4 py-2">Threads</th><th className="px-4 py-2">Microcode</th><th className="px-4 py-2">Health</th>
            </tr></thead>
            <tbody>
              {(data.processors ?? []).map((p: any, i: number) => (
                <tr key={i} className="border-b border-surface-2 hover:bg-surface-2/40">
                  <td className="px-4 py-2 font-mono">{p.id ?? `P${i}`}</td>
                  <td className="px-4 py-2 text-text-muted">{p.model ?? "—"}</td>
                  <td className="px-4 py-2">{p.cores ?? "—"}</td>
                  <td className="px-4 py-2">{p.threads ?? "—"}</td>
                  <td className="px-4 py-2 font-mono">{p.microcode ?? "—"}</td>
                  <td className="px-4 py-2">{p.health ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Components */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-text-secondary mb-3">Memory ({(comp.dimms ?? []).length} DIMMs)</h3>
          <div className="grid grid-cols-2 gap-1 max-h-48 overflow-y-auto text-xs">
            {(comp.dimms ?? []).map((d: any) => (
              <div key={d.id} className="flex justify-between bg-surface-2/40 rounded px-2 py-1">
                <span className="text-text-muted truncate">{d.slot_name}</span>
                <span>{d.capacity_gb}GB</span>
              </div>
            ))}
            {(comp.dimms ?? []).length === 0 && <p className="text-text-muted col-span-2">No DIMM data</p>}
          </div>
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-text-secondary mb-3 flex items-center gap-2"><Activity size={14} /> Recent Events (SEL)</h3>
          <div className="space-y-1 max-h-48 overflow-y-auto text-xs">
            {sel.length === 0 ? <p className="text-text-muted">No recent events</p> : sel.slice(0, 15).map((e: any, i: number) => (
              <div key={i} className="bg-surface-2/40 rounded px-2 py-1">
                <span className={e.severity === "Critical" ? "text-red-400" : e.severity === "Warning" ? "text-yellow-400" : "text-text-muted"}>{e.severity ?? "Info"}</span>
                <span className="ml-2">{e.message}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* BMC sensor alerts */}
      {(snap?.raw_sensors?.critical_sensors ?? []).length > 0 && (
        <div className="card border border-red-400/30">
          <h3 className="text-sm font-semibold text-text-secondary mb-3 flex items-center gap-2">
            <Thermometer size={14} /> BMC Sensor Alerts
            <span className={`px-2 py-0.5 rounded-full text-xs ${snap.sensor_health === "Critical" ? "bg-red-400/10 text-red-400" : "bg-yellow-400/10 text-yellow-400"}`}>{snap.sensor_health}</span>
          </h3>
          <table className="w-full text-xs">
            <thead><tr className="text-left text-text-muted uppercase border-b border-surface-2">
              <th className="py-1.5">Sensor</th><th className="py-1.5">Reading</th><th className="py-1.5">Warn</th><th className="py-1.5">Crit</th><th className="py-1.5">State</th>
            </tr></thead>
            <tbody>
              {snap.raw_sensors.critical_sensors.map((cs: any, i: number) => (
                <tr key={i} className="border-b border-surface-2">
                  <td className="py-1.5 font-mono">{cs.name}</td>
                  <td className="py-1.5">{cs.reading != null ? `${cs.reading}°C` : "—"}</td>
                  <td className="py-1.5 text-text-muted">{cs.warn ?? "—"}</td>
                  <td className="py-1.5 text-text-muted">{cs.crit ?? "—"}</td>
                  <td className={`py-1.5 font-semibold ${cs.state === "Critical" ? "text-red-400" : "text-yellow-400"}`}>{cs.state}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
