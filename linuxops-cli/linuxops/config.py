"""CLI configuration: ``~/.linuxops/config.toml`` with environment overrides.

Precedence for every setting: command-line flag > environment variable >
config file > built-in default.
"""

import os
import tomllib
from pathlib import Path

import tomli_w

CONFIG_DIR = Path.home() / ".linuxops"
CONFIG_PATH = CONFIG_DIR / "config.toml"
DEFAULT_SERVER_URL = "http://localhost:8000"

SERVER_URL_ENV = "LINUXOPS_SERVER_URL"
API_TOKEN_ENV = "LINUXOPS_API_TOKEN"


def load_config() -> dict[str, str]:
    """Load the config file.

    Returns:
        The stored settings, or an empty dict if the file does not exist.

    """
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("rb") as fh:
        return {k: str(v) for k, v in tomllib.load(fh).items()}


def save_config_value(key: str, value: str) -> None:
    """Persist one setting, keeping the file readable by the owner only.

    Args:
        key: setting name (``server_url`` or ``api_token``).
        value: value to store.

    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config()
    config[key] = value
    CONFIG_PATH.write_bytes(tomli_w.dumps(config).encode())
    CONFIG_PATH.chmod(0o600)


def resolve_server_url(override: str | None = None) -> str:
    """Return the backend URL from flag, env, config file, or default."""
    return (
        override
        or os.environ.get(SERVER_URL_ENV)
        or load_config().get("server_url")
        or DEFAULT_SERVER_URL
    )


def resolve_api_token() -> str | None:
    """Return the API token from env or config file, if any is set."""
    return os.environ.get(API_TOKEN_ENV) or load_config().get("api_token") or None


def mask_token(token: str | None) -> str:
    """Return a display-safe version of a token."""
    if not token:
        return "[not set]"
    return f"{token[:4]}…" if len(token) > 8 else "****"
