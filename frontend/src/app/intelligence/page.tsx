"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { healthScoreColor, formatWatts } from "@/lib/utils";
import Link from "next/link";
import { Brain, AlertTriangle, Zap, Lightbulb, X, Download } from "lucide-react";

function riskColor(level: string) {
  return level === "high" ? "text-red-400" : level === "medium" ? "text-yellow-400" : "text-green-400";
}
function riskBar(v: number) {
  return v >= 70 ? "#ef4444" : v >= 40 ? "#f59e0b" : "#22c55e";
}
const sevColor: Record<string, string> = {
  critical: "border-red-400/30 bg-red-400/10 text-red-400",
  warning: "border-yellow-400/30 bg-yellow-400/10 text-yellow-400",
  info: "border-blue-400/30 bg-blue-400/10 text-blue-400",
};

export default function IntelligencePage() {
  const qc = useQueryClient();
  const { data: summary } = useQuery({ queryKey: ["intel-summary"], queryFn: fleetApi.getFleetIntelligence, refetchInterval: 30_000 });
  const { data: risk } = useQuery({ queryKey: ["risk"], queryFn: fleetApi.getRisk, refetchInterval: 30_000 });
  const { data: recos } = useQuery({ queryKey: ["recos"], queryFn: fleetApi.getRecommendations, refetchInterval: 30_000 });
  const { data: recosByServer } = useQuery({ queryKey: ["recos-by-server"], queryFn: fleetApi.getRecommendationsByServer, refetchInterval: 30_000 });
  const { data: opt } = useQuery({ queryKey: ["opt"], queryFn: fleetApi.getOptimization, refetchInterval: 30_000 });

  const dismiss = useMutation({
    mutationFn: (id: string) => fleetApi.dismissReco(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recos"] }),
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><Brain size={20} className="text-blue-400" /> Health Intelligence</h1>
          <p className="text-sm text-text-muted">Predictive maintenance, risk ranking & recommendations</p>
        </div>
        <a href={fleetApi.reportUrl("exec", "pdf")} target="_blank" className="flex items-center gap-2 bg-surface-2 hover:bg-surface border border-border rounded-lg px-3 py-1.5 text-sm">
          <Download size={14} /> Executive Report (PDF)
        </a>
      </div>

      {/* Top summary */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="card"><p className="metric-label">Total Servers</p><p className="metric-value">{summary?.total_servers ?? "—"}</p></div>
        <div className="card"><p className="metric-label flex items-center gap-1"><AlertTriangle size={12} /> High Risk</p><p className={`metric-value ${summary?.high_risk_servers ? "text-red-400" : "text-green-400"}`}>{summary?.high_risk_servers ?? "—"}</p></div>
        <div className="card"><p className="metric-label flex items-center gap-1"><Lightbulb size={12} /> Recommendations</p><p className="metric-value text-yellow-400">{summary?.open_recommendations ?? "—"}</p></div>
        <div className="card"><p className="metric-label flex items-center gap-1"><Zap size={12} /> Monthly Cost</p><p className="metric-value">${summary?.monthly_cost_est?.toLocaleString() ?? "—"}</p></div>
        <div className="card"><p className="metric-label flex items-center gap-1"><Zap size={12} /> Total Power</p><p className="metric-value text-yellow-400">{summary?.total_power_watts != null ? `${(summary.total_power_watts/1000).toFixed(1)} kW` : "—"}</p></div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Top Risk Servers */}
        <div className="card p-0 overflow-hidden">
          <h3 className="text-sm font-semibold text-text-secondary p-4 pb-2 flex items-center gap-2"><AlertTriangle size={15} /> Top Risk Servers</h3>
          <table className="w-full text-sm">
            <thead><tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
              <th className="px-4 py-2">#</th><th className="px-4 py-2">Server</th><th className="px-4 py-2">Health</th><th className="px-4 py-2">Risk</th><th className="px-4 py-2">Level</th>
            </tr></thead>
            <tbody>
              {(risk?.top_risk ?? []).map((r: any, i: number) => (
                <tr key={r.id} className="border-b border-surface-2 hover:bg-surface-2/40">
                  <td className="px-4 py-2 text-text-muted">{i + 1}</td>
                  <td className="px-4 py-2"><Link href={`/servers/${r.id}`} className="font-mono hover:text-blue-400">{r.hostname}</Link></td>
                  <td className={`px-4 py-2 font-bold ${healthScoreColor(r.health_score)}`}>{r.health_score ?? "—"}</td>
                  <td className="px-4 py-2"><div className="flex items-center gap-2"><div className="w-16 bg-surface-2 rounded-full h-1.5"><div className="h-1.5 rounded-full" style={{ width: `${r.overall_risk}%`, background: riskBar(r.overall_risk) }} /></div><span className="font-bold" style={{ color: riskBar(r.overall_risk) }}>{r.overall_risk}</span></div></td>
                  <td className={`px-4 py-2 font-semibold uppercase text-xs ${riskColor(r.risk_level)}`}>{r.risk_level}</td>
                </tr>
              ))}
              {(risk?.top_risk ?? []).length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-text-muted">No risk data yet</td></tr>}
            </tbody>
          </table>
        </div>

        {/* Utilization classification */}
        <div className="card">
          <h3 className="text-sm font-semibold text-text-secondary mb-4">Health Utilization</h3>
          <div className="grid grid-cols-2 gap-3">
            {opt && ["active", "overutilized", "underutilized", "idle"].map((cat) => {
              const c = opt.categories?.[cat];
              const colors: Record<string, string> = { active: "text-green-400", overutilized: "text-red-400", underutilized: "text-yellow-400", idle: "text-gray-400" };
              return (
                <div key={cat} className="bg-surface-2/40 rounded-lg p-3">
                  <p className={`text-2xl font-bold ${colors[cat]}`}>{c?.count ?? 0}</p>
                  <p className="text-xs text-text-muted capitalize">{cat}</p>
                </div>
              );
            })}
          </div>
          {opt?.reclaimable_watts > 0 && (
            <p className="text-xs text-text-muted mt-4">♻ Reclaimable power from idle/underutilized: <span className="text-yellow-400 font-bold">{formatWatts(opt.reclaimable_watts)}</span></p>
          )}
        </div>
      </div>

      {/* Recommendations feed */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-secondary mb-4 flex items-center gap-2"><Lightbulb size={15} /> Recommendations ({recos?.total ?? 0})</h3>
        <div className="space-y-2">
          {(recos?.recommendations ?? []).map((r: any) => (
            <div key={r.id} className={`flex items-start gap-3 rounded-lg border p-3 ${sevColor[r.severity] ?? sevColor.info}`}>
              <div className="flex-1">
                <p className="text-sm font-semibold text-text-primary">{r.title}</p>
                <p className="text-xs text-text-secondary mt-0.5">{r.body}</p>
                {r.rationale && <p className="text-xs text-text-muted mt-1">↳ {r.rationale}</p>}
                {(r.steps ?? []).length > 0 && (
                  <div className="mt-2 pl-3 border-l-2 border-surface-2">
                    <p className="text-xs font-semibold text-text-secondary mb-1">Steps to resolve:</p>
                    <ol className="list-decimal list-inside space-y-0.5">
                      {r.steps.map((step: string, i: number) => (
                        <li key={i} className="text-xs text-text-muted">{step}</li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
              <span className="text-xs uppercase">{r.category}</span>
              <button onClick={() => dismiss.mutate(r.id)} className="text-text-muted hover:text-text-primary"><X size={14} /></button>
            </div>
          ))}
          {(recos?.recommendations ?? []).length === 0 && <p className="text-sm text-green-400">✓ No open recommendations — fleet is optimized.</p>}
        </div>
      </div>

      {/* Per-server recommendations */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-secondary mb-4">Recommendations by Server</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {(recosByServer?.servers ?? []).map((srv: any) => (
            <div key={srv.server_id} className="bg-surface-2/30 rounded-lg p-3 border border-surface-2">
              <Link href={`/servers/${srv.server_id}`} className="font-mono text-sm hover:text-blue-400">{srv.hostname}</Link>
              <div className="mt-2 space-y-1.5">
                {srv.items.map((it: any) => (
                  <div key={it.id} className="text-xs">
                    <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle ${it.severity === "critical" ? "bg-red-400" : it.severity === "warning" ? "bg-yellow-400" : "bg-blue-400"}`} />
                    <span className="text-text-secondary">{it.title.replace(`: ${srv.hostname}`, "")}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {(recosByServer?.servers ?? []).length === 0 && <p className="text-sm text-text-muted col-span-full">No per-server recommendations yet — run the risk engine.</p>}
        </div>
      </div>
    </div>
  );
}
