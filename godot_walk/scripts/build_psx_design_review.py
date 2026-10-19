#!/usr/bin/env python3
"""Run the reproducible capture, traversal, and comparison bundle for #120."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from psx_design_review_execution import odiff_command, run_capture, run_fps, run_verifier
from psx_design_review_report import build_report

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "godot_walk"
SCENE = "res://scenes/corridor_psx_design_candidate.tscn"
VARIANTS = ("v2_control", "door_flush", "door_removed")
SETTLE = 200
PROTECTED_INPUTS = (
    "assets/corridor_splat/corridor_clean.ply",
    "scenes/corridor_psx_room_v2.tscn",
    "scripts/psx_patch_room_extension_v2.gd",
    "scenes/corridor_psx_design_candidate.tscn",
    "scripts/psx_design_variant_driver.gd",
    "design_variants/v2_control.json",
    "design_variants/door_flush.json",
    "design_variants/door_removed.json",
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _hash_inputs() -> dict[str, str]:
    hashes = {}
    for relative in PROTECTED_INPUTS:
        path = PROJECT / relative
        if path.is_file():
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _route_run_drift(reference: dict, samples: list[dict], repeat: int) -> dict:
    deltas = []
    mismatches = 0
    for sample in samples:
        prior = reference.get(sample["tick"])
        if prior is None:
            continue
        delta = sum((float(a) - float(b)) ** 2
                    for a, b in zip(sample["position"], prior["position"])) ** 0.5
        deltas.append(delta)
        if sample["contacts"] != prior["contacts"] or sample["on_floor"] != prior["on_floor"]:
            mismatches += 1
    return {"repeat": repeat, "reference_ticks": len(reference),
            "repeat_ticks": len(samples), "compared_ticks": len(deltas),
            "max_position_drift_m": max(deltas, default=0.0),
            "contact_or_floor_mismatch_ticks": mismatches}


def _route_drift(out_dir: Path) -> dict:
    base = out_dir / "mechanics" / "v2_control"
    traces = [_read_json(base / f"repeat_{index}" / "physics_candidate.json")
              .get("route_state_trace", []) for index in range(1, 4)]
    reference = {sample["tick"]: sample for sample in traces[0]}
    comparisons = [_route_run_drift(reference, samples, index)
                   for index, samples in enumerate(traces[1:], start=2)]
    return {"determinism_assumed": False, "comparisons_to_repeat_1": comparisons}


def _create_manifest() -> dict:
    return {"created_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                          capture_output=True, text=True, check=True).stdout.strip(),
            "scope": "Only doorway_policy varies; room, splat, route and collision are locked.",
            "variants": list(VARIANTS), "resolution": [1280, 720], "fov_degrees": 75,
            "settle_frames": SETTLE, "fixed_fps": 60, "rendering_driver": "vulkan",
            "capture_path": "Godot get_image() from the rendered viewport",
            "route_state_trace": "Per-physics-tick position, eye, velocity, floor and contacts; drift is measured, not assumed zero.",
            "source_sha256": _hash_inputs(), "commands": [], "odiff": None}


def _add_visual_summary(manifest: dict, out_dir: Path, odiff: list[str]) -> None:
    metrics = build_report(out_dir, odiff)
    manifest["odiff"] = {"command": odiff, "version": "4.5.0", "threshold": 0.1}
    manifest["visual_summary"] = {"repeat_noise_max_pct": max(
        item["max_diff_pct"] for item in metrics["repeat_noise"]),
        "candidate_mean_diff_pct": {item["variant"]: item["mean_diff_pct"]
                                    for item in metrics["candidate_comparisons"]}}


def _record_input_end(manifest: dict) -> None:
    final_hashes = _hash_inputs()
    manifest["source_sha256_end"] = final_hashes
    manifest["protected_inputs_unchanged"] = manifest["source_sha256"] == final_hashes


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


def _run_report_only(out_dir: Path) -> None:
    path = out_dir / "review_manifest.json"
    if not path.is_file():
        raise RuntimeError(f"review manifest not found: {path}")
    manifest = _read_json(path)
    _add_visual_summary(manifest, out_dir, odiff_command())
    _record_input_end(manifest)
    manifest.pop("failure", None)
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def _run_physics(binary: str, out_dir: Path, manifest: dict) -> None:
    for variant in VARIANTS:
        for repeat in range(1, 4 if variant == "v2_control" else 2):
            evidence = out_dir / "mechanics" / variant / f"repeat_{repeat}"
            run_verifier(binary, out_dir, manifest, f"physics_{variant}_{repeat}",
                         evidence, variant)
    for mutation in ("boundary", "floor"):
        evidence = out_dir / "mechanics" / f"negative_{mutation}"
        run_verifier(binary, out_dir, manifest, "negative_" + mutation,
                     evidence, "v2_control", mutation)


def _run_performance_and_captures(binary: str, out_dir: Path, manifest: dict) -> None:
    for variant in VARIANTS:
        evidence = out_dir / "mechanics" / variant / "repeat_1"
        run_fps(binary, out_dir, manifest, variant, evidence, False)
        run_fps(binary, out_dir, manifest, variant, evidence, True)
        for repeat in range(1, 4 if variant == "v2_control" else 2):
            positions = out_dir / "mechanics" / variant / f"repeat_{repeat}" / "route_positions.json"
            run_capture(binary, out_dir, manifest, variant, repeat, positions)


def _run_full_review(out_dir: Path, binary: str) -> None:
    manifest_path = out_dir / "review_manifest.json"
    manifest = _create_manifest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    try:
        _run_physics(binary, out_dir, manifest)
        _run_performance_and_captures(binary, out_dir, manifest)
        (out_dir / "route_drift.json").write_text(json.dumps(_route_drift(out_dir), indent=2) + "\n")
        _add_visual_summary(manifest, out_dir, odiff_command())
        _record_input_end(manifest)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        manifest["failure"] = str(error)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="godot_walk/evidence/2026-10-13-psx-design-review")
    parser.add_argument("--report-only", action="store_true",
                        help="rebuild ODiff metrics and HTML from existing captures")
    args = parser.parse_args()
    out_dir = _resolve_out_dir(args.out_dir, args.report_only)
    if args.report_only:
        _run_report_only(out_dir)
    else:
        binary = os.environ.get("GODOT_BIN", "godot4")
        if shutil.which(binary) is None:
            raise RuntimeError(f"Godot executable not found: {binary}")
        _run_full_review(out_dir, binary)
    print(f"Review bundle ready: {out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
