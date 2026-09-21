"""File tools: list_dir and read_file.

Both tools are scoped to an allowlist (~ and /tmp). Paths are resolved and
must stay inside an allowed base, blocking traversal like ``../etc/passwd``.
"""

import asyncio
import os
from pathlib import Path

from pydantic import BaseModel, Field

from app.tools.registry import registry

ALLOWED_BASES: tuple[Path, ...] = (Path.home(), Path("/tmp"))


def _resolve_within_allowlist(raw_path: str) -> Path:
    """Resolve a path and assert it lives inside the allowlist.

    Args:
        raw_path: user/model-supplied path (absolute or ~-relative).

    Returns:
        The resolved, allowlisted path.

    Raises:
        PermissionError: if the resolved path escapes the allowlist.

    """
    candidate = Path(raw_path).expanduser().resolve()
    if not any(candidate == base or base in candidate.parents for base in ALLOWED_BASES):
        allowed = ", ".join(str(b) for b in ALLOWED_BASES)
        raise PermissionError(f"path outside allowlist ({allowed}): {candidate}")
    return candidate


class ListDirArgs(BaseModel):
    """Arguments for list_dir."""

    path: str = Field(..., description="Directory path to list (~ or /tmp scoped)")


class ReadFileArgs(BaseModel):
    """Arguments for read_file."""

    path: str = Field(..., description="File path to read (~ or /tmp scoped)")
    max_bytes: int = Field(default=65536, ge=1, le=1_048_576)


@registry.tool(
    risk="safe",
    description="List entries in a directory. Returns name, type, and size for each entry.",
)
async def list_dir(args: ListDirArgs) -> dict:
    """List a directory's entries.

    Args:
        args: the validated tool arguments.

    Returns:
        A dict with the path and a list of entry descriptors.

    """
    target = _resolve_within_allowlist(args.path)

    def _scan() -> list[dict]:
        entries = []
        with os.scandir(target) as it:
            for entry in it:
                try:
                    stat = entry.stat(follow_symlinks=False)
                    size = stat.st_size
                except OSError:
                    size = None
                entries.append(
                    {
                        "name": entry.name,
                        "type": "dir" if entry.is_dir() else "file",
                        "size": size,
                    }
                )
        return sorted(entries, key=lambda e: (e["type"] != "dir", e["name"]))

    entries = await asyncio.to_thread(_scan)
    return {"path": str(target), "entries": entries, "count": len(entries)}


@registry.tool(
    risk="safe",
    description="Read the text content of a file, capped at max_bytes.",
)
async def read_file(args: ReadFileArgs) -> dict:
    """Read a file's text content.

    Args:
        args: the validated tool arguments.

    Returns:
        A dict with content, byte length, and a truncated flag.

    """
    target = _resolve_within_allowlist(args.path)
    if not target.is_file():
        raise FileNotFoundError(f"not a file: {target}")

    def _read() -> tuple[str, int]:
        data = target.read_bytes()[: args.max_bytes]
        return data.decode("utf-8", errors="replace"), len(data)

    content, size = await asyncio.to_thread(_read)
    truncated = size >= args.max_bytes
    return {
        "path": str(target),
        "content": content,
        "size": size,
        "truncated": truncated,
    }
