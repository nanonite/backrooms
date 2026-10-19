#!/usr/bin/env python3
"""Build a source-textured artifact-cleanup review for issue #121."""

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
OUT_DIR = "godot_walk/evidence/2026-10-14-psx-design-round-4"
BASELINE = "door_flush"
VARIANTS = (BASELINE, "north_wall_source_texture", "source_texture_cleanup")
SETTLE = 200
VIDEO = "data/scenes/corridor_travel/video.mp4"
SOURCE_FRAME = "data/scenes/corridor_travel/images/frame_0001.jpg"
TEXTURE_CROPS = {
    "wall": [1550, 320, 370, 380],
    "ceiling": [640, 0, 320, 170],
    "floor": [850, 900, 360, 150],
    "column": [610, 300, 100, 400],
}
SCOPE = (
    "Compare the flush-door control and north-wall texture against a visual-only "
    "candidate that source-textures the square wall shell, ceiling, floor, and column. "
    "The Gaussian PLY, collision, route, and door remain fixed."
)
REVIEW_PROMPT = (
    "Review wall and corner coverage from every angle, column alignment, ceiling and "
    "floor texture, and the overall walk. Does the new candidate hide the artifacts "
    "without erasing the Backrooms character?"
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
        "round": 4,
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
                           title="PSX Design Round 4: Source-Texture Cleanup",
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
            "# Operator Feedback: PSX Design Round 4\n\n"
            "Review the wall/corner, column, ceiling, and floor from matched angles. "
            "Note where `door_flush` preserves texture better than the source-textured "
            "candidate, and whether the room still feels coherent during the live walk.\n\n"
            "Candidate choice by view:\n\n"
            "Overall walkthrough feel:\n\n"
            "Remaining problems:\n"
        )
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
        if manifest.get("round") != 4 or manifest.get("variants") != list(VARIANTS):
            raise RuntimeError("manifest does not describe PSX design round 4")
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
