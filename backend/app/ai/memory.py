"""
Three-tier memory.

- Short-term: per-session conversation turns in Redis (1h TTL).
- Episodic: past Q&A / RCA verdicts in Postgres, recalled by server + keyword + recency.
- Long-term: durable confirmed facts in Postgres, recalled by keyword + recency.

Semantic recall is keyword+recency for now (pgvector not installed); the schema is
embedding-ready for a later upgrade.
"""
import json
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import structlog
from sqlalchemy import select, or_
from app.database import AsyncSessionLocal
from app.models.ai import AIEpisode, AIKnowledge
from app.config import settings

log = structlog.get_logger(__name__)

_STOP = {"the", "a", "an", "is", "are", "of", "in", "on", "and", "or", "to", "for",
         "what", "which", "how", "why", "show", "me", "list", "all", "server", "servers"}


def keywords(text: str, n: int = 12) -> str:
    toks = re.findall(r"[a-zA-Z0-9_\-]{3,}", (text or "").lower())
    out, seen = [], set()
    for t in toks:
        if t in _STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= n:
            break
    return " ".join(out)


# ── Short-term (Redis) ──────────────────────────────────────────────────────
async def _redis():
    try:
        import redis.asyncio as redis
        return redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as e:
        log.debug("redis_unavailable", error=str(e))
        return None


async def get_short_term(session_id: str, limit: int = 6) -> List[Dict[str, str]]:
    if not session_id:
        return []
    r = await _redis()
    if not r:
        return []
    try:
        raw = await r.lrange(f"ai:sess:{session_id}", -limit * 2, -1)
        return [json.loads(x) for x in raw]
    except Exception:
        return []
    finally:
        try:
            await r.aclose()
        except Exception:
            pass


async def append_short_term(session_id: str, role: str, content: str) -> None:
    if not session_id:
        return
    r = await _redis()
    if not r:
        return
    try:
        key = f"ai:sess:{session_id}"
        await r.rpush(key, json.dumps({"role": role, "content": content[:4000]}))
        await r.expire(key, 3600)
        await r.ltrim(key, -40, -1)
    except Exception:
        pass
    finally:
        try:
            await r.aclose()
        except Exception:
            pass


# ── Episodic (Postgres) ─────────────────────────────────────────────────────
async def save_episode(kind: str, question: str, answer: str, *, session_id: str = None,
                       server_id: str = None, tools_used: List[str] = None) -> None:
    try:
        async with AsyncSessionLocal() as db:
            db.add(AIEpisode(
                id=str(uuid.uuid4()), session_id=session_id, server_id=server_id, kind=kind,
                question=question[:4000], answer=answer[:8000], tools_used=tools_used or [],
                key_terms=keywords(question + " " + answer),
                ttl_at=datetime.now(timezone.utc) + timedelta(days=90),
            ))
            await db.commit()
    except Exception as e:
        log.debug("episode_save_failed", error=str(e))


async def recall_episodes(query: str, server_id: str = None, k: int = 3) -> List[Dict[str, Any]]:
    terms = keywords(query).split()
    if not terms and not server_id:
        return []
    try:
        async with AsyncSessionLocal() as db:
            q = select(AIEpisode)
            conds = []
            if server_id:
                conds.append(AIEpisode.server_id == server_id)
            for t in terms[:6]:
                conds.append(AIEpisode.key_terms.ilike(f"%{t}%"))
            if conds:
                q = q.where(or_(*conds))
            q = q.order_by(AIEpisode.created_at.desc()).limit(k)
            rows = (await db.execute(q)).scalars().all()
            return [{"question": r.question, "answer": r.answer,
                     "when": r.created_at.isoformat() if r.created_at else None} for r in rows]
    except Exception as e:
        log.debug("episode_recall_failed", error=str(e))
        return []


# ── Long-term (Postgres) ────────────────────────────────────────────────────
async def save_knowledge(scope: str, scope_ref: str, fact: str, *, source: str = "rca",
                         confidence: float = 0.6) -> None:
    try:
        async with AsyncSessionLocal() as db:
            db.add(AIKnowledge(
                id=str(uuid.uuid4()), scope=scope, scope_ref=scope_ref, fact=fact[:4000],
                source=source, confidence=confidence, key_terms=keywords(fact),
            ))
            await db.commit()
    except Exception as e:
        log.debug("knowledge_save_failed", error=str(e))


async def recall_knowledge(query: str, scope_ref: str = None, k: int = 3) -> List[Dict[str, Any]]:
    terms = keywords(query).split()
    try:
        async with AsyncSessionLocal() as db:
            q = select(AIKnowledge)
            conds = []
            if scope_ref:
                conds.append(AIKnowledge.scope_ref == scope_ref)
            for t in terms[:6]:
                conds.append(AIKnowledge.key_terms.ilike(f"%{t}%"))
            if conds:
                q = q.where(or_(*conds))
            q = q.order_by(AIKnowledge.confidence.desc(), AIKnowledge.created_at.desc()).limit(k)
            rows = (await db.execute(q)).scalars().all()
            return [{"fact": r.fact, "source": r.source, "confidence": r.confidence} for r in rows]
    except Exception as e:
        log.debug("knowledge_recall_failed", error=str(e))
        return []


def format_memory_context(episodes: List[Dict], knowledge: List[Dict]) -> str:
    """Render recalled memory as a compact grounding block for the system prompt."""
    if not episodes and not knowledge:
        return ""
    parts = []
    if knowledge:
        parts.append("Known facts (long-term memory):")
        parts += [f"- {k['fact']} (confidence {k.get('confidence', '?')})" for k in knowledge]
    if episodes:
        parts.append("Relevant past Q&A (episodic memory):")
        parts += [f"- Q: {e['question'][:120]} → A: {e['answer'][:160]}" for e in episodes]
    return "\n".join(parts)
