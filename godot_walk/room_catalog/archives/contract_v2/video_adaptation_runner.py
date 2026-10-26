"""Explicit commands for validating and running video-adaptation workflow stages."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from video_adaptation_contracts import candidate_identity_v2
from video_adaptation_errors import AdaptationValidationError
from video_adaptation_sources import extract_source_crops, extract_source_frames
from video_adaptation_stage import relative_output as _relative_output  # noqa: F401
from video_adaptation_stage import run_tool as _run_tool
from video_adaptation_validation import ROOT, validate_bundle


def _validate(args: argparse.Namespace) -> int:
    record, fingerprint = validate_bundle(args.bundle)
    identity = candidate_identity_v2(record)
    print(
        json.dumps(
            {
                "status": "valid",
                "adaptation_id": record["adaptation_id"],
                "candidate_fingerprint": fingerprint,
                "candidate_identity": identity,
                "static_consistency": "passed",
                "runtime_evidence": {
                    "status": "historical fingerprinted records verified; runtime not rerun",
                    "stages": [
                        {"stage_id": stage["stage_id"], "status": stage["status"]}
                        for stage in record["validation"]["stages"]
                    ],
                },
                "validation_is_read_only": True,
            },
            indent=2,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    _add_validation_command(commands)
    _add_extraction_commands(commands)
    _add_stage_command(commands)
    return parser


def _add_validation_command(commands: Any) -> None:
    validate = commands.add_parser(
        "validate", help="Read-only schema, path and hash checks"
    )
    validate.add_argument("--bundle", type=Path, required=True)
    validate.set_defaults(handler=_validate)


def _add_extraction_commands(commands: Any) -> None:
    frames = commands.add_parser(
        "extract-source-frames", help="Decode exact frames from the original video"
    )
    frames.add_argument("--video", required=True)
    frames.add_argument("--indices", type=int, nargs="+", required=True)
    frames.add_argument("--output", required=True)
    frames.set_defaults(handler=_extract_frames)
    crops = commands.add_parser(
        "extract-source-crops", help="Crop pixels from a frame manifest"
    )
    crops.add_argument("--frame-manifest", required=True)
    crops.add_argument("--crop-plan", required=True)
    crops.add_argument("--output", required=True)
    crops.set_defaults(handler=_extract_crops)


def _add_stage_command(commands: Any) -> None:
    stage = commands.add_parser(
        "run-tool", help="Run one explicit, fingerprint-bound stage"
    )
    stage.add_argument("--bundle", type=Path, required=True)
    stage.add_argument("--stage", required=True)
    stage.add_argument("--output", action="append", required=True)
    stage.add_argument("--timeout-seconds", type=int, default=240)
    stage.add_argument("--expect-exit-code", type=int, default=0)
    stage.add_argument("--requires-gpu", action="store_true")
    stage.add_argument("command", nargs=argparse.REMAINDER)
    stage.set_defaults(handler=_run_tool)


def _extract_frames(args: argparse.Namespace) -> int:
    manifest = extract_source_frames(args.video, args.indices, args.output)
    print(manifest.relative_to(ROOT))
    return 0


def _extract_crops(args: argparse.Namespace) -> int:
    manifest = extract_source_crops(args.frame_manifest, args.crop_plan, args.output)
    print(manifest.relative_to(ROOT))
    return 0


def main() -> int:
    args = _parser().parse_args()
    try:
        return args.handler(args)
    except (
        AdaptationValidationError,
        FileExistsError,
        OSError,
        ValueError,
        subprocess.SubprocessError,
        RuntimeError,
        TimeoutError,
    ) as error:
        print(f"video adaptation stage failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
