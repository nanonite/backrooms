"""Run the operator-directed, column-only Hunyuan PSX design round."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "godot_walk"
OUT = PROJECT / "evidence" / "2026-10-21-issue-151-round-2"
ROUND_ONE = PROJECT / "evidence" / "2026-10-21-issue-151-round-1"
SCENE = "res://scenes/hunyuan_psx_round2.tscn"
CAPTURE = "res://scripts/capture_hunyuan_psx_round1.gd"
VERIFY = "res://scripts/verify_bounded_psx.gd"
FPS = "res://scripts/measure_bounded_fps.gd"
BUILDER = PROJECT / "scripts" / "build_hunyuan_round2_bundle.py"
ROUND_ID = "hunyuan-psx-r2"
BASELINE = "preserve_hunyuan"
CANDIDATE = "column_box_source_face"
VARIANTS = (BASELINE, CANDIDATE)
TIMEOUT_SECONDS = 300
PROTECTED = (
    "data/scenes/corridor_travel/video.mp4",
    "data/scenes/corridor_travel/images/frame_0152.jpg",
    "godot_walk/assets/corridor_splat/corridor_clean.ply",
    "godot_walk/assets/corridor_splat/corridor_clean.report.json",
    "godot_walk/assets/corridor_splat/collision/corridor_splat.collision.glb",
    "godot_walk/assets/corridor_splat/alignment_manifest.json",
    "godot_walk/assets/psx_extension/textures/floor_source_video.png",
    "godot_walk/assets/psx_extension/textures/wallpaper_source_video.png",
    "godot_walk/assets/psx_extension/textures/ceiling_source_video.png",
    "godot_walk/assets/psx_extension/textures/column_source_video.png",
    "godot_walk/assets/psx_extension/textures/column_face_frame_0152.png",
    "godot_walk/scenes/corridor_psx.tscn",
    "godot_walk/scenes/corridor_psx_room_v2.tscn",
    "godot_walk/scripts/psx_patch_room_extension_v2.gd",
)
PROTECTED_EVIDENCE_DIRS = (
    "2026-10-20-issue-147",
    "2026-10-20-issue-150",
    "2026-10-21-issue-151-round-1",
)

sys.path.insert(0, str(PROJECT / "scripts"))
from hunyuan_round1_contract import SCHEMA_DIR
from hunyuan_round1_records import validate_document, validate_feedback_for_round
from psx_design_round_resources import (
    PeakResourceSampler,
    check_capture_headroom,
)


def main() -> int:
    args = _arguments()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else OUT
    _validate_previous_feedback()
    _validate_protected_paths()
    _validate_output_directory(out_dir)
    binary = shutil.which("godot4") or shutil.which("godot")
    if binary is None:
        raise RuntimeError("Godot 4 executable not found")
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("GPU capture requires the active desktop DISPLAY")

    initial_preflight = check_capture_headroom()
    godot_version = _godot_version(binary)
    out_dir.mkdir(parents=True, exist_ok=True)
    before = _snapshot_protected()
    commands: list[dict[str, Any]] = []
    failure: str | None = None
    try:
        _run_mechanics(binary, out_dir, commands)
        _run_visual_captures(binary, out_dir, commands)
        _run_fps(binary, out_dir, commands)
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
        raise
    finally:
        after = _snapshot_protected()
        _write_execution_log(
            out_dir,
            commands,
            before,
            after,
            initial_preflight,
            godot_version,
            failure,
        )
    if before != after:
        raise RuntimeError("Protected source, Round 1, #147, or #150 inputs changed")

    _run_bundle_builder(out_dir)
    print(f"ROUND_2_READY: {out_dir}")
    return 0


def _arguments() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        help="new evidence directory; existing outputs are never overwritten",
    )
    return parser.parse_args()


def _validate_previous_feedback() -> None:
    manifest = _read_json(ROUND_ONE / "round_manifest.json")
    feedback = _read_json(ROUND_ONE / "operator_feedback.json")
    validate_document(manifest, SCHEMA_DIR / "hunyuan_round.schema.json")
    validate_document(feedback, SCHEMA_DIR / "operator_feedback.schema.json")
    validate_feedback_for_round(feedback, manifest)
    if (
        manifest.get("status") != "operator_reviewed"
        or feedback.get("status") != "confirmed"
    ):
        raise RuntimeError("Round 1 operator feedback must be confirmed before Round 2")


def _validate_protected_paths() -> None:
    missing = [token for token in PROTECTED if not (ROOT / token).is_file()]
    if missing:
        raise FileNotFoundError("Protected input(s) missing: " + ", ".join(missing))
    for issue in PROTECTED_EVIDENCE_DIRS:
        folder = PROJECT / "evidence" / issue
        if not folder.is_dir() or not any(folder.rglob("*")):
            raise FileNotFoundError(
                f"Protected evidence folder missing or empty: {folder}"
            )


def _validate_output_directory(out_dir: Path) -> None:
    try:
        out_dir.relative_to(PROJECT)
    except ValueError as error:
        raise ValueError("Round output must be inside godot_walk/evidence") from error
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RuntimeError(
            f"Evidence path is append-only and already populated: {out_dir}"
        )


def _protected_files() -> list[Path]:
    files = {ROOT / token for token in PROTECTED}
    for issue in PROTECTED_EVIDENCE_DIRS:
        evidence_dir = PROJECT / "evidence" / issue
        files.update(path for path in evidence_dir.rglob("*") if path.is_file())
    return sorted(files)


def _snapshot_protected() -> dict[str, Any]:
    paths = _protected_files()
    relative = tuple(path.relative_to(ROOT).as_posix() for path in paths)
    return {
        "sha256": {token: _sha256(ROOT / token) for token in relative},
        "unstaged_git_diff_sha256": _git_diff_digest(relative, staged=False),
        "staged_git_diff_sha256": _git_diff_digest(relative, staged=True),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_diff_digest(paths: tuple[str, ...], staged: bool) -> str:
    command = ["git", "diff", "--binary"]
    if staged:
        command.append("--cached")
    result = subprocess.run(
        [*command, "--", *paths], cwd=ROOT, capture_output=True, check=True
    )
    return hashlib.sha256(result.stdout).hexdigest()


def _run_mechanics(binary: str, out_dir: Path, commands: list[dict[str, Any]]) -> None:
    runs = [(BASELINE, 1), (BASELINE, 2), (BASELINE, 3), (CANDIDATE, 1)]
    for variant, repeat in runs:
        evidence = out_dir / "mechanics" / variant / f"repeat_{repeat}"
        args = [
            f"--scene={SCENE}",
            f"--out-dir={_resource_path(evidence)}",
            f"--variant={variant}",
            "--trace-state",
        ]
        command = [
            binary,
            "--fixed-fps",
            "60",
            "--path",
            str(PROJECT),
            "--headless",
            "--script",
            VERIFY,
            "--",
            *args,
        ]
        _run_command(f"walk_{variant}_repeat_{repeat}", command, out_dir, commands)
    _run_negative_controls(binary, out_dir, commands)


def _run_negative_controls(
    binary: str, out_dir: Path, commands: list[dict[str, Any]]
) -> None:
    evidence = out_dir / "mechanics" / "negative_controls"
    for mutation in ("boundary", "floor"):
        args = [
            f"--scene={SCENE}",
            f"--out-dir={_resource_path(evidence)}",
            f"--variant={BASELINE}",
            f"--break={mutation}",
        ]
        command = [
            binary,
            "--fixed-fps",
            "60",
            "--path",
            str(PROJECT),
            "--headless",
            "--script",
            VERIFY,
            "--",
            *args,
        ]
        _run_command(f"negative_{mutation}", command, out_dir, commands, (1,))
        report = evidence / f"physics_candidate_broken_{mutation}.json"
        if not report.is_file() or not _read_json(report).get("failures"):
            raise RuntimeError(f"Negative control {mutation} did not fail closed")


def _run_visual_captures(
    binary: str, out_dir: Path, commands: list[dict[str, Any]]
) -> None:
    for variant, repeat in (
        (BASELINE, 1),
        (BASELINE, 2),
        (BASELINE, 3),
        (CANDIDATE, 1),
    ):
        destination = out_dir / "captures" / variant / f"repeat_{repeat}"
        args = [
            f"--scene={SCENE}",
            f"--variant={variant}",
            f"--out={_resource_path(destination)}",
        ]
        command = [
            binary,
            "--fixed-fps",
            "60",
            "--path",
            str(PROJECT),
            "--rendering-driver",
            "vulkan",
            "--resolution",
            "960x540",
            "--disable-vsync",
            "--script",
            CAPTURE,
            "--",
            *args,
        ]
        _run_command(
            f"capture_{variant}_repeat_{repeat}", command, out_dir, commands, gpu=True
        )


def _run_fps(binary: str, out_dir: Path, commands: list[dict[str, Any]]) -> None:
    evidence = out_dir / "mechanics" / CANDIDATE / "repeat_1"
    args = [
        f"--scene={SCENE}",
        f"--out-dir={_resource_path(evidence)}",
        f"--label={CANDIDATE}",
        f"--variant={CANDIDATE}",
        "--capped",
    ]
    command = [
        binary,
        "--path",
        str(PROJECT),
        "--rendering-driver",
        "vulkan",
        "--resolution",
        "1280x720",
        "--disable-vsync",
        "--max-fps",
        "60",
        "--script",
        FPS,
        "--",
        *args,
    ]
    _run_command(f"fps_{CANDIDATE}_capped", command, out_dir, commands, gpu=True)


def _run_command(
    name: str,
    command: list[str],
    out_dir: Path,
    commands: list[dict[str, Any]],
    expected: tuple[int, ...] = (0,),
    gpu: bool = False,
) -> None:
    preflight = check_capture_headroom() if gpu else None
    sampler = PeakResourceSampler() if gpu else None
    if sampler is not None:
        sampler.start()
    timeout = False
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        returncode = result.returncode
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired as error:
        timeout = True
        returncode = None
        output = _timeout_output(error)
    finally:
        resources = sampler.stop() if sampler is not None else None

    log_path = out_dir / "logs" / f"{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")
    record = {
        "name": name,
        "command": command,
        "returncode": returncode,
        "timed_out": timeout,
        "log": log_path.relative_to(out_dir).as_posix(),
        "gpu": gpu,
        "preflight": preflight,
        "resources": resources,
    }
    commands.append(record)
    if timeout:
        raise RuntimeError(f"{name} timed out after {TIMEOUT_SECONDS}s")
    if returncode not in expected:
        raise RuntimeError(f"{name} exited {returncode}; see {log_path}")
    print(f"[{name}] exit {returncode}")


def _timeout_output(error: subprocess.TimeoutExpired) -> str:
    stdout = error.stdout or ""
    stderr = error.stderr or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode(errors="replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode(errors="replace")
    return f"TIMEOUT after {TIMEOUT_SECONDS}s\n{stdout}{stderr}"


def _resource_path(path: Path) -> str:
    return "res://" + path.resolve().relative_to(PROJECT).as_posix()


def _godot_version(binary: str) -> str:
    result = subprocess.run(
        [binary, "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return result.stdout.strip()


def _write_execution_log(
    out_dir: Path,
    commands: list[dict[str, Any]],
    before: dict[str, Any],
    after: dict[str, Any],
    initial_preflight: dict[str, Any],
    godot_version: str,
    failure: str | None,
) -> None:
    record = {
        "round_id": ROUND_ID,
        "status": "failed" if failure else "captures_complete",
        "failure": failure,
        "commands": commands,
        "protected_inputs_before": before,
        "protected_inputs_after": after,
        "protected_inputs_unchanged": before == after,
        "initial_gpu_preflight": initial_preflight,
        "toolchain": {
            "godot": godot_version,
            "python": platform.python_version(),
            "odiff": "odiff-bin@4.5.0",
        },
        "timeout_seconds": TIMEOUT_SECONDS,
        "gpu_preflight_per_capture_and_fps": True,
    }
    path = out_dir / "execution_log.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def _run_bundle_builder(out_dir: Path) -> None:
    command = [sys.executable, str(BUILDER), "--out-dir", str(out_dir)]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Review bundle build timed out") from error
    log = out_dir / "logs" / "build_review_bundle.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"Review bundle build failed; see {log}")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        FileNotFoundError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
