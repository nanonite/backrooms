"""Full-resolution model inputs and prompt for picture seed review v1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from picture_seed_review_contract_v1 import DIRECT_IMAGE_REVIEW, MAX_REVIEW_IMAGES
from seed_review_errors import SeedReviewError
from seed_review_metrics import load_native_gray
from seed_review_paths import ROOT, canonical_sha256, resolve_repo_path, sha256_file
from seed_review_provider import ModelIdentity, ModelInvocation


def build_picture_model_invocation(
    review: dict[str, Any],
    identity: ModelIdentity,
    root: Path = ROOT,
    *,
    timeout_seconds: float = 120.0,
) -> ModelInvocation:
    """Bind at most three original image files to the existing vision adapter."""
    candidates = review.get("candidates")
    if (
        not isinstance(candidates, list)
        or not candidates
        or len(candidates) > MAX_REVIEW_IMAGES
        or timeout_seconds <= 0
    ):
        raise SeedReviewError("review_invalid", "Picture review request is invalid")
    registered = _verify_review(review, root)
    image_paths = [
        _verify_original(candidate, registered, root) for candidate in candidates
    ]
    return ModelInvocation(
        identity=identity,
        prompt=_picture_review_prompt(review),
        image_paths=tuple(image_paths),
        timeout_seconds=float(timeout_seconds),
    )


def _verify_review(review: dict[str, Any], root: Path) -> dict[str, Any]:
    from picture_seed_review_v1 import (
        build_picture_seed_review,
        load_picture_set_record,
    )

    source = load_picture_set_record(review.get("source_id"), root)
    if source.source_image_set_sha256 != review.get("source_image_set_sha256"):
        raise SeedReviewError("review_source_mismatch", "Review source hash changed")
    expected = build_picture_seed_review(source.source_id, root)
    if canonical_sha256(expected) != canonical_sha256(review):
        raise SeedReviewError("review_changed", "Picture review request changed")
    return {image["image_id"]: image for image in source.images}


def _verify_original(
    candidate: dict[str, Any], registered: dict[str, Any], root: Path
) -> Path:
    original = registered.get(candidate.get("image_id"))
    if (
        original is None
        or candidate.get("origin") != "direct_source_picture"
        or candidate.get("decode_operation") != DIRECT_IMAGE_REVIEW
        or candidate.get("path") != original.get("path")
        or candidate.get("sha256") != original.get("sha256")
        or candidate.get("width") != original.get("width")
        or candidate.get("height") != original.get("height")
    ):
        raise SeedReviewError(
            "not_direct_source_picture", "Review inputs must be original images"
        )
    path = resolve_repo_path(candidate["path"], root, require_file=True)
    if path.is_symlink() or sha256_file(path) != candidate["sha256"]:
        raise SeedReviewError(
            "picture_hash_mismatch",
            f"Original picture changed: {candidate.get('image_id')}",
        )
    native = load_native_gray(path)
    if native.shape != (candidate["height"], candidate["width"]):
        raise SeedReviewError(
            "picture_size_mismatch",
            f"Original picture dimensions changed: {candidate.get('image_id')}",
        )
    return path


def _picture_review_prompt(review: dict[str, Any]) -> str:
    metadata = [
        {
            "image_id": image["image_id"],
            "capture_index_file_order_only": image["capture_index"],
            "sha256": image["sha256"],
            "width": image["width"],
            "height": image["height"],
            "resolution_warning": image["resolution_warning"],
            "mechanical_score": image["metrics"]["mechanical_score"],
        }
        for image in review["candidates"]
    ]
    return (
        "\n".join(
            [
                "PICTURE-SET SEED REVIEW v1",
                f"Source ID: {review['source_id']}",
                f"Image-set SHA-256: {review['source_image_set_sha256']}",
                "The attached images are the exact full-resolution originals listed below.",
                "They are not resized, edited, or combined into a contact sheet.",
                "capture_index is file order for an unrelated collection, not time.",
                "Compare only visible evidence and choose one suitable image ID, or abstain.",
                "Mechanical focus, exposure, and duplicate scores are advisory; there is no temporal score.",
                "An image with resolution_warning=true is below 1024 pixels on its long side; the Hunyuan guard rejects it.",
                json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                'Return one JSON object: {"selected_image_id": "img_0001" or null, "evidence": "...", "uncertainty": "...", "confidence_1_to_5": 1}.',
            ]
        )
        + "\n"
    )
