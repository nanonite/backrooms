"""Execute a single overwrite-safe, fingerprint-bound adaptation stage."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from video_adaptation_contracts import candidate_identity_v2
from video_adaptation_paths import (
    create_new_file,
    receipt_file,
    resolve_repo_path,
    validate_stage_id,
)
from video_adaptation_validation import (
    ROOT,
    sha256_file,
    validate_bundle,
)


def relative_output(path_text: str) -> Path:
    path = resolve_repo_path(path_text, ROOT)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite stage output: {path_text}")
    return path


def run_tool(args: argparse.Namespace) -> int:
    record, fingerprint = validate_bundle(args.bundle)
    validate_stage_id(args.stage)
    outputs = [relative_output(text) for text in args.output]
    _require_fresh_outputs(outputs)
    _require_gpu_guard(args)
    receipt = receipt_file(args.bundle.resolve(), record["adaptation_id"], args.stage)
    if receipt.exists():
        raise FileExistsError(f"Refusing to overwrite stage receipt: {receipt}")
    completed, elapsed, command = _execute_command(args, outputs)
    artifacts = _hash_outputs(outputs)
    _write_receipt(args, record, fingerprint, completed, elapsed, command, artifacts)
    return 0 if completed.returncode == args.expect_exit_code else 1


def _write_receipt(
    args: argparse.Namespace,
    record: dict,
    fingerprint: str,
    completed: subprocess.CompletedProcess[str],
    elapsed: float,
    command: list[str],
    artifacts: list[dict],
) -> None:
    identity = candidate_identity_v2(record)
    data = _stage_receipt(
        args, record, fingerprint, identity, completed, elapsed, command, artifacts
    )
    path = _receipt_path(args, record)
    _create_receipt_file(path, data)
    print(json.dumps(data, indent=2))


def _receipt_path(args: argparse.Namespace, record: dict) -> Path:
    return receipt_file(
        args.bundle.resolve(),
        record["adaptation_id"],
        args.stage,
        create_directory=True,
    )


def _create_receipt_file(path: Path, data: dict) -> None:
    content = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    create_new_file(path, content)


def _require_fresh_outputs(outputs: list[Path]) -> None:
    if not outputs or any(path.exists() for path in outputs):
        raise FileExistsError(
            "Declare fresh outputs; existing paths are never overwritten"
        )


def _require_gpu_guard(args: argparse.Namespace) -> None:
    if args.requires_gpu and not any(
        "run_issue149_gpu.py" in part for part in args.command
    ):
        raise ValueError("GPU stages must run through the shared GPU/RAM guard")


def _execute_command(
    args: argparse.Namespace, outputs: list[Path]
) -> tuple[subprocess.CompletedProcess[str], float, list[str]]:
    command = _normalize_command(args.command)
    if not command:
        raise ValueError("A stage command is required after --")
    started = time.monotonic()
    completed = _run_process(command, args)
    _validate_process_result(completed, args, outputs)
    return completed, round(time.monotonic() - started, 3), command


def _normalize_command(command: list[str]) -> list[str]:
    return command[1:] if command and command[0] == "--" else command


def _run_process(
    command: list[str], args: argparse.Namespace
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            timeout=args.timeout_seconds,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(
            f"Stage timed out after {args.timeout_seconds}s: {args.stage}"
        ) from error


def _validate_process_result(
    completed: subprocess.CompletedProcess[str],
    args: argparse.Namespace,
    outputs: list[Path],
) -> None:
    if completed.returncode != args.expect_exit_code:
        raise RuntimeError(
            f"Stage {args.stage} returned {completed.returncode}; expected {args.expect_exit_code}\n"
            f"{completed.stderr}"
        )
    if not all(path.exists() for path in outputs):
        raise RuntimeError(f"Stage {args.stage} did not create every declared output")


def _hash_outputs(outputs: list[Path]) -> list[dict[str, str]]:
    artifacts = []
    for output in outputs:
        if not output.is_file():
            raise ValueError(f"Stage output must be a file: {output}")
        artifacts.append(
            {
                "path": output.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(output),
                "role": "explicit workflow stage output",
            }
        )
    return artifacts


def _stage_receipt(
    args: argparse.Namespace,
    record: dict,
    fingerprint: str,
    identity: str,
    completed: subprocess.CompletedProcess[str],
    elapsed: float,
    command: list[str],
    artifacts: list[dict],
) -> dict:
    return {
        "schema_version": 2,
        "stage_id": args.stage,
        "adaptation_id": record["adaptation_id"],
        "candidate_identity": identity,
        "legacy_dependency_fingerprint": fingerprint,
        "command": command,
        "expected_exit_code": args.expect_exit_code,
        "return_code": completed.returncode,
        "elapsed_seconds": elapsed,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifacts": artifacts,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
    }
