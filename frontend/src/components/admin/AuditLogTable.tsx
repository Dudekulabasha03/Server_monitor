"use client";
import { useState } from "react";
import { Search, Shield, Clock, Monitor } from "lucide-react";

interface AuditEntry {
  id: string;
  timestamp: string;
  username: string | null;
  user_email: string | null;
  team: string | null;
  role: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  old_value: string | null;
  new_value: string | null;
  ip_address: string | null;
}

const ACTION_COLORS: Record<string, string> = {
  user_login: "text-green-400 bg-green-400/10 border-green-400/30",
  user_registered: "text-cyan-400 bg-cyan-400/10 border-cyan-400/30",
  admin_create_user: "text-blue-400 bg-blue-400/10 border-blue-400/30",
  admin_update_user: "text-amber-400 bg-amber-400/10 border-amber-400/30",
  admin_disable_user: "text-red-400 bg-red-400/10 border-red-400/30",
  admin_create_team: "text-purple-400 bg-purple-400/10 border-purple-400/30",
  admin_update_team: "text-indigo-400 bg-indigo-400/10 border-indigo-400/30",
  admin_disable_team: "text-orange-400 bg-orange-400/10 border-orange-400/30",
};

function actionColor(action: string) {
  return ACTION_COLORS[action] ?? "text-text-muted bg-surface border-surface-2";
}

interface AuditLogTableProps {
  logs: AuditEntry[];
}

export function AuditLogTable({ logs }: AuditLogTableProps) {
  const [search, setSearch] = useState("");

  const filtered = logs.filter(
    (l) =>
      (l.action ?? "").includes(search.toLowerCase()) ||
      (l.user_email ?? "").toLowerCase().includes(search.toLowerCase()) ||
      (l.username ?? "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search audit logs..."
          className="w-full bg-surface border border-surface-2 rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
        />
      </div>

      <div className="overflow-x-auto rounded-lg border border-surface-2">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-2 bg-surface/50">
              <th className="text-left px-4 py-3 text-xs text-text-muted font-medium">Time</th>
              <th className="text-left px-4 py-3 text-xs text-text-muted font-medium">User</th>
              <th className="text-left px-4 py-3 text-xs text-text-muted font-medium">Action</th>
              <th className="text-left px-4 py-3 text-xs text-text-muted font-medium">Resource</th>
              <th className="text-left px-4 py-3 text-xs text-text-muted font-medium">IP</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((log) => (
              <tr key={log.id} className="border-b border-surface-2/50 hover:bg-surface/30 transition-colors">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1.5 text-xs text-text-muted">
                    <Clock size={11} />
                    {new Date(log.timestamp).toLocaleString()}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div>
                    <p className="text-text-primary text-xs font-medium">{log.username ?? "—"}</p>
                    <p className="text-text-muted text-xs">{log.user_email ?? "—"}</p>
                    {log.team && (
                      <span className="text-[10px] text-text-muted/70">{log.team}</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border ${actionColor(log.action)}`}>
                    <Shield size={9} /> {log.action.replace(/_/g, " ")}
                  </span>
                  {log.role && (
                    <p className="text-[10px] text-text-muted mt-0.5">{log.role}</p>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-text-muted">
                  {log.resource_type && (
                    <div>
                      <p>{log.resource_type}</p>
                      {log.resource_id && <p className="text-[10px] font-mono opacity-60">{log.resource_id.slice(0, 8)}…</p>}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1 text-xs text-text-muted">
                    <Monitor size={11} />
                    {log.ip_address ?? "—"}
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-text-muted text-sm">No audit logs found</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-text-muted">{filtered.length} entries shown</p>
    </div>
  );
}
