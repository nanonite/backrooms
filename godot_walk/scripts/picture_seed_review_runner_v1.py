"""Run advisory model review for a versioned picture-set seed request."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from picture_seed_review_invocation_v1 import build_picture_model_invocation
from picture_seed_review_receipts_v1 import (
    build_receipt,
    input_fingerprint,
    receipt_command,
)
from picture_seed_review_results_v1 import status_and_result
from picture_seed_review_v1 import build_picture_seed_review
from picture_seed_review_execution_v1 import (
    confidence_threshold,
    execute_invocation,
    invocation_mode,
    paid_call_allowed,
    timeout_value,
)
from seed_review_errors import SeedReviewError
from seed_review_paths import DEFAULT_RECEIPTS_DIR, ROOT
from seed_review_provider import (
    ModelIdentity,
    ModelInvocation,
    ProviderResponse,
    SeedReviewModel,
)
from seed_review_receipts import finalize_receipt, find_existing_receipt, write_receipt
from seed_review_response import RecordedResponse
from seed_review_usage import UsageMetadata
from seed_review_workflow import WorkflowSpec, load_workflow_spec

EXIT_OK = 0
EXIT_OPERATOR_REVIEW = 2
EXIT_FAIL_CLOSED = 3


@dataclass(frozen=True)
class PictureSeedReviewRun:
    status: str
    receipt: dict[str, Any]
    receipt_path: Path | None
    command: tuple[str, ...]
    exit_code: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "receipt_path": self.receipt_path.as_posix() if self.receipt_path else None,
            "command": list(self.command),
            "receipt": self.receipt,
        }


@dataclass(frozen=True)
class _Options:
    source_id: str
    identity: ModelIdentity
    root: Path
    spec: WorkflowSpec | None
    model: SeedReviewModel | None
    replay_response: RecordedResponse | None
    enable_model: bool
    dry_run: bool
    receipts_dir: Path | None
    timeout_seconds: float | None
    confidence_threshold: int | None
    hard_cost_ceiling_usd: float | None
    provider_enforces_spend_limit: bool
    now: Callable[[], str]


@dataclass(frozen=True)
class _PreparedReview:
    review: dict[str, Any]
    invocation: ModelInvocation
    threshold: int
    mode: str
    paid_call_allowed: bool
    fingerprint: str
    directory: Path
    command: list[str]


@dataclass(frozen=True)
class _Execution:
    response: ProviderResponse | None
    usage: UsageMetadata
    fixture_path: str | None
    fixture_sha256: str | None
    status: str
    result: dict[str, Any]
    error: str | None


def run_picture_seed_review(
    *,
    source_id: str,
    identity: ModelIdentity,
    root: Path = ROOT,
    spec: WorkflowSpec | None = None,
    model: SeedReviewModel | None = None,
    replay_response: RecordedResponse | None = None,
    enable_model: bool = False,
    dry_run: bool = False,
    receipts_dir: Path | None = None,
    timeout_seconds: float | None = None,
    confidence_threshold: int | None = None,
    hard_cost_ceiling_usd: float | None = None,
    provider_enforces_spend_limit: bool = False,
    now: Callable[[], str] = lambda: datetime.now(timezone.utc).isoformat(),
) -> PictureSeedReviewRun:
    options = _Options(
        source_id,
        identity,
        root,
        spec,
        model,
        replay_response,
        enable_model,
        dry_run,
        receipts_dir,
        timeout_seconds,
        confidence_threshold,
        hard_cost_ceiling_usd,
        provider_enforces_spend_limit,
        now,
    )
    return _run(options)


def _run(options: _Options) -> PictureSeedReviewRun:
    prepared = _prepare(options)
    started_at = options.now()
    execution = _execute(options, prepared)
    finished_at = options.now()
    receipt = _build_receipt(options, prepared, started_at, finished_at, execution)
    receipt_path = _write_receipt(options, prepared, receipt)
    return PictureSeedReviewRun(
        status=receipt["status"],
        receipt=receipt,
        receipt_path=receipt_path,
        command=tuple(prepared.command),
        exit_code=_exit_code(receipt["status"]),
    )


def _prepare(options: _Options) -> _PreparedReview:
    spec = options.spec or load_workflow_spec()
    review = build_picture_seed_review(options.source_id, options.root)
    timeout = timeout_value(spec, options.timeout_seconds)
    threshold = confidence_threshold(spec, options.confidence_threshold)
    invocation = build_picture_model_invocation(
        review, options.identity, options.root, timeout_seconds=timeout
    )
    mode = invocation_mode(options.dry_run, options.replay_response)
    paid = paid_call_allowed(
        options.dry_run,
        options.replay_response,
        options.enable_model,
        options.identity,
        options.hard_cost_ceiling_usd,
        options.provider_enforces_spend_limit,
    )
    fingerprint = input_fingerprint(
        review, invocation, options.identity, mode, options.replay_response
    )
    directory = options.receipts_dir or DEFAULT_RECEIPTS_DIR
    _refuse_duplicate(options, directory, fingerprint)
    return _PreparedReview(
        review,
        invocation,
        threshold,
        mode,
        paid,
        fingerprint,
        directory,
        receipt_command(options.identity, invocation),
    )


def _refuse_duplicate(options: _Options, directory: Path, fingerprint: str) -> None:
    if options.dry_run:
        return
    existing = find_existing_receipt(
        directory, options.source_id, fingerprint, options.root
    )
    if existing is not None:
        raise SeedReviewError(
            "stage_already_completed",
            "An identical picture seed-review input already has an append-only receipt",
            details={"receipt_path": existing.get("path")},
        )


def _execute(
    options: _Options, prepared: _PreparedReview
) -> _Execution:
    response, usage, raw_text, fixture_path, fixture_sha256 = execute_invocation(
        invocation=prepared.invocation,
        dry_run=options.dry_run,
        enable_model=options.enable_model,
        model=options.model,
        replay_response=options.replay_response,
        listed_price_usd=options.identity.listed_price_usd,
    )
    status, result, error = status_and_result(
        dry_run=options.dry_run,
        response=response,
        raw_text=raw_text,
        review=prepared.review,
        threshold=prepared.threshold,
    )
    return _Execution(
        response,
        usage,
        fixture_path,
        fixture_sha256,
        status,
        result,
        error,
    )


def _build_receipt(
    options: _Options,
    prepared: _PreparedReview,
    started_at: str,
    finished_at: str,
    execution: _Execution,
) -> dict[str, Any]:
    return finalize_receipt(
        build_receipt(
            created_at=finished_at,
            review=prepared.review,
            identity=options.identity,
            invocation=prepared.invocation,
            invocation_mode=prepared.mode,
            command=prepared.command,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=(
                execution.response.elapsed_seconds if execution.response else 0.0
            ),
            fixture_path=execution.fixture_path,
            fixture_sha256=execution.fixture_sha256,
            status=execution.status,
            result=execution.result,
            usage=execution.usage,
            input_fingerprint_value=prepared.fingerprint,
            paid_call_allowed=prepared.paid_call_allowed,
            hard_cost_ceiling_usd=options.hard_cost_ceiling_usd,
            provider_enforces_spend_limit=options.provider_enforces_spend_limit,
            model_invoked=(
                prepared.mode == "live_model_call" and execution.response is not None
            ),
            error=execution.error,
        )
    )


def _write_receipt(
    options: _Options, prepared: _PreparedReview, receipt: dict[str, Any]
) -> Path | None:
    if options.dry_run:
        return None
    return write_receipt(receipt, prepared.directory, options.root)


def _exit_code(status: str) -> int:
    if status in {"completed", "dry_run"}:
        return EXIT_OK
    if status in {"completed_low_confidence", "abstained"}:
        return EXIT_OPERATOR_REVIEW
    return EXIT_FAIL_CLOSED
