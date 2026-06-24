"use client";
import { useQuery } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { Activity, Cpu, AlertTriangle } from "lucide-react";

export default function AIOpsPage() {
  const { data: health } = useQuery({ queryKey: ["ai-health"], queryFn: fleetApi.aiHealth, refetchInterval: 30_000 });
  const { data, isLoading } = useQuery({ queryKey: ["ai-obs"], queryFn: fleetApi.aiObservability, refetchInterval: 15_000 });

  const agents = data?.agents ?? [];
  const traces = data?.recent_traces ?? [];

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2"><Cpu size={18} className="text-cyan-400" /> AI Ops — Observability</h1>
        <p className="text-sm text-text-muted">Every agent run is traced: thoughts, tool calls, latency, tokens, and hallucination flags.</p>
      </div>

      {/* Model health */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card"><p className="metric-label">Model</p><p className="metric-value text-base">{health?.model ?? "—"}</p></div>
        <div className="card"><p className="metric-label">Status</p><p className={`metric-value text-base ${health?.available ? "text-green-400" : "text-red-400"}`}>{health?.available ? "Reachable" : "Unavailable"}</p></div>
        <div className="card"><p className="metric-label">Total Trace Steps</p><p className="metric-value">{data?.total_traces ?? 0}</p></div>
        <div className="card"><p className="metric-label">Flagged Runs</p><p className={`metric-value ${(data?.flagged_runs ?? 0) > 0 ? "text-yellow-400" : "text-green-400"}`}>{data?.flagged_runs ?? 0}</p></div>
      </div>

      {/* Per-agent metrics */}
      <div className="card p-0 overflow-x-auto">
        <h3 className="text-sm font-semibold text-text-secondary p-4 pb-2 flex items-center gap-2"><Activity size={14} /> Per-Agent Metrics</h3>
        <table className="w-full text-sm">
          <thead><tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
            <th className="px-4 py-2">Agent</th><th className="px-4 py-2">Steps</th><th className="px-4 py-2">Avg Latency</th><th className="px-4 py-2">Tokens In</th><th className="px-4 py-2">Tokens Out</th>
          </tr></thead>
          <tbody>
            {agents.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-6 text-text-muted text-center">No agent activity yet — ask Helios something.</td></tr>
            ) : agents.map((a: any) => (
              <tr key={a.agent} className="border-b border-surface-2 hover:bg-surface-2/40">
                <td className="px-4 py-2"><span className="text-cyan-400">{a.agent}</span></td>
                <td className="px-4 py-2">{a.steps}</td>
                <td className="px-4 py-2">{a.avg_latency_ms ? `${a.avg_latency_ms} ms` : "—"}</td>
                <td className="px-4 py-2 text-text-muted">{a.tokens_in}</td>
                <td className="px-4 py-2 text-text-muted">{a.tokens_out}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Recent trace steps */}
      <div className="card p-0 overflow-x-auto">
        <h3 className="text-sm font-semibold text-text-secondary p-4 pb-2">Recent ReAct Steps</h3>
        {isLoading ? (
          <div className="flex justify-center py-10"><div className="animate-spin rounded-full h-7 w-7 border-b-2 border-cyan-400" /></div>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
              <th className="px-4 py-2">Agent</th><th className="px-4 py-2">Step</th><th className="px-4 py-2">Thought / Action</th><th className="px-4 py-2">Latency</th><th className="px-4 py-2">Flags</th>
            </tr></thead>
            <tbody>
              {traces.map((t: any, i: number) => (
                <tr key={i} className="border-b border-surface-2 hover:bg-surface-2/40 align-top">
                  <td className="px-4 py-2 text-cyan-400 whitespace-nowrap">{t.agent}</td>
                  <td className="px-4 py-2">{t.step}</td>
                  <td className="px-4 py-2 max-w-lg">
                    {t.action ? <span className="font-mono text-xs text-blue-300">→ {t.action.tool}({JSON.stringify(t.action.args)})</span>
                      : <span className="text-text-muted text-xs">{t.thought || "—"}</span>}
                  </td>
                  <td className="px-4 py-2 text-text-muted whitespace-nowrap">{t.latency_ms ? `${t.latency_ms} ms` : "—"}</td>
                  <td className="px-4 py-2">
                    {t.flags?.unbacked_claims?.length > 0 && <span className="text-yellow-400 flex items-center gap-1 text-xs"><AlertTriangle size={11} /> {t.flags.unbacked_claims.length}</span>}
                    {t.flags?.max_steps_hit && <span className="text-orange-400 text-xs">max-steps</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
