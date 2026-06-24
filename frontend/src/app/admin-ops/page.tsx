"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Users, BarChart3, Activity, RefreshCw, LogOut, LayoutDashboard,
  Server, AlertTriangle, CheckCircle2, Calendar, ClipboardList,
  UserCheck, UserX, Trash2, Shield, ChevronRight,
} from "lucide-react";
import Link from "next/link";
import axios from "axios";
import { useAuthStore, ROLE_LABELS, ROLE_COLORS, UserRole } from "@/lib/auth";
import { RoleGuard } from "@/components/auth/RoleGuard";
import { UserTable } from "@/components/admin/UserTable";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type TabId = "overview" | "pending" | "servers" | "reservations" | "report" | "users" | "activity";

export default function AdminOpsDashboard() {
  const { user, clearAuth } = useAuthStore();
  const router = useRouter();
  const [tab, setTab] = useState<TabId>("overview");
  const [dashboard, setDashboard] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [activity, setActivity] = useState<any[]>([]);
  const [teamServers, setTeamServers] = useState<Record<string, any[]>>({});
  const [fleetSummary, setFleetSummary] = useState<any>(null);
  const [pendingUsers, setPendingUsers] = useState<any[]>([]);
  const [reservations, setReservations] = useState<any[]>([]);
  const [usageReport, setUsageReport] = useState<any>(null);
  const [allServers, setAllServers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const token = typeof window !== "undefined" ? localStorage.getItem("helios_jwt") : null;
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dash, usersRes, actRes, summaryRes, pendingRes, resRes, reportRes, srvRes] = await Promise.all([
        axios.get(`${API_BASE}/admin/dashboard`, { headers }),
        axios.get(`${API_BASE}/admin/users?limit=100`, { headers }),
        axios.get(`${API_BASE}/admin/user-activity`, { headers }),
        axios.get(`${API_BASE}/api/v1/servers/summary`, { headers }),
        axios.get(`${API_BASE}/admin/pending-users`, { headers }),
        axios.get(`${API_BASE}/admin/reservations?active_only=false&limit=200`, { headers }),
        axios.get(`${API_BASE}/admin/usage-report?days=7`, { headers }),
        axios.get(`${API_BASE}/admin/servers?limit=300`, { headers }),
      ]);
      setDashboard(dash.data);
      setUsers(usersRes.data.users);
      setActivity(actRes.data.activity);
      setFleetSummary(summaryRes.data);
      setPendingUsers(pendingRes.data.pending ?? []);
      setReservations(resRes.data.reservations ?? []);
      setUsageReport(reportRes.data);
      setAllServers(srvRes.data.servers ?? []);

      const teamNames = ["Security Patch Team", "TSP", "DPDK", "Performance", "AI", "Cloud"];
      const results = await Promise.all(
        teamNames.map((t) => axios.get(`${API_BASE}/api/v1/servers?team=${encodeURIComponent(t)}&page_size=200`, { headers }))
      );
      const grouped: Record<string, any[]> = {};
      teamNames.forEach((t, i) => {
        const d = results[i].data;
        grouped[t] = Array.isArray(d) ? d : (d.servers ?? []);
      });
      setTeamServers(grouped);
    } catch { if (!token) router.replace("/login"); }
    finally { setLoading(false); }
  }, [token, router]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!user) { router.replace("/login"); return; }
    if (user.role === "user") { router.replace("/user-home"); return; }
    fetchAll();
  }, [user, router, fetchAll]);

  const logout = () => { clearAuth(); router.replace("/login"); };

  const approveUser = async (userId: string, action: "approve" | "reject", role = "user") => {
    setBusy(userId);
    try {
      await axios.post(`${API_BASE}/admin/users/${userId}/approve`, { action, role }, { headers });
      fetchAll();
    } finally { setBusy(null); }
  };

  const forceRelease = async (reservationId: string) => {
    setBusy(reservationId);
    try {
      await axios.delete(`${API_BASE}/admin/reservations/${reservationId}`, { headers });
      fetchAll();
    } finally { setBusy(null); }
  };

  const assignTeam = async (serverId: string, team: string) => {
    try {
      await axios.patch(`${API_BASE}/admin/servers/${serverId}/team`, { team }, { headers });
      fetchAll();
    } catch (e: any) { alert(e.response?.data?.detail || "Failed"); }
  };

  if (!user) return null;

  const stats = dashboard?.users as any;
  const teamDist = (dashboard?.team_distribution as any[]) ?? [];

  const TABS: { id: TabId; label: string; icon: React.ElementType; badge?: number }[] = [
    { id: "overview",     label: "Overview",     icon: BarChart3 },
    { id: "pending",      label: "Approvals",    icon: UserCheck, badge: pendingUsers.length || undefined },
    { id: "servers",      label: "Team Servers", icon: Server },
    { id: "reservations", label: "Reservations", icon: Calendar, badge: reservations.filter(r => r.is_active).length || undefined },
    { id: "report",       label: "Usage Report", icon: ClipboardList },
    { id: "users",        label: "Users",        icon: Users },
    { id: "activity",     label: "Activity",     icon: Activity },
  ];

  return (
    <RoleGuard minRole="admin">
      <div className="min-h-screen bg-background text-text-primary">
        {/* Header */}
        <div className="border-b border-surface-2 bg-surface/50 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "linear-gradient(135deg, #f59e0b, #ED1C24)" }}>
                <span className="text-white font-bold">☀</span>
              </div>
              <div>
                <h1 className="font-bold">Helios — Admin Operations</h1>
                <p className="text-xs text-text-muted">Fleet Operations · User Management · Oversight</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Link href="/" className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-surface-2 rounded-lg hover:bg-surface-2 transition-colors">
                <LayoutDashboard size={13} /> Fleet
              </Link>
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
          {/* Tabs */}
          <div className="flex items-center gap-1 bg-surface border border-surface-2 rounded-xl p-1 overflow-x-auto">
            {TABS.map((t) => {
              const Icon = t.icon;
              return (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                    tab === t.id ? "bg-blue-600/20 text-blue-400 border border-blue-600/30" : "text-text-secondary hover:bg-surface-2"
                  }`}>
                  <Icon size={14} /> {t.label}
                  {t.badge ? <span className="ml-1 bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">{t.badge}</span> : null}
                </button>
              );
            })}
            <button onClick={fetchAll} className="ml-auto p-2 text-text-muted hover:text-text-primary">
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            </button>
          </div>

          {/* ── OVERVIEW ── */}
          {tab === "overview" && (
            <div className="space-y-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: "Total Servers",  value: fleetSummary?.total ?? "—",   color: "text-cyan-400" },
                  { label: "Healthy",        value: fleetSummary?.healthy ?? "—", color: "text-green-400" },
                  { label: "Registered Users", value: stats?.total ?? "—",        color: "text-blue-400" },
                  { label: "Pending Approval", value: pendingUsers.length,        color: pendingUsers.length > 0 ? "text-amber-400" : "text-text-muted" },
                ].map((c) => (
                  <div key={c.label} className="bg-surface border border-surface-2 rounded-xl p-4">
                    <p className="text-xs text-text-muted">{c.label}</p>
                    <p className={`text-3xl font-bold mt-1 ${c.color}`}>{c.value as string}</p>
                  </div>
                ))}
              </div>

              {/* Team server health matrix */}
              <div className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-surface-2">
                  <h3 className="text-sm font-medium flex items-center gap-2"><Server size={14} className="text-cyan-400" /> Server Health by Team</h3>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-surface-2 text-xs text-text-muted">
                      <th className="text-left px-4 py-2">Team</th>
                      <th className="text-left px-3 py-2">Total</th>
                      <th className="text-left px-3 py-2">Healthy</th>
                      <th className="text-left px-3 py-2">Warning/Risk</th>
                      <th className="text-left px-3 py-2">Critical</th>
                      <th className="text-left px-3 py-2">Offline</th>
                      <th className="text-left px-3 py-2">Avg Health</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(teamServers).filter(([,s]) => s.length > 0).map(([team, srvs]) => {
                      const c = srvs.reduce((a:any,s:any) => { a[s.status]=(a[s.status]||0)+1; return a; }, {});
                      const avg = Math.round(srvs.filter((s:any)=>s.health_score!=null).reduce((a:any,s:any)=>a+s.health_score,0)/(srvs.filter((s:any)=>s.health_score!=null).length||1));
                      return (
                        <tr key={team} className={`border-b border-surface-2/50 hover:bg-surface-2/30 ${(c.critical||0)>0?"border-l-2 border-l-red-400/50":""}`}>
                          <td className="px-4 py-2.5 text-xs font-medium">{team}</td>
                          <td className="px-3 py-2.5 text-xs text-cyan-400 font-bold">{srvs.length}</td>
                          <td className="px-3 py-2.5 text-xs text-green-400">{c.healthy??0}</td>
                          <td className="px-3 py-2.5 text-xs text-amber-400">{(c.warning??0)+(c.at_risk??0)}</td>
                          <td className="px-3 py-2.5 text-xs text-red-400">{c.critical??0}</td>
                          <td className="px-3 py-2.5 text-xs text-gray-400">{c.offline??0}</td>
                          <td className="px-3 py-2.5 text-xs">
                            <span className={avg>=80?"text-green-400":avg>=60?"text-amber-400":"text-red-400"}>{avg}/100</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* User team distribution */}
              <div className="bg-surface border border-surface-2 rounded-xl p-4">
                <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><Users size={14} className="text-cyan-400" /> Registered Users by Team</h3>
                {teamDist.map((t:any) => (
                  <div key={t.team} className="flex items-center justify-between mb-2">
                    <span className="text-sm text-text-secondary">{t.team}</span>
                    <div className="flex items-center gap-3">
                      <div className="w-32 bg-surface-2 rounded-full h-1.5">
                        <div className="h-1.5 rounded-full bg-cyan-500" style={{width:`${Math.min(100,(t.count/(stats?.total||1))*100)}%`}} />
                      </div>
                      <span className="text-sm text-cyan-400 w-4">{t.count}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── PENDING APPROVALS ── */}
          {tab === "pending" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold flex items-center gap-2">
                  <UserCheck size={16} className="text-amber-400" /> Pending Approvals ({pendingUsers.length})
                </h2>
              </div>
              {pendingUsers.length === 0 ? (
                <div className="bg-surface border border-surface-2 rounded-xl py-12 text-center text-text-muted">
                  <CheckCircle2 size={32} className="mx-auto mb-2 text-green-400 opacity-60" />
                  <p className="text-sm">No pending approvals</p>
                </div>
              ) : (
                <div className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-surface-2 text-xs text-text-muted">
                        <th className="text-left px-4 py-3">User</th>
                        <th className="text-left px-3 py-3">Team Requested</th>
                        <th className="text-left px-3 py-3">Registered</th>
                        <th className="text-left px-3 py-3">Approve As</th>
                        <th className="text-left px-3 py-3">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pendingUsers.map((u: any) => (
                        <tr key={u.id} className="border-b border-surface-2/50 hover:bg-surface-2/40">
                          <td className="px-4 py-3">
                            <p className="font-medium text-sm">{u.full_name}</p>
                            <p className="text-xs text-text-muted">{u.email}</p>
                          </td>
                          <td className="px-3 py-3 text-xs">{u.team_name ?? "—"}</td>
                          <td className="px-3 py-3 text-xs text-text-muted">
                            {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                          </td>
                          <td className="px-3 py-3">
                            <select id={`role-${u.id}`} defaultValue="user"
                              className="text-xs bg-background border border-surface-2 rounded px-2 py-1 focus:outline-none">
                              <option value="user">User</option>
                              <option value="admin">Admin</option>
                            </select>
                          </td>
                          <td className="px-3 py-3">
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => {
                                  const sel = document.getElementById(`role-${u.id}`) as HTMLSelectElement;
                                  approveUser(u.id, "approve", sel?.value || "user");
                                }}
                                disabled={busy === u.id}
                                className="flex items-center gap-1 px-2.5 py-1 text-xs bg-green-400/10 border border-green-400/30 text-green-400 rounded-lg hover:bg-green-400/20 transition-colors">
                                <UserCheck size={11} /> Approve
                              </button>
                              <button onClick={() => approveUser(u.id, "reject")} disabled={busy === u.id}
                                className="flex items-center gap-1 px-2.5 py-1 text-xs bg-red-400/10 border border-red-400/30 text-red-400 rounded-lg hover:bg-red-400/20 transition-colors">
                                <UserX size={11} /> Reject
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ── TEAM SERVERS ── */}
          {tab === "servers" && (
            <div className="space-y-4">
              <h2 className="font-semibold">Server Team Assignment</h2>
              {Object.entries(teamServers).filter(([,s]) => s.length > 0).map(([team, srvs]) => (
                <div key={team} className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-surface-2">
                    <h3 className="text-sm font-semibold">{team} ({srvs.length} servers)</h3>
                  </div>
                  <div className="overflow-x-auto max-h-48">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-surface/90">
                        <tr className="border-b border-surface-2 text-text-muted">
                          <th className="text-left px-4 py-2">Hostname</th>
                          <th className="text-left px-3 py-2">Family</th>
                          <th className="text-left px-3 py-2">DC</th>
                          <th className="text-left px-3 py-2">Status</th>
                          <th className="text-left px-3 py-2">Reassign to</th>
                        </tr>
                      </thead>
                      <tbody>
                        {srvs.slice(0,20).map((s:any) => (
                          <tr key={s.id} className="border-b border-surface-2/30 hover:bg-surface-2/30">
                            <td className="px-4 py-2 font-mono">{s.hostname}</td>
                            <td className="px-3 py-2 text-text-muted">{s.family??"—"}</td>
                            <td className="px-3 py-2 text-text-muted">{s.datacenter??"—"}</td>
                            <td className="px-3 py-2">
                              <span className={s.status==="healthy"?"text-green-400":s.status==="critical"?"text-red-400":"text-amber-400"}>{s.status}</span>
                            </td>
                            <td className="px-3 py-2">
                              <div className="flex items-center gap-1">
                                <select defaultValue="" onChange={(e) => { if(e.target.value) assignTeam(s.id, e.target.value); e.target.value=""; }}
                                  className="text-xs bg-background border border-surface-2 rounded px-1 py-0.5">
                                  <option value="">Move to...</option>
                                  {["Security Patch Team","TSP","DPDK","Performance","AI","Cloud"].filter(t=>t!==team).map(t=>(
                                    <option key={t} value={t}>{t}</option>
                                  ))}
                                </select>
                              </div>
                            </td>
                          </tr>
                        ))}
                        {srvs.length>20 && <tr><td colSpan={5} className="px-4 py-2 text-text-muted">+{srvs.length-20} more</td></tr>}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* ── RESERVATIONS ── */}
          {tab === "reservations" && (
            <div className="space-y-4">
              <h2 className="font-semibold">All Reservations ({reservations.length})</h2>
              <div className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-surface-2 text-xs text-text-muted">
                        <th className="text-left px-4 py-3">Server</th>
                        <th className="text-left px-3 py-3">User</th>
                        <th className="text-left px-3 py-3">Team</th>
                        <th className="text-left px-3 py-3">Purpose / Benchmark</th>
                        <th className="text-left px-3 py-3">Status</th>
                        <th className="text-left px-3 py-3">Expires</th>
                        <th className="text-left px-3 py-3">Result</th>
                        <th className="text-left px-3 py-3">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reservations.map((r:any) => (
                        <tr key={r.id} className={`border-b border-surface-2/50 hover:bg-surface-2/30 ${r.is_active?"":"opacity-50"}`}>
                          <td className="px-4 py-2.5 font-mono text-xs">{r.hostname}</td>
                          <td className="px-3 py-2.5 text-xs">
                            <p className="font-medium">{r.user_name?.split(" ")[0]}</p>
                            <p className="text-text-muted">{r.user_email}</p>
                          </td>
                          <td className="px-3 py-2.5 text-xs text-text-muted">{r.team??"—"}</td>
                          <td className="px-3 py-2.5 text-xs">
                            <p>{r.purpose}</p>
                            {r.benchmark_name && <p className="text-cyan-400/70">📊 {r.benchmark_name}</p>}
                          </td>
                          <td className="px-3 py-2.5 text-xs">
                            <span className={`px-2 py-0.5 rounded-full border ${
                              r.status==="active"?"text-green-400 bg-green-400/10 border-green-400/20":
                              r.status==="completed"?"text-blue-400 bg-blue-400/10 border-blue-400/20":
                              "text-gray-400 bg-gray-400/10 border-gray-400/20"
                            }`}>{r.status}</span>
                          </td>
                          <td className="px-3 py-2.5 text-xs text-text-muted">
                            {r.is_active && r.remaining_hours != null ? `${r.remaining_hours.toFixed(0)}h left` : r.expires_at ? new Date(r.expires_at).toLocaleDateString() : "—"}
                          </td>
                          <td className="px-3 py-2.5 text-xs">
                            {r.result_url ? <a href={r.result_url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline">View</a> : "—"}
                          </td>
                          <td className="px-3 py-2.5">
                            {r.is_active && (
                              <button onClick={() => forceRelease(r.id)} disabled={busy===r.id}
                                className="text-xs text-red-400 hover:text-red-300 border border-red-400/30 px-2 py-0.5 rounded transition-colors flex items-center gap-1">
                                <Trash2 size={10} /> Release
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                      {reservations.length===0 && <tr><td colSpan={8} className="px-4 py-8 text-center text-text-muted">No reservations</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ── USAGE REPORT ── */}
          {tab === "report" && usageReport && (
            <div className="space-y-4">
              <h2 className="font-semibold">Usage Report — Last {usageReport.period_days} days</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-surface-2"><h3 className="text-sm font-medium">Team Usage</h3></div>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-surface-2 text-xs text-text-muted">
                        <th className="text-left px-4 py-2">Team</th>
                        <th className="text-left px-3 py-2">Reservations</th>
                        <th className="text-left px-3 py-2">Total Hours</th>
                        <th className="text-left px-3 py-2">Users</th>
                        <th className="text-left px-3 py-2">Servers</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(usageReport.team_usage as any[]).map((r:any) => (
                        <tr key={r.team} className="border-b border-surface-2/50 hover:bg-surface-2/30">
                          <td className="px-4 py-2.5 text-xs font-medium">{r.team ?? "Unknown"}</td>
                          <td className="px-3 py-2.5 text-xs text-cyan-400">{r.total_reservations}</td>
                          <td className="px-3 py-2.5 text-xs">{r.total_hours.toFixed(1)}h</td>
                          <td className="px-3 py-2.5 text-xs text-text-muted">{r.unique_users}</td>
                          <td className="px-3 py-2.5 text-xs text-text-muted">{r.unique_servers}</td>
                        </tr>
                      ))}
                      {usageReport.team_usage.length===0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-text-muted text-sm">No reservation data in this period</td></tr>}
                    </tbody>
                  </table>
                </div>

                <div className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-surface-2"><h3 className="text-sm font-medium">Top Benchmarks</h3></div>
                  {(usageReport.top_benchmarks as any[]).length === 0 ? (
                    <p className="px-4 py-6 text-center text-text-muted text-sm">No benchmark data yet</p>
                  ) : (
                    <div className="divide-y divide-surface-2">
                      {(usageReport.top_benchmarks as any[]).map((b:any,i:number) => (
                        <div key={i} className="flex items-center justify-between px-4 py-2.5">
                          <div>
                            <p className="text-xs font-medium">📊 {b.name}</p>
                            <p className="text-xs text-text-muted">{b.team}</p>
                          </div>
                          <span className="text-cyan-400 text-sm font-bold">{b.runs}x</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ── USERS ── */}
          {tab === "users" && (
            <div className="space-y-3">
              <h2 className="font-semibold">User Management</h2>
              <UserTable users={users} currentUserRole={user.role as UserRole} onRefresh={fetchAll} />
            </div>
          )}

          {/* ── ACTIVITY ── */}
          {tab === "activity" && (
            <div className="bg-surface border border-surface-2 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-surface-2"><h3 className="text-sm font-medium">User Activity Summary</h3></div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-2 bg-surface/30 text-xs text-text-muted">
                    <th className="text-left px-4 py-3">User</th>
                    <th className="text-left px-4 py-3">Team</th>
                    <th className="text-left px-4 py-3">Role</th>
                    <th className="text-left px-4 py-3">Actions</th>
                    <th className="text-left px-4 py-3">Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {activity.map((a:any, i:number) => (
                    <tr key={i} className="border-b border-surface-2/50 hover:bg-surface/30">
                      <td className="px-4 py-3">
                        <p className="text-xs font-medium">{a.username ?? "—"}</p>
                        <p className="text-xs text-text-muted">{a.user_email}</p>
                      </td>
                      <td className="px-4 py-3 text-xs text-text-secondary">{a.team ?? "—"}</td>
                      <td className="px-4 py-3 text-xs text-text-secondary">{a.role ?? "—"}</td>
                      <td className="px-4 py-3 text-cyan-400 font-medium">{a.action_count}</td>
                      <td className="px-4 py-3 text-xs text-text-muted">{a.last_action ? new Date(a.last_action).toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                  {activity.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-text-muted">No activity data yet</td></tr>}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </RoleGuard>
  );
}
