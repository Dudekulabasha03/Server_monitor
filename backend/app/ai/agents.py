"""
Supervisor + specialist ReAct agents.

The supervisor classifies intent and routes to ONE specialist. Each specialist gets a
rich domain-grounded system prompt (app/ai/prompts.py) + few-shot guidance + a focused
tool set. RCA/Capacity/SEL fall back to deterministic engines on LLM failure.
"""
import re
from typing import Any, Dict, List, Optional
import structlog

from app.ai.client import llm, LLMUnavailable
from app.ai.react import run_react
from app.ai import memory, prompts

log = structlog.get_logger(__name__)

ROUTES = prompts.ROUTE_PROMPTS
ROUTE_TOOLS = prompts.ROUTE_TOOLS

_METRIC_WORDS = ("temperature", "temp", "thermal", "power", "watt", "cpu", "utiliz",
                 "memory", "mem ", "disk", "hottest", "coolest", "busiest", "highest",
                 "lowest", "compare", "vs ", "versus", "trend", "draw", "consumption",
                 "live", "stream", "real-time", "realtime", "monitor")
_RCA_WORDS = ("root cause", "why is", "why did", "why has", "diagnose", "rca", "failed",
              "failure", "overheat", "went offline", "prevent", "fix", "what do i do",
              "what should i do", "recover", "troubleshoot")
_SEL_WORDS = ("sel", "event log", "recent events", "hardware event")
_CAP_WORDS = ("capacity", "headroom", "idle", "wasting", "hotspot", "forecast", "growth")


_FLEETQA_WORDS = ("user activity", "logged in", "login", "session", "who is on", "who's on",
                  "ip address", "ip of", "network", "nic", "mac address", "link down", "link up",
                  "disk", "storage", "smart", "firmware", "bios", "microcode", "idle vs")


_VIZ_WORDS = ("graph", "chart", "plot", "visual", "visualization", "visualisation",
              "bar chart", "pie chart", "diagram", "dashboard view", "draw")


async def classify_intent(question: str) -> str:
    """Heuristic router. Order matters: viz/tab terms and RCA before generic metrics."""
    q = question.lower()
    # Graph/chart requests -> visualization agent (emits chart specs).
    if any(w in q for w in _VIZ_WORDS):
        return "viz"
    # User activity / network / storage / firmware -> fleet_qa (has those tools).
    # Checked early so 'idle servers' / 'link down' don't get grabbed by capacity/metrics.
    if any(w in q for w in _FLEETQA_WORDS):
        return "fleet_qa"
    if any(w in q for w in _RCA_WORDS):
        return "rca"
    if any(w in q for w in _SEL_WORDS):
        return "sel"
    if any(w in q for w in _CAP_WORDS):
        return "capacity"
    if any(w in q for w in _METRIC_WORDS):
        return "metrics"
    return "fleet_qa"


def _hostnames_in(question: str) -> List[str]:
    """Extract likely hostnames (codename-style) to pre-focus memory recall."""
    return re.findall(r"\b(?:volcano|titanite|cinnabar|ruby|shale|daytona[a-z]*|idrac[-\w]*|"
                      r"ilo[\w]*|smc[\w-]*|xcc[-\w]*)[-\w]*\b", question.lower())


async def answer_question(question: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Main Copilot entrypoint: route -> recall memory -> ReAct -> persist memory."""
    route = await classify_intent(question)
    system = ROUTES[route]
    tool_names = ROUTE_TOOLS[route]

    # Few-shot guidance for this route (teaches tool selection + answer style)
    system = system + "\n\n" + prompts.few_shot_block(route)

    # Memory recall (episodic + long-term) -> grounding block
    episodes = await memory.recall_episodes(question, k=3)
    knowledge = await memory.recall_knowledge(question, k=3)
    mem_block = memory.format_memory_context(episodes, knowledge)
    if mem_block:
        system = system + prompts.memory_context_template(mem_block)

    history = await memory.get_short_term(session_id) if session_id else []

    result = await run_react(
        agent=route, system_prompt=system, user_content=question,
        tool_names=tool_names, session_id=session_id, history=history,
    )

    # Persist memory (best-effort)
    if session_id:
        await memory.append_short_term(session_id, "user", question)
        await memory.append_short_term(session_id, "assistant", result["answer"])
    await memory.save_episode(route, question, result["answer"],
                              session_id=session_id, tools_used=result.get("tools_used"))
    result["route"] = route
    return result
