"""HTTP layer tests with the agent dependency overridden (no Ollama needed)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_agent
from app.api.errors import REQUEST_ID_HEADER
from app.core.agent import Agent
from app.llm.base import LLMResponse
from app.llm.errors import OllamaConnectionError
from app.main import app
from tests.conftest import FakeProvider


class DownProvider(FakeProvider):
    """Provider whose health check always fails."""

    async def health_check(self) -> float:
        """Simulate an unreachable Ollama."""
        raise OllamaConnectionError("http://ollama.test", "refused")


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Test client whose agent answers 'pong' without any tools."""
    agent = Agent(FakeProvider([LLMResponse(content="pong")]))
    app.dependency_overrides[get_agent] = lambda: agent
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_chat(client: TestClient) -> None:
    resp = client.post("/chat", json={"message": "ping"})
    assert resp.status_code == 200
    assert resp.json() == {"response": "pong", "tool_calls": []}


def test_request_id_echoed(client: TestClient) -> None:
    resp = client.post("/chat", json={"message": "ping"}, headers={REQUEST_ID_HEADER: "abc"})
    assert resp.headers[REQUEST_ID_HEADER] == "abc"


def test_validation_error_shape(client: TestClient) -> None:
    resp = client.post("/chat", json={"message": ""})
    body = resp.json()
    assert resp.status_code == 422
    assert body["error"] == "validation_error"
    assert body["request_id"] == resp.headers[REQUEST_ID_HEADER]


def test_health_ok(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model"] == "fake"


def test_health_degraded() -> None:
    app.dependency_overrides[get_agent] = lambda: Agent(DownProvider([]))
    try:
        body = TestClient(app).get("/health").json()
    finally:
        app.dependency_overrides.clear()
    assert body["status"] == "degraded"
    assert body["ollama"] == "unreachable"
