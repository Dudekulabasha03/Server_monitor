"use client";
import { useState } from "react";
import { Search, UserCheck, UserX, Shield, ChevronDown } from "lucide-react";
import { ROLE_COLORS, ROLE_LABELS, UserRole } from "@/lib/auth";
import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  team_name: string | null;
  is_active: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

interface UserTableProps {
  users: User[];
  currentUserRole: UserRole;
  onRefresh: () => void;
}

export function UserTable({ users, currentUserRole, onRefresh }: UserTableProps) {
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const token = typeof window !== "undefined" ? localStorage.getItem("helios_jwt") : null;
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const filtered = users.filter(
    (u) =>
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      u.full_name.toLowerCase().includes(search.toLowerCase()) ||
      (u.team_name ?? "").toLowerCase().includes(search.toLowerCase())
  );

  const toggleActive = async (user: User) => {
    setBusy(user.id);
    try {
      await axios.patch(`${API_BASE}/admin/users/${user.id}`, { is_active: !user.is_active }, { headers });
      onRefresh();
    } finally {
      setBusy(null);
    }
  };

  const changeRole = async (user: User, newRole: string) => {
    setBusy(user.id + newRole);
    try {
      await axios.patch(`${API_BASE}/admin/users/${user.id}`, { role: newRole }, { headers });
      onRefresh();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search users..."
          className="w-full bg-surface border border-surface-2 rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
        />
      </div>

      <div className="overflow-x-auto rounded-lg border border-surface-2">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-2 bg-surface/50">
              <th className="text-left px-4 py-3 text-xs text-text-muted font-medium">User</th>
              <th className="text-left px-4 py-3 text-xs text-text-muted font-medium">Team</th>
              <th className="text-left px-4 py-3 text-xs text-text-muted font-medium">Role</th>
              <th className="text-left px-4 py-3 text-xs text-text-muted font-medium">Status</th>
              <th className="text-left px-4 py-3 text-xs text-text-muted font-medium">Last Login</th>
              <th className="text-left px-4 py-3 text-xs text-text-muted font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((user) => (
              <tr key={user.id} className="border-b border-surface-2/50 hover:bg-surface/30 transition-colors">
                <td className="px-4 py-3">
                  <div>
                    <p className="font-medium text-text-primary">{user.full_name}</p>
                    <p className="text-xs text-text-muted">{user.email}</p>
                  </div>
                </td>
                <td className="px-4 py-3 text-text-secondary">{user.team_name ?? "—"}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border ${ROLE_COLORS[user.role]}`}>
                    <Shield size={10} /> {ROLE_LABELS[user.role]}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${
                    user.is_active
                      ? "text-green-400 bg-green-400/10 border-green-400/30"
                      : "text-red-400 bg-red-400/10 border-red-400/30"
                  }`}>
                    {user.is_active ? "Active" : "Disabled"}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-text-muted">
                  {user.last_login_at ? new Date(user.last_login_at).toLocaleDateString() : "Never"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {currentUserRole === "super_admin" && user.role !== "super_admin" && (
                      <div className="relative group">
                        <button className="flex items-center gap-1 px-2 py-1 text-xs border border-surface-2 rounded hover:bg-surface-2 transition-colors">
                          Role <ChevronDown size={10} />
                        </button>
                        <div className="hidden group-hover:block absolute right-0 top-full mt-1 bg-surface border border-surface-2 rounded-lg shadow-xl z-10 min-w-32">
                          {(["admin", "user"] as const).map((r) => (
                            <button
                              key={r}
                              onClick={() => changeRole(user, r)}
                              disabled={!!busy}
                              className="w-full text-left px-3 py-2 text-xs hover:bg-surface-2 transition-colors first:rounded-t-lg last:rounded-b-lg"
                            >
                              {ROLE_LABELS[r]}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    <button
                      onClick={() => toggleActive(user)}
                      disabled={!!busy}
                      className={`flex items-center gap-1 px-2 py-1 text-xs border rounded transition-colors ${
                        user.is_active
                          ? "border-red-400/30 text-red-400 hover:bg-red-400/10"
                          : "border-green-400/30 text-green-400 hover:bg-green-400/10"
                      }`}
                    >
                      {user.is_active ? <><UserX size={10} /> Disable</> : <><UserCheck size={10} /> Enable</>}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-text-muted text-sm">No users found</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-text-muted">{filtered.length} of {users.length} users</p>
    </div>
  );
}
