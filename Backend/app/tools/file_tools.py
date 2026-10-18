"""File tools: list_dir, read_file, write_file.

All file tools share a three-layer scope check, in order:

1. **Hard deny** — ``Settings.denied_bases`` is seeded with ``~/.ssh``,
   ``~/.aws``, ``~/.gnupg``, ``~/.config/gh``, ``/etc``, ``/boot``, ``/sys``,
   ``/proc``. Any path resolving under one of these is rejected with
   ``PermissionError``, regardless of ``LINUXOPS_ALLOWED_PATHS``. The user
   cannot widen past these via env vars.

2. **Capability allowlist** — read tools check against ``allowed_bases``
   (home + cwd + extras); write tools check against ``write_allowed_bases``
   (cwd + /tmp + extras). The home directory is **not** auto-included for
   writes.

3. **Realpath eval** — symlinks are resolved before either check, so a
   symlink inside an allowed base that points at ``~/.ssh`` is still denied.

This is the cheap, in-the-meantime safety floor. Phase 02 will layer the
risk classifier + audit log on top.
"""

import asyncio
import re
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.tools.registry import registry

_HIDDEN_FILE_RE = re.compile(r"^\.env($|\.)")


def _is_hidden_secret_file(path: Path) -> bool:
    """True if the filename looks like a secret env file (``.env``, ``.env.*``)."""
    return bool(_HIDDEN_FILE_RE.match(path.name))


def _check_scope(raw: Path, allowed: tuple[Path, ...]) -> Path:
    """Resolve + apply deny-then-allow scope check against an allow tuple.

    Args:
        raw: the user/model-supplied path.
        allowed: the capability-specific allow tuple.

    Returns:
        The resolved, in-scope absolute path.

    Raises:
        PermissionError: if the path is denied, outside the allowlist, or is
            a hidden secret file.

    """
    settings = get_settings()
    candidate = raw.expanduser().resolve()

    # Layer 1 — hard deny (always wins).
    for base in settings.denied_bases:
        if candidate == base or base in candidate.parents:
            raise PermissionError(f"path denied by hard policy: {candidate}")

    # Layer 1b — hidden secret files (defense in depth against name-based bypass).
    if _is_hidden_secret_file(candidate):
        raise PermissionError(f"path denied by hard policy (.env*): {candidate}")

    # Layer 2 — capability allowlist.
    if not any(candidate == base or base in candidate.parents for base in allowed):
        listed = ", ".join(str(b) for b in allowed) or "<empty>"
        raise PermissionError(f"path outside allowlist ({listed}): {candidate}")

    return candidate


class ListDirArgs(BaseModel):
    """Arguments for list_dir."""

    path: str = Field(..., description="Directory path to list (inside an allowlisted base)")


class ReadFileArgs(BaseModel):
    """Arguments for read_file."""

    path: str = Field(..., description="File path to read (must be inside an allowlisted base)")
    max_bytes: int = Field(default=65536, ge=1, le=1_048_576)


class WriteFileArgs(BaseModel):
    """Arguments for write_file."""

    path: str = Field(..., description="File path to write (write-scoped base; not ~)")
    content: str = Field(..., description="Exact file content to write (overwrites)")
    create_parents: bool = Field(default=False, description="If true, mkdir -p the parent")


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
    target = _check_scope(Path(args.path), get_settings().allowed_bases)

    def _scan() -> list[dict]:
        entries: list[dict] = []
        with __import__("os").scandir(target) as it:
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
    target = _check_scope(Path(args.path), get_settings().allowed_bases)
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


@registry.tool(
    risk="confirm",
    description=(
        "Write text content to a file. Overwrites existing files. "
        "Scope: cwd + /tmp only (NOT the home directory)."
    ),
)
async def write_file(args: WriteFileArgs) -> dict:
    """Write content to a file inside the write-scoped allowlist.

    Args:
        args: the validated tool arguments.

    Returns:
        A dict with the resolved path and bytes written.

    """
    target = _check_scope(Path(args.path), get_settings().write_allowed_bases)

    def _write() -> int:
        if args.create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        return target.write_text(args.content, encoding="utf-8")

    written = await asyncio.to_thread(_write)
    return {"path": str(target), "bytes_written": written}
