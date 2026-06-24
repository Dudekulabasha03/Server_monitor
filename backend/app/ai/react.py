"""
Generic ReAct loop: Thought -> Action(tool) -> Observation -> ... -> Answer.

GPT-oss-20B returns `reasoning` (thought) + `tool_calls` (actions). We execute the
read-only tools, feed observations back, and repeat until the model answers or we hit
AI_MAX_REACT_STEPS. Every step is traced; the final answer is hallucination-checked.
"""
import json
import time
import uuid
from typing import Any, Dict, List, Optional
import structlog

from app.config import settings
from app.ai.client import llm, LLMUnavailable
from app.ai import tools as toolmod
from app.ai.observability import record_step, check_unbacked_claims

log = structlog.get_logger(__name__)


async def run_react(
    *,
    agent: str,
    system_prompt: str,
    user_content: str,
    tool_names: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    max_steps: Optional[int] = None,
) -> Dict[str, Any]:
    """Run one ReAct conversation. Returns {answer, tools_used, run_id, flags, steps}.

    Raises LLMUnavailable so the caller can fall back to a deterministic engine.
    """
    run_id = str(uuid.uuid4())
    steps = max_steps or settings.AI_MAX_REACT_STEPS
    schemas = toolmod.tool_schemas(tool_names)

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})

    observations: List[Any] = []
    tools_used: List[str] = []

    for step in range(steps):
        t0 = time.monotonic()
        msg = await llm.chat(messages, tools=schemas)
        latency = int((time.monotonic() - t0) * 1000)
        usage = msg.get("_usage", {})
        thought = msg.get("reasoning") or ""
        tool_calls = msg.get("tool_calls") or []

        # Append assistant turn (preserve tool_calls so the API can match tool results)
        messages.append({k: v for k, v in msg.items() if k != "_usage"})

        if not tool_calls:
            answer = (msg.get("content") or "").strip()
            flagged = check_unbacked_claims(answer, observations)
            await record_step(run_id, agent, step, session_id=session_id, thought=thought,
                              latency_ms=latency, tokens_in=usage.get("prompt_tokens"),
                              tokens_out=usage.get("completion_tokens"),
                              flags={"unbacked_claims": flagged} if flagged else None)
            return {"answer": answer, "tools_used": tools_used, "run_id": run_id,
                    "flags": {"unbacked_claims": flagged}, "steps": step + 1,
                    "observations": observations}

        # Execute each requested tool call, feed observations back
        for tc in tool_calls:
            fn = (tc.get("function") or {})
            name = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            result = await toolmod.run_tool(name, args)
            observations.append(result)
            tools_used.append(name)
            await record_step(run_id, agent, step, session_id=session_id, thought=thought,
                              action={"tool": name, "args": args}, observation=result,
                              latency_ms=latency, tokens_in=usage.get("prompt_tokens"),
                              tokens_out=usage.get("completion_tokens"))
            messages.append({
                "role": "tool", "tool_call_id": tc.get("id"),
                "name": name, "content": json.dumps(result)[:24000],
            })

    # Ran out of steps — ask for a final answer with no tools
    messages.append({"role": "user",
                     "content": "Provide your final answer now using the data gathered above."})
    try:
        final = await llm.chat(messages)
        answer = (final.get("content") or "").strip()
    except LLMUnavailable:
        answer = "I gathered data but could not finalize an answer in time."
    flagged = check_unbacked_claims(answer, observations)
    await record_step(run_id, agent, steps, session_id=session_id,
                      flags={"unbacked_claims": flagged, "max_steps_hit": True})
    return {"answer": answer, "tools_used": tools_used, "run_id": run_id,
            "flags": {"unbacked_claims": flagged, "max_steps_hit": True},
            "steps": steps, "observations": observations}


# ── Friendly labels for streaming status events ─────────────────────────────
_TOOL_LABEL = {
    "get_fleet_summary": "Reading fleet status",
    "query_servers": "Searching servers",
    "get_server_detail": "Inspecting server",
    "get_alerts": "Checking alerts",
    "get_sel_events": "Reading event log (SEL)",
    "get_risk": "Evaluating risk scores",
    "compare_servers": "Comparing servers",
    "top_servers_by_metric": "Ranking servers",
    "get_metric_history": "Analyzing trend",
    "get_recommendations": "Gathering remediation steps",
}


def _tool_label(name: str, args: Dict[str, Any]) -> str:
    """Human label that includes the key argument so repeated calls look distinct."""
    base = _TOOL_LABEL.get(name, f"Running {name}")
    if not args:
        return base
    hint = args.get("hostname") or args.get("search") or args.get("metric") \
        or args.get("family") or args.get("team") or args.get("datacenter")
    if name == "compare_servers" and args.get("hostnames"):
        hint = ", ".join(args["hostnames"][:4])
    return f"{base}: {hint}" if hint else base


# Hard cap on total tool calls per run — prevents the model from inspecting every
# server one-by-one (which looks like an endless "Inspecting server" loop).
_MAX_TOOL_CALLS = 12


async def run_react_stream(
    *, agent: str, system_prompt: str, user_content: str,
    tool_names: Optional[List[str]] = None, session_id: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None, max_steps: Optional[int] = None,
):
    """Async generator yielding progress events for a live 'thinking' UX.

    Event dicts: {type: status|thinking|tool|answer|done|error, ...}. The model is asked
    in a non-streamed loop (tool calls need full messages), but we emit a status event at
    each step so the UI shows 'thinking', 'reading fleet status', etc., then stream the
    final answer in word chunks.
    """
    run_id = str(uuid.uuid4())
    steps = max_steps or settings.AI_MAX_REACT_STEPS
    schemas = toolmod.tool_schemas(tool_names)
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    observations: List[Any] = []
    tools_used: List[str] = []

    yield {"type": "status", "stage": "thinking", "label": "Thinking…", "run_id": run_id}

    for step in range(steps):
        t0 = time.monotonic()
        try:
            msg = await llm.chat(messages, tools=schemas)
        except LLMUnavailable as e:
            yield {"type": "error", "message": f"AI unavailable: {e}"}
            return
        latency = int((time.monotonic() - t0) * 1000)
        usage = msg.get("_usage", {})
        thought = msg.get("reasoning") or ""
        tool_calls = msg.get("tool_calls") or []
        messages.append({k: v for k, v in msg.items() if k != "_usage"})

        if thought:
            yield {"type": "thinking", "text": thought[:600]}

        if not tool_calls:
            answer = (msg.get("content") or "").strip()
            flagged = check_unbacked_claims(answer, observations)
            await record_step(run_id, agent, step, session_id=session_id, thought=thought,
                              latency_ms=latency, tokens_in=usage.get("prompt_tokens"),
                              tokens_out=usage.get("completion_tokens"),
                              flags={"unbacked_claims": flagged} if flagged else None)
            # stream the answer in chunks for a typed-out feel
            buf = ""
            for tok in answer.split(" "):
                buf += tok + " "
                if len(buf) >= 24:
                    yield {"type": "answer", "delta": buf}
                    buf = ""
            if buf:
                yield {"type": "answer", "delta": buf}
            yield {"type": "done", "run_id": run_id, "tools_used": tools_used,
                   "route": agent, "flags": {"unbacked_claims": flagged}}
            if session_id:
                from app.ai import memory
                await memory.append_short_term(session_id, "user", user_content)
                await memory.append_short_term(session_id, "assistant", answer)
                await memory.save_episode(agent, user_content, answer,
                                          session_id=session_id, tools_used=tools_used)
            return

        over_cap = False
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            # Enforce the global tool-call cap so the model can't loop over every server.
            if len(tools_used) >= _MAX_TOOL_CALLS:
                messages.append({"role": "tool", "tool_call_id": tc.get("id"), "name": name,
                                 "content": json.dumps({"error": "tool budget exhausted — "
                                 "answer now with the data already gathered; use bulk tools "
                                 "(query_servers/top_servers_by_metric) instead of per-server calls."})})
                over_cap = True
                continue
            yield {"type": "tool", "tool": name, "label": _tool_label(name, args), "args": args}
            result = await toolmod.run_tool(name, args)
            observations.append(result)
            tools_used.append(name)
            # If a long-running batch job was started, tell the UI to auto-poll it so it
            # can post the completion result without the user asking again.
            if isinstance(result, dict) and result.get("batch_job_id") and result.get("started"):
                yield {"type": "batch_started", "batch_job_id": result["batch_job_id"]}
            await record_step(run_id, agent, step, session_id=session_id, thought=thought,
                              action={"tool": name, "args": args}, observation=result,
                              latency_ms=latency, tokens_in=usage.get("prompt_tokens"),
                              tokens_out=usage.get("completion_tokens"))
            messages.append({"role": "tool", "tool_call_id": tc.get("id"),
                             "name": name, "content": json.dumps(result)[:24000]})
        if over_cap:
            yield {"type": "status", "stage": "finalizing", "label": "Summarizing findings…"}

    yield {"type": "status", "stage": "finalizing", "label": "Finalizing answer…"}
    messages.append({"role": "user", "content": "Provide your final answer now."})
    try:
        final = await llm.chat(messages)
        answer = (final.get("content") or "").strip()
    except LLMUnavailable:
        answer = "I gathered data but could not finalize an answer in time."
    for tok in answer.split(" "):
        yield {"type": "answer", "delta": tok + " "}
    yield {"type": "done", "run_id": run_id, "tools_used": tools_used, "route": agent}
