"""Autonomous SEL triage — audit feed + controls (kill switch, shadow toggle, manual run)."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.intelligence import TriageLog
from app.config import settings

router = APIRouter(prefix="/api/v1/triage", tags=["triage"])


@router.get("")
async def triage_log(
    hours: int = 168,
    verdict: Optional[str] = None,
    host: Optional[str] = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = select(TriageLog).where(TriageLog.created_at >= cutoff)
    if verdict:
        q = q.where(TriageLog.verdict == verdict)
    if host:
        q = q.where(TriageLog.hostname.ilike(f"%{host}%"))
    q = q.order_by(TriageLog.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()

    # Verdict breakdown over the window
    counts = dict((await db.execute(
        select(TriageLog.verdict, func.count(TriageLog.id))
        .where(TriageLog.created_at >= cutoff).group_by(TriageLog.verdict)
    )).all())

    return {
        "config": {
            "enabled": settings.SEL_AUTOTRIAGE_ENABLED,
            "shadow": settings.SEL_AUTOTRIAGE_SHADOW,
            "autonomy_paused": settings.AUTONOMY_PAUSED,
            "interval_s": settings.SEL_AUTOTRIAGE_INTERVAL,
        },
        "hours": hours,
        "counts": counts,
        "events": [{
            "timestamp": r.created_at.isoformat() if r.created_at else None,
            "hostname": r.hostname,
            "severity": r.severity,
            "message": r.message,
            "verdict": r.verdict,
            "confidence": r.confidence,
            "reasoning": r.reasoning,
            "action_taken": r.action_taken,
            "shadow": r.shadow,
            "alert_id": r.alert_id,
        } for r in rows],
    }


@router.get("/status")
async def triage_status():
    """Current autonomy configuration (for a settings/control panel)."""
    return {
        "enabled": settings.SEL_AUTOTRIAGE_ENABLED,
        "shadow": settings.SEL_AUTOTRIAGE_SHADOW,
        "autonomy_paused": settings.AUTONOMY_PAUSED,
        "interval_s": settings.SEL_AUTOTRIAGE_INTERVAL,
    }


@router.post("/run")
async def triage_run_now():
    """Trigger a triage sweep immediately (does not wait for the beat schedule)."""
    from app.tasks.collection import autonomous_sel_triage
    return await autonomous_sel_triage()
