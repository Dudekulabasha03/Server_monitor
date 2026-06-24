"use client";
import { useQuery } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { formatPct } from "@/lib/utils";
import { Users, Power, Activity, Search } from "lucide-react";
import { ExportButton } from "@/components/ExportButton";
import { useMemo, useState } from "react";

const ACT_BADGE: Record<string, string> = {
  in_use: "text-green-400 bg-green-400/10",
  idle:   "text-gray-400 bg-gray-400/10",
  no_data:"text-amber-400 bg-amber-400/10",
};
const ACT_LABEL: Record<string, string> = { in_use: "In use", idle: "Idle", no_data: "OS unreachable" };

// BMC-named entries (iDRAC, iLO, SMC, XCC) never have OS SSH — exclude from unreachable count
const BMC_PREFIXES = ["idrac-", "ilo", "smc", "xcc-"];
const isBmcEntry = (hostname: string) =>
  BMC_PREFIXES.some((p) => hostname.toLowerCase().startsWith(p));

export default function UsersPage() {
  const { data: sessions, isLoading } = useQuery({ queryKey: ["sessions"], queryFn: fleetApi.getSessions, refetchInterval: 20_000 });
  const { data: activity } = useQuery({ queryKey: ["fleet-activity"], queryFn: fleetApi.getFleetActivity, refetchInterval: 30_000 });

  const [search, setSearch] = useState("");
  const [actFilter, setActFilter] = useState("");

  const servers = useMemo(() => {
    let list = (activity?.servers ?? []).filter((s: any) => !isBmcEntry(s.hostname));
    if (search) { const q = search.toLowerCase(); list = list.filter((s: any) => s.hostname.toLowerCase().includes(q) || (s.team || "").toLowerCase().includes(q)); }
    if (actFilter) list = list.filter((s: any) => s.activity === actFilter);
    return list;
  }, [activity, search, actFilter]);

  // Recompute counts excluding BMC-named entries
  const counts = useMemo(() => {
    const all = (activity?.servers ?? []).filter((s: any) => !isBmcEntry(s.hostname));
    return {
      in_use:  all.filter((s: any) => s.activity === "in_use").length,
      idle:    all.filter((s: any) => s.activity === "idle").length,
      no_data: all.filter((s: any) => s.activity === "no_data").length,
    };
  }, [activity]);

  if (isLoading) {
    return <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" /></div>;
  }

  const rows = sessions?.sessions ?? [];
  const c = counts;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">User Activity</h1>
          <p className="text-sm text-text-muted">Active sessions & fleet-wide server activity (OS agent)</p>
        </div>
        <ExportButton endpoint="/export/user-activity" label="Export CSV" />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card flex items-center gap-3"><div className="bg-blue-400/10 p-3 rounded-xl"><Users size={20} className="text-blue-400" /></div><div><p className="metric-label">Active Sessions</p><p className="metric-value">{sessions?.total ?? 0}</p></div></div>
        <div className="card flex items-center gap-3"><div className="bg-green-400/10 p-3 rounded-xl"><Activity size={20} className="text-green-400" /></div><div><p className="metric-label">In Use</p><p className="metric-value text-green-400">{c.in_use}</p></div></div>
        <div className="card flex items-center gap-3"><div className="bg-gray-400/10 p-3 rounded-xl"><Power size={20} className="text-gray-400" /></div><div><p className="metric-label">Idle</p><p className="metric-value text-gray-400">{c.idle}</p></div></div>
        <div className="card flex items-center gap-3"><div className="bg-amber-400/10 p-3 rounded-xl"><Power size={20} className="text-amber-400" /></div><div><p className="metric-label">OS Unreachable</p><p className="metric-value text-amber-400">{c.no_data}</p></div></div>
      </div>

      {/* Active SSH sessions (real logins) */}
      {rows.length === 0 ? (
        <div className="card flex flex-col items-center py-10 text-text-muted">
          <Users size={36} className="mb-3 opacity-30" />
          <p>No active SSH sessions right now</p>
          <p className="text-xs mt-1">Sessions appear for servers where the OS agent can SSH in.</p>
        </div>
      ) : (
        <div className="card p-0 overflow-x-auto">
          <h3 className="text-sm font-semibold text-text-secondary p-4 pb-2">Active Sessions ({rows.length})</h3>
          <table className="w-full">
            <thead><tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
              <th className="px-4 py-2">Server</th><th className="px-4 py-2">User</th><th className="px-4 py-2">Type</th><th className="px-4 py-2">Source</th><th className="px-4 py-2">Terminal</th><th className="px-4 py-2">Login</th>
            </tr></thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={r.id} className="border-b border-surface-2 hover:bg-surface-2/40">
                  <td className="px-4 py-2 text-sm font-mono">{r.hostname}</td>
                  <td className="px-4 py-2 text-sm font-semibold">{r.username}</td>
                  <td className="px-4 py-2 text-sm">{r.session_type ?? "—"}</td>
                  <td className="px-4 py-2 text-sm text-text-muted">{r.source_ip ?? "local"}</td>
                  <td className="px-4 py-2 text-sm text-text-muted">{r.terminal ?? "—"}</td>
                  <td className="px-4 py-2 text-sm text-text-muted">{r.login_at ? new Date(r.login_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Fleet-wide server activity — scales with the whole fleet */}
      <div className="card p-0 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 p-4 pb-3">
          <h3 className="text-sm font-semibold text-text-secondary">Server Activity ({servers.length})</h3>
          <div className="flex gap-2 items-center">
            <div className="relative w-56">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search host / team..."
                className="w-full bg-surface border border-surface-2 rounded-lg pl-8 pr-4 py-1.5 text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <select value={actFilter} onChange={(e) => setActFilter(e.target.value)} className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
              <option value="">All Activity</option>
              <option value="in_use">In use</option>
              <option value="idle">Idle</option>
              <option value="no_data">OS unreachable</option>
            </select>
          </div>
        </div>
        <div className="overflow-x-auto border-t border-surface-2">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-text-muted uppercase border-b border-surface-2">
              <th className="px-4 py-2">Server</th><th className="px-3 py-2">Team</th><th className="px-3 py-2">Family</th><th className="px-3 py-2">DC</th>
              <th className="px-3 py-2">CPU</th><th className="px-3 py-2">Mem</th><th className="px-3 py-2">Sessions</th><th className="px-3 py-2">Activity</th>
            </tr></thead>
            <tbody>
              {servers.map((s: any) => (
                <tr key={s.id} className="border-b border-surface-2 hover:bg-surface-2/40">
                  <td className="px-4 py-2 font-mono">{s.hostname}</td>
                  <td className="px-3 py-2 text-text-muted">{s.team ?? "—"}</td>
                  <td className="px-3 py-2 text-text-muted">{s.family ?? "—"}</td>
                  <td className="px-3 py-2 text-text-muted">{s.datacenter ?? "—"}</td>
                  <td className="px-3 py-2">{s.cpu_usage_avg != null ? formatPct(s.cpu_usage_avg) : "—"}</td>
                  <td className="px-3 py-2">{s.memory_usage_pct != null ? formatPct(s.memory_usage_pct) : "—"}</td>
                  <td className="px-3 py-2">{s.active_sessions || 0}</td>
                  <td className="px-3 py-2"><span className={`text-xs rounded-full px-2 py-0.5 ${ACT_BADGE[s.activity] ?? ""}`}>{ACT_LABEL[s.activity] ?? s.activity}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
