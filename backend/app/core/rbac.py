"""FastAPI RBAC dependencies — inject into route handlers."""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.models.auth import AuthUser
from app.core.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

ROLES_HIERARCHY = {"super_admin": 3, "admin": 2, "user": 1}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthUser:
    """Validate Bearer token and return the AuthUser.

    Uses its own independent session so it never interferes with the
    handler's get_db() session lifecycle (avoids MissingGreenlet errors).
    """
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuthUser)
            .options(selectinload(AuthUser.team))  # eagerly load team so it survives after session closes
            .where(AuthUser.id == user_id)
        )
        user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or deactivated")

    return user


def require_role(*roles: str):
    """Dependency factory: require the current user to have one of the given roles."""
    async def _check(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {' or '.join(roles)}",
            )
        return current_user
    return _check


def require_min_role(min_role: str):
    """Dependency factory: require role level >= min_role (user < admin < super_admin)."""
    min_level = ROLES_HIERARCHY.get(min_role, 0)

    async def _check(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
        user_level = ROLES_HIERARCHY.get(current_user.role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires at least {min_role} role",
            )
        return current_user
    return _check


require_super_admin = require_role("super_admin")
require_admin_or_above = require_min_role("admin")
require_any_auth = get_current_user
