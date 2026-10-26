"""CLI commands against a mocked backend transport."""

from collections.abc import Callable

import httpx
import pytest
from typer.testing import CliRunner

from linuxops import cli
from linuxops.client import LinuxOpsClient

runner = CliRunner()
Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], None]:
    """Return a setter that routes the CLI's HTTP calls to a handler."""

    def use(handler: Handler) -> None:
        monkeypatch.setattr(
            cli,
            "_client",
            lambda server: LinuxOpsClient("http://test", transport=httpx.MockTransport(handler)),
        )

    return use


def test_chat_shows_answer_and_tools(backend: Callable[[Handler], None]) -> None:
    backend(lambda _: httpx.Response(200, json={"response": "3 files", "tool_calls": ["list_dir"]}))
    result = runner.invoke(cli.app, ["chat", "what's here?"])
    assert result.exit_code == 0
    assert "3 files" in result.output
    assert "list_dir" in result.output


def test_chat_backend_error_exits_1(backend: Callable[[Handler], None]) -> None:
    backend(lambda _: httpx.Response(503, json={"detail": "Ollama not reachable"}))
    result = runner.invoke(cli.app, ["chat", "hi"])
    assert result.exit_code == 1
    assert "Ollama not reachable" in result.output


def test_unreachable_backend_hint(backend: Callable[[Handler], None]) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    backend(refuse)
    result = runner.invoke(cli.app, ["health"])
    assert result.exit_code == 1
    assert "unreachable" in result.output


def test_health_table(backend: Callable[[Handler], None]) -> None:
    payload = {"status": "ok", "ollama": "connected", "ollama_latency_ms": 2.5, "model": "qwen3:4b"}
    backend(lambda _: httpx.Response(200, json=payload))
    result = runner.invoke(cli.app, ["health"])
    assert result.exit_code == 0
    assert "qwen3:4b" in result.output
