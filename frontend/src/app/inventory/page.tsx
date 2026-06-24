"use client";
import { useQuery } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { Database, Search, ChevronDown, ChevronRight } from "lucide-react";
import { ExportButton } from "@/components/ExportButton";
import { useState, useMemo } from "react";
import Link from "next/link";

function familyShort(model: string | null): string {
  if (!model) return "Other";
  if (model.includes("Milan")) return "Milan";
  if (model.includes("Genoa")) return "Genoa";
  if (model.includes("Turin Dense")) return "Turin Dense";
  if (model.includes("Turin Classic")) return "Turin Classic";
  return model;
}

export default function InventoryPage() {
  const [search, setSearch] = useState("");
  const [activeRegion, setActiveRegion] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const { data, isLoading } = useQuery({ queryKey: ["inventory"], queryFn: fleetApi.getInventory, refetchInterval: 60_000 });

  const rows = useMemo(() => {
    const all = data?.servers ?? [];
    if (!search) return all;
    const q = search.toLowerCase();
    return all.filter((r: any) =>
      [r.hostname, r.bmc_ip, r.model, r.serial_number, r.vendor, r.rack, r.team]
        .some((v) => v && String(v).toLowerCase().includes(q))
    );
  }, [data, search]);

  // region -> family -> servers
  const grouped = useMemo(() => {
    const g: Record<string, Record<string, any[]>> = {};
    for (const r of rows) {
      const region = r.datacenter || "Unassigned";
      const fam = familyShort(r.model);
      ((g[region] ??= {})[fam] ??= []).push(r);
    }
    return g;
  }, [rows]);

  const regions = Object.keys(grouped).sort();
  const currentRegion = activeRegion && grouped[activeRegion] ? activeRegion : regions[0];

  const exportCsv = () => {
    const cols = ["hostname", "bmc_ip", "datacenter", "model", "serial_number", "cpu_model", "memory_gb", "dimm_count", "bmc_firmware", "bios_version", "rack", "rack_unit", "team"];
    const lines = rows.map((r: any) => cols.map((c) => `"${r[c] ?? ""}"`).join(","));
    const blob = new Blob([[cols.join(","), ...lines].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "fleet-inventory.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  if (isLoading || !data) {
    return <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" /></div>;
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Inventory</h1>
          <p className="text-sm text-text-muted">{data.total} assets across {regions.length} regions</p>
        </div>
        <ExportButton endpoint="/export/servers" params={{ datacenter: activeRegion || undefined }} label="Export CSV" />
      </div>

      <div className="relative w-72">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search assets..."
          className="w-full bg-surface border border-surface-2 rounded-lg pl-8 pr-4 py-1.5 text-sm focus:outline-none focus:border-blue-500" />
      </div>

      {/* Region tabs */}
      <div className="flex gap-1 border-b border-surface-2">
        {regions.map((region) => {
          const count = Object.values(grouped[region]).reduce((a, b) => a + b.length, 0);
          const active = region === currentRegion;
          return (
            <button key={region} onClick={() => setActiveRegion(region)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${active ? "border-blue-500 text-blue-400" : "border-transparent text-text-muted hover:text-text-primary"}`}>
              {region} <span className="text-xs opacity-70">({count})</span>
            </button>
          );
        })}
      </div>

      {/* Family sub-groups within the active region */}
      {currentRegion && Object.keys(grouped[currentRegion]).sort().map((fam) => {
        const list = grouped[currentRegion][fam];
        const key = `${currentRegion}:${fam}`;
        const isCollapsed = collapsed[key];
        return (
          <div key={key} className="card p-0 overflow-hidden">
            <button onClick={() => setCollapsed((c) => ({ ...c, [key]: !c[key] }))}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-2/40">
              <div className="flex items-center gap-2">
                {isCollapsed ? <ChevronRight size={15} /> : <ChevronDown size={15} />}
                <span className="font-semibold text-sm">{fam}</span>
                <span className="text-xs text-text-muted">({list.length})</span>
              </div>
              <span className="text-xs text-text-muted">{list[0]?.model}</span>
            </button>
            {!isCollapsed && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-y border-surface-2 text-left text-xs text-text-muted uppercase">
                    <th className="px-4 py-2">Hostname</th><th className="px-3 py-2">BMC IP</th><th className="px-3 py-2">Serial</th><th className="px-3 py-2">Mem</th><th className="px-3 py-2">DIMMs</th><th className="px-3 py-2">BMC FW</th><th className="px-3 py-2">BIOS</th><th className="px-3 py-2">Rack</th>
                  </tr></thead>
                  <tbody>
                    {list.sort((a, b) => a.hostname.localeCompare(b.hostname)).map((r: any) => (
                      <tr key={r.id} className="border-b border-surface-2 hover:bg-surface-2/40">
                        <td className="px-4 py-2"><Link href={`/servers/${r.id}`} className="font-mono hover:text-blue-400">{r.hostname}</Link></td>
                        <td className="px-3 py-2 text-text-muted">{r.bmc_ip ?? "—"}</td>
                        <td className="px-3 py-2 font-mono text-text-muted">{r.serial_number ?? "—"}</td>
                        <td className="px-3 py-2">{r.memory_gb ? `${r.memory_gb} GB` : "—"}</td>
                        <td className="px-3 py-2">{r.dimm_count ?? "—"}</td>
                        <td className="px-3 py-2 text-text-muted">{r.bmc_firmware ?? "—"}</td>
                        <td className="px-3 py-2 text-text-muted">{r.bios_version ?? "—"}</td>
                        <td className="px-3 py-2">{r.rack ? `${r.rack}/U${r.rack_unit ?? "?"}` : "—"}</td>
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
  );
}
