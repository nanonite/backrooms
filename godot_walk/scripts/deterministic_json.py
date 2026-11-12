"""Deterministic JSON bytes, hashing and refuse-to-overwrite writes."""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VALIDATION_STATE_ROOTS = (
    "data/pictures",
    "data/videos",
    "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md",
    "godot_walk/evidence/2026-11-11-issue-216",
    "godot_walk/room_catalog",
    "godot_walk/source_library",
)


def repository_state(root: Path = ROOT) -> tuple[tuple[str, int, int], ...]:
    """Stat identity of every input the read-only validators consume.

    The tuple changes when a file is added, removed, resized, or touched, so a
    memoized validation result is reused only for an unchanged repository.
    """
    entries: list[tuple[str, int, int]] = []
    for relative in VALIDATION_STATE_ROOTS:
        path = root / relative
        if path.is_file():
            stat = path.stat()
            entries.append((relative, stat.st_mtime_ns, stat.st_size))
        elif path.is_dir():
            for item in sorted(path.rglob("*")):
                if item.is_file() and not item.is_symlink():
                    stat = item.stat()
                    entries.append(
                        (
                            item.relative_to(root).as_posix(),
                            stat.st_mtime_ns,
                            stat.st_size,
                        )
                    )
    return tuple(entries)


class DeterministicWriteError(ValueError):
    """A derived file already exists with different content."""


def canonical_bytes(value: Any) -> bytes:
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=8192)
def _sha256_unchanged(path: str, mtime_ns: int, size: int) -> str:
    del mtime_ns, size
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a file, reusing the digest only while its stat identity is unchanged."""
    stat = path.stat()
    return _sha256_unchanged(str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def repo_relative(path: Path, root: Path = ROOT) -> str:
    """Return the posix path of `path` below `root`, or fail."""
    base = root.resolve()
    target = path if path.is_absolute() else base / path
    try:
        return target.resolve().relative_to(base).as_posix()
    except ValueError as error:
        raise ValueError(f"{path} is outside the repository root {base}") from error


def resolve_cli_path(path: Path, root: Path = ROOT) -> Path:
    """Absolute path for a CLI argument: as given if it exists, else below root."""
    if path.is_absolute() or path.exists():
        return path.resolve()
    return root / path


def plan_write(path: Path, data: bytes) -> str:
    """Return "create" or "unchanged"; raise if different content exists."""
    if path.is_symlink():
        raise DeterministicWriteError(f"Refusing to write through symlink {path}")
    if not path.exists():
        return "create"
    if path.read_bytes() == data:
        return "unchanged"
    raise DeterministicWriteError(
        f"Refusing to overwrite {path}: existing content differs from derived content"
    )


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def write_deterministic(path: Path, data: bytes) -> str:
    status = plan_write(path, data)
    if status == "create":
        write_new(path, data)
        return "created"
    return status
