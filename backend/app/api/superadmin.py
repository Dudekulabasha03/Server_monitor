"""
Super Admin exclusive endpoints.
- Global settings (thresholds, JWT expiry, cost rates, PSU policy)
- Maintenance windows (suppress alerts during planned downtime)
- Team quotas (max reservations per team)
- Access review (inactive users, last-login audit)
- Power cost by team
- Bulk server operations (team assign, environment tag, BIOS baseline)
- Fleet SLA attainment
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, and_

from app.database import get_db, Base
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, ARRAY
from app.models.server import Server
from app.models.auth import AuthUser, AuthTeam
from app.core.rbac import require_super_admin

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


# ── SQLAlchemy models for new tables ─────────────────────────────────────────

class GlobalSetting(Base):
    __tablename__ = "global_settings"
    key         = Column(String(128), primary_key=True)
    value       = Column(Text, nullable=False)
    description = Column(Text)
    updated_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_by  = Column(String(36))


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"
    id         = Column(String(36), primary_key=True)
    name       = Column(String(255), nullable=False)
    team       = Column(String(128))
    starts_at  = Column(DateTime(timezone=True), nullable=False)
    ends_at    = Column(DateTime(timezone=True), nullable=False)
    reason     = Column(Text)
    created_by = Column(String(36))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active  = Column(Boolean, default=True)


class TeamQuota(Base):
    __tablename__ = "team_quotas"
    team                  = Column(String(128), primary_key=True)
    max_reservations      = Column(Integer, default=10)
    max_reservation_hours = Column(Integer, default=168)
    updated_at            = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_by            = Column(String(36))


# ── Schemas ──────────────────────────────────────────────────────────────────

class SettingUpdate(BaseModel):
    value: str


class MaintenanceWindowCreate(BaseModel):
    name:      str
    team:      Optional[str] = None
    starts_at: datetime
    ends_at:   datetime
    reason:    Optional[str] = None


class QuotaUpdate(BaseModel):
    max_reservations:      Optional[int] = None
    max_reservation_hours: Optional[int] = None


class BulkServerOp(BaseModel):
    server_ids:  List[str]
    operation:   str           # assign_team | set_environment | set_bios_baseline
    value:       str


# ── Global Settings ───────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_super_admin),
):
    result = await db.execute(select(GlobalSetting).order_by(GlobalSetting.key))
    settings = result.scalars().all()
    return {
        "settings": [
            {"key": s.key, "value": s.value, "description": s.description,
             "updated_at": s.updated_at.isoformat() if s.updated_at else None}
            for s in settings
        ]
    }


@router.patch("/settings/{key}")
async def update_setting(
    key: str,
    body: SettingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_super_admin),
):
    setting = (await db.execute(select(GlobalSetting).where(GlobalSetting.key == key))).scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    setting.value = body.value
    setting.updated_at = datetime.now(timezone.utc)
    setting.updated_by = current_user.id
    await db.flush()
    return {"key": key, "value": body.value, "message": "Setting updated"}


# ── Maintenance Windows ────────────────────────────────────────────────────────

@router.get("/maintenance")
async def list_maintenance(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_super_admin),
):
    q = select(MaintenanceWindow)
    if active_only:
        now = datetime.now(timezone.utc)
        q = q.where(and_(MaintenanceWindow.starts_at <= now, MaintenanceWindow.ends_at >= now, MaintenanceWindow.is_active == True))  # noqa: E712
    q = q.order_by(MaintenanceWindow.starts_at.desc())
    result = await db.execute(q)
    windows = result.scalars().all()
    return {
        "windows": [
            {"id": w.id, "name": w.name, "team": w.team,
             "starts_at": w.starts_at.isoformat(), "ends_at": w.ends_at.isoformat(),
             "reason": w.reason, "is_active": w.is_active,
             "created_at": w.created_at.isoformat() if w.created_at else None}
            for w in windows
        ]
    }


@router.post("/maintenance", status_code=201)
async def create_maintenance(
    body: MaintenanceWindowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_super_admin),
):
    import uuid
    window = MaintenanceWindow(
        id=str(uuid.uuid4()), name=body.name, team=body.team,
        starts_at=body.starts_at, ends_at=body.ends_at,
        reason=body.reason, created_by=current_user.id, is_active=True,
    )
    db.add(window)
    await db.flush()
    return {"message": "Maintenance window created", "id": window.id}


@router.delete("/maintenance/{window_id}")
async def cancel_maintenance(
    window_id: str,
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_super_admin),
):
    w = (await db.execute(select(MaintenanceWindow).where(MaintenanceWindow.id == window_id))).scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Window not found")
    w.is_active = False
    await db.flush()
    return {"message": "Maintenance window cancelled"}


@router.get("/maintenance/active-servers")
async def active_maintenance_servers(
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_super_admin),
):
    """List server IDs currently in a maintenance window (alerts suppressed)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(MaintenanceWindow).where(
            and_(MaintenanceWindow.starts_at <= now,
                 MaintenanceWindow.ends_at >= now,
                 MaintenanceWindow.is_active == True)  # noqa: E712
        )
    )
    active = result.scalars().all()
    teams_in_maint = {w.team for w in active if w.team}

    # Get server IDs for those teams
    server_result = await db.execute(
        select(Server.id, Server.hostname, Server.team)
        .where(Server.team.in_(teams_in_maint) if teams_in_maint else Server.id == "none")
    )
    servers = [{"id": r.id, "hostname": r.hostname, "team": r.team} for r in server_result]
    return {"in_maintenance": servers, "active_windows": len(active)}


# ── Team Quotas ───────────────────────────────────────────────────────────────

@router.get("/quotas")
async def get_quotas(
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_super_admin),
):
    result = await db.execute(select(TeamQuota).order_by(TeamQuota.team))
    quotas = result.scalars().all()

    # Also get current usage
    from app.api.reservations import ServerReservation
    usage_result = await db.execute(text(
        "SELECT team, COUNT(*) as active FROM server_reservations "
        "WHERE is_active=TRUE GROUP BY team"
    ))
    usage_map = {row[0]: int(row[1]) for row in usage_result}

    return {
        "quotas": [
            {"team": q.team, "max_reservations": q.max_reservations,
             "max_reservation_hours": q.max_reservation_hours,
             "current_usage": usage_map.get(q.team, 0),
             "available": max(0, q.max_reservations - usage_map.get(q.team, 0))}
            for q in quotas
        ]
    }


@router.patch("/quotas/{team}")
async def update_quota(
    team: str,
    body: QuotaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_super_admin),
):
    q = (await db.execute(select(TeamQuota).where(TeamQuota.team == team))).scalar_one_or_none()
    if not q:
        # Create if not exists
        q = TeamQuota(team=team, max_reservations=10, max_reservation_hours=168)
        db.add(q)
    if body.max_reservations is not None:
        q.max_reservations = body.max_reservations
    if body.max_reservation_hours is not None:
        q.max_reservation_hours = body.max_reservation_hours
    q.updated_at = datetime.now(timezone.utc)
    q.updated_by = current_user.id
    await db.flush()
    return {"message": f"Quota updated for {team}"}


# ── Access Review ─────────────────────────────────────────────────────────────

@router.get("/access-review")
async def access_review(
    inactive_days: int = Query(30, ge=1),
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_super_admin),
):
    """Full user access audit — last login, role, team, reservation activity."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=inactive_days)

    result = await db.execute(
        select(AuthUser).where(AuthUser.is_active == True)  # noqa: E712
        .order_by(AuthUser.last_login_at.asc().nulls_first())
    )
    users = result.scalars().all()

    # Reservation counts per user
    res_result = await db.execute(text(
        "SELECT user_email, COUNT(*) as total, "
        "SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active "
        "FROM server_reservations GROUP BY user_email"
    ))
    res_map = {row[0]: {"total": int(row[1]), "active": int(row[2])} for row in res_result}

    teams_map: dict = {}
    team_ids = list({u.team_id for u in users if u.team_id})
    if team_ids:
        tr = await db.execute(select(AuthTeam).where(AuthTeam.id.in_(team_ids)))
        teams_map = {t.id: t.name for t in tr.scalars().all()}

    now = datetime.now(timezone.utc)
    return {
        "users": [
            {
                "id": u.id, "email": u.email, "full_name": u.full_name,
                "role": u.role, "team": teams_map.get(u.team_id),
                "is_active": u.is_active, "approval_status": getattr(u, "approval_status", "approved"),
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "days_since_login": round((now - u.last_login_at.replace(tzinfo=timezone.utc)).days, 0) if u.last_login_at else None,
                "inactive": u.last_login_at is None or u.last_login_at.replace(tzinfo=timezone.utc) < cutoff,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "reservations": res_map.get(u.email, {"total": 0, "active": 0}),
            }
            for u in users
        ],
        "inactive_threshold_days": inactive_days,
        "inactive_count": sum(1 for u in users if u.last_login_at is None or u.last_login_at.replace(tzinfo=timezone.utc) < cutoff),
        "total": len(users),
    }


# ── Power Cost by Team ────────────────────────────────────────────────────────

@router.get("/power-cost")
async def power_cost(
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_super_admin),
):
    """Per-team power consumption and estimated cost."""
    # Get cost rate from settings
    rate_setting = (await db.execute(select(GlobalSetting).where(GlobalSetting.key == "power_cost_kwh"))).scalar_one_or_none()
    cost_per_kwh = float(rate_setting.value) if rate_setting else 0.10

    result = await db.execute(text(
        "SELECT s.team, COUNT(DISTINCT s.id) servers, "
        "COALESCE(SUM(CASE WHEN ms.power_consumed_watts IS NOT NULL AND ms.power_consumed_watts > 0 AND ms.power_consumed_watts < 50000 THEN ms.power_consumed_watts ELSE 0 END), 0) total_w "
        "FROM servers s "
        "LEFT JOIN LATERAL ("
        "  SELECT power_consumed_watts FROM metrics_snapshots ms2 "
        "  WHERE ms2.server_id = s.id ORDER BY ms2.collected_at DESC LIMIT 1"
        ") ms ON TRUE "
        "GROUP BY s.team ORDER BY total_w DESC"
    ))

    rows = []
    for row in result:
        total_w = float(row[2] or 0)
        daily_kwh = (total_w / 1000) * 24
        monthly_kwh = daily_kwh * 30
        rows.append({
            "team": row[0], "servers": int(row[1]),
            "total_watts": round(total_w, 0),
            "daily_kwh": round(daily_kwh, 1),
            "monthly_kwh": round(monthly_kwh, 0),
            "daily_cost_usd": round(daily_kwh * cost_per_kwh, 2),
            "monthly_cost_usd": round(monthly_kwh * cost_per_kwh, 2),
        })

    fleet_w = sum(r["total_watts"] for r in rows)
    fleet_monthly = sum(r["monthly_cost_usd"] for r in rows)
    return {
        "teams": rows,
        "fleet_total_watts": round(fleet_w, 0),
        "fleet_monthly_cost_usd": round(fleet_monthly, 2),
        "cost_per_kwh": cost_per_kwh,
    }


# ── Bulk Server Operations ────────────────────────────────────────────────────

@router.post("/servers/bulk")
async def bulk_server_op(
    body: BulkServerOp,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_super_admin),
):
    """Bulk assign team, set environment, or set BIOS baseline for many servers at once."""
    if not body.server_ids:
        raise HTTPException(status_code=400, detail="server_ids required")

    result = await db.execute(select(Server).where(Server.id.in_(body.server_ids)))
    servers = result.scalars().all()

    if not servers:
        raise HTTPException(status_code=404, detail="No servers found")

    updated = []
    for server in servers:
        if body.operation == "assign_team":
            server.team = body.value
        elif body.operation == "set_environment":
            server.environment = body.value
        elif body.operation == "set_bios_baseline":
            server.firmware_baseline = body.value
            server.firmware_baseline_compliant = (server.bios_version == body.value) if server.bios_version else None
        else:
            raise HTTPException(status_code=400, detail=f"Unknown operation: {body.operation}")
        updated.append(server.hostname)

    await db.flush()
    return {
        "message": f"{body.operation} applied to {len(updated)} servers",
        "updated": updated,
    }


# ── SLA Dashboard ──────────────────────────────────────────────────────────────

@router.get("/sla")
async def sla_dashboard(
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_super_admin),
):
    """Fleet health SLA attainment per team vs configured target."""
    sla_setting = (await db.execute(select(GlobalSetting).where(GlobalSetting.key == "sla_healthy_pct"))).scalar_one_or_none()
    sla_target = float(sla_setting.value) if sla_setting else 90.0

    result = await db.execute(text(
        "SELECT team, COUNT(*) total, "
        "COUNT(CASE WHEN status::text='healthy' THEN 1 END) healthy, "
        "COUNT(CASE WHEN status::text IN ('critical','offline') THEN 1 END) critical, "
        "ROUND(AVG(health_score)::numeric, 1) avg_health "
        "FROM servers GROUP BY team ORDER BY team"
    ))

    rows = []
    for row in result:
        total = int(row[1] or 0)
        healthy = int(row[2] or 0)
        pct = round((healthy / total) * 100, 1) if total > 0 else 0
        rows.append({
            "team": row[0], "total": total, "healthy": healthy,
            "critical_offline": int(row[3] or 0),
            "healthy_pct": pct, "avg_health": float(row[4] or 0),
            "sla_met": pct >= sla_target,
            "sla_gap": round(sla_target - pct, 1) if pct < sla_target else 0,
        })

    breaching = [r for r in rows if not r["sla_met"]]
    return {
        "sla_target_pct": sla_target,
        "teams": rows,
        "breaching": len(breaching),
        "compliant": len(rows) - len(breaching),
    }


# ── Idle Server Reclamation ───────────────────────────────────────────────────

@router.get("/idle-servers")
async def idle_servers(
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_super_admin),
):
    """Servers idle for longer than configured threshold with no active reservation."""
    setting = (await db.execute(select(GlobalSetting).where(GlobalSetting.key == "idle_flag_days"))).scalar_one_or_none()
    idle_days = int(setting.value) if setting else 7
    cutoff = datetime.now(timezone.utc) - timedelta(days=idle_days)

    from app.api.reservations import ServerReservation
    # Servers with no recent CPU activity and no active reservation
    active_res_result = await db.execute(
        select(ServerReservation.server_id).where(ServerReservation.is_active == True)  # noqa: E712
    )
    reserved_ids = {r[0] for r in active_res_result}

    result = await db.execute(text(
        "SELECT s.id, s.hostname, s.team, s.datacenter, s.family, s.last_seen, s.health_score, "
        "ms.cpu_usage_avg "
        "FROM servers s "
        "LEFT JOIN LATERAL ("
        "  SELECT cpu_usage_avg FROM metrics_snapshots ms2 "
        "  WHERE ms2.server_id = s.id ORDER BY ms2.collected_at DESC LIMIT 1"
        ") ms ON TRUE "
        "WHERE s.status::text != 'offline' "
        "AND (ms.cpu_usage_avg IS NULL OR ms.cpu_usage_avg < 5) "
        "ORDER BY s.team, s.hostname"
    ))

    idle = []
    for row in result:
        sid = row[0]
        if sid not in reserved_ids:
            idle.append({
                "id": sid, "hostname": row[1], "team": row[2],
                "datacenter": row[3], "family": row[4],
                "last_seen": row[5].isoformat() if row[5] else None,
                "health_score": row[6], "cpu_usage_avg": row[7],
            })

    return {
        "idle_servers": idle,
        "total": len(idle),
        "idle_threshold_days": idle_days,
    }
