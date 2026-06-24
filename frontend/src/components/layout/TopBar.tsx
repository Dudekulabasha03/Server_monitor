"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { Bell, Search, RefreshCw, LogOut, Shield } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore, ROLE_LABELS, ROLE_COLORS, UserRole } from "@/lib/auth";

export function TopBar() {
  const queryClient = useQueryClient();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const { data: alertStats } = useQuery({ queryKey: ["alert-stats"], queryFn: fleetApi.getAlertStats });
  const { user, clearAuth } = useAuthStore();
  const router = useRouter();

  const displayName = user?.full_name ?? user?.email ?? "User";
  const initials = displayName.split(/[@.\s]/)[0].slice(0, 2).toUpperCase();

  const logout = () => {
    clearAuth();
    router.replace("/login");
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await queryClient.invalidateQueries();
    setTimeout(() => setIsRefreshing(false), 800);
  };

  const now = new Date();
  const timeStr = now.toLocaleTimeString("en-US", { hour12: false });

  return (
    <header className="h-14 bg-surface border-b border-surface-2 px-6 flex items-center justify-between flex-shrink-0">
      {/* Search */}
      <div className="relative w-72">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          type="text"
          placeholder="Search servers, IPs, racks..."
          className="w-full bg-surface-2 border border-surface-2 rounded-lg pl-9 pr-4 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-blue-500"
        />
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-xs text-text-secondary">
          <span className="live-dot" />
          <span>Live — {timeStr}</span>
        </div>

        <button
          onClick={handleRefresh}
          className="p-1.5 hover:bg-surface-2 rounded-lg text-text-secondary hover:text-text-primary transition-colors"
          title="Refresh all data"
        >
          <RefreshCw size={15} className={isRefreshing ? "animate-spin" : ""} />
        </button>

        <button className="relative p-1.5 hover:bg-surface-2 rounded-lg text-text-secondary hover:text-text-primary">
          <Bell size={16} />
          {alertStats?.critical > 0 && (
            <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center">
              {alertStats.critical}
            </span>
          )}
        </button>

        {/* User menu */}
        <div className="relative">
          <button
            onClick={() => setMenuOpen((o) => !o)}
            className="flex items-center gap-2 hover:bg-surface-2 rounded-lg pl-1 pr-2 py-1 transition-colors"
          >
            <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-xs font-semibold text-white">
              {initials}
            </div>
            <span className="text-sm text-text-secondary hidden sm:inline max-w-[140px] truncate">{displayName}</span>
          </button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
              <div className="absolute right-0 mt-2 w-56 bg-surface border border-surface-2 rounded-lg shadow-xl z-20 py-1">
                <div className="px-3 py-2 border-b border-surface-2">
                  <p className="text-sm font-medium truncate">{displayName}</p>
                  <p className="text-xs text-text-muted truncate">{user?.email}</p>
                  {user?.role && (
                    <span className={`mt-1 inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${ROLE_COLORS[user.role as UserRole]}`}>
                      <Shield size={9} /> {ROLE_LABELS[user.role as UserRole]}
                    </span>
                  )}
                  {user?.team_name && (
                    <p className="text-xs text-text-muted/70 mt-0.5">{user.team_name}</p>
                  )}
                </div>
                <button
                  onClick={logout}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-red-400/10"
                >
                  <LogOut size={14} /> Sign out
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
