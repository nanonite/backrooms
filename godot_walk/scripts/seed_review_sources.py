"""Read one registered source and bind it to its canonical video bytes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seed_review_errors import SeedReviewError
from seed_review_paths import (
    ROOT,
    SOURCE_LIBRARY_INDEX,
    read_json_object,
    resolve_repo_path,
    sha256_file,
)

SOURCE_ID_PATTERN = re.compile(r"^video-[0-9a-f]{16}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DIRECT_SOURCE_DECODE = "direct_source_video_decode_no_resize_or_edit"
MANIFEST_NAME_PATTERN = re.compile(r"^source_manifest(?:-v([2-9]|[1-9][0-9]+))?\.json$")


@dataclass(frozen=True)
class SourceRecord:
    """The canonical source-video identity used by one review stage."""

    source_id: str
    video_path: str
    video_sha256: str
    width: int
    height: int
    fps: float
    duration_seconds: float
    frame_count: int | None
    manifest_path: str
    manifest_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "video_path": self.video_path,
            "video_sha256": self.video_sha256,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration_seconds": self.duration_seconds,
            "frame_count": self.frame_count,
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
        }


def load_source_record(source_id: str, root: Path = ROOT) -> SourceRecord:
    _validate_source_id(source_id)
    index = read_json_object(
        root / SOURCE_LIBRARY_INDEX.relative_to(ROOT), "source index"
    )
    if index.get("schema_version") != 1 or not isinstance(index.get("sources"), list):
        raise SeedReviewError(
            "source_index_invalid", "Unsupported source-library index"
        )
    entry = next(
        (item for item in index["sources"] if item.get("source_id") == source_id),
        None,
    )
    if entry is None:
        raise SeedReviewError(
            "source_not_registered", f"Source is not registered: {source_id}"
        )
    _verify_entry_identity(entry)
    manifest_path = _verify_manifest(entry, root)
    manifest = read_json_object(manifest_path, "source manifest")
    video_path, video_sha256 = _canonical_video(entry, manifest, source_id, root)
    if sha256_file(video_path) != video_sha256:
        raise SeedReviewError(
            "source_video_changed",
            f"Source video bytes changed since registration: {source_id}",
        )
    metadata = manifest["canonical_video"]["metadata"]
    return SourceRecord(
        source_id=source_id,
        video_path=entry["source_path"],
        video_sha256=video_sha256,
        width=int(metadata["width"]),
        height=int(metadata["height"]),
        fps=float(metadata["fps"]),
        duration_seconds=float(metadata["duration_seconds"]),
        frame_count=_optional_int(metadata.get("frame_count")),
        manifest_path=manifest_path.relative_to(root.resolve()).as_posix(),
        manifest_sha256=entry["manifest_sha256"],
    )


def _validate_source_id(source_id: str) -> None:
    if not isinstance(source_id, str) or SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise SeedReviewError("unsafe_source_id", "Source ID is not safe")


def _verify_entry_identity(entry: dict[str, Any]) -> None:
    source_id = entry.get("source_id")
    source_path = entry.get("source_path")
    source_sha256 = entry.get("source_sha256")
    manifest_sha256 = entry.get("manifest_sha256")
    if (
        not isinstance(source_id, str)
        or SOURCE_ID_PATTERN.fullmatch(source_id) is None
        or not isinstance(source_path, str)
        or not source_path.startswith("data/videos/")
        or not isinstance(source_sha256, str)
        or SHA256_PATTERN.fullmatch(source_sha256) is None
        or not isinstance(manifest_sha256, str)
        or SHA256_PATTERN.fullmatch(manifest_sha256) is None
    ):
        raise SeedReviewError("source_index_invalid", "Source index entry is malformed")


def _verify_manifest(entry: dict[str, Any], root: Path) -> Path:
    source_id = entry["source_id"]
    manifest_text = entry.get("manifest_path")
    expected_dir = f"godot_walk/source_library/sources/{source_id}"
    if not isinstance(manifest_text, str):
        raise SeedReviewError("source_manifest_invalid", "Manifest path is missing")
    manifest_path = resolve_repo_path(manifest_text, root, require_file=True)
    if (
        manifest_path.parent != (root.resolve() / expected_dir)
        or MANIFEST_NAME_PATTERN.fullmatch(manifest_path.name) is None
    ):
        raise SeedReviewError(
            "source_manifest_invalid", "Manifest path is not source-scoped"
        )
    if sha256_file(manifest_path) != entry["manifest_sha256"]:
        raise SeedReviewError(
            "source_manifest_changed", f"Source manifest changed: {source_id}"
        )
    return manifest_path


def _canonical_video(
    entry: dict[str, Any],
    manifest: dict[str, Any],
    source_id: str,
    root: Path,
) -> tuple[Path, str]:
    canonical = manifest.get("canonical_video")
    if not isinstance(canonical, dict):
        raise SeedReviewError(
            "source_manifest_invalid", "Manifest lacks canonical video identity"
        )
    path_text = canonical.get("path")
    digest = canonical.get("sha256")
    metadata = canonical.get("metadata")
    if (
        manifest.get("source_id") != source_id
        or path_text != entry.get("source_path")
        or digest != entry.get("source_sha256")
        or not isinstance(digest, str)
        or SHA256_PATTERN.fullmatch(digest) is None
        or not isinstance(metadata, dict)
    ):
        raise SeedReviewError(
            "source_manifest_mismatch",
            f"Manifest source identity mismatch: {source_id}",
        )
    _verify_metadata(metadata)
    video_path = resolve_repo_path(path_text, root, require_file=True)
    video_root = (root.resolve() / "data/videos").resolve()
    if video_path.parent != video_root:
        raise SeedReviewError(
            "unsafe_source_path", "Source videos must be direct files under data/videos"
        )
    return video_path, digest


def _verify_metadata(metadata: dict[str, Any]) -> None:
    try:
        width = int(metadata["width"])
        height = int(metadata["height"])
        fps = float(metadata["fps"])
        duration = float(metadata["duration_seconds"])
    except (KeyError, TypeError, ValueError) as error:
        raise SeedReviewError(
            "source_metadata_invalid", "Source metadata is incomplete"
        ) from error
    if width <= 0 or height <= 0 or fps <= 0 or duration <= 0:
        raise SeedReviewError(
            "source_metadata_invalid", "Source metadata must be positive"
        )


def _optional_int(value: Any) -> int | None:
    if value in (None, "N/A"):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise SeedReviewError(
            "source_metadata_invalid", "Source frame count is not an integer"
        ) from error
    if parsed <= 0:
        raise SeedReviewError(
            "source_metadata_invalid", "Source frame count must be positive"
        )
    return parsed
