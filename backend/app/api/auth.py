"""
Authentication endpoints: register, login, logout, me, refresh.
All users must have @amd.com email addresses.

IMPORTANT: Never call await db.commit() inside handlers.
get_db() commits once when the context exits — mid-handler commits
cause MissingGreenlet errors in SQLAlchemy async. Use await db.flush()
to persist rows and get generated IDs without committing.
"""
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.auth import AuthUser, AuthTeam, RefreshToken
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, hash_refresh_token,
)
from app.core.rbac import get_current_user
from app.core.audit import log_action
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ─────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    team_id: str
    password: str
    confirm_password: str

    @field_validator("email")
    @classmethod
    def amd_email_only(cls, v: str) -> str:
        if not v.lower().endswith("@amd.com"):
            raise ValueError("Only AMD email addresses (@amd.com) are allowed")
        return v.lower()

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Full name must be at least 2 characters")
        return v.strip()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    def validate_passwords_match(self) -> None:
        if self.password != self.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.lower()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def _user_payload(user: AuthUser) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "team_id": user.team_id,
        "team_name": user.team.name if user.team else None,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


async def _issue_tokens(user: AuthUser, db: AsyncSession) -> TokenResponse:
    """Add refresh token + update last_login. Uses flush — get_db commits."""
    access = create_access_token({"sub": user.id, "role": user.role, "email": user.email})
    raw_refresh, hashed_refresh = create_refresh_token()

    db.add(RefreshToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=hashed_refresh,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()  # persist without committing — get_db handles the commit

    return TokenResponse(
        access_token=access,
        refresh_token=raw_refresh,
        user=_user_payload(user),
    )


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    body.validate_passwords_match()

    existing = (await db.execute(
        select(AuthUser).where(AuthUser.email == body.email)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    team = (await db.execute(
        select(AuthTeam).where(AuthTeam.id == body.team_id, AuthTeam.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=400, detail="Invalid or inactive team")

    new_user = AuthUser(
        id=str(uuid.uuid4()),
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role="user",
        team_id=body.team_id,
        is_active=False,           # disabled until admin approves
        approval_status="pending", # awaiting admin approval
    )
    db.add(new_user)
    await db.flush()

    await log_action(None, "user_registered", user=new_user, resource_type="auth_user",
                     resource_id=new_user.id, new_value={"email": new_user.email, "team": team.name},
                     request=request)

    return {
        "message": "Registration submitted. An administrator will review and activate your account shortly.",
        "user_id": new_user.id,
        "status": "pending",
    }


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AuthUser).where(AuthUser.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        status_msg = {
            "pending": "Your account is pending approval. An administrator will activate it shortly.",
            "rejected": "Your account registration was not approved. Contact your administrator.",
        }.get(getattr(user, "approval_status", ""), "Account is disabled. Contact your administrator.")
        raise HTTPException(status_code=403, detail=status_msg)

    if user.team_id:
        user.team = (await db.execute(
            select(AuthTeam).where(AuthTeam.id == user.team_id)
        )).scalar_one_or_none()

    tokens = await _issue_tokens(user, db)

    await log_action(None, "user_login", user=user, resource_type="auth_user",
                     resource_id=user.id, new_value={"role": user.role}, request=request)

    return tokens


@router.post("/logout")
async def logout(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    hashed = hash_refresh_token(body.refresh_token)
    token_rec = (await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hashed,
            RefreshToken.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if token_rec:
        token_rec.revoked = True
        await db.flush()
    return {"message": "Logged out successfully"}


@router.get("/me")
async def me(current_user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.team_id and not current_user.team:
        current_user.team = (await db.execute(
            select(AuthTeam).where(AuthTeam.id == current_user.team_id)
        )).scalar_one_or_none()
    return _user_payload(current_user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    hashed = hash_refresh_token(body.refresh_token)
    token_rec = (await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hashed,
            RefreshToken.revoked == False,  # noqa: E712
        )
    )).scalar_one_or_none()

    if not token_rec:
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")
    if token_rec.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = (await db.execute(
        select(AuthUser).where(AuthUser.id == token_rec.user_id)
    )).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or deactivated")

    token_rec.revoked = True
    if user.team_id:
        user.team = (await db.execute(
            select(AuthTeam).where(AuthTeam.id == user.team_id)
        )).scalar_one_or_none()

    return await _issue_tokens(user, db)


@router.get("/teams")
async def list_teams(db: AsyncSession = Depends(get_db)):
    """Public — populates registration team dropdown."""
    result = await db.execute(
        select(AuthTeam).where(AuthTeam.is_active == True).order_by(AuthTeam.name)  # noqa: E712
    )
    return [{"id": t.id, "name": t.name, "description": t.description} for t in result.scalars().all()]


@router.get("/my-team-context")
async def my_team_context(
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current user's role + team name so the frontend can scope server views."""
    team_name = None
    if current_user.team_id:
        team = (await db.execute(
            select(AuthTeam).where(AuthTeam.id == current_user.team_id)
        )).scalar_one_or_none()
        team_name = team.name if team else None

    # Map auth team name -> fleet server team name
    # Auth teams: "Security Patch Team", "TSP Team", "DPDK Team", "Performance Team", "AI Team", "Cloud Team"
    # Fleet DB teams: "Security Patch Team", "TSP"
    TEAM_MAP = {
        "Security Patch Team": "Security Patch Team",
        "TSP Team":            "TSP",
        "DPDK Team":           "DPDK",
        "Performance Team":    "Performance",
        "AI Team":             "AI",
        "Cloud Team":          "Cloud",
    }
    fleet_team = TEAM_MAP.get(team_name, team_name) if team_name else None

    return {
        "user_id":    current_user.id,
        "email":      current_user.email,
        "role":       current_user.role,
        "team_name":  team_name,
        "fleet_team": fleet_team,  # matches servers.team in fleet DB
        "can_see_all": current_user.role in ("super_admin", "admin"),
    }
