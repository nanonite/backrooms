#!/usr/bin/env python3
"""Review up to three registered picture originals; model calls are opt-in."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from run_seed_review import _identity
from seed_review_errors import SeedReviewError
from seed_review_paths import ROOT, resolve_repo_path
from seed_review_provider import OpenCodeCliModel
from seed_review_response import load_recorded_response
from seed_review_workflow import load_workflow_spec
from picture_seed_review_runner_v1 import run_picture_seed_review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review up to three full-resolution picture-set originals and write a receipt."
    )
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--provider", default="opencode")
    parser.add_argument("--model")
    parser.add_argument("--opencode-version")
    parser.add_argument("--model-is-free", action="store_true")
    parser.add_argument("--listed-price-usd", type=float)
    parser.add_argument("--hard-cost-ceiling-usd", type=float)
    parser.add_argument("--provider-enforces-spend-limit", action="store_true")
    parser.add_argument("--image-input-supported", action="store_true")
    parser.add_argument("--image-support-basis")
    parser.add_argument("--accounting")
    parser.add_argument("--enable-model", action="store_true")
    parser.add_argument("--replay-response")
    parser.add_argument("--dry-run", action="store_true")
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
    identity = _identity(args, spec.preferred_vision_model)
    replay = None
    if args.replay_response:
        replay_path = resolve_repo_path(args.replay_response, ROOT, require_file=True)
        replay = load_recorded_response(replay_path, ROOT)
    model = OpenCodeCliModel() if args.enable_model and replay is None else None
    run = run_picture_seed_review(
        source_id=args.source_id,
        identity=identity,
        spec=spec,
        model=model,
        replay_response=replay,
        enable_model=args.enable_model,
        dry_run=args.dry_run,
        receipts_dir=Path(args.receipts_dir) if args.receipts_dir else None,
        timeout_seconds=args.timeout,
        confidence_threshold=args.confidence_threshold,
        hard_cost_ceiling_usd=args.hard_cost_ceiling_usd,
        provider_enforces_spend_limit=args.provider_enforces_spend_limit,
    )
    _print_run(run, args.json)
    return run.exit_code


def _print_run(run: object, as_json: bool) -> None:
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
    selected = result["selected_image_id"]
    print(f"selected: {selected or 'none'}")
    print("operator_approval_recorded: false")
    print("next_stage_authorized: false")
    if result["error"]:
        print(f"error: {result['error']}")


if __name__ == "__main__":
    raise SystemExit(main())
