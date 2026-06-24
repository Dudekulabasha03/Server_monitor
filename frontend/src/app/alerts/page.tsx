"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fleetApi, Alert } from "@/lib/api";
import { useState, Fragment } from "react";
import { formatDistanceToNow } from "date-fns";
import { CheckCircle, XCircle, AlertTriangle, Bell, Search } from "lucide-react";
import { ExportButton } from "@/components/ExportButton";
import { api } from "@/lib/api";

const SEVERITY_CONFIG = {
  critical:  { color: "text-red-400",    bg: "bg-red-400/10",    border: "border-red-400/30",    icon: "🔴" },
  warning:   { color: "text-yellow-400", bg: "bg-yellow-400/10", border: "border-yellow-400/30", icon: "🟡" },
  emergency: { color: "text-red-300",    bg: "bg-red-300/10",    border: "border-red-300/30",    icon: "🚨" },
  info:      { color: "text-blue-400",   bg: "bg-blue-400/10",   border: "border-blue-400/30",   icon: "🔵" },
};

function AlertRow({ alert, onAck, onResolve, onRca }: { alert: Alert; onAck: () => void; onResolve: () => void; onRca: () => void }) {
  const cfg = SEVERITY_CONFIG[alert.severity] ?? SEVERITY_CONFIG.info;

  return (
    <tr className="border-b border-surface-2 hover:bg-surface-2/50 transition-colors">
      <td className="py-3 px-4">
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.color} ${cfg.bg} ${cfg.border}`}>
          {cfg.icon} {alert.severity}
        </span>
      </td>
      <td className="py-3 px-4">
        <p className="text-sm font-medium text-text-primary">{alert.title}</p>
        <p className="text-xs text-text-muted mt-0.5 max-w-md">{alert.message}</p>
        {alert.runbook_url && (
          /^https?:\/\//i.test(alert.runbook_url) ? (
            <a href={alert.runbook_url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-400 hover:underline mt-1 inline-flex items-center gap-1">
              📖 Runbook
            </a>
          ) : (
            <p className="text-xs text-blue-300/80 mt-1 max-w-md">
              <span className="font-semibold">Remediation:</span> {alert.runbook_url}
            </p>
          )
        )}
      </td>
      <td className="py-3 px-4">
        <span className="text-xs px-2 py-0.5 rounded bg-surface-2 text-text-secondary">{alert.category}</span>
      </td>
      <td className="py-3 px-4 text-xs text-text-secondary">
        {alert.metric_name && (
          <span>
            {alert.metric_name}:{" "}
            <span className="font-mono text-text-primary">
              {alert.metric_value?.toFixed(1) ?? "—"}
            </span>
            {alert.threshold_value && <span className="text-text-muted"> / {alert.threshold_value}</span>}
          </span>
        )}
      </td>
      <td className="py-3 px-4 text-xs text-text-muted">
        {formatDistanceToNow(new Date(alert.fired_at), { addSuffix: true })}
      </td>
      <td className="py-3 px-4">
        <span className={`text-xs px-2 py-0.5 rounded-full border ${
          alert.state === "firing" ? "bg-red-400/10 border-red-400/30 text-red-400" :
          alert.state === "acknowledged" ? "bg-yellow-400/10 border-yellow-400/30 text-yellow-400" :
          "bg-green-400/10 border-green-400/30 text-green-400"
        }`}>
          {alert.state}
        </span>
      </td>
      <td className="py-3 px-4">
        <div className="flex gap-2">
          <button onClick={onRca} className="p-1 hover:bg-blue-400/10 rounded text-blue-400 transition-colors" title="Root Cause Analysis">
            <Search size={14} />
          </button>
          {alert.state === "firing" && (
            <button
              onClick={onAck}
              className="p-1 hover:bg-yellow-400/10 rounded text-yellow-400 transition-colors"
              title="Acknowledge"
            >
              <CheckCircle size={14} />
            </button>
          )}
          {alert.state !== "resolved" && (
            <button
              onClick={onResolve}
              className="p-1 hover:bg-green-400/10 rounded text-green-400 transition-colors"
              title="Resolve"
            >
              <XCircle size={14} />
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

function RcaPanel({ rca }: { rca: any }) {
  if (!rca) return null;
  return (
    <tr className="bg-surface-2/30">
      <td colSpan={7} className="px-6 py-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div>
            <p className="font-semibold text-blue-400 mb-1">Possible Causes</p>
            <ul className="space-y-0.5 text-text-secondary">{rca.possible_causes?.map((c: string, i: number) => <li key={i}>• {c}</li>)}</ul>
          </div>
          <div>
            <p className="font-semibold text-yellow-400 mb-1">Impact</p>
            <ul className="space-y-0.5 text-text-secondary">{rca.impact?.map((c: string, i: number) => <li key={i}>• {c}</li>)}</ul>
          </div>
          <div>
            <p className="font-semibold text-green-400 mb-1">Recommended Actions</p>
            <ul className="space-y-0.5 text-text-secondary">{rca.recommended_actions?.map((c: string, i: number) => <li key={i}>• {c}</li>)}</ul>
          </div>
        </div>
        {(rca.correlated_signals ?? []).length > 0 && (
          <div className="mt-3 pt-3 border-t border-surface-2">
            {rca.correlated_signals.map((s: string, i: number) => <p key={i} className="text-xs text-orange-400">{s}</p>)}
          </div>
        )}
      </td>
    </tr>
  );
}

export default function AlertsPage() {
  const [stateFilter, setStateFilter] = useState("firing");
  const [severityFilter, setSeverityFilter] = useState("");
  const [rcaFor, setRcaFor] = useState<string | null>(null);
  const [rcaData, setRcaData] = useState<any>(null);
  const queryClient = useQueryClient();

  const loadRca = async (id: string) => {
    if (rcaFor === id) { setRcaFor(null); setRcaData(null); return; }
    setRcaFor(id);
    try {
      const d = await api.get(`/api/v1/intelligence/rca/${id}`).then((r) => r.data);
      setRcaData(d);
    } catch { setRcaData(null); }
  };

  const { data: alerts, isLoading } = useQuery({
    queryKey: ["alerts", stateFilter, severityFilter],
    queryFn: () => fleetApi.getAlerts({
      state: stateFilter || undefined,
      severity: severityFilter || undefined,
      page_size: 200,
    }),
    refetchInterval: 15_000,
  });

  const { data: stats } = useQuery({
    queryKey: ["alert-stats"],
    queryFn: fleetApi.getAlertStats,
    refetchInterval: 15_000,
  });

  const ackMutation = useMutation({
    mutationFn: (id: string) => fleetApi.acknowledgeAlert(id, "dashboard-user"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const resolveMutation = useMutation({
    mutationFn: (id: string) => fleetApi.resolveAlert(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Alert Center</h1>
          <p className="text-sm text-text-muted">Monitor and manage all system alerts</p>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Critical", count: stats?.critical ?? 0, color: "text-red-400", bg: "bg-red-400/10", border: "border-red-400/30" },
          { label: "Warning", count: stats?.warning ?? 0, color: "text-yellow-400", bg: "bg-yellow-400/10", border: "border-yellow-400/30" },
          { label: "Info", count: stats?.info ?? 0, color: "text-blue-400", bg: "bg-blue-400/10", border: "border-blue-400/30" },
          { label: "Emergency", count: stats?.emergency ?? 0, color: "text-red-300", bg: "bg-red-300/10", border: "border-red-300/30" },
        ].map((s) => (
          <div key={s.label} className={`card border ${s.border} text-center`}>
            <p className={`text-3xl font-bold ${s.color}`}>{s.count}</p>
            <p className="text-xs text-text-muted mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <select
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value)}
          className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none"
        >
          <option value="">All States</option>
          <option value="firing">Firing</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
        </select>
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none"
        >
          <option value="">All Severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <ExportButton
          endpoint="/export/alerts"
          params={{ severity: severityFilter || undefined, state: stateFilter || undefined }}
          label="Export CSV"
          className="ml-auto"
        />
      </div>

      {/* Table */}
      <div className="card p-0 overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-surface-2 text-left">
              {["Severity", "Alert", "Category", "Metric", "Time", "State", "Actions"].map((h) => (
                <th key={h} className="px-4 py-3 text-xs font-semibold text-text-muted uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={7} className="py-10 text-center text-text-muted">Loading...</td></tr>
            ) : (alerts ?? []).length === 0 ? (
              <tr>
                <td colSpan={7} className="py-16 text-center">
                  <Bell size={32} className="mx-auto mb-3 text-text-muted opacity-30" />
                  <p className="text-text-muted text-sm">No alerts match your filters</p>
                </td>
              </tr>
            ) : (
              (alerts ?? []).map((alert) => (
                <Fragment key={alert.id}>
                  <AlertRow
                    alert={alert}
                    onAck={() => ackMutation.mutate(alert.id)}
                    onResolve={() => resolveMutation.mutate(alert.id)}
                    onRca={() => loadRca(alert.id)}
                  />
                  {rcaFor === alert.id && <RcaPanel rca={rcaData} />}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
