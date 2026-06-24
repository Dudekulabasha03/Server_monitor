# Quick Start Guide — AMD Fleet Monitor

## Prerequisites

- Docker Desktop (Windows) or Docker + Docker Compose (Linux)
- Node.js 20+ (for frontend dev)
- Python 3.12+ (for backend dev)
- `ipmitool` (for IPMI collection — Linux only, or WSL on Windows)

---

## 1. Clone & Configure

```bash
# Copy example env
cp .env.example .env
# Edit .env — fill in POSTGRES_PASSWORD and SECRET_KEY at minimum
```

---

## 2. Start Infrastructure

```bash
docker compose up -d postgres redis victoriametrics
# Wait for healthy status
docker compose ps
```

---

## 3. Run Database Migrations

```bash
cd backend
pip install poetry
poetry install
poetry run alembic upgrade head
```

---

## 4. Start Backend

```bash
# Development
cd backend
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or via Docker
docker compose up -d backend worker beat
```

---

## 5. Start Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

---

## 6. Add Your First Servers

Using the API (or the UI once running):

```bash
# Add volcano-eb87.amd.com
curl -X POST http://localhost:8000/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "volcano-eb87",
    "fqdn": "volcano-eb87.amd.com",
    "bmc_ip": "<BMC_IP>",
    "bmc_port": 443,
    "vendor": "amd_crb",
    "datacenter": "AMD-DC1",
    "rack": "A01",
    "rack_unit": 12,
    "environment": "production",
    "team": "Infrastructure",
    "redfish_enabled": true,
    "ipmi_enabled": true
  }'

# Add titanite-d310.amd.com
curl -X POST http://localhost:8000/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "titanite-d310",
    "fqdn": "titanite-d310.amd.com",
    "bmc_ip": "<BMC_IP>",
    "datacenter": "AMD-DC1",
    "rack": "A02",
    "rack_unit": 8,
    "environment": "production"
  }'

# Add daytonax42cd.amd.com
curl -X POST http://localhost:8000/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "daytonax42cd",
    "fqdn": "daytonax42cd.amd.com",
    "bmc_ip": "<BMC_IP>",
    "datacenter": "AMD-DC1",
    "rack": "B01",
    "rack_unit": 4,
    "environment": "production"
  }'
```

---

## 7. Configure BMC Credentials

**IMPORTANT:** Never put BMC passwords in the database directly.

### Option A: HashiCorp Vault (Recommended for Production)
```bash
# Store credentials in Vault
vault kv put secret/fleet-monitor/servers/<server-id> \
  username=root \
  password=<bmc_password>
```

### Option B: Environment Variable (Dev/Lab only)
```bash
# In .env — for testing only
DEFAULT_BMC_USERNAME=root
DEFAULT_BMC_PASSWORD=your_bmc_password
```

---

## 8. Trigger a Collection

```bash
# Manually trigger Redfish collection for a server
curl -X POST http://localhost:8000/api/v1/servers/<server-id>/collect
```

---

## 9. Full Docker Stack

```bash
# Start everything
docker compose up -d

# Check logs
docker compose logs -f backend
docker compose logs -f worker

# Access
# Dashboard:       http://localhost:3000
# API Docs:        http://localhost:8000/api/docs
# VictoriaMetrics: http://localhost:8428
# Grafana:         http://localhost:3001
```

---

## API Docs

Full interactive API documentation at: http://localhost:8000/api/docs

Key endpoints:
- `GET /api/v1/servers/summary` — Fleet health summary
- `GET /api/v1/servers` — Server list with metrics
- `GET /api/v1/servers/{id}` — Server detail
- `GET /api/v1/alerts` — Active alerts
- `POST /api/v1/alerts/{id}/acknowledge` — Acknowledge alert

---

## Production Deployment

```bash
# Build production images
docker compose -f docker-compose.yml build

# Push to your registry
docker tag fleetmon-backend your-registry.amd.com/fleet-monitor/backend:v1.0.0
docker push your-registry.amd.com/fleet-monitor/backend:v1.0.0

# Deploy to Kubernetes
kubectl apply -f deploy/kubernetes/fleet-monitor.yaml

# Create secrets
kubectl create secret generic fleet-monitor-secrets \
  --from-literal=DATABASE_URL="postgresql+asyncpg://..." \
  --from-literal=SECRET_KEY="..." \
  --from-literal=SMTP_PASSWORD="..." \
  --from-literal=TEAMS_WEBHOOK_URL="..." \
  -n fleet-monitor
```

---

## Troubleshooting

### Redfish connection fails
- Verify BMC IP is reachable from the collector host
- Check BMC HTTPS is enabled (port 443)
- Try: `curl -k -u root:password https://<bmc-ip>/redfish/v1/`
- For AMD CRB servers, check if Redfish service is enabled in BMC settings

### IPMI collection fails
- Ensure `ipmitool` is installed: `ipmitool -V`
- Test: `ipmitool -I lanplus -H <bmc-ip> -U root -P password chassis status`
- Check firewall — IPMI uses UDP port 623

### High memory usage in VictoriaMetrics
- Reduce retention: `-retentionPeriod=30d`
- Or increase the VM container memory limit in docker-compose.yml
