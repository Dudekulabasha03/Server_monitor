import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export type ServerStatus = "healthy" | "warning" | "at_risk" | "critical" | "offline" | "unknown";

export const STATUS_CONFIG: Record<ServerStatus, { label: string; color: string; bg: string; border: string; dot: string }> = {
  healthy:  { label: "Healthy",  color: "text-green-400",  bg: "bg-green-400/10",  border: "border-green-400/30",  dot: "bg-green-400"  },
  warning:  { label: "Warning",  color: "text-yellow-400", bg: "bg-yellow-400/10", border: "border-yellow-400/30", dot: "bg-yellow-400" },
  at_risk:  { label: "At Risk",  color: "text-orange-400", bg: "bg-orange-400/10", border: "border-orange-400/30", dot: "bg-orange-400" },
  critical: { label: "Critical", color: "text-red-400",    bg: "bg-red-400/10",    border: "border-red-400/30",    dot: "bg-red-400"    },
  offline:  { label: "Offline",  color: "text-gray-400",   bg: "bg-gray-400/10",   border: "border-gray-400/30",   dot: "bg-gray-500"   },
  unknown:  { label: "Unknown",  color: "text-slate-400",  bg: "bg-slate-400/10",  border: "border-slate-400/30",  dot: "bg-slate-400"  },
};

export function getStatusConfig(status: string) {
  return STATUS_CONFIG[status as ServerStatus] ?? STATUS_CONFIG.unknown;
}

export function formatWatts(w: number | null): string {
  if (w === null || w === undefined) return "—";
  if (w >= 1000) return `${(w / 1000).toFixed(1)} kW`;
  return `${Math.round(w)} W`;
}

export function formatPct(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(1)}%`;
}

export function formatTemp(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(1)}°C`;
}

export function healthScoreColor(score: number | null): string {
  if (score === null) return "text-slate-400";
  if (score >= 90) return "text-green-400";
  if (score >= 70) return "text-yellow-400";
  if (score >= 50) return "text-orange-400";
  return "text-red-400";
}
