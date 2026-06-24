from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class UserSession(Base):
    """Tracks user login sessions on servers."""
    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)

    username = Column(String(128), nullable=False, index=True)
    full_name = Column(String(255))
    email = Column(String(255))
    team = Column(String(128))
    project = Column(String(128))

    session_type = Column(String(32))  # ssh | rdp | console | vnc
    source_ip = Column(String(45))
    terminal = Column(String(64))

    login_at = Column(DateTime(timezone=True), nullable=False, index=True)
    logout_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    duration_seconds = Column(Integer)

    # Resource consumption during session
    cpu_avg_pct = Column(Float)
    memory_avg_pct = Column(Float)
    disk_read_gb = Column(Float)
    disk_write_gb = Column(Float)
    net_rx_gb = Column(Float)
    net_tx_gb = Column(Float)

    server = relationship("Server", back_populates="user_sessions")

    __table_args__ = (
        Index("ix_user_session_server_active", "server_id", "is_active"),
        Index("ix_user_session_user_time", "username", "login_at"),
    )


class UserResourceUsage(Base):
    """Aggregated daily resource usage per user per server."""
    __tablename__ = "user_resource_usage"

    id = Column(String(36), primary_key=True)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    username = Column(String(128), nullable=False, index=True)
    date = Column(DateTime(timezone=True), nullable=False, index=True)

    team = Column(String(128))
    project = Column(String(128))

    session_count = Column(Integer, default=0)
    total_session_seconds = Column(Integer, default=0)
    cpu_core_hours = Column(Float, default=0)
    memory_gb_hours = Column(Float, default=0)
    disk_io_gb = Column(Float, default=0)
    net_io_gb = Column(Float, default=0)

    top_processes = Column(JSON)  # [{"name": "python", "cpu_pct": 45.2, "mem_gb": 12.1}]

    __table_args__ = (
        Index("ix_user_usage_server_date", "server_id", "date"),
        Index("ix_user_usage_team_date", "team", "date"),
    )
