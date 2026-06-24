"""
Admin & Super Admin management endpoints.
- /admin/dashboard       — stats
- /admin/users           — user CRUD (super_admin full control, admin limited)
- /admin/teams           — team CRUD (super_admin only for create/delete)
- /admin/audit-logs      — immutable audit trail (super_admin only)
- /admin/user-activity   — user action summaries
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, text

from app.database import get_db
from app.models.auth import AuthUser, AuthTeam, AuditLog
from app.models.server import Server
from app.core.rbac import require_admin_or_above, require_super_admin, get_current_user
from app.core.security import hash_password
from app.core.audit import log_action

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: str = "user"
    team_id: Optional[str] = None

    @field_validator("email")
    @classmethod
    def amd_only(cls, v: str) -> str:
        if not v.lower().endswith("@amd.com"):
            raise ValueError("Only AMD email addresses allowed")
        return v.lower()

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ("super_admin", "admin", "user"):
            raise ValueError("Role must be super_admin, admin, or user")
        return v


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    team_id: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in ("super_admin", "admin", "user"):
            raise ValueError("Invalid role")
        return v


class CreateTeamRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateTeamRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


# ── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def admin_dashboard(
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_admin_or_above),
):
    total = (await db.execute(select(func.count()).select_from(AuthUser))).scalar()
    active = (await db.execute(select(func.count()).select_from(AuthUser).where(AuthUser.is_active == True))).scalar()  # noqa: E712
    disabled = (await db.execute(select(func.count()).select_from(AuthUser).where(AuthUser.is_active == False))).scalar()  # noqa: E712
    teams_count = (await db.execute(select(func.count()).select_from(AuthTeam).where(AuthTeam.is_active == True))).scalar()  # noqa: E712

    # Team distribution
    teams_result = await db.execute(
        select(AuthTeam.name, func.count(AuthUser.id).label("count"))
        .join(AuthUser, AuthUser.team_id == AuthTeam.id, isouter=True)
        .where(AuthTeam.is_active == True)  # noqa: E712
        .group_by(AuthTeam.name)
        .order_by(desc("count"))
    )
    team_dist = [{"team": row.name, "count": row.count} for row in teams_result]

    # Role distribution
    roles_result = await db.execute(
        select(AuthUser.role, func.count(AuthUser.id).label("count"))
        .group_by(AuthUser.role)
    )
    role_dist = [{"role": row.role, "count": row.count} for row in roles_result]

    # Recent audit events
    recent_result = await db.execute(
        select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(10)
    )
    recent_logs = [
        {"id": l.id, "action": l.action, "username": l.username, "timestamp": l.timestamp.isoformat(), "resource_type": l.resource_type}
        for l in recent_result.scalars().all()
    ]

    return {
        "users": {"total": total, "active": active, "disabled": disabled},
        "teams_count": teams_count,
        "team_distribution": team_dist,
        "role_distribution": role_dist,
        "recent_activity": recent_logs,
    }


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    role: Optional[str] = None,
    team_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_admin_or_above),
):
    q = select(AuthUser)
    if role:
        q = q.where(AuthUser.role == role)
    if team_id:
        q = q.where(AuthUser.team_id == team_id)
    if is_active is not None:
        q = q.where(AuthUser.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        q = q.where(AuthUser.email.ilike(pattern) | AuthUser.full_name.ilike(pattern))

    # Admins cannot see super admins
    if current_user.role == "admin":
        q = q.where(AuthUser.role != "super_admin")

    q = q.order_by(desc(AuthUser.created_at)).offset(offset).limit(limit)
    result = await db.execute(q)
    users = result.scalars().all()

    # Fetch teams
    team_ids = list({u.team_id for u in users if u.team_id})
    teams_map: dict = {}
    if team_ids:
        tr = await db.execute(select(AuthTeam).where(AuthTeam.id.in_(team_ids)))
        teams_map = {t.id: t.name for t in tr.scalars().all()}

    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "team_id": u.team_id,
                "team_name": teams_map.get(u.team_id),
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            }
            for u in users
        ],
        "total": len(users),
        "offset": offset,
    }


@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_super_admin),
):
    existing = (await db.execute(select(AuthUser).where(AuthUser.email == body.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already exists")

    user = AuthUser(
        id=str(uuid.uuid4()),
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=body.role,
        team_id=body.team_id,
        is_active=True,
        created_by=current_user.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await log_action(db, "admin_create_user", user=current_user, resource_type="auth_user",
                     resource_id=user.id, new_value={"email": user.email, "role": user.role}, request=request)
    return {"message": "User created", "user_id": user.id}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_admin_or_above),
):
    target = (await db.execute(select(AuthUser).where(AuthUser.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Admins cannot modify super admins
    if current_user.role == "admin" and target.role == "super_admin":
        raise HTTPException(status_code=403, detail="Admins cannot modify super admins")

    # Only super_admin can promote to super_admin
    if body.role == "super_admin" and current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admins can grant super_admin role")

    old = {"role": target.role, "is_active": target.is_active, "team_id": target.team_id}
    if body.full_name is not None:
        target.full_name = body.full_name
    if body.role is not None:
        target.role = body.role
    if body.team_id is not None:
        target.team_id = body.team_id
    if body.is_active is not None:
        target.is_active = body.is_active

    target.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await log_action(db, "admin_update_user", user=current_user, resource_type="auth_user",
                     resource_id=user_id, old_value=old,
                     new_value={"role": target.role, "is_active": target.is_active}, request=request)
    return {"message": "User updated"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_super_admin),
):
    target = (await db.execute(select(AuthUser).where(AuthUser.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    # Soft delete
    target.is_active = False
    target.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await log_action(db, "admin_disable_user", user=current_user, resource_type="auth_user",
                     resource_id=user_id, old_value={"email": target.email}, request=request)
    return {"message": "User disabled"}


# ── Teams ─────────────────────────────────────────────────────────────────────

@router.get("/teams")
async def list_teams(
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_admin_or_above),
):
    result = await db.execute(select(AuthTeam).order_by(AuthTeam.name))
    teams = result.scalars().all()
    return [{"id": t.id, "name": t.name, "description": t.description, "is_active": t.is_active} for t in teams]


@router.post("/teams", status_code=201)
async def create_team(
    body: CreateTeamRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_super_admin),
):
    exists = (await db.execute(select(AuthTeam).where(AuthTeam.name == body.name))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="Team name already exists")

    team = AuthTeam(id=str(uuid.uuid4()), name=body.name, description=body.description, created_by=current_user.id)
    db.add(team)
    await db.flush()
    await log_action(db, "admin_create_team", user=current_user, resource_type="auth_team",
                     resource_id=team.id, new_value={"name": team.name}, request=request)
    return {"message": "Team created", "team_id": team.id}


@router.patch("/teams/{team_id}")
async def update_team(
    team_id: str,
    body: UpdateTeamRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_admin_or_above),
):
    team = (await db.execute(select(AuthTeam).where(AuthTeam.id == team_id))).scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    old = {"name": team.name, "is_active": team.is_active}
    if body.name is not None:
        team.name = body.name
    if body.description is not None:
        team.description = body.description
    if body.is_active is not None:
        team.is_active = body.is_active

    await db.flush()
    await log_action(db, "admin_update_team", user=current_user, resource_type="auth_team",
                     resource_id=team_id, old_value=old, new_value={"name": team.name}, request=request)
    return {"message": "Team updated"}


@router.delete("/teams/{team_id}")
async def delete_team(
    team_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_super_admin),
):
    team = (await db.execute(select(AuthTeam).where(AuthTeam.id == team_id))).scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    team.is_active = False
    await db.flush()
    await log_action(db, "admin_disable_team", user=current_user, resource_type="auth_team",
                     resource_id=team_id, old_value={"name": team.name}, request=request)
    return {"message": "Team deactivated"}


# ── Audit Logs ────────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def audit_logs(
    action: Optional[str] = None,
    user_email: Optional[str] = None,
    resource_type: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_super_admin),
):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action.ilike(f"%{action}%"))
    if user_email:
        q = q.where(AuditLog.user_email.ilike(f"%{user_email}%"))
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)

    q = q.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit)
    result = await db.execute(q)
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": l.id,
                "timestamp": l.timestamp.isoformat(),
                "username": l.username,
                "user_email": l.user_email,
                "team": l.team,
                "role": l.role,
                "action": l.action,
                "resource_type": l.resource_type,
                "resource_id": l.resource_id,
                "old_value": l.old_value,
                "new_value": l.new_value,
                "ip_address": l.ip_address,
            }
            for l in logs
        ],
        "total": len(logs),
        "offset": offset,
    }


@router.get("/user-activity")
async def user_activity(
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_admin_or_above),
):
    result = await db.execute(
        select(
            AuditLog.user_email, AuditLog.username, AuditLog.role, AuditLog.team,
            func.count(AuditLog.id).label("action_count"),
            func.max(AuditLog.timestamp).label("last_action"),
        )
        .where(AuditLog.user_email.isnot(None))
        .group_by(AuditLog.user_email, AuditLog.username, AuditLog.role, AuditLog.team)
        .order_by(desc("last_action")).limit(limit)
    )
    return {
        "activity": [
            {"user_email": row.user_email, "username": row.username, "role": row.role,
             "team": row.team, "action_count": row.action_count,
             "last_action": row.last_action.isoformat() if row.last_action else None}
            for row in result
        ]
    }


# ── Approval Queue ────────────────────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    action:   str        # approve | reject
    role:     str = "user"
    team_id:  Optional[str] = None
    note:     Optional[str] = None


@router.get("/pending-users")
async def pending_users(
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_admin_or_above),
):
    """Users who registered but haven't been approved yet."""
    result = await db.execute(
        select(AuthUser).where(AuthUser.approval_status == "pending")
        .order_by(AuthUser.created_at.desc())
    )
    users = result.scalars().all()
    team_ids = list({u.team_id for u in users if u.team_id})
    teams_map: dict = {}
    if team_ids:
        tr = await db.execute(select(AuthTeam).where(AuthTeam.id.in_(team_ids)))
        teams_map = {t.id: t.name for t in tr.scalars().all()}
    return {
        "pending": [
            {"id": u.id, "email": u.email, "full_name": u.full_name,
             "team_id": u.team_id, "team_name": teams_map.get(u.team_id),
             "created_at": u.created_at.isoformat() if u.created_at else None}
            for u in users
        ],
        "total": len(users),
    }


@router.post("/users/{user_id}/approve")
async def approve_user(
    user_id: str,
    body: ApprovalRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_admin_or_above),
):
    target = (await db.execute(select(AuthUser).where(AuthUser.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if body.action == "approve":
        target.approval_status = "approved"
        target.is_active = True
        target.role = body.role
        if body.team_id:
            target.team_id = body.team_id
        target.approved_by = current_user.id
        msg = "User approved"
    elif body.action == "reject":
        target.approval_status = "rejected"
        target.is_active = False
        target.approved_by = current_user.id
        msg = "User rejected"
    else:
        raise HTTPException(status_code=400, detail="action must be approve or reject")

    target.approval_note = body.note
    target.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await log_action(None, f"admin_{body.action}_user", user=current_user,
                     resource_type="auth_user", resource_id=user_id,
                     new_value={"action": body.action, "role": body.role}, request=request)

    # Send approval email (best-effort)
    try:
        from app.config import settings
        import aiosmtplib
        from email.message import EmailMessage
        if settings.SMTP_HOST and settings.SMTP_USER:
            em = EmailMessage()
            em["From"] = settings.SMTP_FROM
            em["To"] = target.email
            em["Subject"] = f"[Helios] Your account has been {body.action}d"
            body_text = (
                f"Hi {target.full_name},\n\n"
                f"Your Helios account has been {body.action}d.\n"
                + (f"Note: {body.note}\n" if body.note else "")
                + f"\nLog in: http://10.194.168.138:3200/login\n\nHelios Fleet Monitor"
            )
            em.set_content(body_text)
            await aiosmtplib.send(em, hostname=settings.SMTP_HOST, port=settings.SMTP_PORT,
                                  username=settings.SMTP_USER, password=settings.SMTP_PASSWORD,
                                  start_tls=True)
    except Exception:
        pass

    return {"message": msg}


# ── Server Team Assignment ────────────────────────────────────────────────────

class TeamAssignRequest(BaseModel):
    team: str


@router.patch("/servers/{server_id}/team")
async def assign_server_team(
    server_id: str,
    body: TeamAssignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_admin_or_above),
):
    """Reassign a server to a different team."""
    server = (await db.execute(select(Server).where(Server.id == server_id))).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    old_team = server.team
    server.team = body.team
    await db.flush()
    await log_action(None, "admin_assign_server_team", user=current_user,
                     resource_type="server", resource_id=server_id,
                     old_value={"team": old_team}, new_value={"team": body.team}, request=request)
    return {"message": f"Server {server.hostname} assigned to {body.team}"}


@router.get("/servers")
async def list_servers_admin(
    team: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(200, le=500),
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_admin_or_above),
):
    """Server list with team info for admin reassignment UI."""
    q = select(Server)
    if team:
        q = q.where(Server.team == team)
    if status:
        q = q.where(Server.status == status)
    q = q.order_by(Server.team, Server.hostname).limit(limit)
    result = await db.execute(q)
    servers = result.scalars().all()
    return {
        "servers": [
            {"id": s.id, "hostname": s.hostname, "team": s.team,
             "family": s.family, "datacenter": s.datacenter,
             "status": s.status, "health_score": s.health_score}
            for s in servers
        ],
        "total": len(servers),
    }


# ── Reservation Oversight ─────────────────────────────────────────────────────

@router.get("/reservations")
async def admin_reservations(
    active_only: bool = True,
    team: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_admin_or_above),
):
    """All reservations across all teams for admin oversight."""
    from app.api.reservations import ServerReservation
    q = select(ServerReservation)
    if active_only:
        q = q.where(ServerReservation.is_active == True)  # noqa: E712
    if team:
        q = q.where(ServerReservation.team == team)
    q = q.order_by(desc(ServerReservation.reserved_at)).limit(limit)
    result = await db.execute(q)
    reservations = result.scalars().all()
    server_ids = list({r.server_id for r in reservations})
    hostname_map: dict = {}
    if server_ids:
        srvs = await db.execute(select(Server).where(Server.id.in_(server_ids)))
        hostname_map = {s.id: s.hostname for s in srvs.scalars().all()}
    now = datetime.now(timezone.utc)
    return {
        "reservations": [
            {
                "id": r.id, "server_id": r.server_id,
                "hostname": hostname_map.get(r.server_id, ""),
                "user_email": r.user_email, "user_name": r.user_name,
                "team": r.team, "purpose": r.purpose, "benchmark_name": r.benchmark_name,
                "reserved_at": r.reserved_at.isoformat() if r.reserved_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "remaining_hours": round(max(0, (r.expires_at.replace(tzinfo=timezone.utc) - now).total_seconds() / 3600), 1) if r.expires_at else 0,
                "is_active": r.is_active, "status": r.status,
                "result_url": r.result_url, "notes": r.notes,
            }
            for r in reservations
        ],
        "total": len(reservations),
    }


@router.delete("/reservations/{reservation_id}")
async def admin_force_release(
    reservation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(require_admin_or_above),
):
    """Admin force-release any reservation."""
    from app.api.reservations import ServerReservation
    r = (await db.execute(select(ServerReservation).where(ServerReservation.id == reservation_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    r.is_active = False
    r.released_at = datetime.now(timezone.utc)
    r.status = "released"
    await db.flush()
    await log_action(None, "admin_force_release", user=current_user,
                     resource_type="reservation", resource_id=reservation_id,
                     old_value={"user_email": r.user_email}, request=request)
    return {"message": "Reservation force-released"}


# ── Usage Report ─────────────────────────────────────────────────────────────

@router.get("/usage-report")
async def usage_report(
    team: Optional[str] = None,
    days: int = Query(7, le=30),
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(require_admin_or_above),
):
    """Per-team server usage summary for the last N days."""
    from app.api.reservations import ServerReservation
    cutoff = f"NOW() - INTERVAL '{days} days'"

    # Reservation stats per team
    res_result = await db.execute(text(
        f"SELECT team, COUNT(*) as total_reservations, "
        f"SUM(EXTRACT(EPOCH FROM (COALESCE(released_at, expires_at) - reserved_at))/3600) as total_hours, "
        f"COUNT(DISTINCT user_email) as unique_users, "
        f"COUNT(DISTINCT server_id) as unique_servers "
        f"FROM server_reservations "
        f"WHERE reserved_at > {cutoff} "
        + (f"AND team = :team " if team else "")
        + "GROUP BY team ORDER BY total_reservations DESC"
    ), {"team": team} if team else {})

    rows = []
    for row in res_result:
        rows.append({
            "team": row[0], "total_reservations": int(row[1] or 0),
            "total_hours": round(float(row[2] or 0), 1),
            "unique_users": int(row[3] or 0), "unique_servers": int(row[4] or 0),
        })

    # Top benchmarks
    bench_result = await db.execute(text(
        f"SELECT benchmark_name, COUNT(*) as runs, team "
        f"FROM server_reservations "
        f"WHERE benchmark_name IS NOT NULL AND reserved_at > {cutoff} "
        + (f"AND team = :team " if team else "")
        + "GROUP BY benchmark_name, team ORDER BY runs DESC LIMIT 10"
    ), {"team": team} if team else {})

    benchmarks = [{"name": r[0], "runs": int(r[1]), "team": r[2]} for r in bench_result]

    return {
        "period_days": days,
        "team_usage": rows,
        "top_benchmarks": benchmarks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
