"""Utilization-history endpoints — how much the fleet is used over time.

"Used" = a snapshot whose util_bucket is active/heavy (a test/workload was running)
OR whose OS CPU usage exceeded a small threshold. Aggregated per calendar period
(day/week/month/year) from the metrics_snapshots history.

Honesty note: raw snapshots are pruned to SNAPSHOT_RETENTION_HOURS (48h), so deep
daily history is bounded by retention; weekly/monthly/yearly buckets only fill as
history accrues. The window each response covers is returned in `coverage`.
"""
from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.server import Server, MetricsSnapshot

router = APIRouter(prefix="/api/v1/usage", tags=["usage"])

_TRUNC = {"daily": "day", "weekly": "week", "monthly": "month", "yearly": "year"}
_ACTIVE_BUCKETS = ["active", "heavy"]
CPU_USED_THRESHOLD = 10.0  # % — OS CPU above this counts as "in use"


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_date(s: Optional[str]):
    if not s:
        return None
    try:
        # accept YYYY-MM-DD or full ISO
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


async def _scoped_server_ids(db, team: Optional[str], family: Optional[str]):
    """Return server-id list matching team/family filters, or None if no filter."""
    if not team and not family:
        return None
    q = select(Server.id)
    if team:
        q = q.where(Server.team == team)
    if family:
        q = q.where(Server.family == family)
    return [r[0] for r in (await db.execute(q)).all()]


@router.get("/summary")
async def usage_summary(
    period: str = Query("daily", pattern="^(daily|weekly|monthly|yearly)$"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    team: Optional[str] = None,
    family: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Fleet-wide usage over time, bucketed by calendar period.

    Optional filters: date_from/date_to (ISO), team, family.
    Returns, per period bucket: used_servers, executions (active/heavy datapoints), avg_util.
    """
    trunc = _TRUNC[period]
    bexpr = func.date_trunc(trunc, MetricsSnapshot.collected_at)
    used_filter = MetricsSnapshot.util_bucket.in_(_ACTIVE_BUCKETS)

    q = select(
        bexpr.label("b"),
        func.count(func.distinct(MetricsSnapshot.server_id)).filter(used_filter).label("used_servers"),
        func.count(MetricsSnapshot.id).filter(used_filter).label("executions"),
        func.avg(MetricsSnapshot.util_score).label("avg_util"),
        func.count(func.distinct(MetricsSnapshot.server_id)).label("reporting_servers"),
    )

    df, dt = _parse_date(date_from), _parse_date(date_to)
    if df:
        q = q.where(MetricsSnapshot.collected_at >= df)
    if dt:
        q = q.where(MetricsSnapshot.collected_at <= dt)
    ids = await _scoped_server_ids(db, team, family)
    if ids is not None:
        if not ids:
            return {"period": period, "points": [], "coverage": {"from": None, "to": None}}
        q = q.where(MetricsSnapshot.server_id.in_(ids))

    rows = (await db.execute(q.group_by("b").order_by("b"))).all()

    points = [{
        "t": r[0].isoformat() if r[0] else None,
        "used_servers": int(r[1] or 0),
        "executions": int(r[2] or 0),
        "avg_util": round(float(r[3]), 2) if r[3] is not None else 0.0,
        "reporting_servers": int(r[4] or 0),
    } for r in rows]

    bounds = (await db.execute(
        select(func.min(MetricsSnapshot.collected_at), func.max(MetricsSnapshot.collected_at))
    )).first()
    return {
        "period": period,
        "points": points,
        "coverage": {
            "from": bounds[0].isoformat() if bounds and bounds[0] else None,
            "to": bounds[1].isoformat() if bounds and bounds[1] else None,
        },
    }


@router.get("/by-server")
async def usage_by_server(
    days: int = 30,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    team: Optional[str] = None,
    family: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Per-server usage: distinct days each server was 'used' + total executions.

    Window is date_from..date_to if given, else the last `days`. Optional team/family.
    """
    day = func.date_trunc("day", MetricsSnapshot.collected_at)
    used_filter = MetricsSnapshot.util_bucket.in_(_ACTIVE_BUCKETS)

    q = select(
        MetricsSnapshot.server_id,
        func.count(func.distinct(day)).filter(used_filter).label("active_days"),
        func.count(MetricsSnapshot.id).filter(used_filter).label("executions"),
        func.avg(MetricsSnapshot.util_score).label("avg_util"),
    )

    df, dt = _parse_date(date_from), _parse_date(date_to)
    if df or dt:
        if df:
            q = q.where(MetricsSnapshot.collected_at >= df)
        if dt:
            q = q.where(MetricsSnapshot.collected_at <= dt)
    else:
        q = q.where(MetricsSnapshot.collected_at >= _utcnow() - timedelta(days=days))

    ids = await _scoped_server_ids(db, team, family)
    if ids is not None:
        if not ids:
            return {"window_days": days, "servers": []}
        q = q.where(MetricsSnapshot.server_id.in_(ids))

    rows = (await db.execute(q.group_by(MetricsSnapshot.server_id))).all()

    servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
    out = []
    for r in rows:
        srv = servers.get(r[0])
        out.append({
            "server_id": r[0],
            "hostname": srv.hostname if srv else "—",
            "family": srv.family if srv else None,
            "team": srv.team if srv else None,
            "active_days": int(r[1] or 0),
            "executions": int(r[2] or 0),
            "avg_util": round(float(r[3]), 2) if r[3] is not None else 0.0,
        })
    out.sort(key=lambda x: x["executions"], reverse=True)
    return {"window_days": days, "servers": out}
