"""Build and validate the first operator-reviewed Hunyuan PSX design round."""

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
OUT = PROJECT / "evidence" / "2026-10-21-issue-151-round-1"
SCENE = "res://scenes/hunyuan_psx_round1.tscn"
CAPTURE = "res://scripts/capture_hunyuan_psx_round1.gd"
VERIFY = "res://scripts/verify_bounded_psx.gd"
FPS = "res://scripts/measure_bounded_fps.gd"
BUILDER = PROJECT / "scripts" / "build_hunyuan_round1_bundle.py"
TIMEOUT_SECONDS = 300
VARIANTS = ("preserve_hunyuan", "source_surface_cleanup")
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
    "godot_walk/scenes/corridor_psx.tscn",
    "godot_walk/scenes/corridor_psx_room_v2.tscn",
    "godot_walk/scripts/psx_patch_room_extension_v2.gd",
    "godot_walk/evidence/2026-10-20-issue-147/hunyuan_layers.glb",
    "godot_walk/evidence/2026-10-20-issue-147/source_selection.json",
    "godot_walk/evidence/2026-10-20-issue-150/module_manifest.json",
    "godot_walk/evidence/2026-10-20-issue-150/authored_room_collision.glb",
)

sys.path.insert(0, str(PROJECT / "scripts"))
from psx_design_round_resources import PeakResourceSampler, check_capture_headroom  # noqa: I001


def main() -> int:
    args = _arguments()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else OUT
    _prepare_output_directory(out_dir)
    binary = shutil.which("godot4") or shutil.which("godot")
    if binary is None:
        raise RuntimeError("Godot 4 executable not found")
    godot_version = _godot_version(binary)
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("GPU capture requires the active desktop DISPLAY")
    initial_gpu_preflight = check_capture_headroom()
    _validate_protected_paths()
    out_dir.mkdir(parents=True, exist_ok=True)
    before = _snapshot_protected()
    commands: list[dict[str, Any]] = []
    _run_mechanics(binary, out_dir, commands)
    _run_visual_captures(binary, out_dir, commands)
    _run_fps(binary, out_dir, commands)
    after = _snapshot_protected()
    if before != after:
        raise RuntimeError(
            "Protected #100/#115, #147 or #150 inputs changed during the round"
        )
    _write_execution_log(
        out_dir, commands, before, after, initial_gpu_preflight, godot_version
    )
    _run_bundle_builder(out_dir)
    print(f"ROUND_1_READY: {out_dir}")
    return 0


def _prepare_output_directory(out_dir: Path) -> None:
    bootstrap_files = {"COMMANDS.md", "candidate_layout.svg"}
    if out_dir == OUT:
        if (
            out_dir.exists()
            and {path.name for path in out_dir.iterdir()} - bootstrap_files
        ):
            raise RuntimeError(
                f"Evidence path is append-only and already populated: {out_dir}"
            )
        out_dir.mkdir(parents=True, exist_ok=True)
        return
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RuntimeError(
            f"Evidence path is append-only and already populated: {out_dir}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in bootstrap_files:
        shutil.copyfile(OUT / name, out_dir / name)


def _arguments() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        help="new evidence directory; existing outputs are never overwritten",
    )
    return parser.parse_args()


def _validate_protected_paths() -> None:
    missing = [path for path in PROTECTED if not (ROOT / path).is_file()]
    if missing:
        raise FileNotFoundError("Protected input(s) missing: " + ", ".join(missing))


def _protected_files() -> list[Path]:
    files = {ROOT / token for token in PROTECTED}
    for issue in ("2026-10-20-issue-147", "2026-10-20-issue-150"):
        evidence_dir = PROJECT / "evidence" / issue
        files.update(path for path in evidence_dir.rglob("*") if path.is_file())
    return sorted(files)


def _snapshot_protected() -> dict[str, Any]:
    paths = _protected_files()
    relative = tuple(path.relative_to(ROOT).as_posix() for path in paths)
    hashes = {token: _sha256(ROOT / token) for token in relative}
    unstaged = _git_diff_digest(relative, staged=False)
    staged = _git_diff_digest(relative, staged=True)
    return {
        "sha256": hashes,
        "unstaged_git_diff_sha256": unstaged,
        "staged_git_diff_sha256": staged,
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
    for variant in VARIANTS:
        repeats = range(1, 4) if variant == "preserve_hunyuan" else range(1, 2)
        for repeat in repeats:
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
            commands.append(
                _run_command(f"walk_{variant}_repeat_{repeat}", command, out_dir)
            )
    for mutation in ("boundary", "floor"):
        evidence = out_dir / "mechanics" / "negative_controls"
        args = [
            f"--scene={SCENE}",
            f"--out-dir={_resource_path(evidence)}",
            "--variant=preserve_hunyuan",
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
        record = _run_command(f"negative_{mutation}", command, out_dir, expected=(1,))
        report = evidence / f"physics_candidate_broken_{mutation}.json"
        if not report.is_file() or not json.loads(report.read_text()).get("failures"):
            raise RuntimeError(f"Negative control {mutation} did not fail closed")
        commands.append(record)


def _run_visual_captures(
    binary: str, out_dir: Path, commands: list[dict[str, Any]]
) -> None:
    runs = [
        ("preserve_hunyuan", 1),
        ("preserve_hunyuan", 2),
        ("preserve_hunyuan", 3),
        ("source_surface_cleanup", 1),
    ]
    for variant, repeat in runs:
        destination = out_dir / "captures" / variant / f"repeat_{repeat}"
        args = [f"--variant={variant}", f"--out={_resource_path(destination)}"]
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
        commands.append(
            _run_command(
                f"capture_{variant}_repeat_{repeat}", command, out_dir, gpu=True
            )
        )


def _run_fps(binary: str, out_dir: Path, commands: list[dict[str, Any]]) -> None:
    evidence = out_dir / "mechanics" / "source_surface_cleanup" / "repeat_1"
    args = [
        f"--scene={SCENE}",
        f"--out-dir={_resource_path(evidence)}",
        "--label=source_surface_cleanup",
        "--variant=source_surface_cleanup",
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
    commands.append(
        _run_command("fps_source_surface_cleanup_capped", command, out_dir, gpu=True)
    )


def _run_command(
    name: str,
    command: list[str],
    out_dir: Path,
    expected: tuple[int, ...] = (0,),
    gpu: bool = False,
) -> dict[str, Any]:
    preflight = check_capture_headroom() if gpu else None
    sampler = PeakResourceSampler() if gpu else None
    if sampler is not None:
        sampler.start()
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
        raise RuntimeError(f"{name} timed out after {TIMEOUT_SECONDS}s") from error
    finally:
        resource_sample = sampler.stop() if sampler is not None else None
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    record = {
        "name": name,
        "command": command,
        "returncode": result.returncode,
        "log": log_path.relative_to(out_dir).as_posix(),
        "gpu": gpu,
        "preflight": preflight,
        "resources": resource_sample,
    }
    if result.returncode not in expected:
        raise RuntimeError(f"{name} exited {result.returncode}; see {log_path}")
    print(f"[{name}] exit {result.returncode}")
    return record


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
    initial_gpu_preflight: dict[str, Any],
    godot_version: str,
) -> None:
    record = {
        "round_id": "hunyuan-psx-r1",
        "commands": commands,
        "protected_inputs_before": before,
        "protected_inputs_after": after,
        "protected_inputs_unchanged": before == after,
        "initial_gpu_preflight": initial_gpu_preflight,
        "toolchain": {
            "godot": godot_version,
            "python": platform.python_version(),
            "odiff": "odiff-bin@4.5.0",
        },
        "timeout_seconds": TIMEOUT_SECONDS,
        "gpu_preflight_per_capture_and_fps": True,
    }
    (out_dir / "execution_log.json").write_text(json.dumps(record, indent=2) + "\n")


def _run_bundle_builder(out_dir: Path) -> None:
    command = [sys.executable, str(BUILDER), "--out-dir", str(out_dir)]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    (out_dir / "logs" / "build_review_bundle.log").write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Review bundle build failed; see logs/build_review_bundle.log"
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
