"""Run the Issue 163 Vulkan capture after the shared resource preflight."""

from __future__ import annotations

import json
import argparse
import os
import signal
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "godot_walk"
EVIDENCE = PROJECT / "evidence/2026-10-24-issue-163"
CAPTURE = "res://evidence/2026-10-24-issue-163/capture_issue163_room.gd"
TIMEOUT_SECONDS = 300


def main() -> int:
    args = _arguments()
    output = _output_directory(args.out_dir)
    binary = shutil.which("godot4") or shutil.which("godot")
    if binary is None:
        raise FileNotFoundError("Godot 4 executable not found")
    sys.path.insert(0, str(PROJECT / "scripts"))
    from psx_design_round_resources import PeakResourceSampler, check_capture_headroom

    preflight = check_capture_headroom()
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("Vulkan capture requires the desktop display")
    command = _command(binary, output)
    status = _execute(command, output, preflight, PeakResourceSampler)
    print(f"ISSUE163_CAPTURE_{status['status'].upper()}: {output}")
    return int(status["exit_code"])


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="captures_final")
    return parser.parse_args()


def _output_directory(name: str) -> Path:
    if Path(name).name != name or name in {"", ".", ".."}:
        raise ValueError("--out-dir must be one folder name inside the issue evidence")
    output = EVIDENCE / name
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite captures: {output}")
    return output


def _command(binary: str, output: Path) -> list[str]:
    return [
        binary,
        "--fixed-fps", "60",
        "--path", str(PROJECT),
        "--rendering-driver", "vulkan",
        "--resolution", "960x540",
        "--disable-vsync",
        "--script", CAPTURE,
        "--", f"--out=res://evidence/2026-10-24-issue-163/{output.name}",
    ]


def _execute(
    command: list[str], output: Path, preflight: dict[str, Any], sampler_type: type
) -> dict[str, Any]:
    log_path = EVIDENCE / f"{output.name}_run.log"
    sampler = sampler_type()
    sampler.start()
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            exit_code = process.wait(timeout=TIMEOUT_SECONDS)
            status = "complete" if exit_code == 0 else "failed"
            reason = None
        except subprocess.TimeoutExpired:
            _stop(process)
            exit_code = 124
            status = "timeout"
            reason = f"hard timeout after {TIMEOUT_SECONDS} seconds"
    resource_use = sampler.stop()
    record = {
        "command": command,
        "status": status,
        "exit_code": exit_code,
        "stop_reason": reason,
        "preflight": preflight,
        "resources": resource_use,
        "output_directory": output.relative_to(ROOT).as_posix(),
        "timeout_seconds": TIMEOUT_SECONDS,
    }
    status_path = EVIDENCE / f"{output.name}_status.json"
    status_path.write_text(json.dumps(record, indent=2) + "\n")
    return record


def _stop(process: subprocess.Popen[bytes]) -> None:
    for sig, grace in ((signal.SIGINT, 10), (signal.SIGTERM, 10), (signal.SIGKILL, 0)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"ISSUE163_CAPTURE_REFUSED: {error}", file=sys.stderr)
        raise SystemExit(1)
