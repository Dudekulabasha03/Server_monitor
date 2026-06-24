"use client";
import { useQuery } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { HardDrive, AlertTriangle, ChevronDown, ChevronRight, Search } from "lucide-react";
import { useState, useMemo } from "react";
import Link from "next/link";
import { ExportButton } from "@/components/ExportButton";

function fmtCap(gb: number | null): string {
  if (!gb) return "—";
  return gb >= 1000 ? `${(gb / 1000).toFixed(1)} TB` : `${gb} GB`;
}

const FAMILIES = ["Naples", "Rome", "Milan", "Genoa", "Bergamo", "Siena", "Turin"];
const TEAMS = ["Security Patch Team", "TSP", "DPDK team"];
const REGIONS = ["Santa Clara", "Plano", "Dallas", "Bangalore"];

export default function StoragePage() {
  const { data, isLoading } = useQuery({ queryKey: ["storage"], queryFn: fleetApi.getStorage, refetchInterval: 30_000 });
  const [search, setSearch] = useState("");
  const [team, setTeam] = useState("");
  const [family, setFamily] = useState("");
  const [region, setRegion] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});

  // Group disks by server
  const groups = useMemo(() => {
    const disks = data?.disks ?? [];
    const g: Record<string, any> = {};
    for (const d of disks) {
      (g[d.server_id] ??= { hostname: d.hostname, server_id: d.server_id, team: d.team, family: d.family, datacenter: d.datacenter, disks: [] }).disks.push(d);
    }
    let list = Object.values(g);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((x: any) => x.hostname.toLowerCase().includes(q));
    }
    if (team) list = list.filter((x: any) => x.team === team);
    if (family) list = list.filter((x: any) => x.family === family);
    if (region) list = list.filter((x: any) => x.datacenter === region);
    return list.sort((a: any, b: any) => a.hostname.localeCompare(b.hostname));
  }, [data, search, team, family, region]);

  if (isLoading || !data) {
    return <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" /></div>;
  }
  const s = data.summary;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold">Storage Health</h1>
        <p className="text-sm text-text-muted">Per-server disk inventory · SMART status · failure prediction</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card flex items-center gap-3"><div className="bg-blue-400/10 p-3 rounded-xl"><HardDrive size={20} className="text-blue-400" /></div><div><p className="metric-label">Total Disks</p><p className="metric-value">{s.total_disks}</p></div></div>
        <div className="card"><p className="metric-label">Servers</p><p className="metric-value">{groups.length}</p></div>
        <div className="card"><p className="metric-label">Predicted Failures</p><p className={`metric-value ${s.predicted_failures > 0 ? "text-red-400" : "text-green-400"}`}>{s.predicted_failures}</p></div>
        <div className="card"><p className="metric-label">Total Capacity</p><p className="metric-value">{(s.total_capacity_gb / 1000).toFixed(1)} TB</p></div>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative w-64">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search server..."
            className="w-full bg-surface border border-surface-2 rounded-lg pl-8 pr-4 py-1.5 text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <select value={team} onChange={(e) => setTeam(e.target.value)} className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
          <option value="">All Teams</option>{TEAMS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={family} onChange={(e) => setFamily(e.target.value)} className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
          <option value="">All Families</option>{FAMILIES.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <select value={region} onChange={(e) => setRegion(e.target.value)} className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
          <option value="">All Regions</option>{REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <ExportButton endpoint="/export/storage" params={{ team: team || undefined, datacenter: region || undefined }} label="Export CSV" className="ml-auto" />
      </div>

      {groups.length === 0 ? (
        <div className="card flex flex-col items-center py-16 text-text-muted">
          <HardDrive size={40} className="mb-3 opacity-30" />
          <p>No disk inventory for matching servers</p>
        </div>
      ) : (
        <div className="space-y-2">
          {groups.map((g) => {
            const isOpen = open[g.server_id];
            const totalCap = g.disks.reduce((a, d) => a + (d.capacity_gb || 0), 0);
            const failing = g.disks.filter((d) => d.failure_predicted).length;
            return (
              <div key={g.server_id} className="card p-0 overflow-hidden">
                <button onClick={() => setOpen((o) => ({ ...o, [g.server_id]: !o[g.server_id] }))}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-2/40">
                  <div className="flex items-center gap-2">
                    {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                    <Link href={`/servers/${g.server_id}`} onClick={(e) => e.stopPropagation()} className="font-mono text-sm hover:text-blue-400">{g.hostname}</Link>
                    <span className="ml-2 text-xs bg-blue-400/10 text-blue-400 rounded-full px-2 py-0.5">{g.disks.length} disks</span>
                    {failing > 0 && <span className="text-xs bg-red-400/10 text-red-400 rounded-full px-2 py-0.5 flex items-center gap-1"><AlertTriangle size={10} />{failing} at risk</span>}
                  </div>
                  <span className="text-xs text-text-muted">{fmtCap(totalCap)}</span>
                </button>
                {isOpen && (
                  <div className="overflow-x-auto border-t border-surface-2">
                    <table className="w-full text-sm">
                      <thead><tr className="text-left text-xs text-text-muted uppercase border-b border-surface-2">
                        <th className="px-4 py-2">Disk</th><th className="px-3 py-2">Model</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Capacity</th><th className="px-3 py-2">Health</th><th className="px-3 py-2">SMART</th>
                      </tr></thead>
                      <tbody>
                        {g.disks.map((d: any) => (
                          <tr key={d.id} className="border-b border-surface-2 hover:bg-surface-2/40">
                            <td className="px-4 py-2 font-mono">{d.name}</td>
                            <td className="px-3 py-2 text-text-muted">{d.model ?? "—"}</td>
                            <td className="px-3 py-2">{d.media_type ?? d.protocol ?? "—"}</td>
                            <td className="px-3 py-2">{fmtCap(d.capacity_gb)}</td>
                            <td className="px-3 py-2">{(d.health || "").toUpperCase() === "OK" ? <span className="text-green-400">OK</span> : <span className="text-red-400">{d.health}</span>}</td>
                            <td className="px-3 py-2">{d.failure_predicted ? <span className="text-red-400 flex items-center gap-1"><AlertTriangle size={12} /> Predicted</span> : <span className="text-green-400">Nominal</span>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
