"use client";
import { useQuery } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { useState } from "react";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { HourOfWeekHeatmap } from "@/components/charts/HourOfWeekHeatmap";
import { COLORS } from "@/lib/echarts-theme";
import { Activity, AlertTriangle, Power, Cpu } from "lucide-react";

const WINDOWS = ["15m", "1h", "6h", "24h", "7d", "30d"];
const BUCKET_COLORS: Record<string, string> = {
  idle: "#22c55e", light: "#a3e635", active: "#f59e0b", heavy: "#ef4444", unknown: "#64748b", off: "#475569",
};

function KpiTile({ value, label, sub, accent }: { value: React.ReactNode; label: string; sub?: string; accent: string }) {
  return (
    <div className="glass-card border-l-4" style={{ borderLeftColor: accent }}>
      <p className="text-2xl font-bold text-text-primary tabular-nums">{value}</p>
      <p className="text-sm font-medium text-text-secondary">{label}</p>
      {sub && <p className="text-xs text-text-muted mt-0.5">{sub}</p>}
    </div>
  );
}

function FamilyBuckets({ fam }: { fam: any }) {
  const total = fam.total || 1;
  return (
    <div className="flex items-center gap-3">
      <span className="w-20 text-sm font-medium text-text-secondary">{fam.family}</span>
      <span className="text-xs text-text-muted w-10">{fam.total}</span>
      <div className="flex-1 flex h-5 rounded overflow-hidden bg-surface-2">
        {["idle", "light", "active", "heavy", "unknown", "off"].map((b) =>
          fam.buckets[b] > 0 ? (
            <div key={b} title={`${b}: ${fam.buckets[b]}`} style={{ width: `${(fam.buckets[b] / total) * 100}%`, background: BUCKET_COLORS[b] }} />
          ) : null
        )}
      </div>
    </div>
  );
}

export default function UtilizationPage() {
  const [window, setWindow] = useState("7d");
  const [hwMetric, setHwMetric] = useState<"util" | "tests">("util");

  const { data: sum } = useQuery({ queryKey: ["util-sum", window], queryFn: () => fleetApi.utilSummary(window), refetchInterval: 15_000 });
  const { data: fam } = useQuery({ queryKey: ["util-fam"], queryFn: fleetApi.utilByFamily, refetchInterval: 20_000 });
  const { data: tlTests } = useQuery({ queryKey: ["util-tl-tests", window], queryFn: () => fleetApi.utilTimeline("tests", window), refetchInterval: 30_000 });
  const { data: tlUtil } = useQuery({ queryKey: ["util-tl-util", window], queryFn: () => fleetApi.utilTimeline("util", window), refetchInterval: 30_000 });
  const { data: how } = useQuery({ queryKey: ["util-how", hwMetric], queryFn: () => fleetApi.utilHourOfWeek(hwMetric), refetchInterval: 60_000 });
  const { data: howUtil } = useQuery({ queryKey: ["util-how-util"], queryFn: () => fleetApi.utilHourOfWeek("util"), refetchInterval: 60_000 });
  const { data: attn } = useQuery({ queryKey: ["util-attn"], queryFn: fleetApi.utilAttention, refetchInterval: 20_000 });

  const tests = (tlTests?.points ?? []).map((p: any) => ({ t: p.t, v: p.v }));
  const util = (tlUtil?.points ?? []).map((p: any) => ({ t: p.t, v: p.v }));

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><Activity size={18} className="text-blue-400" /> Utilization</h1>
          <p className="text-sm text-text-muted">Health activity & test utilization · 15s refresh</p>
        </div>
        <div className="flex gap-1 bg-surface rounded-lg p-1">
          {WINDOWS.map((w) => (
            <button key={w} onClick={() => setWindow(w)}
              className={`px-2.5 py-1 rounded text-xs font-medium ${window === w ? "bg-blue-600 text-white" : "text-text-muted hover:text-text-primary"}`}>{w}</button>
          ))}
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiTile value={`${sum?.hosts_reporting ?? "—"} / ${sum?.hosts_total ?? "—"}`} label="Hosts reporting" sub="in window" accent={COLORS.healthy} />
        <KpiTile value={`${sum?.idle_pct ?? "—"}%`} label="Idle right now" sub={`${sum?.idle_now ?? 0} of ${sum?.hosts_total ?? 0} hosts`} accent={COLORS.warning} />
        <KpiTile value={sum?.tests_executing ?? "—"} label="Tests executing" sub="active + heavy hosts" accent={COLORS.info} />
        <KpiTile value={sum?.needs_attention ?? attn?.hosts?.length ?? "—"} label="Needs attention" sub={`${attn?.summary?.heavy ?? 0} heavy · ${attn?.summary?.stale ?? 0} unreach`} accent={COLORS.critical} />
      </div>

      {/* Fleet summary line */}
      <div className="glass-card">
        <p className="text-sm">
          <span className="font-semibold text-text-secondary">Health summary</span>
          <span className="text-text-muted"> — Hosts: </span><b className="text-text-primary">{sum?.hosts_total ?? 0}</b>
          <span className="text-text-muted"> · Datapoints: </span><b className="text-text-primary">{(sum?.datapoints ?? 0).toLocaleString()}</b>
          {sum?.bucket_pct && ["idle", "light", "active", "heavy", "unknown"].map((b) => (
            <span key={b}>
              <span className="text-text-muted"> · </span>
              <span style={{ color: BUCKET_COLORS[b] }}>{b}: </span>
              <b className="text-text-primary">{sum.bucket_pct[b]}%</b>
            </span>
          ))}
        </p>
      </div>

      {/* Activity timelines */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="glass-card">
          <h3 className="text-sm font-semibold text-text-secondary mb-2">Tests activity (active+heavy hosts)</h3>
          <TimeSeriesChart series={tests} name="Tests" unit="" color={COLORS.info} height={160} zoom={false} />
        </div>
        <div className="glass-card">
          <h3 className="text-sm font-semibold text-text-secondary mb-2">Health utilization (avg score 0–9)</h3>
          <TimeSeriesChart series={util} name="Util" unit="" color={COLORS.warning} height={160} zoom={false} />
        </div>
      </div>

      {/* Family activity bands */}
      <div className="glass-card">
        <h3 className="text-sm font-semibold text-text-secondary mb-3">Activity by family</h3>
        <div className="space-y-2">
          {(fam?.families ?? []).map((f: any) => <FamilyBuckets key={f.family} fam={f} />)}
        </div>
        <div className="flex gap-3 mt-3 text-xs text-text-muted">
          {["idle", "light", "active", "heavy", "unknown", "off"].map((b) => (
            <span key={b} className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm" style={{ background: BUCKET_COLORS[b] }} /> {b}</span>
          ))}
        </div>
      </div>

      {/* Hour-of-week heatmaps */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="glass-card">
          <h3 className="text-sm font-semibold text-text-secondary mb-2">Hour-of-week — Test volume <span className="text-text-muted font-normal">(all history)</span></h3>
          <HourOfWeekHeatmap grid={how?.grid ?? []} palette="blue" />
        </div>
        <div className="glass-card">
          <h3 className="text-sm font-semibold text-text-secondary mb-2">Hour-of-week — Utilization <span className="text-text-muted font-normal">(green=idle, red=heavy)</span></h3>
          <HourOfWeekHeatmap grid={howUtil?.grid ?? []} palette="util" max={9} />
        </div>
      </div>

      {/* Attention list */}
      <div className="glass-card">
        <h3 className="text-sm font-semibold text-text-secondary mb-3 flex items-center gap-2"><AlertTriangle size={15} /> Needs Attention</h3>
        {(attn?.hosts ?? []).length === 0 ? (
          <p className="text-sm text-green-400">✓ No hosts need attention</p>
        ) : (
          <div className="space-y-1.5">
            {attn.hosts.map((h: any) => (
              <div key={h.host} className="flex items-center gap-3 text-sm bg-surface-2/40 rounded-lg px-3 py-2">
                <span className="font-mono text-text-primary w-44">{h.host}</span>
                <span className="text-xs px-2 py-0.5 rounded-full" style={{ color: BUCKET_COLORS[h.bucket] ?? "#94a3b8", background: `${BUCKET_COLORS[h.bucket] ?? "#94a3b8"}1a` }}>{h.bucket ?? "—"}</span>
                <span className="text-xs text-text-muted">{h.family} · {h.location}</span>
                {h.stale && <span className="text-xs text-red-400">unreachable</span>}
                {h.blocked_by?.length > 0 && <span className="text-xs text-yellow-400">{h.blocked_by.join(", ")}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
