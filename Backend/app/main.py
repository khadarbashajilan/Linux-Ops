"""FastAPI application entrypoint — thin HTTP shell.

Constructs the agent and exposes it behind ``GET /health`` and ``POST /chat``.
All agent logic lives in ``app.core.agent``; this file only shapes HTTP.
"""

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.core.agent import Agent, AgentResult
from app.llm.base import ProviderError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="LinuxOps Backend", version="0.1.0")
agent = Agent()


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
    return {"status": "ok", "tiers": agent.active_tiers}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a single user message through the agent loop.

    Args:
        request: the chat request payload.

    Returns:
        The final answer and the tools that were invoked.

    """
    try:
        result: AgentResult = await agent.run(request.message)
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(response=result.answer, tool_calls=result.invoked_tools)
