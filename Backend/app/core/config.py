"""Application configuration loaded from environment and .env.

Central settings object for the LinuxOps backend, including the filesystem
scope model: a hard-deny list that always wins, plus per-capability
allowlists (read, write, exec).
"""

import os
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_SEEDED_DENY: tuple[str, ...] = (
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.config/gh",
    "~/.config/git-credential-manager",
    "/etc",
    "/boot",
    "/sys",
    "/proc",
)


def _unique(paths: Iterable[Path]) -> tuple[Path, ...]:
    """Return paths with duplicates removed, preserving first-seen order."""
    return tuple(dict.fromkeys(paths))


def _resolve(raw: str) -> Path:
    """Expand ``~`` and resolve symlinks so comparisons use real paths."""
    return Path(raw).expanduser().resolve()


class Settings(BaseSettings):
    """Runtime configuration for the backend.

    Reads from environment variables, falling back to ``Backend/.env``
    (git-ignored). Ollama is the sole LLM provider.
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_connect: int = 60
    ollama_timeout_read: int = 120
    ollama_max_retries: int = 3

    # Extra scope on top of the implicit per-capability defaults. The deny list
    # is additive only, so a typo here can never expose a seeded path.
    linuxops_allowed_paths: str = ""
    linuxops_denied_paths: str = ""

    def _parse_paths(self, raw: str) -> tuple[Path, ...]:
        """Parse a ``:`` or ``,`` separated path list into resolved Paths."""
        entries = raw.replace(os.pathsep, ",").split(",")
        return tuple(_resolve(e.strip()) for e in entries if e.strip())

    def _with_extras(self, *implicit: Path) -> tuple[Path, ...]:
        """Combine implicit bases with ``LINUXOPS_ALLOWED_PATHS`` extras."""
        return _unique((*implicit, *self._parse_paths(self.linuxops_allowed_paths)))

    @property
    def allowed_bases(self) -> tuple[Path, ...]:
        """Read scope: ``~``, server cwd, plus extras."""
        return self._with_extras(Path.home().resolve(), Path.cwd().resolve())

    @property
    def write_allowed_bases(self) -> tuple[Path, ...]:
        """Write scope: server cwd and ``/tmp`` plus extras. ``~`` is not included."""
        return self._with_extras(Path.cwd().resolve(), _resolve("/tmp"))

    @property
    def exec_allowed_bases(self) -> tuple[Path, ...]:
        """Exec scope: server cwd plus extras. Tightest of the three."""
        return self._with_extras(Path.cwd().resolve())

    @property
    def denied_bases(self) -> tuple[Path, ...]:
        """Hard-deny list — always wins over every allowlist.

        Seeded paths are resolved too, so a symlinked home directory cannot
        sidestep the check.
        """
        seeded = (_resolve(p) for p in _SEEDED_DENY)
        return _unique((*seeded, *self._parse_paths(self.linuxops_denied_paths)))


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
