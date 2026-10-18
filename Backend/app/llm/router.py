"""LLM provider entrypoint.

Single Ollama provider — calls the local Ollama instance.
Assumes Docker (or bare-metal Ollama) is already running with the configured model.
"""

import logging

from app.core.config import get_settings
from app.llm.base import (
    ChatMessage,
    LLMResponse,
    ToolSchema,
)
from app.llm.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)


class LLMRouter:
    """Thin wrapper — single Ollama provider, no failover."""

    def __init__(self) -> None:
        """Initialise the Ollama provider."""
        self._provider = OllamaProvider(get_settings())

    @property
    def active_tiers(self) -> list[str]:
        """Return the active provider name."""
        return ["OllamaProvider"]

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSchema]) -> LLMResponse:
        """Run a chat completion against the Ollama provider.

        Args:
            messages: OpenAI-style conversation history.
            tools: JSON tool schemas for tool calling.

        Returns:
            The model response.

        Raises:
            OllamaConnectionError: when Ollama is unreachable.
            OllamaResponseError: when Ollama returns a non-200 or unexpected format.
            ProviderError: on unexpected internal errors.

        """
        response = await self._provider.chat(messages, tools)
        logger.info("LLM response from Ollama (%s)", self._provider._model)
        return response

    async def health_check(self) -> tuple[bool, float]:
        """Check if Ollama is reachable and responsive.

        Returns:
            A tuple of (is_healthy, latency_ms).

        Raises:
            OllamaConnectionError: when Ollama cannot be reached.

        """
        return await self._provider.health_check()
