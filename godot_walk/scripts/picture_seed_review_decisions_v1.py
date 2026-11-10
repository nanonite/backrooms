"""Operator approval records and Hunyuan binding checks for picture review v1."""

from __future__ import annotations

from typing import Any

from picture_seed_review_contract_v1 import (
    MAX_REVIEW_IMAGES,
    MIN_HUNYUAN_LONG_SIDE,
    PICTURE_SOURCE_ID_PATTERN,
    SHA256_PATTERN,
)
from seed_review_errors import SeedReviewError
from seed_review_paths import canonical_sha256
from video_source_library import PICTURE_SET_SOURCE_KIND


def make_operator_decision(
    review: dict[str, Any], image_id: str, rationale: str
) -> dict[str, Any]:
    """Build an explicit operator approval for one reviewed original image."""
    if not isinstance(rationale, str) or not rationale.strip():
        raise SeedReviewError(
            "operator_rationale_required", "An operator rationale is required"
        )
    candidates = review.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > MAX_REVIEW_IMAGES:
        raise SeedReviewError("review_invalid", "Review candidate list is invalid")
    selected = next(
        (
            candidate
            for candidate in candidates
            if candidate.get("image_id") == image_id
        ),
        None,
    )
    if selected is None:
        raise SeedReviewError(
            "image_not_reviewed", "Only an image sent to model review can be approved"
        )
    decision = {
        "schema_version": 1,
        "review_spec": "picture_seed_review_v1",
        "decision": "approved",
        "source_kind": PICTURE_SET_SOURCE_KIND,
        "source_id": review["source_id"],
        "source_image_set_sha256": review["source_image_set_sha256"],
        "review_request_sha256": canonical_sha256(review),
        "image_id": selected["image_id"],
        "image_sha256": selected["sha256"],
        "path": selected["path"],
        "capture_index": selected["capture_index"],
        "width": selected["width"],
        "height": selected["height"],
        "resolution_warning": selected["resolution_warning"],
        "operator_rationale": rationale.strip(),
    }
    decision["decision_sha256"] = canonical_sha256(decision)
    return decision


def validate_picture_seed_decision(
    decision: dict[str, Any],
    source_image_set_sha256: str,
    image_id: str,
    image_sha256: str,
    *,
    enforce_hunyuan_resolution: bool = True,
    expected_image: dict[str, Any] | None = None,
) -> None:
    """Validate approval identity and enforce the Hunyuan resolution gate."""
    digest = decision.get("decision_sha256")
    body = {key: value for key, value in decision.items() if key != "decision_sha256"}
    if (
        decision.get("schema_version") != 1
        or decision.get("review_spec") != "picture_seed_review_v1"
        or decision.get("decision") != "approved"
        or decision.get("source_kind") != PICTURE_SET_SOURCE_KIND
        or not isinstance(decision.get("source_id"), str)
        or PICTURE_SOURCE_ID_PATTERN.fullmatch(decision["source_id"]) is None
        or decision.get("source_image_set_sha256") != source_image_set_sha256
        or decision.get("image_id") != image_id
        or decision.get("image_sha256") != image_sha256
        or not isinstance(digest, str)
        or SHA256_PATTERN.fullmatch(digest) is None
        or canonical_sha256(body) != digest
    ):
        raise SeedReviewError(
            "picture_seed_decision_mismatch",
            "Picture seed approval does not bind this image set and image",
        )
    width, height = decision.get("width"), decision.get("height")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or isinstance(height, bool)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
    ):
        raise SeedReviewError(
            "picture_seed_decision_invalid", "Approved image dimensions are invalid"
        )
    if expected_image is not None and (
        decision.get("path") != expected_image.get("source_image_path")
        or width != expected_image.get("width")
        or height != expected_image.get("height")
        or decision.get("capture_index") != expected_image.get("capture_index")
    ):
        raise SeedReviewError(
            "picture_seed_decision_mismatch",
            "Picture seed approval dimensions or source path do not match the image",
        )
    _validate_resolution(decision, width, height, enforce_hunyuan_resolution)


def _validate_resolution(
    decision: dict[str, Any], width: int, height: int, enforce: bool
) -> None:
    low_resolution = max(width, height) < MIN_HUNYUAN_LONG_SIDE
    if decision.get("resolution_warning") is not low_resolution:
        raise SeedReviewError(
            "picture_seed_decision_mismatch",
            "Picture seed approval has an invalid resolution warning",
        )
    if enforce and low_resolution:
        raise SeedReviewError(
            "picture_seed_resolution_too_low",
            "Hunyuan guard rejects approved images below 1024 pixels on the long side",
        )
