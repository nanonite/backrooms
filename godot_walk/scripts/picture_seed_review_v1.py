"""Versioned seed review for direct images in registered picture sets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from picture_seed_review_candidates_v1 import evaluate_and_rank_images
from picture_seed_review_contract_v1 import (
    MAX_REVIEW_IMAGES,
    PICTURE_SOURCE_ID_PATTERN,
    REVIEW_SPEC_VERSION,
    SHORTLIST_REASON,
    PictureSetRecord,
)
from picture_seed_review_decisions_v1 import (
    make_operator_decision,
    validate_picture_seed_decision,
)
from picture_seed_review_invocation_v1 import build_picture_model_invocation
from seed_review_errors import SeedReviewError
from seed_review_paths import ROOT
from video_source_library import (
    PICTURE_SET_SOURCE_KIND,
    SourceLibraryError,
    picture_set_sha256,
    validate_index,
)

__all__ = [
    "MAX_REVIEW_IMAGES",
    "PictureSetRecord",
    "build_picture_model_invocation",
    "build_picture_seed_review",
    "load_picture_set_record",
    "make_operator_decision",
    "validate_picture_seed_decision",
]


def load_picture_set_record(source_id: str, root: Path = ROOT) -> PictureSetRecord:
    """Load schema-v3 picture identity through the picture-specific path."""
    if (
        not isinstance(source_id, str)
        or PICTURE_SOURCE_ID_PATTERN.fullmatch(source_id) is None
    ):
        raise SeedReviewError("unsafe_source_id", "Source ID is not a picture set")
    entry = _source_entry(source_id, root)
    if entry.get("source_kind", PICTURE_SET_SOURCE_KIND) != PICTURE_SET_SOURCE_KIND:
        raise SeedReviewError("source_kind_mismatch", "Source is not a picture set")
    manifest = _read_manifest(root / entry["manifest_path"])
    images = (manifest.get("content") or {}).get("picture_set")
    if (
        manifest.get("source_kind") != PICTURE_SET_SOURCE_KIND
        or manifest.get("source_id") != source_id
        or not isinstance(images, list)
        or not images
        or picture_set_sha256(images) != entry["source_sha256"]
    ):
        raise SeedReviewError(
            "source_manifest_mismatch", "Picture-set manifest identity is invalid"
        )
    return PictureSetRecord(
        source_id=source_id,
        source_path=entry["source_path"],
        source_image_set_sha256=entry["source_sha256"],
        manifest_path=entry["manifest_path"],
        manifest_sha256=entry["manifest_sha256"],
        images=tuple(images),
    )


def build_picture_seed_review(source_id: str, root: Path = ROOT) -> dict[str, Any]:
    """Score the full set and return at most three direct originals for review."""
    source = load_picture_set_record(source_id, root)
    ranked = evaluate_and_rank_images(source, root)
    candidates = [
        item for item in ranked if item["mechanical_rank"] <= MAX_REVIEW_IMAGES
    ]
    excluded = [item for item in ranked if item["mechanical_rank"] > MAX_REVIEW_IMAGES]
    return {
        "schema_version": 1,
        "review_spec": "picture_seed_review_v1",
        "review_spec_version": REVIEW_SPEC_VERSION,
        "source_kind": PICTURE_SET_SOURCE_KIND,
        "source_id": source.source_id,
        "source_image_set_sha256": source.source_image_set_sha256,
        "source_manifest_path": source.manifest_path,
        "source_manifest_sha256": source.manifest_sha256,
        "capture_index_semantics": (
            "file order only for an unrelated picture collection; no timeline "
            "or temporal coverage is inferred"
        ),
        "scoring": {
            "metrics": ["focus", "exposure", "duplicate_similarity"],
            "temporal_coverage_term": False,
            "score": (
                "(0.50*focus + 0.25*exposure + 0.15*(1-duplicate_similarity)) / 0.90"
            ),
            "resolution_is_not_a_ranking_term": True,
        },
        "model_review_limit": MAX_REVIEW_IMAGES,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "excluded": [_excluded_record(image) for image in excluded],
    }


def _source_entry(source_id: str, root: Path) -> dict[str, Any]:
    try:
        entry = next(
            item for item in validate_index(root) if item.get("source_id") == source_id
        )
    except StopIteration as error:
        raise SeedReviewError(
            "source_not_registered", f"Picture set is not registered: {source_id}"
        ) from error
    except SourceLibraryError as error:
        raise SeedReviewError("source_index_invalid", str(error)) from error
    return entry


def _excluded_record(image: dict[str, Any]) -> dict[str, Any]:
    return {
        "image_id": image["image_id"],
        "capture_index": image["capture_index"],
        "path": image["path"],
        "sha256": image["sha256"],
        "width": image["width"],
        "height": image["height"],
        "resolution_warning": image["resolution_warning"],
        "resolution_warning_code": image["resolution_warning_code"],
        "mechanical_score": image["metrics"]["mechanical_score"],
        "mechanical_rank": image["mechanical_rank"],
        "reason": SHORTLIST_REASON,
    }


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SeedReviewError(
            "source_manifest_invalid", "Picture-set manifest cannot be read"
        ) from error
    if not isinstance(value, dict):
        raise SeedReviewError(
            "source_manifest_invalid", "Picture-set manifest must be an object"
        )
    return value
