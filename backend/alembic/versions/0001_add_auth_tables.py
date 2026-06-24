"""Add RBAC auth tables: auth_teams, auth_users, refresh_tokens, audit_logs

Revision ID: 0001_add_auth_tables
Revises:
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_add_auth_tables"
down_revision = "af6adb496aaf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_teams",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(36)),
    )
    op.create_index("ix_auth_teams_name", "auth_teams", ["name"])

    op.create_table(
        "auth_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="user"),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("auth_teams.id", ondelete="SET NULL")),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("is_email_verified", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(36)),
    )
    op.create_index("ix_auth_users_email", "auth_users", ["email"])
    op.create_index("ix_auth_users_role", "auth_users", ["role"])
    op.create_index("ix_auth_users_team_id", "auth_users", ["team_id"])
    op.create_index("ix_auth_user_email_active", "auth_users", ["email", "is_active"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked", sa.Boolean, default=False, nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", sa.String(36)),
        sa.Column("username", sa.String(255)),
        sa.Column("user_email", sa.String(255)),
        sa.Column("team", sa.String(128)),
        sa.Column("role", sa.String(32)),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_id", sa.String(36)),
        sa.Column("old_value", sa.Text),
        sa.Column("new_value", sa.Text),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("session_id", sa.String(64)),
    )
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_log_user_time", "audit_logs", ["user_id", "timestamp"])
    op.create_index("ix_audit_log_action_time", "audit_logs", ["action", "timestamp"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("refresh_tokens")
    op.drop_table("auth_users")
    op.drop_table("auth_teams")
