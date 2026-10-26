"""LLM provider contracts.

Defines the shared ``LLMProvider`` Protocol every provider implements, the
message/tool shapes exchanged with it, and the response types returned by
``chat``. Shapes follow Ollama's ``/api/chat`` format.
"""

from dataclasses import dataclass, field
from typing import Any, NotRequired, Protocol, TypedDict


class FunctionCall(TypedDict):
    """The function part of a tool call: name plus already-parsed arguments."""

    name: str
    arguments: dict[str, Any]


class ToolCallMessage(TypedDict):
    """A tool call as it appears inside an assistant message."""

    type: str
    function: FunctionCall
    id: NotRequired[str]


class ChatMessage(TypedDict):
    """One conversation message (user, assistant, or tool result)."""

    role: str
    content: str
    tool_calls: NotRequired[list[ToolCallMessage]]
    tool_call_id: NotRequired[str]
    tool_name: NotRequired[str]


class FunctionSchema(TypedDict):
    """The function part of a tool schema shown to the model."""

    name: str
    description: str
    parameters: dict[str, Any]


class ToolSchema(TypedDict):
    """A tool the model may call."""

    type: str
    function: FunctionSchema


@dataclass(frozen=True)
class ToolCall:
    """A single function call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    """Model output: text, tool calls, or both."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    """Interface every provider implements."""

    @property
    def model(self) -> str:
        """Return the model name this provider talks to."""
        ...

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSchema]) -> LLMResponse:
        """Run a chat completion against this provider.

        Args:
            messages: conversation history.
            tools: JSON tool schemas the model may call.

        Returns:
            The model response (text and/or tool calls).

        """
        ...

    async def health_check(self) -> float:
        """Check the provider is reachable.

        Returns:
            Round-trip latency in milliseconds.

        """
        ...

    async def aclose(self) -> None:
        """Release network resources held by the provider."""
        ...
