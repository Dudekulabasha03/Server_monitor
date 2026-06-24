import axios from "axios";

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

// Attach JWT token from localStorage
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("fleet_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Types
export interface FleetSummary {
  total: number;
  healthy: number;
  warning: number;
  at_risk: number;
  critical: number;
  offline: number;
  unknown: number;
  avg_health_score: number | null;
  total_power_watts: number | null;
  avg_cpu_pct: number | null;
  avg_memory_pct: number | null;
  avg_cpu_temp: number | null;
}

export interface ServerSummary {
  id: string;
  hostname: string;
  fqdn: string | null;
  bmc_ip: string | null;
  os_ip: string | null;
  vendor: string | null;
  model: string | null;
  family: string | null;
  datacenter: string;
  rack: string | null;
  rack_unit: number | null;
  status: "healthy" | "warning" | "at_risk" | "critical" | "offline" | "unknown";
  health_score: number | null;
  cpu_usage_avg: number | null;
  memory_usage_pct: number | null;
  cpu_temp_max: number | null;
  power_consumed_watts: number | null;
  sensor_health: string | null;
  last_seen: string | null;
  team: string | null;
  environment: string;
  tags: string[];
}

export interface Alert {
  id: string;
  server_id: string;
  severity: "info" | "warning" | "critical" | "emergency";
  category: string;
  state: "firing" | "acknowledged" | "resolved" | "suppressed";
  title: string;
  message: string;
  metric_name: string | null;
  metric_value: number | null;
  threshold_value: number | null;
  fired_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  runbook_url: string | null;
}

// API Functions
export const fleetApi = {
  getSummary: () => api.get<FleetSummary>("/api/v1/servers/summary").then((r) => r.data),
  getServers: (params?: Record<string, any>) =>
    api.get<ServerSummary[]>("/api/v1/servers", { params }).then((r) => r.data),
  getServer: (id: string) => api.get(`/api/v1/servers/${id}`).then((r) => r.data),
  createServer: (data: Record<string, any>) => api.post("/api/v1/servers", data).then((r) => r.data),
  updateServer: (id: string, data: Record<string, any>) => api.patch(`/api/v1/servers/${id}`, data).then((r) => r.data),
  deleteServer: (id: string) => api.delete(`/api/v1/servers/${id}`),
  prismRefresh: (id: string) => api.post(`/api/v1/servers/${id}/prism-refresh`).then((r) => r.data),
  osRefresh: (id: string) => api.post(`/api/v1/servers/${id}/os-refresh`).then((r) => r.data),
  fullRefresh: (id: string) => api.post(`/api/v1/servers/${id}/full-refresh`).then((r) => r.data),
  getMetricsHistory: (id: string, metric: string, hours = 24) =>
    api.get(`/api/v1/servers/${id}/metrics/history`, { params: { metric, hours } }).then((r) => r.data),
  getHealthHistory: (id: string, hours = 48) =>
    api.get(`/api/v1/servers/${id}/health/history`, { params: { hours } }).then((r) => r.data),

  getAlerts: (params?: Record<string, any>) =>
    api.get<Alert[]>("/api/v1/alerts", { params }).then((r) => r.data),
  getAlertStats: () => api.get("/api/v1/alerts/stats").then((r) => r.data),
  acknowledgeAlert: (id: string, by: string) =>
    api.post(`/api/v1/alerts/${id}/acknowledge`, null, { params: { acknowledged_by: by } }),
  resolveAlert: (id: string) => api.post(`/api/v1/alerts/${id}/resolve`),

  // Metrics tabs
  getThermal: () => api.get("/api/v1/metrics/thermal").then((r) => r.data),
  getPower: (rate = 0.12, pue = 1.5) =>
    api.get("/api/v1/metrics/power", { params: { rate_per_kwh: rate, pue } }).then((r) => r.data),
  getPowerTrend: (hours = 24) =>
    api.get("/api/v1/metrics/power/trend", { params: { hours } }).then((r) => r.data),
  getStorage: () => api.get("/api/v1/metrics/storage").then((r) => r.data),
  getNetwork: () => api.get("/api/v1/metrics/network").then((r) => r.data),
  getSelEvents: (params?: Record<string, any>) => api.get("/api/v1/metrics/sel", { params }).then((r) => r.data),
  getCapacity: () => api.get("/api/v1/metrics/capacity").then((r) => r.data),

  // Inventory & racks
  getInventory: () => api.get("/api/v1/inventory").then((r) => r.data),
  getRacks: () => api.get("/api/v1/racks").then((r) => r.data),

  // Users
  getSessions: () => api.get("/api/v1/users/sessions").then((r) => r.data),
  getIdleServers: () => api.get("/api/v1/users/idle-servers").then((r) => r.data),
  getFleetActivity: () => api.get("/api/v1/users/activity").then((r) => r.data),

  // Intelligence
  getRisk: () => api.get("/api/v1/intelligence/risk").then((r) => r.data),
  getRecommendations: () => api.get("/api/v1/intelligence/recommendations").then((r) => r.data),
  getRecommendationsByServer: () => api.get("/api/v1/intelligence/recommendations/by-server").then((r) => r.data),
  getServerRecommendations: (id: string) => api.get(`/api/v1/intelligence/recommendations/server/${id}`).then((r) => r.data),
  dismissReco: (id: string) => api.post(`/api/v1/intelligence/recommendations/${id}/dismiss`),
  getOptimization: () => api.get("/api/v1/intelligence/optimization").then((r) => r.data),
  getRCA: (alertId: string) => api.get(`/api/v1/intelligence/rca/${alertId}`).then((r) => r.data),
  getFleetIntelligence: () => api.get("/api/v1/intelligence/fleet-summary").then((r) => r.data),

  // Firmware & lifecycle
  getFirmwareCompliance: () => api.get("/api/v1/firmware/compliance").then((r) => r.data),
  getBiosCompare: (params?: { team?: string; family?: string }) =>
    api.get("/api/v1/firmware/compare", { params }).then((r) => r.data),
  setFirmwareBaseline: (id: string, baseline: Record<string, string>) =>
    api.post(`/api/v1/firmware/${id}/baseline`, { baseline }),
  getLifecycle: () => api.get("/api/v1/lifecycle").then((r) => r.data),
  updateLifecycle: (id: string, data: Record<string, any>) => api.post(`/api/v1/lifecycle/${id}`, data),

  // Reports
  reportUrl: (type: string, format = "pdf") =>
    `${api.defaults.baseURL}/api/v1/reports/${type}?format=${format}`,

  // Time-series / Live Lab
  tsKpis: () => api.get("/api/v1/ts/kpis").then((r) => r.data),
  tsHeartbeat: () => api.get("/api/v1/ts/heartbeat").then((r) => r.data),
  tsFleet: (metrics: string, range = "24h", agg = "avg") =>
    api.get("/api/v1/ts/fleet", { params: { metrics, range, agg } }).then((r) => r.data),
  tsServer: (id: string, metrics: string, range = "24h") =>
    api.get(`/api/v1/ts/server/${id}`, { params: { metrics, range } }).then((r) => r.data),
  tsAnomalies: (metric: string, range = "6h", serverId?: string) =>
    api.get("/api/v1/ts/anomalies", { params: { metric, range, server_id: serverId } }).then((r) => r.data),
  tsForecast: (metric: string, range = "24h", horizon_hours = 24, cap?: number, serverId?: string) =>
    api.get("/api/v1/ts/forecast", { params: { metric, range, horizon_hours, cap, server_id: serverId } }).then((r) => r.data),
  tsCorrelation: (range = "6h", serverId?: string) =>
    api.get("/api/v1/ts/correlation", { params: { range, server_id: serverId } }).then((r) => r.data),

  // Utilization (PIPT-style) dashboard
  utilSummary: (window = "7d") => api.get("/api/v1/util/summary", { params: { window } }).then((r) => r.data),
  utilByFamily: () => api.get("/api/v1/util/by-family").then((r) => r.data),
  utilByTeam: () => api.get("/api/v1/util/by-team").then((r) => r.data),
  utilTimeline: (metric = "util", window = "7d") =>
    api.get("/api/v1/util/timeline", { params: { metric, window } }).then((r) => r.data),
  utilHourOfWeek: (metric = "util") =>
    api.get("/api/v1/util/hour-of-week", { params: { metric } }).then((r) => r.data),
  utilAttention: () => api.get("/api/v1/util/attention").then((r) => r.data),

  // Changelog
  getChangelog: (params?: Record<string, any>) =>
    api.get("/api/v1/changelog", { params }).then((r) => r.data),

  // Usage history
  usageSummary: (params: Record<string, any> = {}) => api.get("/api/v1/usage/summary", { params }).then((r) => r.data),
  usageByServer: (params: Record<string, any> = {}) => api.get("/api/v1/usage/by-server", { params }).then((r) => r.data),

  // BIOS patch & upgrade
  biosHealth: () => api.get("/api/v1/bios/health").then((r) => r.data),
  biosServers: (params?: { team?: string; family?: string; bios_version?: string }) =>
    api.get("/api/v1/bios/servers", { params }).then((r) => r.data),
  biosAttributes: (serverId: string) =>
    api.get(`/api/v1/bios/${serverId}/attributes`).then((r) => r.data),
  biosUpdateAttributes: (
    serverId: string,
    attributes_to_update: { "Setup Question": string; Value: string }[],
    reset = false,
  ) =>
    api.post(`/api/v1/bios/${serverId}/update-attributes`, { attributes_to_update, reset }).then((r) => r.data),
  biosVerify: (serverId: string, formData: FormData) =>
    api.post(`/api/v1/bios/${serverId}/verify`, formData, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data),
  biosFlash: (serverId: string, formData: FormData) =>
    api.post(`/api/v1/bios/${serverId}/flash`, formData, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data),
  biosBulkFlash: (server_ids: string[], bios_file_url: string) =>
    api.post("/api/v1/bios/bulk-flash", { server_ids, bios_file_url }).then((r) => r.data),
  biosReset: (serverId: string) =>
    api.post(`/api/v1/bios/${serverId}/reset`).then((r) => r.data),
  biosJob: (jobId: string) =>
    api.get(`/api/v1/bios/jobs/${jobId}`).then((r) => r.data),
  biosRefresh: (serverId: string) =>
    api.post(`/api/v1/bios/${serverId}/refresh`).then((r) => r.data),
  biosBatchStatus: (jobId: string) =>
    api.get(`/api/v1/bios/batch/${jobId}`).then((r) => r.data),
  biosBatchUpdate: (server_names: string[], bios_file_url: string, do_flash = true) =>
    api.post("/api/v1/bios/batch-update", { server_names, bios_file_url, do_flash }).then((r) => r.data),

  // Live monitor (on-demand SSH/BMC sample for comparison streaming)
  liveSample: (server_names: string[], metric: string) =>
    api.post("/api/v1/livemon/sample", { server_names, metric }).then((r) => r.data),

  // AI / agents (experimental)
  aiHealth: () => api.get("/api/v1/ai/health").then((r) => r.data),
  aiAsk: (question: string, session_id?: string) => api.post("/api/v1/ai/ask", { question, session_id }).then((r) => r.data),
  aiRca: (alertId: string) => api.get(`/api/v1/ai/rca/${alertId}`).then((r) => r.data),
  aiSelSummary: (hostname?: string) => api.get("/api/v1/ai/sel-summary", { params: { hostname } }).then((r) => r.data),
  aiObservability: () => api.get("/api/v1/ai/observability").then((r) => r.data),
};
