"""CLI configuration management."""

import os
from pathlib import Path
import toml

CONFIG_DIR = Path.home() / ".linuxops"
CONFIG_PATH = CONFIG_DIR / "config.toml"


def ensure_config_dir() -> None:
    """Create the config directory if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_config() -> dict:
    """Load config from ~/.linuxops/config.toml.

    Returns:
        Config dict with server_url, api_token, etc.
    """
    if not CONFIG_PATH.exists():
        return {
            "server_url": "http://localhost:8000",
            "api_token": "",
        }
    with open(CONFIG_PATH) as f:
        return toml.load(f)


def set_config_value(key: str, value: str) -> None:
    """Set a config value and save to disk.

    Args:
        key: Config key (e.g., 'server_url', 'api_token').
        value: Value to set.
    """
    ensure_config_dir()
    cfg = get_config()
    cfg[key] = value
    with open(CONFIG_PATH, "w") as f:
        toml.dump(cfg, f)


def get_server_url() -> str:
    """Get the backend server URL from config or environment.

    Returns:
        Server URL string.
    """
    # Environment variable takes precedence
    env_url = os.environ.get("LINUXOPS_SERVER_URL")
    if env_url:
        return env_url
    cfg = get_config()
    return cfg.get("server_url", "http://localhost:8000")


def get_api_token() -> str | None:
    """Get the API token from config or environment.

    Returns:
        API token string or None.
    """
    # Environment variable takes precedence
    env_token = os.environ.get("LINUXOPS_API_TOKEN")
    if env_token:
        return env_token
    cfg = get_config()
    token = cfg.get("api_token", "")
    return token if token else None
