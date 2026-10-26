"""FastAPI dependencies shared by the routes."""

from typing import Annotated

from fastapi import Depends, Request

from app.core.agent import Agent


def get_agent(request: Request) -> Agent:
    """Return the agent built during application startup."""
    return request.app.state.agent


AgentDep = Annotated[Agent, Depends(get_agent)]
