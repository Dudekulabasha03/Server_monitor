"""
AI subsystem tables: observability traces + 3-tier memory (episodic, long-term).

Short-term memory lives in Redis (per-session), not here. These tables back the
Observability agent and the episodic/long-term recall used to ground answers.
"""
from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Text, Index
from sqlalchemy.sql import func
from app.database import Base


class AITrace(Base):
    """One row per ReAct step — powers the AI Ops observability dashboard."""
    __tablename__ = "ai_traces"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), index=True, nullable=False)
    session_id = Column(String(64), index=True)
    agent = Column(String(48), index=True)        # supervisor | fleet_qa | rca | sel | capacity
    step_no = Column(Integer, default=0)
    thought = Column(Text)                          # model reasoning for this step
    action = Column(JSON)                           # {tool, args} or null
    observation = Column(JSON)                      # tool result (truncated) or null
    latency_ms = Column(Integer)
    tokens_in = Column(Integer)
    tokens_out = Column(Integer)
    flags = Column(JSON)                            # {unbacked_claims:[...], fallback:bool, error:str}
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (Index("ix_ai_traces_run_step", "run_id", "step_no"),)


class AIEpisode(Base):
    """Episodic memory: past Q&A / RCA verdicts, recalled by server + keyword + recency."""
    __tablename__ = "ai_episodes"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(64), index=True)
    server_id = Column(String(36), index=True)      # nullable — fleet-level episodes
    kind = Column(String(32), index=True)           # qa | rca | sel | capacity
    question = Column(Text)
    answer = Column(Text)
    tools_used = Column(JSON)
    key_terms = Column(Text)                         # space-joined keywords for ILIKE recall
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    ttl_at = Column(DateTime(timezone=True))         # prune after this


class AIKnowledge(Base):
    """Long-term memory: durable confirmed facts (root causes, working remediations,
    fleet patterns). Keyword+recency recall now; an `embedding` column can be added later
    for true semantic search (pgvector)."""
    __tablename__ = "ai_knowledge"

    id = Column(String(36), primary_key=True)
    scope = Column(String(16), index=True)          # server | family | fleet
    scope_ref = Column(String(128), index=True)     # hostname / family / "fleet"
    key_terms = Column(Text)
    fact = Column(Text, nullable=False)
    source = Column(String(24))                      # rca | resolution | pattern | feedback
    confidence = Column(Float, default=0.6)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
