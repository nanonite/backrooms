"""Repository-contained paths and canonical hashing for seed review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from seed_review_errors import SeedReviewError

ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = ROOT / "godot_walk/seed_review"
WORKFLOW_MANIFEST = SPEC_DIR / "workflow.v1.json"
SCHEMA_DIR = SPEC_DIR / "schemas"
DEFAULT_RECEIPTS_DIR = SPEC_DIR / "receipts"
SOURCE_LIBRARY_INDEX = ROOT / "godot_walk/source_library/index.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SeedReviewError(
            "unreadable_json", f"Cannot read {label}: {path}"
        ) from error
    if not isinstance(value, dict):
        raise SeedReviewError("invalid_json", f"{label} must be a JSON object: {path}")
    return value


def resolve_repo_path(
    path_text: str, root: Path = ROOT, *, require_file: bool = False
) -> Path:
    relative = validated_relative_path(path_text)
    repo = root.resolve()
    candidate = repo.joinpath(*relative.parts)
    _reject_symlink_components(candidate, repo)
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(repo):
        raise SeedReviewError(
            "unsafe_path", f"Path escapes the repository: {path_text}"
        )
    if require_file and not resolved.is_file():
        raise SeedReviewError("missing_file", f"Missing repository file: {path_text}")
    return resolved


def repo_relative(path: Path, root: Path = ROOT) -> str:
    repo = root.resolve()
    resolved = path.resolve(strict=False)
    if not resolved.is_relative_to(repo):
        raise SeedReviewError("unsafe_path", f"Path is outside the repository: {path}")
    return resolved.relative_to(repo).as_posix()


def validated_relative_path(path_text: str) -> PurePosixPath:
    if (
        not isinstance(path_text, str)
        or not path_text
        or "\\" in path_text
        or "\x00" in path_text
    ):
        raise SeedReviewError(
            "unsafe_path", "Repository paths must be nonempty POSIX paths"
        )
    raw_parts = path_text.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise SeedReviewError(
            "unsafe_path", f"Traversal or empty path component: {path_text}"
        )
    relative = PurePosixPath(path_text)
    if relative.is_absolute() or PureWindowsPath(path_text).is_absolute():
        raise SeedReviewError(
            "unsafe_path", f"Absolute repository path is forbidden: {path_text}"
        )
    return relative


def _reject_symlink_components(path: Path, repo: Path) -> None:
    candidate = path.absolute()
    if not candidate.is_relative_to(repo):
        raise SeedReviewError("unsafe_path", f"Path escapes the repository: {path}")
    current = repo
    for component in candidate.relative_to(repo).parts:
        current /= component
        if current.is_symlink():
            raise SeedReviewError("unsafe_path", f"Path uses a symlink: {current}")
