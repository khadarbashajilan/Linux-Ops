"""FastAPI application entrypoint.

Wires the pieces together: builds the Ollama provider and agent at startup,
installs error handling, and mounts the routes. No logic lives here.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import install_error_handling
from app.api.routes import router
from app.core.agent import Agent
from app.llm.errors import OllamaConnectionError, OllamaResponseError
from app.llm.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the agent, probe Ollama, and close the provider on shutdown."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    provider = OllamaProvider()
    app.state.agent = Agent(provider)
    try:
        latency_ms = await provider.health_check()
        logger.info("ollama reachable — latency=%.1fms", latency_ms)
    except (OllamaConnectionError, OllamaResponseError) as exc:
        logger.warning("ollama unreachable on startup — chat will fail until it is up: %s", exc)
    yield
    await provider.aclose()


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(title="LinuxOps Backend", version="0.1.0", lifespan=lifespan)
    install_error_handling(app)
    app.include_router(router)
    return app


app = create_app()
