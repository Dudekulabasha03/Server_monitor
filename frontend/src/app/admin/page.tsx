"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Users, Shield, Activity, BarChart3, RefreshCw, LogOut, Plus,
  Settings, Calendar, Target, Zap, Server, AlertTriangle,
  CheckCircle2, Clock, Trash2, ChevronRight, WifiOff,
  UserCheck, DollarSign, Database, Save, Info,
} from "lucide-react";
import axios from "axios";
import { useAuthStore, ROLE_LABELS, ROLE_COLORS, UserRole } from "@/lib/auth";
import { RoleGuard } from "@/components/auth/RoleGuard";
import { UserTable } from "@/components/admin/UserTable";
import { AuditLogTable } from "@/components/admin/AuditLogTable";
import { TeamManager } from "@/components/admin/TeamManager";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type TabId = "overview" | "access" | "sla" | "power" | "settings" | "maintenance" | "quotas" | "idle" | "bulk" | "users" | "teams" | "audit";

export default function SuperAdminDashboard() {
  const { user, clearAuth } = useAuthStore();
  const router = useRouter();
  const [tab, setTab] = useState<TabId>("overview");
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  // Data states
  const [dashboard, setDashboard] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [teams, setTeams] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [accessReview, setAccessReview] = useState<any>(null);
  const [sla, setSla] = useState<any>(null);
  const [powerCost, setPowerCost] = useState<any>(null);
  const [globalSettings, setGlobalSettings] = useState<any[]>([]);
  const [settingsEdits, setSettingsEdits] = useState<Record<string, string>>({});
  const [maintenanceWindows, setMaintenanceWindows] = useState<any[]>([]);
  const [quotas, setQuotas] = useState<any[]>([]);
  const [idleServers, setIdleServers] = useState<any[]>([]);
  const [allServers, setAllServers] = useState<any[]>([]);

  // Maintenance form
  const [mwForm, setMwForm] = useState({ name: "", team: "", starts_at: "", ends_at: "", reason: "" });
  const [mwBusy, setMwBusy] = useState(false);

  // Bulk op
  const [selectedServers, setSelectedServers] = useState<Set<string>>(new Set());
  const [bulkOp, setBulkOp] = useState("assign_team");
  const [bulkValue, setBulkValue] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);

  const token = typeof window !== "undefined" ? localStorage.getItem("helios_jwt") : null;
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dash, usersRes, teamsRes, logsRes, accessRes, slaRes, powerRes, settingsRes, mwRes, quotasRes, idleRes, srvRes] =
        await Promise.all([
          axios.get(`${API_BASE}/admin/dashboard`, { headers }),
          axios.get(`${API_BASE}/admin/users?limit=200`, { headers }),
          axios.get(`${API_BASE}/admin/teams`, { headers }),
          axios.get(`${API_BASE}/admin/audit-logs?limit=100`, { headers }),
          axios.get(`${API_BASE}/superadmin/access-review`, { headers }),
          axios.get(`${API_BASE}/superadmin/sla`, { headers }),
          axios.get(`${API_BASE}/superadmin/power-cost`, { headers }),
          axios.get(`${API_BASE}/superadmin/settings`, { headers }),
          axios.get(`${API_BASE}/superadmin/maintenance`, { headers }),
          axios.get(`${API_BASE}/superadmin/quotas`, { headers }),
          axios.get(`${API_BASE}/superadmin/idle-servers`, { headers }),
          axios.get(`${API_BASE}/admin/servers?limit=300`, { headers }),
        ]);
      setDashboard(dash.data);
      setUsers(usersRes.data.users);
      setTeams(teamsRes.data);
      setAuditLogs(logsRes.data.logs);
      setAccessReview(accessRes.data);
      setSla(slaRes.data);
      setPowerCost(powerRes.data);
      setGlobalSettings(settingsRes.data.settings ?? []);
      setSettingsEdits({});
      setMaintenanceWindows(mwRes.data.windows ?? []);
      setQuotas(quotasRes.data.quotas ?? []);
      setIdleServers(idleRes.data.idle_servers ?? []);
      setAllServers(srvRes.data.servers ?? []);
    } catch { if (!token) router.replace("/login"); }
    finally { setLoading(false); }
  }, [token, router]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!user) { router.replace("/login"); return; }
    if (user.role !== "super_admin") { router.replace("/admin-ops"); return; }
    fetchAll();
  }, [user, router, fetchAll]);

  const logout = () => { clearAuth(); router.replace("/login"); };

  const saveSetting = async (key: string) => {
    const value = settingsEdits[key];
    if (!value) return;
    setSavingKey(key);
    try {
      await axios.patch(`${API_BASE}/superadmin/settings/${key}`, { value }, { headers });
      fetchAll();
    } finally { setSavingKey(null); }
  };

  const saveAllSettings = async () => {
    const keys = Object.keys(settingsEdits);
    for (const key of keys) {
      await axios.patch(`${API_BASE}/superadmin/settings/${key}`, { value: settingsEdits[key] }, { headers });
    }
    fetchAll();
  };

  const updateQuota = async (team: string, field: string, value: number) => {
    await axios.patch(`${API_BASE}/superadmin/quotas/${encodeURIComponent(team)}`, { [field]: value }, { headers });
    fetchAll();
  };

  const createMaintenance = async () => {
    if (!mwForm.name || !mwForm.starts_at || !mwForm.ends_at) return;
    setMwBusy(true);
    try {
      await axios.post(`${API_BASE}/superadmin/maintenance`, {
        ...mwForm,
        starts_at: new Date(mwForm.starts_at).toISOString(),
        ends_at: new Date(mwForm.ends_at).toISOString(),
        team: mwForm.team || null,
      }, { headers });
      setMwForm({ name: "", team: "", starts_at: "", ends_at: "", reason: "" });
      fetchAll();
    } finally { setMwBusy(false); }
  };

  const cancelMaintenance = async (id: string) => {
    await axios.delete(`${API_BASE}/superadmin/maintenance/${id}`, { headers });
    fetchAll();
  };

  const doBulkOp = async () => {
    if (!selectedServers.size || !bulkValue) return;
    setBulkBusy(true);
    try {
      await axios.post(`${API_BASE}/superadmin/servers/bulk`,
        { server_ids: Array.from(selectedServers), operation: bulkOp, value: bulkValue },
        { headers }
      );
      setSelectedServers(new Set());
      setBulkValue("");
      fetchAll();
    } finally { setBulkBusy(false); }
  };

  if (!user || user.role !== "super_admin") return null;

  const stats = dashboard?.users as any;
  const teamDist = (dashboard?.team_distribution as any[]) ?? [];
  const recentActivity = (dashboard?.recent_activity as any[]) ?? [];

  const TABS: { id: TabId; label: string; icon: React.ElementType; badge?: number }[] = [
    { id: "overview",    label: "Overview",       icon: BarChart3 },
    { id: "access",      label: "Access Review",  icon: UserCheck, badge: accessReview?.inactive_count || undefined },
    { id: "sla",         label: "SLA",            icon: Target,    badge: sla?.breaching || undefined },
    { id: "power",       label: "Power Cost",     icon: Zap },
    { id: "settings",    label: "Settings",       icon: Settings },
    { id: "maintenance", label: "Maintenance",    icon: Calendar },
    { id: "quotas",      label: "Quotas",         icon: Database },
    { id: "idle",        label: "Idle Servers",   icon: WifiOff,   badge: idleServers.length || undefined },
    { id: "bulk",        label: "Bulk Ops",       icon: Server },
    { id: "users",       label: "Users",          icon: Users },
    { id: "teams",       label: "Teams",          icon: Shield },
    { id: "audit",       label: "Audit Logs",     icon: Activity },
  ];

  const TEAM_OPTIONS = ["Security Patch Team", "TSP", "DPDK", "Performance", "AI", "Cloud"];

  return (
    <RoleGuard roles={["super_admin"]}>
      <div className="min-h-screen bg-background text-text-primary">
        {/* Header */}
        <div className="border-b border-surface-2 bg-surface/50 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "linear-gradient(135deg, #f59e0b, #ED1C24)" }}>
                <span className="text-white font-bold">☀</span>
              </div>
              <div>
                <h1 className="font-bold">Helios — Super Admin</h1>
                <p className="text-xs text-text-muted">Full platform governance & operations</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className="text-sm font-medium">{user.full_name}</p>
                <span className={`text-xs px-2 py-0.5 rounded-full border ${ROLE_COLORS[user.role as UserRole]}`}>
                  {ROLE_LABELS[user.role as UserRole]}
                </span>
              </div>
              <button onClick={logout} className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-surface-2 rounded-lg hover:bg-surface-2">
                <LogOut size={13} /> Logout
              </button>
            </div>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
          {/* Tabs — scrollable */}
          <div className="flex items-center gap-1 bg-surface border border-surface-2 rounded-xl p-1 overflow-x-auto">
            {TABS.map((t) => {
              const Icon = t.icon;
              return (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                    tab === t.id ? "bg-blue-600/20 text-blue-400 border border-blue-600/30" : "text-text-secondary hover:bg-surface-2"
                  }`}>
                  <Icon size={14} /> {t.label}
                  {t.badge ? <span className="ml-1 bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full min-w-[18px] text-center">{t.badge}</span> : null}
                </button>
              );
            })}
            <button onClick={fetchAll} className="ml-auto p-2 text-text-muted hover:text-text-primary flex-shrink-0">
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            </button>
          </div>

          {/* ── OVERVIEW ── */}
          {tab === "overview" && (
            <div className="space-y-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: "Total Users",   value: stats?.total ?? "—",   color: "text-cyan-400" },
                  { label: "Active Users",  value: stats?.active ?? "—",  color: "text-green-400" },
                  { label: "Teams",         value: dashboard?.teams_count ?? "—", color: "text-amber-400" },
                  { label: "SLA Breaching", value: sla?.breaching ?? "—", color: sla?.breaching > 0 ? "text-red-400" : "text-green-400" },
                ].map((c) => (
                  <div key={c.label} className="bg-surface border border-surface-2 rounded-xl p-4">
                    <p className="text-xs text-text-muted">{c.label}</p>
                    <p className={`text-3xl font-bold mt-1 ${c.color}`}>{c.value as string}</p>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-surface border border-surface-2 rounded-xl p-4">
                  <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><Users size={13} className="text-cyan-400" /> Team Distribution</h3>
                  {teamDist.map((t: any) => (
                    <div key={t.team} className="flex items-center justify-between mb-2">
                      <span className="text-xs text-text-secondary">{t.team}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-20 bg-surface-2 rounded-full h-1">
                          <div className="h-1 rounded-full bg-cyan-500" style={{ width: `${Math.min(100, (t.count / (stats?.total || 1)) * 100)}%` }} />
                        </div>
                        <span className="text-xs text-cyan-400 w-4">{t.count}</span>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="bg-surface border border-surface-2 rounded-xl p-4">
                  <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><Activity size={13} className="text-cyan-400" /> Recent Activity</h3>
                  <div className="space-y-1.5">
                    {recentActivity.slice(0, 8).map((a: any, i: number) => (
                      <div key={i} className="flex items-center justify-between text-xs">
                        <span className="text-text-muted truncate max-w-[120px]">{a.username ?? "—"}</span>
                        <span className="text-amber-400">{a.action?.replace(/_/g, " ")}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-surface border border-surface-2 rounded-xl p-4">
                  <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><DollarSign size={13} className="text-amber-400" /> Power Cost (est.)</h3>
                  <p className={`text-3xl font-bold text-amber-400`}>${powerCost?.fleet_monthly_cost_usd?.toFixed(0) ?? "—"}</p>
                  <p className="text-xs text-text-muted mt-1">estimated monthly ({powerCost?.fleet_total_watts?.toFixed(0) ?? "—"}W total)</p>
                  <p className="text-xs text-text-muted/60 mt-1">${powerCost?.cost_per_kwh ?? "0.10"}/kWh</p>
                </div>
              </div>
            </div>
          )}

          {/* ── ACCESS REVIEW ── */}
          {tab === "access" && accessReview && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-semibold">Access Review</h2>
                  <p className="text-xs text-text-muted mt-0.5">
                    {accessReview.inactive_count} users inactive for {accessReview.inactive_threshold_days}+ days
                  </p>
                </div>
              </div>

              <div className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-surface-2 text-xs text-text-muted">
                      <th className="text-left px-4 py-3">User</th>
                      <th className="text-left px-3 py-3">Role</th>
                      <th className="text-left px-3 py-3">Team</th>
                      <th className="text-left px-3 py-3">Last Login</th>
                      <th className="text-left px-3 py-3">Reservations</th>
                      <th className="text-left px-3 py-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(accessReview.users as any[]).map((u: any) => (
                      <tr key={u.id} className={`border-b border-surface-2/50 hover:bg-surface-2/30 ${u.inactive ? "border-l-2 border-l-amber-400/40" : ""}`}>
                        <td className="px-4 py-2.5">
                          <p className="text-sm font-medium">{u.full_name}</p>
                          <p className="text-xs text-text-muted">{u.email}</p>
                        </td>
                        <td className="px-3 py-2.5 text-xs">{u.role}</td>
                        <td className="px-3 py-2.5 text-xs text-text-muted">{u.team ?? "—"}</td>
                        <td className="px-3 py-2.5 text-xs">
                          {u.last_login_at ? (
                            <div>
                              <p>{new Date(u.last_login_at).toLocaleDateString()}</p>
                              <p className={`${u.inactive ? "text-amber-400" : "text-text-muted/60"}`}>
                                {u.days_since_login != null ? `${u.days_since_login}d ago` : "—"}
                              </p>
                            </div>
                          ) : <span className="text-red-400">Never</span>}
                        </td>
                        <td className="px-3 py-2.5 text-xs">
                          <p className="text-cyan-400">{u.reservations.total} total</p>
                          <p className="text-text-muted/60">{u.reservations.active} active</p>
                        </td>
                        <td className="px-3 py-2.5">
                          {u.inactive ? (
                            <span className="text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 px-2 py-0.5 rounded-full">Inactive</span>
                          ) : (
                            <span className="text-xs text-green-400 bg-green-400/10 border border-green-400/20 px-2 py-0.5 rounded-full">Active</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── SLA ── */}
          {tab === "sla" && sla && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-semibold">Fleet Health SLA</h2>
                  <p className="text-xs text-text-muted mt-0.5">Target: {sla.sla_target_pct}% healthy per team</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-green-400">{sla.compliant} teams compliant</span>
                  {sla.breaching > 0 && <span className="text-xs text-red-400 bg-red-400/10 border border-red-400/20 px-2 py-0.5 rounded-full">{sla.breaching} breaching</span>}
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(sla.teams as any[]).filter((t: any) => t.total > 0).map((t: any) => (
                  <div key={t.team} className={`bg-surface border rounded-xl p-4 ${!t.sla_met ? "border-red-400/30" : "border-surface-2"}`}>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold">{t.team ?? "Unassigned"}</h3>
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${t.sla_met ? "text-green-400 bg-green-400/10 border-green-400/20" : "text-red-400 bg-red-400/10 border-red-400/20"}`}>
                        {t.sla_met ? "SLA Met" : `${t.sla_gap}% below SLA`}
                      </span>
                    </div>
                    <div className="space-y-2">
                      <div className="flex justify-between text-xs">
                        <span className="text-text-muted">Healthy</span>
                        <span className={t.sla_met ? "text-green-400" : "text-red-400"}>{t.healthy_pct}%</span>
                      </div>
                      <div className="w-full bg-surface-2 rounded-full h-2">
                        <div className={`h-2 rounded-full ${t.sla_met ? "bg-green-500" : "bg-red-500"}`}
                          style={{ width: `${Math.min(100, t.healthy_pct)}%` }} />
                        <div className="relative">
                          <div className="absolute top-0 w-px h-2 bg-amber-400 opacity-60"
                            style={{ left: `${sla.sla_target_pct}%`, marginTop: "-8px" }} />
                        </div>
                      </div>
                      <div className="flex justify-between text-xs text-text-muted">
                        <span>{t.healthy}/{t.total} servers healthy</span>
                        <span>avg {t.avg_health}/100</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── POWER COST ── */}
          {tab === "power" && powerCost && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                {[
                  { label: "Fleet Total Power", value: `${powerCost.fleet_total_watts?.toFixed(0)}W`, color: "text-amber-400" },
                  { label: "Monthly Cost (est.)", value: `$${powerCost.fleet_monthly_cost_usd?.toFixed(0)}`, color: "text-red-400" },
                  { label: "Rate", value: `$${powerCost.cost_per_kwh}/kWh`, color: "text-text-muted" },
                ].map((c) => (
                  <div key={c.label} className="bg-surface border border-surface-2 rounded-xl p-4">
                    <p className="text-xs text-text-muted">{c.label}</p>
                    <p className={`text-2xl font-bold mt-1 ${c.color}`}>{c.value}</p>
                  </div>
                ))}
              </div>
              <div className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-surface-2">
                  <h3 className="text-sm font-medium">Power Cost by Team</h3>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-surface-2 text-xs text-text-muted">
                      <th className="text-left px-4 py-2">Team</th>
                      <th className="text-left px-3 py-2">Servers</th>
                      <th className="text-left px-3 py-2">Total Watts</th>
                      <th className="text-left px-3 py-2">Daily kWh</th>
                      <th className="text-left px-3 py-2">Daily Cost</th>
                      <th className="text-left px-3 py-2">Monthly Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(powerCost.teams as any[]).filter((t: any) => t.total_watts > 0).map((t: any) => (
                      <tr key={t.team} className="border-b border-surface-2/50 hover:bg-surface-2/30">
                        <td className="px-4 py-2.5 text-xs font-medium">{t.team ?? "Unknown"}</td>
                        <td className="px-3 py-2.5 text-xs text-text-muted">{t.servers}</td>
                        <td className="px-3 py-2.5 text-xs text-amber-400">{t.total_watts.toFixed(0)}W</td>
                        <td className="px-3 py-2.5 text-xs text-text-muted">{t.daily_kwh} kWh</td>
                        <td className="px-3 py-2.5 text-xs">${t.daily_cost_usd}</td>
                        <td className="px-3 py-2.5 text-xs font-semibold text-red-400">${t.monthly_cost_usd}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="bg-surface/50 border border-surface-2 rounded-xl px-4 py-3 flex items-start gap-2 text-xs text-text-muted">
                <Info size={13} className="flex-shrink-0 mt-0.5 text-cyan-400" />
                <span>Update the electricity rate in Settings → power_cost_kwh to match your facility cost. Power data sourced from live BMC readings.</span>
              </div>
            </div>
          )}

          {/* ── GLOBAL SETTINGS ── */}
          {tab === "settings" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold">Global Platform Settings</h2>
                {Object.keys(settingsEdits).length > 0 && (
                  <button onClick={saveAllSettings}
                    className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors">
                    <Save size={13} /> Save All ({Object.keys(settingsEdits).length} changed)
                  </button>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {globalSettings.map((s: any) => {
                  const isEdited = s.key in settingsEdits;
                  return (
                    <div key={s.key} className={`bg-surface border rounded-xl p-4 ${isEdited ? "border-cyan-500/40" : "border-surface-2"}`}>
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <p className="text-xs font-mono font-semibold text-cyan-400">{s.key}</p>
                          <p className="text-xs text-text-muted mt-0.5">{s.description}</p>
                        </div>
                        {isEdited && (
                          <button onClick={() => saveSetting(s.key)} disabled={savingKey === s.key}
                            className="text-xs bg-cyan-600/20 border border-cyan-600/30 text-cyan-400 px-2 py-0.5 rounded hover:bg-cyan-600/30 transition-colors">
                            {savingKey === s.key ? "..." : "Save"}
                          </button>
                        )}
                      </div>
                      <input
                        value={settingsEdits[s.key] ?? s.value}
                        onChange={(e) => setSettingsEdits((prev) => ({ ...prev, [s.key]: e.target.value }))}
                        className={`w-full text-sm font-mono bg-background border rounded-lg px-3 py-2 focus:outline-none ${
                          isEdited ? "border-cyan-500 text-cyan-400" : "border-surface-2"
                        }`}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── MAINTENANCE WINDOWS ── */}
          {tab === "maintenance" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Create form */}
              <div className="bg-surface border border-surface-2 rounded-xl p-4 space-y-3">
                <h3 className="text-sm font-semibold flex items-center gap-2"><Plus size={14} className="text-cyan-400" /> Schedule Maintenance</h3>
                <div>
                  <label className="text-xs text-text-muted mb-1 block">Window Name *</label>
                  <input value={mwForm.name} onChange={(e) => setMwForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="e.g. Security Patch Team BIOS Upgrade"
                    className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500" />
                </div>
                <div>
                  <label className="text-xs text-text-muted mb-1 block">Team (leave blank for all)</label>
                  <select value={mwForm.team} onChange={(e) => setMwForm((f) => ({ ...f, team: e.target.value }))}
                    className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500">
                    <option value="">All teams</option>
                    {TEAM_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs text-text-muted mb-1 block">Start *</label>
                    <input type="datetime-local" value={mwForm.starts_at} onChange={(e) => setMwForm((f) => ({ ...f, starts_at: e.target.value }))}
                      className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-cyan-500" />
                  </div>
                  <div>
                    <label className="text-xs text-text-muted mb-1 block">End *</label>
                    <input type="datetime-local" value={mwForm.ends_at} onChange={(e) => setMwForm((f) => ({ ...f, ends_at: e.target.value }))}
                      className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-cyan-500" />
                  </div>
                </div>
                <div>
                  <label className="text-xs text-text-muted mb-1 block">Reason</label>
                  <textarea value={mwForm.reason} onChange={(e) => setMwForm((f) => ({ ...f, reason: e.target.value }))}
                    rows={2} placeholder="Why this maintenance window..."
                    className="w-full bg-background border border-surface-2 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500 resize-none" />
                </div>
                <button onClick={createMaintenance} disabled={mwBusy}
                  className="w-full flex items-center justify-center gap-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold px-4 py-2.5 rounded-lg disabled:opacity-50 transition-colors">
                  <Calendar size={14} /> Schedule Window
                </button>
              </div>

              {/* Existing windows */}
              <div className="bg-surface border border-surface-2 rounded-xl p-4">
                <h3 className="text-sm font-semibold mb-4">Scheduled Windows ({maintenanceWindows.length})</h3>
                {maintenanceWindows.length === 0 ? (
                  <div className="text-center py-8 text-text-muted text-sm">No maintenance windows scheduled</div>
                ) : (
                  <div className="space-y-3 max-h-96 overflow-y-auto">
                    {maintenanceWindows.map((w: any) => {
                      const now = new Date();
                      const start = new Date(w.starts_at);
                      const end = new Date(w.ends_at);
                      const active = start <= now && end >= now;
                      const future = start > now;
                      return (
                        <div key={w.id} className={`border rounded-xl p-3 ${active ? "border-amber-400/40 bg-amber-400/5" : future ? "border-surface-2" : "border-surface-2 opacity-50"}`}>
                          <div className="flex items-start justify-between">
                            <div>
                              <p className="text-sm font-medium">{w.name}</p>
                              <p className="text-xs text-text-muted">{w.team ?? "All teams"}</p>
                              <p className="text-xs text-text-muted mt-1">
                                {new Date(w.starts_at).toLocaleString()} → {new Date(w.ends_at).toLocaleString()}
                              </p>
                              {w.reason && <p className="text-xs text-text-muted/70 mt-0.5">{w.reason}</p>}
                            </div>
                            <div className="flex items-center gap-2">
                              {active && <span className="text-xs text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full border border-amber-400/20">Active</span>}
                              {w.is_active && (
                                <button onClick={() => cancelMaintenance(w.id)}
                                  className="text-red-400 hover:text-red-300 p-1 hover:bg-red-400/10 rounded transition-colors">
                                  <Trash2 size={12} />
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── TEAM QUOTAS ── */}
          {tab === "quotas" && (
            <div className="space-y-4">
              <h2 className="font-semibold">Team Reservation Quotas</h2>
              <div className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-surface-2 text-xs text-text-muted">
                      <th className="text-left px-4 py-3">Team</th>
                      <th className="text-left px-3 py-3">Max Reservations</th>
                      <th className="text-left px-3 py-3">Currently Active</th>
                      <th className="text-left px-3 py-3">Available</th>
                      <th className="text-left px-3 py-3">Max Hours per Reservation</th>
                      <th className="text-left px-3 py-3">Save</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quotas.map((q: any) => (
                      <tr key={q.team} className="border-b border-surface-2/50">
                        <td className="px-4 py-3 text-sm font-medium">{q.team}</td>
                        <td className="px-3 py-3">
                          <input type="number" min={1} max={50} defaultValue={q.max_reservations}
                            id={`max-res-${q.team}`}
                            className="w-20 text-xs bg-background border border-surface-2 rounded px-2 py-1 focus:outline-none focus:border-cyan-500" />
                        </td>
                        <td className="px-3 py-3 text-xs">
                          <span className={q.current_usage >= q.max_reservations ? "text-red-400" : "text-text-muted"}>
                            {q.current_usage}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-xs text-green-400">{q.available}</td>
                        <td className="px-3 py-3">
                          <input type="number" min={1} max={720} defaultValue={q.max_reservation_hours}
                            id={`max-hrs-${q.team}`}
                            className="w-20 text-xs bg-background border border-surface-2 rounded px-2 py-1 focus:outline-none focus:border-cyan-500" />
                        </td>
                        <td className="px-3 py-3">
                          <button onClick={() => {
                            const res = (document.getElementById(`max-res-${q.team}`) as HTMLInputElement)?.valueAsNumber;
                            const hrs = (document.getElementById(`max-hrs-${q.team}`) as HTMLInputElement)?.valueAsNumber;
                            updateQuota(q.team, "max_reservations", res);
                            updateQuota(q.team, "max_reservation_hours", hrs);
                          }}
                            className="text-xs bg-cyan-600/20 border border-cyan-600/30 text-cyan-400 px-2 py-1 rounded hover:bg-cyan-600/30 transition-colors">
                            Save
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── IDLE SERVERS ── */}
          {tab === "idle" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-semibold">Idle Servers — Reclamation Candidates</h2>
                  <p className="text-xs text-text-muted mt-0.5">
                    {idleServers.length} servers with CPU &lt;5% and no active reservation
                  </p>
                </div>
              </div>
              <div className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-surface-2 text-xs text-text-muted">
                      <th className="text-left px-4 py-3">Server</th>
                      <th className="text-left px-3 py-3">Team</th>
                      <th className="text-left px-3 py-3">Family</th>
                      <th className="text-left px-3 py-3">DC</th>
                      <th className="text-left px-3 py-3">CPU%</th>
                      <th className="text-left px-3 py-3">Health</th>
                      <th className="text-left px-3 py-3">Last Seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {idleServers.slice(0, 50).map((s: any) => (
                      <tr key={s.id} className="border-b border-surface-2/50 hover:bg-surface-2/30">
                        <td className="px-4 py-2.5 font-mono text-xs">{s.hostname}</td>
                        <td className="px-3 py-2.5 text-xs text-text-muted">{s.team ?? "—"}</td>
                        <td className="px-3 py-2.5 text-xs text-text-muted">{s.family ?? "—"}</td>
                        <td className="px-3 py-2.5 text-xs text-text-muted">{s.datacenter ?? "—"}</td>
                        <td className="px-3 py-2.5 text-xs">{s.cpu_usage_avg != null ? `${s.cpu_usage_avg.toFixed(1)}%` : "—"}</td>
                        <td className="px-3 py-2.5 text-xs">{s.health_score != null ? `${s.health_score}/100` : "—"}</td>
                        <td className="px-3 py-2.5 text-xs text-text-muted">{s.last_seen ? new Date(s.last_seen).toLocaleDateString() : "—"}</td>
                      </tr>
                    ))}
                    {idleServers.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-text-muted text-sm">No idle servers</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── BULK OPS ── */}
          {tab === "bulk" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold">Bulk Server Operations</h2>
                {selectedServers.size > 0 && (
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-cyan-400">{selectedServers.size} selected</span>
                    <select value={bulkOp} onChange={(e) => setBulkOp(e.target.value)}
                      className="text-xs bg-background border border-surface-2 rounded-lg px-2 py-1.5 focus:outline-none">
                      <option value="assign_team">Assign Team</option>
                      <option value="set_environment">Set Environment</option>
                      <option value="set_bios_baseline">Set BIOS Baseline</option>
                    </select>
                    <input value={bulkValue} onChange={(e) => setBulkValue(e.target.value)}
                      placeholder={bulkOp === "assign_team" ? "Team name..." : bulkOp === "set_environment" ? "dev / staging / production" : "BIOS version..."}
                      className="text-xs bg-background border border-surface-2 rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500 w-48" />
                    <button onClick={doBulkOp} disabled={bulkBusy || !bulkValue}
                      className="text-xs bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1.5 rounded-lg disabled:opacity-50 transition-colors">
                      Apply to {selectedServers.size} servers
                    </button>
                    <button onClick={() => setSelectedServers(new Set())} className="text-xs text-text-muted hover:text-text-primary">Clear</button>
                  </div>
                )}
              </div>

              <div className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-surface-2 flex items-center gap-3">
                  <input type="checkbox" checked={selectedServers.size === allServers.length && allServers.length > 0}
                    onChange={(e) => setSelectedServers(e.target.checked ? new Set(allServers.map((s: any) => s.id)) : new Set())}
                    className="rounded" />
                  <span className="text-xs text-text-muted">Select all ({allServers.length} servers)</span>
                </div>
                <div className="overflow-x-auto max-h-96">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-surface/90">
                      <tr className="border-b border-surface-2 text-xs text-text-muted">
                        <th className="text-left px-4 py-2">Select</th>
                        <th className="text-left px-3 py-2">Hostname</th>
                        <th className="text-left px-3 py-2">Team</th>
                        <th className="text-left px-3 py-2">Family</th>
                        <th className="text-left px-3 py-2">DC</th>
                        <th className="text-left px-3 py-2">Environment</th>
                        <th className="text-left px-3 py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {allServers.slice(0, 100).map((s: any) => (
                        <tr key={s.id} className={`border-b border-surface-2/50 hover:bg-surface-2/30 ${selectedServers.has(s.id) ? "bg-cyan-500/5" : ""}`}>
                          <td className="px-4 py-2">
                            <input type="checkbox" checked={selectedServers.has(s.id)}
                              onChange={(e) => {
                                const next = new Set(selectedServers);
                                e.target.checked ? next.add(s.id) : next.delete(s.id);
                                setSelectedServers(next);
                              }} className="rounded" />
                          </td>
                          <td className="px-3 py-2 font-mono text-xs">{s.hostname}</td>
                          <td className="px-3 py-2 text-xs text-text-muted">{s.team ?? "—"}</td>
                          <td className="px-3 py-2 text-xs text-text-muted">{s.family ?? "—"}</td>
                          <td className="px-3 py-2 text-xs text-text-muted">{s.datacenter ?? "—"}</td>
                          <td className="px-3 py-2 text-xs text-text-muted">{s.environment ?? "—"}</td>
                          <td className="px-3 py-2 text-xs">
                            <span className={s.status === "healthy" ? "text-green-400" : s.status === "critical" ? "text-red-400" : "text-amber-400"}>{s.status}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {allServers.length > 100 && <p className="text-xs text-text-muted text-center py-3">Showing 100 of {allServers.length}</p>}
                </div>
              </div>
            </div>
          )}

          {/* ── USERS ── */}
          {tab === "users" && (
            <div className="space-y-3">
              <h2 className="font-semibold">User Management</h2>
              <UserTable users={users} currentUserRole="super_admin" onRefresh={fetchAll} />
            </div>
          )}

          {/* ── TEAMS ── */}
          {tab === "teams" && (
            <div className="bg-surface border border-surface-2 rounded-xl p-4">
              <TeamManager teams={teams} onRefresh={fetchAll} />
            </div>
          )}

          {/* ── AUDIT ── */}
          {tab === "audit" && (
            <div className="space-y-3">
              <h2 className="font-semibold">Audit Logs</h2>
              <AuditLogTable logs={auditLogs} />
            </div>
          )}
        </div>
      </div>
    </RoleGuard>
  );
}
