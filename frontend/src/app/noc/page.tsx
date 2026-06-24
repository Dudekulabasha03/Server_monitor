"use client";
import { useQuery } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { getStatusConfig, formatWatts, formatPct, formatTemp } from "@/lib/utils";
import { useEffect, useState, useRef } from "react";
import { formatDistanceToNow } from "date-fns";

// NOC Live Screen — auto-refreshes every 5 seconds, dark-room optimized

function LiveTicker({ alerts }: { alerts: any[] }) {
  return (
    <div className="bg-red-950/40 border border-red-800/40 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="live-dot bg-red-400" />
        <h2 className="text-sm font-bold text-red-400 uppercase tracking-widest">Active Critical Alerts</h2>
      </div>
      {alerts.length === 0 ? (
        <p className="text-sm text-green-400">✓ No critical alerts</p>
      ) : (
        <div className="space-y-2">
          {alerts.slice(0, 8).map((a) => (
            <div key={a.id} className="flex items-start gap-3 text-sm bg-red-900/20 rounded-lg p-2">
              <span className="text-red-400 font-mono text-xs mt-0.5">
                {formatDistanceToNow(new Date(a.fired_at), { addSuffix: true })}
              </span>
              <div>
                <span className="text-red-300 font-semibold">{a.title}</span>
                <p className="text-red-400/70 text-xs">{a.message}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TopServersList({
  title, servers, metric, format, colorFn
}: {
  title: string;
  servers: any[];
  metric: string;
  format: (v: any) => string;
  colorFn: (v: any) => string;
}) {
  const sorted = [...servers]
    .filter((s) => s[metric] !== null && s[metric] !== undefined)
    .sort((a, b) => b[metric] - a[metric])
    .slice(0, 8);

  return (
    <div className="card">
      <h3 className="text-xs font-bold text-text-secondary uppercase tracking-widest mb-3">{title}</h3>
      {sorted.length === 0 ? (
        <p className="text-xs text-text-muted">No data</p>
      ) : (
        <div className="space-y-2">
          {sorted.map((s, i) => (
            <div key={s.id} className="flex items-center gap-2 text-xs">
              <span className="text-text-muted w-4 text-right">{i + 1}</span>
              <span className="flex-1 truncate font-mono text-text-primary">{s.hostname}</span>
              <span className={`font-bold tabular-nums ${colorFn(s[metric])}`}>{format(s[metric])}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function NOCScreen() {
  const [tick, setTick] = useState(0);
  const [now, setNow] = useState(new Date());

  const { data: servers } = useQuery({
    queryKey: ["servers-noc"],
    queryFn: () => fleetApi.getServers({ page_size: 500 }),
    refetchInterval: 5_000,
  });
  const { data: criticalAlerts } = useQuery({
    queryKey: ["alerts-critical"],
    queryFn: () => fleetApi.getAlerts({ state: "firing", severity: "critical", page_size: 20 }),
    refetchInterval: 5_000,
  });
  const { data: summary } = useQuery({
    queryKey: ["fleet-summary"],
    queryFn: fleetApi.getSummary,
    refetchInterval: 5_000,
  });

  useEffect(() => {
    const interval = setInterval(() => {
      setTick((t) => t + 1);
      setNow(new Date());
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const allServers = servers ?? [];
  const offlineServers = allServers.filter((s) => s.status === "offline");
  const cpuReporting = allServers.filter((s) => s.cpu_usage_avg != null);
  const memReporting = allServers.filter((s) => s.memory_usage_pct != null);
  const avgCpu = cpuReporting.length ? cpuReporting.reduce((a, s) => a + (s.cpu_usage_avg ?? 0), 0) / cpuReporting.length : null;
  const avgMem = memReporting.length ? memReporting.reduce((a, s) => a + (s.memory_usage_pct ?? 0), 0) / memReporting.length : null;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* NOC Header */}
      <div className="flex items-center justify-between bg-surface border border-surface-2 rounded-xl px-5 py-3">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-lg font-bold text-text-primary tracking-tight">AMD NOC — Live Operations</h1>
            <p className="text-xs text-text-muted">Auto-refresh every 5 seconds</p>
          </div>
        </div>
        <div className="flex items-center gap-6">
          {summary && [
            { label: "Total", val: summary.total, color: "text-text-primary" },
            { label: "Healthy", val: summary.healthy, color: "text-green-400" },
            { label: "Warning", val: summary.warning, color: "text-yellow-400" },
            { label: "Critical", val: summary.critical, color: "text-red-400" },
            { label: "Offline", val: summary.offline, color: "text-gray-400" },
          ].map((item) => (
            <div key={item.label} className="text-center">
              <p className={`text-2xl font-bold ${item.color}`}>{item.val}</p>
              <p className="text-xs text-text-muted">{item.label}</p>
            </div>
          ))}
        </div>
        <div className="text-right">
          <p className="text-xl font-mono text-text-primary">
            {now.toLocaleTimeString("en-US", { hour12: false })}
          </p>
          <p className="text-xs text-text-muted">
            {now.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}
          </p>
        </div>
      </div>

      {/* Critical Alerts Ticker */}
      <LiveTicker alerts={criticalAlerts ?? []} />

      {/* Live OS utilization coverage (SSH/OS agent) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card"><p className="metric-label">Live CPU Reporting</p><p className="metric-value">{cpuReporting.length}<span className="text-sm text-text-muted">/{allServers.length}</span></p><p className="text-xs text-text-muted">via OS agent (SSH)</p></div>
        <div className="card"><p className="metric-label">Avg CPU (reachable)</p><p className="metric-value">{avgCpu != null ? formatPct(avgCpu) : "N/A"}</p></div>
        <div className="card"><p className="metric-label">Live Memory Reporting</p><p className="metric-value">{memReporting.length}<span className="text-sm text-text-muted">/{allServers.length}</span></p></div>
        <div className="card"><p className="metric-label">Avg Memory (reachable)</p><p className="metric-value">{avgMem != null ? formatPct(avgMem) : "N/A"}</p></div>
      </div>

      {/* Top Lists */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <TopServersList
          title="Hottest CPUs"
          servers={allServers}
          metric="cpu_temp_max"
          format={formatTemp}
          colorFn={(v) => v > 85 ? "text-red-400" : v > 75 ? "text-yellow-400" : "text-green-400"}
        />
        <TopServersList
          title="Top Power Draw"
          servers={allServers}
          metric="power_consumed_watts"
          format={formatWatts}
          colorFn={(v) => v > 1500 ? "text-red-400" : v > 1000 ? "text-yellow-400" : "text-blue-400"}
        />
        <TopServersList
          title="Highest CPU %"
          servers={allServers}
          metric="cpu_usage_avg"
          format={formatPct}
          colorFn={(v) => v > 90 ? "text-red-400" : v > 70 ? "text-yellow-400" : "text-green-400"}
        />
        <TopServersList
          title="Highest Memory %"
          servers={allServers}
          metric="memory_usage_pct"
          format={formatPct}
          colorFn={(v) => v > 90 ? "text-red-400" : v > 75 ? "text-yellow-400" : "text-blue-400"}
        />
      </div>

      {/* Offline Servers */}
      {offlineServers.length > 0 && (
        <div className="card border-gray-600/30">
          <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">
            Offline Servers ({offlineServers.length})
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {offlineServers.map((s) => (
              <div key={s.id} className="bg-gray-800/40 border border-gray-700/40 rounded-lg p-2">
                <p className="text-xs font-mono text-gray-400 truncate">{s.hostname}</p>
                <p className="text-xs text-gray-600">{s.bmc_ip}</p>
                <p className="text-xs text-gray-600 mt-1">
                  {s.last_seen ? formatDistanceToNow(new Date(s.last_seen), { addSuffix: true }) : "Never seen"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
