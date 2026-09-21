"""Application configuration loaded from environment and .env.

Central settings object for LinuxOps backend. Secrets are held as
pydantic.SecretStr and never logged or echoed in errors.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the backend.

    Reads from environment variables, falling back to the Backend/.env
    file (git-ignored). Model IDs default to the locked 3-tier chain.
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")

    groq_model: str = "openai/gpt-oss-20b"
    openrouter_model: str = "openrouter/free"
    gemini_model: str = "gemini-3.5-flash"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
