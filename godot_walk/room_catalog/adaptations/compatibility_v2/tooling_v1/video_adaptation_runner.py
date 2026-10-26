"""Explicit commands for validating and running video-adaptation workflow stages."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from video_adaptation_sources import extract_source_crops, extract_source_frames
from video_adaptation_validation import (
    ROOT,
    AdaptationValidationError,
    sha256_file,
    validate_bundle,
)


def _relative_output(path_text: str) -> Path:
    path = (ROOT / path_text).resolve()
    if not path.is_relative_to(ROOT):
        raise AdaptationValidationError("Stage outputs must stay inside the repository")
    return path


def _run_tool(args: argparse.Namespace) -> int:
    record, fingerprint = validate_bundle(args.bundle)
    if re.fullmatch(r"[a-zA-Z0-9_-]+", args.stage) is None:
        raise ValueError("Stage id may contain only letters, numbers, underscores and hyphens")
    output_paths = [_relative_output(text) for text in args.output]
    if not output_paths or any(path.exists() for path in output_paths):
        raise FileExistsError("Declare fresh outputs; existing paths are never overwritten")
    if args.requires_gpu and not any("run_issue149_gpu.py" in part for part in args.command):
        raise ValueError("GPU stages must run through the shared GPU/RAM guard")
    receipt_dir = Path(args.bundle).resolve().parent / "stage_receipts" / record["adaptation_id"]
    receipt_path = receipt_dir / f"{args.stage}.json"
    if receipt_path.exists():
        raise FileExistsError(f"Refusing to overwrite stage receipt: {receipt_path}")
    completed, elapsed, command = _execute_command(args, output_paths)
    artifacts = _hash_outputs(output_paths)
    receipt = _stage_receipt(args, record, fingerprint, completed, elapsed, command, artifacts)
    receipt_dir.mkdir(exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if completed.returncode == args.expect_exit_code else 1


def _execute_command(args: argparse.Namespace, outputs: list[Path]) -> tuple[subprocess.CompletedProcess[str], float, list[str]]:
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        raise ValueError("A stage command is required after --")
    started = time.monotonic()
    try:
        completed = subprocess.run(command, cwd=ROOT, check=False, timeout=args.timeout_seconds,
                                   capture_output=True, text=True)
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(f"Stage timed out after {args.timeout_seconds}s: {args.stage}") from error
    if completed.returncode != args.expect_exit_code:
        raise RuntimeError(f"Stage {args.stage} returned {completed.returncode}; expected {args.expect_exit_code}\n{completed.stderr}")
    if not all(path.exists() for path in outputs):
        raise RuntimeError(f"Stage {args.stage} did not create every declared output")
    return completed, round(time.monotonic() - started, 3), command


def _hash_outputs(outputs: list[Path]) -> list[dict[str, str]]:
    artifacts = []
    for output in outputs:
        if not output.is_file():
            raise ValueError(f"Stage output must be a file: {output}")
        artifacts.append({
            "path": output.relative_to(ROOT).as_posix(), "sha256": sha256_file(output),
            "role": "explicit workflow stage output",
        })
    return artifacts


def _stage_receipt(args: argparse.Namespace, record: dict, fingerprint: str,
                   completed: subprocess.CompletedProcess[str], elapsed: float,
                   command: list[str], artifacts: list[dict]) -> dict:
    return {
        "schema_version": 1, "stage_id": args.stage,
        "adaptation_id": record["adaptation_id"], "candidate_fingerprint": fingerprint,
        "command": command, "expected_exit_code": args.expect_exit_code,
        "return_code": completed.returncode, "elapsed_seconds": elapsed,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(), "artifacts": artifacts,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
    }


def _validate(args: argparse.Namespace) -> int:
    record, fingerprint = validate_bundle(args.bundle)
    print(json.dumps({
        "status": "valid", "adaptation_id": record["adaptation_id"],
        "candidate_fingerprint": fingerprint,
        "validation_is_read_only": True,
    }, indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    validate = commands.add_parser("validate", help="Read-only schema, path and hash checks")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.set_defaults(handler=_validate)
    frames = commands.add_parser("extract-source-frames", help="Decode exact frames from the original video")
    frames.add_argument("--video", required=True)
    frames.add_argument("--indices", type=int, nargs="+", required=True)
    frames.add_argument("--output", required=True)
    frames.set_defaults(handler=_extract_frames)
    crops = commands.add_parser("extract-source-crops", help="Crop pixels from a frame manifest")
    crops.add_argument("--frame-manifest", required=True)
    crops.add_argument("--crop-plan", required=True)
    crops.add_argument("--output", required=True)
    crops.set_defaults(handler=_extract_crops)
    stage = commands.add_parser("run-tool", help="Run one explicit, fingerprint-bound stage")
    stage.add_argument("--bundle", type=Path, required=True)
    stage.add_argument("--stage", required=True)
    stage.add_argument("--output", action="append", required=True)
    stage.add_argument("--timeout-seconds", type=int, default=240)
    stage.add_argument("--expect-exit-code", type=int, default=0)
    stage.add_argument("--requires-gpu", action="store_true")
    stage.add_argument("command", nargs=argparse.REMAINDER)
    stage.set_defaults(handler=_run_tool)
    return parser


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
    except (AdaptationValidationError, FileExistsError, OSError, ValueError,
            subprocess.SubprocessError, RuntimeError, TimeoutError) as error:
        print(f"video adaptation stage failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
