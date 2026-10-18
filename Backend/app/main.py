"""FastAPI application entrypoint — thin HTTP shell.

Constructs the agent and exposes it behind ``GET /health`` and ``POST /chat``.
All agent logic lives in ``app.core.agent``; this file only shapes HTTP.
"""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from app.core.agent import Agent, AgentResult
from app.core.exceptions import (
    ErrorResponse,
    OllamaConnectionError,
    OllamaResponseError,
)
from app.llm.base import ProviderError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_agent: Agent | None = None


def _request_id(request: Request) -> str:
    """Extract or generate a request ID for correlation."""
    return request.headers.get("X-Request-ID", str(uuid.uuid4()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify Ollama connectivity on startup; run in degraded mode if unreachable."""
    global _agent
    _agent = Agent()
    try:
        is_healthy, latency_ms = await _agent._router.health_check()
        logger.info("Ollama health check passed — latency=%.1fms", latency_ms)
    except OllamaConnectionError as exc:
        logger.warning(
            "Ollama unreachable on startup — chat will return 503: %s",
            exc,
        )
    except Exception as exc:
        logger.warning("Ollama health check failed unexpectedly: %s", exc)
    yield
    _agent = None


app = FastAPI(
    title="LinuxOps Backend",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Handle Pydantic validation errors from request bodies."""
    rid = _request_id(request)
    logger.warning("request_id=%s validation_error: %s", rid, exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error="validation_error",
            detail=exc.errors()[0].get("msg", str(exc)) if exc.errors() else str(exc),
            request_id=rid,
        ).model_dump(),
    )


@app.exception_handler(OllamaConnectionError)
async def ollama_connection_handler(request: Request, exc: OllamaConnectionError) -> JSONResponse:
    """Handle Ollama being unreachable."""
    rid = _request_id(request)
    logger.warning("request_id=%s ollama_unreachable: %s", rid, exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=ErrorResponse(
            error="ollama_unreachable",
            detail=str(exc),
            request_id=rid,
        ).model_dump(),
    )


@app.exception_handler(OllamaResponseError)
async def ollama_response_handler(request: Request, exc: OllamaResponseError) -> JSONResponse:
    """Handle Ollama returning a non-200 or malformed response."""
    rid = _request_id(request)
    logger.warning("request_id=%s ollama_bad_response: %s", rid, exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=ErrorResponse(
            error="ollama_bad_response",
            detail=str(exc),
            request_id=rid,
        ).model_dump(),
    )


@app.exception_handler(ProviderError)
async def provider_error_handler(request: Request, exc: ProviderError) -> JSONResponse:
    """Handle LLM provider errors (upstream model failures)."""
    rid = _request_id(request)
    logger.warning("request_id=%s llm_error: %s", rid, exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=ErrorResponse(
            error="llm_unavailable",
            detail=str(exc),
            request_id=rid,
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all — log full traceback, return a generic error to the client."""
    rid = _request_id(request)
    logger.exception("request_id=%s unhandled_exception: %s", rid, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="internal_error",
            detail="An unexpected error occurred. If the problem persists, check server logs.",
            request_id=rid,
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Payload for POST /chat."""

    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    """Response for POST /chat."""

    response: str
    tool_calls: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str = Field(..., description="'ok', 'degraded', or 'unhealthy'")
    ollama: str = Field(..., description="'connected' or 'unreachable'")
    ollama_latency_ms: float | None = Field(default=None, description="Ollama ping latency in ms")
    providers: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return service health with Ollama connectivity detail.

    Three possible states:
    - ok            — FastAPI + Ollama both healthy
    - degraded      — FastAPI up but Ollama unreachable (chat will 503)
    - unhealthy     — FastAPI itself failed to initialise

    """
    if _agent is None:
        return HealthResponse(
            status="unhealthy",
            ollama="unknown",
            ollama_latency_ms=None,
            providers=[],
        )
    try:
        is_healthy, latency_ms = await _agent._router.health_check()
    except OllamaConnectionError:
        return HealthResponse(
            status="degraded",
            ollama="unreachable",
            ollama_latency_ms=None,
            providers=_agent.active_tiers,
        )
    return HealthResponse(
        status="ok" if is_healthy else "degraded",
        ollama="connected" if is_healthy else "unreachable",
        ollama_latency_ms=round(latency_ms, 1),
        providers=_agent.active_tiers,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a single user message through the agent loop.

    Args:
        request: the chat request payload.

    Returns:
        The final answer and the tools that were invoked.

    Raises:
        OllamaConnectionError: 503 — Ollama not reachable.
        OllamaResponseError: 502 — Ollama returned an error or unexpected response.
        ProviderError: 503 — LLM call failed after retries.

    """
    if _agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="agent not initialised — check server startup logs",
        )
    result: AgentResult = await _agent.run(request.message)
    return ChatResponse(response=result.answer, tool_calls=result.invoked_tools)
