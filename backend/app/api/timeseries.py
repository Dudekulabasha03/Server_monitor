"""Time-series + analytics endpoints for the Live Lab dashboard. Sources from Postgres snapshots."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.server import Server, MetricsSnapshot, ServerStatus
from app.models.health import HealthScore
from app.models.alerts import Alert, AlertState
from app.engines.analytics import downsample, rolling_band, linreg_forecast, range_to_delta

router = APIRouter(prefix="/api/v1/ts", tags=["timeseries"])

NUMERIC_METRICS = {
    "cpu_temp_max", "cpu_temp_avg", "inlet_temp", "outlet_temp",
    "cpu_usage_avg", "memory_usage_pct", "power_consumed_watts",
    "disk_usage_max_pct", "fan_speed_avg_rpm", "load_avg_1m",
}


def _utcnow():
    return datetime.now(timezone.utc)


@router.get("/server/{server_id}")
async def server_timeseries(
    server_id: str,
    metrics: str = "cpu_temp_max,power_consumed_watts",
    range: str = "24h",
    db: AsyncSession = Depends(get_db),
):
    cutoff = _utcnow() - range_to_delta(range)
    wanted = [m.strip() for m in metrics.split(",") if m.strip() in NUMERIC_METRICS]
    cols = [getattr(MetricsSnapshot, m) for m in wanted]
    rows = (await db.execute(
        select(MetricsSnapshot.collected_at, *cols)
        .where(MetricsSnapshot.server_id == server_id, MetricsSnapshot.collected_at >= cutoff)
        .order_by(MetricsSnapshot.collected_at.asc())
    )).all()
    out = {}
    for i, m in enumerate(wanted):
        pts = [(r[0], r[i + 1]) for r in rows if r[i + 1] is not None]
        out[m] = downsample(pts)
    return {"server_id": server_id, "range": range, "series": out}


@router.get("/fleet")
async def fleet_timeseries(
    metrics: str = "cpu_temp_max,power_consumed_watts",
    range: str = "24h",
    agg: str = "avg",
    db: AsyncSession = Depends(get_db),
):
    cutoff = _utcnow() - range_to_delta(range)
    wanted = [m.strip() for m in metrics.split(",") if m.strip() in NUMERIC_METRICS]
    agg_fn = func.max if agg == "max" else func.avg
    # Bucket by minute across the fleet
    bucket = func.date_trunc("minute", MetricsSnapshot.collected_at)
    out = {}
    for m in wanted:
        col = getattr(MetricsSnapshot, m)
        rows = (await db.execute(
            select(bucket.label("b"), agg_fn(col))
            .where(MetricsSnapshot.collected_at >= cutoff, col.isnot(None))
            .group_by("b").order_by("b")
        )).all()
        pts = [(r[0], float(r[1])) for r in rows if r[1] is not None]
        out[m] = downsample(pts)
    return {"range": range, "agg": agg, "series": out}


def _trend(curr: Optional[float], prev: Optional[float]):
    if curr is None:
        return {"value": None, "change": None, "dir": "flat"}
    if prev is None or prev == 0:
        return {"value": round(curr, 1), "change": None, "dir": "flat"}
    chg = curr - prev
    return {"value": round(curr, 1), "change": round(chg, 1),
            "dir": "up" if chg > 0.5 else "down" if chg < -0.5 else "flat"}


@router.get("/kpis")
async def kpis(db: AsyncSession = Depends(get_db)):
    now = _utcnow()
    day_ago = now - timedelta(hours=24)

    servers = (await db.execute(select(Server))).scalars().all()
    status_counts = {s.value: 0 for s in ServerStatus}
    for s in servers:
        k = s.status.value if s.status else "unknown"
        status_counts[k] = status_counts.get(k, 0) + 1
    health_vals = [s.health_score for s in servers if s.health_score is not None]

    # latest snapshot per server
    snaps = {}
    for snap in (await db.execute(select(MetricsSnapshot).order_by(MetricsSnapshot.collected_at.desc()))).scalars().all():
        if snap.server_id not in snaps:
            snaps[snap.server_id] = snap
    cur = list(snaps.values())

    def fleet_avg(attr):
        vals = [getattr(s, attr) for s in cur if getattr(s, attr) is not None]
        return sum(vals) / len(vals) if vals else None

    def fleet_sum(attr):
        vals = [getattr(s, attr) for s in cur if getattr(s, attr) is not None]
        return sum(vals) if vals else None

    # 24h-ago fleet averages (one bucket) for trend
    async def avg_at(attr, ts_lo, ts_hi):
        col = getattr(MetricsSnapshot, attr)
        r = (await db.execute(
            select(func.avg(col)).where(MetricsSnapshot.collected_at.between(ts_lo, ts_hi), col.isnot(None))
        )).scalar()
        return float(r) if r is not None else None

    async def sum_at(attr, ts_lo, ts_hi):
        # approximate prior total = avg-per-server * server count
        col = getattr(MetricsSnapshot, attr)
        r = (await db.execute(
            select(func.avg(col)).where(MetricsSnapshot.collected_at.between(ts_lo, ts_hi), col.isnot(None))
        )).scalar()
        return float(r) * len(servers) if r is not None else None

    # sparkline helper: hourly fleet avg over 24h
    async def spark(attr, aggfn=func.avg):
        b = func.date_trunc("hour", MetricsSnapshot.collected_at)
        col = getattr(MetricsSnapshot, attr)
        rows = (await db.execute(
            select(aggfn(col)).where(MetricsSnapshot.collected_at >= day_ago, col.isnot(None))
            .group_by(b).order_by(b)
        )).all()
        return [round(float(r[0]), 1) for r in rows if r[0] is not None]

    win = timedelta(minutes=30)
    cur_temp = fleet_avg("cpu_temp_max")
    prev_temp = await avg_at("cpu_temp_max", day_ago - win, day_ago + win)
    cur_cpu = fleet_avg("cpu_usage_avg")
    prev_cpu = await avg_at("cpu_usage_avg", day_ago - win, day_ago + win)
    cur_mem = fleet_avg("memory_usage_pct")
    prev_mem = await avg_at("memory_usage_pct", day_ago - win, day_ago + win)
    cur_pwr = fleet_sum("power_consumed_watts")
    prev_pwr = await sum_at("power_consumed_watts", day_ago - win, day_ago + win)

    active_alerts = len((await db.execute(select(Alert).where(Alert.state == AlertState.FIRING))).scalars().all())
    avg_health = sum(health_vals) / len(health_vals) if health_vals else None

    return {
        "counts": {
            "total": len(servers),
            "healthy": status_counts.get("healthy", 0),
            "warning": status_counts.get("warning", 0) + status_counts.get("at_risk", 0),
            "critical": status_counts.get("critical", 0),
            "offline": status_counts.get("offline", 0) + status_counts.get("unknown", 0),
        },
        "cards": {
            "avg_cpu_temp": {**_trend(cur_temp, prev_temp), "spark": await spark("cpu_temp_max")},
            "avg_cpu": {**_trend(cur_cpu, prev_cpu), "spark": await spark("cpu_usage_avg")},
            "avg_memory": {**_trend(cur_mem, prev_mem), "spark": await spark("memory_usage_pct")},
            "total_power": {**_trend(cur_pwr, prev_pwr), "spark": await spark("power_consumed_watts", func.sum)},
            "active_alerts": {"value": active_alerts, "change": None, "dir": "flat", "spark": []},
            "fleet_health_score": {"value": round(avg_health, 1) if avg_health else None, "change": None, "dir": "flat", "spark": []},
        },
    }


@router.get("/heartbeat")
async def heartbeat(db: AsyncSession = Depends(get_db)):
    now = _utcnow()
    servers = (await db.execute(select(Server))).scalars().all()
    rows = []
    for s in servers:
        if s.last_seen:
            delta = (now - s.last_seen).total_seconds()
            state = "alive" if delta < 120 else "late" if delta < 600 else "stale"
        else:
            delta = None
            state = "stale"
        rows.append({
            "id": s.id, "hostname": s.hostname, "datacenter": s.datacenter,
            "status": s.status.value if s.status else "unknown",
            "last_seen": s.last_seen.isoformat() if s.last_seen else None,
            "seconds_since": round(delta) if delta is not None else None,
            "beat": state,
        })
    rows.sort(key=lambda r: (r["beat"] != "stale", r["hostname"]))
    return {
        "servers": rows,
        "summary": {
            "alive": sum(1 for r in rows if r["beat"] == "alive"),
            "late": sum(1 for r in rows if r["beat"] == "late"),
            "stale": sum(1 for r in rows if r["beat"] == "stale"),
        },
    }


@router.get("/anomalies")
async def anomalies(
    metric: str = "cpu_temp_max",
    range: str = "6h",
    server_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    if metric not in NUMERIC_METRICS:
        metric = "cpu_temp_max"
    cutoff = _utcnow() - range_to_delta(range)
    col = getattr(MetricsSnapshot, metric)
    if server_id:
        rows = (await db.execute(
            select(MetricsSnapshot.collected_at, col)
            .where(MetricsSnapshot.server_id == server_id, MetricsSnapshot.collected_at >= cutoff, col.isnot(None))
            .order_by(MetricsSnapshot.collected_at)
        )).all()
        pts = [(r[0], float(r[1])) for r in rows]
    else:
        b = func.date_trunc("minute", MetricsSnapshot.collected_at)
        rows = (await db.execute(
            select(b, func.avg(col)).where(MetricsSnapshot.collected_at >= cutoff, col.isnot(None))
            .group_by(b).order_by(b)
        )).all()
        pts = [(r[0], float(r[1])) for r in rows]
    return {"metric": metric, "range": range, **rolling_band(pts)}


@router.get("/forecast")
async def forecast(
    metric: str = "cpu_temp_max",
    range: str = "24h",
    horizon_hours: int = 24,
    cap: Optional[float] = None,
    server_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    if metric not in NUMERIC_METRICS:
        metric = "cpu_temp_max"
    cutoff = _utcnow() - range_to_delta(range)
    col = getattr(MetricsSnapshot, metric)
    if server_id:
        rows = (await db.execute(
            select(MetricsSnapshot.collected_at, col)
            .where(MetricsSnapshot.server_id == server_id, MetricsSnapshot.collected_at >= cutoff, col.isnot(None))
            .order_by(MetricsSnapshot.collected_at)
        )).all()
        pts = [(r[0], float(r[1])) for r in rows]
    else:
        b = func.date_trunc("minute", MetricsSnapshot.collected_at)
        rows = (await db.execute(
            select(b, func.avg(col)).where(MetricsSnapshot.collected_at >= cutoff, col.isnot(None))
            .group_by(b).order_by(b)
        )).all()
        pts = [(r[0], float(r[1])) for r in rows]
    step = 60 if horizon_hours <= 48 else 360
    return {"metric": metric, **linreg_forecast(pts, horizon_hours=horizon_hours, step_minutes=step, cap=cap)}


@router.get("/correlation")
async def correlation(range: str = "6h", server_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    cutoff = _utcnow() - range_to_delta(range)
    q = select(MetricsSnapshot.power_consumed_watts, MetricsSnapshot.cpu_temp_max).where(
        MetricsSnapshot.collected_at >= cutoff,
        MetricsSnapshot.power_consumed_watts.isnot(None),
        MetricsSnapshot.cpu_temp_max.isnot(None),
    )
    if server_id:
        q = q.where(MetricsSnapshot.server_id == server_id)
    rows = (await db.execute(q)).all()
    points = [{"power": round(float(r[0]), 1), "temp": round(float(r[1]), 1)} for r in rows]
    return {"range": range, "points": points[:2000]}
