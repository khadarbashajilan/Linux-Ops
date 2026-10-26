"""HTTP routes: ``GET /health`` and ``POST /chat``."""

from fastapi import APIRouter, status

from app.api.deps import AgentDep
from app.api.schemas import ChatRequest, ChatResponse, ErrorResponse, HealthResponse
from app.llm.errors import OllamaConnectionError, OllamaResponseError

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(agent: AgentDep) -> HealthResponse:
    """Report service health and Ollama reachability (no model inference).

    ``degraded`` means FastAPI is up but Ollama is not, so chat will fail.
    """
    model = agent.provider.model
    try:
        latency_ms = await agent.provider.health_check()
    except OllamaConnectionError, OllamaResponseError:
        return HealthResponse(status="degraded", ollama="unreachable", model=model)
    return HealthResponse(
        status="ok", ollama="connected", ollama_latency_ms=round(latency_ms, 1), model=model
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def chat(request: ChatRequest, agent: AgentDep) -> ChatResponse:
    """Process one user message through the agent loop.

    Args:
        request: the chat request payload.
        agent: the agent built at startup.

    Returns:
        The final answer and the names of tools that were invoked.

    """
    result = await agent.run(request.message)
    return ChatResponse(response=result.answer, tool_calls=result.invoked_tools)
