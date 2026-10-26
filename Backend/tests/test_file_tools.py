"""Filesystem scope tests: hard deny, .env*, allowlist, symlinks, read limits."""

from pathlib import Path

import pytest

from app.tools.file_tools import ListDirArgs, ReadFileArgs, list_dir, read_file
from tests.conftest import UseHome, isolated_settings

pytestmark = pytest.mark.anyio


async def test_reads_file_in_home(sandbox: Path) -> None:
    (sandbox / "notes.txt").write_text("hello")
    result = await read_file(ReadFileArgs(path="~/notes.txt"))
    assert result["content"] == "hello"
    assert result["truncated"] is False


async def test_lists_cwd_dirs_first(sandbox: Path) -> None:
    Path("b.txt").write_text("x")
    Path("a_dir").mkdir()
    result = await list_dir(ListDirArgs(path="."))
    assert [e["name"] for e in result["entries"]] == ["a_dir", "b.txt"]


@pytest.mark.parametrize("path", ["~/.ssh/id_rsa", "~/.aws/credentials", "/etc/passwd", "/proc"])
async def test_hard_deny(sandbox: Path, path: str) -> None:
    (sandbox / ".ssh").mkdir()
    (sandbox / ".ssh" / "id_rsa").write_text("secret")
    with pytest.raises(PermissionError, match="hard policy"):
        await read_file(ReadFileArgs(path=path))


@pytest.mark.parametrize("name", [".env", ".env.local", ".env.production"])
async def test_env_files_denied(sandbox: Path, name: str) -> None:
    (sandbox / name).write_text("KEY=1")
    with pytest.raises(PermissionError, match=r"\.env"):
        await read_file(ReadFileArgs(path=f"~/{name}"))


async def test_outside_allowlist_denied(sandbox: Path) -> None:
    with pytest.raises(PermissionError, match="outside allowlist"):
        await list_dir(ListDirArgs(path="/usr"))


async def test_symlink_into_denied_path(sandbox: Path) -> None:
    (sandbox / ".ssh").mkdir()
    (sandbox / ".ssh" / "id_rsa").write_text("secret")
    (sandbox / "innocent").symlink_to(sandbox / ".ssh" / "id_rsa")
    with pytest.raises(PermissionError, match="hard policy"):
        await read_file(ReadFileArgs(path="~/innocent"))


async def test_traversal_resolved(sandbox: Path) -> None:
    with pytest.raises(PermissionError):
        await read_file(ReadFileArgs(path="~/../../../../etc/passwd"))


async def test_symlinked_home_cannot_bypass_deny(tmp_path: Path, use_home: UseHome) -> None:
    real_home = tmp_path / "real_home"
    (real_home / ".ssh").mkdir(parents=True)
    (real_home / ".ssh" / "id_rsa").write_text("secret")
    link_home = tmp_path / "link_home"
    link_home.symlink_to(real_home)
    use_home(link_home)
    with pytest.raises(PermissionError, match="hard policy"):
        await read_file(ReadFileArgs(path="~/.ssh/id_rsa"))


async def test_exact_size_not_truncated(sandbox: Path) -> None:
    (sandbox / "f").write_bytes(b"x" * 10)
    result = await read_file(ReadFileArgs(path="~/f", max_bytes=10))
    assert result["size"] == 10
    assert result["truncated"] is False


async def test_larger_file_truncated(sandbox: Path) -> None:
    (sandbox / "f").write_bytes(b"x" * 11)
    result = await read_file(ReadFileArgs(path="~/f", max_bytes=10))
    assert result["size"] == 10
    assert result["truncated"] is True


async def test_directory_is_not_a_file(sandbox: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await read_file(ReadFileArgs(path="~"))


def test_denied_paths_are_additive(tmp_path: Path, use_home: UseHome) -> None:
    settings = use_home(tmp_path, linuxops_denied_paths=str(tmp_path / "private"))
    assert (tmp_path / "private").resolve() in settings.denied_bases
    assert Path("/etc").resolve() in settings.denied_bases


def test_home_not_in_write_scope(sandbox: Path) -> None:
    settings = isolated_settings()
    assert sandbox.resolve() not in settings.write_allowed_bases
