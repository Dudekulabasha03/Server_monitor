# Helios — AMD Health Intelligence Platform

> Real-time fleet monitoring, firmware compliance, and AI-driven operations for AMD datacenter infrastructure.

---

## Dashboard

![Helios Dashboard](docs/screenshots/dashboard.png)

The **main dashboard** provides a live, at-a-glance view of the entire server fleet:

| Metric | Value |
|---|---|
| Total Servers Monitored | 274 |
| Healthy | 214 |
| Warning | 14 |
| Critical | 19 |
| Offline | 12 |
| Avg Health Score | 94.4 / 100 |
| Total Power Draw | 18.4 kW (~$2,384/mo est.) |
| Avg CPU Temperature | 36.0 °C (Normal) |
| Active Alerts | 45 (43 critical · 2 warning) |

**Server Utilization Bar** shows real-time workload distribution across the fleet:
- Idle: 88 · Light: 8 · Active: 2 · Heavy: 2 · Unknown: 160

**By Team & Family** breaks down health per team (Naples, Rome, Milan, Genoa, Bergamo, Siena, Turin) with per-team healthy/warning/critical/offline/unknown counts and health scores.

---

## Firmware & BIOS

![Firmware & BIOS](docs/screenshots/firmware-bios.png)

The **Firmware & BIOS** page gives full visibility into fleet-wide BIOS compliance against auto-detected baselines:

- **155 servers behind baseline** highlighted across all teams
- Per-team compliance cards show baseline version, on-baseline count, drift count, and version distribution:

| Team | Baseline | Compliance |
|---|---|---|
| Bergamo | RTI100FD | 100% |
| Siena | RCB100HB | 86% |
| Milan | RYM100JA | 42% |
| Naples | 1.28.0 | 40% |
| Turin | RVOT100AA | 35% |
| Rome | 2.18.1 | 22% |
| Genoa | RTI100HB | 25% |

**Tabs available:**
- **Patch (Flash)** — flash firmware to baseline across selected servers
- **Tune Settings** — push BIOS setting tuning profiles
- **Drift Report** (155) — full list of servers drifted from baseline
- **A/B Compare** — side-by-side BIOS version diff

Filterable by Team, Family, Turin Variant, and BIOS Version.

---

## Live NOC — Live Operations Center

![Live NOC](docs/screenshots/live-noc.png)

The **AMD NOC** page is a real-time operations center with genuine sensor readings, auto-refreshing every 5 seconds. It gives NOC engineers an instant full-fleet situational view.

**Live Fleet Summary (snapshot: 11:45:38, Fri Jul 10):**

| Metric | Value |
|---|---|
| Total Servers | 274 |
| Healthy | 213 |
| Warning | 17 |
| Critical | 17 |
| Offline | 11 |
| Avg CPU Temp | 42 °C |
| Max CPU Temp | 82.125 °C |
| Fleet Power | 17 kW |
| BMC Critical | 6 servers |

**Active Critical Alerts (40)** are shown in a live feed with timestamps:
- PSU Failure — 1 PSU(s) failed on `smc2890-ipmi`. Redundancy lost. *(8 min ago)*
- Server Offline / BMC Unreachable — `cinnabar-3ee2` *(~1 hr ago)*
- Server Offline / BMC Unreachable — `cinnabar-30bb` *(~1 hr ago)*

**Problem Servers (24)** table lists every critical/warning server with per-server telemetry:

| Server | Status | Health | CPU Temp | Power | Sensor |
|---|---|---|---|---|---|
| idrac-jpn43w2 | Critical | 86 | — | — | — |
| titanite-d33e | Critical | 88 | 75.625 °C | 496W | Critical |
| titanite-d2e6 | Critical | 92 | 46.75 °C | 60W | Critical |
| titanite-d4c0 | Critical | 92 | 66.5 °C | 61W | Critical |

Columns: Server · Status · Health Score · CPU Temp · Inlet Temp · Power · PSU Fail · Fan Fail · Sensor status. Exportable via the **Export** button.

---

## Ask Helios — AI Operations Assistant

![Ask Helios](docs/screenshots/ask-helios.png)

**Ask Helios** is a natural-language AI assistant powered by **Claude Opus 4.6 (Live)** that reasons step-by-step over live fleet data — read-only and grounded in real tool data, never hallucinating.

**Example interaction shown:** *"Can you test Samsung disk on a Turin system?"*

Helios autonomously:
1. Located a Turin server (`volcano-9a44`) with a Samsung NVMe disk
2. Identified the correct data disk (`/dev/nvme1n1` — Samsung MZWLO3T8HCLS-00A07, 3.5 TB NVMe) and excluded the OS disk
3. Ran FIO benchmark and returned structured results

**Disk Inventory surfaced by Helios (volcano-9a44):**

| Device | Model | Capacity | Health | Role |
|---|---|---|---|---|
| /dev/nvme0n1 | SAMSUNG MZVL2512HCJQ-00B00 | 477 GB | OK | OS disk (excluded) |
| /dev/nvme1n1 | SAMSUNG MZWLO3T8HCLS-00A07 | 3.5 TB | OK | **Tested** |
| /dev/nvme2n1 | SAMSUNG MZWLO3T8HCLS-00A07 | 3.5 TB | OK | Data |
| /dev/nvme3n1 | SAMSUNG MZWLO3T8HCLS-00A07 | 3.5 TB | OK | Data |
| /dev/nvme4n1 | SAMSUNG MZWLO3T8HCLS-00A07 | 3.5 TB | OK | Data |

**Capabilities:**
- Natural language queries over live server telemetry
- Autonomous tool use: disk inventory, FIO benchmarks, BIOS checks, alert lookups
- Batch operations via attached server lists
- Fully read-only — no unintended mutations

---

## Features

- Live fleet health dashboard with real-time telemetry
- Per-server drill-down: CPU, memory, power, thermals, storage, network
- AI-powered ops assistant ("Ask Helios")
- Automated alert engine with SEL event parsing
- BIOS/firmware compliance tracking and remote flash
- RBAC with role-based access (Admin, NOC, User)
- Changelog and audit trail

---

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) v2+
- Git
- An `ANTHROPIC_API_KEY` for the Ask Helios AI assistant

### 1. Clone the repository

```bash
git clone https://github.com/Dudekulabasha03/Server_monitor.git
cd Server_monitor
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Random secret for JWT signing (use `openssl rand -hex 32`) |
| `POSTGRES_PASSWORD` | Password for the PostgreSQL database |
| `ANTHROPIC_API_KEY` | API key for Ask Helios (Claude AI) |
| `DEFAULT_BMC_USERNAME` | Default BMC/iDRAC username for server polling |
| `DEFAULT_BMC_PASSWORD` | Default BMC/iDRAC password for server polling |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | Email alert settings (optional) |
| `TEAMS_WEBHOOK_URL` | MS Teams alert webhook (optional) |
| `PRISM_URL` / `PRISM_USER` / `PRISM_PASSWORD` | PRISM OS-provisioning API (optional) |
| `BIOS_API_URL` | BIOS flash API endpoint (optional) |

### 3. Start the full stack

```bash
docker compose up -d
```

This starts all services:

| Service | Port | Description |
|---|---|---|
| Frontend (Next.js) | `3000` | Main UI |
| Backend API (FastAPI) | `8000` | REST API |
| PostgreSQL | `5432` | Primary database |
| Redis | `6379` | Cache + task queue |
| VictoriaMetrics | `8428` | Time-series metrics |
| Grafana | `3001` | Raw metric exploration |
| Nginx | `80` / `443` | Reverse proxy |

### 4. Open the app

```
http://localhost:3000
```

Default login is created on first run. Check the backend logs for the initial admin credentials:

```bash
docker compose logs backend | grep "admin"
```

---

### Optional: Run with RBAC (Enterprise Auth)

For role-based access control with JWT authentication (Admin / NOC / User roles):

```bash
cp .env.rbac .env
docker compose -f docker-compose.rbac.yml up -d
```

The RBAC stack runs on separate ports:

| Service | Port |
|---|---|
| Frontend (RBAC) | `3200` |
| Backend API (RBAC) | `8200` |

---

### Useful commands

```bash
# View logs
docker compose logs -f backend
docker compose logs -f worker

# Stop all services
docker compose down

# Stop and wipe all data volumes
docker compose down -v

# Rebuild after code changes
docker compose up -d --build
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy |
| Frontend | Next.js 14 · TypeScript · Tailwind CSS |
| Database | PostgreSQL 16 |
| Time-Series | VictoriaMetrics |
| Task Queue | Celery + Redis |
| AI Assistant | Claude Opus 4.6 (Anthropic) |
| Deployment | Docker Compose · Nginx |
| BMC Protocol | Redfish (OpenBMC / HPE iLO) |
