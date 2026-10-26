"""Ollama provider tests against a mocked HTTP transport (no real Ollama)."""

from collections.abc import Callable

import httpx
import pytest

from app.core.config import Settings
from app.llm.errors import OllamaConnectionError, OllamaResponseError
from app.llm.ollama_provider import OllamaProvider

pytestmark = pytest.mark.anyio

Handler = Callable[[httpx.Request], httpx.Response]


def _provider(handler: Handler, retries: int = 2) -> OllamaProvider:
    settings = Settings(_env_file=None, ollama_max_retries=retries)
    provider = OllamaProvider(settings)
    provider._client = httpx.AsyncClient(
        base_url="http://ollama.test", transport=httpx.MockTransport(handler)
    )
    return provider


def _ok(tool_args: object) -> httpx.Response:
    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "list_dir", "arguments": tool_args}}],
    }
    return httpx.Response(200, json={"message": message})


@pytest.mark.parametrize("raw", [{"path": "."}, '{"path": "."}'])
async def test_parses_tool_arguments(raw: object) -> None:
    response = await _provider(lambda _: _ok(raw)).chat([], [])
    (call,) = response.tool_calls
    assert call.name == "list_dir"
    assert call.arguments == {"path": "."}


async def test_retries_transient_5xx() -> None:
    attempts: list[int] = []

    def handler(_: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503) if len(attempts) == 1 else _ok({})

    await _provider(handler).chat([], [])
    assert len(attempts) == 2


async def test_does_not_retry_client_errors() -> None:
    attempts: list[int] = []

    def handler(_: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(400, text="bad request")

    with pytest.raises(OllamaResponseError):
        await _provider(handler).chat([], [])
    assert len(attempts) == 1


async def test_connection_error_after_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(OllamaConnectionError):
        await _provider(handler, retries=1).chat([], [])


async def test_health_check_uses_version_endpoint() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"version": "0.0.0"})

    assert await _provider(handler).health_check() >= 0
    assert paths == ["/api/version"]
