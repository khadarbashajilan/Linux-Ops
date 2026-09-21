"""Agent loop orchestrator — the tool-calling brain.

Owns the loop that asks the LLM for tool calls, executes them via the
registry, feeds results back, and repeats until the model answers without
tools. The HTTP layer constructs an ``Agent`` and delegates to ``run``.
"""

import json
import logging
from dataclasses import dataclass, field

from app.llm.base import LLMResponse, ProviderError, ToolCall
from app.llm.router import LLMRouter
from app.tools import file_tools  # noqa: F401 — registers tools on import
from app.tools.registry import registry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5


@dataclass
class AgentResult:
    """Final answer plus the names of tools invoked."""

    answer: str
    invoked_tools: list[str] = field(default_factory=list)


class Agent:
    """Owns the tool loop. HTTP layer just constructs and calls this."""

    def __init__(self, router: LLMRouter | None = None) -> None:
        """Initialise with a failover LLM router.

        Args:
            router: an LLM router; defaults to one built from settings.

        """
        self._router = router or LLMRouter()

    @property
    def active_tiers(self) -> list[str]:
        """Return the names of providers currently enabled."""
        return self._router.active_tiers

    async def run(self, message: str) -> AgentResult:
        """Process one user message through the tool-calling loop.

        Args:
            message: the user's message.

        Returns:
            The final answer and the tools that were invoked.

        Raises:
            ProviderError: if all LLM tiers fail or the loop maxes out.

        """
        messages: list[dict] = [{"role": "user", "content": message}]
        invoked: list[str] = []
        for _ in range(MAX_TOOL_ROUNDS):
            response: LLMResponse = await self._router.chat(messages, registry.schemas())
            if not response.tool_calls:
                return AgentResult(answer=response.content or "", invoked_tools=invoked)
            for tool_call in response.tool_calls:
                invoked.append(tool_call.name)
                await self._execute_tool(tool_call, messages)
        raise ProviderError(f"tool loop exceeded {MAX_TOOL_ROUNDS} rounds")

    async def _execute_tool(self, tool_call: ToolCall, messages: list[dict]) -> None:
        """Execute one tool call and append its result to the message history.

        Args:
            tool_call: the model's requested tool call.
            messages: the live OpenAI-style message list (mutated in place).

        """
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(tool_call.arguments),
                        },
                    }
                ],
            }
        )
        try:
            result = await registry.execute(tool_call.name, tool_call.arguments)
            content = json.dumps(result)
        except Exception as exc:  # noqa: BLE001 — surface tool failure to the LLM
            logger.warning("tool %s failed: %s", tool_call.name, exc)
            content = json.dumps({"error": str(exc)})
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.name,
                "content": content,
            }
        )
