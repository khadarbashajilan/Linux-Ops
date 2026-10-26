"""Request and response bodies for the HTTP API."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Payload for POST /chat."""

    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    """Response for POST /chat."""

    response: str
    tool_calls: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: Literal["ok", "degraded"]
    ollama: Literal["connected", "unreachable"]
    ollama_latency_ms: float | None = None
    model: str


class ErrorResponse(BaseModel):
    """Shape of every error response from the API."""

    error: str = Field(..., description="Short machine-readable error code.")
    detail: str = Field(..., description="Human-readable message.")
    request_id: str | None = Field(default=None, description="Correlates to server logs.")
