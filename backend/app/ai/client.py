"""
LLM client for the AMD on-prem GPT-oss-20B endpoint (OpenAI-compatible).

Auth is a custom header (Ocp-Apim-Subscription-Key), NOT a bearer token. Exposes
async chat() with optional tool-calling and a streaming helper. All AI features are
gated by settings.AI_ENABLED; when disabled the client reports unavailable and callers
fall back to deterministic engines.
"""
import json
from typing import Any, Dict, List, Optional
import httpx
import structlog

from app.config import settings

log = structlog.get_logger(__name__)


class LLMUnavailable(Exception):
    """Raised when the model can't be reached / AI disabled — callers fall back."""


class LLMClient:
    def __init__(self):
        self.base_url = settings.AI_BASE_URL.rstrip("/")
        self.model = settings.AI_MODEL
        self.key = settings.AI_SUBSCRIPTION_KEY
        self.timeout = settings.AI_TIMEOUT
        self.max_tokens = settings.AI_MAX_TOKENS
        self.temperature = settings.AI_TEMPERATURE

    @property
    def enabled(self) -> bool:
        return bool(settings.AI_ENABLED and self.key)

    def _headers(self, user: str = "helios") -> Dict[str, str]:
        return {
            "Ocp-Apim-Subscription-Key": self.key,
            "user": user,
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Single chat completion. Returns the raw OpenAI-style `message` dict
        (may contain tool_calls). Raises LLMUnavailable on failure."""
        if not self.enabled:
            raise LLMUnavailable("AI disabled or no subscription key")

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_completion_tokens": self.max_tokens if max_tokens is None else max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(verify=False, timeout=self.timeout) as c:
                r = await c.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            log.warning("llm_call_failed", error=str(e))
            raise LLMUnavailable(str(e))

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        usage = data.get("usage") or {}
        msg["_usage"] = {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }
        return msg

    async def health(self) -> Dict[str, Any]:
        """Lightweight reachability probe for /ai/health."""
        if not self.enabled:
            return {"available": False, "reason": "AI disabled or missing key",
                    "model": self.model, "enabled": settings.AI_ENABLED}
        try:
            msg = await self.chat(
                [{"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=5, temperature=0.0,
            )
            content = (msg.get("content") or "").strip()
            return {"available": True, "model": self.model, "probe": content[:20]}
        except LLMUnavailable as e:
            return {"available": False, "reason": str(e), "model": self.model}


llm = LLMClient()
