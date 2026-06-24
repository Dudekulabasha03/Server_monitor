"""User activity / utilization tracking endpoints (from OS agent data)."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.server import Server, MetricsSnapshot
from app.models.users import UserSession

router = APIRouter(prefix="/api/v1/users", tags=["users"])

# A session only counts as truly "active" if its server was reconciled by the OS
# agent recently. Unreachable servers can't clear their sessions, so we treat
# sessions whose server hasn't been re-collected within this window as stale.
SESSION_FRESH_SECONDS = 600


@router.get("/sessions")
async def active_sessions(db: AsyncSession = Depends(get_db)):
    servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
    res = await db.execute(
        select(UserSession).where(UserSession.is_active == True).order_by(UserSession.login_at.desc())  # noqa: E712
    )
    sessions = res.scalars().all()
    now = datetime.now(timezone.utc)
    rows = []
    stale = 0
    for s in sessions:
        srv = servers.get(s.server_id)
        # Drop sessions whose server hasn't been freshly collected (can't be verified live)
        login = s.login_at
        fresh = login is not None and (now - login).total_seconds() <= SESSION_FRESH_SECONDS
        if not fresh:
            stale += 1
            continue
        rows.append({
            "id": s.id, "server_id": s.server_id,
            "hostname": srv.hostname if srv else "—",
            "username": s.username, "full_name": s.full_name, "team": s.team,
            "session_type": s.session_type, "source_ip": s.source_ip,
            "login_at": s.login_at.isoformat() if s.login_at else None,
            "cpu_avg_pct": s.cpu_avg_pct, "memory_avg_pct": s.memory_avg_pct,
        })
    return {"sessions": rows, "total": len(rows), "stale_excluded": stale}


@router.get("/idle-servers")
async def idle_servers(cpu_threshold: float = 5.0, db: AsyncSession = Depends(get_db)):
    """Classify servers as idle vs active based on CPU usage + active sessions."""
    servers = (await db.execute(select(Server))).scalars().all()
    res = await db.execute(
        select(MetricsSnapshot)
        .distinct(MetricsSnapshot.server_id)
        .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
    )
    snaps = {snap.server_id: snap for snap in res.scalars().all()}
    sess_res = await db.execute(select(UserSession).where(UserSession.is_active == True))  # noqa: E712
    active_servers = {s.server_id for s in sess_res.scalars().all()}

    idle, active = [], []
    for s in servers:
        snap = snaps.get(s.id)
        cpu = snap.cpu_usage_avg if snap else None
        has_users = s.id in active_servers
        entry = {"id": s.id, "hostname": s.hostname, "cpu_usage_avg": cpu, "has_active_users": has_users}
        if (cpu is not None and cpu < cpu_threshold) and not has_users:
            idle.append(entry)
        else:
            active.append(entry)
    return {"idle": idle, "active": active, "idle_count": len(idle), "active_count": len(active)}


@router.get("/activity")
async def fleet_activity(cpu_threshold: float = 5.0, db: AsyncSession = Depends(get_db)):
    """Fleet-wide activity: EVERY server with its OS-level activity state, so the page
    scales with the fleet instead of only showing the ~handful of SSH-reachable hosts.

    activity = in_use  (active user session, or CPU >= threshold)
             | idle    (OS reachable, CPU < threshold, no users)
             | no-data (OS agent not enabled / never returned CPU — unreachable)
    """
    servers = (await db.execute(select(Server))).scalars().all()
    res = await db.execute(
        select(MetricsSnapshot)
        .distinct(MetricsSnapshot.server_id)
        .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
    )
    snaps = {snap.server_id: snap for snap in res.scalars().all()}
    sess_res = await db.execute(select(UserSession).where(UserSession.is_active == True))  # noqa: E712
    sess_by_server: dict = {}
    for us in sess_res.scalars().all():
        sess_by_server.setdefault(us.server_id, 0)
        sess_by_server[us.server_id] += 1

    rows = []
    counts = {"in_use": 0, "idle": 0, "no_data": 0}
    for s in servers:
        snap = snaps.get(s.id)
        cpu = snap.cpu_usage_avg if snap else None
        mem = snap.memory_usage_pct if snap else None
        n_sessions = sess_by_server.get(s.id, 0)
        os_reachable = bool(s.os_agent_enabled) and cpu is not None
        if n_sessions > 0 or (cpu is not None and cpu >= cpu_threshold):
            activity = "in_use"
        elif cpu is not None:
            activity = "idle"
        else:
            activity = "no_data"
        counts[activity] += 1
        rows.append({
            "id": s.id, "hostname": s.hostname,
            "team": s.team, "family": s.family, "datacenter": s.datacenter,
            "os_ip": s.os_ip, "os_reachable": os_reachable,
            "cpu_usage_avg": cpu, "memory_usage_pct": mem,
            "active_sessions": n_sessions, "activity": activity,
        })
    rows.sort(key=lambda r: (r["activity"] != "in_use", r["hostname"]))
    return {"servers": rows, "total": len(rows), "counts": counts}
