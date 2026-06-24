"""
Auth models: application users, teams, roles, audit logs, refresh tokens.
These are separate from UserSession (OS-level SSH session tracking on servers).
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text, Index
)
from sqlalchemy.orm import relationship
from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AuthTeam(Base):
    __tablename__ = "auth_teams"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(128), nullable=False, unique=True, index=True)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(36))  # user id who created it

    members = relationship("AuthUser", back_populates="team", foreign_keys="AuthUser.team_id")


class AuthUser(Base):
    """Application user accounts (not OS/SSH sessions on monitored servers)."""
    __tablename__ = "auth_users"

    id = Column(String(36), primary_key=True, default=_uuid)
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)

    # role: super_admin | admin | user
    role = Column(String(32), nullable=False, default="user", index=True)

    team_id = Column(String(36), ForeignKey("auth_teams.id", ondelete="SET NULL"), nullable=True, index=True)

    is_active = Column(Boolean, default=True, index=True)
    is_email_verified = Column(Boolean, default=False)

    # approval_status: pending | approved | rejected
    approval_status = Column(String(20), default="approved")
    approved_by     = Column(String(36))
    approval_note   = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime(timezone=True))
    created_by = Column(String(36))  # super_admin user id

    team = relationship("AuthTeam", back_populates="members", foreign_keys=[team_id])
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_auth_user_email_active", "email", "is_active"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    revoked = Column(Boolean, default=False)

    user = relationship("AuthUser", back_populates="refresh_tokens")


class AuditLog(Base):
    """Immutable audit trail — never updated, only inserted."""
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    user_id = Column(String(36), index=True)
    username = Column(String(255))
    user_email = Column(String(255))
    team = Column(String(128))
    role = Column(String(32))

    action = Column(String(128), nullable=False, index=True)
    resource_type = Column(String(64))
    resource_id = Column(String(36))
    old_value = Column(Text)
    new_value = Column(Text)

    ip_address = Column(String(45))
    user_agent = Column(String(512))
    session_id = Column(String(64))

    __table_args__ = (
        Index("ix_audit_log_user_time", "user_id", "timestamp"),
        Index("ix_audit_log_action_time", "action", "timestamp"),
    )
