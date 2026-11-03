#!/usr/bin/env python3
"""Run one bounded seed-review stage; model calls require explicit opt-in."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from seed_review_errors import SeedReviewError
from seed_review_paths import ROOT, read_json_object, resolve_repo_path
from seed_review_provider import (
    ModelIdentity,
    OpenCodeCliModel,
    detect_opencode_version,
)
from seed_review_response import load_recorded_response
from seed_review_runner import run_seed_review
from seed_review_workflow import load_workflow_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review at most three direct-source frames and write a receipt."
    )
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--provider", default="opencode")
    parser.add_argument("--model")
    parser.add_argument("--opencode-version")
    parser.add_argument("--model-is-free", action="store_true")
    parser.add_argument("--listed-price-usd", type=float)
    parser.add_argument("--hard-cost-ceiling-usd", type=float)
    parser.add_argument("--provider-enforces-spend-limit", action="store_true")
    parser.add_argument("--image-input-supported", action="store_true")
    parser.add_argument("--image-support-basis")
    parser.add_argument("--accounting", default=None)
    parser.add_argument("--enable-model", action="store_true")
    parser.add_argument("--replay-response")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mechanical-shortlist", action="store_true")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--confidence-threshold", type=int)
    parser.add_argument("--receipts-dir")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except SeedReviewError as error:
        print(
            json.dumps(
                {"status": "error", **error.to_dict()},
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


def _run(args: argparse.Namespace) -> int:
    spec = load_workflow_spec()
    request_path = args.request
    request_document = read_json_object(
        resolve_repo_path(request_path, ROOT, require_file=True),
        "seed-review request",
    )
    identity = _identity(args, spec.preferred_vision_model)
    replay = None
    if args.replay_response:
        replay_path = resolve_repo_path(args.replay_response, ROOT, require_file=True)
        replay = load_recorded_response(replay_path, ROOT)
    model = OpenCodeCliModel() if args.enable_model and replay is None else None
    run = run_seed_review(
        source_id=args.source_id,
        request_document=request_document,
        request_path=request_path,
        identity=identity,
        spec=spec,
        model=model,
        replay_response=replay,
        enable_model=args.enable_model,
        dry_run=args.dry_run,
        allow_mechanical_shortlist=args.mechanical_shortlist,
        receipts_dir=Path(args.receipts_dir) if args.receipts_dir else None,
        timeout_seconds=args.timeout,
        confidence_threshold=args.confidence_threshold,
        hard_cost_ceiling_usd=args.hard_cost_ceiling_usd,
        provider_enforces_spend_limit=args.provider_enforces_spend_limit,
    )
    _print_run(run, as_json=args.json)
    return run.exit_code


def _identity(args: argparse.Namespace, default_reference: str) -> ModelIdentity:
    reference = args.model or default_reference
    provider, model = _split_reference(reference, args.provider)
    is_free = args.model_is_free or args.listed_price_usd == 0.0
    listed_price = args.listed_price_usd
    if listed_price is None and is_free:
        listed_price = 0.0
    image_supported, basis = _image_support(args, is_free)
    accounting = args.accounting or (
        "free_no_charge" if is_free else "provider_reported_or_unavailable"
    )
    opencode_version = args.opencode_version
    if args.enable_model and not args.replay_response and opencode_version is None:
        opencode_version = detect_opencode_version()
    return ModelIdentity(
        provider=provider,
        model=model,
        image_input_supported=image_supported,
        image_input_support_basis=basis,
        is_free=is_free,
        listed_price_usd=listed_price,
        accounting=accounting,
        opencode_version=opencode_version,
    )


def _split_reference(reference: str, provider: str) -> tuple[str, str]:
    if "/" in reference:
        provider, model = reference.split("/", 1)
    else:
        model = reference
    if not provider or not model:
        raise SeedReviewError(
            "model_identity_invalid", "Provider and model must be nonempty"
        )
    return provider, model


def _image_support(args: argparse.Namespace, is_free: bool) -> tuple[bool, str]:
    if args.image_input_supported:
        return True, args.image_support_basis or "operator_asserted_before_frame_review"
    if args.replay_response:
        return True, "recorded_image_response_fixture"
    if args.dry_run:
        return True, "dry_run_plan_only_no_model_call"
    if is_free:
        return False, "not_verified"
    return False, "not_verified"


def _print_run(run: object, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(run.to_dict(), indent=2, ensure_ascii=False))
        return
    receipt = run.receipt
    result = receipt["result"]
    print(f"status: {run.status}")
    print(
        "receipt: "
        + (run.receipt_path.as_posix() if run.receipt_path else "not written")
    )
    if result["selected_frame_id"]:
        print(
            f"selected: {result['selected_frame_id']} "
            f"(confidence {result['confidence_1_to_5']}/5)"
        )
    else:
        print("selected: none")
    print(f"operator_review_required: {receipt['requires_operator_review']}")
    print("next_stage_authorized: false")
    if result["error"]:
        print(f"error: {result['error']}")


if __name__ == "__main__":
    raise SystemExit(main())
