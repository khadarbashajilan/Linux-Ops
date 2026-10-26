"""Shared pytest fixtures: async backend, isolated settings, fake LLM provider."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config import Settings
from app.llm.base import ChatMessage, LLMResponse, ToolSchema


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio only."""
    return "asyncio"


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point HOME and cwd at temp dirs and use settings that ignore ``.env``.

    Yields:
        The fake home directory.

    """
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    settings = Settings(_env_file=None)
    monkeypatch.setattr("app.tools.file_tools.get_settings", lambda: settings)
    yield home


class FakeProvider:
    """Scripted LLM provider that records every message list it receives."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        """Queue the responses returned by successive ``chat`` calls."""
        self._responses = list(responses)
        self.calls: list[list[ChatMessage]] = []

    @property
    def model(self) -> str:
        """Return a fixed fake model name."""
        return "fake"

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSchema]) -> LLMResponse:
        """Record the history and return the next scripted response."""
        self.calls.append([dict(m) for m in messages])  # type: ignore[misc]
        return self._responses.pop(0)

    async def health_check(self) -> float:
        """Report a fixed latency."""
        return 1.0

    async def aclose(self) -> None:
        """Nothing to close."""
