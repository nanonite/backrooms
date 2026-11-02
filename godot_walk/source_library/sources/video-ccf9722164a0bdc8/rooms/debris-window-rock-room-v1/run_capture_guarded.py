"""Run candidate Vulkan capture under the shared GPU lock and resource guard."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / "godot_walk/scripts"))

from gpu_job_lock import exclusive_gpu_job
from psx_design_round_resources import PeakResourceSampler, check_capture_headroom


def main() -> int:
	arguments = _arguments()
	output = _inside_repo(arguments.output_dir)
	report_path = _inside_repo(arguments.report)
	if output.exists() or report_path.exists():
		raise SystemExit("Refusing to overwrite capture output or resource receipt")
	command = _command(arguments.command)
	started = time.monotonic()
	preflight = None
	resources = None
	return_code = 125
	error = None
	timed_out = False
	try:
		with exclusive_gpu_job(ROOT):
			preflight = check_capture_headroom()
			sampler = PeakResourceSampler()
			sampler.start()
			try:
				completed = subprocess.run(command, cwd=ROOT, check=False, timeout=arguments.timeout_seconds)
				return_code = completed.returncode
			except subprocess.TimeoutExpired:
				return_code = 124
				timed_out = True
			finally:
				resources = sampler.stop()
	except (OSError, RuntimeError, subprocess.SubprocessError) as error_value:
		error = str(error_value)
	_write_report(report_path, arguments, command, preflight, resources, started, return_code, timed_out, error)
	return return_code


def _arguments() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--output-dir", required=True)
	parser.add_argument("--report", required=True)
	parser.add_argument("--timeout-seconds", type=int, default=240)
	parser.add_argument("command", nargs=argparse.REMAINDER)
	return parser.parse_args()


def _command(command: list[str]) -> list[str]:
	result = command[1:] if command and command[0] == "--" else command
	if not result:
		raise SystemExit("A capture command is required after --")
	return result


def _inside_repo(relative: str) -> Path:
	path = (ROOT / relative).resolve(strict=False)
	if not path.is_relative_to(ROOT.resolve()):
		raise SystemExit(f"Repository output path escapes workspace: {relative}")
	return path


def _write_report(path: Path, arguments: argparse.Namespace, command: list[str], preflight: dict | None,
				  resources: dict | None, started: float, return_code: int, timed_out: bool,
				  error: str | None) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	report = {
		"label": "debris-window-rock-room-v1-review-capture",
		"command": command,
		"output_dir": arguments.output_dir,
		"timeout_seconds": arguments.timeout_seconds,
		"return_code": return_code,
		"timed_out": timed_out,
		"error": error,
		"elapsed_seconds": round(time.monotonic() - started, 3),
		"finished_at_utc": datetime.now(timezone.utc).isoformat(),
		"preflight": preflight,
		"peak_resources": resources,
	}
	descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
	with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
		json.dump(report, stream, indent=2)
		stream.write("\n")


if __name__ == "__main__":
	raise SystemExit(main())
