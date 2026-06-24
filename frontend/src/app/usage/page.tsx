"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { BarChart3, Server, Activity, CalendarDays } from "lucide-react";
import ReactECharts from "echarts-for-react";

const PERIODS = [
  { key: "daily", label: "Daily" },
  { key: "weekly", label: "Weekly" },
  { key: "monthly", label: "Monthly" },
  { key: "yearly", label: "Yearly" },
];

function fmtBucket(t: string, period: string): string {
  const d = new Date(t);
  if (period === "yearly") return String(d.getUTCFullYear());
  if (period === "monthly") return d.toLocaleString(undefined, { month: "short", year: "2-digit", timeZone: "UTC" });
  if (period === "weekly") return `wk ${d.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" })}`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
}

const FAMILIES = ["Naples", "Rome", "Milan", "Genoa", "Bergamo", "Siena", "Turin"];
const TEAMS = ["Security Patch Team", "TSP", "DPDK team"];

export default function UsagePage() {
  const [period, setPeriod] = useState("daily");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [team, setTeam] = useState("");
  const [family, setFamily] = useState("");

  const filters: Record<string, any> = {};
  if (dateFrom) filters.date_from = dateFrom;
  if (dateTo) filters.date_to = dateTo;
  if (team) filters.team = team;
  if (family) filters.family = family;

  const { data: summary, isLoading } = useQuery({
    queryKey: ["usage-summary", period, dateFrom, dateTo, team, family],
    queryFn: () => fleetApi.usageSummary({ period, ...filters }),
    refetchInterval: 60_000,
  });
  const { data: byServer } = useQuery({
    queryKey: ["usage-by-server", dateFrom, dateTo, team, family],
    queryFn: () => fleetApi.usageByServer({ days: 30, ...filters }),
    refetchInterval: 60_000,
  });

  // Independent filters for the Per-Server Usage table (client-side)
  const [psTeam, setPsTeam] = useState("");
  const [psFamily, setPsFamily] = useState("");
  const [psSearch, setPsSearch] = useState("");

  const points: any[] = summary?.points ?? [];
  const maxExec = Math.max(1, ...points.map((p) => p.executions));
  const allServers: any[] = byServer?.servers ?? [];
  const servers = allServers.filter((s) =>
    (!psTeam || s.team === psTeam) &&
    (!psFamily || s.family === psFamily) &&
    (!psSearch || (s.hostname || "").toLowerCase().includes(psSearch.toLowerCase()))
  );
  const cov = summary?.coverage;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Utilization History</h1>
          <p className="text-sm text-text-muted">Server utilization over time — executions & active days</p>
        </div>
        <div className="flex gap-1 bg-surface-2 rounded-lg p-1">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              onClick={() => setPeriod(p.key)}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${
                period === p.key ? "bg-blue-600/30 text-blue-400" : "text-text-muted hover:text-text-primary"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Filters: date range + team + family */}
      <div className="card flex flex-wrap items-end gap-3">
        <div>
          <label className="text-xs text-text-muted block mb-1">From</label>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
            className="bg-surface-2 border border-surface-2 rounded px-2 py-1.5 text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <div>
          <label className="text-xs text-text-muted block mb-1">To</label>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
            className="bg-surface-2 border border-surface-2 rounded px-2 py-1.5 text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <div>
          <label className="text-xs text-text-muted block mb-1">Team</label>
          <select value={team} onChange={(e) => setTeam(e.target.value)}
            className="bg-surface-2 border border-surface-2 rounded px-2 py-1.5 text-sm focus:outline-none focus:border-blue-500">
            <option value="">All Teams</option>
            {TEAMS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-text-muted block mb-1">Family</label>
          <select value={family} onChange={(e) => setFamily(e.target.value)}
            className="bg-surface-2 border border-surface-2 rounded px-2 py-1.5 text-sm focus:outline-none focus:border-blue-500">
            <option value="">All Families</option>
            {FAMILIES.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
        {(dateFrom || dateTo || team || family) && (
          <button onClick={() => { setDateFrom(""); setDateTo(""); setTeam(""); setFamily(""); }}
            className="text-xs text-text-muted hover:text-text-primary border border-surface-2 rounded px-3 py-1.5">Clear</button>
        )}
      </div>

      {cov?.from && (
        <p className="text-xs text-text-muted flex items-center gap-1">
          <CalendarDays size={12} /> History window: {new Date(cov.from).toLocaleString()} → {new Date(cov.to).toLocaleString()}
          <span className="opacity-60">(bounded by snapshot retention; longer periods fill as history accrues)</span>
        </p>
      )}

      {isLoading ? (
        <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" /></div>
      ) : points.length === 0 ? (
        <div className="card flex flex-col items-center py-16 text-text-muted">
          <BarChart3 size={40} className="mb-3 opacity-30" />
          <p>No utilization history yet</p>
          <p className="text-xs mt-1">Usage accrues from PIPT/OS activity (active &amp; heavy buckets).</p>
        </div>
      ) : (
        <div className="card relative overflow-hidden">
          <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
            <h3 className="text-sm font-semibold text-text-secondary flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400" />
              </span>
              Health Utilization Stream — {period}
            </h3>
            <div className="flex items-center gap-3 text-xs text-text-muted">
              <span className="flex items-center gap-1"><span className="w-3 h-1 rounded bg-cyan-400" /> Active samples</span>
              <span className="flex items-center gap-1"><span className="w-3 h-1 rounded bg-fuchsia-400" /> Servers busy</span>
            </div>
          </div>
          <p className="text-xs text-text-muted mb-3">
            Live workload volume across the fleet. Each point = busy (active/heavy) data-points in that {period.replace("ly", "")}.
            <span className="text-cyan-400/80"> Click a point to filter the per-server table below.</span>
          </p>
          <ReactECharts
            style={{ height: 280 }}
            opts={{ renderer: "canvas" }}
            onEvents={{
              click: (e: any) => {
                // sync: clicking a point scrolls to & highlights per-server table
                const el = document.getElementById("per-server-usage");
                if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
              },
            }}
            option={{
              backgroundColor: "transparent",
              grid: { left: 44, right: 16, top: 24, bottom: 40 },
              tooltip: {
                trigger: "axis",
                backgroundColor: "rgba(15,23,42,0.95)",
                borderColor: "#1e293b",
                textStyle: { color: "#e2e8f0", fontSize: 11 },
                formatter: (ps: any[]) => {
                  const i = ps[0].dataIndex;
                  const p = points[i];
                  return `<b>${fmtBucket(p.t, period)}</b><br/>` +
                    `${p.executions} active samples<br/>` +
                    `${p.used_servers} servers busy<br/>` +
                    `avg util ${p.avg_util}/9`;
                },
              },
              xAxis: {
                type: "category",
                data: points.map((p) => fmtBucket(p.t, period)),
                axisLine: { lineStyle: { color: "#334155" } },
                axisLabel: { color: "#94a3b8", fontSize: 10 },
                axisTick: { show: false },
                boundaryGap: false,
              },
              yAxis: {
                type: "value",
                splitLine: { lineStyle: { color: "rgba(51,65,85,0.4)" } },
                axisLabel: { color: "#94a3b8", fontSize: 10 },
              },
              series: [
                {
                  name: "Active samples",
                  type: "line",
                  smooth: true,
                  symbol: "circle",
                  symbolSize: 7,
                  data: points.map((p) => p.executions),
                  lineStyle: { width: 3, color: "#22d3ee", shadowColor: "rgba(34,211,238,0.6)", shadowBlur: 14 },
                  itemStyle: { color: "#22d3ee", borderColor: "#0e7490", borderWidth: 1 },
                  areaStyle: {
                    color: {
                      type: "linear", x: 0, y: 0, x2: 0, y2: 1,
                      colorStops: [
                        { offset: 0, color: "rgba(34,211,238,0.45)" },
                        { offset: 1, color: "rgba(34,211,238,0.02)" },
                      ],
                    },
                  },
                  emphasis: { focus: "series", itemStyle: { shadowBlur: 20, shadowColor: "#22d3ee" } },
                  animationDuration: 1200,
                  animationEasing: "cubicOut",
                },
                {
                  name: "Servers busy",
                  type: "line",
                  smooth: true,
                  symbol: "none",
                  data: points.map((p) => p.used_servers),
                  lineStyle: { width: 2, color: "#e879f9", type: "dashed", shadowColor: "rgba(232,121,249,0.5)", shadowBlur: 10 },
                  itemStyle: { color: "#e879f9" },
                  animationDuration: 1400,
                },
              ],
            }}
          />
        </div>
      )}

      {/* Per-server usage */}
      <div id="per-server-usage" className="card p-0 overflow-x-auto scroll-mt-4">
        <div className="flex items-center justify-between flex-wrap gap-2 p-4 pb-2">
          <h3 className="text-sm font-semibold text-text-secondary flex items-center gap-2">
            <Server size={14} /> Per-Server Usage <span className="text-text-muted font-normal">({servers.length})</span>
          </h3>
          <div className="flex flex-wrap items-center gap-2">
            <input value={psSearch} onChange={(e) => setPsSearch(e.target.value)} placeholder="Search host…"
              className="bg-surface-2 border border-surface-2 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-500 w-36" />
            <select value={psTeam} onChange={(e) => setPsTeam(e.target.value)}
              className="bg-surface-2 border border-surface-2 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-500">
              <option value="">All Teams</option>
              {TEAMS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <select value={psFamily} onChange={(e) => setPsFamily(e.target.value)}
              className="bg-surface-2 border border-surface-2 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-500">
              <option value="">All Families</option>
              {FAMILIES.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            {(psTeam || psFamily || psSearch) && (
              <button onClick={() => { setPsTeam(""); setPsFamily(""); setPsSearch(""); }}
                className="text-xs text-text-muted hover:text-text-primary border border-surface-2 rounded px-2 py-1">Clear</button>
            )}
          </div>
        </div>
        {servers.length === 0 ? (
          <p className="px-4 pb-4 text-sm text-text-muted">No per-server usage recorded yet.</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
                <th className="px-4 py-2">Server</th>
                <th className="px-4 py-2">Family</th>
                <th className="px-4 py-2">Team</th>
                <th className="px-4 py-2">Active Days</th>
                <th className="px-4 py-2">Executions</th>
                <th className="px-4 py-2">Avg Util</th>
              </tr>
            </thead>
            <tbody>
              {servers.slice(0, 100).map((s) => (
                <tr key={s.server_id} className="border-b border-surface-2 hover:bg-surface-2/40">
                  <td className="px-4 py-2 text-sm font-mono">{s.hostname}</td>
                  <td className="px-4 py-2 text-sm">{s.family ?? "—"}</td>
                  <td className="px-4 py-2 text-sm text-text-muted">{s.team ?? "—"}</td>
                  <td className="px-4 py-2 text-sm">{s.active_days}</td>
                  <td className="px-4 py-2 text-sm font-semibold">{s.executions}</td>
                  <td className="px-4 py-2 text-sm text-text-muted">{s.avg_util}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
