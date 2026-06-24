"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fleetApi } from "@/lib/api";
import { ChangelogTable } from "@/components/ChangelogTable";
import { Search, History } from "lucide-react";
import { ExportButton } from "@/components/ExportButton";

const HOURS = [
  { label: "24h", v: 24 }, { label: "48h", v: 48 }, { label: "7d", v: 168 },
];

export default function ChangelogPage() {
  const [kind, setKind] = useState("");
  const [host, setHost] = useState("");
  const [hours, setHours] = useState(24);

  const { data } = useQuery({
    queryKey: ["changelog", kind, host, hours],
    queryFn: () => fleetApi.getChangelog({ hours, kind: kind || undefined, host: host || undefined, limit: 500 }),
    refetchInterval: 20_000,
  });

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2"><History size={18} /> Changelog</h1>
        <p className="text-sm text-text-muted"><b className="text-text-primary">{data?.total ?? 0}</b> event(s) in the selected window. Newest first.</p>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative w-64">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input value={host} onChange={(e) => setHost(e.target.value)} placeholder="Search host..."
            className="w-full bg-surface border border-surface-2 rounded-lg pl-8 pr-4 py-1.5 text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <select value={kind} onChange={(e) => setKind(e.target.value)} className="bg-surface border border-surface-2 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
          <option value="">All Kinds</option>
          <option value="status">Status</option>
          <option value="power">Power</option>
          <option value="drift">Drift</option>
        </select>
        <div className="flex gap-1 bg-surface rounded-lg p-1">
          {HOURS.map((h) => (
            <button key={h.v} onClick={() => setHours(h.v)}
              className={`px-2.5 py-1 rounded text-xs font-medium ${hours === h.v ? "bg-blue-600 text-white" : "text-text-muted hover:text-text-primary"}`}>{h.label}</button>
          ))}
        </div>
        <ExportButton endpoint="/export/changelog" params={{ hours }} label="Export CSV" className="ml-auto" />
      </div>

      <div className="card p-0">
        <ChangelogTable events={data?.events ?? []} />
      </div>
    </div>
  );
}
