"""Server lifecycle management — warranty, EOL, EOS tracking."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
from app.database import get_db
from app.models.server import Server

router = APIRouter(prefix="/api/v1/lifecycle", tags=["lifecycle"])


class LifecycleUpdate(BaseModel):
    procurement_date: Optional[datetime] = None
    installation_date: Optional[datetime] = None
    warranty_start: Optional[datetime] = None
    warranty_expiry: Optional[datetime] = None
    eol_date: Optional[datetime] = None
    eos_date: Optional[datetime] = None
    support_contract: Optional[str] = None


def _risk(days: Optional[int]) -> str:
    if days is None:
        return "unknown"
    if days < 0:
        return "expired"
    if days < 90:
        return "expiring_soon"
    return "supported"


@router.get("")
async def lifecycle(db: AsyncSession = Depends(get_db)):
    servers = (await db.execute(select(Server))).scalars().all()
    now = datetime.now(timezone.utc)
    rows = []
    for s in servers:
        warranty_days = (s.warranty_expiry - now).days if s.warranty_expiry else None
        eos_days = (s.eos_date - now).days if s.eos_date else None
        eol_days = (s.eol_date - now).days if s.eol_date else None
        age_years = round((now - (s.installation_date or s.procurement_date)).days / 365.0, 1) if (s.installation_date or s.procurement_date) else None
        rows.append({
            "id": s.id, "hostname": s.hostname, "model": s.model, "vendor": s.vendor.value if s.vendor else None,
            "procurement_date": s.procurement_date.isoformat() if s.procurement_date else None,
            "installation_date": s.installation_date.isoformat() if s.installation_date else None,
            "warranty_expiry": s.warranty_expiry.isoformat() if s.warranty_expiry else None,
            "eol_date": s.eol_date.isoformat() if s.eol_date else None,
            "eos_date": s.eos_date.isoformat() if s.eos_date else None,
            "support_contract": s.support_contract,
            "age_years": age_years,
            "warranty_days_left": warranty_days, "warranty_status": _risk(warranty_days),
            "eos_days_left": eos_days, "eos_status": _risk(eos_days),
            "eol_days_left": eol_days,
        })
    return {
        "servers": rows,
        "summary": {
            "supported": sum(1 for r in rows if r["warranty_status"] == "supported"),
            "expiring_soon": sum(1 for r in rows if r["warranty_status"] == "expiring_soon"),
            "expired": sum(1 for r in rows if r["warranty_status"] == "expired"),
            "end_of_support": sum(1 for r in rows if r["eos_status"] == "expired"),
        },
    }


@router.post("/{server_id}")
async def update_lifecycle(server_id: str, payload: LifecycleUpdate, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(Server).where(Server.id == server_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Server not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    return {"status": "updated"}
