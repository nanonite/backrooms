"""Run one issue #168 Vulkan capture under the shared GPU guard."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
import sys

sys.path.insert(0, str(ROOT / "godot_walk/scripts"))

from gpu_job_lock import exclusive_gpu_job
from psx_design_round_resources import PeakResourceSampler, check_capture_headroom


def main() -> int:
    args = _arguments()
    output_dir = _safe_path(args.output_dir)
    report_path = _safe_path(args.report)
    if output_dir.exists() or report_path.exists():
        raise SystemExit("Refusing to overwrite capture output or resource receipt")
    command = _command(args.command)
    started = time.monotonic()
    preflight, resources, return_code, timed_out, error = _run_guarded(
        command, args.timeout_seconds
    )
    _write_receipt(
        args, command, preflight, resources, started, return_code, timed_out, error
    )
    return return_code


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="issue168-two-room-review-capture")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def _command(values: list[str]) -> list[str]:
    command = values[1:] if values and values[0] == "--" else values
    if not command:
        raise SystemExit("Provide a command after --")
    return command


def _safe_path(relative: str) -> Path:
    path = (ROOT / relative).resolve(strict=False)
    if not path.is_relative_to(ROOT.resolve()):
        raise SystemExit(f"Path escapes repository: {relative}")
    return path


def _run_guarded(
    command: list[str], timeout: int
) -> tuple[dict | None, dict | None, int, bool, str | None]:
    preflight = None
    resources = None
    return_code = 125
    timed_out = False
    error = None
    try:
        with exclusive_gpu_job(ROOT):
            preflight = check_capture_headroom()
            sampler = PeakResourceSampler()
            sampler.start()
            try:
                return_code = subprocess.run(
                    command, cwd=ROOT, check=False, timeout=timeout
                ).returncode
            except subprocess.TimeoutExpired:
                return_code = 124
                timed_out = True
            finally:
                resources = sampler.stop()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error_value:
        error = str(error_value)
    return preflight, resources, return_code, timed_out, error


def _write_receipt(
    args: argparse.Namespace,
    command: list[str],
    preflight: dict | None,
    resources: dict | None,
    started: float,
    return_code: int,
    timed_out: bool,
    error: str | None,
) -> None:
    report_path = _safe_path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "label": args.label,
        "command": command,
        "output_dir": args.output_dir,
        "timeout_seconds": args.timeout_seconds,
        "return_code": return_code,
        "timed_out": timed_out,
        "error": error,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "preflight": preflight,
        "peak_resources": resources,
    }
    descriptor = os.open(
        report_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o644,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
