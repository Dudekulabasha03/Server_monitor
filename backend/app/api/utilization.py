"""Utilization (PIPT-style) dashboard endpoints. Sources from Postgres snapshots + live PIPT."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.database import get_db
from app.models.server import Server, MetricsSnapshot, ServerStatus

router = APIRouter(prefix="/api/v1/util", tags=["utilization"])

BUCKETS = ["idle", "light", "active", "heavy", "unknown", "off"]


def _utcnow():
    return datetime.now(timezone.utc)


def _range_delta(window: str) -> timedelta:
    return {
        "15m": timedelta(minutes=15), "1h": timedelta(hours=1), "6h": timedelta(hours=6),
        "24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30),
    }.get(window, timedelta(days=7))


from app.utils.family import derive_family


def _family(server) -> str:
    """CPU family for a server: prefer the stored family column, else derive from model."""
    fam = getattr(server, "family", None)
    if fam:
        return fam
    return derive_family(getattr(server, "cpu_model", None) or getattr(server, "model", None)) or "Unknown"


FAMILY_ORDER = ["Naples", "Rome", "Milan", "Genoa", "Bergamo", "Siena", "Sorano", "Turin", "Unknown"]


async def _latest_snaps(db: AsyncSession):
    res = await db.execute(
        select(MetricsSnapshot)
        .distinct(MetricsSnapshot.server_id)
        .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
    )
    return {s.server_id: s for s in res.scalars().all()}


@router.get("/summary")
async def summary(window: str = "7d", db: AsyncSession = Depends(get_db)):
    now = _utcnow()
    cutoff = now - _range_delta(window)
    servers = (await db.execute(select(Server))).scalars().all()
    latest = await _latest_snaps(db)

    fresh = sum(1 for s in servers if s.last_seen and (now - s.last_seen).total_seconds() < 600)
    # bucket distribution from latest snapshots
    dist = {b: 0 for b in BUCKETS}
    idle_now = 0
    for s in servers:
        snap = latest.get(s.id)
        b = (snap.util_bucket if snap else None) or "unknown"
        dist[b] = dist.get(b, 0) + 1
        if b == "idle":
            idle_now += 1
    total = len(servers)
    active_heavy = dist.get("active", 0) + dist.get("heavy", 0)

    datapoints = (await db.execute(
        select(func.count(MetricsSnapshot.id)).where(MetricsSnapshot.collected_at >= cutoff)
    )).scalar() or 0

    # OS-agent coverage: servers with fresh CPU/mem from SSH
    os_enabled = sum(1 for s in servers if s.os_agent_enabled)
    os_reporting = sum(1 for s in servers
                       if (snap := latest.get(s.id)) and snap.cpu_usage_avg is not None
                       and (now - snap.collected_at).total_seconds() < 300)

    pct = lambda n: round(100 * n / total, 0) if total else 0
    return {
        "hosts_reporting": fresh, "hosts_total": total,
        "idle_now": idle_now, "idle_pct": pct(idle_now),
        "tests_executing": active_heavy,
        "needs_attention": dist.get("heavy", 0),
        "datapoints": datapoints,
        "os_agent_enabled": os_enabled, "os_metrics_count": os_reporting,
        "buckets": {b: dist.get(b, 0) for b in BUCKETS},
        "bucket_pct": {b: pct(dist.get(b, 0)) for b in BUCKETS},
        "window": window,
    }


@router.get("/by-family")
async def by_family(db: AsyncSession = Depends(get_db)):
    servers = (await db.execute(select(Server))).scalars().all()
    latest = await _latest_snaps(db)
    fams: dict = {}
    for s in servers:
        fam = _family(s)
        snap = latest.get(s.id)
        b = (snap.util_bucket if snap else None) or "unknown"
        g = fams.setdefault(fam, {"family": fam, "total": 0, "buckets": {x: 0 for x in BUCKETS}})
        g["total"] += 1
        g["buckets"][b] = g["buckets"].get(b, 0) + 1
    return {"families": sorted(fams.values(),
                               key=lambda x: FAMILY_ORDER.index(x["family"]) if x["family"] in FAMILY_ORDER else 99)}


def _status_str(s) -> str:
    return s.status.value if s.status else "unknown"


def _blank_health():
    return {"total": 0, "healthy": 0, "warning": 0, "critical": 0, "offline": 0,
            "unknown": 0, "health_sum": 0.0, "health_n": 0}


def _tally(bucket, s):
    bucket["total"] += 1
    st = _status_str(s)
    if st == "healthy":
        bucket["healthy"] += 1
    elif st in ("warning", "at_risk"):
        bucket["warning"] += 1
    elif st == "critical":
        bucket["critical"] += 1
    elif st == "offline":
        bucket["offline"] += 1
    else:  # unknown / any other status — must still count toward the total
        bucket["unknown"] += 1
    if s.health_score is not None:
        bucket["health_sum"] += float(s.health_score)
        bucket["health_n"] += 1


def _finalize(bucket):
    n = bucket.pop("health_n")
    hs = bucket.pop("health_sum")
    bucket["avg_health"] = round(hs / n, 1) if n else None
    return bucket


@router.get("/by-team")
async def by_team(db: AsyncSession = Depends(get_db)):
    """Fleet grouped by team, each with a per-family breakdown + a Total bucket.

    Powers the Dashboard's Total + Team-wise (family-wise underneath) view.
    """
    servers = (await db.execute(select(Server))).scalars().all()

    total = _blank_health()
    total_fams: dict = {}
    teams: dict = {}

    for s in servers:
        fam = _family(s)
        team = s.team or "Unassigned"

        _tally(total, s)
        tf = total_fams.setdefault(fam, _blank_health())
        _tally(tf, s)

        tg = teams.setdefault(team, {"team": team, "summary": _blank_health(), "_fams": {}})
        _tally(tg["summary"], s)
        fg = tg["_fams"].setdefault(fam, _blank_health())
        _tally(fg, s)

    def _fam_list(fammap):
        out = []
        for fam, b in fammap.items():
            row = _finalize(b)
            row["family"] = fam
            out.append(row)
        return sorted(out, key=lambda x: FAMILY_ORDER.index(x["family"]) if x["family"] in FAMILY_ORDER else 99)

    team_rows = []
    for t in teams.values():
        team_rows.append({
            "team": t["team"],
            "summary": _finalize(t["summary"]),
            "families": _fam_list(t["_fams"]),
        })
    team_rows.sort(key=lambda x: x["summary"]["total"], reverse=True)

    return {
        "total": _finalize(total),
        "total_families": _fam_list(total_fams),
        "teams": team_rows,
    }


@router.get("/timeline")
async def timeline(metric: str = "util", window: str = "7d", db: AsyncSession = Depends(get_db)):
    cutoff = _utcnow() - _range_delta(window)
    # bucket by hour, avg util_score (util) or count of active+heavy (tests)
    bucket_expr = func.date_trunc("hour", MetricsSnapshot.collected_at)
    if metric == "tests":
        val = func.count(MetricsSnapshot.id).filter(MetricsSnapshot.util_bucket.in_(["active", "heavy"]))
    else:
        val = func.avg(MetricsSnapshot.util_score)
    rows = (await db.execute(
        select(bucket_expr.label("b"), val)
        .where(MetricsSnapshot.collected_at >= cutoff, MetricsSnapshot.util_bucket.isnot(None))
        .group_by("b").order_by("b")
    )).all()
    return {"metric": metric, "window": window,
            "points": [{"t": r[0].isoformat(), "v": round(float(r[1]), 2) if r[1] is not None else 0} for r in rows]}


@router.get("/hour-of-week")
async def hour_of_week(metric: str = "util", db: AsyncSession = Depends(get_db)):
    # 7x24 grid across ALL stored history. dow: 0=Sunday (postgres EXTRACT dow)
    if metric == "tests":
        val = func.count(MetricsSnapshot.id).filter(MetricsSnapshot.util_bucket.in_(["active", "heavy"]))
    else:
        val = func.avg(MetricsSnapshot.util_score)
    dow = func.extract("dow", MetricsSnapshot.collected_at)
    hour = func.extract("hour", MetricsSnapshot.collected_at)
    rows = (await db.execute(
        select(dow.label("d"), hour.label("h"), val)
        .where(MetricsSnapshot.util_bucket.isnot(None))
        .group_by("d", "h")
    )).all()
    grid = [{"dow": int(r[0]), "hour": int(r[1]), "value": round(float(r[2]), 2) if r[2] is not None else 0} for r in rows]
    return {"metric": metric, "grid": grid}


@router.get("/attention")
async def attention(db: AsyncSession = Depends(get_db)):
    """Live PIPT availability: heavy / blocked / stale hosts needing attention."""
    from app.collectors.pipt_client import PiptClient, normalize_host
    avail = await PiptClient().availability()
    hosts = avail.get("hosts", []) if isinstance(avail, dict) else []
    rows = []
    for h in hosts:
        blocked = h.get("blocked_by") or []
        bucket = h.get("bucket")
        stale = h.get("stale")
        if bucket == "heavy" or blocked or stale:
            rows.append({
                "host": normalize_host(h.get("host")), "family": h.get("family"),
                "location": h.get("location"), "bucket": bucket,
                "blocked_by": blocked, "stale": stale, "score": h.get("score"),
            })
    return {
        "hosts": rows,
        "summary": {
            "heavy": sum(1 for r in rows if r["bucket"] == "heavy"),
            "blocked": sum(1 for r in rows if r["blocked_by"]),
            "stale": sum(1 for r in rows if r["stale"]),
        },
    }
