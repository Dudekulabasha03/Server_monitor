"""
Observability helper — records every ReAct step to ai_traces and runs the
hallucination check (numbers/hostnames in the answer not present in any tool result).
"""
import re
import uuid
from typing import Any, Dict, List, Optional
import structlog
from app.database import AsyncSessionLocal
from app.models.ai import AITrace

log = structlog.get_logger(__name__)

_NUM = re.compile(r"\b\d[\d,\.]*\b")


def _truncate(obj: Any, n: int = 2000) -> Any:
    try:
        import json
        s = json.dumps(obj)
        return obj if len(s) <= n else {"_truncated": s[:n]}
    except Exception:
        return {"_unserializable": str(obj)[:n]}


async def record_step(run_id: str, agent: str, step_no: int, *, session_id: str = None,
                      thought: str = None, action: Dict = None, observation: Any = None,
                      latency_ms: int = None, tokens_in: int = None, tokens_out: int = None,
                      flags: Dict = None) -> None:
    try:
        async with AsyncSessionLocal() as db:
            db.add(AITrace(
                id=str(uuid.uuid4()), run_id=run_id, session_id=session_id, agent=agent,
                step_no=step_no, thought=(thought or "")[:4000], action=action,
                observation=_truncate(observation) if observation is not None else None,
                latency_ms=latency_ms, tokens_in=tokens_in, tokens_out=tokens_out,
                flags=flags,
            ))
            await db.commit()
    except Exception as e:
        log.debug("trace_write_failed", error=str(e))


def check_unbacked_claims(answer: str, observations: List[Any]) -> List[str]:
    """Return numeric tokens in the answer that don't appear in any tool observation.

    Heuristic guardrail: flags potential hallucinated figures. Not a hard block —
    surfaced in the AI Ops dashboard for review.
    """
    if not answer:
        return []
    import json
    obs_text = " ".join(json.dumps(o) for o in observations if o is not None)
    obs_nums = set(_NUM.findall(obs_text.replace(",", "")))
    flagged = []
    for tok in _NUM.findall(answer.replace(",", "")):
        # ignore trivial small ints (counts like "1.", years, list markers)
        if tok in obs_nums:
            continue
        try:
            v = float(tok)
        except ValueError:
            continue
        if v < 5 or 2000 <= v <= 2100:  # skip tiny numbers and year-like values
            continue
        flagged.append(tok)
    return flagged[:10]
