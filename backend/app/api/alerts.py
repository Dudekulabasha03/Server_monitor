from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timezone

from app.database import get_db
from app.models.alerts import Alert, AlertState, AlertSeverity

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(
    state: Optional[str] = "firing",
    severity: Optional[str] = None,
    server_id: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
    db: AsyncSession = Depends(get_db),
):
    query = select(Alert)
    if state:
        query = query.where(Alert.state == state)
    if severity:
        query = query.where(Alert.severity == severity)
    if server_id:
        query = query.where(Alert.server_id == server_id)
    if category:
        query = query.where(Alert.category == category)

    query = query.order_by(Alert.fired_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    acknowledged_by: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.state = AlertState.ACKNOWLEDGED
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = acknowledged_by
    return {"status": "acknowledged"}


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.state = AlertState.RESOLVED
    alert.resolved_at = datetime.now(timezone.utc)
    return {"status": "resolved"}


@router.get("/stats")
async def alert_stats(db: AsyncSession = Depends(get_db)):
    """Count of alerts by severity and state — for dashboard badges."""
    from sqlalchemy import func
    result = await db.execute(
        select(Alert.severity, Alert.state, func.count(Alert.id))
        .where(Alert.state == AlertState.FIRING)
        .group_by(Alert.severity, Alert.state)
    )
    rows = result.all()
    stats = {"critical": 0, "warning": 0, "info": 0, "emergency": 0}
    for severity, state, count in rows:
        key = severity.value if hasattr(severity, "value") else str(severity)
        stats[key] = count
    return stats
