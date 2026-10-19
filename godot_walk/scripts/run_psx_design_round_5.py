#!/usr/bin/env python3
"""Build the next operator-reviewed #121 floor, column, and ceiling loop."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from psx_design_review_execution import odiff_command, run_capture, run_fps, run_verifier
from psx_design_review_report import build_report

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "godot_walk"
OUT_DIR = "godot_walk/evidence/2026-10-14-psx-design-round-5-final"
BASELINE = "door_flush"
VARIANTS = (BASELINE, "source_floor_single_column", "source_floor_ceiling_single_column")
VIDEO = "data/scenes/corridor_travel/video.mp4"
SOURCE_FRAME = "data/scenes/corridor_travel/images/frame_0001.jpg"
TEXTURE_CROPS = {
    "ceiling": [640, 0, 320, 170],
    "floor": [850, 900, 360, 150],
    "column": [610, 300, 100, 400],
}
SCOPE = (
    "Compare door_flush walls with two source-texture candidates: a clean floor and "
    "single aligned column, then the same treatment with a lower ceiling and square "
    "corner trim. The Gaussian PLY, route, and collision remain fixed."
)
REVIEW_PROMPT = (
    "Check that the added column cover reads as the existing single column. Compare "
    "the clean floor and ceiling-wall corners, and note any remaining Gaussian "
    "artifacts or loss of the Backrooms character."
)
PROTECTED_INPUTS = (
    "assets/corridor_splat/corridor_clean.ply",
    "assets/corridor_splat/corridor_clean.report.json",
    "assets/corridor_splat/collision/corridor_splat.collision.glb",
    "assets/corridor_splat/alignment_manifest.json",
    "scenes/corridor_psx.tscn",
    "scenes/corridor_psx_room_v2.tscn",
    "scripts/psx_patch_room_extension_v2.gd",
    "scripts/verify_bounded_psx.gd",
    "scripts/measure_bounded_fps.gd",
    "scripts/capture_psx_design_review.gd",
    "scripts/psx_design_review_report.py",
    "scripts/psx_design_review_execution.py",
    "scripts/psx_design_variant_driver.gd",
    "scripts/psx_design_variant_catalog.gd",
    "design_variants/source_floor_single_column.json",
    "design_variants/source_floor_ceiling_single_column.json",
    "assets/psx_extension/textures/ceiling_source_video.png",
    "assets/psx_extension/textures/floor_source_video.png",
    "assets/psx_extension/textures/column_source_video.png",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_inputs() -> dict[str, str]:
    values = {item: _sha256(PROJECT / item) for item in PROTECTED_INPUTS}
    values[VIDEO] = _sha256(ROOT / VIDEO)
    values[SOURCE_FRAME] = _sha256(ROOT / SOURCE_FRAME)
    return values


def _create_manifest() -> dict:
    return {
        "issue": 121,
        "round": 5,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                      capture_output=True, text=True, check=True).stdout.strip(),
        "scope": SCOPE,
        "baseline_variant": BASELINE,
        "variants": list(VARIANTS),
        "texture_provenance": {"video": VIDEO, "frame": SOURCE_FRAME,
                                "crops_xywh": TEXTURE_CROPS,
                                "gaussian_render_used": False},
        "resolution": [1280, 720],
        "fov_degrees": 75,
        "settle_frames": 200,
        "fixed_fps": 60,
        "rendering_driver": "vulkan",
        "capture_path": "Godot viewport get_image()",
        "source_sha256": _hash_inputs(),
        "commands": [],
        "odiff": None,
    }


def _record(manifest: dict, out_dir: Path, result: dict) -> None:
    manifest["commands"].append(result)
    (out_dir / "review_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def _run_verification(binary: str, out_dir: Path, manifest: dict) -> None:
    for variant in VARIANTS:
        repeat_count = 3 if variant == BASELINE else 1
        for repeat in range(1, repeat_count + 1):
            evidence = out_dir / "mechanics" / variant / f"repeat_{repeat}"
            run_verifier(binary, out_dir, manifest, f"physics_{variant}_{repeat}",
                         evidence, variant)
    for mutation in ("boundary", "floor"):
        evidence = out_dir / "mechanics" / f"negative_{mutation}"
        run_verifier(binary, out_dir, manifest, f"negative_{mutation}", evidence,
                     BASELINE, mutation)


def _run_captures(binary: str, out_dir: Path, manifest: dict) -> None:
    for variant in VARIANTS:
        evidence = out_dir / "mechanics" / variant / "repeat_1"
        for capped in (False, True):
            run_fps(binary, out_dir, manifest, variant, evidence, capped)
        repeat_count = 3 if variant == BASELINE else 1
        for repeat in range(1, repeat_count + 1):
            positions = out_dir / "mechanics" / variant / f"repeat_{repeat}" \
                / "route_positions.json"
            run_capture(binary, out_dir, manifest, variant, repeat, positions)


def _write_report(out_dir: Path, manifest: dict) -> None:
    command = odiff_command()
    metrics = build_report(out_dir, command, variant_ids=VARIANTS,
                           title="PSX Design Round 5: Single Column and Clean Surfaces",
                           scope=SCOPE, review_prompt=REVIEW_PROMPT,
                           baseline_id=BASELINE)
    manifest["odiff"] = {"command": command, "version": "4.5.0", "threshold": 0.1}
    manifest["visual_summary"] = {
        "repeat_noise_max_pct": max(item["max_diff_pct"] for item in metrics["repeat_noise"]),
        "candidate_mean_diff_pct": {item["variant"]: item["mean_diff_pct"]
                                    for item in metrics["candidate_comparisons"]},
    }
    feedback = out_dir / "operator_feedback.md"
    if not feedback.exists():
        feedback.write_text(
            "# Operator Feedback: PSX Design Round 5\n\n"
            "Candidate choice by view:\n\n"
            "Overall walkthrough feel:\n\n"
            "Remaining problems:\n"
        )
    ending = _hash_inputs()
    manifest["source_sha256_end"] = ending
    manifest["protected_inputs_unchanged"] = manifest["source_sha256"] == ending
    (out_dir / "review_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    _write_commands(out_dir)


def _write_commands(out_dir: Path) -> None:
    commands = (
        "# Round 5 Review Commands\n\n"
        "Open matched views in Firefox:\n\n"
        "```sh\nfirefox " + out_dir.relative_to(ROOT).as_posix() + "/index.html\n```\n\n"
        "Run the clean-floor, aligned-column candidate:\n\n"
        "```sh\nDISPLAY=:1 godot4 --path godot_walk "
        "--scene res://scenes/corridor_psx_design_candidate.tscn "
        "-- --variant=source_floor_single_column\n```\n\n"
        "Run the lower-ceiling candidate:\n\n"
        "```sh\nDISPLAY=:1 godot4 --path godot_walk "
        "--scene res://scenes/corridor_psx_design_candidate.tscn "
        "-- --variant=source_floor_ceiling_single_column\n```\n\n"
        "Reproduce captures and mechanics:\n\n"
        "```sh\nDISPLAY=:1 python3 godot_walk/scripts/run_psx_design_round_5.py\n```\n"
    )
    (out_dir / "COMMANDS.md").write_text(commands)


def _resolve_out_dir(value: str, report_only: bool) -> Path:
    requested = Path(value)
    out_dir = (ROOT / requested).resolve() if not requested.is_absolute() else requested.resolve()
    try:
        out_dir.relative_to(PROJECT)
    except ValueError as error:
        raise RuntimeError("review evidence must be inside godot_walk") from error
    if not report_only and out_dir.exists() and any(out_dir.iterdir()):
        raise RuntimeError(f"evidence directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=OUT_DIR)
    parser.add_argument("--report-only", action="store_true",
                        help="rebuild ODiff and the HTML review from completed captures")
    args = parser.parse_args()
    out_dir = _resolve_out_dir(args.out_dir, args.report_only)
    if args.report_only:
        manifest = json.loads((out_dir / "review_manifest.json").read_text())
        if manifest.get("round") != 5 or manifest.get("variants") != list(VARIANTS):
            raise RuntimeError("manifest does not describe PSX design round 5")
        _write_report(out_dir, manifest)
    else:
        _run_full_review(out_dir)
    print(f"Design round ready: {out_dir / 'index.html'}")
    return 0


def _run_full_review(out_dir: Path) -> None:
    binary = os.environ.get("GODOT_BIN", "godot4")
    if shutil.which(binary) is None:
        raise RuntimeError(f"Godot executable not found: {binary}")
    manifest = _create_manifest()
    (out_dir / "review_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    _run_verification(binary, out_dir, manifest)
    _run_captures(binary, out_dir, manifest)
    _write_report(out_dir, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
