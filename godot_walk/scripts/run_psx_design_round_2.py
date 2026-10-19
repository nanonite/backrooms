#!/usr/bin/env python3
"""Build and report the feedback-driven PSX design round 2 for issue #121."""

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
OUT_DIR = "godot_walk/evidence/2026-10-13-psx-design-round-2-final"
BASELINE = "door_flush"
VARIANTS = (BASELINE, "north_wall_smooth", "clean_ceiling")
SETTLE = 200
TITLE = "PSX Design Round 2: Wall and Ceiling Treatments"
SCOPE = (
    "Carry forward the operator-selected flush hatch. Compare a smoothed north wall "
    "with a clean ceiling grid; splat, route, room envelope, and collision remain fixed."
)
REVIEW_PROMPT = (
    "Does the north-wall treatment make the right-hand wall feel more intentional? "
    "Does the clean ceiling reduce distracting artifacts? Choose a candidate, request "
    "a combination, or reject both."
)
ROUND_ONE_FEEDBACK = (
    "The operator preferred door_flush at far_room/E, patch_anchor/E, "
    "transition/E, and column/E. The right-hand wall needs smoothing and a more "
    "coherent design; ceiling Gaussian artifacts remain distracting."
)
FEEDBACK_TEMPLATE = f"""# Operator Feedback: PSX Design Round 2

Round 1 feedback carried forward: {ROUND_ONE_FEEDBACK}

Compare matched views in the three columns. The first is the selected `door_flush`
baseline, the second adds north-wall paneling, and the third adds a lowered ceiling
tile grid. Record what improves, what still feels wrong, and what should carry into
the next round.

1. `door_flush` vs `north_wall_smooth` (right-hand north wall):
   Choice:
   Reason:
2. `door_flush` vs `clean_ceiling` (ceiling treatment):
   Choice:
   Reason:
3. `north_wall_smooth` vs `clean_ceiling`:
   Choice:
   Reason:

Overall: choose a candidate, request a combination, reject all, or name a new direction.
Traits to keep:
Remaining problems:
Would you approve one candidate as the room to carry forward? Why?
"""
PROTECTED_INPUTS = (
    "assets/corridor_splat/corridor_clean.ply",
    "assets/psx_extension/textures/wallpaper.png",
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
    "design_variants/clean_ceiling.json",
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _hash_inputs() -> dict[str, str]:
    return {relative: hashlib.sha256((PROJECT / relative).read_bytes()).hexdigest()
            for relative in PROTECTED_INPUTS}


def _record(manifest: dict, out_dir: Path, command: dict) -> None:
    manifest["commands"].append(command)
    (out_dir / "review_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def _route_drift(out_dir: Path) -> dict:
    root = out_dir / "mechanics" / BASELINE
    traces = [_read_json(root / f"repeat_{index}" / "physics_candidate.json")
              .get("route_state_trace", []) for index in range(1, 4)]
    reference = {sample["tick"]: sample for sample in traces[0]}
    comparisons = []
    for repeat, samples in enumerate(traces[1:], start=2):
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
        comparisons.append({"repeat": repeat, "compared_ticks": len(deltas),
                            "max_position_drift_m": max(deltas, default=0.0),
                            "contact_or_floor_mismatch_ticks": mismatches})
    return {"baseline": BASELINE, "determinism_assumed": False,
            "comparisons_to_repeat_1": comparisons}


def _create_manifest() -> dict:
    return {
        "issue": 121,
        "round": 2,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                      capture_output=True, text=True, check=True).stdout.strip(),
        "scope": SCOPE,
        "round_1_operator_feedback": ROUND_ONE_FEEDBACK,
        "baseline_variant": BASELINE,
        "variants": list(VARIANTS),
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


def _run_captures_and_fps(binary: str, out_dir: Path, manifest: dict) -> None:
    for variant in VARIANTS:
        evidence = out_dir / "mechanics" / variant / "repeat_1"
        run_fps(binary, out_dir, manifest, variant, evidence, False)
        run_fps(binary, out_dir, manifest, variant, evidence, True)
        repeats = 3 if variant == BASELINE else 1
        for repeat in range(1, repeats + 1):
            route = out_dir / "mechanics" / variant / f"repeat_{repeat}" / "route_positions.json"
            run_capture(binary, out_dir, manifest, variant, repeat, route)


def _report(out_dir: Path, manifest: dict) -> None:
    command = odiff_command()
    metrics = build_report(out_dir, command, variant_ids=VARIANTS,
                           title=TITLE, scope=SCOPE, review_prompt=REVIEW_PROMPT,
                           baseline_id=BASELINE)
    manifest["odiff"] = {"command": command, "version": "4.5.0", "threshold": 0.1}
    manifest["visual_summary"] = {
        "repeat_noise_max_pct": max(item["max_diff_pct"] for item in metrics["repeat_noise"]),
        "candidate_mean_diff_pct": {item["variant"]: item["mean_diff_pct"]
                                    for item in metrics["candidate_comparisons"]},
    }
    drift = _route_drift(out_dir)
    manifest["route_drift"] = drift
    (out_dir / "route_drift.json").write_text(json.dumps(drift, indent=2) + "\n")
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
        manifest = _read_json(manifest_path)
        if manifest.get("round") != 2 or manifest.get("variants") != list(VARIANTS):
            raise RuntimeError("manifest does not describe PSX design round 2")
        _report(out_dir, manifest)
    else:
        binary = os.environ.get("GODOT_BIN", "godot4")
        if shutil.which(binary) is None:
            raise RuntimeError(f"Godot executable not found: {binary}")
        manifest = _create_manifest()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        _run_verification(binary, out_dir, manifest)
        _run_captures_and_fps(binary, out_dir, manifest)
        _report(out_dir, manifest)
    print(f"Design round ready: {out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
