"""Groq LLM provider (tier 1).

Uses the official Groq async SDK, which exposes an OpenAI-compatible chat
completions API.
"""

import json
import logging

from groq import APIConnectionError, APIStatusError, AsyncGroq

from app.core.config import Settings, get_settings
from app.llm.base import (
    ChatMessage,
    LLMResponse,
    ProviderError,
    ToolCall,
    ToolSchema,
)

logger = logging.getLogger(__name__)


class GroqProvider:
    """Provider wrapping Groq's chat completions API."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialise the Groq client from the given (or cached) settings."""
        self._settings = settings or get_settings()
        self._client = AsyncGroq(api_key=self._settings.groq_api_key.get_secret_value())

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSchema]) -> LLMResponse:
        """Run a chat completion against Groq.

        Args:
            messages: OpenAI-style conversation history.
            tools: JSON tool schemas the model may call.

        Returns:
            The parsed model response.

        Raises:
            ProviderError: on transport or API errors, so the router can
                fail over to the next tier.

        """
        kwargs: dict = {"model": self._settings.groq_model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        try:
            completion = await self._client.chat.completions.create(**kwargs)
        except (APIConnectionError, APIStatusError) as exc:
            status = getattr(exc, "status_code", None)
            logger.warning("Groq provider failed (status=%s): %s", status, exc)
            retryable = status in (429, 500, 502, 503, 504) or isinstance(exc, APIConnectionError)
            raise ProviderError(f"groq: {exc}", retryable=retryable) from exc

        message = completion.choices[0].message
        tool_calls = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
        return LLMResponse(content=message.content, tool_calls=tool_calls)
