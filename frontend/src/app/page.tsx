"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { formatWatts, formatPct, formatTemp, healthScoreColor } from "@/lib/utils";
import { Thermometer, Zap, Server, Bell, Activity, AlertTriangle, Leaf, Brain, ChevronRight, Users, Home, ArrowRight } from "lucide-react";
import { PieChart, Pie, Cell } from "recharts";
import { HourOfWeekHeatmap } from "@/components/charts/HourOfWeekHeatmap";
import { ChangelogTable } from "@/components/ChangelogTable";
import Link from "next/link";
import { useAuthStore } from "@/lib/auth";

const BUCKET_COLORS: Record<string, string> = {
  idle: "#22c55e", light: "#a3e635", active: "#f59e0b", heavy: "#ef4444", unknown: "#64748b", off: "#475569",
};
const DONUT = ["#22c55e", "#f59e0b", "#f97316", "#ef4444", "#6b7280", "#475569"];

function StatCard({ label, value, sub, icon: Icon, color = "text-blue-400", bg = "bg-blue-400/10" }: any) {
  return (
    <div className="card flex items-center gap-4">
      <div className={`${bg} p-3 rounded-xl`}><Icon size={20} className={color} /></div>
      <div><p className="metric-label">{label}</p><p className="metric-value text-text-primary">{value}</p>{sub && <p className="text-xs text-text-muted mt-0.5">{sub}</p>}</div>
    </div>
  );
}

function HealthPills({ s }: { s: any }) {
  const items = [
    ["healthy", s.healthy, "#22c55e"], ["warning", s.warning, "#f59e0b"],
    ["critical", s.critical, "#ef4444"], ["offline", s.offline, "#6b7280"],
    ["unknown", s.unknown, "#475569"],
  ] as const;
  return (
    <div className="flex gap-2 flex-wrap">
      {items.filter(([, v]) => v > 0).map(([l, v, c]) => (
        <span key={l} className="flex items-center gap-1 text-xs"><span className="w-2 h-2 rounded-full" style={{ background: c }} />{v} {l}</span>
      ))}
    </div>
  );
}

function TeamCard({ team, summary, families, defaultOpen = false }: any) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card">
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center justify-between text-left">
        <div className="flex items-center gap-2">
          <ChevronRight size={16} className={`transition-transform ${open ? "rotate-90" : ""} text-text-muted`} />
          <span className="text-sm font-semibold">{team}</span>
          <span className="text-xs text-text-muted">{summary.total} servers</span>
          {summary.avg_health != null && <span className="text-xs text-text-muted">· avg {summary.avg_health}/100</span>}
        </div>
        <HealthPills s={summary} />
      </button>
      {open && (
        <div className="mt-3 pt-3 border-t border-surface-2 space-y-1.5">
          {families.map((f: any) => (
            <div key={f.family} className="flex items-center gap-3 text-xs">
              <span className="w-20 text-text-secondary">{f.family}</span>
              <span className="w-8 text-text-muted">{f.total}</span>
              <div className="flex-1"><HealthPills s={f} /></div>
              {f.avg_health != null && <span className="text-text-muted w-16 text-right">{f.avg_health}/100</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuthStore();
  const { data: summary } = useQuery({ queryKey: ["fleet-summary"], queryFn: fleetApi.getSummary, refetchInterval: 15_000 });
  const { data: alertStats } = useQuery({ queryKey: ["alert-stats"], queryFn: fleetApi.getAlertStats, refetchInterval: 15_000 });
  const { data: util } = useQuery({ queryKey: ["util-sum"], queryFn: () => fleetApi.utilSummary("7d"), refetchInterval: 15_000 });
  const { data: fam } = useQuery({ queryKey: ["util-fam"], queryFn: fleetApi.utilByFamily, refetchInterval: 20_000 });
  const { data: risk } = useQuery({ queryKey: ["risk"], queryFn: fleetApi.getRisk, refetchInterval: 30_000 });
  const { data: how } = useQuery({ queryKey: ["how-util"], queryFn: () => fleetApi.utilHourOfWeek("util"), refetchInterval: 60_000 });
  const { data: byTeam } = useQuery({ queryKey: ["util-team"], queryFn: fleetApi.utilByTeam, refetchInterval: 20_000 });
  const { data: changelog } = useQuery({ queryKey: ["changelog-dash"], queryFn: () => fleetApi.getChangelog({ hours: 24, limit: 15 }), refetchInterval: 20_000 });

  if (!summary) {
    return <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" /></div>;
  }

  const donutData = [
    { name: "Healthy", value: summary.healthy }, { name: "Warning", value: summary.warning },
    { name: "At Risk", value: summary.at_risk }, { name: "Critical", value: summary.critical },
    { name: "Offline", value: summary.offline }, { name: "Unknown", value: summary.unknown },
  ].filter((d) => d.value > 0);
  const totalAlerts = (alertStats?.critical ?? 0) + (alertStats?.warning ?? 0);
  const topRisk = (risk?.top_risk ?? []).filter((r: any) => r.risk_level !== "low").slice(0, 5);

  return (
    <div className="space-y-6 animate-fade-in">

      {/* Banner for regular users — they have a team-scoped workspace */}
      {user?.role === "user" && (
        <div className="flex items-center justify-between bg-amber-400/10 border border-amber-400/30 rounded-xl px-4 py-3">
          <div className="flex items-center gap-3">
            <Home size={16} className="text-amber-400 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-amber-400">You&apos;re viewing the full fleet</p>
              <p className="text-xs text-text-muted mt-0.5">
                Your personalised workspace shows only{" "}
                <span className="text-amber-400 font-medium">{user.team_name ?? "your team"}</span> servers with reservations, sessions, and team alerts.
              </p>
            </div>
          </div>
          <Link
            href="/user-home"
            className="flex items-center gap-1.5 flex-shrink-0 ml-4 px-3 py-2 text-xs font-semibold bg-amber-400/20 hover:bg-amber-400/30 border border-amber-400/30 text-amber-400 rounded-lg transition-colors"
          >
            My Workspace <ArrowRight size={13} />
          </Link>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Dashboard</h1>
          <p className="text-sm text-text-muted">Helios — AMD Server Health · Real-time Overview</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-text-muted bg-surface-2 px-3 py-1.5 rounded-lg"><span className="live-dot" /> Auto-refresh 15s</div>
      </div>

      {/* Status bar */}
      <div className="card">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm text-text-secondary font-medium">Servers:</span>
            <span className="text-2xl font-bold">{summary.total}</span><span className="text-sm text-text-muted">servers</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {[["Healthy", summary.healthy, "status-healthy"], ["Warning", summary.warning, "status-warning"], ["At Risk", summary.at_risk, "status-at-risk"], ["Critical", summary.critical, "status-critical"], ["Offline", summary.offline, "status-offline"]].map(([l, v, c]: any) => (
              <div key={l} className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${c} text-sm`}><span className="text-lg font-bold">{v}</span><span className="text-xs opacity-80">{l}</span></div>
            ))}
          </div>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Avg Health Score" value={summary.avg_health_score != null ? `${summary.avg_health_score}/100` : "—"} sub="Health-wide" icon={Server} color={healthScoreColor(summary.avg_health_score)} />
        <StatCard label="Total Power" value={formatWatts(summary.total_power_watts)} sub={`~${(((summary.total_power_watts ?? 0) / 1000) * 24 * 30 * 1.5 * 0.12).toFixed(0)} $/mo est.`} icon={Zap} color="text-yellow-400" bg="bg-yellow-400/10" />
        <StatCard label="Avg CPU Temp" value={formatTemp(summary.avg_cpu_temp)} sub={summary.avg_cpu_temp > 75 ? "⚠ Above normal" : "Normal"} icon={Thermometer} color={summary.avg_cpu_temp > 85 ? "text-red-400" : summary.avg_cpu_temp > 75 ? "text-yellow-400" : "text-green-400"} bg="bg-orange-400/10" />
        <StatCard label="Active Alerts" value={totalAlerts} sub={`${alertStats?.critical ?? 0} critical · ${alertStats?.warning ?? 0} warning`} icon={Bell} color={totalAlerts > 0 ? "text-red-400" : "text-green-400"} bg={totalAlerts > 0 ? "bg-red-400/10" : "bg-green-400/10"} />
      </div>

      {/* Utilization bucket bar + idle KPI */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-text-secondary flex items-center gap-2"><Activity size={15} /> Server Utilization</h3>
          <span className="text-xs text-text-muted">{util?.idle_pct ?? 0}% idle · {util?.tests_executing ?? 0} active · {(util?.datapoints ?? 0).toLocaleString()} datapoints</span>
        </div>
        {util?.buckets && (
          <>
            <div className="flex h-6 rounded overflow-hidden bg-surface-2">
              {["idle", "light", "active", "heavy", "unknown", "off"].map((b) => util.buckets[b] > 0 ? (
                <div key={b} title={`${b}: ${util.buckets[b]}`} style={{ width: `${(util.buckets[b] / summary.total) * 100}%`, background: BUCKET_COLORS[b] }} />
              ) : null)}
            </div>
            <div className="flex gap-3 mt-2 text-xs text-text-muted">
              {["idle", "light", "active", "heavy", "unknown"].map((b) => (
                <span key={b} className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: BUCKET_COLORS[b] }} /> {b} {util.buckets[b]}</span>
              ))}
            </div>
          </>
        )}
      </div>

      {/* By Team — Total + per-team (family breakdown inside) */}
      {byTeam && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-text-secondary flex items-center gap-2"><Users size={15} /> By Team &amp; Family</h3>
          <TeamCard team="Total — All Teams" summary={byTeam.total} families={byTeam.total_families} defaultOpen />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {(byTeam.teams ?? []).map((t: any) => (
              <TeamCard key={t.team} team={t.team} summary={t.summary} families={t.families} />
            ))}
          </div>
        </div>
      )}

      {/* Donut + Family + Top risk */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-text-secondary mb-4">Health Distribution</h3>
          <div className="flex items-center gap-4">
            <PieChart width={130} height={130}>
              <Pie data={donutData} cx={60} cy={60} innerRadius={42} outerRadius={60} paddingAngle={2} dataKey="value">
                {donutData.map((_, i) => <Cell key={i} fill={DONUT[i]} />)}
              </Pie>
            </PieChart>
            <div className="flex flex-col gap-1.5">
              {donutData.map((d, i) => (
                <div key={i} className="flex items-center gap-2 text-xs"><div className="w-2.5 h-2.5 rounded-full" style={{ background: DONUT[i] }} /><span className="text-text-secondary">{d.name}</span><span className="ml-auto font-semibold">{d.value}</span></div>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className="text-sm font-semibold text-text-secondary mb-3">By Family</h3>
          <div className="space-y-2">
            {(fam?.families ?? []).map((f: any) => (
              <div key={f.family} className="flex items-center gap-2 text-xs">
                <span className="w-20 text-text-secondary">{f.family}</span><span className="text-text-muted w-7">{f.total}</span>
                <div className="flex-1 flex h-4 rounded overflow-hidden bg-surface-2">
                  {["idle", "light", "active", "heavy", "unknown", "off"].map((b) => f.buckets[b] > 0 ? <div key={b} style={{ width: `${(f.buckets[b] / f.total) * 100}%`, background: BUCKET_COLORS[b] }} /> : null)}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3 className="text-sm font-semibold text-text-secondary mb-3 flex items-center gap-2"><Brain size={15} /> Top Risk</h3>
          {topRisk.length === 0 ? <p className="text-sm text-green-400">✓ No elevated-risk servers</p> : (
            <div className="space-y-1.5">
              {topRisk.map((r: any) => (
                <Link key={r.id} href={`/servers/${r.id}`} className="flex items-center justify-between text-xs hover:bg-surface-2/40 rounded px-2 py-1">
                  <span className="font-mono">{r.hostname}</span>
                  <span className="font-bold" style={{ color: r.overall_risk >= 70 ? "#ef4444" : "#f59e0b" }}>{r.overall_risk}</span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Hour-of-week utilization heatmap */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-secondary mb-2">Utilization — Hour of Week <span className="text-text-muted font-normal">(green=idle, red=heavy)</span></h3>
        <HourOfWeekHeatmap grid={how?.grid ?? []} palette="util" max={9} />
      </div>

      {/* Changelog */}
      <div className="card">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold text-text-secondary">Changelog — last 24 hours</h3>
          <Link href="/changelog" className="text-xs text-blue-400 hover:underline">View all →</Link>
        </div>
        <p className="text-xs text-text-muted mb-3"><b className="text-text-primary">{changelog?.total ?? 0}</b> event(s) in the last 24 hours. Newest first.</p>
        <ChangelogTable events={changelog?.events ?? []} compact />
      </div>
    </div>
  );
}
