"use client";

import { useState, useRef, useEffect, Fragment } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { RefreshCw } from "lucide-react";
import {
  Cpu, Upload, Link, CheckCircle, XCircle,
  AlertTriangle, RotateCcw, Zap, Settings2, Search, Loader2,
} from "lucide-react";
import { ExportButton } from "@/components/ExportButton";

// ── Types ─────────────────────────────────────────────────────────────────────

interface BiosServer {
  id: string;
  hostname: string;
  bmc_ip: string | null;
  os_ip: string | null;
  vendor: string | null;
  family: string | null;
  cpu_model: string | null;
  team: string | null;
  bios_version: string | null;
  bmc_firmware: string | null;
  microcode: string | null;
  has_bmc_creds: boolean;
  has_os_creds: boolean;
}

interface BiosAttribute {
  "Setup Question": string;
  "Help String"?: string;
  Options?: string[];
  Value: string;
}

interface BiosJob {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  result?: any;
  logs?: string[];
}

// Common AMD EPYC tuning presets. Keys are matched fuzzily against the server's live
// Setup Questions, so only the knobs that actually exist on that board get staged.
const TUNING_PRESETS: { label: string; values: Record<string, string> }[] = [
  { label: "NPS1", values: { "NUMA nodes per socket": "NPS1" } },
  { label: "NPS2", values: { "NUMA nodes per socket": "NPS2" } },
  { label: "NPS4", values: { "NUMA nodes per socket": "NPS4" } },
  { label: "SMT On", values: { "SMT Control": "Enable" } },
  { label: "SMT Off", values: { "SMT Control": "Disable" } },
  { label: "Determinism: Performance", values: { "Determinism": "Performance" } },
  { label: "Determinism: Power", values: { "Determinism": "Power" } },
  { label: "IOMMU On", values: { "IOMMU": "Enabled" } },
  { label: "IOMMU Off", values: { "IOMMU": "Disabled" } },
  { label: "SVM On", values: { "SVM Mode": "Enabled" } },
  { label: "SVM Off", values: { "SVM Mode": "Disabled" } },
];

// ── Job progress panel ────────────────────────────────────────────────────────

function JobPanel({ jobId, onClose, onCompleted, kind }: { jobId: string; onClose: () => void; onCompleted?: () => void; kind?: string }) {
  const [done, setDone] = useState(false);

  const { data } = useQuery<BiosJob | any>({
    queryKey: ["bios-job", jobId],
    queryFn: () => kind === "batch" ? fleetApi.biosBatchStatus(jobId) : fleetApi.biosJob(jobId),
    refetchInterval: done ? false : 3000,
  });

  useEffect(() => {
    if (data?.status === "completed" || data?.status === "failed") {
      setDone(true);
      if (data?.status === "completed") onCompleted?.();
    }
  }, [data?.status]);

  const statusColor =
    data?.status === "completed" ? "text-green-400"
    : data?.status === "failed" ? "text-red-400"
    : data?.status === "running" ? "text-blue-400"
    : "text-text-muted";

  const isRunning = !done && data?.status === "running";

  return (
    <div className="card border border-surface-2 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {data?.status === "completed" ? <CheckCircle size={14} className="text-green-400" />
            : data?.status === "failed" ? <XCircle size={14} className="text-red-400" />
            : <Loader2 size={14} className={`${statusColor} ${isRunning ? "animate-spin" : ""}`} />}
          <span className="text-sm font-semibold">Job {jobId.slice(0, 8)}…</span>
          <span className={`text-xs font-mono uppercase ${statusColor}`}>{data?.status ?? "pending"}</span>
        </div>
        <button onClick={onClose} className="text-text-muted hover:text-text-primary text-xs">dismiss</button>
      </div>
      {/* Batch job: show per-server summary */}
      {data?.summary && (
        <div className="text-xs text-text-muted bg-surface-2 rounded p-2 space-y-0.5">
          <p>Total: {data.summary.total} · SSH OK: {data.summary.ssh_ok} · Flashed: {data.summary.flashed} · Missing: {data.summary.missing}</p>
          {data.missing?.length > 0 && <p className="text-amber-400">Not found: {data.missing.join(", ")}</p>}
        </div>
      )}
      {data?.servers && data.servers.length > 0 && (
        <div className="bg-surface-2 rounded p-2 max-h-48 overflow-y-auto space-y-0.5">
          {data.servers.map((s: any, i: number) => (
            <p key={i} className="text-xs font-mono text-text-muted">
              <span className="text-text-primary">{s.hostname}</span>
              {" — "}{s.stage}
              {s.bios_before && s.bios_after && s.bios_before !== s.bios_after
                ? <span className="text-green-400"> {s.bios_before}→{s.bios_after}</span>
                : s.bios_after ? <span> {s.bios_after}</span> : null}
              {s.note ? <span className="text-amber-400"> ({s.note})</span> : null}
            </p>
          ))}
        </div>
      )}
      {/* Single-server job */}
      {data?.result && !data?.servers && (
        <p className="text-xs text-text-muted font-mono bg-surface-2 rounded p-2 whitespace-pre-wrap">
          {typeof data.result === "string" ? data.result : JSON.stringify(data.result, null, 2)}
        </p>
      )}
      {data?.logs && data.logs.length > 0 && (
        <div className="bg-surface-2 rounded p-2 max-h-48 overflow-y-auto space-y-0.5">
          {data.logs.map((line: string, i: number) => (
            <p key={i} className="text-xs font-mono text-text-muted leading-relaxed">{line}</p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Attribute row in upgrade table ────────────────────────────────────────────

function AttributeRow({
  attr,
  pendingChange,
  onSet,
}: {
  attr: BiosAttribute;
  pendingChange: string | null;
  onSet: (question: string, value: string) => void;
}) {
  const q = attr["Setup Question"];
  const opts = attr.Options ?? [];
  const current = pendingChange ?? attr.Value;
  const changed = pendingChange !== null && pendingChange !== attr.Value;

  return (
    <tr className={`border-b border-surface-2 hover:bg-surface-2/30 ${changed ? "bg-amber-950/20" : ""}`}>
      <td className="px-4 py-2 text-xs font-mono text-text-primary">{q}</td>
      <td className="px-4 py-2 text-xs text-text-muted max-w-xs truncate" title={attr["Help String"] ?? ""}>
        {attr["Help String"] ?? "—"}
      </td>
      <td className="px-4 py-2 text-xs font-mono text-text-muted">{attr.Value}</td>
      <td className="px-4 py-2">
        {opts.length > 0 ? (
          <select
            value={current}
            onChange={(e) => onSet(q, e.target.value)}
            className="text-xs bg-surface-2 border border-surface-2 rounded px-2 py-1 text-text-primary focus:outline-none focus:border-blue-500"
          >
            {opts.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        ) : (
          <input
            value={current}
            onChange={(e) => onSet(q, e.target.value)}
            className="text-xs bg-surface-2 border border-surface-2 rounded px-2 py-1 text-text-primary font-mono w-40 focus:outline-none focus:border-blue-500"
          />
        )}
      </td>
      <td className="px-4 py-2">
        {changed && <span className="text-xs text-amber-400 font-semibold">modified</span>}
      </td>
    </tr>
  );
}

// ── Compliance view: Baseline (Config A, pre-flash) vs Patch (Config B, post-flash) ──
function ComplianceView() {
  const { data, isLoading } = useQuery({ queryKey: ["bios-compare"], queryFn: () => fleetApi.getBiosCompare(), refetchInterval: 60_000 });
  // Default to Security Patch Team — the team whose compliance is tracked here
  const [fTeam, setFTeam] = useState("Security Patch Team");
  const [fFamily, setFFamily] = useState("");
  const [onlyChanged, setOnlyChanged] = useState(false);
  const [sortChanged, setSortChanged] = useState(true); // changed servers first

  const servers: any[] = data?.servers ?? [];
  const teams = Array.from(new Set(servers.map((s) => s.team).filter(Boolean))).sort();
  const families = Array.from(new Set(servers.map((s) => s.family).filter(Boolean))).sort();

  const rows = servers
    .filter((s) =>
      (!fTeam || s.team === fTeam) && (!fFamily || s.family === fFamily) &&
      (!onlyChanged || s.bios_changed || s.microcode_changed)
    )
    .sort((a: any, b: any) => {
      // Changed servers first when sortChanged is on
      if (sortChanged) {
        const aC = a.bios_changed || a.microcode_changed ? 1 : 0;
        const bC = b.bios_changed || b.microcode_changed ? 1 : 0;
        if (bC !== aC) return bC - aC;
      }
      return (a.hostname ?? "").localeCompare(b.hostname ?? "");
    });
  const summary = data?.summary ?? { total: 0, changed: 0, awaiting_patch: 0 };

  if (isLoading || !data) {
    return <div className="flex justify-center py-16"><div className="animate-spin rounded-full h-7 w-7 border-b-2 border-blue-400" /></div>;
  }

  const Cell = ({ a, b, changed }: { a: string; b: string; changed: boolean }) => (
    <td className="px-3 py-2 font-mono text-xs">
      <span className="text-text-muted">{a}</span>
      <span className="mx-1 text-text-muted">→</span>
      <span className={changed ? "text-amber-400 font-semibold" : "text-text-primary"}>{b}</span>
    </td>
  );

  return (
    <div className="space-y-5">
      <div className="text-sm text-text-muted">
        Config <b className="text-text-primary">A (Baseline)</b> = BIOS captured before the last flash ·
        Config <b className="text-text-primary">B (Patch)</b> = BIOS after the flash. Captured automatically on every flash.
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card"><p className="metric-label">With History</p><p className="metric-value">{summary.total}</p></div>
        <div className="card"><p className="metric-label">Changed (A→B)</p><p className="metric-value text-amber-400">{summary.changed}</p></div>
        <div className="card"><p className="metric-label">Awaiting Patch</p><p className="metric-value text-text-muted">{summary.awaiting_patch}</p></div>
      </div>

      {/* Filters */}
      <div className="card p-3 flex flex-wrap gap-3 items-end">
        <Filter label="Team" value={fTeam} set={setFTeam} opts={teams} />
        <Filter label="Family" value={fFamily} set={setFFamily} opts={families} />
        <label className="flex items-center gap-2 text-xs text-text-muted cursor-pointer">
          <input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} />
          Only changed
        </label>
        <label className="flex items-center gap-2 text-xs text-text-muted cursor-pointer">
          <input type="checkbox" checked={sortChanged} onChange={(e) => setSortChanged(e.target.checked)} />
          Changed first
        </label>
        {(fFamily || onlyChanged) && (
          <button onClick={() => { setFTeam("Security Patch Team"); setFFamily(""); setOnlyChanged(false); }}
            className="text-xs text-text-muted hover:text-text-primary border border-surface-2 rounded px-3 py-1.5">Reset filters</button>
        )}
        <ExportButton
          endpoint="/export/compliance"
          params={{ team: fTeam || undefined, family: fFamily || undefined }}
          label="Export CSV"
          className="ml-auto"
        />
      </div>

      {/* A/B comparison table */}
      <div className="card p-0 overflow-x-auto">
        <h3 className="text-sm font-semibold text-text-secondary p-4 pb-2">Baseline (A) vs Patch (B)</h3>
        <table className="w-full text-sm">
          <thead><tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
            <th className="px-4 py-2">Server</th><th className="px-3 py-2">Team</th><th className="px-3 py-2">Family</th>
            <th className="px-3 py-2">BIOS (A→B)</th><th className="px-3 py-2">Microcode (A→B)</th><th className="px-3 py-2">BMC (A→B)</th><th className="px-3 py-2">Status</th>
          </tr></thead>
          <tbody>
            {rows.map((srv) => {
              const changed = srv.bios_changed || srv.microcode_changed;
              return (
                <tr key={srv.id} className="border-b border-surface-2 hover:bg-surface-2/40">
                  <td className="px-4 py-2 font-mono">{srv.hostname}</td>
                  <td className="px-3 py-2 text-text-muted">{srv.team ?? "—"}</td>
                  <td className="px-3 py-2">{srv.family ?? "—"}</td>
                  <Cell a={srv.baseline_bios} b={srv.patch_bios} changed={srv.bios_changed} />
                  <Cell a={srv.baseline_microcode} b={srv.patch_microcode} changed={srv.microcode_changed} />
                  <Cell a={srv.baseline_bmc} b={srv.patch_bmc} changed={srv.bmc_changed} />
                  <td className="px-3 py-2">
                    {!srv.has_patch
                      ? <span className="text-text-muted">baseline only</span>
                      : changed
                        ? <span className="text-amber-400 flex items-center gap-1"><AlertTriangle size={12} /> Changed</span>
                        : <span className="text-green-400">✓ Same</span>}
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-text-muted">
              No BIOS history yet. Flash a server (Patch tab) — its before/after config is captured automatically and appears here.
            </td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Filter({ label, value, set, opts }: { label: string; value: string; set: (v: string) => void; opts: string[] }) {
  return (
    <div>
      <label className="text-xs text-text-muted mb-1 block">{label}</label>
      <select value={value} onChange={(e) => set(e.target.value)}
        className="text-xs bg-surface-2 border border-surface-2 rounded px-2 py-1.5 focus:outline-none min-w-28">
        <option value="">All {label}</option>
        {opts.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function BiosPage() {
  const [tab, setTab] = useState<"patch" | "upgrade" | "compliance">("patch");

  // Filters
  const [filterTeam, setFilterTeam] = useState("");
  const [filterFamily, setFilterFamily] = useState("");
  const [filterBios, setFilterBios] = useState("");
  const [filterVariant, setFilterVariant] = useState("");  // Turin Classic | Turin Dense (from cpu_model)
  const [search, setSearch] = useState("");

  // Patch — server selection
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [biosUrl, setBiosUrl] = useState("");
  const [biosFile, setBiosFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Jobs
  const [jobs, setJobs] = useState<{ id: string; serverId?: string; kind?: string }[]>([]);

  // Per-server OS credential overrides (entered inline before verify/flash).
  // creds[serverId] = { os_ip, os_user, os_pwd }
  const [creds, setCreds] = useState<Record<string, { os_ip: string; os_user: string; os_pwd: string }>>({});
  const setCred = (sid: string, key: "os_ip" | "os_user" | "os_pwd", val: string) =>
    setCreds((p) => ({ ...p, [sid]: { os_ip: "", os_user: "amd", os_pwd: "amd123", ...p[sid], [key]: val } }));
  // Track which servers passed verify (gates the Flash button) + which row's creds are open
  const [verified, setVerified] = useState<Record<string, boolean>>({});
  const [credRowOpen, setCredRowOpen] = useState<Record<string, boolean>>({});

  // Upgrade
  const [upgradeServer, setUpgradeServer] = useState<BiosServer | null>(null);
  const [attrSearch, setAttrSearch] = useState("");
  const [pendingChanges, setPendingChanges] = useState<Record<string, string>>({});
  const [presetMsg, setPresetMsg] = useState<string | null>(null);
  // before→after diff shown after an Apply (snapshot of changed knobs pre/post)
  const [tuneDiff, setTuneDiff] = useState<{ knob: string; before: string; after: string }[] | null>(null);

  // ── Queries ───────────────────────────────────────────────────────────────

  const { data: serversData, isLoading } = useQuery({
    queryKey: ["bios-servers", filterTeam, filterFamily, filterBios],
    queryFn: () => fleetApi.biosServers({
      team: filterTeam || undefined,
      family: filterFamily || undefined,
      bios_version: filterBios || undefined,
    }),
    refetchInterval: 60_000,
  });

  const { data: biosHealth } = useQuery({
    queryKey: ["bios-health"],
    queryFn: fleetApi.biosHealth,
    retry: false,
    staleTime: 60_000,
  });

  const { data: attrData, isLoading: attrLoading, error: attrError } = useQuery({
    queryKey: ["bios-attrs", upgradeServer?.id],
    queryFn: async () => {
      if (!upgradeServer) throw new Error("No server");
      // If user entered credential overrides, save them first via verify endpoint before reading attrs
      const c = creds[upgradeServer.id];
      if (c?.os_ip && c.os_ip !== upgradeServer.os_ip) {
        // Persist the OS IP override so the backend uses it
        const fd = new FormData();
        fd.append("os_ip", c.os_ip);
        fd.append("os_user", c.os_user || "amd");
        fd.append("os_pwd", c.os_pwd || "amd123");
        await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/bios/${upgradeServer.id}/verify`, {
          method: "POST", body: fd,
          headers: { Authorization: `Bearer ${localStorage.getItem("helios_jwt") ?? ""}` },
        }).catch(() => {}); // best-effort persist
      }
      return fleetApi.biosAttributes(upgradeServer.id);
    },
    enabled: !!upgradeServer && tab === "upgrade",
    staleTime: 0,
    retry: false,
  });

  const servers: BiosServer[] = serversData?.servers ?? [];
  const filters = serversData?.filters ?? { teams: [], families: [], bios_versions: [] };

  const filtered = servers.filter((s) => {
    // Turin Classic / Turin Dense live in cpu_model, not family
    if (filterVariant && !(s.cpu_model ?? "").toLowerCase().includes(filterVariant.toLowerCase())) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      s.hostname.toLowerCase().includes(q) ||
      (s.bios_version ?? "").toLowerCase().includes(q) ||
      (s.family ?? "").toLowerCase().includes(q) ||
      (s.cpu_model ?? "").toLowerCase().includes(q) ||
      (s.team ?? "").toLowerCase().includes(q)
    );
  });

  const attributes: BiosAttribute[] = attrData?.bios_attributes?.Data ?? [];
  const filteredAttrs = attributes.filter(
    (a) =>
      !attrSearch ||
      a["Setup Question"].toLowerCase().includes(attrSearch.toLowerCase()) ||
      (a["Help String"] ?? "").toLowerCase().includes(attrSearch.toLowerCase()),
  );

  // ── Mutations ─────────────────────────────────────────────────────────────

  const qc = useQueryClient();
  const addJob = (jobId: string, serverId?: string, kind?: string) =>
    setJobs((p) => [{ id: jobId, serverId, kind }, ...p]);

  // Re-read the applied BIOS version from the BMC and propagate it app-wide.
  const refreshMut = useMutation({
    mutationFn: (serverId: string) => fleetApi.biosRefresh(serverId),
    onSuccess: () => {
      // Refresh every view that shows BIOS/firmware so the new version appears everywhere.
      qc.invalidateQueries({ queryKey: ["bios-servers"] });
      qc.invalidateQueries({ queryKey: ["servers"] });
      qc.invalidateQueries({ queryKey: ["firmware"] });
      qc.invalidateQueries({ queryKey: ["inventory"] });
    },
  });

  // Append inline OS credential overrides (if entered) to the request.
  const appendCreds = (fd: FormData, serverId: string) => {
    const c = creds[serverId];
    if (c?.os_ip) fd.append("os_ip", c.os_ip);
    fd.append("os_user", c?.os_user || "amd");
    fd.append("os_pwd", c?.os_pwd || "amd123");
  };

  const flashMut = useMutation({
    mutationFn: async (serverId: string) => {
      const fd = new FormData();
      if (biosFile) fd.append("file", biosFile);
      else if (biosUrl) fd.append("bios_file_url", biosUrl);
      else throw new Error("Provide a file or URL");
      appendCreds(fd, serverId);
      const res = await fleetApi.biosFlash(serverId, fd);
      return { serverId, res };
    },
    onSuccess: ({ serverId, res }) => { if (res?.job_id) addJob(res.job_id, serverId, "flash"); },
  });

  // Bulk flash via batch-update: resolves server names, does SSH-check + PRISM refresh
  // fallback, then flashes using stored creds (amd/amd123 default). Returns a single
  // batch job_id to poll rather than one job per server.
  const bulkFlashMut = useMutation({
    mutationFn: () => {
      if (!biosUrl) throw new Error("URL required for bulk flash");
      const names = Array.from(selected).map(
        (id) => servers.find((s) => s.id === id)?.hostname ?? id
      ).filter(Boolean);
      return fleetApi.biosBatchUpdate(names, biosUrl, true);
    },
    onSuccess: (data) => {
      if (data?.batch_job_id) addJob(data.batch_job_id, undefined, "batch");
      setSelected(new Set());
    },
  });

  // Bulk refresh: re-read applied BIOS version from BMC for all ticked servers.
  const [bulkRefreshing, setBulkRefreshing] = useState(false);
  const bulkRefreshMut = useMutation({
    mutationFn: async () => {
      const ids = Array.from(selected);
      setBulkRefreshing(true);
      const results = await Promise.allSettled(ids.map((id) => fleetApi.biosRefresh(id)));
      return { total: ids.length, ok: results.filter((r) => r.status === "fulfilled").length };
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bios-servers"] });
      qc.invalidateQueries({ queryKey: ["servers"] });
      qc.invalidateQueries({ queryKey: ["firmware"] });
      qc.invalidateQueries({ queryKey: ["inventory"] });
    },
    onSettled: () => setBulkRefreshing(false),
  });

  const verifyMut = useMutation({
    mutationFn: async (serverId: string) => {
      const fd = new FormData();
      if (biosFile) fd.append("file", biosFile);
      else if (biosUrl) fd.append("bios_file_url", biosUrl);
      else throw new Error("Provide a file or URL");
      appendCreds(fd, serverId);
      const res = await fleetApi.biosVerify(serverId, fd);
      return { serverId, res };
    },
    onSuccess: ({ serverId, res }) => {
      if (res?.job_id) addJob(res.job_id);
      // Unlock Flash for this server once verify has been submitted/checked.
      setVerified((p) => ({ ...p, [serverId]: true }));
    },
  });

  const updateAttrMut = useMutation({
    mutationFn: () => {
      if (!upgradeServer) throw new Error("No server selected");
      const attrs = Object.entries(pendingChanges).map(([q, v]) => ({
        "Setup Question": q, Value: v,
      }));
      return fleetApi.biosUpdateAttributes(upgradeServer.id, attrs);
    },
    onSuccess: (data) => {
      if (data?.job_id) addJob(data.job_id);
      // Build a before→after audit from the staged changes (before = live value, after = staged).
      const liveByQ: Record<string, string> = {};
      for (const a of attributes) liveByQ[a["Setup Question"]] = a.Value;
      const diff = Object.entries(pendingChanges).map(([knob, after]) => ({
        knob, before: liveByQ[knob] ?? "—", after,
      }));
      setTuneDiff(diff);
      setPendingChanges({});
      setPresetMsg(null);
      // Re-read live attributes so the table reflects the applied values once the job lands.
      if (upgradeServer) qc.invalidateQueries({ queryKey: ["bios-attrs", upgradeServer.id] });
    },
  });

  const resetMut = useMutation({
    mutationFn: (serverId: string) => fleetApi.biosReset(serverId),
    onSuccess: (data) => { if (data?.job_id) addJob(data.job_id); },
  });

  // ── Helpers ───────────────────────────────────────────────────────────────

  const toggleSelect = (id: string) =>
    setSelected((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const toggleAll = () =>
    setSelected(selected.size === filtered.length ? new Set() : new Set(filtered.map((s) => s.id)));

  const credsBadge = (srv: BiosServer) =>
    srv.has_bmc_creds && srv.has_os_creds
      ? <span className="text-green-400 text-xs">✓</span>
      : <span className="text-amber-400 text-xs" title="Missing credentials">⚠</span>;

  const changedCount = Object.keys(pendingChanges).length;

  // Stage a tuning preset: match preset knobs against this server's live attribute list
  // (case-insensitive on the Setup Question) and queue the values that actually exist.
  const applyPreset = (preset: { label: string; values: Record<string, string> }) => {
    const staged: Record<string, string> = {};
    const unmatched: string[] = [];
    for (const [knob, val] of Object.entries(preset.values)) {
      const match = attributes.find((a) =>
        a["Setup Question"].toLowerCase().replace(/[^a-z0-9]/g, "")
          .includes(knob.toLowerCase().replace(/[^a-z0-9]/g, "")));
      if (match) staged[match["Setup Question"]] = val;
      else unmatched.push(knob);
    }
    if (Object.keys(staged).length === 0) {
      setPresetMsg(`Preset "${preset.label}": none of these knobs exist on this server`);
      return;
    }
    setPendingChanges((p) => ({ ...p, ...staged }));
    setPresetMsg(`Staged ${Object.keys(staged).length} setting(s) from "${preset.label}"${unmatched.length ? ` · skipped ${unmatched.length} not present` : ""}`);
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Cpu size={18} /> Firmware &amp; BIOS
          </h1>
          <p className="text-sm text-text-muted">
            Patch: flash firmware · Upgrade: tune settings · Compliance: versions vs baseline
          </p>
        </div>
        {biosHealth && (
          biosHealth.reachable
            ? <span className="flex items-center gap-1 text-xs text-green-400"><CheckCircle size={12} /> BIOS API online</span>
            : <span className="flex items-center gap-1 text-xs text-red-400"><XCircle size={12} /> BIOS API offline</span>
        )}
      </div>

      {/* Active job panels */}
      {jobs.length > 0 && (
        <div className="space-y-2">
          {jobs.slice(0, 5).map((j) => (
            <JobPanel key={j.id} jobId={j.id} kind={j.kind}
              onClose={() => setJobs((p) => p.filter((x) => x.id !== j.id))}
              onCompleted={() => {
                if (j.kind === "flash" && j.serverId) refreshMut.mutate(j.serverId);
                // After batch completes, refresh BIOS server list
                if (j.kind === "batch") qc.invalidateQueries({ queryKey: ["bios-servers"] });
              }}
            />
          ))}
        </div>
      )}

      {/* Sub-tabs */}
      <div className="flex gap-1 border-b border-surface-2">
        {(["patch", "upgrade", "compliance"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-text-muted hover:text-text-primary"
            }`}
          >
            {t === "patch" ? "Patch (Flash Firmware)" : t === "upgrade" ? "Upgrade (Tune Settings)" : "Compliance (A/B Compare)"}
          </button>
        ))}
      </div>

      {/* ── COMPLIANCE TAB (merged from Firmware) ──────────────────────────── */}
      {tab === "compliance" && <ComplianceView />}

      {/* ── PATCH TAB ──────────────────────────────────────────────────────── */}
      {tab === "patch" && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="card p-3 flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-40">
              <label className="text-xs text-text-muted mb-1 block">Search</label>
              <div className="relative">
                <Search size={12} className="absolute left-2.5 top-2.5 text-text-muted" />
                <input value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="hostname, family, team…"
                  className="w-full pl-7 pr-3 py-1.5 text-xs bg-surface-2 border border-surface-2 rounded focus:outline-none focus:border-blue-500" />
              </div>
            </div>
            <div>
              <label className="text-xs text-text-muted mb-1 block">Team</label>
              <select value={filterTeam} onChange={(e) => setFilterTeam(e.target.value)}
                className="text-xs bg-surface-2 border border-surface-2 rounded px-2 py-1.5 focus:outline-none">
                <option value="">All Teams</option>
                {filters.teams.map((t: string) => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-text-muted mb-1 block">Family</label>
              <select value={filterFamily} onChange={(e) => setFilterFamily(e.target.value)}
                className="text-xs bg-surface-2 border border-surface-2 rounded px-2 py-1.5 focus:outline-none">
                <option value="">All Families</option>
                {filters.families.map((f: string) => <option key={f}>{f}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-text-muted mb-1 block">Turin Variant</label>
              <select value={filterVariant} onChange={(e) => setFilterVariant(e.target.value)}
                className="text-xs bg-surface-2 border border-surface-2 rounded px-2 py-1.5 focus:outline-none">
                <option value="">All Turin</option>
                <option value="Turin Classic">Turin Classic</option>
                <option value="Turin Dense">Turin Dense</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-text-muted mb-1 block">BIOS Version</label>
              <select value={filterBios} onChange={(e) => setFilterBios(e.target.value)}
                className="text-xs bg-surface-2 border border-surface-2 rounded px-2 py-1.5 focus:outline-none">
                <option value="">All Versions</option>
                {filters.bios_versions.map((v: string) => <option key={v}>{v}</option>)}
              </select>
            </div>
          </div>

          {/* Firmware source */}
          <div className="card p-4 space-y-3">
            <p className="text-sm font-semibold">Firmware Source</p>
            <div className="flex gap-3 items-end flex-wrap">
              <div className="flex-1 min-w-64">
                <label className="text-xs text-text-muted mb-1 flex items-center gap-1 block">
                  <Link size={10} /> URL (.tar.gz or .fd)
                </label>
                <input value={biosUrl}
                  onChange={(e) => { setBiosUrl(e.target.value); setBiosFile(null); }}
                  placeholder="http://internal-server/bios/RVOT100AA.tar.gz"
                  className="w-full px-3 py-1.5 text-xs bg-surface-2 border border-surface-2 rounded focus:outline-none focus:border-blue-500 font-mono" />
              </div>
              <div>
                <label className="text-xs text-text-muted mb-1 flex items-center gap-1 block">
                  <Upload size={10} /> Upload file
                </label>
                <button onClick={() => fileRef.current?.click()}
                  className="px-3 py-1.5 text-xs bg-surface-2 border border-surface-2 rounded hover:bg-surface-2/80 flex items-center gap-1">
                  <Upload size={11} />
                  {biosFile ? biosFile.name : "Choose file…"}
                </button>
                <input ref={fileRef} type="file" accept=".gz,.tgz,.fd,application/gzip,application/octet-stream,*/*" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) { setBiosFile(f); setBiosUrl(""); } }} />
              </div>
            </div>
            {biosFile && (
              <p className="text-xs text-blue-400">
                {biosFile.name} ({(biosFile.size / 1024 / 1024).toFixed(1)} MB)
              </p>
            )}
          </div>

          {/* Bulk action bar */}
          {selected.size > 0 && (
            <div className="card p-3 flex items-center gap-3 flex-wrap bg-blue-950/30 border border-blue-800/40">
              <span className="text-sm font-semibold text-blue-300">
                {selected.size} server{selected.size !== 1 ? "s" : ""} selected
              </span>
              {!biosUrl && <span className="text-xs text-amber-400">Add URL above for bulk flash</span>}
              <div className="flex gap-2 ml-auto">
                <button disabled={bulkRefreshing}
                  title="Re-read applied BIOS version from BMC for all selected servers"
                  onClick={() => bulkRefreshMut.mutate()}
                  className="px-3 py-1.5 text-xs bg-green-700 hover:bg-green-600 disabled:opacity-50 rounded flex items-center gap-1 font-semibold">
                  {bulkRefreshing ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                  Bulk Refresh
                </button>
                <button disabled={bulkFlashMut.isPending || !biosUrl}
                  onClick={() => bulkFlashMut.mutate()}
                  className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded flex items-center gap-1 font-semibold">
                  {bulkFlashMut.isPending ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
                  Bulk Flash
                </button>
                <button onClick={() => setSelected(new Set())}
                  className="px-3 py-1.5 text-xs bg-surface-2 hover:bg-surface-2/80 rounded">Clear</button>
              </div>
              {bulkRefreshMut.data && (
                <span className="text-xs text-green-300 w-full">
                  ✓ Refreshed {bulkRefreshMut.data.ok}/{bulkRefreshMut.data.total} servers — applied BIOS versions updated.
                </span>
              )}
            </div>
          )}

          {/* Server table */}
          <div className="card p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
                  <th className="px-3 py-2 w-8">
                    <input type="checkbox"
                      checked={filtered.length > 0 && selected.size === filtered.length}
                      onChange={toggleAll} className="rounded" />
                  </th>
                  <th className="px-3 py-2">Server</th>
                  <th className="px-3 py-2">Team</th>
                  <th className="px-3 py-2">Family</th>
                  <th className="px-3 py-2">BIOS</th>
                  <th className="px-3 py-2">BMC FW</th>
                  <th className="px-3 py-2">Creds</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={8} className="text-center py-10 text-text-muted text-xs">
                    <Loader2 size={16} className="animate-spin inline mr-2" />Loading…
                  </td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={8} className="text-center py-10 text-text-muted text-xs">No servers match filters</td></tr>
                ) : filtered.map((srv) => (
                  <Fragment key={srv.id}>
                  <tr className="border-b border-surface-2 hover:bg-surface-2/30">
                    <td className="px-3 py-2">
                      <input type="checkbox" checked={selected.has(srv.id)}
                        onChange={() => toggleSelect(srv.id)} className="rounded" />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{srv.hostname}</td>
                    <td className="px-3 py-2 text-xs text-text-muted">{srv.team ?? "—"}</td>
                    <td className="px-3 py-2 text-xs text-text-muted">{srv.family ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{srv.bios_version ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs text-text-muted">{srv.bmc_firmware ?? "—"}</td>
                    <td className="px-3 py-2">{credsBadge(srv)}</td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1 flex-wrap items-center">
                        <button title="Enter OS IP & credentials"
                          onClick={() => {
                            setCredRowOpen((p) => ({ ...p, [srv.id]: !p[srv.id] }));
                            if (!creds[srv.id] && srv.os_ip) setCred(srv.id, "os_ip", srv.os_ip);
                          }}
                          className={`px-2 py-1 text-xs rounded flex items-center gap-1 ${credRowOpen[srv.id] ? "bg-blue-600/30 text-blue-300" : "bg-surface-2 hover:bg-surface-2/80"}`}>
                          <Settings2 size={10} /> Creds
                        </button>
                        <button title="Step 1 — Verify compatibility"
                          disabled={verifyMut.isPending || (!biosUrl && !biosFile)}
                          onClick={() => verifyMut.mutate(srv.id)}
                          className="px-2 py-1 text-xs rounded bg-surface-2 hover:bg-surface-2/80 disabled:opacity-40 flex items-center gap-1">
                          {verifyMut.isPending && verifyMut.variables === srv.id ? <Loader2 size={10} className="animate-spin" /> : <CheckCircle size={10} />} Verify
                        </button>
                        <button title={verified[srv.id] ? "Step 2 — Flash BIOS" : "Verify first to enable Flash"}
                          disabled={flashMut.isPending || (!biosUrl && !biosFile) || !verified[srv.id]}
                          onClick={() => {
                            if (confirm(`⚠ Flash BIOS on ${srv.hostname}?\n\nThis writes firmware to live hardware and will reboot the server. This cannot be undone. Continue?`))
                              flashMut.mutate(srv.id);
                          }}
                          className="px-2 py-1 text-xs rounded bg-blue-700 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1">
                          <Zap size={10} /> Flash
                          {verified[srv.id] && <CheckCircle size={9} className="text-green-300" />}
                        </button>
                        <button title="Re-read applied BIOS version from BMC (use after a flash)"
                          disabled={refreshMut.isPending && refreshMut.variables === srv.id}
                          onClick={() => refreshMut.mutate(srv.id)}
                          className="px-2 py-1 text-xs rounded bg-surface-2 hover:bg-green-900/40 disabled:opacity-40 flex items-center gap-1 text-text-muted hover:text-green-300">
                          {refreshMut.isPending && refreshMut.variables === srv.id ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />} Refresh
                        </button>
                        <button title="Reset to factory defaults"
                          disabled={resetMut.isPending}
                          onClick={() => {
                            if (confirm(`Reset BIOS on ${srv.hostname} to factory defaults?`))
                              resetMut.mutate(srv.id);
                          }}
                          className="px-2 py-1 text-xs rounded bg-surface-2 hover:bg-red-900/60 disabled:opacity-40 flex items-center gap-1 text-text-muted hover:text-red-300">
                          <RotateCcw size={10} /> Reset
                        </button>
                      </div>
                    </td>
                  </tr>
                  {credRowOpen[srv.id] && (
                    <tr className="bg-surface-2/20 border-b border-surface-2">
                      <td colSpan={8} className="px-3 py-2">
                        <div className="flex flex-wrap items-end gap-2 text-xs">
                          <span className="text-text-muted">OS credentials for verify/flash:</span>
                          <div>
                            <label className="block text-[10px] text-text-muted mb-0.5">OS IP {srv.os_ip ? `(network: ${srv.os_ip})` : ""}</label>
                            <input value={creds[srv.id]?.os_ip ?? ""} onChange={(e) => setCred(srv.id, "os_ip", e.target.value)}
                              placeholder={srv.os_ip ?? "10.x.x.x"}
                              className="bg-surface border border-surface-2 rounded px-2 py-1 w-36 focus:outline-none focus:border-blue-500" />
                          </div>
                          <div>
                            <label className="block text-[10px] text-text-muted mb-0.5">OS User</label>
                            <input value={creds[srv.id]?.os_user ?? "amd"} onChange={(e) => setCred(srv.id, "os_user", e.target.value)}
                              className="bg-surface border border-surface-2 rounded px-2 py-1 w-28 focus:outline-none focus:border-blue-500" />
                          </div>
                          <div>
                            <label className="block text-[10px] text-text-muted mb-0.5">OS Password</label>
                            <input type="password" value={creds[srv.id]?.os_pwd ?? "amd123"} onChange={(e) => setCred(srv.id, "os_pwd", e.target.value)}
                              placeholder="••••••"
                              className="bg-surface border border-surface-2 rounded px-2 py-1 w-32 focus:outline-none focus:border-blue-500" />
                          </div>
                          {srv.os_ip && (
                            <button onClick={() => setCred(srv.id, "os_ip", srv.os_ip!)}
                              className="px-2 py-1 rounded bg-surface-2 hover:bg-surface-2/80 text-text-muted">Use network IP</button>
                          )}
                          <span className="text-[10px] text-text-muted ml-auto">Step 1: enter creds → Verify → Step 2: Flash unlocks</span>
                        </div>
                      </td>
                    </tr>
                  )}
                  </Fragment>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-text-muted p-3 border-t border-surface-2">
              {filtered.length} servers · {selected.size} selected
            </p>
          </div>
        </div>
      )}

      {/* ── UPGRADE TAB ──────────────────────────────────────────────────────── */}
      {tab === "upgrade" && (
        <div className="space-y-4">
          <p className="text-sm text-text-muted">
            Select a server to read its live BIOS settings, then edit and apply tuning changes.
          </p>

          {/* Filters */}
          <div className="card p-3 flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-40">
              <label className="text-xs text-text-muted mb-1 block">Search</label>
              <div className="relative">
                <Search size={12} className="absolute left-2.5 top-2.5 text-text-muted" />
                <input value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="hostname, family, team…"
                  className="w-full pl-7 pr-3 py-1.5 text-xs bg-surface-2 border border-surface-2 rounded focus:outline-none focus:border-blue-500" />
              </div>
            </div>
            <div>
              <label className="text-xs text-text-muted mb-1 block">Team</label>
              <select value={filterTeam} onChange={(e) => setFilterTeam(e.target.value)}
                className="text-xs bg-surface-2 border border-surface-2 rounded px-2 py-1.5 focus:outline-none">
                <option value="">All Teams</option>
                {filters.teams.map((t: string) => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-text-muted mb-1 block">Family</label>
              <select value={filterFamily} onChange={(e) => setFilterFamily(e.target.value)}
                className="text-xs bg-surface-2 border border-surface-2 rounded px-2 py-1.5 focus:outline-none">
                <option value="">All Families</option>
                {filters.families.map((f: string) => <option key={f}>{f}</option>)}
              </select>
            </div>
          </div>

          {/* Server picker */}
          <div className="card p-0 overflow-x-auto max-h-64 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface">
                <tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
                  <th className="px-3 py-2">Server</th>
                  <th className="px-3 py-2">Team</th>
                  <th className="px-3 py-2">Family</th>
                  <th className="px-3 py-2">BIOS</th>
                  <th className="px-3 py-2">Creds</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && (
                  <tr><td colSpan={5} className="text-center py-8 text-text-muted text-xs">No servers</td></tr>
                )}
                {filtered.map((srv) => (
                  <tr key={srv.id}
                    onClick={() => { setUpgradeServer(srv); setPendingChanges({}); setAttrSearch(""); }}
                    className={`border-b border-surface-2 cursor-pointer ${
                      upgradeServer?.id === srv.id
                        ? "bg-blue-600/20"
                        : "hover:bg-surface-2/40"
                    }`}>
                    <td className="px-3 py-2 font-mono text-xs">{srv.hostname}</td>
                    <td className="px-3 py-2 text-xs text-text-muted">{srv.team ?? "—"}</td>
                    <td className="px-3 py-2 text-xs text-text-muted">{srv.family ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{srv.bios_version ?? "—"}</td>
                    <td className="px-3 py-2">{credsBadge(srv)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Attribute editor */}
          {upgradeServer && (
            <div className="space-y-3">
              {/* Credential warning + inline override */}
              {(!upgradeServer.has_os_creds || !upgradeServer.os_ip) && (
                <div className="card p-3 border border-amber-400/30 bg-amber-400/5 space-y-2">
                  <p className="text-xs text-amber-400 font-semibold flex items-center gap-1.5">
                    <AlertTriangle size={13} />
                    {!upgradeServer.os_ip
                      ? "No OS IP — needed to read BIOS attributes via SCELNX"
                      : "OS credentials missing — enter below to enable attribute read"}
                  </p>
                  <div className="flex flex-wrap gap-2 items-end">
                    <div>
                      <label className="text-[10px] text-text-muted block mb-0.5">OS IP</label>
                      <input value={creds[upgradeServer.id]?.os_ip ?? upgradeServer.os_ip ?? ""}
                        onChange={(e) => setCred(upgradeServer.id, "os_ip", e.target.value)}
                        placeholder="10.x.x.x"
                        className="bg-surface border border-surface-2 rounded px-2 py-1 text-xs w-36 focus:outline-none focus:border-cyan-500" />
                    </div>
                    <div>
                      <label className="text-[10px] text-text-muted block mb-0.5">OS User</label>
                      <input value={creds[upgradeServer.id]?.os_user ?? "amd"}
                        onChange={(e) => setCred(upgradeServer.id, "os_user", e.target.value)}
                        className="bg-surface border border-surface-2 rounded px-2 py-1 text-xs w-24 focus:outline-none focus:border-cyan-500" />
                    </div>
                    <div>
                      <label className="text-[10px] text-text-muted block mb-0.5">OS Password</label>
                      <input type="password" value={creds[upgradeServer.id]?.os_pwd ?? "amd123"}
                        onChange={(e) => setCred(upgradeServer.id, "os_pwd", e.target.value)}
                        className="bg-surface border border-surface-2 rounded px-2 py-1 text-xs w-28 focus:outline-none focus:border-cyan-500" />
                    </div>
                    <button onClick={() => {
                      const c = creds[upgradeServer.id];
                      if (c?.os_ip) {
                        // Save creds override so the backend picks them up
                        qc.invalidateQueries({ queryKey: ["bios-attrs", upgradeServer.id] });
                      }
                    }} className="px-3 py-1 text-xs bg-cyan-600/20 border border-cyan-600/30 text-cyan-400 rounded hover:bg-cyan-600/30 transition-colors">
                      Try loading
                    </button>
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <p className="text-sm font-semibold">{upgradeServer.hostname} — BIOS Settings</p>
                  <p className="text-xs text-text-muted">
                    {upgradeServer.cpu_model ?? ""}{upgradeServer.bios_version ? ` · ${upgradeServer.bios_version}` : ""}
                    {" · "}{upgradeServer.os_ip ? <span className="text-green-400/80">OS IP: {upgradeServer.os_ip}</span> : <span className="text-red-400/80">No OS IP</span>}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {changedCount > 0 && (
                    <>
                      <span className="text-xs text-amber-400 font-semibold">
                        {changedCount} change{changedCount !== 1 ? "s" : ""} pending
                      </span>
                      <button onClick={() => setPendingChanges({})}
                        className="px-2 py-1 text-xs rounded bg-surface-2 hover:bg-surface-2/80">
                        Discard
                      </button>
                      <button
                        disabled={updateAttrMut.isPending}
                        onClick={() => {
                          if (confirm(`Apply ${changedCount} BIOS change${changedCount !== 1 ? "s" : ""} to ${upgradeServer.hostname}? Server will reboot.`))
                            updateAttrMut.mutate();
                        }}
                        className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded flex items-center gap-1 font-semibold">
                        {updateAttrMut.isPending ? <Loader2 size={11} className="animate-spin" /> : <Settings2 size={11} />}
                        Apply Changes
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* One-click AMD tuning presets — stage common knobs into pendingChanges */}
              <div className="card p-3 space-y-2">
                <p className="text-xs text-text-muted">Quick presets (stages matching knobs for review before Apply):</p>
                <div className="flex flex-wrap gap-1.5">
                  {TUNING_PRESETS.map((p) => (
                    <button key={p.label} onClick={() => applyPreset(p)}
                      className="px-2.5 py-1 text-xs rounded bg-surface-2 hover:bg-blue-600/20 border border-surface-2 hover:border-blue-500">
                      {p.label}
                    </button>
                  ))}
                </div>
                {presetMsg && <p className="text-xs text-amber-400">{presetMsg}</p>}
              </div>

              {/* Before → after audit from the last Apply */}
              {tuneDiff && tuneDiff.length > 0 && (
                <div className="card p-3">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold text-text-secondary">Last applied — before → after</p>
                    <button onClick={() => setTuneDiff(null)} className="text-xs text-text-muted hover:text-text-primary">dismiss</button>
                  </div>
                  <table className="w-full text-xs">
                    <thead><tr className="text-left text-text-muted border-b border-surface-2"><th className="py-1">Setting</th><th className="py-1">Before</th><th className="py-1">After</th></tr></thead>
                    <tbody>
                      {tuneDiff.map((d) => (
                        <tr key={d.knob} className="border-b border-surface-2/50">
                          <td className="py-1 pr-3">{d.knob}</td>
                          <td className="py-1 pr-3 font-mono text-text-muted">{d.before}</td>
                          <td className="py-1 font-mono text-amber-400">{d.after}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="relative">
                <Search size={12} className="absolute left-2.5 top-2.5 text-text-muted" />
                <input value={attrSearch} onChange={(e) => setAttrSearch(e.target.value)}
                  placeholder="Filter settings (SVM, IOMMU, NPS, SMT…)"
                  className="w-full pl-7 pr-3 py-1.5 text-xs bg-surface-2 border border-surface-2 rounded focus:outline-none focus:border-blue-500" />
              </div>

              <div className="card p-0 overflow-x-auto max-h-[32rem] overflow-y-auto">
                {attrLoading ? (
                  <div className="py-16 text-center space-y-2">
                    <Loader2 size={20} className="animate-spin inline text-text-muted" />
                    <p className="text-xs text-text-muted">Reading BIOS settings via SCELNX_64…</p>
                    <p className="text-xs text-text-muted">(may take 30–60 seconds)</p>
                  </div>
                ) : attrError ? (
                  <div className="py-12 text-center text-xs space-y-1">
                    <AlertTriangle size={20} className="inline text-red-400 mb-1" />
                    <p className="text-red-400 font-semibold">Failed to read BIOS attributes</p>
                    <p className="text-text-muted">{(attrError as Error)?.message ?? "Unknown error"}</p>
                    <p className="text-text-muted">Enter OS IP + credentials in the panel above, then click Try loading.</p>
                  </div>
                ) : attributes.length === 0 ? (
                  <div className="py-12 text-center text-xs text-text-muted space-y-1">
                    <AlertTriangle size={20} className="inline text-amber-400 mb-1" />
                    <p>No BIOS attributes returned.</p>
                    <p>The server may not have SCELNX_64 installed, or OS credentials are wrong.</p>
                  </div>
                ) : (
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-surface">
                      <tr className="border-b border-surface-2 text-left text-xs text-text-muted uppercase">
                        <th className="px-4 py-2">Setting</th>
                        <th className="px-4 py-2">Help</th>
                        <th className="px-4 py-2">Current</th>
                        <th className="px-4 py-2">New Value</th>
                        <th className="px-4 py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredAttrs.map((a) => (
                        <AttributeRow
                          key={a["Setup Question"]}
                          attr={a}
                          pendingChange={pendingChanges[a["Setup Question"]] ?? null}
                          onSet={(q, v) => setPendingChanges((p) => ({ ...p, [q]: v }))}
                        />
                      ))}
                    </tbody>
                  </table>
                )}
                {!attrLoading && attributes.length > 0 && (
                  <p className="text-xs text-text-muted p-3 border-t border-surface-2">
                    {filteredAttrs.length} / {attributes.length} settings shown
                    {changedCount > 0 && ` · ${changedCount} modified`}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
