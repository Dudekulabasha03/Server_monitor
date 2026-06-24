"use client";
import { useQuery } from "@tanstack/react-query";
import { fleetApi, ServerSummary } from "@/lib/api";
import { getStatusConfig, formatWatts, formatPct, formatTemp, healthScoreColor } from "@/lib/utils";
import { useState } from "react";
import Link from "next/link";
import { Search, Filter, Server } from "lucide-react";

// ── Health Score Ring ──────────────────────────────────────────────────────
function HealthRing({ score }: { score: number | null }) {
  if (score === null) return <div className="w-12 h-12 rounded-full bg-surface-2 flex items-center justify-center text-xs text-text-muted">—</div>;

  const r = 20;
  const circ = 2 * Math.PI * r;
  const fill = (score / 100) * circ;
  const color = score >= 90 ? "#22c55e" : score >= 70 ? "#f59e0b" : score >= 50 ? "#f97316" : "#ef4444";

  return (
    <div className="relative w-12 h-12">
      <svg width="48" height="48" viewBox="0 0 48 48">
        <circle cx="24" cy="24" r={r} fill="none" stroke="#334155" strokeWidth="4" />
        <circle
          cx="24" cy="24" r={r} fill="none" stroke={color} strokeWidth="4"
          strokeDasharray={`${fill} ${circ}`}
          strokeLinecap="round"
          transform="rotate(-90 24 24)"
        />
      </svg>
      <span className={`absolute inset-0 flex items-center justify-center text-xs font-bold ${healthScoreColor(score)}`}>
        {Math.round(score)}
      </span>
    </div>
  );
}

// ── Server Card ────────────────────────────────────────────────────────────
function ServerCard({ server }: { server: ServerSummary }) {
  const status = getStatusConfig(server.status);

  return (
    <Link href={`/servers/${server.id}`}>
      <div className={`card hover:bg-surface-2 transition-colors cursor-pointer border ${status.border}`}>
        {/* Header */}
        <div className="flex items-start justify-between mb-2">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-text-primary truncate">{server.hostname}</p>
            <p className="text-xs text-text-muted">{server.bmc_ip}</p>
          </div>
          <div className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border ${status.color} ${status.bg} ${status.border}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
            {status.label}
          </div>
        </div>

        {/* Model & Location */}
        <div className="text-xs text-text-muted mb-3 flex items-center gap-2 flex-wrap">
          {server.family && <span className="px-1.5 py-0.5 rounded bg-blue-400/10 text-blue-400">{server.family}</span>}
          <span>{server.model ?? server.vendor ?? "Unknown"}</span>
          {server.rack && <span>• Rack {server.rack}{server.rack_unit ? `/U${server.rack_unit}` : ""}</span>}
          {server.sensor_health === "Critical" && <span className="px-1.5 py-0.5 rounded bg-red-400/10 text-red-400 border border-red-400/30">BMC: Critical</span>}
          {server.sensor_health === "Warning" && <span className="px-1.5 py-0.5 rounded bg-yellow-400/10 text-yellow-400 border border-yellow-400/30">BMC: Warning</span>}
        </div>

        {/* Health Ring + Metrics */}
        <div className="flex items-center gap-4">
          <HealthRing score={server.health_score} />
          <div className="flex-1 grid grid-cols-2 gap-y-1.5 gap-x-3 text-xs">
            <div title={server.cpu_usage_avg == null ? "OS CPU% requires SSH access (not routable from this host)" : ""}>
              <span className="text-text-muted">CPU</span>
              <span className={`ml-2 font-semibold ${server.cpu_usage_avg == null ? "text-text-muted italic" : (server.cpu_usage_avg ?? 0) > 80 ? "text-red-400" : "text-text-primary"}`}>
                {server.cpu_usage_avg == null ? "N/A" : formatPct(server.cpu_usage_avg)}
              </span>
            </div>
            <div title={server.memory_usage_pct == null ? "OS memory% requires SSH access (not routable from this host)" : ""}>
              <span className="text-text-muted">Mem</span>
              <span className={`ml-2 font-semibold ${server.memory_usage_pct == null ? "text-text-muted italic" : (server.memory_usage_pct ?? 0) > 85 ? "text-red-400" : "text-text-primary"}`}>
                {server.memory_usage_pct == null ? "N/A" : formatPct(server.memory_usage_pct)}
              </span>
            </div>
            <div>
              <span className="text-text-muted">Temp</span>
              <span className={`ml-2 font-semibold ${(server.cpu_temp_max ?? 0) > 85 ? "text-red-400" : (server.cpu_temp_max ?? 0) > 75 ? "text-yellow-400" : "text-text-primary"}`}>
                {formatTemp(server.cpu_temp_max)}
              </span>
            </div>
            <div>
              <span className="text-text-muted">Power</span>
              <span className="ml-2 font-semibold text-text-primary">{formatWatts(server.power_consumed_watts)}</span>
            </div>
          </div>
        </div>

        {/* Team tag */}
        {server.team && (
          <div className="mt-3 pt-3 border-t border-surface-2 text-xs text-text-muted">
            {server.team}
          </div>
        )}
      </div>
    </Link>
  );
}

// ── Operations Dashboard ───────────────────────────────────────────────────
export default function OperationsDashboard() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [regionFilter, setRegionFilter] = useState("");
  const [familyFilter, setFamilyFilter] = useState("");

  const { data: servers, isLoading } = useQuery({
    queryKey: ["servers", search, statusFilter, teamFilter, regionFilter, familyFilter],
    queryFn: () => fleetApi.getServers({
      search, status: statusFilter || undefined, team: teamFilter || undefined,
      datacenter: regionFilter || undefined, family: familyFilter || undefined, page_size: 300,
    }),
    refetchInterval: 30_000,
  });

  const filtered = servers ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Operations Dashboard</h1>
          <p className="text-sm text-text-muted">{filtered.length} servers displayed</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Search hostname / IP..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-surface border border-surface-2 rounded-lg pl-8 pr-4 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-blue-500 w-64"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-blue-500"
        >
          <option value="">All Status</option>
          <option value="healthy">🟢 Healthy</option>
          <option value="warning">🟡 Warning</option>
          <option value="at_risk">🟠 At Risk</option>
          <option value="critical">🔴 Critical</option>
          <option value="offline">⚫ Offline</option>
        </select>

        <select value={regionFilter} onChange={(e) => setRegionFilter(e.target.value)}
          className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-blue-500">
          <option value="">All Regions</option>
          <option value="Santa Clara">Santa Clara</option>
          <option value="Plano">Plano</option>
          <option value="Dallas">Dallas</option>
          <option value="Bangalore">Bangalore</option>
        </select>

        <select value={familyFilter} onChange={(e) => setFamilyFilter(e.target.value)}
          className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-blue-500">
          <option value="">All Families</option>
          <option value="Naples">Naples</option>
          <option value="Rome">Rome</option>
          <option value="Milan">Milan</option>
          <option value="Genoa">Genoa</option>
          <option value="Bergamo">Bergamo</option>
          <option value="Siena">Siena</option>
          <option value="Turin">Turin</option>
        </select>

        <select
          value={teamFilter}
          onChange={(e) => setTeamFilter(e.target.value)}
          className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-blue-500"
        >
          <option value="">All Teams</option>
          <option value="Security Patch Team">Security Patch Team</option>
          <option value="TSP">TSP</option>
          <option value="DPDK team">DPDK team</option>
        </select>
      </div>

      {/* Server Grid */}
      {isLoading ? (
        <div className="flex justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map((server) => (
            <ServerCard key={server.id} server={server} />
          ))}
          {filtered.length === 0 && (
            <div className="col-span-full flex flex-col items-center py-20 text-text-muted">
              <Server size={40} className="mb-3 opacity-30" />
              <p>No servers match your filters</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
