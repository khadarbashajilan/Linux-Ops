"""OpenRouter LLM provider (tier 2).

OpenRouter exposes an OpenAI-compatible REST API; we call it with httpx so
the dependency surface stays small. The ``openrouter/free`` router model
selects free tool-calling-capable models automatically.
"""

import json
import logging

import httpx

from app.core.config import Settings, get_settings
from app.llm.base import (
    ChatMessage,
    LLMResponse,
    ProviderError,
    ToolCall,
    ToolSchema,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider:
    """Provider calling OpenRouter's OpenAI-compatible chat endpoint."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialise with the API key and model id from settings."""
        self._settings = settings or get_settings()
        self._api_key = self._settings.openrouter_api_key.get_secret_value()

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSchema]) -> LLMResponse:
        """Run a chat completion against OpenRouter.

        Args:
            messages: OpenAI-style conversation history.
            tools: JSON tool schemas the model may call.

        Returns:
            The parsed model response.

        Raises:
            ProviderError: on HTTP or transport errors (retryable for 4xx/5xx).

        """
        payload: dict = {
            "model": self._settings.openrouter_model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{BASE_URL}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            status = getattr(exc, "response", None)
            code = getattr(status, "status_code", None) if status else None
            logger.warning("OpenRouter provider failed (status=%s): %s", code, exc)
            raise ProviderError(f"openrouter: {exc}") from exc

        message = data["choices"][0]["message"]
        tool_calls = []
        for call in message.get("tool_calls") or []:
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(
                ToolCall(
                    id=call["id"],
                    name=call["function"]["name"],
                    arguments=arguments,
                )
            )
        return LLMResponse(content=message.get("content"), tool_calls=tool_calls)
