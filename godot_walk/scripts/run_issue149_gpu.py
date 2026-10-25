"""Run #149 Vulkan work behind the shared fail-closed GPU/RAM guard."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from psx_design_round_resources import PeakResourceSampler, check_capture_headroom

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE = ROOT / "godot_walk/evidence/2026-10-22-issue-149"


def main() -> int:
    arguments = _arguments()
    command = arguments.command[1:] if arguments.command and arguments.command[0] == "--" else arguments.command
    if not command:
        raise SystemExit("A GPU command is required after --")
    try:
        preflight = check_capture_headroom()
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        _write_report(arguments, command, None, None, time.monotonic(), 125, str(error), False)
        return 125
    sampler = PeakResourceSampler()
    sampler.start()
    started = time.monotonic()
    timed_out = False
    error_text = None
    try:
        completed = subprocess.run(command, check=False, timeout=arguments.timeout_seconds)
        return_code = completed.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        return_code = 124
    except OSError as error:
        error_text = str(error)
        return_code = 127
    resources = sampler.stop()
    _write_report(arguments, command, preflight, resources, started, return_code, error_text, timed_out)
    return return_code


def _write_report(arguments: argparse.Namespace, command: list[str], preflight: dict | None,
                  resources: dict | None, started: float, return_code: int,
                  error: str | None, timed_out: bool) -> None:
    report = {
        "label": arguments.label,
        "command": command,
        "timeout_seconds": arguments.timeout_seconds,
        "timed_out": timed_out,
        "return_code": return_code,
        "error": error,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "preflight": preflight,
        "resources": resources,
    }
    output = arguments.evidence_dir / "resource_runs" / f"{arguments.label}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
