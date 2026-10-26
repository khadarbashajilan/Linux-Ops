"""Config precedence, persistence, and token masking."""

import stat
from pathlib import Path

import pytest

from linuxops import config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the config file into a temp dir and clear env overrides."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.delenv(config.SERVER_URL_ENV, raising=False)
    monkeypatch.delenv(config.API_TOKEN_ENV, raising=False)
    return tmp_path / "config.toml"


def test_default_server_url() -> None:
    assert config.resolve_server_url() == config.DEFAULT_SERVER_URL


def test_precedence_flag_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    config.save_config_value("server_url", "http://file")
    assert config.resolve_server_url() == "http://file"
    monkeypatch.setenv(config.SERVER_URL_ENV, "http://env")
    assert config.resolve_server_url() == "http://env"
    assert config.resolve_server_url("http://flag") == "http://flag"


def test_token_from_env_or_file(monkeypatch: pytest.MonkeyPatch) -> None:
    assert config.resolve_api_token() is None
    config.save_config_value("api_token", "file-token")
    assert config.resolve_api_token() == "file-token"
    monkeypatch.setenv(config.API_TOKEN_ENV, "env-token")
    assert config.resolve_api_token() == "env-token"


def test_config_file_owner_only(isolated_config: Path) -> None:
    config.save_config_value("api_token", "secret")
    assert stat.S_IMODE(isolated_config.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("token", "shown"),
    [(None, "[not set]"), ("short", "****"), ("abcdefghijkl", "abcd…")],
)
def test_mask_token(token: str | None, shown: str) -> None:
    assert config.mask_token(token) == shown
