"""FastAPI routes for server CRUD and metrics."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

from app.database import get_db
from app.models.server import Server, MetricsSnapshot, ServerStatus, ServerVendor, DimmSlot, Disk, PSU, NIC
from app.models.health import HealthScore

router = APIRouter(prefix="/api/v1/servers", tags=["servers"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ServerCreate(BaseModel):
    hostname: str
    bmc_ip: str
    bmc_port: int = 443
    os_ip: Optional[str] = None
    ipmi_ip: Optional[str] = None
    vendor: Optional[ServerVendor] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    asset_tag: Optional[str] = None
    datacenter: str = "AMD-DC1"
    room: Optional[str] = None
    rack: Optional[str] = None
    rack_unit: Optional[int] = None
    environment: str = "production"
    team: Optional[str] = None
    project: Optional[str] = None
    tags: List[str] = []
    redfish_enabled: bool = True
    ipmi_enabled: bool = True
    # Credentials (per-server; CredentialProvider reads these first)
    bmc_username: Optional[str] = None
    bmc_password: Optional[str] = None
    os_username: Optional[str] = None
    os_password: Optional[str] = None


class ServerUpdate(BaseModel):
    display_name: Optional[str] = None
    team: Optional[str] = None
    project: Optional[str] = None
    tags: Optional[List[str]] = None
    rack: Optional[str] = None
    rack_unit: Optional[int] = None
    environment: Optional[str] = None
    os_ip: Optional[str] = None
    bmc_username: Optional[str] = None
    bmc_password: Optional[str] = None
    os_username: Optional[str] = None
    os_password: Optional[str] = None
    redfish_enabled: Optional[bool] = None
    ipmi_enabled: Optional[bool] = None
    os_agent_enabled: Optional[bool] = None
    collect_interval: Optional[int] = None


class ServerSummary(BaseModel):
    id: str
    hostname: str
    fqdn: Optional[str]
    bmc_ip: Optional[str]
    os_ip: Optional[str]
    vendor: Optional[str]
    model: Optional[str]
    family: Optional[str]
    datacenter: str
    rack: Optional[str]
    rack_unit: Optional[int]
    status: str
    health_score: Optional[float]
    cpu_usage_avg: Optional[float]
    memory_usage_pct: Optional[float]
    cpu_temp_max: Optional[float]
    power_consumed_watts: Optional[float]
    sensor_health: Optional[str]
    last_seen: Optional[datetime]
    team: Optional[str]
    environment: str
    tags: List[str]

    class Config:
        from_attributes = True


class FleetSummary(BaseModel):
    total: int
    healthy: int
    warning: int
    at_risk: int
    critical: int
    offline: int
    unknown: int
    avg_health_score: Optional[float]
    total_power_watts: Optional[float]
    avg_cpu_pct: Optional[float]
    avg_memory_pct: Optional[float]
    avg_cpu_temp: Optional[float]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/summary", response_model=FleetSummary)
async def get_fleet_summary(
    datacenter: Optional[str] = None,
    environment: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Executive summary — total counts by status + aggregate metrics."""
    query = select(Server)
    if datacenter:
        query = query.where(Server.datacenter == datacenter)
    if environment:
        query = query.where(Server.environment == environment)

    result = await db.execute(query)
    servers = result.scalars().all()

    status_counts = {s.value: 0 for s in ServerStatus}
    for s in servers:
        key = s.status.value if s.status else "unknown"
        status_counts[key] = status_counts.get(key, 0) + 1

    health_scores = [s.health_score for s in servers if s.health_score is not None]

    # Get latest snapshot per server (DISTINCT ON — one row/server, not whole table)
    snap_q = (
        select(MetricsSnapshot)
        .where(MetricsSnapshot.server_id.in_([s.id for s in servers]))
        .distinct(MetricsSnapshot.server_id)
        .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
    )
    snap_result = await db.execute(snap_q)
    snapshots = snap_result.scalars().all()
    latest_by_server: dict = {snap.server_id: snap for snap in snapshots}

    snaps = list(latest_by_server.values())
    # Guard against BMC sentinel/garbage power readings (negative or absurdly large)
    total_power = sum(s.power_consumed_watts for s in snaps
                      if s.power_consumed_watts and 0 < s.power_consumed_watts < 50000)
    cpu_vals = [s.cpu_usage_avg for s in snaps if s.cpu_usage_avg is not None]
    mem_vals = [s.memory_usage_pct for s in snaps if s.memory_usage_pct is not None]
    temp_vals = [s.cpu_temp_avg for s in snaps if s.cpu_temp_avg is not None]

    return FleetSummary(
        total=len(servers),
        healthy=status_counts.get("healthy", 0),
        warning=status_counts.get("warning", 0),
        at_risk=status_counts.get("at_risk", 0),
        critical=status_counts.get("critical", 0),
        offline=status_counts.get("offline", 0),
        unknown=status_counts.get("unknown", 0),
        avg_health_score=round(sum(health_scores) / len(health_scores), 1) if health_scores else None,
        total_power_watts=total_power if total_power else None,
        avg_cpu_pct=round(sum(cpu_vals) / len(cpu_vals), 1) if cpu_vals else None,
        avg_memory_pct=round(sum(mem_vals) / len(mem_vals), 1) if mem_vals else None,
        avg_cpu_temp=round(sum(temp_vals) / len(temp_vals), 1) if temp_vals else None,
    )


@router.get("", response_model=List[ServerSummary])
async def list_servers(
    status: Optional[str] = None,
    datacenter: Optional[str] = None,
    rack: Optional[str] = None,
    team: Optional[str] = None,
    environment: Optional[str] = None,
    family: Optional[str] = None,
    search: Optional[str] = None,
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    sort_by: str = "health_score",
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List all servers with latest snapshot metrics. Supports filtering and search."""
    query = select(Server)

    if status:
        query = query.where(Server.status == status)
    if datacenter:
        query = query.where(Server.datacenter == datacenter)
    if rack:
        query = query.where(Server.rack == rack)
    if team:
        query = query.where(Server.team == team)
    if environment:
        query = query.where(Server.environment == environment)
    if family:
        query = query.where(or_(
            Server.family == family,
            Server.family.ilike(f"%{family}%"),
            Server.model.ilike(f"%{family}%"),
        ))
    if search:
        query = query.where(or_(
            Server.hostname.ilike(f"%{search}%"),
            Server.bmc_ip.ilike(f"%{search}%"),
            Server.model.ilike(f"%{search}%"),
            Server.serial_number.ilike(f"%{search}%"),
        ))

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    servers = result.scalars().all()

    # Pull latest snapshot per server (DISTINCT ON — one row/server)
    server_ids = [s.id for s in servers]
    snap_result = await db.execute(
        select(MetricsSnapshot)
        .where(MetricsSnapshot.server_id.in_(server_ids))
        .distinct(MetricsSnapshot.server_id)
        .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
    )
    latest: dict = {snap.server_id: snap for snap in snap_result.scalars().all()}

    summaries = []
    for server in servers:
        snap = latest.get(server.id)
        summaries.append(ServerSummary(
            id=server.id,
            hostname=server.hostname,
            fqdn=server.fqdn,
            bmc_ip=server.bmc_ip,
            os_ip=server.os_ip,
            vendor=server.vendor.value if server.vendor else None,
            model=server.model,
            family=server.family,
            datacenter=server.datacenter,
            rack=server.rack,
            rack_unit=server.rack_unit,
            status=server.status.value if server.status else "unknown",
            health_score=server.health_score,
            cpu_usage_avg=snap.cpu_usage_avg if snap else None,
            memory_usage_pct=snap.memory_usage_pct if snap else None,
            cpu_temp_max=snap.cpu_temp_max if snap else None,
            power_consumed_watts=snap.power_consumed_watts if snap else None,
            sensor_health=getattr(snap, "sensor_health", None) if snap else None,
            last_seen=server.last_seen,
            team=server.team,
            environment=server.environment or "production",
            tags=server.tags or [],
        ))

    return summaries


@router.get("/{server_id}")
async def get_server_detail(server_id: str, db: AsyncSession = Depends(get_db)):
    """Full server detail with latest metrics + component health."""
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    # Latest snapshot
    snap_result = await db.execute(
        select(MetricsSnapshot)
        .where(MetricsSnapshot.server_id == server_id)
        .order_by(MetricsSnapshot.collected_at.desc())
        .limit(1)
    )
    snapshot = snap_result.scalar_one_or_none()

    # Latest health score
    hs_result = await db.execute(
        select(HealthScore)
        .where(HealthScore.server_id == server_id)
        .order_by(HealthScore.scored_at.desc())
        .limit(1)
    )
    health = hs_result.scalar_one_or_none()

    # Components
    dimms = (await db.execute(select(DimmSlot).where(DimmSlot.server_id == server_id))).scalars().all()
    disks = (await db.execute(select(Disk).where(Disk.server_id == server_id))).scalars().all()
    psus = (await db.execute(select(PSU).where(PSU.server_id == server_id))).scalars().all()
    nics = (await db.execute(select(NIC).where(NIC.server_id == server_id))).scalars().all()

    raw = (snapshot.raw_sensors or {}) if snapshot else {}
    sel_events = raw.get("sel_events", [])
    processors = raw.get("processors", [])

    return {
        "server": server,
        "snapshot": snapshot,
        "health_score": health,
        "components": {"dimms": dimms, "disks": disks, "psus": psus, "nics": nics},
        "processors": processors,
        "sel_events": sel_events,
    }


@router.post("", status_code=201)
async def create_server(payload: ServerCreate, full_refresh: bool = True, db: AsyncSession = Depends(get_db)):
    """Register a new server. With full_refresh=true (default), immediately fetch
    BMC (Redfish) + PRISM hardware + OS (SSH) so the server populates right away."""
    data = payload.model_dump()
    # Auto-enable OS agent when OS creds + IP are supplied
    os_agent = bool(data.get("os_ip") and data.get("os_username") and data.get("os_password"))
    server = Server(id=str(uuid.uuid4()), os_agent_enabled=os_agent, **data)
    # Best-effort family guess from hostname codename (collector refines from BMC model)
    from app.utils.family import family_from_codename
    server.family = family_from_codename(server.hostname)
    db.add(server)
    await db.flush()
    server_id = server.id
    hostname = server.hostname
    await db.commit()

    refresh = None
    if full_refresh:
        from app.tasks.collection import full_refresh_server
        try:
            refresh = await full_refresh_server(server_id)
        except Exception as e:
            refresh = {"error": str(e)}
    return {"id": server_id, "hostname": hostname, "refresh": refresh}


@router.post("/{server_id}/os-refresh")
async def os_refresh(server_id: str, db: AsyncSession = Depends(get_db)):
    """Trigger an immediate OS-agent (SSH) collection for one server.

    Enables os_agent if OS creds/IP are present, then collects CPU/mem/sessions now.
    """
    server = (await db.execute(select(Server).where(Server.id == server_id))).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if server.os_ip:
        server.os_agent_enabled = True
    await db.commit()
    from app.tasks.collection import collect_os_all
    return await collect_os_all(only_server_id=server_id)


@router.post("/{server_id}/full-refresh")
async def full_refresh_endpoint(server_id: str, db: AsyncSession = Depends(get_db)):
    """Re-fetch everything (Redfish + PRISM + OS) for one server on demand."""
    server = (await db.execute(select(Server).where(Server.id == server_id))).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    from app.tasks.collection import full_refresh_server
    return await full_refresh_server(server_id)


@router.patch("/{server_id}")
async def update_server(server_id: str, payload: ServerUpdate, db: AsyncSession = Depends(get_db)):
    """Update server metadata."""
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(server, field, value)
    return {"status": "updated"}


@router.post("/{server_id}/prism-refresh")
async def prism_refresh(server_id: str, db: AsyncSession = Depends(get_db)):
    """Enrich one server's hardware + OS IP from PRISM on demand."""
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    from app.tasks.collection import enrich_from_prism
    summary = await enrich_from_prism(only_hostname=server.hostname)
    return summary


@router.delete("/{server_id}", status_code=204)
async def delete_server(server_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a server from inventory."""
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    await db.delete(server)


@router.get("/{server_id}/metrics/history")
async def get_metrics_history(
    server_id: str,
    metric: str = "cpu_usage_avg",
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
):
    """Return time-series of a metric for a server (from snapshots table)."""
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(MetricsSnapshot.collected_at, getattr(MetricsSnapshot, metric, None))
        .where(MetricsSnapshot.server_id == server_id)
        .where(MetricsSnapshot.collected_at >= cutoff)
        .order_by(MetricsSnapshot.collected_at.asc())
    )
    rows = result.all()
    return [{"timestamp": r[0].isoformat(), "value": r[1]} for r in rows if r[1] is not None]


@router.get("/{server_id}/health/history")
async def get_health_history(
    server_id: str,
    hours: int = 48,
    db: AsyncSession = Depends(get_db),
):
    """Return health score trend for a server."""
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(HealthScore)
        .where(HealthScore.server_id == server_id)
        .where(HealthScore.scored_at >= cutoff)
        .order_by(HealthScore.scored_at.asc())
    )
    scores = result.scalars().all()
    return [{"timestamp": s.scored_at.isoformat(), "score": s.total_score, "status": s.status} for s in scores]
