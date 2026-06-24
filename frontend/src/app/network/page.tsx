"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { Activity, ChevronDown, ChevronRight, Search, Pencil, Check, X, RefreshCw } from "lucide-react";
import { ExportButton } from "@/components/ExportButton";
import { useState, useMemo } from "react";
import Link from "next/link";

function OsIpEditor({ serverId, osIp }: { serverId: string; osIp: string | null }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(osIp ?? "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const save = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setBusy(true); setMsg(null);
    try {
      await fleetApi.updateServer(serverId, { os_ip: val || null, os_agent_enabled: !!val });
      const res = await fleetApi.osRefresh(serverId);
      const reach = res?.collected > 0 ? "fetched live data" : (res?.unreachable > 0 ? "unreachable (firewall)" : "no data");
      setMsg(reach);
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["network"] });
    } catch (err: any) {
      setMsg("error");
    } finally { setBusy(false); }
  };

  if (!editing) {
    return (
      <span className="flex items-center gap-1 text-xs text-text-muted" onClick={(e) => e.stopPropagation()}>
        OS {osIp ?? "—"}
        <button onClick={(e) => { e.stopPropagation(); setEditing(true); }} className="hover:text-blue-400"><Pencil size={11} /></button>
        {msg && <span className="text-text-muted italic">· {msg}</span>}
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      <input value={val} onChange={(e) => setVal(e.target.value)} placeholder="OS IP"
        className="w-32 bg-surface border border-surface-2 rounded px-2 py-0.5 text-xs focus:outline-none focus:border-blue-500" />
      <button onClick={save} disabled={busy} className="text-green-400 hover:text-green-300">{busy ? <RefreshCw size={12} className="animate-spin" /> : <Check size={13} />}</button>
      <button onClick={(e) => { e.stopPropagation(); setEditing(false); setVal(osIp ?? ""); }} className="text-red-400 hover:text-red-300"><X size={13} /></button>
    </span>
  );
}

function PrismRefreshBtn({ serverId }: { serverId: string }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const run = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setBusy(true); setMsg(null);
    try {
      // PRISM enrich fetches the server's OS IP (and hardware) and stores it.
      const res = await fleetApi.prismRefresh(serverId);
      const ok = (res?.enriched ?? 0) > 0;
      setMsg(ok ? "OS IP updated" : (res?.not_found ? "not in PRISM" : "no change"));
      qc.invalidateQueries({ queryKey: ["network"] });
    } catch {
      setMsg("failed");
    } finally { setBusy(false); setTimeout(() => setMsg(null), 4000); }
  };
  return (
    <span className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      <button onClick={run} disabled={busy} title="PRISM refresh — fetch this server's OS IP from PRISM"
        className="flex items-center gap-1 text-xs border border-blue-500/40 hover:bg-blue-400/10 text-blue-400 rounded px-1.5 py-0.5 disabled:opacity-50">
        {busy ? <RefreshCw size={11} className="animate-spin" /> : <RefreshCw size={11} />} PRISM
      </button>
      {msg && <span className="text-[10px] text-text-muted italic">{msg}</span>}
    </span>
  );
}

const FAMILIES = ["Naples", "Rome", "Milan", "Genoa", "Bergamo", "Siena", "Turin"];
const TEAMS = ["Security Patch Team", "TSP", "DPDK team"];

// BMC/OS sources report link state inconsistently ("Up", "LinkUp", "Enabled",
// "LinkDown", null). Normalize so the UI always shows an honest Up/Down.
function isLinkUp(status: string | null | undefined): boolean {
  const s = (status || "").toLowerCase().replace(/[^a-z]/g, "");
  return s === "up" || s === "linkup" || s === "enabled" || s === "connected" || s === "active";
}

// Speed: Gigabit and above show "N Gb"; a stored 0 means a sub-gigabit link that
// survived the conversion; null means the BMC didn't report SpeedMbps at all.
function fmtSpeed(speed: number | null | undefined): string {
  if (speed === null || speed === undefined) return "—";
  if (speed >= 1) return `${speed} Gb`;
  return "< 1 Gb";
}

export default function NetworkPage() {
  const { data, isLoading } = useQuery({ queryKey: ["network"], queryFn: fleetApi.getNetwork, refetchInterval: 20_000 });
  const [search, setSearch] = useState("");
  const [region, setRegion] = useState("");
  const [family, setFamily] = useState("");
  const [team, setTeam] = useState("");
  const [linkFilter, setLinkFilter] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});

  const groups = useMemo(() => {
    const nics = data?.nics ?? [];
    const g: Record<string, any> = {};
    for (const n of nics) {
      (g[n.server_id] ??= { hostname: n.hostname, server_id: n.server_id, os_ip: n.os_ip, bmc_ip: n.bmc_ip, datacenter: n.datacenter, team: n.team, family: n.family, model: n.model, nics: [] }).nics.push(n);
    }
    let list = Object.values(g);
    if (search) { const q = search.toLowerCase(); list = list.filter((x: any) => x.hostname.toLowerCase().includes(q) || (x.os_ip || "").includes(q)); }
    if (region) list = list.filter((x: any) => x.datacenter === region);
    if (team) list = list.filter((x: any) => x.team === team);
    if (family) list = list.filter((x: any) => x.family === family);
    if (linkFilter) {
      list = list.map((x: any) => ({
        ...x,
        nics: x.nics.filter((n: any) => {
          const up = isLinkUp(n.link_status);
          return linkFilter === "up" ? up : !up;
        }),
      })).filter((x: any) => x.nics.length > 0);
    }
    return list.sort((a: any, b: any) => a.hostname.localeCompare(b.hostname));
  }, [data, search, region, family, team, linkFilter]);

  if (isLoading || !data) {
    return <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" /></div>;
  }
  const s = data.summary;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold">Network</h1>
        <p className="text-sm text-text-muted">Per-server port inventory · link status · throughput</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card flex items-center gap-3"><div className="bg-blue-400/10 p-3 rounded-xl"><Activity size={20} className="text-blue-400" /></div><div><p className="metric-label">Total Ports</p><p className="metric-value">{s.total_nics}</p></div></div>
        <div className="card"><p className="metric-label">Servers</p><p className="metric-value">{groups.length}</p></div>
        <div className="card"><p className="metric-label">Link Up</p><p className="metric-value text-green-400">{s.up}</p></div>
        <div className="card"><p className="metric-label">Link Down</p><p className={`metric-value ${s.down > 0 ? "text-red-400" : "text-green-400"}`}>{s.down}</p></div>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative w-64">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search host / IP..."
            className="w-full bg-surface border border-surface-2 rounded-lg pl-8 pr-4 py-1.5 text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <select value={region} onChange={(e) => setRegion(e.target.value)} className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
          <option value="">All Regions</option><option>Santa Clara</option><option>Plano</option><option>Dallas</option><option>Bangalore</option>
        </select>
        <select value={family} onChange={(e) => setFamily(e.target.value)} className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
          <option value="">All Families</option>{FAMILIES.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <select value={team} onChange={(e) => setTeam(e.target.value)} className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
          <option value="">All Teams</option>{TEAMS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={linkFilter} onChange={(e) => setLinkFilter(e.target.value)} className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
          <option value="">All Links</option>
          <option value="up">Link Up</option>
          <option value="down">Link Down</option>
        </select>
        <ExportButton endpoint="/export/network" params={{ team: team || undefined, datacenter: region || undefined, link_status: linkFilter || undefined }} label="Export CSV" className="ml-auto" />
      </div>

      {groups.length === 0 ? (
        <div className="card flex flex-col items-center py-16 text-text-muted">
          <Activity size={40} className="mb-3 opacity-30" />
          <p>No NIC inventory for matching servers</p>
        </div>
      ) : (
        <div className="space-y-2">
          {groups.map((g) => {
            const isOpen = open[g.server_id];
            const up = g.nics.filter((n) => isLinkUp(n.link_status)).length;
            return (
              <div key={g.server_id} className="card p-0 overflow-hidden">
                <button onClick={() => setOpen((o) => ({ ...o, [g.server_id]: !o[g.server_id] }))}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-2/40">
                  <div className="flex items-center gap-2">
                    {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                    <Link href={`/servers/${g.server_id}`} onClick={(e) => e.stopPropagation()} className="font-mono text-sm hover:text-blue-400">{g.hostname}</Link>
                    <span className="ml-2 text-xs bg-blue-400/10 text-blue-400 rounded-full px-2 py-0.5">{g.nics.length} Ports</span>
                    <OsIpEditor serverId={g.server_id} osIp={g.os_ip} />
                    <PrismRefreshBtn serverId={g.server_id} />
                    {g.datacenter && <span className="text-xs text-text-muted">· {g.datacenter}</span>}
                  </div>
                  <span className="text-xs text-text-muted">{up}/{g.nics.length} up</span>
                </button>
                {isOpen && (
                  <div className="overflow-x-auto border-t border-surface-2">
                    <table className="w-full text-sm">
                      <thead><tr className="text-left text-xs text-text-muted uppercase border-b border-surface-2">
                        <th className="px-4 py-2">Port</th><th className="px-3 py-2">Model</th><th className="px-3 py-2">MAC</th><th className="px-3 py-2">Speed</th><th className="px-3 py-2">Link</th><th className="px-3 py-2">IP</th>
                      </tr></thead>
                      <tbody>
                        {g.nics.map((n: any) => (
                          <tr key={n.id} className="border-b border-surface-2 hover:bg-surface-2/40">
                            <td className="px-4 py-2 font-mono">{n.name}</td>
                            <td className="px-3 py-2 text-text-muted">{n.driver ?? n.model ?? "—"}</td>
                            <td className="px-3 py-2 font-mono text-text-muted">{n.mac_address ?? "—"}</td>
                            <td className="px-3 py-2">{fmtSpeed(n.speed_gbps)}</td>
                            <td className="px-3 py-2">{isLinkUp(n.link_status) ? <span className="text-green-400">● Up</span> : <span className="text-red-400">○ Down</span>}</td>
                            <td className="px-3 py-2 text-text-muted">{n.ip_address ?? "—"}</td>
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
