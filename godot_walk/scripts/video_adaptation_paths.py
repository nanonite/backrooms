"""Repository-contained paths and adaptation-scoped receipt locations."""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

from video_adaptation_errors import AdaptationValidationError

ROOT = Path(__file__).resolve().parents[2]
ADAPTATION_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_adaptation_id(value: object) -> str:
    if not isinstance(value, str) or len(value) > 80:
        raise AdaptationValidationError("Adaptation ID must be a stable lowercase slug")
    if ADAPTATION_ID_PATTERN.fullmatch(value) is None:
        raise AdaptationValidationError("Adaptation ID contains unsafe path characters")
    return value


def validate_stage_id(value: object) -> str:
    if not isinstance(value, str) or STAGE_ID_PATTERN.fullmatch(value) is None:
        raise AdaptationValidationError(
            "Stage ID may contain only letters, digits, '_' and '-'"
        )
    return value


def resolve_repo_path(
    path_text: str, root: Path = ROOT, *, require_file: bool = False
) -> Path:
    relative = _validated_relative_path(path_text)
    candidate = (root.resolve() / Path(*relative.parts)).resolve(strict=False)
    _ensure_contained(candidate, root, path_text)
    if require_file and not candidate.is_file():
        raise AdaptationValidationError(f"Missing repository file: {path_text}")
    return candidate


def _validated_relative_path(path_text: str) -> PurePosixPath:
    if not isinstance(path_text, str) or not path_text or "\\" in path_text:
        raise AdaptationValidationError(
            "Repository paths must be nonempty POSIX relative paths"
        )
    raw_parts = path_text.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise AdaptationValidationError(
            f"Traversal or empty component in repository path: {path_text}"
        )
    relative = PurePosixPath(path_text)
    if relative.is_absolute() or PureWindowsPath(path_text).is_absolute():
        raise AdaptationValidationError(
            f"Absolute repository path is forbidden: {path_text}"
        )
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise AdaptationValidationError(
            f"Traversal or empty component in repository path: {path_text}"
        )
    return relative


def _ensure_contained(candidate: Path, root: Path, path_text: str) -> None:
    if not candidate.is_relative_to(root.resolve()):
        raise AdaptationValidationError(f"Path escapes repository root: {path_text}")


def resolve_scene_reference(scene_text: str, root: Path = ROOT) -> tuple[Path, str]:
    if not isinstance(scene_text, str) or not scene_text:
        raise AdaptationValidationError("Scene references must be nonempty strings")
    relative = (
        scene_text.removeprefix("res://")
        if scene_text.startswith("res://")
        else scene_text
    )
    if scene_text.startswith("res://"):
        relative = f"godot_walk/{relative}"
    path = resolve_repo_path(relative, root, require_file=True)
    return path, path.relative_to(root.resolve()).as_posix()


def receipt_directory(
    bundle_path: Path, adaptation_id: str, root: Path = ROOT, *, create: bool = False
) -> Path:
    safe_id = validate_adaptation_id(adaptation_id)
    base = bundle_path.resolve().parent
    directory = base / "stage_receipts" / safe_id
    _reject_symlink_components(directory, base)
    resolved = directory.resolve(strict=False)
    _ensure_contained(resolved, root, "Stage receipt directory")
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
        _reject_symlink_components(directory, base)
        resolved = directory.resolve(strict=True)
        _ensure_contained(resolved, root, "Stage receipt directory")
    return resolved


def receipt_file(
    bundle_path: Path,
    adaptation_id: str,
    stage_id: str,
    root: Path = ROOT,
    *,
    create_directory: bool = False,
) -> Path:
    directory = receipt_directory(
        bundle_path, adaptation_id, root, create=create_directory
    )
    filename = f"{validate_stage_id(stage_id)}.json"
    target = directory / filename
    if target.is_symlink():
        raise AdaptationValidationError(
            f"Stage receipt may not be a symlink: {filename}"
        )
    resolved = target.resolve(strict=False)
    if not resolved.is_relative_to(directory):
        raise AdaptationValidationError(
            f"Stage receipt escapes its adaptation directory: {filename}"
        )
    return resolved


def receipt_files(
    bundle_path: Path, adaptation_id: str, root: Path = ROOT
) -> list[Path]:
    directory = receipt_directory(bundle_path, adaptation_id, root)
    if not directory.exists():
        return []
    files = []
    for path in sorted(directory.iterdir()):
        if path.suffix != ".json":
            continue
        if path.is_symlink():
            raise AdaptationValidationError(
                f"Stage receipt may not be a symlink: {path.name}"
            )
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(directory) or not resolved.is_file():
            raise AdaptationValidationError(f"Unsafe stage receipt path: {path.name}")
        files.append(resolved)
    return files


def create_new_file(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise AdaptationValidationError(f"Refusing to write through symlink: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def _reject_symlink_components(path: Path, stop_at: Path) -> None:
    current = stop_at
    if current.is_symlink():
        raise AdaptationValidationError(
            f"Receipt path parent may not be a symlink: {current}"
        )
    for component in path.relative_to(stop_at).parts:
        current = current / component
        if current.is_symlink():
            raise AdaptationValidationError(
                f"Receipt path component may not be a symlink: {current}"
            )


def _ensure_contained(path: Path, root: Path, label: str) -> None:
    if not path.is_relative_to(root.resolve()):
        raise AdaptationValidationError(f"{label} escapes repository root")
