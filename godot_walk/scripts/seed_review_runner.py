"""Orchestrate one bounded, receipt-backed seed-review stage."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from seed_review_candidates import (
    CandidateSet,
    candidates_from_document,
    prepare_candidates,
)
from seed_review_errors import SeedReviewError
from seed_review_paths import (
    DEFAULT_RECEIPTS_DIR,
    ROOT,
    canonical_sha256,
    read_json_object,
    resolve_repo_path,
    sha256_text,
)
from seed_review_prompt import build_prompt
from seed_review_provider import (
    ModelIdentity,
    ModelInvocation,
    ProviderResponse,
    SeedReviewModel,
    build_opencode_command,
    enforce_model_policy,
)
from seed_review_receipts import (
    build_input_fingerprint,
    finalize_receipt,
    find_existing_receipt,
    write_receipt,
)
from seed_review_response import (
    RecordedResponse,
    normalise_response,
    parse_response_text,
    response_text,
)
from seed_review_schemas import validate_receipt, validate_request, validate_response
from seed_review_sources import SourceRecord, load_source_record
from seed_review_usage import UsageMetadata, unavailable_usage, usage_from_payload
from seed_review_workflow import WorkflowSpec, load_workflow_spec

EXIT_OK = 0
EXIT_CONTRACT = 1
EXIT_OPERATOR_REVIEW = 2
EXIT_FAIL_CLOSED = 3
MODEL_FAILURE_STATUSES = {"timed_out", "provider_error", "invalid_response"}
EMPTY_RESULT: dict[str, Any] = {
    "selection_status": "not_available",
    "selected_frame_id": None,
    "selected_index_zero_based": None,
    "selected_pts_seconds": None,
    "selected_frame_sha256": None,
    "ranked_alternatives": [],
    "confidence_1_to_5": None,
    "confidence_threshold": 3,
    "evidence": None,
    "uncertainty": None,
    "raw_response_sha256": None,
    "raw_response": None,
    "error": None,
}


@dataclass(frozen=True)
class SeedReviewRun:
    status: str
    receipt: dict[str, Any]
    receipt_path: Path | None
    command: tuple[str, ...]
    exit_code: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "receipt_path": (
                self.receipt_path.as_posix() if self.receipt_path else None
            ),
            "command": list(self.command),
            "receipt": self.receipt,
        }


def run_seed_review(
    *,
    source_id: str,
    request_document: dict[str, Any],
    identity: ModelIdentity,
    request_path: str | None = None,
    root: Path = ROOT,
    spec: WorkflowSpec | None = None,
    model: SeedReviewModel | None = None,
    replay_response: RecordedResponse | None = None,
    enable_model: bool = False,
    dry_run: bool = False,
    allow_mechanical_shortlist: bool = False,
    receipts_dir: Path | None = None,
    timeout_seconds: float | None = None,
    confidence_threshold: int | None = None,
    hard_cost_ceiling_usd: float | None = None,
    provider_enforces_spend_limit: bool = False,
    now: Callable[[], str] = lambda: datetime.now(timezone.utc).isoformat(),
) -> SeedReviewRun:
    spec = spec or load_workflow_spec(root)
    source = load_source_record(source_id, root)
    request_document = _verified_request_document(
        source_id, request_document, request_path, root, spec
    )
    candidate_set = prepare_candidates(
        candidates_from_document(request_document),
        source,
        root,
        allow_mechanical_shortlist=allow_mechanical_shortlist,
    )
    prompt = build_prompt(candidate_set, source, spec)
    prompt_sha256 = sha256_text(prompt)
    timeout = _timeout(spec, timeout_seconds)
    threshold = _confidence_threshold(spec, confidence_threshold)
    invocation_mode = _invocation_mode(dry_run, replay_response)
    paid_call_allowed = _paid_call_policy(
        dry_run,
        replay_response,
        enable_model,
        identity,
        hard_cost_ceiling_usd,
        provider_enforces_spend_limit,
    )
    directory = receipts_dir or DEFAULT_RECEIPTS_DIR
    fingerprint = build_input_fingerprint(
        spec=spec,
        source=source,
        candidate_set=candidate_set,
        identity=identity,
        prompt_sha256=prompt_sha256,
        timeout_seconds=timeout,
        confidence_threshold=threshold,
        invocation_mode=invocation_mode,
        replay_response_sha256=(
            replay_response.fixture_sha256 if replay_response else None
        ),
    )
    existing = find_existing_receipt(directory, source_id, fingerprint, root)
    if existing is not None and not dry_run:
        raise SeedReviewError(
            "stage_already_completed",
            "An identical seed-review input already has an append-only receipt",
            details={"receipt_path": existing.get("path")},
        )
    command = _receipt_command(identity, candidate_set, prompt, root)
    started_at = now()
    response, usage, raw_text, fixture_path, fixture_sha256 = _execute(
        dry_run=dry_run,
        enable_model=enable_model,
        model=model,
        replay_response=replay_response,
        identity=identity,
        prompt=prompt,
        candidate_set=candidate_set,
        timeout=timeout,
        root=root,
        listed_price_usd=identity.listed_price_usd,
    )
    finished_at = now()
    status, result, error = _status_and_result(
        dry_run=dry_run,
        response=response,
        raw_text=raw_text,
        candidate_set=candidate_set,
        threshold=threshold,
        spec=spec,
    )
    receipt = _receipt(
        created_at=finished_at,
        spec=spec,
        source=source,
        candidate_set=candidate_set,
        identity=identity,
        prompt=prompt,
        prompt_sha256=prompt_sha256,
        timeout=timeout,
        threshold=threshold,
        invocation_mode=invocation_mode,
        request_path=request_path,
        request_document=request_document,
        command=command,
        started_at=started_at,
        finished_at=finished_at,
        elapsed_seconds=(response.elapsed_seconds if response is not None else 0.0),
        fixture_path=fixture_path,
        fixture_sha256=fixture_sha256,
        status=status,
        result=result,
        usage=usage,
        input_fingerprint=fingerprint,
        paid_call_allowed=paid_call_allowed,
        hard_cost_ceiling_usd=hard_cost_ceiling_usd,
        provider_enforces_spend_limit=provider_enforces_spend_limit,
        model_invoked=(invocation_mode == "live_model_call" and response is not None),
        error=error,
    )
    receipt = finalize_receipt(receipt)
    validate_receipt(receipt, spec)
    receipt_path = None
    if not dry_run:
        receipt_path = write_receipt(receipt, directory, root)
    return SeedReviewRun(
        status=status,
        receipt=receipt,
        receipt_path=receipt_path,
        command=tuple(command),
        exit_code=_exit_code(status),
    )


def _verified_request_document(
    source_id: str,
    document: dict[str, Any],
    request_path: str | None,
    root: Path,
    spec: WorkflowSpec,
) -> dict[str, Any]:
    validate_request(document, spec)
    if document["source_id"] != source_id:
        raise SeedReviewError(
            "source_mismatch", "Request source ID does not match --source-id"
        )
    if request_path is not None:
        path = resolve_repo_path(request_path, root, require_file=True)
        file_document = read_json_object(path, "seed-review request")
        if canonical_sha256(file_document) != canonical_sha256(document):
            raise SeedReviewError(
                "request_changed", "Request file changed while it was being read"
            )
    return document


def _timeout(spec: WorkflowSpec, value: float | None) -> float:
    timeout = spec.default_timeout_seconds if value is None else float(value)
    if timeout <= 0 or timeout > spec.max_timeout_seconds:
        raise SeedReviewError(
            "invalid_timeout",
            f"Timeout must be between 0 and {spec.max_timeout_seconds:g} seconds",
        )
    return timeout


def _confidence_threshold(spec: WorkflowSpec, value: int | None) -> int:
    threshold = spec.default_confidence_threshold if value is None else int(value)
    if threshold < 1 or threshold > 5:
        raise SeedReviewError(
            "invalid_confidence_threshold",
            "Confidence threshold must be between 1 and 5",
        )
    return threshold


def _invocation_mode(dry_run: bool, replay_response: RecordedResponse | None) -> str:
    if dry_run:
        return "dry_run"
    if replay_response is not None:
        return "replayed_recorded_response"
    return "live_model_call"


def _paid_call_policy(
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


def _execute(
    *,
    dry_run: bool,
    enable_model: bool,
    model: SeedReviewModel | None,
    replay_response: RecordedResponse | None,
    identity: ModelIdentity,
    prompt: str,
    candidate_set: CandidateSet,
    timeout: float,
    root: Path,
    listed_price_usd: float | None,
) -> tuple[
    ProviderResponse | None,
    UsageMetadata,
    str | None,
    str | None,
    str | None,
]:
    if dry_run:
        return None, unavailable_usage(listed_price_usd), None, None, None
    if replay_response is not None:
        raw_text = response_text(replay_response.response)
        usage = usage_from_payload(
            replay_response.usage_payload,
            listed_price_usd,
            source="recorded_fixture",
        )
        return (
            None,
            usage,
            raw_text,
            replay_response.fixture_path,
            replay_response.fixture_sha256,
        )
    if not enable_model:
        raise SeedReviewError(
            "model_stage_not_enabled",
            "Live model calls require the explicit --enable-model flag",
        )
    if model is None:
        raise SeedReviewError(
            "model_not_configured", "No seed-review model adapter was provided"
        )
    image_paths = tuple(
        resolve_repo_path(item.candidate.path, root, require_file=True)
        for item in candidate_set.reviewed
    )
    response = model.invoke(
        ModelInvocation(
            identity=identity,
            prompt=prompt,
            image_paths=image_paths,
            timeout_seconds=timeout,
        )
    )
    usage = usage_from_payload(response.usage_payload, listed_price_usd)
    return (
        response,
        usage,
        response.raw_text or None,
        None,
        None,
    )


def _status_and_result(
    *,
    dry_run: bool,
    response: ProviderResponse | None,
    raw_text: str | None,
    candidate_set: CandidateSet,
    threshold: int,
    spec: WorkflowSpec,
) -> tuple[str, dict[str, Any], str | None]:
    if dry_run:
        result = {**EMPTY_RESULT, "ranked_alternatives": []}
        result["confidence_threshold"] = threshold
        return "dry_run", result, None
    if response is not None and response.status == "timed_out":
        return (
            "timed_out",
            _failure_result(raw_text, response.error, threshold),
            response.error,
        )
    if response is not None and response.status != "completed":
        error = response.error or "Provider returned an error"
        return "provider_error", _failure_result(raw_text, error, threshold), error
    if raw_text is None:
        error = "Provider returned no response text"
        return "invalid_response", _failure_result(None, error, threshold), error
    try:
        document = parse_response_text(raw_text)
        validate_response(document, spec)
        normalised = normalise_response(
            document,
            {item.candidate.frame_id for item in candidate_set.reviewed},
            threshold,
        )
    except SeedReviewError as error:
        return (
            "invalid_response",
            _failure_result(raw_text, str(error), threshold),
            str(error),
        )
    result = _selected_result(normalised, candidate_set, threshold, raw_text)
    if normalised["selection_status"] == "abstained":
        return "abstained", result, None
    if normalised["requires_operator_review"]:
        return "completed_low_confidence", result, None
    return "completed", result, None


def _selected_result(
    normalised: dict[str, Any],
    candidate_set: CandidateSet,
    threshold: int,
    raw_text: str,
) -> dict[str, Any]:
    selected_id = normalised["selected_frame_id"]
    selected = next(
        (
            item.candidate
            for item in candidate_set.reviewed
            if item.candidate.frame_id == selected_id
        ),
        None,
    )
    return {
        "selection_status": normalised["selection_status"],
        "selected_frame_id": selected_id,
        "selected_index_zero_based": (selected.index_zero_based if selected else None),
        "selected_pts_seconds": selected.pts_seconds if selected else None,
        "selected_frame_sha256": selected.sha256 if selected else None,
        "ranked_alternatives": normalised["ranked_alternatives"],
        "confidence_1_to_5": normalised["confidence_1_to_5"],
        "confidence_threshold": threshold,
        "evidence": normalised["evidence"],
        "uncertainty": normalised["uncertainty"],
        "raw_response_sha256": sha256_text(raw_text),
        "raw_response": raw_text,
        "error": None,
    }


def _failure_result(raw_text: str | None, error: str, threshold: int) -> dict[str, Any]:
    result = {**EMPTY_RESULT, "ranked_alternatives": []}
    result["confidence_threshold"] = threshold
    result["raw_response_sha256"] = sha256_text(raw_text) if raw_text else None
    result["raw_response"] = raw_text
    result["error"] = error
    return result


def _receipt_command(
    identity: ModelIdentity,
    candidate_set: CandidateSet,
    prompt: str,
    root: Path,
) -> list[str]:
    if identity.provider != "opencode":
        return []
    image_paths = tuple(
        resolve_repo_path(item.candidate.path, root, require_file=True)
        for item in candidate_set.reviewed
    )
    return build_opencode_command(identity.reference, image_paths, prompt)


def _receipt(
    *,
    created_at: str,
    spec: WorkflowSpec,
    source: SourceRecord,
    candidate_set: CandidateSet,
    identity: ModelIdentity,
    prompt: str,
    prompt_sha256: str,
    timeout: float,
    threshold: int,
    invocation_mode: str,
    request_path: str | None,
    request_document: dict[str, Any],
    command: list[str],
    started_at: str,
    finished_at: str,
    elapsed_seconds: float,
    fixture_path: str | None,
    fixture_sha256: str | None,
    status: str,
    result: dict[str, Any],
    usage: UsageMetadata,
    input_fingerprint: str,
    paid_call_allowed: bool,
    hard_cost_ceiling_usd: float | None,
    provider_enforces_spend_limit: bool,
    model_invoked: bool,
    error: str | None,
) -> dict[str, Any]:
    limitations = [
        (
            "Mechanical metrics are relative within this candidate set, not "
            "absolute image-quality thresholds."
        ),
        "Model visual claims are recorded but were not independently verified.",
        (
            "This stage does not authorize Hunyuan, room authoring, catalog "
            "admission, or issue closure."
        ),
        (
            "Confidence below the threshold, abstention, timeout, provider "
            "error, or invalid output requires operator review."
        ),
    ]
    if invocation_mode == "replayed_recorded_response":
        limitations.append(
            "Response was replayed from a recorded fixture; no model was called."
        )
    if not usage.reported:
        limitations.append(
            "The provider or fixture did not report token usage or cost."
        )
    return {
        "schema_version": 1,
        "workflow_spec_version": spec.spec_version,
        "stage": "seed_review",
        "status": status,
        "input_fingerprint": input_fingerprint,
        "created_at_utc": created_at,
        "invocation_mode": invocation_mode,
        "requires_operator_review": status not in {"completed", "dry_run"},
        "next_stage_authorized": False,
        "source": source.to_dict(),
        "candidate_set": candidate_set.to_dict(),
        "model": identity.to_dict(),
        "prompt": {
            "version": spec.prompt_version,
            "text": prompt,
            "sha256": prompt_sha256,
        },
        "request": {
            "timeout_seconds": timeout,
            "started_at_utc": started_at,
            "finished_at_utc": finished_at,
            "elapsed_seconds": round(float(elapsed_seconds), 3),
            "command": command,
            "response_fixture_path": fixture_path,
            "response_fixture_sha256": fixture_sha256,
        },
        "result": result,
        "usage": usage.to_dict(),
        "guards": {
            "model_invoked": model_invoked,
            "paid_call_allowed": paid_call_allowed,
            "hard_cost_ceiling_usd": hard_cost_ceiling_usd,
            "provider_enforces_spend_limit": provider_enforces_spend_limit,
            "automatic_retry_allowed": False,
            "max_candidates": spec.max_candidates,
            "timeout_within_limit": timeout <= spec.max_timeout_seconds,
            "registration_accepted": False,
            "scale_calibrated": False,
        },
        "artifacts": {
            "workflow_spec_path": spec.manifest_path,
            "workflow_spec_sha256": spec.manifest_sha256,
            "request_schema_path": spec.schema_paths["request"],
            "request_schema_sha256": spec.schema_sha256["request"],
            "response_schema_path": spec.schema_paths["response"],
            "response_schema_sha256": spec.schema_sha256["response"],
            "receipt_schema_path": spec.schema_paths["receipt"],
            "receipt_schema_sha256": spec.schema_sha256["receipt"],
            "request_path": request_path,
            "request_sha256": canonical_sha256(request_document),
        },
        "limitations": limitations,
    }


def _exit_code(status: str) -> int:
    if status in {"completed", "dry_run"}:
        return EXIT_OK
    if status in {"completed_low_confidence", "abstained"}:
        return EXIT_OPERATOR_REVIEW
    return EXIT_FAIL_CLOSED


def receipt_as_json(receipt: dict[str, Any]) -> str:
    return json.dumps(receipt, indent=2, ensure_ascii=False)
