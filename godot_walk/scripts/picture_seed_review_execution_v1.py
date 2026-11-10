"""Apply model call gates and execute or replay one picture review."""

from __future__ import annotations

from seed_review_errors import SeedReviewError
from seed_review_provider import (
    ModelIdentity,
    ModelInvocation,
    ProviderResponse,
    SeedReviewModel,
    enforce_model_policy,
)
from seed_review_response import RecordedResponse, response_text
from seed_review_usage import UsageMetadata, unavailable_usage, usage_from_payload
from seed_review_workflow import WorkflowSpec


def timeout_value(spec: WorkflowSpec, value: float | None) -> float:
    timeout = spec.default_timeout_seconds if value is None else float(value)
    if timeout <= 0 or timeout > spec.max_timeout_seconds:
        raise SeedReviewError(
            "invalid_timeout",
            f"Timeout must be between 0 and {spec.max_timeout_seconds:g} seconds",
        )
    return timeout


def confidence_threshold(spec: WorkflowSpec, value: int | None) -> int:
    threshold = spec.default_confidence_threshold if value is None else int(value)
    if threshold < 1 or threshold > 5:
        raise SeedReviewError(
            "invalid_confidence_threshold",
            "Confidence threshold must be between 1 and 5",
        )
    return threshold


def invocation_mode(
    dry_run: bool, replay_response: RecordedResponse | None
) -> str:
    if dry_run:
        return "dry_run"
    if replay_response is not None:
        return "replayed_recorded_response"
    return "live_model_call"


def paid_call_allowed(
    dry_run: bool,
    replay_response: RecordedResponse | None,
    enable_model: bool,
    identity: ModelIdentity,
    hard_cost_ceiling_usd: float | None,
    provider_enforces_spend_limit: bool,
) -> bool:
    if dry_run or replay_response is not None or not enable_model:
        return False
    return enforce_model_policy(
        identity, hard_cost_ceiling_usd, provider_enforces_spend_limit
    )


def execute_invocation(
    *,
    invocation: ModelInvocation,
    dry_run: bool,
    enable_model: bool,
    model: SeedReviewModel | None,
    replay_response: RecordedResponse | None,
    listed_price_usd: float | None,
) -> tuple[ProviderResponse | None, UsageMetadata, str | None, str | None, str | None]:
    if dry_run:
        return None, unavailable_usage(listed_price_usd), None, None, None
    if replay_response is not None:
        return _replay(replay_response, listed_price_usd)
    if not enable_model:
        raise SeedReviewError(
            "model_stage_not_enabled",
            "Live model calls require the explicit --enable-model flag",
        )
    if model is None:
        raise SeedReviewError(
            "model_not_configured", "No picture seed-review model adapter was provided"
        )
    return _invoke(model, invocation, listed_price_usd)


def _replay(
    replay: RecordedResponse, listed_price_usd: float | None
) -> tuple[None, UsageMetadata, str, str | None, str | None]:
    return (
        None,
        usage_from_payload(
            replay.usage_payload, listed_price_usd, source="recorded_fixture"
        ),
        response_text(replay.response),
        replay.fixture_path,
        replay.fixture_sha256,
    )


def _invoke(
    model: SeedReviewModel,
    invocation: ModelInvocation,
    listed_price_usd: float | None,
) -> tuple[ProviderResponse, UsageMetadata, str | None, None, None]:
    response = model.invoke(invocation)
    return (
        response,
        usage_from_payload(response.usage_payload, listed_price_usd),
        response.raw_text or None,
        None,
        None,
    )
