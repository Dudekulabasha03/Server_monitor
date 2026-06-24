# AMD Server Fleet Observability Platform — Architecture & Development Plan

## Overview

Centralized monitoring platform for AMD's server fleet.
- Current: 140 servers
- Target: 500+ servers
- Example hosts: volcano-eb87.amd.com, titanite-d310.amd.com, daytonax42cd.amd.com

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Redfish  │  │   IPMI   │  │ OS Agent │  │   SNMP   │           │
│  │  API     │  │/IPMITool │  │(Linux/Win│  │  Traps   │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
└───────┼─────────────┼─────────────┼─────────────┼───────────────────┘
        │             │             │             │
┌───────▼─────────────▼─────────────▼─────────────▼───────────────────┐
│                    COLLECTOR LAYER (Python Async)                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Fleet Discovery → Scheduler → Async Collectors → Normalizer │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
└─────────────────────────────┼────────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────────┐
│                      MESSAGE QUEUE (Redis Streams)                    │
│   raw_metrics | alerts_queue | discovery_queue | events_queue         │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────────┐
│                    PROCESSING LAYER (FastAPI Workers)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐             │
│  │ Health Score │  │ Alert Engine │  │ Anomaly/ML    │             │
│  │   Engine     │  │              │  │ Predictor     │             │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘             │
└─────────┼─────────────────┼──────────────────┼──────────────────────┘
          │                 │                  │
┌─────────▼─────────────────▼──────────────────▼──────────────────────┐
│                        STORAGE LAYER                                  │
│  ┌─────────────────┐              ┌──────────────────────┐          │
│  │   PostgreSQL     │              │   VictoriaMetrics    │          │
│  │  (Inventory,     │              │   (Time-Series       │          │
│  │   Config, CMDB,  │              │    Metrics, Telemetry│          │
│  │   Alerts, Users) │              │    60-day retention) │          │
│  └─────────────────┘              └──────────────────────┘          │
└──────────────────────────────────────────────────────────────────────┘
          │
┌─────────▼──────────────────────────────────────────────────────────┐
│                    API LAYER (FastAPI)                               │
│  REST API + WebSocket (real-time push) + GraphQL (analytics)        │
└─────────┬──────────────────────────────────────────────────────────┘
          │
┌─────────▼──────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js 14)                             │
│  Executive Dashboard | Ops Dashboard | Rack View | Live NOC Screen  │
│  Server Drill-down | Alerts | Inventory | Capacity | Reports        │
└────────────────────────────────────────────────────────────────────┘
```

---

## Development Plan — Phased Approach

### Phase 1: Foundation (Weeks 1-3)
**Goal:** Working inventory + basic data collection from AMD servers

- [ ] Project scaffolding (monorepo with backend + frontend)
- [ ] PostgreSQL schema: servers, inventory, metrics_raw
- [ ] VictoriaMetrics setup
- [ ] Redfish collector (async Python, targets AMD/Dell/HPE/Supermicro)
- [ ] IPMI collector (ipmitools wrapper + python-ipmi)
- [ ] Fleet auto-discovery (IP range scan + Redfish probe)
- [ ] Basic FastAPI REST endpoints
- [ ] Simple server list UI

**Deliverable:** Can add servers, poll Redfish/IPMI, store metrics

---

### Phase 2: Core Monitoring (Weeks 4-6)
**Goal:** Real-time health monitoring + alerting

- [ ] Health Score Engine (0-100 weighted scoring)
- [ ] Alert Engine (rules engine + notification channels)
- [ ] Redis Streams message pipeline
- [ ] WebSocket real-time push to frontend
- [ ] Operations Dashboard (server grid with health badges)
- [ ] Server detail drill-down page
- [ ] Email + Teams + Slack alert integrations

**Deliverable:** Full real-time monitoring with alerting

---

### Phase 3: Observability Depth (Weeks 7-9)
**Goal:** Thermal, power, capacity deep analytics

- [ ] Thermal heatmaps (rack-level visualization)
- [ ] Power consumption tracking + cost estimation
- [ ] Capacity trending (CPU/Memory/Storage forecasting)
- [ ] User utilization tracking (SSH/RDP sessions, process attribution)
- [ ] OS agent (lightweight Python/Go agent for Linux servers)
- [ ] Historical analysis dashboards

**Deliverable:** Full observability across all metric categories

---

### Phase 4: Intelligence (Weeks 10-12)
**Goal:** Predictive analytics + recommendations engine

- [ ] SMART disk failure prediction (ML model)
- [ ] PSU failure prediction (voltage trend analysis)
- [ ] Thermal risk prediction (LSTM/ARIMA forecasting)
- [ ] Capacity exhaustion forecasting (30/60/90 day)
- [ ] Recommendations engine (rule-based + ML hybrid)
- [ ] Executive dashboard + reporting module
- [ ] PDF report generation

**Deliverable:** Predictive intelligence layer

---

### Phase 5: Production Hardening (Weeks 13-15)
**Goal:** Enterprise-ready, secure, scalable

- [ ] Azure AD / Keycloak SSO integration
- [ ] RBAC (Admin, Operator, Read-only, Team-scoped)
- [ ] Kubernetes deployment (Helm charts)
- [ ] Horizontal scaling of collectors
- [ ] Multi-datacenter support
- [ ] API rate limiting + security hardening
- [ ] Full audit logging
- [ ] Disaster recovery procedures

**Deliverable:** Production-ready enterprise platform

---

## Technology Stack (Final Decisions)

### Frontend
| Component | Technology | Reason |
|-----------|-----------|--------|
| Framework | Next.js 14 (App Router) | SSR + RSC for fast initial load |
| Language | TypeScript | Type safety for complex data models |
| Styling | TailwindCSS + shadcn/ui | Rapid UI, dark mode native |
| Charts | Recharts + Apache ECharts | Recharts for simple, ECharts for heatmaps/complex |
| Real-time | Socket.io client | WebSocket with fallback |
| State | Zustand + React Query | Simple global state + server state caching |
| Tables | TanStack Table v8 | Virtualized rows for 500+ servers |

### Backend
| Component | Technology | Reason |
|-----------|-----------|--------|
| Framework | FastAPI 0.111 | Async-native, OpenAPI auto-docs |
| Language | Python 3.12 | Rich async ecosystem, IPMI/Redfish libs |
| Task Queue | Celery + Redis | Distributed collector scheduling |
| WebSocket | FastAPI WebSocket | Real-time metric push |
| ORM | SQLAlchemy 2.0 (async) | Type-safe async DB access |
| Validation | Pydantic v2 | Fast model validation |

### Data Storage
| Component | Technology | Reason |
|-----------|-----------|--------|
| Relational | PostgreSQL 16 | Inventory, config, alerts, RBAC |
| Time-series | VictoriaMetrics | 10x cheaper than InfluxDB, Prometheus-compatible |
| Cache | Redis 7 | Queue, session cache, real-time pub/sub |
| Object Store | MinIO (optional) | Log archives, report PDFs |

### Collection
| Protocol | Library | Coverage |
|----------|---------|---------|
| Redfish | `python-redfish-library` + `httpx async` | Dell iDRAC, HPE iLO, Lenovo XCC, Supermicro BMC |
| IPMI | `python-ipmi` + `ipmitool` subprocess | Legacy BMC, sensors |
| SNMP | `pysnmp` | Network devices, older hardware |
| OS Agent | Custom Python agent | SSH-based or installed agent |

### AMD-Specific Notes
- AMD EPYC servers (Rome/Milan/Genoa) support Redfish natively via iDRAC/iLO/XCC
- volcano-eb87, titanite-d310, daytonax42cd suggest AMD internal codename servers (EPYC CRB/OEM)
- These may use AMD's internal BMC — verify Redfish endpoint at https://<bmc-ip>/redfish/v1/
- IPMI over LAN should work on all AMD-qualified platforms

---

## Additional Recommendations (Beyond Requirements)

### 1. AMD EPYC Power Telemetry
AMD EPYC CPUs expose per-socket/per-NUMA power via RAPL (Running Average Power Limit). Integrate `pyRAPL` or `/sys/class/powercap/` for fine-grained CPU power breakdown unavailable via Redfish.

### 2. ROCm GPU Monitoring
For GPU-equipped servers, integrate ROCm SMI (`rocm-smi` Python bindings) for:
- GPU Temperature, Power, Memory, Utilization
- ECC errors
- PCIe bandwidth

### 3. Fabric / Network Telemetry
Integrate with AMD Instinct interconnect fabric metrics (if applicable) and standard NIC stats via ethtool/PCIe counters.

### 4. CMDB Integration
Export inventory to ServiceNow CMDB via REST API — keeps asset records synchronized without manual entry.

### 5. Cost Allocation
Tag servers by team/project (from LDAP/AD group membership), calculate per-team power cost and resource consumption for chargeback/showback.

### 6. Automated Remediation
Connect alerts to runbook automation:
- Auto-restart stuck services
- Auto-trigger fan speed increase via Redfish
- Auto-open ITSM tickets (ServiceNow/Jira) on critical alerts

### 7. Firmware Compliance Baseline
Track firmware versions against AMD's approved baseline matrix. Auto-flag servers running EOL or vulnerable firmware.

### 8. Secure Credential Vault
Use HashiCorp Vault (or Azure Key Vault) for BMC credentials — never store plaintext passwords in the database.

---

## Security Architecture

```
External Users → Azure AD SSO → JWT → API Gateway → FastAPI
                                                        ↓
                                                    RBAC Guard
                                                    ↙    ↘
                                               Admin   Read-only
                                                 ↓
                                          Vault (BMC credentials)
                                                 ↓
                                          Encrypted channels (TLS)
                                                 ↓
                                          Server BMC endpoints
```

All BMC communication over HTTPS (Redfish) or encrypted IPMI LAN (cipher suite 17+).
All inter-service communication within Kubernetes via mTLS (Istio/Linkerd).
