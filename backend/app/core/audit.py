"""Audit logging helper — writes immutable records to audit_logs table."""
import json
from typing import Optional, Any
from fastapi import Request

from app.models.auth import AuditLog, AuthUser
from app.database import AsyncSessionLocal


async def log_action(
    db,  # kept for backward-compat signature but we open our own session
    action: str,
    user: Optional[AuthUser] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    old_value: Optional[Any] = None,
    new_value: Optional[Any] = None,
    request: Optional[Request] = None,
) -> None:
    """Write an immutable audit record in its own session so it never conflicts
    with the caller's transaction state. Never raises."""
    try:
        ip = None
        ua = None
        if request:
            forwarded = request.headers.get("X-Forwarded-For")
            ip = forwarded.split(",")[0].strip() if forwarded else (
                request.client.host if request.client else None
            )
            ua = request.headers.get("User-Agent", "")[:512]

        record = AuditLog(
            user_id=user.id if user else None,
            username=user.full_name if user else None,
            user_email=user.email if user else None,
            team=user.team.name if (user and user.team) else None,
            role=user.role if user else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_value=json.dumps(old_value) if old_value is not None else None,
            new_value=json.dumps(new_value) if new_value is not None else None,
            ip_address=ip,
            user_agent=ua,
        )
        async with AsyncSessionLocal() as session:
            session.add(record)
            await session.commit()
    except Exception:
        pass  # audit failure must never break the primary request
