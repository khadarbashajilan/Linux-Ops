"""Agent loop orchestrator — the tool-calling brain.

Owns the loop that asks the LLM for tool calls, executes them via the
registry, feeds results back, and repeats until the model answers without
tools. The HTTP layer constructs an ``Agent`` and delegates to ``run``.
"""

import json
import logging
from dataclasses import dataclass, field

from app.llm.base import ChatMessage, LLMProvider, ToolCall
from app.tools.registry import ToolRegistry, registry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
LOOP_LIMIT_ANSWER = (
    f"Stopped after {MAX_TOOL_ROUNDS} tool rounds without a final answer. "
    "Try a more specific question."
)


@dataclass
class AgentResult:
    """Final answer plus the names of tools invoked."""

    answer: str
    invoked_tools: list[str] = field(default_factory=list)


class Agent:
    """Owns the tool loop. The HTTP layer just constructs and calls this."""

    def __init__(self, provider: LLMProvider, tools: ToolRegistry = registry) -> None:
        """Initialise with an LLM provider and a tool registry.

        Args:
            provider: the LLM provider to call.
            tools: registry of tools the model may call.

        """
        self.provider = provider
        self._tools = tools

    async def run(self, message: str) -> AgentResult:
        """Process one user message through the tool-calling loop.

        Args:
            message: the user's message.

        Returns:
            The final answer and the tools that were invoked. If the round cap
            is hit, the answer explains that instead of raising.

        """
        messages: list[ChatMessage] = [{"role": "user", "content": message}]
        invoked: list[str] = []
        for _ in range(MAX_TOOL_ROUNDS):
            response = await self.provider.chat(messages, self._tools.schemas())
            if not response.tool_calls:
                return AgentResult(answer=response.content, invoked_tools=invoked)
            messages.append(_assistant_message(response.content, response.tool_calls))
            for tool_call in response.tool_calls:
                invoked.append(tool_call.name)
                messages.append(await self._execute_tool(tool_call))
        logger.warning("tool loop hit %d rounds", MAX_TOOL_ROUNDS)
        return AgentResult(answer=LOOP_LIMIT_ANSWER, invoked_tools=invoked)

    async def _execute_tool(self, tool_call: ToolCall) -> ChatMessage:
        """Execute one tool call and build the tool-result message.

        Tool failures are returned to the model as an error payload so it can
        recover (e.g. try another path) instead of aborting the loop.

        Args:
            tool_call: the model's requested tool call.

        Returns:
            The ``tool`` role message carrying the JSON result or error.

        """
        try:
            result = await self._tools.execute(tool_call.name, tool_call.arguments)
            content = json.dumps(result)
        except Exception as exc:  # noqa: BLE001 — surface tool failure to the LLM
            logger.warning("tool %s failed: %s", tool_call.name, exc)
            content = json.dumps({"error": str(exc)})
        message: ChatMessage = {"role": "tool", "content": content, "tool_name": tool_call.name}
        if tool_call.id:
            message["tool_call_id"] = tool_call.id
        return message


def _assistant_message(content: str, tool_calls: list[ToolCall]) -> ChatMessage:
    """Build the assistant message that records the model's tool calls.

    Arguments stay as dicts: Ollama rejects JSON-string arguments in history.

    Args:
        content: any text the model returned alongside the calls.
        tool_calls: the calls the model requested.

    Returns:
        An ``assistant`` role message with all tool calls attached.

    """
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
                **({"id": call.id} if call.id else {}),
            }
            for call in tool_calls
        ],
    }
