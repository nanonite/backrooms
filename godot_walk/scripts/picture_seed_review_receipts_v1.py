"""Build picture seed-review receipt identity and append-only payloads."""

from __future__ import annotations

from typing import Any

from seed_review_paths import canonical_sha256, sha256_text
from seed_review_provider import ModelIdentity, ModelInvocation, build_opencode_command
from seed_review_response import RecordedResponse
from seed_review_usage import UsageMetadata


def input_fingerprint(
    review: dict[str, Any],
    invocation: ModelInvocation,
    identity: ModelIdentity,
    invocation_mode: str,
    replay_response: RecordedResponse | None,
) -> str:
    return canonical_sha256(
        {
            "review_spec": review["review_spec"],
            "review_spec_version": review["review_spec_version"],
            "review_request_sha256": canonical_sha256(review),
            "source_image_set_sha256": review["source_image_set_sha256"],
            "reviewed_images": [
                {"image_id": image["image_id"], "sha256": image["sha256"]}
                for image in review["candidates"]
            ],
            "model_reference": identity.reference,
            "image_input_supported": identity.image_input_supported,
            "prompt_sha256": sha256_text(invocation.prompt),
            "timeout_seconds": round(invocation.timeout_seconds, 6),
            "invocation_mode": invocation_mode,
            "replay_response_sha256": (
                replay_response.fixture_sha256 if replay_response else None
            ),
        }
    )


def receipt_command(identity: ModelIdentity, invocation: ModelInvocation) -> list[str]:
    if identity.provider != "opencode":
        return []
    return build_opencode_command(
        identity.reference, invocation.image_paths, invocation.prompt
    )


def build_receipt(
    *,
    created_at: str,
    review: dict[str, Any],
    identity: ModelIdentity,
    invocation: ModelInvocation,
    invocation_mode: str,
    command: list[str],
    started_at: str,
    finished_at: str,
    elapsed_seconds: float,
    fixture_path: str | None,
    fixture_sha256: str | None,
    status: str,
    result: dict[str, Any],
    usage: UsageMetadata,
    input_fingerprint_value: str,
    paid_call_allowed: bool,
    hard_cost_ceiling_usd: float | None,
    provider_enforces_spend_limit: bool,
    model_invoked: bool,
    error: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "receipt_spec": "picture_seed_review_receipt_v1",
        "stage": "picture_seed_review",
        "status": status,
        "input_fingerprint": input_fingerprint_value,
        "created_at_utc": created_at,
        "invocation_mode": invocation_mode,
        "requires_operator_review": True,
        "operator_decision_recorded": False,
        "next_stage_authorized": False,
        "source": _source(review),
        "review_request": review,
        "review_request_sha256": canonical_sha256(review),
        "reviewed_images": _reviewed_images(review),
        "model": identity.to_dict(),
        "prompt": _prompt(invocation, review),
        "request": _request(
            invocation,
            command,
            started_at,
            finished_at,
            elapsed_seconds,
            fixture_path,
            fixture_sha256,
        ),
        "result": result,
        "usage": usage.to_dict(),
        "guards": _guards(
            model_invoked,
            paid_call_allowed,
            hard_cost_ceiling_usd,
            provider_enforces_spend_limit,
        ),
        "limitations": _limitations(invocation_mode, usage, error),
    }


def _source(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_kind": review["source_kind"],
        "source_id": review["source_id"],
        "source_image_set_sha256": review["source_image_set_sha256"],
        "source_manifest_path": review["source_manifest_path"],
        "source_manifest_sha256": review["source_manifest_sha256"],
    }


def _reviewed_images(review: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"image_id": image["image_id"], "sha256": image["sha256"]}
        for image in review["candidates"]
    ]


def _prompt(invocation: ModelInvocation, review: dict[str, Any]) -> dict[str, str]:
    return {
        "version": review["review_spec"],
        "text": invocation.prompt,
        "sha256": sha256_text(invocation.prompt),
    }


def _request(
    invocation: ModelInvocation,
    command: list[str],
    started_at: str,
    finished_at: str,
    elapsed_seconds: float,
    fixture_path: str | None,
    fixture_sha256: str | None,
) -> dict[str, Any]:
    return {
        "timeout_seconds": invocation.timeout_seconds,
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "elapsed_seconds": round(float(elapsed_seconds), 3),
        "command": command,
        "response_fixture_path": fixture_path,
        "response_fixture_sha256": fixture_sha256,
    }


def _guards(
    model_invoked: bool,
    paid_call_allowed: bool,
    hard_cost_ceiling_usd: float | None,
    provider_enforces_spend_limit: bool,
) -> dict[str, Any]:
    return {
        "model_invoked": model_invoked,
        "paid_call_allowed": paid_call_allowed,
        "hard_cost_ceiling_usd": hard_cost_ceiling_usd,
        "provider_enforces_spend_limit": provider_enforces_spend_limit,
        "automatic_retry_allowed": False,
        "max_candidates": 3,
        "direct_original_bytes_only": True,
        "registration_accepted": False,
        "scale_calibrated": False,
        "hunyuan_authorized": False,
    }


def _limitations(
    invocation_mode: str, usage: UsageMetadata, error: str | None
) -> list[str]:
    limitations = [
        "Model output is advisory; it does not record operator approval.",
        "Only the exact full-resolution originals listed in the request were reviewed.",
        "capture_index is file order for an unrelated picture collection, not time.",
        "Low-resolution images remain flagged and the Hunyuan guard rejects them.",
        "This receipt does not authorize Hunyuan or catalog admission.",
    ]
    if invocation_mode == "replayed_recorded_response":
        limitations.append("Response was replayed from a recorded fixture; no model was called.")
    if not usage.reported:
        limitations.append("The provider or fixture did not report token usage or cost.")
    if error:
        limitations.append(error)
    return limitations
