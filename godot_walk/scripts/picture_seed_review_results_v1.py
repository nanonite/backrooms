"""Validate advisory model responses for picture-set seed review v1."""

from __future__ import annotations

from typing import Any

from seed_review_errors import SeedReviewError
from seed_review_paths import sha256_text
from seed_review_provider import ProviderResponse
from seed_review_response import parse_response_text


def status_and_result(
    *,
    dry_run: bool,
    response: ProviderResponse | None,
    raw_text: str | None,
    review: dict[str, Any],
    threshold: int,
) -> tuple[str, dict[str, Any], str | None]:
    if dry_run:
        return "dry_run", _empty_result(threshold), None
    if response is not None and response.status == "timed_out":
        error = response.error or "Provider timed out"
        return "timed_out", _failure_result(raw_text, error, threshold), error
    if response is not None and response.status != "completed":
        error = response.error or "Provider returned an error"
        return "provider_error", _failure_result(raw_text, error, threshold), error
    if raw_text is None:
        error = "Provider returned no response text"
        return "invalid_response", _failure_result(None, error, threshold), error
    return _parse_model_result(raw_text, review, threshold)


def _parse_model_result(
    raw_text: str, review: dict[str, Any], threshold: int
) -> tuple[str, dict[str, Any], str | None]:
    try:
        selected = _normalise_picture_response(
            parse_response_text(raw_text),
            {image["image_id"] for image in review["candidates"]},
        )
    except SeedReviewError as error:
        return (
            "invalid_response",
            _failure_result(raw_text, str(error), threshold),
            str(error),
        )
    result = _selected_result(selected, review, threshold, raw_text)
    if selected["selected_image_id"] is None:
        return "abstained", result, None
    if selected["confidence_1_to_5"] < threshold:
        return "completed_low_confidence", result, None
    return "completed", result, None


def _normalise_picture_response(
    response: dict[str, Any], candidate_ids: set[str]
) -> dict[str, Any]:
    selected = response.get("selected_image_id")
    if selected is not None and (
        not isinstance(selected, str) or selected not in candidate_ids
    ):
        raise SeedReviewError(
            "invalid_response", "Selected image is not in the reviewed candidate set"
        )
    confidence = response.get("confidence_1_to_5")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, int)
        or not 1 <= confidence <= 5
    ):
        raise SeedReviewError(
            "invalid_response", "Confidence must be an integer from 1 to 5"
        )
    evidence = response.get("evidence")
    uncertainty = response.get("uncertainty")
    if not isinstance(evidence, str) or not evidence.strip():
        raise SeedReviewError("invalid_response", "Evidence must be nonempty text")
    if not isinstance(uncertainty, str) or not uncertainty.strip():
        raise SeedReviewError("invalid_response", "Uncertainty must be nonempty text")
    return {
        "selected_image_id": selected,
        "confidence_1_to_5": confidence,
        "evidence": evidence,
        "uncertainty": uncertainty,
    }


def _selected_result(
    selected: dict[str, Any],
    review: dict[str, Any],
    threshold: int,
    raw_text: str,
) -> dict[str, Any]:
    candidate = next(
        (
            image
            for image in review["candidates"]
            if image["image_id"] == selected["selected_image_id"]
        ),
        None,
    )
    return {
        "selection_status": "abstained" if candidate is None else "selected",
        **selected,
        "selected_image_sha256": candidate["sha256"] if candidate else None,
        "resolution_warning": candidate["resolution_warning"] if candidate else None,
        "confidence_threshold": threshold,
        "raw_response_sha256": sha256_text(raw_text),
        "raw_response": raw_text,
        "error": None,
    }


def _empty_result(threshold: int) -> dict[str, Any]:
    return {
        "selection_status": "not_available",
        "selected_image_id": None,
        "selected_image_sha256": None,
        "resolution_warning": None,
        "confidence_1_to_5": None,
        "confidence_threshold": threshold,
        "evidence": None,
        "uncertainty": None,
        "raw_response_sha256": None,
        "raw_response": None,
        "error": None,
    }


def _failure_result(
    raw_text: str | None, error: str, threshold: int
) -> dict[str, Any]:
    result = _empty_result(threshold)
    result["raw_response_sha256"] = sha256_text(raw_text) if raw_text else None
    result["raw_response"] = raw_text
    result["error"] = error
    return result
