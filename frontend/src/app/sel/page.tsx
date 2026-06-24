"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fleetApi } from "@/lib/api";
import { Search, Activity } from "lucide-react";

function sevColor(s: string): string {
  const k = (s || "").toLowerCase();
  if (k === "critical") return "text-red-400";
  if (k === "warning") return "text-yellow-400";
  return "text-text-muted";
}

export default function SelEventsPage() {
  const [host, setHost] = useState("");
  const [severity, setSeverity] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["sel", severity],
    queryFn: () => fleetApi.getSelEvents({ limit: 1000, severity: severity || undefined }),
    refetchInterval: 30_000,
  });

  const events: any[] = (data?.events ?? []).filter((e: any) =>
    !host || (e.hostname || "").toLowerCase().includes(host.toLowerCase())
  );
  const sev = data?.severity_counts ?? {};

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2"><Activity size={18} /> Recent Events (SEL)</h1>
        <p className="text-sm text-text-muted">
          System Event Log across all servers · <b className="text-text-primary">{data?.total ?? 0}</b> events from{" "}
          <b className="text-text-primary">{data?.servers_with_events ?? 0}</b> servers. Newest first.
        </p>
      </div>

      {/* Severity summary */}
      <div className="grid grid-cols-3 gap-3">
        <div className="card text-center"><p className="text-2xl font-bold text-red-400">{sev.Critical ?? 0}</p><p className="text-xs text-text-muted">Critical</p></div>
        <div className="card text-center"><p className="text-2xl font-bold text-yellow-400">{sev.Warning ?? 0}</p><p className="text-xs text-text-muted">Warning</p></div>
        <div className="card text-center"><p className="text-2xl font-bold text-text-secondary">{sev.Info ?? 0}</p><p className="text-xs text-text-muted">Info</p></div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative w-64">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input value={host} onChange={(e) => setHost(e.target.value)} placeholder="Search host..."
            className="w-full bg-surface border border-surface-2 rounded-lg pl-8 pr-4 py-1.5 text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <select value={severity} onChange={(e) => setSeverity(e.target.value)}
          className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
          <option value="">All Severities</option>
          <option value="Critical">Critical</option>
          <option value="Warning">Warning</option>
          <option value="Info">Info</option>
        </select>
      </div>

      <div className="card p-0 overflow-x-auto">
        {isLoading ? (
          <div className="flex justify-center py-16"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" /></div>
        ) : events.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-text-muted">
            <Activity size={40} className="mb-3 opacity-30" />
            <p>No SEL events</p>
            <p className="text-xs mt-1">Events appear here as BMCs report them (reachable servers only).</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
                <th className="px-4 py-2">Server</th>
                <th className="px-4 py-2">Team</th>
                <th className="px-4 py-2">Severity</th>
                <th className="px-4 py-2">Message</th>
                <th className="px-4 py-2">Time</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={i} className="border-b border-surface-2 hover:bg-surface-2/40">
                  <td className="px-4 py-2 font-mono">{e.hostname}</td>
                  <td className="px-4 py-2 text-text-muted">{e.team ?? "—"}</td>
                  <td className={`px-4 py-2 font-semibold ${sevColor(e.severity)}`}>{e.severity}</td>
                  <td className="px-4 py-2 max-w-xl">{e.message}</td>
                  <td className="px-4 py-2 text-text-muted whitespace-nowrap">{e.timestamp ? new Date(e.timestamp).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
