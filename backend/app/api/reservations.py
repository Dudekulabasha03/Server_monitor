"""
Server reservation endpoints — full lifecycle management.
Users: reserve/release/extend their own. Admins: see all, force-release, oversight.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, Column, String, Boolean, DateTime, Text, ForeignKey

from app.database import get_db, Base
from app.models.server import Server
from app.core.rbac import get_current_user, require_admin_or_above
from app.models.auth import AuthUser

router = APIRouter(prefix="/reservations", tags=["reservations"])


class ServerReservation(Base):
    __tablename__ = "server_reservations"
    id             = Column(String(36), primary_key=True)
    server_id      = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    user_email     = Column(String(255), nullable=False)
    user_name      = Column(String(255))
    team           = Column(String(128))
    purpose        = Column(Text)
    benchmark_name = Column(String(255))
    reserved_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at     = Column(DateTime(timezone=True), nullable=False)
    released_at    = Column(DateTime(timezone=True))
    is_active      = Column(Boolean, default=True)
    notes          = Column(Text)
    result_url     = Column(Text)
    started_at     = Column(DateTime(timezone=True))
    completed_at   = Column(DateTime(timezone=True))
    status         = Column(String(20), default="active")  # active|completed|released|expired


class ReserveRequest(BaseModel):
    server_id:      str
    purpose:        str
    benchmark_name: Optional[str] = None
    duration_hours: int = 24
    notes:          Optional[str] = None


class ExtendRequest(BaseModel):
    extra_hours: int = 24


class UpdateReservationRequest(BaseModel):
    result_url:     Optional[str] = None
    notes:          Optional[str] = None
    status:         Optional[str] = None  # completed


def _fmt(r: ServerReservation, hostname: str = "") -> dict:
    now = datetime.now(timezone.utc)
    expires = r.expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    remaining_h = max(0, (expires - now).total_seconds() / 3600) if expires else 0
    return {
        "id": r.id, "server_id": r.server_id, "hostname": hostname,
        "user_email": r.user_email, "user_name": r.user_name, "team": r.team,
        "purpose": r.purpose, "benchmark_name": r.benchmark_name,
        "reserved_at": r.reserved_at.isoformat() if r.reserved_at else None,
        "expires_at": expires.isoformat() if expires else None,
        "released_at": r.released_at.isoformat() if r.released_at else None,
        "is_active": r.is_active, "remaining_hours": round(remaining_h, 1),
        "notes": r.notes, "result_url": r.result_url, "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


async def _expire_old(db: AsyncSession):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(ServerReservation).where(
            and_(ServerReservation.is_active == True,  # noqa: E712
                 ServerReservation.expires_at < now)
        )
    )
    for r in result.scalars().all():
        r.is_active = False
        r.status = "expired"
        r.released_at = now
    await db.flush()


async def _send_expiry_email(user_email: str, hostname: str, hours_left: float):
    """Fire-and-forget expiry warning email."""
    try:
        from app.config import settings
        import aiosmtplib
        from email.message import EmailMessage
        if not settings.SMTP_HOST or not settings.SMTP_USER:
            return
        msg = EmailMessage()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = user_email
        msg["Subject"] = f"[Helios] Reservation expiring: {hostname}"
        msg.set_content(
            f"Your reservation of {hostname} expires in {hours_left:.0f} hours.\n"
            f"Log in to extend: http://10.194.168.138:3200/user-home\n\nHelios Fleet Monitor"
        )
        await aiosmtplib.send(msg, hostname=settings.SMTP_HOST, port=settings.SMTP_PORT,
                              username=settings.SMTP_USER, password=settings.SMTP_PASSWORD,
                              start_tls=True)
    except Exception:
        pass


@router.get("")
async def list_reservations(
    active_only: bool = True,
    team: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    await _expire_old(db)
    q = select(ServerReservation)
    if active_only:
        q = q.where(ServerReservation.is_active == True)  # noqa: E712
    if current_user.role == "user":
        q = q.where(ServerReservation.user_email == current_user.email)
    elif team:
        q = q.where(ServerReservation.team == team)
    q = q.order_by(desc(ServerReservation.reserved_at))
    result = await db.execute(q)
    reservations = result.scalars().all()
    server_ids = list({r.server_id for r in reservations})
    hostname_map: dict = {}
    if server_ids:
        srvs = await db.execute(select(Server).where(Server.id.in_(server_ids)))
        hostname_map = {s.id: s.hostname for s in srvs.scalars().all()}
    return {
        "reservations": [_fmt(r, hostname_map.get(r.server_id, "")) for r in reservations],
        "total": len(reservations),
    }


@router.post("", status_code=201)
async def reserve_server(
    body: ReserveRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    await _expire_old(db)
    server = (await db.execute(select(Server).where(Server.id == body.server_id))).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    existing = (await db.execute(
        select(ServerReservation).where(
            and_(ServerReservation.server_id == body.server_id,
                 ServerReservation.is_active == True)  # noqa: E712
        )
    )).scalar_one_or_none()

    if existing and existing.user_email != current_user.email:
        raise HTTPException(status_code=409,
            detail=f"Reserved by {existing.user_email} until {existing.expires_at.strftime('%Y-%m-%d %H:%M UTC')}")

    duration = min(body.duration_hours, 168)
    now = datetime.now(timezone.utc)

    if existing and existing.user_email == current_user.email:
        existing.expires_at = now + timedelta(hours=duration)
        existing.purpose = body.purpose
        existing.benchmark_name = body.benchmark_name
        existing.notes = body.notes
        await db.flush()
        return {"message": "Reservation extended", "reservation": _fmt(existing, server.hostname)}

    reservation = ServerReservation(
        id=str(uuid.uuid4()), server_id=body.server_id,
        user_email=current_user.email, user_name=current_user.full_name,
        team=current_user.team.name if current_user.team else None,
        purpose=body.purpose, benchmark_name=body.benchmark_name,
        reserved_at=now, expires_at=now + timedelta(hours=duration),
        is_active=True, notes=body.notes, status="active",
    )
    db.add(reservation)
    await db.flush()
    return {"message": "Server reserved", "reservation": _fmt(reservation, server.hostname)}


@router.delete("/{reservation_id}")
async def release_server(
    reservation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    r = (await db.execute(select(ServerReservation).where(ServerReservation.id == reservation_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if current_user.role == "user" and r.user_email != current_user.email:
        raise HTTPException(status_code=403, detail="Cannot release another user's reservation")
    r.is_active = False
    r.released_at = datetime.now(timezone.utc)
    r.status = "released"
    await db.flush()
    return {"message": "Reservation released"}


@router.patch("/{reservation_id}/extend")
async def extend_reservation(
    reservation_id: str,
    body: ExtendRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    r = (await db.execute(
        select(ServerReservation).where(
            and_(ServerReservation.id == reservation_id, ServerReservation.is_active == True)  # noqa: E712
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Active reservation not found")
    if current_user.role == "user" and r.user_email != current_user.email:
        raise HTTPException(status_code=403, detail="Cannot extend another user's reservation")
    extra = min(body.extra_hours, 168)
    now = datetime.now(timezone.utc)
    current_expiry = r.expires_at if r.expires_at.tzinfo else r.expires_at.replace(tzinfo=timezone.utc)
    r.expires_at = max(current_expiry, now) + timedelta(hours=extra)
    await db.flush()
    server = (await db.execute(select(Server).where(Server.id == r.server_id))).scalar_one_or_none()
    return {"message": f"Extended by {extra}h", "reservation": _fmt(r, server.hostname if server else "")}


@router.patch("/{reservation_id}")
async def update_reservation(
    reservation_id: str,
    body: UpdateReservationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Update result URL, notes, or mark as completed."""
    r = (await db.execute(select(ServerReservation).where(ServerReservation.id == reservation_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if current_user.role == "user" and r.user_email != current_user.email:
        raise HTTPException(status_code=403, detail="Cannot update another user's reservation")
    if body.result_url is not None:
        r.result_url = body.result_url
    if body.notes is not None:
        r.notes = body.notes
    if body.status == "completed":
        r.status = "completed"
        r.completed_at = datetime.now(timezone.utc)
        r.is_active = False
        r.released_at = datetime.now(timezone.utc)
    await db.flush()
    server = (await db.execute(select(Server).where(Server.id == r.server_id))).scalar_one_or_none()
    return {"message": "Updated", "reservation": _fmt(r, server.hostname if server else "")}


@router.get("/server/{server_id}")
async def server_reservation_status(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    await _expire_old(db)
    server = (await db.execute(select(Server).where(Server.id == server_id))).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    r = (await db.execute(
        select(ServerReservation).where(
            and_(ServerReservation.server_id == server_id, ServerReservation.is_active == True)  # noqa: E712
        )
    )).scalar_one_or_none()
    if not r:
        return {"reserved": False, "hostname": server.hostname}
    return {"reserved": True, "hostname": server.hostname, "reservation": _fmt(r, server.hostname)}


@router.post("/check-expiry")
async def check_expiry_warnings(
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_admin_or_above),
):
    """Send expiry warnings for reservations expiring in <2h. Called by Celery Beat."""
    now = datetime.now(timezone.utc)
    warning_window = now + timedelta(hours=2)
    result = await db.execute(
        select(ServerReservation).where(
            and_(ServerReservation.is_active == True,  # noqa: E712
                 ServerReservation.expires_at <= warning_window,
                 ServerReservation.expires_at > now)
        )
    )
    warned = 0
    for r in result.scalars().all():
        server = (await db.execute(select(Server).where(Server.id == r.server_id))).scalar_one_or_none()
        if server:
            hours_left = (r.expires_at.replace(tzinfo=timezone.utc) - now).total_seconds() / 3600
            await _send_expiry_email(r.user_email, server.hostname, hours_left)
            warned += 1
    return {"warned": warned}
