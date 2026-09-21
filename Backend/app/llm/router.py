"""3-tier failover router.

Tries providers in order (Groq -> OpenRouter -> Gemini) on ``ProviderError``.
Tiers whose API key is unset are skipped so a missing key doesn't burn a
request.
"""

import logging

from app.core.config import Settings, get_settings
from app.llm.base import (
    ChatMessage,
    LLMProvider,
    LLMResponse,
    ProviderError,
    ToolSchema,
)
from app.llm.gemini_provider import GeminiProvider
from app.llm.groq_provider import GroqProvider
from app.llm.openrouter_provider import OpenRouterProvider

logger = logging.getLogger(__name__)


class LLMRouter:
    """Failover chain over the configured providers."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Build the tier list, skipping providers without a key."""
        self._settings = settings or get_settings()
        self._tiers: list[LLMProvider] = []
        if self._settings.groq_api_key.get_secret_value():
            self._tiers.append(GroqProvider(self._settings))
        if self._settings.openrouter_api_key.get_secret_value():
            self._tiers.append(OpenRouterProvider(self._settings))
        if self._settings.gemini_api_key.get_secret_value():
            self._tiers.append(GeminiProvider(self._settings))

    @property
    def active_tiers(self) -> list[str]:
        """Return the names of providers currently enabled."""
        return [type(p).__name__ for p in self._tiers]

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSchema]) -> LLMResponse:
        """Run a chat completion, failing over across enabled tiers.

        Args:
            messages: OpenAI-style conversation history.
            tools: JSON tool schemas for tool calling.

        Returns:
            The first successful provider response.

        Raises:
            ProviderError: if every enabled tier fails.

        """
        if not self._tiers:
            raise ProviderError(
                "no LLM providers configured — set at least one API key",
                retryable=False,
            )
        errors: list[str] = []
        for provider in self._tiers:
            try:
                response = await provider.chat(messages, tools)
                logger.info("LLM response from %s", type(provider).__name__)
                return response
            except ProviderError as exc:
                errors.append(str(exc))
                logger.warning(
                    "tier %s failed, failing over: %s",
                    type(provider).__name__,
                    exc,
                )
        raise ProviderError(f"all LLM tiers failed: {' | '.join(errors)}")
