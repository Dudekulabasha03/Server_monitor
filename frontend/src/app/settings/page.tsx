"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { fleetApi } from "@/lib/api";
import { useState } from "react";
import { Bell, Clock, Shield, Plus, X } from "lucide-react";

const EMPTY = {
  hostname: "", bmc_ip: "", os_ip: "", vendor: "amd_crb", model: "", datacenter: "Santa Clara",
  rack: "", rack_unit: "", environment: "production", team: "", bmc_username: "", bmc_password: "",
  os_username: "", os_password: "",
  redfish_enabled: true,
};

export default function SettingsPage() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState<Record<string, any>>({ ...EMPTY });
  const [msg, setMsg] = useState("");

  const createMut = useMutation({
    mutationFn: (data: any) => fleetApi.createServer(data),
    onSuccess: (d: any) => {
      const r = d?.refresh ?? {};
      const parts: string[] = [];
      if (r.redfish) parts.push(`BMC ${r.redfish.collected ?? 0}`);
      if (r.os) parts.push(r.os.collected > 0 ? "OS live" : "OS N/A");
      if (r.prism) parts.push(`PRISM ${r.prism.enriched ?? 0}`);
      setMsg(`✓ Server added & enriched${parts.length ? ` (${parts.join(", ")})` : ""}`);
      setShowAdd(false); setForm({ ...EMPTY });
      qc.invalidateQueries({ queryKey: ["servers-settings"] });
    },
    onError: (e: any) => setMsg("✗ " + (e?.response?.data?.detail || "failed to add")),
  });
  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }));

  const submit = () => {
    if (!form.hostname || !form.bmc_ip) { setMsg("✗ hostname and BMC IP required"); return; }
    const payload: any = { ...form };
    if (payload.rack_unit) payload.rack_unit = parseInt(payload.rack_unit); else delete payload.rack_unit;
    Object.keys(payload).forEach((k) => payload[k] === "" && delete payload[k]);
    createMut.mutate(payload);
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Settings</h1>
          <p className="text-sm text-text-muted">Platform configuration & fleet management</p>
        </div>
        <button onClick={() => { setShowAdd(!showAdd); setMsg(""); }} className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg px-3 py-1.5 text-sm">
          <Plus size={14} /> Add Server
        </button>
      </div>

      {msg && <div className="card text-sm py-2">{msg}</div>}

      {/* Add server form */}
      {showAdd && (
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-text-secondary">Add Server</h3>
            <button onClick={() => setShowAdd(false)} className="text-text-muted hover:text-text-primary"><X size={16} /></button>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
            {[["hostname", "Hostname *"], ["bmc_ip", "BMC IP *"], ["os_ip", "OS IP"], ["model", "Model / Family"], ["rack", "Rack"], ["rack_unit", "Rack Unit"], ["team", "Team"], ["bmc_username", "BMC User"], ["bmc_password", "BMC Password"], ["os_username", "OS User"], ["os_password", "OS Password"]].map(([k, lbl]) => (
              <div key={k}>
                <label className="text-xs text-text-muted">{lbl}</label>
                <input type={k.endsWith("password") ? "password" : "text"} value={form[k]} onChange={(e) => set(k, e.target.value)}
                  className="w-full bg-surface-2 border border-surface-2 rounded px-2 py-1.5 mt-0.5 focus:outline-none focus:border-blue-500" />
              </div>
            ))}
            <div>
              <label className="text-xs text-text-muted">Region</label>
              <select value={form.datacenter} onChange={(e) => set("datacenter", e.target.value)} className="w-full bg-surface-2 border border-surface-2 rounded px-2 py-1.5 mt-0.5">
                <option>Santa Clara</option><option>Plano</option><option>Dallas</option><option>Bangalore</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-text-muted">Environment</label>
              <select value={form.environment} onChange={(e) => set("environment", e.target.value)} className="w-full bg-surface-2 border border-surface-2 rounded px-2 py-1.5 mt-0.5">
                <option>production</option><option>staging</option><option>dev</option><option>lab</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button onClick={submit} disabled={createMut.isPending} className="bg-green-600 hover:bg-green-500 text-white rounded-lg px-4 py-1.5 text-sm disabled:opacity-50">
              {createMut.isPending ? "Adding…" : "Create Server"}
            </button>
            <button onClick={() => setShowAdd(false)} className="bg-surface-2 rounded-lg px-4 py-1.5 text-sm">Cancel</button>
          </div>
        </div>
      )}

      {/* Thresholds */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-secondary mb-4 flex items-center gap-2"><Shield size={15} /> Alert Thresholds (defaults)</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
          {[["CPU Temp Warning", "75°C"], ["CPU Temp Critical", "85°C"], ["Inlet Warning", "30°C"], ["Inlet Critical", "35°C"], ["CPU Usage Warning", "80%"], ["CPU Usage Critical", "95%"], ["Memory Warning", "85%"], ["Disk Critical", "90%"]].map(([k, v]) => (
            <div key={k} className="bg-surface-2/40 rounded-lg p-3"><p className="text-text-muted text-xs">{k}</p><p className="font-bold">{v}</p></div>
          ))}
        </div>
        <p className="text-xs text-text-muted mt-3">Configured in backend settings. Edit via environment or AlertRule API.</p>
      </div>

      {/* Collection intervals */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-secondary mb-4 flex items-center gap-2"><Clock size={15} /> Collection Intervals</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
          {[["Redfish", "60s"], ["IPMI", "60s"], ["OS Agent", "60s"], ["Health Score", "60s"], ["Alerts", "60s"], ["Discovery", "3600s"]].map(([k, v]) => (
            <div key={k} className="bg-surface-2/40 rounded-lg p-3"><p className="text-text-muted text-xs">{k}</p><p className="font-bold">{v}</p></div>
          ))}
        </div>
      </div>

      {/* Notification channels */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-secondary mb-4 flex items-center gap-2"><Bell size={15} /> Notification Channels</h3>
        <div className="space-y-2 text-sm">
          {[["Email (SMTP)", "smtp.amd.com"], ["Microsoft Teams", "Webhook"], ["Slack", "#server-alerts"]].map(([k, v]) => (
            <div key={k} className="flex items-center justify-between bg-surface-2/40 rounded-lg p-3">
              <span>{k}</span><span className="text-text-muted text-xs">{v} · configure in .env</span>
            </div>
          ))}
        </div>
      </div>

      <p className="text-xs text-text-muted">Per-server actions (Full Refresh, PRISM) are available on each server in the Operations tab.</p>
    </div>
  );
}
