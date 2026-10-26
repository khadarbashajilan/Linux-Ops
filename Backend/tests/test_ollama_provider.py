"""Ollama provider tests against a mocked HTTP transport (no real Ollama)."""

from collections.abc import Callable

import httpx
import pytest

from app.llm.errors import OllamaConnectionError, OllamaResponseError
from app.llm.ollama_provider import OllamaProvider
from tests.conftest import isolated_settings

pytestmark = pytest.mark.anyio

Handler = Callable[[httpx.Request], httpx.Response]


def _provider(handler: Handler, retries: int = 2) -> OllamaProvider:
    provider = OllamaProvider(isolated_settings(ollama_max_retries=retries))
    provider._client = httpx.AsyncClient(
        base_url="http://ollama.test", transport=httpx.MockTransport(handler)
    )
    return provider


def _recording(respond: Callable[[int], httpx.Response]) -> tuple[Handler, list[httpx.Request]]:
    """Build a handler that records each request and answers via ``respond(attempt)``."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return respond(len(seen))

    return handler, seen


def _ok(tool_args: object = None) -> httpx.Response:
    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "list_dir", "arguments": tool_args or {}}}],
    }
    return httpx.Response(200, json={"message": message})


@pytest.mark.parametrize("raw", [{"path": "."}, '{"path": "."}'])
async def test_parses_tool_arguments(raw: object) -> None:
    response = await _provider(lambda _: _ok(raw)).chat([], [])
    (call,) = response.tool_calls
    assert call.name == "list_dir"
    assert call.arguments == {"path": "."}


async def test_retries_transient_5xx() -> None:
    handler, seen = _recording(lambda n: httpx.Response(503) if n == 1 else _ok())
    await _provider(handler).chat([], [])
    assert len(seen) == 2


async def test_does_not_retry_client_errors() -> None:
    handler, seen = _recording(lambda _: httpx.Response(400, text="bad request"))
    with pytest.raises(OllamaResponseError):
        await _provider(handler).chat([], [])
    assert len(seen) == 1


async def test_connection_error_after_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(OllamaConnectionError):
        await _provider(handler, retries=1).chat([], [])


async def test_health_check_uses_version_endpoint() -> None:
    handler, seen = _recording(lambda _: httpx.Response(200, json={"version": "0.0.0"}))
    assert await _provider(handler).health_check() >= 0
    assert [r.url.path for r in seen] == ["/api/version"]


async def test_health_check_error_status() -> None:
    handler, _ = _recording(lambda _: httpx.Response(500, text="boom"))
    with pytest.raises(OllamaResponseError):
        await _provider(handler).health_check()
