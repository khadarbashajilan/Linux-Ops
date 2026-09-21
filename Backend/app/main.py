"""FastAPI application entrypoint.

Serves ``GET /health`` and ``POST /chat``. The chat endpoint runs a minimal
tool-calling loop: ask the LLM, execute any requested tools via the registry,
feed results back, and return the final answer.
"""

import json
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.llm.base import LLMResponse, ProviderError, ToolCall
from app.llm.router import LLMRouter
from app.tools import file_tools  # noqa: F401 — registers tools on import
from app.tools.registry import registry

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5

app = FastAPI(title="LinuxOps Backend", version="0.1.0")
router = LLMRouter()


class ChatRequest(BaseModel):
    """Payload for POST /chat."""

    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    """Response for POST /chat."""

    response: str
    tool_calls: list[str] = Field(default_factory=list)


@app.get("/health")
async def health() -> dict:
    """Return service health status."""
    return {"status": "ok", "tiers": router.active_tiers}


async def _run_tool(tool_call: ToolCall, messages: list[dict]) -> None:
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


async def _agent_loop(messages: list[dict]) -> tuple[str, list[str]]:
    """Run the tool-calling loop until the model answers without tools.

    Args:
        messages: OpenAI-style conversation history (mutated in place).

    Returns:
        Final answer text and the list of tools invoked.

    Raises:
        ProviderError: if all LLM tiers fail.

    """
    invoked: list[str] = []
    for _ in range(MAX_TOOL_ROUNDS):
        response: LLMResponse = await router.chat(messages, registry.schemas())
        if not response.tool_calls:
            return response.content or "", invoked
        for tool_call in response.tool_calls:
            invoked.append(tool_call.name)
            await _run_tool(tool_call, messages)
    raise ProviderError(f"tool loop exceeded {MAX_TOOL_ROUNDS} rounds")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a single user message through the agent loop.

    Args:
        request: the chat request payload.

    Returns:
        The final answer and the tools that were invoked.

    """
    messages: list[dict] = [{"role": "user", "content": request.message}]
    try:
        answer, invoked = await _agent_loop(messages)
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(response=answer, tool_calls=invoked)
