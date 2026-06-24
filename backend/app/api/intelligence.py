"""Fleet intelligence endpoints — risk ranking, recommendations, optimization, RCA."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.server import Server, MetricsSnapshot
from app.models.intelligence import RiskScore, Recommendation
from app.models.alerts import Alert
from app.models.users import UserSession

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])


async def _latest_risk(db: AsyncSession):
    res = await db.execute(
        select(RiskScore).distinct(RiskScore.server_id)
        .order_by(RiskScore.server_id, RiskScore.scored_at.desc())
    )
    return {r.server_id: r for r in res.scalars().all()}


@router.get("/risk")
async def risk_ranking(db: AsyncSession = Depends(get_db)):
    servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
    latest = await _latest_risk(db)
    rows = []
    for sid, risk in latest.items():
        s = servers.get(sid)
        if not s:
            continue
        rows.append({
            "id": sid, "hostname": s.hostname, "rack": s.rack,
            "health_score": s.health_score, "status": s.status.value if s.status else "unknown",
            "overall_risk": risk.overall_risk, "risk_level": risk.risk_level,
            "disk_risk": risk.disk_risk, "psu_risk": risk.psu_risk, "fan_risk": risk.fan_risk,
            "memory_risk": risk.memory_risk, "thermal_risk": risk.thermal_risk,
            "factors": risk.factors or [],
        })
    rows.sort(key=lambda r: r["overall_risk"], reverse=True)
    return {
        "servers": rows,
        "summary": {
            "high": sum(1 for r in rows if r["risk_level"] == "high"),
            "medium": sum(1 for r in rows if r["risk_level"] == "medium"),
            "low": sum(1 for r in rows if r["risk_level"] == "low"),
        },
        "top_risk": rows[:10],
    }


@router.get("/recommendations")
async def recommendations(db: AsyncSession = Depends(get_db)):
    servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
    res = await db.execute(
        select(Recommendation).where(Recommendation.dismissed == False)  # noqa: E712
        .order_by(Recommendation.created_at.desc())
    )
    recos = res.scalars().all()
    sev_order = {"critical": 0, "warning": 1, "info": 2}
    rows = [{
        "id": r.id, "server_id": r.server_id,
        "hostname": servers[r.server_id].hostname if r.server_id in servers else "—",
        "category": r.category, "severity": r.severity,
        "title": r.title, "body": r.body, "rationale": r.rationale, "steps": r.steps or [],
    } for r in recos]
    rows.sort(key=lambda r: sev_order.get(r["severity"], 9))
    return {"recommendations": rows, "total": len(rows)}


@router.get("/recommendations/by-server")
async def recommendations_by_server(db: AsyncSession = Depends(get_db)):
    """Group active recommendations per server (for individual server view)."""
    servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
    res = await db.execute(
        select(Recommendation).where(Recommendation.dismissed == False)  # noqa: E712
        .order_by(Recommendation.created_at.desc())
    )
    grouped: dict = {}
    for r in res.scalars().all():
        g = grouped.setdefault(r.server_id, {
            "server_id": r.server_id,
            "hostname": servers[r.server_id].hostname if r.server_id in servers else "—",
            "items": [],
        })
        g["items"].append({"id": r.id, "category": r.category, "severity": r.severity,
                           "title": r.title, "body": r.body, "rationale": r.rationale, "steps": r.steps or []})
    return {"servers": list(grouped.values())}


@router.get("/recommendations/server/{server_id}")
async def recommendations_for_server(server_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Recommendation).where(
            Recommendation.server_id == server_id,
            Recommendation.dismissed == False,  # noqa: E712
        ).order_by(Recommendation.created_at.desc())
    )
    return {"recommendations": [
        {"id": r.id, "category": r.category, "severity": r.severity,
         "title": r.title, "body": r.body, "rationale": r.rationale, "steps": r.steps or []}
        for r in res.scalars().all()
    ]}


@router.post("/recommendations/{reco_id}/dismiss")
async def dismiss_reco(reco_id: str, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(Recommendation).where(Recommendation.id == reco_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Recommendation not found")
    r.dismissed = True
    return {"status": "dismissed"}


@router.get("/optimization")
async def optimization(db: AsyncSession = Depends(get_db)):
    from app.engines.optimization import ResourceOptimizer
    opt = ResourceOptimizer()
    servers = (await db.execute(select(Server))).scalars().all()
    sess = (await db.execute(select(UserSession).where(UserSession.is_active == True))).scalars().all()  # noqa: E712
    active_users = {s.server_id for s in sess}

    snaps = {snap.server_id: snap for snap in (await db.execute(
        select(MetricsSnapshot).distinct(MetricsSnapshot.server_id)
        .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
    )).scalars().all()}

    buckets = {"active": [], "idle": [], "underutilized": [], "overutilized": [], "unknown": []}
    waste_watts = 0.0
    for s in servers:
        snap = snaps.get(s.id)
        u = opt.classify(snap, s.id in active_users)
        buckets.setdefault(u.category, []).append({"id": s.id, "hostname": s.hostname, "reason": u.reason})
        waste_watts += opt.waste_watts(snap, u)

    return {
        "categories": {k: {"count": len(v), "servers": v} for k, v in buckets.items()},
        "reclaimable_watts": round(waste_watts, 1),
    }


@router.get("/rca/{alert_id}")
async def rca(alert_id: str, db: AsyncSession = Depends(get_db)):
    from app.engines.rca import RCAEngine
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")
    snap = (await db.execute(
        select(MetricsSnapshot).where(MetricsSnapshot.server_id == alert.server_id)
        .order_by(MetricsSnapshot.collected_at.desc()).limit(1)
    )).scalar_one_or_none()
    res = RCAEngine().analyze(alert, snap)
    return {
        "alert_id": alert_id, "alert_title": alert.title,
        "possible_causes": res.possible_causes, "impact": res.impact,
        "recommended_actions": res.recommended_actions, "correlated_signals": res.correlated_signals,
    }


@router.get("/fleet-summary")
async def fleet_intelligence_summary(db: AsyncSession = Depends(get_db)):
    """Combined health + risk + utilization + energy for the executive intelligence view."""
    servers = (await db.execute(select(Server))).scalars().all()
    latest_risk = await _latest_risk(db)
    snaps = {snap.server_id: snap for snap in (await db.execute(
        select(MetricsSnapshot).distinct(MetricsSnapshot.server_id)
        .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
    )).scalars().all()}

    high_risk = sum(1 for r in latest_risk.values() if r.risk_level == "high")
    total_power = sum(s.power_consumed_watts for s in snaps.values() if s.power_consumed_watts)
    reco_count = len((await db.execute(
        select(Recommendation).where(Recommendation.dismissed == False))).scalars().all())  # noqa: E712

    return {
        "total_servers": len(servers),
        "high_risk_servers": high_risk,
        "open_recommendations": reco_count,
        "total_power_watts": round(total_power, 1),
        "monthly_cost_est": round((total_power / 1000) * 24 * 30 * 1.5 * 0.12, 2),
        "monthly_carbon_kg": round((total_power / 1000) * 24 * 30 * 1.5 * 0.37, 1),
    }
