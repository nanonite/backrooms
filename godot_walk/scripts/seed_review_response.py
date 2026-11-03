"""Parse, normalise, and replay bounded seed-review model responses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seed_review_errors import SeedReviewError
from seed_review_paths import (
    canonical_sha256,
    read_json_object,
    repo_relative,
    sha256_file,
)


@dataclass(frozen=True)
class RecordedResponse:
    response: dict[str, Any]
    fixture_path: str | None
    fixture_sha256: str | None
    usage_payload: dict[str, Any] | None
    provenance: dict[str, Any] | None


def extract_json_object(text: str) -> dict[str, Any]:
    """Return the last JSON object in text that carries a seed selection."""
    decoder = json.JSONDecoder()
    found: dict[str, Any] | None = None
    for position, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[position:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "selected_frame_id" in value:
            found = value
    if found is None:
        raise SeedReviewError(
            "invalid_response",
            "Model output did not contain a seed-review JSON object",
        )
    return found


def parse_response_text(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise SeedReviewError("invalid_response", "Model returned an empty response")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return extract_json_object(text)
    if not isinstance(value, dict):
        raise SeedReviewError(
            "invalid_response", "Model response must be one JSON object"
        )
    return value


def normalise_response(
    response: dict[str, Any],
    candidate_ids: set[str],
    confidence_threshold: int,
) -> dict[str, Any]:
    selected = response.get("selected_frame_id")
    if selected is not None and (
        not isinstance(selected, str) or selected not in candidate_ids
    ):
        raise SeedReviewError(
            "invalid_response",
            "Selected frame is not in the reviewed candidate set",
            details={"selected_frame_id": selected},
        )
    alternatives = response.get("ranked_alternatives")
    if not isinstance(alternatives, list) or any(
        not isinstance(item, str) or item not in candidate_ids for item in alternatives
    ):
        raise SeedReviewError(
            "invalid_response",
            "Ranked alternatives must name reviewed candidate frames",
        )
    if len(set(alternatives)) != len(alternatives) or selected in alternatives:
        raise SeedReviewError(
            "invalid_response",
            "Ranked alternatives must be unique and exclude the selected frame",
        )
    confidence = response.get("confidence_1_to_5")
    if isinstance(confidence, bool) or not isinstance(confidence, int):
        raise SeedReviewError(
            "invalid_response", "Confidence must be an integer from 1 to 5"
        )
    if confidence < 1 or confidence > 5:
        raise SeedReviewError(
            "invalid_response", "Confidence must be an integer from 1 to 5"
        )
    evidence = response.get("evidence")
    uncertainty = response.get("uncertainty")
    if not isinstance(evidence, str) or not evidence.strip():
        raise SeedReviewError("invalid_response", "Evidence must be nonempty text")
    if not isinstance(uncertainty, str) or not uncertainty.strip():
        raise SeedReviewError("invalid_response", "Uncertainty must be nonempty text")
    if response.get("use_original_frame_not_a_composite") is not True:
        raise SeedReviewError(
            "invalid_response",
            "Model must affirm use_original_frame_not_a_composite=true",
        )
    selection_status = "abstained" if selected is None else "selected"
    return {
        "selection_status": selection_status,
        "selected_frame_id": selected,
        "ranked_alternatives": list(alternatives),
        "confidence_1_to_5": confidence,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "requires_operator_review": (
            selected is None or confidence < confidence_threshold
        ),
    }


def load_recorded_response(path: Path, root: Path) -> RecordedResponse:
    document = read_json_object(path, "recorded seed-review response")
    if isinstance(document.get("response"), dict):
        response = document["response"]
        usage = (
            document.get("usage") if isinstance(document.get("usage"), dict) else None
        )
        provenance = (
            document.get("provenance")
            if isinstance(document.get("provenance"), dict)
            else None
        )
    else:
        response = document
        usage = None
        provenance = None
    return RecordedResponse(
        response=response,
        fixture_path=repo_relative(path, root),
        fixture_sha256=sha256_file(path),
        usage_payload=usage,
        provenance=provenance,
    )


def response_text(response: dict[str, Any]) -> str:
    return json.dumps(response, sort_keys=True, ensure_ascii=False)


def response_sha256(response: dict[str, Any]) -> str:
    return canonical_sha256(response)
