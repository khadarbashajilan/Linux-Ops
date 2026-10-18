"""Application configuration loaded from environment and .env.

Central settings object for LinuxOps backend. Secrets are held as
pydantic.SecretStr and never logged or echoed in errors.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the backend.

    Reads from environment variables, falling back to the Backend/.env
    file (git-ignored). Ollama is used as the sole LLM provider.
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

    # Filesystem scope — split by capability so write/shell are tighter than read.
    # `linuxops_allowed_paths` is the **extra** allowlist on top of the implicit
    # home + cwd scope. `linuxops_denied_paths` is a hard deny that **always**
    # wins and is itself seeded with critical secret/system paths so a typo
    # in `.env` can never expose them.
    linuxops_allowed_paths: str = ""
    linuxops_denied_paths: str = ""

    def _parse_paths(self, raw: str) -> tuple[Path, ...]:
        """Parse a ``:/,/`` separated path list into resolved absolute Paths."""
        raw = raw.replace(os.pathsep, ",")
        out: list[Path] = []
        for entry in raw.split(","):
            entry = entry.strip()
            if entry:
                out.append(Path(entry).expanduser().resolve())
        return tuple(out)

    @property
    def allowed_bases(self) -> tuple[Path, ...]:
        """Default filesystem scope: ``~``, server cwd, plus any user extras.

        Used for **read-only** tools (list_dir, read_file). Write and exec
        tools have their own tighter scopes.
        """
        extras = self._parse_paths(self.linuxops_allowed_paths)
        implicit = (Path.home(), Path.cwd().resolve())
        # Preserve uniqueness, implicit first.
        seen: set[Path] = set()
        bases: list[Path] = []
        for b in (*implicit, *extras):
            if b not in seen:
                bases.append(b)
                seen.add(b)
        return tuple(bases)

    @property
    def denied_bases(self) -> tuple[Path, ...]:
        """Hard-deny list — always wins over allowlist, not env-overridable.

        Seeded with secrets + system mounts. Any path under any of these is
        rejected regardless of ``LINUXOPS_ALLOWED_PATHS``.
        """
        seeded: tuple[Path, ...] = (
            Path.home() / ".ssh",
            Path.home() / ".aws",
            Path.home() / ".gnupg",
            Path.home() / ".config" / "gh",
            Path.home() / ".config" / "git-credential-manager",
            Path("/etc"),
            Path("/boot"),
            Path("/sys"),
            Path("/proc"),
        )
        user_extra = self._parse_paths(self.linuxops_denied_paths)
        seen: set[Path] = set()
        out: list[Path] = []
        for b in (*seeded, *user_extra):
            if b not in seen:
                out.append(b)
                seen.add(b)
        return tuple(out)

    @property
    def write_allowed_bases(self) -> tuple[Path, ...]:
        """Write scope: cwd + /tmp only. ``~`` is NOT auto-included."""
        extras = self._parse_paths(self.linuxops_allowed_paths)
        implicit = (Path.cwd().resolve(), Path("/tmp"))
        seen: set[Path] = set()
        out: list[Path] = []
        for b in (*implicit, *extras):
            if b not in seen:
                out.append(b)
                seen.add(b)
        return tuple(out)

    @property
    def exec_allowed_bases(self) -> tuple[Path, ...]:
        """Exec (shell) scope: cwd only. Tightest of the three."""
        extras = self._parse_paths(self.linuxops_allowed_paths)
        implicit = (Path.cwd().resolve(),)
        seen: set[Path] = set()
        out: list[Path] = []
        for b in (*implicit, *extras):
            if b not in seen:
                out.append(b)
                seen.add(b)
        return tuple(out)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
