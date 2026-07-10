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

## Tech Stack

- **Backend:** Python / FastAPI
- **Frontend:** Next.js / TypeScript
- **Database:** MongoDB
- **Task Queue:** Celery + Redis
- **Deployment:** Docker Compose
- **BMC Protocol:** Redfish (OpenBMC / HPE iLO)
