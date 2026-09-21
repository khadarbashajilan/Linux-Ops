"""LLM provider contracts.

Defines the shared ``LLMProvider`` Protocol every provider implements,
plus the response types returned by ``chat``. Providers speak OpenAI-style
messages/tools dicts; each provider translates to its vendor format.
"""

from dataclasses import dataclass, field
from typing import Protocol

# Messages and tool schemas use the OpenAI chat-completions shape:
#   message  -> {"role": str, "content": str, "tool_call_id"?: str,
#                "tool_calls"?: [{"id": str, "function": {...}}]}
#   tool     -> {"type": "function", "function": {"name", "description",
#                "parameters": JSONSchema}}
ChatMessage = dict
ToolSchema = dict


@dataclass(frozen=True)
class ToolCall:
    """A single function call requested by the model."""

    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class LLMResponse:
    """Model output: either text, tool calls, or both."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class ProviderError(RuntimeError):
    """Raised when a provider call fails; the router uses this to fail over."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        """Initialise with a message and whether the failure is retryable."""
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(Protocol):
    """Interface every provider implements."""

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSchema]) -> LLMResponse:
        """Run a chat completion against this provider.

        Args:
            messages: OpenAI-style conversation history.
            tools: JSON tool schemas the model may call.

        Returns:
            The model response (text and/or tool calls).

        Raises:
            ProviderError: if the upstream call fails.

        """
        ...
