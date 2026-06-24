"use client";
import Link from "next/link";

const KIND_CHIP: Record<string, string> = {
  status: "bg-orange-400/15 text-orange-400",
  power: "bg-blue-400/15 text-blue-400",
  drift: "bg-purple-400/15 text-purple-400",
};

// Color a value token: status OK=green/WARN=amber/CRITICAL=red; power On=green/Off=gray; drift YES=amber/no=gray
function valueColor(kind: string, v: string | null): string {
  if (!v) return "text-text-muted";
  const u = v.toUpperCase();
  if (kind === "status") {
    if (u === "HEALTHY" || u === "OK") return "text-green-400";
    if (u === "WARNING" || u === "WARN" || u === "AT_RISK") return "text-yellow-400";
    if (u === "CRITICAL") return "text-red-400";
    if (u === "OFFLINE") return "text-gray-400";
  }
  if (kind === "power") return u === "ON" ? "text-green-400" : "text-gray-400";
  if (kind === "drift") return u === "YES" ? "text-yellow-400" : "text-gray-400";
  return "text-text-primary";
}

function label(kind: string, v: string | null): string {
  if (!v) return "—";
  if (kind === "status") {
    const m: Record<string, string> = { healthy: "OK", warning: "WARN", at_risk: "AT-RISK", critical: "CRITICAL", offline: "OFFLINE", unknown: "UNKNOWN" };
    return m[v.toLowerCase()] ?? v.toUpperCase();
  }
  return v;
}

function fmtTs(iso: string) {
  const d = new Date(iso);
  const local = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  const utc = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
  return { local, utc };
}

export function ChangelogTable({ events, compact = false }: { events: any[]; compact?: boolean }) {
  if (!events?.length) {
    return <p className="text-sm text-text-muted py-6 text-center">No changes recorded yet</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-text-muted uppercase border-b border-surface-2">
            <th className="px-3 py-2">Timestamp</th>
            <th className="px-3 py-2">Kind</th>
            <th className="px-3 py-2">Host</th>
            <th className="px-3 py-2">Change</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e, i) => {
            const ts = fmtTs(e.timestamp);
            return (
              <tr key={i} className="border-b border-surface-2 hover:bg-surface-2/40">
                <td className="px-3 py-2 text-text-muted whitespace-nowrap">{ts.local} local / {ts.utc} UTC</td>
                <td className="px-3 py-2"><span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase ${KIND_CHIP[e.kind] ?? "bg-surface-2 text-text-secondary"}`}>{e.kind}</span></td>
                <td className="px-3 py-2 font-mono text-text-secondary">{e.hostname}</td>
                <td className="px-3 py-2">
                  <span className={valueColor(e.kind, e.old_value)}>{label(e.kind, e.old_value)}</span>
                  <span className="text-text-muted mx-1.5">→</span>
                  <span className={`font-semibold ${valueColor(e.kind, e.new_value)}`}>{label(e.kind, e.new_value)}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
