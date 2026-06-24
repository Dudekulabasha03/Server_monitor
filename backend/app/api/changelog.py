"""Changelog feed — status/power/drift transition events."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.intelligence import ChangeEvent

router = APIRouter(prefix="/api/v1/changelog", tags=["changelog"])


@router.get("")
async def changelog(
    hours: int = 24,
    kind: Optional[str] = None,
    host: Optional[str] = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = select(ChangeEvent).where(ChangeEvent.created_at >= cutoff)
    if kind:
        q = q.where(ChangeEvent.kind == kind)
    if host:
        q = q.where(ChangeEvent.hostname.ilike(f"%{host}%"))
    q = q.order_by(ChangeEvent.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()

    total = (await db.execute(
        select(func.count(ChangeEvent.id)).where(ChangeEvent.created_at >= cutoff)
    )).scalar() or 0

    return {
        "total": total,
        "hours": hours,
        "events": [{
            "timestamp": e.created_at.isoformat() if e.created_at else None,
            "kind": e.kind,
            "hostname": e.hostname,
            "old_value": e.old_value,
            "new_value": e.new_value,
        } for e in rows],
    }
