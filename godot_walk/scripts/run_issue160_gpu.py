"""Run one #160 GPU job only after a resource/concurrency preflight."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from psx_design_round_resources import PeakResourceSampler, check_capture_headroom

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "godot_walk/evidence/2026-10-22-issue-160"


def main() -> int:
    arguments = _arguments()
    if not arguments.command:
        raise SystemExit("A GPU command is required after --")
    command = arguments.command[1:] if arguments.command[0] == "--" else arguments.command
    preflight = check_capture_headroom()
    sampler = PeakResourceSampler()
    sampler.start()
    started = time.monotonic()
    return_code = 1
    timed_out = False
    try:
        completed = subprocess.run(command, check=False, timeout=arguments.timeout_seconds)
        return_code = completed.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        return_code = 124
    finally:
        resources = sampler.stop()
    report = {
        "label": arguments.label,
        "command": command,
        "timeout_seconds": arguments.timeout_seconds,
        "timed_out": timed_out,
        "return_code": return_code,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "preflight": preflight,
        "resources": resources,
    }
    output = EVIDENCE / "resource_runs" / f"{arguments.label}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return return_code


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
