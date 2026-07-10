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

## Features

- Live fleet health dashboard with real-time telemetry
- Per-server drill-down: CPU, memory, power, thermals, storage, network
- AI-powered ops assistant ("Ask Helios")
- Automated alert engine with SEL event parsing
- BIOS/firmware compliance tracking and remote flash
- RBAC with role-based access (Admin, NOC, User)
- Changelog and audit trail

## Tech Stack

- **Backend:** Python / FastAPI
- **Frontend:** Next.js / TypeScript
- **Database:** MongoDB
- **Task Queue:** Celery + Redis
- **Deployment:** Docker Compose
- **BMC Protocol:** Redfish (OpenBMC / HPE iLO)
