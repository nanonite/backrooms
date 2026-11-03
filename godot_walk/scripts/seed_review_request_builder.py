"""Build seed-review requests from verified direct-source extraction receipts."""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from seed_review_errors import SeedReviewError
from seed_review_paths import (
    ROOT,
    read_json_object,
    repo_relative,
    resolve_repo_path,
    sha256_file,
)
from seed_review_schemas import validate_request
from seed_review_sources import SourceRecord, load_source_record
from seed_review_workflow import load_workflow_spec

DECODE_OPERATION = "direct_source_video_decode_no_resize_or_edit"
DECODER = "ffmpeg select by decoded zero-based frame index"
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def build_request(
    source_id: str,
    extraction_manifest_path: str,
    root: Path = ROOT,
) -> dict[str, Any]:
    source = load_source_record(source_id, root)
    spec = load_workflow_spec(root)
    manifest_path = _verified_manifest_path(source_id, extraction_manifest_path, root)
    extraction = read_json_object(manifest_path, "direct-frame extraction manifest")
    _verify_extraction(extraction, source)
    frames = _frame_list(extraction, spec.max_candidates)
    _verify_frame_order(frames)
    candidates = [
        _candidate(frame, source, manifest_path.parent, root) for frame in frames
    ]
    request = {
        "schema_version": 1,
        "workflow_spec_version": "1.0.0",
        "source_id": source.source_id,
        "source_video_sha256": source.video_sha256,
        "candidates": candidates,
    }
    validate_request(request, spec)
    return request


def write_request(request: dict[str, Any], output_path: str, root: Path = ROOT) -> Path:
    target = resolve_repo_path(output_path, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = resolve_repo_path(output_path, root)
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
        )
    except FileExistsError as error:
        raise SeedReviewError(
            "request_exists", f"Refusing to overwrite request: {output_path}"
        ) from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(request, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return target


def _verified_manifest_path(source_id: str, path_text: str, root: Path) -> Path:
    path = resolve_repo_path(path_text, root, require_file=True)
    source_frames = (
        root.resolve() / "godot_walk/source_library/sources" / source_id / "frames"
    )
    if (
        not path.is_relative_to(source_frames)
        or path.name != "extraction_manifest.json"
    ):
        raise SeedReviewError(
            "unsafe_extraction_manifest",
            "Extraction manifest must be inside this source's frame batches",
        )
    return path


def _verify_extraction(extraction: dict[str, Any], source: SourceRecord) -> None:
    if (
        extraction.get("schema_version") != 1
        or extraction.get("source_video") != source.video_path
        or extraction.get("source_video_sha256") != source.video_sha256
        or extraction.get("decoder") != DECODER
    ):
        raise SeedReviewError(
            "extraction_source_mismatch",
            "Frame extraction is not bound to the registered source video",
        )
    metadata = extraction.get("metadata")
    if not isinstance(metadata, dict) or (
        metadata.get("width"),
        metadata.get("height"),
    ) != (source.width, source.height):
        raise SeedReviewError(
            "extraction_metadata_mismatch",
            "Extracted frames do not use the registered native dimensions",
        )


def _frame_list(extraction: dict[str, Any], maximum: int) -> list[dict[str, Any]]:
    frames = extraction.get("frames")
    if not isinstance(frames, list) or not frames:
        raise SeedReviewError(
            "extraction_frames_missing", "Extraction manifest has no frame list"
        )
    if any(not isinstance(frame, dict) for frame in frames):
        raise SeedReviewError(
            "extraction_frames_invalid", "Every extracted frame must be an object"
        )
    if len(frames) > maximum:
        raise SeedReviewError(
            "candidate_count_exceeds_limit",
            f"Extraction has {len(frames)} frames; the review limit is {maximum}",
        )
    return frames


def _verify_frame_order(frames: list[dict[str, Any]]) -> None:
    indexes = [frame.get("index_zero_based") for frame in frames]
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indexes):
        raise SeedReviewError(
            "extraction_frame_invalid", "Frame indexes must be integers"
        )
    if indexes != sorted(set(indexes)):
        raise SeedReviewError(
            "extraction_frame_order_invalid",
            "Frame indexes must be unique and in source order",
        )


def _candidate(
    frame: dict[str, Any],
    source: SourceRecord,
    batch_dir: Path,
    root: Path,
) -> dict[str, Any]:
    index, pts, frame_id, digest, relative = _validated_frame_metadata(frame, source)
    path = _verified_frame_path(relative, frame_id, digest, batch_dir, root)
    _verify_dimensions(path, frame_id, source)
    return _candidate_document(index, pts, frame_id, digest, path, source, root)


def _validated_frame_metadata(
    frame: dict[str, Any], source: SourceRecord
) -> tuple[int, float, str, str, str]:
    index = frame.get("index_zero_based")
    pts = frame.get("timestamp_seconds")
    frame_id = frame.get("frame_id")
    digest = frame.get("sha256")
    relative = frame.get("path")
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or index < 0
        or not _valid_timestamp(pts, source.duration_seconds)
        or not isinstance(frame_id, str)
        or frame_id != f"frame_{index + 1:04d}"
        or not isinstance(digest, str)
        or HASH_PATTERN.fullmatch(digest) is None
        or not isinstance(relative, str)
        or frame.get("decode_operation") != DECODE_OPERATION
    ):
        raise SeedReviewError(
            "extraction_frame_invalid", "Extracted frame metadata is malformed"
        )
    return index, float(pts), frame_id, digest, relative


def _valid_timestamp(value: Any, duration_seconds: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        timestamp = float(value)
    except OverflowError:
        return False
    return math.isfinite(timestamp) and 0 <= timestamp <= duration_seconds


def _verified_frame_path(
    relative: str,
    frame_id: str,
    digest: str,
    batch_dir: Path,
    root: Path,
) -> Path:
    if relative != f"{batch_dir.relative_to(root.resolve()).as_posix()}/{frame_id}.png":
        raise SeedReviewError(
            "extraction_frame_mismatch",
            f"Frame path does not match its source-frame ID: {frame_id}",
        )
    path = resolve_repo_path(relative, root, require_file=True)
    if path.parent != batch_dir or sha256_file(path) != digest:
        raise SeedReviewError(
            "extraction_frame_mismatch", f"Frame bytes or location changed: {frame_id}"
        )
    return path


def _candidate_document(
    index: int,
    pts: float,
    frame_id: str,
    digest: str,
    path: Path,
    source: SourceRecord,
    root: Path,
) -> dict[str, Any]:
    return {
        "frame_id": frame_id,
        "index_zero_based": index,
        "pts_seconds": float(pts),
        "path": repo_relative(path, root),
        "sha256": digest,
        "width": source.width,
        "height": source.height,
        "origin": "direct_source_frame",
        "decode_operation": DECODE_OPERATION,
    }


def _verify_dimensions(path: Path, frame_id: str, source: SourceRecord) -> None:
    try:
        with Image.open(path) as image:
            dimensions = image.size
    except (OSError, UnidentifiedImageError) as error:
        raise SeedReviewError(
            "extraction_frame_unreadable", f"Cannot read extracted frame: {frame_id}"
        ) from error
    if dimensions != (source.width, source.height):
        raise SeedReviewError(
            "extraction_frame_resized",
            f"Extracted frame is not native resolution: {frame_id}",
        )
