"""Issue #276 — one guarded command from scripted walk to measurement JSON.

New file only. Uses the repository's existing GPU guard (exclusive_gpu_job +
check_capture_headroom + PeakResourceSampler) and the documented DISPLAY=:1
Godot 4.6.3 render path. A capture always produces a WAV and a measurement JSON
plus a receipt; the conversion/verify step is not left to the operator's memory.

Captured media (movie, frame sequence, normalised WAV, log) stays under the
already git-ignored evidence/.../captures/ tree. Receipts, measurements and
expectations are tracked JSON under the evidence directory.

Usage:
    python3 godot_walk/scripts/issue276_capture_audio.py preflight
    python3 godot_walk/scripts/issue276_capture_audio.py capture --name synthetic-1 --mode synthetic
    python3 godot_walk/scripts/issue276_capture_audio.py capture --name walk-1 --mode walk
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import (
    ROOT,
    canonical_bytes,
    sha256_file,
    write_deterministic,
)
from gpu_job_lock import exclusive_gpu_job
from psx_design_round_resources import (
    PeakResourceSampler,
    check_capture_headroom,
)

EVIDENCE = ROOT / "godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio"
CAPTURES = EVIDENCE / "captures"
SCRIPT_SYNTHETIC = "res://evidence/2026-11-19-issue-276-movie-maker-audio/fixture/audio_probe.gd"
SCRIPT_WALK = "res://evidence/2026-11-19-issue-276-movie-maker-audio/fixture/walk_capture.gd"
DEFAULT_GODOT = "godot4"
DEFAULT_FPS = 30
DEFAULT_TIMEOUT_SECONDS = 180
ROOM = "nested-light-corridor-v1"

EXPECTATIONS: dict[str, dict[str, Any]] = {
    "synthetic": {
        "tone_hz": 440.0,
        "tone_tolerance_hz": 120.0,
        "min_peak": 0.99,
        "max_peak": 1.0,
        "min_clipped_samples": 20000,
        "require_clipping": True,
        "min_duration_seconds": 3.9,
        "max_duration_seconds": 4.1,
    },
    "spatial3d": {
        "tone_hz": 440.0,
        "tone_tolerance_hz": 120.0,
        "min_peak": 0.2,
        "max_peak": 0.8,
        "max_clipped_samples": 0,
        "min_duration_seconds": 1.9,
        "max_duration_seconds": 2.1,
    },
    "walk": {
        "max_clipped_samples": 0,
        "min_nonquiet_frames": 4,
        "min_duration_seconds": 3.9,
        "max_duration_seconds": 4.1,
    },
}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("preflight")
    capture_parser = subcommands.add_parser("capture")
    capture_parser.add_argument("--name", required=True)
    capture_parser.add_argument("--mode", choices=sorted(EXPECTATIONS), default="synthetic")
    capture_parser.add_argument("--format", choices=("avi", "png"), default="avi")
    capture_parser.add_argument("--audio-driver")
    capture_parser.add_argument("--godot", default=DEFAULT_GODOT)
    capture_parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    capture_parser.add_argument("--frames", type=int)
    capture_parser.add_argument("--step-every", type=int, default=15)
    capture_parser.add_argument("--reverb", choices=("on", "off"), default="on")
    capture_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args()


def _frames_for(mode: str, requested: int | None) -> int:
    if requested is not None:
        return requested
    return 60 if mode == "spatial3d" else 120


def _godot_version(executable: str) -> str:
    result = subprocess.run([executable, "--version"], cwd=ROOT, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _command(
    arguments: argparse.Namespace, frames: int, output_dir: Path, file_format: str
) -> tuple[list[str], str]:
    movie = output_dir / ("movie.avi" if file_format == "avi" else "movie.png")
    command = [
        arguments.godot, "--path", "godot_walk", "--rendering-driver", "vulkan",
        "--fixed-fps", str(arguments.fps), "--quit-after", str(frames),
        "--write-movie", str(movie), "--script",
        SCRIPT_WALK if arguments.mode == "walk" else SCRIPT_SYNTHETIC, "--",
    ]
    if arguments.mode == "walk":
        command += [
            f"--room={ROOM}", f"--frames={frames}",
            f"--step-every={arguments.step_every}", f"--reverb={arguments.reverb}",
        ]
    else:
        pattern = {"synthetic": "tone_then_clip", "spatial3d": "spatial3d"}[arguments.mode]
        command.append(f"--mode={pattern}")
    if arguments.audio_driver:
        command.insert(3, f"--audio-driver={arguments.audio_driver}")
    return command, str(movie)


def _run_godot(command: list[str], log_path: Path, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    return_code = 125
    timed_out = False
    error = None
    try:
        with log_path.open("wb") as log:
            completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return_code = completed.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
    except OSError as exception:
        error = str(exception)
    return {
        "return_code": return_code,
        "timed_out": timed_out,
        "error": error,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def _capture(arguments: argparse.Namespace) -> int:
    display = os.environ.get("DISPLAY", "")
    if not display:
        raise SystemExit("DISPLAY is not set; Movie Maker needs the guarded DISPLAY=:1 render path")
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg not found; enter the audioAnalysis nix devShell")
    frames = _frames_for(arguments.mode, arguments.frames)
    output_dir = CAPTURES / arguments.name
    if output_dir.exists():
        raise SystemExit(f"Refusing to overwrite capture output: {output_dir}")
    receipt_path = EVIDENCE / "receipts" / f"{arguments.name}_receipt.json"
    measurement_path = EVIDENCE / "measurements" / f"{arguments.name}_measurement.json"
    expectation_path = EVIDENCE / "expectations" / f"{arguments.mode}_expectations.json"
    if receipt_path.exists() or measurement_path.exists():
        raise SystemExit("Refusing to overwrite an existing receipt or measurement")

    output_dir.mkdir(parents=True)
    receipt: dict[str, Any] = {
        "issue": 276,
        "generator": "godot_walk/scripts/issue276_capture_audio.py",
        "name": arguments.name,
        "mode": arguments.mode,
        "room": ROOM if arguments.mode == "walk" else None,
        "reverb": arguments.reverb if arguments.mode == "walk" else None,
        "display": display,
        "format": arguments.format,
        "fps": arguments.fps,
        "frames": frames,
        "duration_seconds": round(frames / arguments.fps, 6),
        "godot_version": _godot_version(arguments.godot),
    }
    command: list[str] = []
    with exclusive_gpu_job(ROOT):
        receipt["preflight"] = check_capture_headroom()
        sampler = PeakResourceSampler()
        sampler.start()
        try:
            command, movie_path = _command(arguments, frames, output_dir, arguments.format)
            receipt["command"] = command
            receipt.update(_run_godot(command, output_dir / "godot.log", arguments.timeout))
        finally:
            receipt["peak_resources"] = sampler.stop()
    _after_run(receipt, arguments, output_dir, movie_path, measurement_path, expectation_path)
    _write_receipt(receipt_path, receipt)
    return 0 if receipt.get("verification_pass") else 1


def _after_run(
    receipt: dict[str, Any], arguments: argparse.Namespace, output_dir: Path,
    movie_path: str, measurement_path: Path, expectation_path: Path,
) -> None:
    if receipt["return_code"] != 0 or receipt["timed_out"]:
        receipt["verification_pass"] = False
        receipt["verification_failures"] = ["godot capture did not complete successfully"]
        return
    audio_source = (
        str(Path(movie_path).with_suffix(".wav")) if arguments.format == "png" else movie_path
    )
    normalised = output_dir / "audio_48k_mono.wav"
    analyser = sys.executable
    measure_command = [
        analyser, str(ROOT / "godot_walk/scripts/issue276_analyze_audio.py"), "measure",
        "--input", audio_source, "--output", str(measurement_path), "--wav", str(normalised),
    ]
    measured = subprocess.run(measure_command, cwd=ROOT, capture_output=True, text=True, check=False)
    print(measured.stdout, end="")
    if measured.returncode != 0:
        receipt.update(verification_pass=False, verification_failures=[measured.stderr.strip()])
        return
    expected = EXPECTATIONS[arguments.mode]
    write_deterministic(expectation_path, canonical_bytes(expected))
    verify_command = [
        analyser, str(ROOT / "godot_walk/scripts/issue276_analyze_audio.py"), "verify",
        "--measurement", str(measurement_path), "--expect", str(expectation_path),
    ]
    verified = subprocess.run(verify_command, cwd=ROOT, capture_output=True, text=True, check=False)
    print(verified.stdout, end="")
    receipt["verification_pass"] = verified.returncode == 0
    receipt["verification_failures"] = [
        line for line in verified.stdout.splitlines() if "FAIL" in line
    ]
    receipt["measurement_path"] = str(measurement_path.relative_to(ROOT))
    receipt["expectation_path"] = str(expectation_path.relative_to(ROOT))
    movie_artifact = (
        output_dir / "movie00000000.png" if arguments.format == "png" else Path(movie_path)
    )
    for label, path in (("movie", movie_artifact), ("audio_source", Path(audio_source)),
                        ("normalized_wav", normalised)):
        if path.is_file():
            receipt[f"sha256_{label}"] = sha256_file(path)


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"ISSUE276_RECEIPT {path.relative_to(ROOT)} pass={receipt.get('verification_pass')}")


def command_preflight() -> int:
    display = os.environ.get("DISPLAY", "")
    print(f"ISSUE276_PREFLIGHT display={display!r} godot={_godot_version(DEFAULT_GODOT)} "
          f"ffmpeg={shutil.which('ffmpeg')}")
    with exclusive_gpu_job(ROOT):
        result = check_capture_headroom()
    print(f"ISSUE276_PREFLIGHT_OK guard_policy={result['guard_policy_version']} "
          f"compute_apps={len(result['compute_apps'])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = _arguments()
    if arguments.command == "preflight":
        return command_preflight()
    return _capture(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
