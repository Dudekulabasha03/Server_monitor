"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Server, Thermometer, Zap, HardDrive,
  Bell, Users, BarChart3, Map, Radio, Settings, Database,
  Activity, Brain, History, Sparkles, Cpu, CircuitBoard, Shield, UserCog, Home
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { useAuthStore, UserRole } from "@/lib/auth";

type NavItem =
  | { divider: true }
  | {
      label: string;
      href: string;
      icon: React.ElementType;
      badge?: boolean;
      aiOnly?: boolean;
      minRole?: UserRole;
      userOnly?: boolean;   // show ONLY for role === "user"
    };

const nav: NavItem[] = [
  { label: "My Workspace", href: "/user-home", icon: Home, minRole: undefined, userOnly: true },
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Ask Helios", href: "/ask", icon: Sparkles, aiOnly: true },
  { label: "Operations", href: "/operations", icon: Server },
  { label: "Live NOC", href: "/noc", icon: Radio },
  { label: "Live Monitor", href: "/livemon", icon: Activity },
  { label: "Rack View", href: "/racks", icon: Map },
  { divider: true },
  { label: "Thermal", href: "/thermal", icon: Thermometer },
  { label: "Power", href: "/power", icon: Zap },
  { label: "Storage", href: "/storage", icon: HardDrive },
  { label: "Network", href: "/network", icon: Activity },
  { divider: true },
  { label: "Alerts", href: "/alerts", icon: Bell, badge: true },
  { label: "SEL Events", href: "/sel", icon: Activity },
  { label: "Changelog", href: "/changelog", icon: History },
  { label: "User Activity", href: "/users", icon: Users, minRole: "admin" },
  { label: "Utilization", href: "/usage", icon: BarChart3, minRole: "admin" },
  { label: "Inventory", href: "/inventory", icon: Database },
  { divider: true },
  { label: "Intelligence", href: "/intelligence", icon: Brain },
  { label: "AI Ops", href: "/ai-ops", icon: Cpu, aiOnly: true },
  { label: "Firmware & BIOS", href: "/bios", icon: CircuitBoard, minRole: "admin" },
  { label: "Settings", href: "/settings", icon: Settings, minRole: "admin" },
  { divider: true },
  { label: "Admin Ops", href: "/admin-ops", icon: UserCog, minRole: "admin" },
  { label: "Super Admin", href: "/admin", icon: Shield, minRole: "super_admin" },
];

const ROLE_LEVELS: Record<string, number> = { user: 1, admin: 2, super_admin: 3 };

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuthStore();
  const userRole = user?.role ?? "user";
  const userLevel = ROLE_LEVELS[userRole] ?? 1;

  const { data: alertStats } = useQuery({
    queryKey: ["alert-stats"],
    queryFn: fleetApi.getAlertStats,
    refetchInterval: 15_000,
  });
  const { data: aiHealth } = useQuery({
    queryKey: ["ai-enabled"],
    queryFn: fleetApi.aiHealth,
    retry: false,
    staleTime: 300_000,
  });
  const aiOn = !!aiHealth?.enabled;

  const visibleNav = nav.filter((item) => {
    if ("divider" in item) return true;
    if (item.aiOnly && !aiOn) return false;
    if (item.minRole && ROLE_LEVELS[item.minRole] > userLevel) return false;
    // userOnly items (My Workspace) hidden for admin/super_admin
    if (item.userOnly && userRole !== "user") return false;
    return true;
  });

  const criticalCount = alertStats?.critical ?? 0;

  return (
    <aside className="w-56 bg-surface border-r border-surface-2 flex flex-col flex-shrink-0">
      <div className="p-4 border-b border-surface-2">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "linear-gradient(135deg, #f59e0b, #ED1C24)" }}>
            <span className="text-white font-bold text-base">☀</span>
          </div>
          <div>
            <p className="text-sm font-semibold text-text-primary">Helios</p>
            <p className="text-xs text-text-muted">AMD Health Intelligence</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-2 overflow-y-auto">
        {visibleNav.map((item, idx) => {
          if ("divider" in item) {
            return <div key={idx} className="my-2 border-t border-surface-2" />;
          }
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors mb-0.5",
                active
                  ? "bg-blue-600/20 text-blue-400 border border-blue-600/30"
                  : "text-text-secondary hover:bg-surface-2 hover:text-text-primary"
              )}
            >
              <Icon size={16} className="flex-shrink-0" />
              <span>{item.label}</span>
              {item.badge && criticalCount > 0 && (
                <span className="ml-auto bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center font-bold">
                  {criticalCount > 99 ? "99+" : criticalCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="p-3 border-t border-surface-2">
        <p className="text-xs text-text-muted">Helios v1.0 · AMD</p>
      </div>
    </aside>
  );
}
