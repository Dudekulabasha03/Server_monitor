from sqlalchemy import Column, String, Float, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class HealthScore(Base):
    """Historical health score records for trend analysis."""
    __tablename__ = "health_scores"

    id = Column(String(36), primary_key=True)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    scored_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Overall
    total_score = Column(Float, nullable=False)          # 0-100
    status = Column(String(32), nullable=False)           # healthy | warning | at_risk | critical

    # Component scores (each 0-100)
    hardware_score = Column(Float)
    thermal_score = Column(Float)
    power_score = Column(Float)
    storage_score = Column(Float)
    network_score = Column(Float)
    utilization_score = Column(Float)

    # Weighted contributions
    hardware_contribution = Column(Float)
    thermal_contribution = Column(Float)
    power_contribution = Column(Float)
    storage_contribution = Column(Float)
    network_contribution = Column(Float)
    utilization_contribution = Column(Float)

    # Deduction details (what caused score reductions)
    deductions = Column(JSON)  # [{"reason": "CPU temp > 85C", "points": -15, "component": "thermal"}]

    server = relationship("Server", back_populates="health_scores")

    __table_args__ = (
        Index("ix_health_server_time", "server_id", "scored_at"),
    )
