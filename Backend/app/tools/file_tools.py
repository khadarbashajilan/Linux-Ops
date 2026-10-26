"""File tools: list_dir, read_file.

All file tools share a three-layer scope check, in order:

1. **Hard deny** — ``Settings.denied_bases`` (``~/.ssh``, ``~/.aws``,
   ``~/.gnupg``, ``~/.config/gh``, ``/etc``, ``/boot``, ``/sys``, ``/proc`` plus
   ``LINUXOPS_DENIED_PATHS``) and any ``.env*`` filename are always rejected.
2. **Capability allowlist** — read tools check ``allowed_bases`` (home + cwd +
   extras). Write tools return in the permission-gate phase with the tighter
   ``write_allowed_bases``.
3. **Realpath** — symlinks are resolved before either check, so a link inside
   an allowed base that points at ``~/.ssh`` is still denied.
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.tools.registry import registry

_SECRET_ENV_FILE_RE = re.compile(r"^\.env($|\.)")


def _check_scope(raw: Path, allowed: tuple[Path, ...]) -> Path:
    """Resolve a path and apply the deny-then-allow scope check.

    Args:
        raw: the user/model-supplied path.
        allowed: the capability-specific allowlist.

    Returns:
        The resolved, in-scope absolute path.

    Raises:
        PermissionError: if the path is denied, is a ``.env*`` file, or lies
            outside the allowlist.

    """
    candidate = raw.expanduser().resolve()

    if any(_is_within(candidate, base) for base in get_settings().denied_bases):
        raise PermissionError(f"path denied by hard policy: {candidate}")
    if _SECRET_ENV_FILE_RE.match(candidate.name):
        raise PermissionError(f"path denied by hard policy (.env*): {candidate}")
    if not any(_is_within(candidate, base) for base in allowed):
        listed = ", ".join(str(b) for b in allowed) or "<empty>"
        raise PermissionError(f"path outside allowlist ({listed}): {candidate}")
    return candidate


def _is_within(path: Path, base: Path) -> bool:
    """Return True if ``path`` is ``base`` or lies beneath it."""
    return path == base or base in path.parents


class ListDirArgs(BaseModel):
    """Arguments for list_dir."""

    path: str = Field(..., description="Directory path to list (inside an allowlisted base)")


class ReadFileArgs(BaseModel):
    """Arguments for read_file."""

    path: str = Field(..., description="File path to read (must be inside an allowlisted base)")
    max_bytes: int = Field(default=65536, ge=1, le=1_048_576)


@registry.tool(
    risk="safe",
    description="List entries in a directory. Returns name, type, and size for each entry.",
)
async def list_dir(args: ListDirArgs) -> dict[str, Any]:
    """List a directory's entries, directories first.

    Args:
        args: the validated tool arguments.

    Returns:
        A dict with the resolved path, entry descriptors, and entry count.

    Raises:
        PermissionError: if the path is out of scope.

    """
    target = _check_scope(Path(args.path), get_settings().allowed_bases)

    def _scan() -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        with os.scandir(target) as it:
            for entry in it:
                try:
                    size: int | None = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    size = None
                kind = "dir" if entry.is_dir() else "file"
                entries.append({"name": entry.name, "type": kind, "size": size})
        return sorted(entries, key=lambda e: (e["type"] != "dir", e["name"]))

    entries = await asyncio.to_thread(_scan)
    return {"path": str(target), "entries": entries, "count": len(entries)}


@registry.tool(
    risk="safe",
    description="Read the text content of a file, capped at max_bytes.",
)
async def read_file(args: ReadFileArgs) -> dict[str, Any]:
    """Read up to ``max_bytes`` of a regular file without loading the rest.

    Args:
        args: the validated tool arguments.

    Returns:
        A dict with content, bytes returned, and whether the file was truncated.

    Raises:
        PermissionError: if the path is out of scope.
        FileNotFoundError: if the path is not a regular file.

    """
    target = _check_scope(Path(args.path), get_settings().allowed_bases)
    if not target.is_file():
        raise FileNotFoundError(f"not a regular file: {target}")

    def _read() -> bytes:
        with target.open("rb") as fh:
            return fh.read(args.max_bytes + 1)

    data = await asyncio.to_thread(_read)
    truncated = len(data) > args.max_bytes
    data = data[: args.max_bytes]
    return {
        "path": str(target),
        "content": data.decode("utf-8", errors="replace"),
        "size": len(data),
        "truncated": truncated,
    }
