"use client";
import { useQuery } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { getStatusConfig, formatTemp, formatWatts } from "@/lib/utils";
import Link from "next/link";
import { Server as ServerIcon } from "lucide-react";

const RACK_HEIGHT = 42; // standard 42U rack

function ServerRow({ srv, u }: { srv: any; u?: number }) {
  const cfg = getStatusConfig(srv.status);
  return (
    <Link href={`/servers/${srv.id}`}>
      <div className={`h-6 rounded border ${cfg.bg} ${cfg.border} flex items-center px-2 gap-2 cursor-pointer hover:ring-1 ring-white/40 text-xs`}>
        <span className="text-text-muted w-7 text-[10px]">{u ? `U${u}` : "—"}</span>
        <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
        <span className="font-mono truncate flex-1">{srv.hostname}</span>
        <span className="text-text-muted text-[10px]">{srv.cpu_temp_max ? formatTemp(srv.cpu_temp_max) : ""}</span>
      </div>
    </Link>
  );
}

function RackColumn({ rack }: { rack: any }) {
  // Separate servers with a known U position from those without.
  // A 42U slot map can only hold one server per U — collisions and null-U
  // servers (common: BMC doesn't expose physical slot) must NOT silently vanish.
  const slots: Record<number, any> = {};
  const unplaced: any[] = [];
  for (const s of rack.servers) {
    if (s.rack_unit && !slots[s.rack_unit]) slots[s.rack_unit] = s;
    else unplaced.push(s);
  }
  const placedCount = Object.keys(slots).length;

  const units = [];
  for (let u = RACK_HEIGHT; u >= 1; u--) {
    const srv = slots[u];
    units.push(srv
      ? <ServerRow key={u} srv={srv} u={u} />
      : <div key={u} className="h-6 rounded border border-surface-2/40 bg-surface/30 flex items-center px-2"><span className="text-text-muted/40 w-7 text-[10px]">U{u}</span></div>
    );
  }

  return (
    <div className="bg-surface border border-surface-2 rounded-xl p-3 min-w-[260px]">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold">Rack {rack.rack}</h3>
        <div className="text-xs text-text-muted">{rack.server_count} servers</div>
      </div>
      <div className="flex gap-3 mb-3 text-xs">
        <span className="text-text-muted">Avg: <span className="text-text-primary">{formatTemp(rack.avg_temp)}</span></span>
        <span className="text-text-muted">Power: <span className="text-text-primary">{formatWatts(rack.total_power)}</span></span>
        {rack.critical_count > 0 && <span className="text-red-400">{rack.critical_count} critical</span>}
      </div>
      {placedCount > 0 && <div className="space-y-0.5">{units}</div>}
      {unplaced.length > 0 && (
        <div className="mt-2">
          {placedCount > 0 && <p className="text-[10px] text-text-muted/70 mb-1 uppercase tracking-wide">No U position ({unplaced.length})</p>}
          <div className="space-y-0.5">
            {unplaced.map((s) => <ServerRow key={s.id} srv={s} />)}
          </div>
        </div>
      )}
    </div>
  );
}

export default function RacksPage() {
  const { data, isLoading } = useQuery({ queryKey: ["racks"], queryFn: fleetApi.getRacks, refetchInterval: 20_000 });

  if (isLoading || !data) {
    return <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold">Rack Visualization</h1>
        <p className="text-sm text-text-muted">Datacenter → Rack → U position with live status</p>
        <p className="text-xs text-text-muted/70 mt-1">U positions are logical where the BMC doesn&apos;t expose a physical slot; servers without a position are listed under &quot;No U position&quot;.</p>
      </div>

      {(data.datacenters ?? []).map((dc: any) => (
        <div key={dc.datacenter}>
          <h2 className="text-sm font-semibold text-text-secondary mb-3 flex items-center gap-2"><ServerIcon size={15} /> {dc.datacenter}</h2>
          <div className="flex gap-4 overflow-x-auto pb-2">
            {dc.racks.map((rack: any) => <RackColumn key={rack.rack} rack={rack} />)}
          </div>
        </div>
      ))}
    </div>
  );
}
