#!/usr/bin/env python3
"""Build and report the source-wallpaper PSX design round for issue #121."""

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
OUT_DIR = "godot_walk/evidence/2026-10-13-psx-design-round-3-source100"
BASELINE = "door_flush"
VARIANTS = (BASELINE, "north_wall_smooth", "north_wall_source_texture")
SETTLE = 200
VIDEO = "data/scenes/corridor_travel/video.mp4"
SOURCE_FRAME = "data/scenes/corridor_travel/images/frame_0001.jpg"
CROP = [1550, 320, 370, 380]
SCOPE = (
    "Compare a flat smooth north wall with the same wall carrying wallpaper sampled "
    "from raw source-video frame 1. Door, room, route, splat, and collision stay fixed."
)
REVIEW_PROMPT = (
    "Does the source-video wallpaper restore the Backrooms identity while keeping "
    "the smoother wall shape? Compare against the flat wall and flush-door control."
)
ROUND_TWO_FEEDBACK = (
    "The operator selected door_flush and said north_wall_smooth had the right wall "
    "shape but lost the original Backrooms texture."
)
FEEDBACK_TEMPLATE = f"""# Operator Feedback: PSX Design Round 3

Round 2 feedback carried forward: {ROUND_TWO_FEEDBACK}

1. `north_wall_smooth` vs `north_wall_source_texture`:
   Choice:
   Reason:
2. `door_flush` vs `north_wall_source_texture`:
   Choice:
   Reason:

Does the wallpaper feel like the original Backrooms surface? Is the pattern too
large, too small, too repetitive, or about right?

Overall: choose a candidate, request a change, or reject both.
Traits to keep:
Remaining problems:
"""
PROTECTED_INPUTS = (
    "assets/corridor_splat/corridor_clean.ply",
    "assets/psx_extension/textures/wallpaper.png",
    "assets/psx_extension/textures/wallpaper_source_video.png",
    "assets/psx_extension/textures/ceiling.png",
    "scenes/corridor_psx_room_v2.tscn",
    "scenes/corridor_psx_design_candidate.tscn",
    "scripts/psx_patch_room_extension_v2.gd",
    "scripts/psx_design_variant_catalog.gd",
    "scripts/psx_design_variant_driver.gd",
    "scripts/capture_psx_design_review.gd",
    "scripts/verify_bounded_psx.gd",
    "scripts/measure_bounded_fps.gd",
    "scripts/psx_design_review_report.py",
    "scripts/psx_design_review_execution.py",
    "design_variants/door_flush.json",
    "design_variants/north_wall_smooth.json",
    "design_variants/north_wall_source_texture.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_inputs() -> dict[str, str]:
    assets = {relative: _sha256(PROJECT / relative) for relative in PROTECTED_INPUTS}
    assets[VIDEO] = _sha256(ROOT / VIDEO)
    assets[SOURCE_FRAME] = _sha256(ROOT / SOURCE_FRAME)
    return assets


def _create_manifest() -> dict:
    return {
        "issue": 121,
        "round": 3,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                      capture_output=True, text=True, check=True).stdout.strip(),
        "scope": SCOPE,
        "round_2_operator_feedback": ROUND_TWO_FEEDBACK,
        "baseline_variant": BASELINE,
        "variants": list(VARIANTS),
        "texture_provenance": {"video": VIDEO, "frame": SOURCE_FRAME,
                                "crop_xywh": CROP, "gaussian_render_used": False},
        "resolution": [1280, 720],
        "fov_degrees": 75,
        "settle_frames": SETTLE,
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
        repeats = 3 if variant == BASELINE else 1
        for repeat in range(1, repeats + 1):
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
        repeats = 3 if variant == BASELINE else 1
        for repeat in range(1, repeats + 1):
            route = out_dir / "mechanics" / variant / f"repeat_{repeat}" / "route_positions.json"
            run_capture(binary, out_dir, manifest, variant, repeat, route)


def _write_report(out_dir: Path, manifest: dict) -> None:
    command = odiff_command()
    metrics = build_report(out_dir, command, variant_ids=VARIANTS,
                           title="PSX Design Round 3: Source Wallpaper",
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
        feedback.write_text(FEEDBACK_TEMPLATE)
    ending = _hash_inputs()
    manifest["source_sha256_end"] = ending
    manifest["protected_inputs_unchanged"] = manifest["source_sha256"] == ending
    (out_dir / "review_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


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
    manifest_path = out_dir / "review_manifest.json"
    if args.report_only:
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("round") != 3 or manifest.get("variants") != list(VARIANTS):
            raise RuntimeError("manifest does not describe PSX design round 3")
        _write_report(out_dir, manifest)
    else:
        binary = os.environ.get("GODOT_BIN", "godot4")
        if shutil.which(binary) is None:
            raise RuntimeError(f"Godot executable not found: {binary}")
        manifest = _create_manifest()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        _run_verification(binary, out_dir, manifest)
        _run_captures(binary, out_dir, manifest)
        _write_report(out_dir, manifest)
    print(f"Design round ready: {out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
