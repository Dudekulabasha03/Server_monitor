"""
Seed default teams and super admin on first RBAC startup.
Safe to call on every startup — idempotent (checks before inserting).
"""
import uuid
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.auth import AuthTeam, AuthUser
from app.core.security import hash_password
from app.config import settings

log = structlog.get_logger(__name__)

DEFAULT_TEAMS = [
    ("Security Patch Team", "Security patch validation and deployment"),
    ("TSP Team", "Technical Support Platform team"),
    ("DPDK Team", "Data Plane Development Kit team"),
    ("Performance Team", "Performance benchmarking and optimization"),
    ("AI Team", "Artificial Intelligence and ML infrastructure"),
    ("Cloud Team", "Cloud infrastructure and virtualization"),
]


async def seed_rbac(db: AsyncSession) -> None:
    if not settings.RBAC_ENABLED:
        return

    # Seed teams
    for name, description in DEFAULT_TEAMS:
        exists = (await db.execute(select(AuthTeam).where(AuthTeam.name == name))).scalar_one_or_none()
        if not exists:
            team = AuthTeam(id=str(uuid.uuid4()), name=name, description=description)
            db.add(team)
            log.info("rbac_seed_team", name=name)

    await db.commit()

    # Seed super admin
    admin_email = settings.RBAC_SUPER_ADMIN_EMAIL
    exists = (await db.execute(select(AuthUser).where(AuthUser.email == admin_email))).scalar_one_or_none()
    if not exists:
        admin = AuthUser(
            id=str(uuid.uuid4()),
            email=admin_email,
            full_name=settings.RBAC_SUPER_ADMIN_NAME,
            password_hash=hash_password(settings.RBAC_SUPER_ADMIN_PASSWORD),
            role="super_admin",
            is_active=True,
            is_email_verified=True,
        )
        db.add(admin)
        await db.commit()
        log.info("rbac_seed_super_admin", email=admin_email)
    else:
        log.info("rbac_seed_skip_admin_exists", email=admin_email)
