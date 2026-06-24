from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Enum, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertCategory(str, enum.Enum):
    HARDWARE = "hardware"
    THERMAL = "thermal"
    POWER = "power"
    STORAGE = "storage"
    NETWORK = "network"
    UTILIZATION = "utilization"
    AVAILABILITY = "availability"
    FIRMWARE = "firmware"
    SECURITY = "security"
    PREDICTION = "prediction"


class AlertState(str, enum.Enum):
    FIRING = "firing"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)

    severity = Column(Enum(AlertSeverity), nullable=False, index=True)
    category = Column(Enum(AlertCategory), nullable=False, index=True)
    state = Column(Enum(AlertState), default=AlertState.FIRING, index=True)

    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(JSON)

    # Metric that triggered
    metric_name = Column(String(128))
    metric_value = Column(Float)
    threshold_value = Column(Float)

    # Lifecycle
    fired_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(String(128))
    resolved_at = Column(DateTime(timezone=True))
    suppressed_until = Column(DateTime(timezone=True))

    # Notification tracking
    notified_email = Column(Boolean, default=False)
    notified_teams = Column(Boolean, default=False)
    notified_slack = Column(Boolean, default=False)
    notified_at = Column(DateTime(timezone=True))
    notification_error = Column(Text)

    # Auto-remediation
    runbook_url = Column(String(512))
    auto_remediated = Column(Boolean, default=False)
    remediation_log = Column(Text)

    # ITSM
    ticket_id = Column(String(128))
    ticket_url = Column(String(512))

    server = relationship("Server", back_populates="alerts")

    __table_args__ = (
        Index("ix_alert_server_state", "server_id", "state"),
        Index("ix_alert_severity_state", "severity", "state"),
        Index("ix_alert_fired_at", "fired_at"),
    )


class AlertRule(Base):
    """Configurable alert rules."""
    __tablename__ = "alert_rules"

    id = Column(String(36), primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    description = Column(Text)
    enabled = Column(Boolean, default=True)

    category = Column(Enum(AlertCategory), nullable=False)
    severity = Column(Enum(AlertSeverity), nullable=False)

    # Rule condition (simple DSL stored as JSON)
    # {"metric": "cpu_temp_max", "operator": ">", "threshold": 85.0, "duration_seconds": 300}
    condition = Column(JSON, nullable=False)

    # Scope
    applies_to_tags = Column(JSON)        # ["gpu", "production"] - null = all servers
    applies_to_vendors = Column(JSON)     # ["dell", "hpe"] - null = all
    applies_to_datacenters = Column(JSON)

    # Suppression
    suppress_during = Column(JSON)        # maintenance windows

    # Notification targets
    notify_email = Column(JSON)           # list of email addresses
    notify_teams = Column(Boolean, default=True)
    notify_slack = Column(Boolean, default=True)
    notify_webhook_url = Column(String(512))

    # Timing
    cooldown_minutes = Column(Integer, default=30)  # Don't re-fire for N minutes
    auto_resolve_minutes = Column(Integer)           # Auto-resolve after N minutes

    runbook_url = Column(String(512))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
