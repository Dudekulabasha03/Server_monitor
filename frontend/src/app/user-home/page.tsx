"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import {
  Server, Activity, RefreshCw, Thermometer, Zap, Cpu,
  CheckCircle2, AlertTriangle, WifiOff, Clock, BookOpen,
  Calendar, Plus, Trash2, Timer, Loader2, ChevronRight,
  BarChart3, Bell, Info, ArrowUpRight, Shield, CircuitBoard,
  Copy, Check, History, RefreshCcw, X,
} from "lucide-react";
import axios from "axios";
import { useAuthStore } from "@/lib/auth";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Colour helpers ────────────────────────────────────────────────────────────
const STATUS_COLOR: Record<string, string> = {
  healthy: "text-green-400", warning: "text-amber-400",
  at_risk: "text-orange-400", critical: "text-red-400",
  offline: "text-gray-400", unknown: "text-gray-500",
};
const STATUS_DOT: Record<string, string> = {
  healthy: "bg-green-400", warning: "bg-amber-400",
  at_risk: "bg-orange-400", critical: "bg-red-400",
  offline: "bg-gray-400", unknown: "bg-gray-500",
};
const STATUS_BG: Record<string, string> = {
  healthy: "bg-green-400/10 border-green-400/20",
  warning: "bg-amber-400/10 border-amber-400/20",
  at_risk: "bg-orange-400/10 border-orange-400/20",
  critical: "bg-red-400/10 border-red-400/20",
  offline: "bg-gray-400/10 border-gray-400/20",
  unknown: "bg-gray-500/10 border-gray-500/20",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${STATUS_BG[status] ?? ""} ${STATUS_COLOR[status] ?? "text-text-muted"}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${STATUS_DOT[status] ?? "bg-gray-400"}`} />
      {status}
    </span>
  );
}

function HealthBar({ score }: { score: number | null }) {
  if (score == null) return <span className="text-text-muted/50 text-xs">—</span>;
  const color = score >= 80 ? "bg-green-500" : score >= 60 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 bg-surface-2 rounded-full h-1.5">
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className={`text-xs ${score >= 80 ? "text-green-400" : score >= 60 ? "text-amber-400" : "text-red-400"}`}>
        {score}
      </span>
    </div>
  );
}

type TabId = "overview" | "servers" | "monitoring" | "bios" | "reserve" | "activity";

// ── Main page ─────────────────────────────────────────────────────────────────
export default function UserHomeDashboard() {
  const { user } = useAuthStore();
  const router = useRouter();

  const [tab, setTab]           = useState<TabId>("overview");
  const [teamCtx, setTeamCtx]   = useState<any>(null);
  const [servers, setServers]   = useState<any[]>([]);
  const [sessions, setSessions] = useState<any[]>([]);
  const [reservations, setResvs]= useState<any[]>([]);
  const [alerts, setAlerts]     = useState<any[]>([]);
  const [alertStats, setAlertStats] = useState<any>(null);
  const [utilTeam, setUtilTeam] = useState<any>(null);
  const [loading, setLoading]   = useState(true);
  const [srvSearch, setSrvSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [biosServers, setBiosServers] = useState<any[]>([]);
  const [changelog, setChangelog] = useState<any[]>([]);
  const [toasts, setToasts] = useState<{id:string; text:string; type:"alert"|"info"}[]>([]);
  const [copiedIp, setCopiedIp] = useState<string | null>(null);
  const [prismLoading, setPrismLoading] = useState<string | null>(null);

  // Reserve form state
  const [resForm, setResForm] = useState({
    server_id: "", purpose: "", benchmark_name: "", duration_hours: 24, notes: "",
  });
  const [resLoading, setResLoading] = useState(false);
  const [resMsg, setResMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const token = typeof window !== "undefined" ? localStorage.getItem("helios_jwt") : null;
  const headers = useMemo(() => token ? { Authorization: `Bearer ${token}` } : {}, [token]);

  const fetchAll = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const ctxRes = await axios.get(`${API_BASE}/auth/my-team-context`, { headers });
      const ctx = ctxRes.data;
      setTeamCtx(ctx);

      const fleetTeam = ctx.fleet_team;
      const teamQ = fleetTeam && !ctx.can_see_all
        ? `?team=${encodeURIComponent(fleetTeam)}&page_size=200`
        : "?page_size=200";

      const alertTeamQ = fleetTeam && !ctx.can_see_all
        ? `?team=${encodeURIComponent(fleetTeam)}&limit=50`
        : "?limit=50";

      const biosTeamQ = fleetTeam && !ctx.can_see_all ? `?team=${encodeURIComponent(fleetTeam)}` : "";
      const [srvRes, sessRes, resRes, alertRes, alertStatsRes, utilRes, biosRes] = await Promise.all([
        axios.get(`${API_BASE}/api/v1/servers${teamQ}`, { headers }),
        axios.get(`${API_BASE}/api/v1/users/sessions`, { headers }),
        axios.get(`${API_BASE}/reservations?active_only=true`, { headers }),
        axios.get(`${API_BASE}/api/v1/alerts${alertTeamQ}`, { headers }).catch(() => ({ data: { alerts: [] } })),
        axios.get(`${API_BASE}/api/v1/alerts/stats`, { headers }).catch(() => ({ data: null })),
        axios.get(`${API_BASE}/api/v1/util/by-team`, { headers }).catch(() => ({ data: null })),
        axios.get(`${API_BASE}/api/v1/bios/servers${biosTeamQ}`, { headers }).catch(() => ({ data: [] })),
      ]);

      const srvData = srvRes.data;
      const allServers = Array.isArray(srvData) ? srvData : (srvData.servers ?? []);
      setServers(allServers);

      // Filter sessions to team servers
      const allSessions = sessRes.data.sessions ?? [];
      const teamServerIds = new Set(allServers.map((s: any) => s.id));
      const teamSessions = allSessions.filter((s: any) => teamServerIds.has(s.server_id));
      setSessions(teamSessions);

      setResvs(resRes.data.reservations ?? []);

      // Filter alerts to team servers
      const allAlerts = alertRes.data?.alerts ?? [];
      const teamAlerts = allAlerts.filter((a: any) =>
        !fleetTeam || teamServerIds.has(a.server_id)
      );
      setAlerts(teamAlerts);
      setAlertStats(alertStatsRes.data);

      const biosData = biosRes.data;
      setBiosServers(Array.isArray(biosData) ? biosData : (biosData.servers ?? []));

      // Changelog for team servers
      if (fleetTeam) {
        try {
          const clRes = await axios.get(`${API_BASE}/api/v1/changelog?hours=24&limit=20`, { headers });
          const clData = clRes.data?.events ?? clRes.data ?? [];
          // Filter to team servers
          const allSrvs = Array.isArray(srvData) ? srvData : (srvData.servers ?? []);
          const teamHosts = new Set(allSrvs.map((s: any) => s.hostname));
          setChangelog(Array.isArray(clData) ? clData.filter((e: any) => teamHosts.has(e.hostname)) : []);
        } catch { /* ignore */ }
      }

      // Util by team — extract team row
      const utilData = utilRes.data;
      if (utilData?.teams && fleetTeam) {
        const teamRow = utilData.teams.find((t: any) =>
          t.team?.toLowerCase() === fleetTeam.toLowerCase()
        );
        setUtilTeam(teamRow ?? null);
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [user, headers]); // eslint-disable-line react-hooks/exhaustive-deps

  const addToast = (text: string, type: "alert" | "info" = "info") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, text, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  };

  const copyIp = (ip: string) => {
    navigator.clipboard.writeText(ip).catch(() => {});
    setCopiedIp(ip);
    setTimeout(() => setCopiedIp(null), 2000);
    addToast(`Copied ${ip}`, "info");
  };

  const prismRefresh = async (serverId: string, hostname: string) => {
    setPrismLoading(serverId);
    try {
      await axios.post(`${API_BASE}/api/v1/servers/${serverId}/prism-refresh`, {}, { headers });
      addToast(`PRISM refreshed: ${hostname}`, "info");
      fetchAll();
    } catch { addToast(`PRISM refresh failed for ${hostname}`, "alert"); }
    finally { setPrismLoading(null); }
  };

  useEffect(() => {
    if (!user) { router.replace("/login"); return; }
    fetchAll();
  }, [user, router, fetchAll]);

  // WebSocket for real-time alerts
  useEffect(() => {
    if (!user) return;
    const wsUrl = API_BASE.replace("http", "ws") + "/ws/live";
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "alert" && data.severity === "critical") {
            addToast(`🚨 Critical alert: ${data.server} — ${data.message}`, "alert");
          }
        } catch { /* ignore */ }
      };
    } catch { /* WS not available */ }
    return () => { try { ws?.close(); } catch { /* ignore */ } };
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Derived data ────────────────────────────────────────────────────────────
  const counts = useMemo(() =>
    servers.reduce((acc: Record<string, number>, s: any) => {
      acc[s.status] = (acc[s.status] || 0) + 1; return acc;
    }, {}),
    [servers]
  );

  const filtered = useMemo(() => {
    let list = servers;
    if (srvSearch) list = list.filter((s: any) => s.hostname?.toLowerCase().includes(srvSearch.toLowerCase()));
    if (statusFilter) list = list.filter((s: any) => s.status === statusFilter);
    return list;
  }, [servers, srvSearch, statusFilter]);

  const myReservations = useMemo(() =>
    reservations.filter((r: any) => r.user_email === user?.email),
    [reservations, user]
  );

  const mySessions = useMemo(() =>
    sessions.filter((s: any) =>
      s.username?.toLowerCase() === user?.email?.split("@")[0].toLowerCase()
    ),
    [sessions, user]
  );

  // Top at-risk servers (critical/at_risk, by health score ascending)
  const atRisk = useMemo(() =>
    [...servers]
      .filter((s: any) => ["critical", "at_risk", "warning"].includes(s.status))
      .sort((a, b) => (a.health_score ?? 100) - (b.health_score ?? 100))
      .slice(0, 5),
    [servers]
  );

  // Thermal hotspots
  const hottest = useMemo(() =>
    [...servers]
      .filter((s: any) => s.cpu_temp_max != null)
      .sort((a, b) => b.cpu_temp_max - a.cpu_temp_max)
      .slice(0, 5),
    [servers]
  );

  // Top power
  const topPower = useMemo(() =>
    [...servers]
      .filter((s: any) => s.power_consumed_watts != null && s.power_consumed_watts > 0)
      .sort((a, b) => b.power_consumed_watts - a.power_consumed_watts)
      .slice(0, 5),
    [servers]
  );

  const totalPower = useMemo(() =>
    servers.reduce((s: number, srv: any) =>
      s + (srv.power_consumed_watts && srv.power_consumed_watts < 50000 ? srv.power_consumed_watts : 0), 0
    ),
    [servers]
  );

  const avgHealth = useMemo(() => {
    const withScore = servers.filter((s: any) => s.health_score != null);
    if (!withScore.length) return null;
    return Math.round(withScore.reduce((s: number, x: any) => s + x.health_score, 0) / withScore.length);
  }, [servers]);

  // ── Reserve helpers ─────────────────────────────────────────────────────────
  const doReserve = async () => {
    if (!resForm.server_id || !resForm.purpose) {
      setResMsg({ type: "err", text: "Server and purpose are required" }); return;
    }
    setResLoading(true); setResMsg(null);
    try {
      await axios.post(`${API_BASE}/reservations`, resForm, { headers });
      setResMsg({ type: "ok", text: "Server reserved successfully!" });
      setResForm({ server_id: "", purpose: "", benchmark_name: "", duration_hours: 24, notes: "" });
      fetchAll();
    } catch (e: any) {
      setResMsg({ type: "err", text: e.response?.data?.detail || "Reservation failed" });
    } finally { setResLoading(false); }
  };

  const doRelease = async (id: string) => {
    await axios.delete(`${API_BASE}/reservations/${id}`, { headers });
    fetchAll();
  };

  if (!user) return null;

  const teamLabel = teamCtx?.team_name ?? "My Team";
  const criticalAlerts = alerts.filter((a: any) => a.severity === "critical");
  const warningAlerts = alerts.filter((a: any) => a.severity === "warning");

  // ── Tabs definition ─────────────────────────────────────────────────────────
  const biosNeedsUpdate = biosServers.filter((s: any) => s.firmware_baseline_compliant === false).length;
  const biosCompliancePct = biosServers.length > 0
    ? Math.round((biosServers.filter((s: any) => s.firmware_baseline_compliant !== false).length / biosServers.length) * 100)
    : null;

  const TABS: { id: TabId; label: string; icon: React.ElementType; badge?: number }[] = [
    { id: "overview",   label: "Overview",    icon: BarChart3 },
    { id: "servers",    label: "My Servers",  icon: Server,   badge: servers.length },
    { id: "monitoring", label: "Monitoring",  icon: Activity, badge: atRisk.length || undefined },
    { id: "bios",       label: "BIOS",        icon: CircuitBoard, badge: biosNeedsUpdate || undefined },
    { id: "reserve",    label: "Reserve",     icon: Calendar, badge: myReservations.length || undefined },
    { id: "activity",   label: "Activity",    icon: Clock,    badge: mySessions.length || undefined },
  ];

  return (
    <div className="space-y-4 animate-fade-in">

      {/* ── Toast notifications ─────────────────────────────────────────────── */}
      {toasts.length > 0 && (
        <div className="fixed bottom-4 right-4 z-50 space-y-2">
          {toasts.map((t) => (
            <div key={t.id} className={`flex items-center gap-3 px-4 py-3 rounded-xl shadow-xl border text-sm max-w-sm ${
              t.type === "alert"
                ? "bg-red-950 border-red-400/30 text-red-300"
                : "bg-surface border-surface-2 text-text-primary"
            }`}>
              <span className="flex-1">{t.text}</span>
              <button onClick={() => setToasts((ts) => ts.filter((x) => x.id !== t.id))} className="text-text-muted hover:text-text-primary">
                <X size={13} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── Page header ────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">My Workspace</h1>
          <p className="text-sm text-text-muted">
            {loading ? "Loading..." : <>
              <span className="text-amber-400 font-medium">{teamLabel}</span>
              {" — "}{servers.length} servers · {sessions.length} sessions · {myReservations.length} reservations
            </>}
          </p>
        </div>
        <button onClick={fetchAll} className="p-1.5 text-text-muted hover:text-text-primary transition-colors">
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* ── Tabs ───────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-1 bg-surface border border-surface-2 rounded-xl p-1 overflow-x-auto">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                tab === t.id
                  ? "bg-blue-600/20 text-blue-400 border border-blue-600/30"
                  : "text-text-secondary hover:bg-surface-2 hover:text-text-primary"
              }`}>
              <Icon size={14} /> {t.label}
              {t.badge ? (
                <span className="ml-1 bg-cyan-500/20 text-cyan-400 text-xs px-1.5 py-0.5 rounded-full">{t.badge}</span>
              ) : null}
            </button>
          );
        })}
      </div>

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* OVERVIEW TAB                                                          */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === "overview" && (
        <div className="space-y-4">

          {/* Welcome + summary bar */}
          <div className="bg-gradient-to-r from-cyan-900/20 to-blue-900/20 border border-cyan-600/20 rounded-xl p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="font-bold text-lg">Welcome back, {user.full_name.split(" ")[0]}!</h2>
                <p className="text-text-muted text-sm mt-1">
                  <span className="text-amber-400 font-medium">{teamLabel}</span>
                  {" — "}{servers.length} servers under your team
                </p>
                <p className="text-xs text-text-muted/60 mt-1">
                  Last login: {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "First login"}
                </p>
              </div>
              <div className="flex-shrink-0 text-right">
                <p className="text-xs text-text-muted">Team Avg Health</p>
                <p className={`text-3xl font-bold ${avgHealth != null ? (avgHealth >= 80 ? "text-green-400" : avgHealth >= 60 ? "text-amber-400" : "text-red-400") : "text-text-muted"}`}>
                  {avgHealth ?? "—"}<span className="text-sm text-text-muted">/100</span>
                </p>
              </div>
            </div>
          </div>

          {/* Status + Power + Temp + Alert + BIOS KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div className="card flex items-center gap-3">
              <div className="bg-green-400/10 p-2.5 rounded-xl"><CheckCircle2 size={16} className="text-green-400" /></div>
              <div><p className="text-xs text-text-muted">Healthy</p><p className="text-2xl font-bold text-green-400">{counts.healthy ?? 0}</p></div>
            </div>
            <div className="card flex items-center gap-3">
              <div className="bg-red-400/10 p-2.5 rounded-xl"><AlertTriangle size={16} className="text-red-400" /></div>
              <div><p className="text-xs text-text-muted">Issues</p><p className="text-2xl font-bold text-red-400">{(counts.critical ?? 0) + (counts.at_risk ?? 0) + (counts.warning ?? 0)}</p></div>
            </div>
            <div className="card flex items-center gap-3">
              <div className="bg-amber-400/10 p-2.5 rounded-xl"><Zap size={16} className="text-amber-400" /></div>
              <div><p className="text-xs text-text-muted">Team Power</p><p className="text-2xl font-bold text-amber-400">{totalPower > 0 ? `${(totalPower / 1000).toFixed(1)}kW` : "—"}</p></div>
            </div>
            <div className="card flex items-center gap-3">
              <div className="bg-red-400/10 p-2.5 rounded-xl"><Bell size={16} className="text-red-400" /></div>
              <div><p className="text-xs text-text-muted">Alerts</p><p className="text-2xl font-bold text-red-400">{criticalAlerts.length + warningAlerts.length}</p></div>
            </div>
            <div className="card flex items-center gap-3">
              <div className="bg-cyan-400/10 p-2.5 rounded-xl"><CircuitBoard size={16} className="text-cyan-400" /></div>
              <div>
                <p className="text-xs text-text-muted">BIOS Compliant</p>
                <p className={`text-2xl font-bold ${biosCompliancePct == null ? "text-text-muted" : biosCompliancePct >= 90 ? "text-green-400" : biosCompliancePct >= 70 ? "text-amber-400" : "text-red-400"}`}>
                  {biosCompliancePct != null ? `${biosCompliancePct}%` : "—"}
                </p>
              </div>
            </div>
          </div>

          {/* Status breakdown pill bar */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold">Fleet Health — {teamLabel}</h3>
              <Link href="/operations" className="text-xs text-cyan-400 hover:underline flex items-center gap-0.5">
                Operations <ArrowUpRight size={11} />
              </Link>
            </div>
            <div className="flex gap-0 h-3 rounded-full overflow-hidden w-full mb-2">
              {([
                ["healthy", counts.healthy ?? 0, "#22c55e"],
                ["warning", counts.warning ?? 0, "#f59e0b"],
                ["at_risk", counts.at_risk ?? 0, "#f97316"],
                ["critical", counts.critical ?? 0, "#ef4444"],
                ["offline", counts.offline ?? 0, "#6b7280"],
              ] as [string, number, string][]).filter(([, v]) => v > 0).map(([key, val, color]) => (
                <div key={key} style={{ width: `${(val / (servers.length || 1)) * 100}%`, background: color }}
                  title={`${key}: ${val}`} />
              ))}
            </div>
            <div className="flex flex-wrap gap-3 text-xs">
              {[
                ["healthy", counts.healthy ?? 0, "text-green-400"],
                ["warning", counts.warning ?? 0, "text-amber-400"],
                ["at_risk", counts.at_risk ?? 0, "text-orange-400"],
                ["critical", counts.critical ?? 0, "text-red-400"],
                ["offline", counts.offline ?? 0, "text-gray-400"],
              ].filter(([, v]) => (v as number) > 0).map(([key, val, color]) => (
                <span key={key as string} className={`flex items-center gap-1 ${color as string}`}>
                  <span className={`w-2 h-2 rounded-full ${(STATUS_DOT[key as string])}`} />
                  {val} {key as string}
                </span>
              ))}
            </div>
          </div>

          {/* Two-column: At-risk + Active alerts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

            {/* Top at-risk servers */}
            <div className="card p-0 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-surface-2">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <Shield size={13} className="text-red-400" /> Needs Attention ({atRisk.length})
                </h3>
                <button onClick={() => setTab("monitoring")} className="text-xs text-cyan-400 hover:underline">View all</button>
              </div>
              {atRisk.length === 0 ? (
                <div className="px-4 py-6 text-center text-text-muted text-sm">
                  <CheckCircle2 size={24} className="mx-auto mb-1 text-green-400 opacity-60" />
                  All servers healthy
                </div>
              ) : (
                <div className="divide-y divide-surface-2">
                  {atRisk.map((s: any) => (
                    <div key={s.id} className="flex items-center justify-between px-4 py-2.5 hover:bg-surface-2/40 transition-colors">
                      <div>
                        <Link href={`/servers/${s.id}`} className="font-mono text-xs hover:text-cyan-400 transition-colors">{s.hostname}</Link>
                        <p className="text-xs text-text-muted">{s.family ?? "—"} · {s.datacenter ?? "—"}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <HealthBar score={s.health_score} />
                        <StatusBadge status={s.status} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Active alerts (team scoped) */}
            <div className="card p-0 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-surface-2">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <Bell size={13} className="text-red-400" /> Active Alerts ({alerts.length})
                </h3>
                <Link href="/alerts" className="text-xs text-cyan-400 hover:underline flex items-center gap-0.5">
                  All alerts <ArrowUpRight size={11} />
                </Link>
              </div>
              {alerts.length === 0 ? (
                <div className="px-4 py-6 text-center text-text-muted text-sm">
                  <CheckCircle2 size={24} className="mx-auto mb-1 text-green-400 opacity-60" />
                  No active alerts
                </div>
              ) : (
                <div className="divide-y divide-surface-2 max-h-52 overflow-y-auto">
                  {alerts.slice(0, 8).map((a: any) => (
                    <div key={a.id} className="px-4 py-2.5 hover:bg-surface-2/40 transition-colors">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-xs font-medium truncate">{a.title ?? a.name}</p>
                          <p className="text-xs text-text-muted font-mono">{a.hostname ?? a.server_hostname ?? "—"}</p>
                        </div>
                        <span className={`text-xs px-2 py-0.5 rounded-full border flex-shrink-0 ${
                          a.severity === "critical" ? "text-red-400 bg-red-400/10 border-red-400/20" : "text-amber-400 bg-amber-400/10 border-amber-400/20"
                        }`}>{a.severity}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* My reservations preview */}
          {myReservations.length > 0 && (
            <div className="card">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <Calendar size={14} className="text-cyan-400" /> My Active Reservations
                </h3>
                <button onClick={() => setTab("reserve")} className="text-xs text-cyan-400 hover:underline">Manage</button>
              </div>
              <div className="space-y-2">
                {myReservations.slice(0, 3).map((r: any) => (
                  <div key={r.id} className="flex items-center justify-between bg-surface-2/40 rounded-lg px-3 py-2">
                    <span className="font-mono text-xs">{r.hostname}</span>
                    <span className="text-text-muted text-xs truncate max-w-[140px]">{r.purpose}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-amber-400 text-xs flex items-center gap-1">
                        <Timer size={11} /> {r.remaining_hours.toFixed(0)}h
                      </span>
                      <button onClick={() => doRelease(r.id)} className="text-red-400/60 hover:text-red-400 transition-colors">
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Utilization snapshot */}
          {utilTeam && (
            <div className="card">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <BarChart3 size={13} className="text-cyan-400" /> {teamLabel} Utilization
              </h3>
              <div className="grid grid-cols-4 gap-3 text-center">
                {(["idle", "light", "active", "heavy"] as const).map((bucket) => {
                  const val = utilTeam[bucket] ?? 0;
                  const colors: Record<string, string> = { idle: "text-green-400", light: "text-cyan-400", active: "text-amber-400", heavy: "text-red-400" };
                  return (
                    <div key={bucket} className="bg-surface-2/40 rounded-xl p-3">
                      <p className={`text-2xl font-bold ${colors[bucket]}`}>{val}</p>
                      <p className="text-xs text-text-muted capitalize">{bucket}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {/* Recent Changes changelog */}
          {changelog.length > 0 && (
            <div className="card p-0 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-surface-2">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <History size={13} className="text-cyan-400" /> Recent Changes (24h)
                </h3>
                <Link href="/changelog" className="text-xs text-cyan-400 hover:underline flex items-center gap-0.5">
                  All changes <ArrowUpRight size={11} />
                </Link>
              </div>
              <div className="divide-y divide-surface-2 max-h-40 overflow-y-auto">
                {changelog.slice(0, 8).map((e: any, i: number) => (
                  <div key={i} className="flex items-center justify-between px-4 py-2 hover:bg-surface-2/30">
                    <div>
                      <span className="font-mono text-xs">{e.hostname}</span>
                      <span className="text-xs text-text-muted ml-2">{e.change_type ?? e.event_type ?? "change"}</span>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-text-muted">{e.new_value ?? e.value ?? ""}</p>
                      <p className="text-xs text-text-muted/60">{e.occurred_at ? new Date(e.occurred_at).toLocaleTimeString() : ""}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* MY SERVERS TAB                                                        */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === "servers" && (
        <div className="space-y-3">
          {/* Summary row */}
          <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
            {(["healthy", "warning", "at_risk", "critical", "offline", "unknown"] as const).map((s) => (
              <button key={s} onClick={() => setStatusFilter(statusFilter === s ? "" : s)}
                className={`rounded-lg py-2 text-center border transition-colors ${
                  statusFilter === s ? STATUS_BG[s] : "bg-surface border-surface-2 hover:bg-surface-2"
                }`}>
                <p className={`text-lg font-bold ${STATUS_COLOR[s]}`}>{counts[s] ?? 0}</p>
                <p className="text-xs text-text-muted capitalize">{s.replace("_", " ")}</p>
              </button>
            ))}
          </div>

          <div className="card p-0 overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-surface-2">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <Server size={14} className="text-cyan-400" />
                {teamCtx?.team_name ?? "My"} Servers
                <span className="text-text-muted font-normal">({filtered.length})</span>
                {statusFilter && <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_BG[statusFilter]} ${STATUS_COLOR[statusFilter]}`}>{statusFilter}</span>}
              </h3>
              <div className="flex items-center gap-2 ml-auto">
                <input value={srvSearch} onChange={(e) => setSrvSearch(e.target.value)}
                  placeholder="Search hostname…"
                  className="text-xs bg-background border border-surface-2 rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500 w-40" />
                {(srvSearch || statusFilter) && (
                  <button onClick={() => { setSrvSearch(""); setStatusFilter(""); }} className="text-xs text-text-muted hover:text-text-primary">Clear</button>
                )}
              </div>
            </div>

            {loading ? (
              <div className="flex justify-center py-16"><div className="animate-spin rounded-full h-7 w-7 border-b-2 border-cyan-400" /></div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-surface-2 text-xs text-text-muted bg-surface/50">
                        <th className="text-left px-4 py-2.5 font-medium">Hostname</th>
                        <th className="text-left px-3 py-2.5 font-medium">Family</th>
                        <th className="text-left px-3 py-2.5 font-medium">DC</th>
                        <th className="text-left px-3 py-2.5 font-medium">Status</th>
                        <th className="text-left px-3 py-2.5 font-medium">Health</th>
                        <th className="text-left px-3 py-2.5 font-medium">
                          <Thermometer size={11} className="inline mr-0.5" />Temp
                        </th>
                        <th className="text-left px-3 py-2.5 font-medium">
                          <Zap size={11} className="inline mr-0.5" />Power
                        </th>
                        <th className="text-left px-3 py-2.5 font-medium">
                          <Cpu size={11} className="inline mr-0.5" />CPU%
                        </th>
                        <th className="text-left px-3 py-2.5 font-medium">OS IP</th>
                        <th className="text-left px-3 py-2.5 font-medium">Reserved</th>
                        <th className="text-left px-3 py-2.5 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.slice(0, 100).map((s: any) => {
                        const myRes   = reservations.find((r: any) => r.server_id === s.id && r.user_email === user.email);
                        const otherRes= reservations.find((r: any) => r.server_id === s.id && r.user_email !== user.email);
                        return (
                          <tr key={s.id} className="border-b border-surface-2/50 hover:bg-surface-2/40 transition-colors">
                            <td className="px-4 py-2.5">
                              <Link href={`/servers/${s.id}`} className="font-mono text-xs hover:text-cyan-400 transition-colors flex items-center gap-1">
                                {s.hostname} <ChevronRight size={10} className="opacity-0 group-hover:opacity-100" />
                              </Link>
                            </td>
                            <td className="px-3 py-2.5 text-xs text-text-muted">{s.family ?? "—"}</td>
                            <td className="px-3 py-2.5 text-xs text-text-muted">{s.datacenter ?? "—"}</td>
                            <td className="px-3 py-2.5"><StatusBadge status={s.status} /></td>
                            <td className="px-3 py-2.5"><HealthBar score={s.health_score} /></td>
                            <td className="px-3 py-2.5 text-xs">
                              <span className={s.cpu_temp_max >= 85 ? "text-red-400" : s.cpu_temp_max >= 75 ? "text-amber-400" : "text-text-muted"}>
                                {s.cpu_temp_max != null ? `${Math.round(s.cpu_temp_max)}°C` : "—"}
                              </span>
                            </td>
                            <td className="px-3 py-2.5 text-xs text-text-muted">
                              {s.power_consumed_watts != null && s.power_consumed_watts > 0 ? `${Math.round(s.power_consumed_watts)}W` : "—"}
                            </td>
                            <td className="px-3 py-2.5 text-xs text-text-muted">
                              {s.cpu_usage_avg != null ? `${Math.round(s.cpu_usage_avg)}%` : "—"}
                            </td>
                            {/* OS IP with copy button + PRISM refresh */}
                            <td className="px-3 py-2.5 text-xs">
                              {s.os_ip ? (
                                <div className="flex items-center gap-1">
                                  <span className="font-mono text-text-muted">{s.os_ip}</span>
                                  <button onClick={() => copyIp(s.os_ip)}
                                    className="p-0.5 text-text-muted/50 hover:text-cyan-400 transition-colors">
                                    {copiedIp === s.os_ip ? <Check size={10} className="text-green-400" /> : <Copy size={10} />}
                                  </button>
                                  <button onClick={() => prismRefresh(s.id, s.hostname)}
                                    disabled={prismLoading === s.id}
                                    title="Refresh OS IP from PRISM"
                                    className="p-0.5 text-text-muted/50 hover:text-cyan-400 transition-colors">
                                    {prismLoading === s.id ? <Loader2 size={10} className="animate-spin" /> : <RefreshCcw size={10} />}
                                  </button>
                                </div>
                              ) : (
                                <button onClick={() => prismRefresh(s.id, s.hostname)}
                                  disabled={prismLoading === s.id}
                                  className="text-text-muted/40 hover:text-cyan-400 flex items-center gap-0.5 transition-colors">
                                  {prismLoading === s.id ? <Loader2 size={10} className="animate-spin" /> : <RefreshCcw size={10} />}
                                  <span>Get IP</span>
                                </button>
                              )}
                            </td>
                            <td className="px-3 py-2.5 text-xs">
                              {myRes ? (
                                <span className="text-green-400 flex items-center gap-1">
                                  <CheckCircle2 size={10} /> Mine ({myRes.remaining_hours.toFixed(0)}h)
                                </span>
                              ) : otherRes ? (
                                <span className="text-amber-400">{otherRes.user_name?.split(" ")[0] ?? otherRes.user_email.split("@")[0]}</span>
                              ) : (
                                <span className="text-text-muted/40">Free</span>
                              )}
                            </td>
                            <td className="px-3 py-2.5">
                              {myRes ? (
                                <button onClick={() => doRelease(myRes.id)}
                                  className="text-xs text-red-400 hover:text-red-300 border border-red-400/30 px-2 py-0.5 rounded transition-colors">
                                  Release
                                </button>
                              ) : !otherRes ? (
                                <button onClick={() => { setResForm((f) => ({ ...f, server_id: s.id })); setTab("reserve"); }}
                                  className="text-xs text-cyan-400 hover:text-cyan-300 border border-cyan-400/30 px-2 py-0.5 rounded transition-colors">
                                  Reserve
                                </button>
                              ) : null}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {filtered.length > 100 && (
                  <p className="text-xs text-text-muted text-center py-3">
                    Showing 100 of {filtered.length} — use search or status filter
                  </p>
                )}
                {filtered.length === 0 && (
                  <div className="py-10 text-center text-text-muted text-sm">No servers match your filter</div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* MONITORING TAB                                                        */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === "monitoring" && (
        <div className="space-y-4">
          {/* Three metric panels */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

            {/* Thermal hotspots */}
            <div className="card p-0 overflow-hidden">
              <div className="px-4 py-3 border-b border-surface-2 flex items-center gap-2">
                <Thermometer size={14} className="text-red-400" />
                <h3 className="text-sm font-semibold">Thermal Hotspots</h3>
              </div>
              <div className="divide-y divide-surface-2">
                {hottest.length === 0 ? (
                  <p className="text-xs text-text-muted px-4 py-6 text-center">No temperature data</p>
                ) : hottest.map((s: any) => (
                  <div key={s.id} className="flex items-center justify-between px-4 py-2.5">
                    <div>
                      <Link href={`/servers/${s.id}`} className="font-mono text-xs hover:text-cyan-400">{s.hostname}</Link>
                      <p className="text-xs text-text-muted">{s.datacenter}</p>
                    </div>
                    <span className={`text-sm font-bold ${s.cpu_temp_max >= 85 ? "text-red-400" : s.cpu_temp_max >= 75 ? "text-amber-400" : "text-green-400"}`}>
                      {Math.round(s.cpu_temp_max)}°C
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Top power consumers */}
            <div className="card p-0 overflow-hidden">
              <div className="px-4 py-3 border-b border-surface-2 flex items-center gap-2">
                <Zap size={14} className="text-amber-400" />
                <h3 className="text-sm font-semibold">Top Power Draw</h3>
              </div>
              <div className="divide-y divide-surface-2">
                {topPower.length === 0 ? (
                  <p className="text-xs text-text-muted px-4 py-6 text-center">No power data</p>
                ) : topPower.map((s: any) => (
                  <div key={s.id} className="flex items-center justify-between px-4 py-2.5">
                    <div>
                      <Link href={`/servers/${s.id}`} className="font-mono text-xs hover:text-cyan-400">{s.hostname}</Link>
                      <p className="text-xs text-text-muted">{s.family}</p>
                    </div>
                    <span className="text-sm font-bold text-amber-400">{Math.round(s.power_consumed_watts)}W</span>
                  </div>
                ))}
                {topPower.length > 0 && (
                  <div className="px-4 py-2 bg-surface-2/30 flex justify-between text-xs text-text-muted">
                    <span>Team total</span>
                    <span className="font-semibold text-amber-400">{(totalPower / 1000).toFixed(1)} kW</span>
                  </div>
                )}
              </div>
            </div>

            {/* At-risk servers */}
            <div className="card p-0 overflow-hidden">
              <div className="px-4 py-3 border-b border-surface-2 flex items-center gap-2">
                <AlertTriangle size={14} className="text-red-400" />
                <h3 className="text-sm font-semibold">Needs Attention ({atRisk.length})</h3>
              </div>
              <div className="divide-y divide-surface-2">
                {atRisk.length === 0 ? (
                  <div className="px-4 py-6 text-center text-text-muted text-sm">
                    <CheckCircle2 size={20} className="mx-auto mb-1 text-green-400 opacity-60" />
                    All servers healthy
                  </div>
                ) : atRisk.map((s: any) => (
                  <div key={s.id} className="px-4 py-2.5">
                    <div className="flex items-center justify-between">
                      <Link href={`/servers/${s.id}`} className="font-mono text-xs hover:text-cyan-400">{s.hostname}</Link>
                      <StatusBadge status={s.status} />
                    </div>
                    <HealthBar score={s.health_score} />
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Team alerts */}
          <div className="card p-0 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-surface-2">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <Bell size={13} className="text-red-400" /> Team Alerts ({alerts.length})
                {criticalAlerts.length > 0 && (
                  <span className="text-xs px-2 py-0.5 bg-red-400/10 border border-red-400/20 text-red-400 rounded-full">
                    {criticalAlerts.length} critical
                  </span>
                )}
              </h3>
              <Link href="/alerts" className="text-xs text-cyan-400 hover:underline">Open Alerts page</Link>
            </div>
            {alerts.length === 0 ? (
              <div className="px-4 py-8 text-center text-text-muted text-sm">
                <CheckCircle2 size={24} className="mx-auto mb-2 text-green-400 opacity-60" />
                No active alerts for {teamLabel}
              </div>
            ) : (
              <div className="overflow-x-auto max-h-64">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-surface/90">
                    <tr className="border-b border-surface-2 text-xs text-text-muted">
                      <th className="text-left px-4 py-2">Severity</th>
                      <th className="text-left px-3 py-2">Alert</th>
                      <th className="text-left px-3 py-2">Server</th>
                      <th className="text-left px-3 py-2">Message</th>
                      <th className="text-left px-3 py-2">Since</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.map((a: any) => (
                      <tr key={a.id} className="border-b border-surface-2/50 hover:bg-surface-2/40">
                        <td className="px-4 py-2.5">
                          <span className={`text-xs px-2 py-0.5 rounded-full border ${
                            a.severity === "critical" ? "text-red-400 bg-red-400/10 border-red-400/20" : "text-amber-400 bg-amber-400/10 border-amber-400/20"
                          }`}>{a.severity}</span>
                        </td>
                        <td className="px-3 py-2.5 text-xs font-medium">{a.title ?? a.name ?? "—"}</td>
                        <td className="px-3 py-2.5 font-mono text-xs">{a.hostname ?? a.server_hostname ?? "—"}</td>
                        <td className="px-3 py-2.5 text-xs text-text-muted max-w-48 truncate">{a.message ?? "—"}</td>
                        <td className="px-3 py-2.5 text-xs text-text-muted">
                          {a.triggered_at ? new Date(a.triggered_at).toLocaleDateString() : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Info panel */}
          <div className="bg-surface/50 border border-surface-2 rounded-xl px-4 py-3 flex items-start gap-2 text-xs text-text-muted">
            <Info size={13} className="flex-shrink-0 mt-0.5 text-cyan-400" />
            <span>
              Monitoring data is scoped to <strong className="text-text-primary">{teamLabel}</strong> servers only.
              {" "}For full fleet analysis and deeper metrics, visit the{" "}
              <Link href="/" className="text-cyan-400 hover:underline">Fleet Dashboard</Link>,{" "}
              <Link href="/thermal" className="text-cyan-400 hover:underline">Thermal</Link>, or{" "}
              <Link href="/power" className="text-cyan-400 hover:underline">Power</Link> pages.
            </span>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* BIOS TAB                                                              */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === "bios" && (
        <div className="space-y-4">
          {/* Summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Total Servers",   value: biosServers.length, color: "text-cyan-400" },
              { label: "Compliant",       value: biosServers.filter((s: any) => s.firmware_baseline_compliant !== false).length, color: "text-green-400" },
              { label: "Non-Compliant",   value: biosNeedsUpdate, color: "text-red-400" },
              { label: "Unknown",         value: biosServers.filter((s: any) => s.firmware_baseline_compliant == null).length, color: "text-gray-400" },
            ].map(({ label, value, color }) => (
              <div key={label} className="card text-center">
                <p className={`text-2xl font-bold ${color}`}>{value}</p>
                <p className="text-xs text-text-muted mt-1">{label}</p>
              </div>
            ))}
          </div>

          {/* Non-compliant servers first */}
          {biosNeedsUpdate > 0 && (
            <div className="bg-red-400/5 border border-red-400/20 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-red-400 flex items-center gap-2 mb-3">
                <AlertTriangle size={14} /> {biosNeedsUpdate} servers need BIOS update
              </h3>
              <div className="space-y-1.5">
                {biosServers.filter((s: any) => s.firmware_baseline_compliant === false).slice(0, 5).map((s: any) => (
                  <div key={s.id} className="flex items-center justify-between text-xs bg-surface/50 rounded-lg px-3 py-2">
                    <span className="font-mono">{s.hostname}</span>
                    <span className="text-text-muted">{s.bios_version ?? "—"} → {s.firmware_baseline ?? "baseline"}</span>
                    <Link href={`/bios?server=${s.hostname}`} className="text-cyan-400 hover:underline flex items-center gap-1">
                      Update <ArrowUpRight size={10} />
                    </Link>
                  </div>
                ))}
                {biosNeedsUpdate > 5 && (
                  <p className="text-xs text-text-muted text-center">+{biosNeedsUpdate - 5} more — <Link href="/bios" className="text-cyan-400 hover:underline">open BIOS page</Link></p>
                )}
              </div>
            </div>
          )}

          {/* Full BIOS table */}
          <div className="card p-0 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-surface-2">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <CircuitBoard size={14} className="text-cyan-400" />
                {teamLabel} BIOS Status ({biosServers.length} servers)
              </h3>
              <Link href="/bios" className="flex items-center gap-1 text-xs text-cyan-400 hover:underline">
                Full BIOS Management <ArrowUpRight size={11} />
              </Link>
            </div>

            {biosServers.length === 0 ? (
              <div className="py-10 text-center text-text-muted text-sm">
                {loading ? "Loading BIOS data..." : "No BIOS data available"}
              </div>
            ) : (
              <div className="overflow-x-auto max-h-96">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-surface/90">
                    <tr className="border-b border-surface-2 text-xs text-text-muted">
                      <th className="text-left px-4 py-2.5">Server</th>
                      <th className="text-left px-3 py-2.5">Family</th>
                      <th className="text-left px-3 py-2.5">DC</th>
                      <th className="text-left px-3 py-2.5">BIOS Version</th>
                      <th className="text-left px-3 py-2.5">BMC Version</th>
                      <th className="text-left px-3 py-2.5">Microcode</th>
                      <th className="text-left px-3 py-2.5">Compliant</th>
                      <th className="text-left px-3 py-2.5">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* Non-compliant first */}
                    {[...biosServers].sort((a: any, b: any) => {
                      if (a.firmware_baseline_compliant === false && b.firmware_baseline_compliant !== false) return -1;
                      if (b.firmware_baseline_compliant === false && a.firmware_baseline_compliant !== false) return 1;
                      return 0;
                    }).slice(0, 100).map((s: any) => {
                      const compliant = s.firmware_baseline_compliant;
                      return (
                        <tr key={s.id} className={`border-b border-surface-2/50 hover:bg-surface-2/40 transition-colors ${
                          compliant === false ? "border-l-2 border-l-red-400/50" : ""
                        }`}>
                          <td className="px-4 py-2.5">
                            <Link href={`/servers/${s.id}`} className="font-mono text-xs hover:text-cyan-400 transition-colors">
                              {s.hostname}
                            </Link>
                          </td>
                          <td className="px-3 py-2.5 text-xs text-text-muted">{s.family ?? "—"}</td>
                          <td className="px-3 py-2.5 text-xs text-text-muted">{s.datacenter ?? "—"}</td>
                          <td className="px-3 py-2.5 text-xs font-mono">{s.bios_version ?? "—"}</td>
                          <td className="px-3 py-2.5 text-xs font-mono text-text-muted">{s.bmc_firmware ?? "—"}</td>
                          <td className="px-3 py-2.5 text-xs font-mono text-text-muted">{s.microcode ? `0x${s.microcode.toString(16)}` : "—"}</td>
                          <td className="px-3 py-2.5 text-xs">
                            {compliant === true ? (
                              <span className="text-green-400 flex items-center gap-1"><CheckCircle2 size={11} /> Yes</span>
                            ) : compliant === false ? (
                              <span className="text-red-400 flex items-center gap-1"><AlertTriangle size={11} /> No</span>
                            ) : (
                              <span className="text-gray-400">—</span>
                            )}
                          </td>
                          <td className="px-3 py-2.5">
                            <Link href="/bios"
                              className="text-xs text-cyan-400 hover:text-cyan-300 border border-cyan-400/30 px-2 py-0.5 rounded transition-colors">
                              Manage
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {biosServers.length > 100 && (
                  <p className="text-xs text-text-muted text-center py-3">
                    Showing 100 of {biosServers.length} — <Link href="/bios" className="text-cyan-400 hover:underline">open BIOS page for full view</Link>
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="bg-surface/50 border border-surface-2 rounded-xl px-4 py-3 flex items-start gap-2 text-xs text-text-muted">
            <Info size={13} className="flex-shrink-0 mt-0.5 text-cyan-400" />
            <span>
              BIOS updates require OS credentials (IP, username, password) to verify compatibility before flashing.
              Use the <Link href="/bios" className="text-cyan-400 hover:underline">full BIOS page</Link> for flash, batch update, attribute tuning, and compliance baseline management.
            </span>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* RESERVE TAB                                                           */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === "reserve" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

          {/* Reserve form */}
          <div className="card space-y-4">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Plus size={14} className="text-cyan-400" /> Reserve a Server
            </h3>
            {resMsg && (
              <div className={`text-sm px-3 py-2 rounded-lg border ${
                resMsg.type === "ok" ? "text-green-400 bg-green-400/10 border-green-400/30"
                  : "text-red-400 bg-red-400/10 border-red-400/30"
              }`}>{resMsg.text}</div>
            )}
            <div className="space-y-3">
              <div>
                <label className="text-xs text-text-muted mb-1 block">Server * <span className="text-text-muted/50">(your team only)</span></label>
                <select value={resForm.server_id} onChange={(e) => setResForm((f) => ({ ...f, server_id: e.target.value }))}
                  className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500">
                  <option value="">Select a server…</option>
                  {servers
                    .filter((s: any) => !reservations.find((r: any) => r.server_id === s.id && r.user_email !== user.email))
                    .map((s: any) => (
                      <option key={s.id} value={s.id}>
                        {s.hostname} ({s.status}) — {s.family ?? "?"}, {s.datacenter ?? "?"}
                      </option>
                    ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-text-muted mb-1 block">Purpose *</label>
                <input value={resForm.purpose} onChange={(e) => setResForm((f) => ({ ...f, purpose: e.target.value }))}
                  placeholder="e.g. BIOS upgrade, DPDK testing, firmware validation…"
                  className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500" />
              </div>
              <div>
                <label className="text-xs text-text-muted mb-1 block">Benchmark / Workload</label>
                <input value={resForm.benchmark_name} onChange={(e) => setResForm((f) => ({ ...f, benchmark_name: e.target.value }))}
                  placeholder="e.g. SPECcpu 2017, STREAM, fio, iperf3, DPDK testpmd…"
                  className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500" />
              </div>
              <div>
                <label className="text-xs text-text-muted mb-1 block">Duration (hours, max 168 = 7 days)</label>
                <div className="flex gap-2">
                  {[4, 8, 24, 48, 72].map((h) => (
                    <button key={h} type="button"
                      onClick={() => setResForm((f) => ({ ...f, duration_hours: h }))}
                      className={`text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
                        resForm.duration_hours === h ? "bg-cyan-600/20 border-cyan-600/30 text-cyan-400" : "border-surface-2 text-text-muted hover:bg-surface-2"
                      }`}>{h}h</button>
                  ))}
                  <input type="number" min={1} max={168} value={resForm.duration_hours}
                    onChange={(e) => setResForm((f) => ({ ...f, duration_hours: parseInt(e.target.value) || 24 }))}
                    className="flex-1 bg-background border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cyan-500 min-w-0" />
                </div>
              </div>
              <div>
                <label className="text-xs text-text-muted mb-1 block">Notes</label>
                <textarea value={resForm.notes} onChange={(e) => setResForm((f) => ({ ...f, notes: e.target.value }))}
                  rows={2} placeholder="Any additional notes…"
                  className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500 resize-none" />
              </div>
              <button onClick={doReserve} disabled={resLoading}
                className="w-full flex items-center justify-center gap-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold px-4 py-2.5 rounded-lg disabled:opacity-50 transition-colors">
                {resLoading ? <Loader2 size={15} className="animate-spin" /> : <Calendar size={15} />}
                Reserve Server
              </button>
            </div>
          </div>

          {/* My active reservations */}
          <div className="card">
            <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
              <BookOpen size={14} className="text-cyan-400" /> My Reservations ({myReservations.length})
            </h3>
            {myReservations.length === 0 ? (
              <div className="text-center py-8 text-text-muted">
                <Calendar size={28} className="mx-auto mb-2 opacity-30" />
                <p className="text-sm">No active reservations</p>
                <p className="text-xs mt-1">Select a server from the form or the Servers tab</p>
              </div>
            ) : (
              <div className="space-y-3">
                {myReservations.map((r: any) => (
                  <div key={r.id} className="bg-surface-2/40 border border-surface-2 rounded-xl p-3 space-y-2">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="font-mono text-sm font-semibold">{r.hostname}</p>
                        <p className="text-xs text-text-muted mt-0.5">{r.purpose}</p>
                        {r.benchmark_name && (
                          <p className="text-xs text-cyan-400/80 mt-0.5">📊 {r.benchmark_name}</p>
                        )}
                      </div>
                      <button onClick={() => doRelease(r.id)}
                        className="text-red-400 hover:text-red-300 p-1 hover:bg-red-400/10 rounded transition-colors">
                        <Trash2 size={13} />
                      </button>
                    </div>
                    <div className="flex items-center justify-between text-xs text-text-muted">
                      <span className="flex items-center gap-1"><Timer size={10} /> {r.remaining_hours.toFixed(1)}h remaining</span>
                      <span>Expires {new Date(r.expires_at).toLocaleString()}</span>
                    </div>
                    <div className="w-full bg-surface-2 rounded-full h-1">
                      <div className="h-1 rounded-full bg-cyan-500"
                        style={{ width: `${Math.min(100, (1 - r.remaining_hours / 168) * 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Others' reservations in this team */}
            {reservations.filter((r: any) => r.user_email !== user.email).length > 0 && (
              <div className="mt-4 pt-4 border-t border-surface-2">
                <h4 className="text-xs text-text-muted mb-2 uppercase tracking-wider">Reserved by Teammates</h4>
                <div className="space-y-1.5">
                  {reservations.filter((r: any) => r.user_email !== user.email).map((r: any) => (
                    <div key={r.id} className="flex items-center justify-between text-xs">
                      <span className="font-mono text-text-primary">{r.hostname}</span>
                      <span className="text-text-muted">{r.user_name?.split(" ")[0] ?? r.user_email.split("@")[0]}</span>
                      <span className="text-amber-400">{r.remaining_hours.toFixed(0)}h left</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* ACTIVITY TAB                                                          */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {tab === "activity" && (
        <div className="space-y-4">

          {/* My sessions */}
          <div className="card p-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-surface-2">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <Clock size={14} className="text-cyan-400" /> My Active Sessions ({mySessions.length})
              </h3>
            </div>
            {mySessions.length === 0 ? (
              <div className="px-4 py-8 text-center text-text-muted text-sm">
                No active SSH/console sessions detected for your username.
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-2 text-xs text-text-muted">
                    <th className="text-left px-4 py-2">Server</th>
                    <th className="text-left px-3 py-2">Type</th>
                    <th className="text-left px-3 py-2">Source IP</th>
                    <th className="text-left px-3 py-2">CPU%</th>
                    <th className="text-left px-3 py-2">Mem%</th>
                    <th className="text-left px-3 py-2">Login</th>
                  </tr>
                </thead>
                <tbody>
                  {mySessions.map((s: any) => (
                    <tr key={s.id} className="border-b border-surface-2/50 hover:bg-surface-2/40">
                      <td className="px-4 py-2.5 font-mono text-xs">{s.hostname}</td>
                      <td className="px-3 py-2.5 text-xs">{s.session_type ?? "—"}</td>
                      <td className="px-3 py-2.5 text-xs text-text-muted">{s.source_ip ?? "local"}</td>
                      <td className="px-3 py-2.5 text-xs">{s.cpu_avg_pct != null ? `${s.cpu_avg_pct.toFixed(0)}%` : "—"}</td>
                      <td className="px-3 py-2.5 text-xs">{s.memory_avg_pct != null ? `${s.memory_avg_pct.toFixed(0)}%` : "—"}</td>
                      <td className="px-3 py-2.5 text-xs text-text-muted">{s.login_at ? new Date(s.login_at).toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Team sessions (scoped to team servers) */}
          <div className="card p-0 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-surface-2">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <Activity size={14} className="text-cyan-400" />
                {teamLabel} Sessions ({sessions.length})
              </h3>
              <span className="text-xs text-text-muted">Your sessions highlighted</span>
            </div>
            <div className="overflow-x-auto max-h-72">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-surface/90">
                  <tr className="border-b border-surface-2 text-xs text-text-muted">
                    <th className="text-left px-4 py-2">Server</th>
                    <th className="text-left px-3 py-2">User</th>
                    <th className="text-left px-3 py-2">Type</th>
                    <th className="text-left px-3 py-2">CPU%</th>
                    <th className="text-left px-3 py-2">Login</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.length === 0 ? (
                    <tr><td colSpan={5} className="px-4 py-8 text-center text-text-muted text-sm">No active team sessions</td></tr>
                  ) : sessions.slice(0, 50).map((s: any) => {
                    const isMe = s.username?.toLowerCase() === user.email.split("@")[0].toLowerCase();
                    return (
                      <tr key={s.id} className={`border-b border-surface-2/50 hover:bg-surface-2/40 ${isMe ? "border-l-2 border-l-cyan-500 bg-cyan-500/5" : ""}`}>
                        <td className="px-4 py-2.5 font-mono text-xs">{s.hostname}</td>
                        <td className="px-3 py-2.5 text-xs font-medium">
                          {s.username}
                          {isMe && <span className="ml-1 text-xs text-cyan-400">(you)</span>}
                        </td>
                        <td className="px-3 py-2.5 text-xs text-text-muted">{s.session_type ?? "—"}</td>
                        <td className="px-3 py-2.5 text-xs">{s.cpu_avg_pct != null ? `${s.cpu_avg_pct.toFixed(0)}%` : "—"}</td>
                        <td className="px-3 py-2.5 text-xs text-text-muted">{s.login_at ? new Date(s.login_at).toLocaleString() : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
