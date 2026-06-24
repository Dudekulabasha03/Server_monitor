"""AI / agentic endpoints (experimental). All read-only; degrade to rule-based on failure."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database import get_db
from app.config import settings
from app.ai.client import llm, LLMUnavailable
from app.ai import agents, tools as toolmod, memory
from app.ai.react import run_react
from app.models.ai import AITrace
from app.models.alerts import Alert
from app.models.server import Server, MetricsSnapshot
from app.core.security import decode_access_token

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)

# Team name → fleet DB team mapping (same as auth.py)
_AUTH_TO_FLEET = {
    "Security Patch Team": "Security Patch Team",
    "TSP Team": "TSP",
    "DPDK Team": "DPDK",
    "Performance Team": "Performance",
    "AI Team": "AI",
    "Cloud Team": "Cloud",
}


def _extract_user(creds: Optional[HTTPAuthorizationCredentials]):
    """Return (user_id, email, fleet_team) from JWT, or (None, None, None)."""
    if not creds:
        return None, None, None
    payload = decode_access_token(creds.credentials)
    if not payload:
        return None, None, None
    return payload.get("sub"), payload.get("email"), None


class AskBody(BaseModel):
    question: str
    session_id: Optional[str] = None
    fleet_team: Optional[str] = None   # passed by frontend for team scoping


@router.get("/health")
async def ai_health():
    h = await llm.health()
    h["enabled"] = settings.AI_ENABLED
    return h


def _scope_question(question: str, fleet_team: Optional[str]) -> str:
    """Prepend team context so AI automatically scopes queries without user having to ask."""
    if not fleet_team:
        return question
    # Only prepend if question doesn't already mention the team
    if fleet_team.lower() in question.lower():
        return question
    return f"[Context: I am working with the {fleet_team} team's servers] {question}"


@router.post("/ask")
async def ask(body: AskBody, creds: HTTPAuthorizationCredentials = Depends(_bearer)):
    """Fleet Copilot — team-scoped, per-user history, benchmark advisor."""
    if not llm.enabled:
        return {"available": False, "answer": "AI is disabled. Set AI_ENABLED and a key.", "fallback": True}

    uid, email, _ = _extract_user(creds)
    fleet_team = body.fleet_team  # frontend sends this from /auth/my-team-context
    scoped_q = _scope_question(body.question, fleet_team)

    try:
        res = await agents.answer_question(scoped_q, session_id=body.session_id, user_id=uid)
        return {"available": True, **res}
    except LLMUnavailable as e:
        return {"available": False, "fallback": True,
                "answer": "AI model is unavailable right now. Try the dashboards directly.",
                "reason": str(e)}


@router.post("/learn-result")
async def learn_from_result(
    server_hostname: str,
    benchmark_name: str,
    result_summary: str,
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """Store benchmark result in AI long-term memory so future queries can reference it."""
    uid, email, _ = _extract_user(creds)
    await memory.save_knowledge(
        topic=f"benchmark_result:{benchmark_name}:{server_hostname}",
        content=f"Benchmark '{benchmark_name}' on {server_hostname}: {result_summary}",
        server_id=None,
        confidence=1.0,
    )
    return {"message": "Result stored in AI memory", "topic": f"{benchmark_name} on {server_hostname}"}


@router.post("/ask-stream")
async def ask_stream(body: AskBody):
    """Streaming Copilot (SSE). Emits status/thinking/tool/answer/done events for a live
    'thinking' UX like ChatGPT/Claude."""
    import json as _json
    from fastapi.responses import StreamingResponse
    from app.ai import agents, memory, prompts
    from app.ai.react import run_react_stream

    if not llm.enabled:
        async def _disabled():
            yield "data: " + _json.dumps({"type": "error", "message": "AI disabled"}) + "\n\n"
        return StreamingResponse(_disabled(), media_type="text/event-stream")

    async def gen():
        route = await agents.classify_intent(body.question)
        system = agents.ROUTES[route] + "\n\n" + prompts.few_shot_block(route)
        episodes = await memory.recall_episodes(body.question, k=3)
        knowledge = await memory.recall_knowledge(body.question, k=3)
        mem_block = memory.format_memory_context(episodes, knowledge)
        if mem_block:
            system += prompts.memory_context_template(mem_block)
        history = await memory.get_short_term(body.session_id) if body.session_id else []
        yield "data: " + _json.dumps({"type": "route", "route": route}) + "\n\n"
        try:
            async for ev in run_react_stream(
                agent=route, system_prompt=system, user_content=body.question,
                tool_names=agents.ROUTE_TOOLS[route], session_id=body.session_id, history=history,
            ):
                yield "data: " + _json.dumps(ev) + "\n\n"
        except Exception as e:
            yield "data: " + _json.dumps({"type": "error", "message": str(e)}) + "\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/rca/{alert_id}")
async def ai_rca(alert_id: str, db: AsyncSession = Depends(get_db)):
    """AI root-cause for an alert, with rule-based fallback (engines/rca.py)."""
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")
    server = (await db.execute(select(Server).where(Server.id == alert.server_id))).scalar_one_or_none()
    snap = (await db.execute(
        select(MetricsSnapshot).where(MetricsSnapshot.server_id == alert.server_id)
        .order_by(MetricsSnapshot.collected_at.desc()).limit(1)
    )).scalar_one_or_none()

    # Rule-based result is ALWAYS computed (guaranteed fallback + shown alongside)
    from app.engines.rca import RCAEngine
    rule = RCAEngine().analyze(alert, snap)
    rule_dict = {"possible_causes": rule.possible_causes, "impact": rule.impact,
                 "recommended_actions": rule.recommended_actions,
                 "correlated_signals": rule.correlated_signals}

    if not llm.enabled or not server:
        return {"available": False, "rule_based": rule_dict}

    try:
        from app.ai import prompts
        q = (f"Perform root-cause analysis for alert '{alert.title}' on server "
             f"{server.hostname}: {alert.message}. Inspect the server, its recent SEL "
             f"events, firing alerts, and metric history. Give the full structured RCA "
             f"including the Prevention section.")
        system = agents.ROUTES["rca"] + "\n\n" + prompts.few_shot_block("rca")
        res = await run_react(agent="rca", system_prompt=system, user_content=q,
                              tool_names=agents.ROUTE_TOOLS["rca"])
        await memory.save_episode("rca", q, res["answer"], server_id=server.id,
                                  tools_used=res.get("tools_used"))
        return {"available": True, "ai_analysis": res["answer"],
                "tools_used": res.get("tools_used"), "flags": res.get("flags"),
                "rule_based": rule_dict}
    except LLMUnavailable as e:
        return {"available": False, "fallback": True, "reason": str(e), "rule_based": rule_dict}


@router.get("/sel-summary")
async def sel_summary(hostname: Optional[str] = None):
    """AI summary of SEL activity (fleet-wide or per host)."""
    if not llm.enabled:
        return {"available": False}
    scope = f"for server {hostname}" if hostname else "across the fleet"
    q = f"Summarize the recent System Event Log (SEL) activity {scope}. Highlight critical items."
    try:
        res = await run_react(agent="sel", system_prompt=agents.ROUTES["sel"],
                              user_content=q, tool_names=agents.ROUTE_TOOLS["sel"])
        return {"available": True, "summary": res["answer"], "flags": res.get("flags")}
    except LLMUnavailable as e:
        return {"available": False, "reason": str(e)}


@router.get("/observability")
async def observability(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """AI Ops: recent traces + per-agent metrics + flagged runs."""
    traces = (await db.execute(
        select(AITrace).order_by(AITrace.created_at.desc()).limit(min(limit, 500))
    )).scalars().all()
    # per-agent aggregates
    agg = (await db.execute(
        select(AITrace.agent, func.count(AITrace.id), func.avg(AITrace.latency_ms),
               func.sum(AITrace.tokens_in), func.sum(AITrace.tokens_out))
        .group_by(AITrace.agent)
    )).all()
    agents_stats = [{"agent": a, "steps": int(n or 0),
                     "avg_latency_ms": round(float(lat), 0) if lat else None,
                     "tokens_in": int(ti or 0), "tokens_out": int(to or 0)}
                    for a, n, lat, ti, to in agg]
    rows = [{
        "run_id": t.run_id, "agent": t.agent, "step": t.step_no,
        "thought": (t.thought or "")[:300], "action": t.action,
        "latency_ms": t.latency_ms, "flags": t.flags,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in traces]
    flagged = sum(1 for t in traces if t.flags and t.flags.get("unbacked_claims"))
    return {"agents": agents_stats, "recent_traces": rows,
            "total_traces": len(rows), "flagged_runs": flagged}
