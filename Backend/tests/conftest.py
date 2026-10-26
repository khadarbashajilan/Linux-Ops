"""Shared pytest fixtures: async backend, isolated settings, fake LLM provider."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.llm.base import ChatMessage, LLMResponse, ToolSchema

UseHome = Callable[..., Settings]


def isolated_settings(**overrides: Any) -> Settings:
    """Build settings that ignore ``Backend/.env``."""
    return Settings(_env_file=None, **overrides)


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio only."""
    return "asyncio"


@pytest.fixture
def use_home(monkeypatch: pytest.MonkeyPatch) -> UseHome:
    """Return ``apply(home, **overrides)``: set HOME and install matching settings.

    The settings are built after HOME changes, so ``~``-based scope rules point
    at the fake home, and file tools are patched to use them.
    """

    def apply(home: Path, **overrides: Any) -> Settings:
        monkeypatch.setenv("HOME", str(home))
        settings = isolated_settings(**overrides)
        monkeypatch.setattr("app.tools.file_tools.get_settings", lambda: settings)
        return settings

    return apply


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, use_home: UseHome) -> Path:
    """Use a fake home and a separate fake cwd, both under ``tmp_path``.

    Returns:
        The fake home directory.

    """
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.chdir(work)
    use_home(home)
    return home


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
