#!/usr/bin/env python3
"""Execute a checked-in, operator-reviewed PSX design round."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from psx_design_round_protection import snapshot_protected_inputs, verify_protected_inputs
from psx_design_round_reproduction import compare_reproduction
from psx_design_round_resources import PeakResourceSampler, check_capture_headroom
from psx_design_round_spec import ROOT, load_spec
from psx_design_review_execution import odiff_command, run_capture, run_fps, run_verifier
from psx_design_review_report import build_report

PROJECT = ROOT / "godot_walk"
SCENE = "res://scenes/corridor_psx_design_candidate.tscn"
SUPPORTED_RESOLUTION = [1280, 720]
SUPPORTED_FOV = 75
SUPPORTED_FPS = 60
SUPPORTED_SETTLE = 200


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--out-dir", type=Path,
                        help="new evidence directory; defaults to the spec's out_dir")
    parser.add_argument("--compare-to", type=Path,
                        help="compare gate outcomes and ODiff metrics with prior evidence")
    args = parser.parse_args()
    try:
        spec_path = args.spec if args.spec.is_absolute() else ROOT / args.spec
        spec = load_spec(spec_path.resolve())
        _validate_supported_contract(spec)
        initial_preflight = check_capture_headroom()
        out_dir = _resolve_out_dir(args.out_dir or Path(spec["out_dir"]))
        manifest = _run_full_review(spec, spec_path.resolve(), out_dir, initial_preflight)
        if args.compare_to:
            comparison = compare_reproduction(args.compare_to.resolve(), out_dir,
                                              spec["variants"])
            (out_dir / "reproduction_report.json").write_text(
                json.dumps(comparison, indent=2) + "\n")
            manifest["reproduction"] = comparison
            _write_manifest(out_dir, manifest)
            if not comparison["passed"]:
                raise RuntimeError(f"reproduction check failed; see {out_dir / 'reproduction_report.json'}")
        print(f"Design round ready: {out_dir / 'index.html'}")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


def _validate_supported_contract(spec: dict[str, Any]) -> None:
    if spec["resolution"] != SUPPORTED_RESOLUTION:
        raise ValueError(f"execution helper requires resolution {SUPPORTED_RESOLUTION}")
    if spec["fov_degrees"] != SUPPORTED_FOV:
        raise ValueError(f"capture helper requires FOV {SUPPORTED_FOV}")
    if spec["fixed_fps"] != SUPPORTED_FPS or spec["settle_frames"] != SUPPORTED_SETTLE:
        raise ValueError("execution helper requires fixed 60 FPS and 200 settle frames")
    if spec["rendering_driver"] != "vulkan":
        raise ValueError("design review captures require Vulkan")


def _resolve_out_dir(value: Path) -> Path:
    out_dir = value if value.is_absolute() else ROOT / value
    out_dir = out_dir.resolve()
    try:
        out_dir.relative_to(PROJECT / "evidence")
    except ValueError as error:
        raise RuntimeError("review evidence must be inside godot_walk/evidence") from error
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RuntimeError(f"evidence directory is not empty; evidence is append-only: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _run_full_review(spec: dict[str, Any], spec_path: Path,
                     out_dir: Path, initial_preflight: dict[str, Any]) -> dict[str, Any]:
    binary = os.environ.get("GODOT_BIN", "godot4")
    if shutil.which(binary) is None:
        raise RuntimeError(f"Godot executable not found: {binary}")
    protected_start = snapshot_protected_inputs(spec, out_dir)
    manifest = _create_manifest(spec, spec_path, protected_start)
    manifest["initial_gpu_preflight"] = initial_preflight
    _write_manifest(out_dir, manifest)
    started = time.monotonic()
    sampler = PeakResourceSampler()
    sampler.start()
    try:
        _run_verification(binary, spec, out_dir, manifest)
        _run_captures(binary, spec, out_dir, manifest)
        _write_report(spec, out_dir, manifest)
    finally:
        manifest["resource_usage"] = sampler.stop()
        manifest["runtime_seconds"] = round(time.monotonic() - started, 3)
        manifest["protected_inputs_end"] = verify_protected_inputs(
            spec, out_dir, protected_start)
        manifest["protected_inputs_unchanged"] = manifest["protected_inputs_end"]["unchanged"]
        _write_manifest(out_dir, manifest)
    if not manifest["protected_inputs_end"]["unchanged"]:
        raise RuntimeError("protected inputs changed during the round")
    return manifest


def _create_manifest(spec: dict[str, Any], spec_path: Path,
                     protected: dict[str, Any]) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "round_id": spec["round_id"],
        "issue": spec["issue"],
        "round": spec["round_number"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "spec": spec_path.relative_to(ROOT).as_posix(),
        "title": spec["title"],
        "scope": spec["scope"],
        "review_prompt": spec["review_prompt"],
        "baseline_variant": spec["baseline"],
        "variants": spec["variants"],
        "repeat_count": spec["repeat_count"],
        "texture_provenance": _texture_provenance(spec),
        "resolution": spec["resolution"],
        "fov_degrees": spec["fov_degrees"],
        "settle_frames": spec["settle_frames"],
        "fixed_fps": spec["fixed_fps"],
        "rendering_driver": spec["rendering_driver"],
        "capture_path": spec["capture_path"],
        "protected_inputs_start": protected["sha256"],
        "protected_input_git_diff_sha256_start": protected["git_diff_sha256"],
        "protected_input_file_count": protected["file_count"],
        "commands": [],
        "odiff": None,
    }
    if spec.get("inherited_feedback"):
        manifest["inherited_feedback"] = spec["inherited_feedback"]
    return manifest


def _texture_provenance(spec: dict[str, Any]) -> dict[str, Any]:
    if "video" not in spec:
        return {"gaussian_render_used": False, "crops_xywh": spec["texture_crops"]}
    return {"video": spec["video"], "frame": spec["source_frame"],
            "crops_xywh": spec["texture_crops"], "gaussian_render_used": False}


def _run_verification(binary: str, spec: dict[str, Any], out_dir: Path,
                      manifest: dict[str, Any]) -> None:
    for variant in spec["variants"]:
        repeats = spec["repeat_count"] if variant == spec["baseline"] else 1
        for repeat in range(1, repeats + 1):
            evidence = out_dir / "mechanics" / variant / f"repeat_{repeat}"
            run_verifier(binary, out_dir, manifest, f"physics_{variant}_{repeat}",
                         evidence, variant)
    for mutation in spec["negative_controls"]:
        evidence = out_dir / "mechanics" / f"negative_{mutation}"
        run_verifier(binary, out_dir, manifest, f"negative_{mutation}", evidence,
                     spec["baseline"], mutation)


def _run_captures(binary: str, spec: dict[str, Any], out_dir: Path,
                  manifest: dict[str, Any]) -> None:
    for variant in spec["variants"]:
        evidence = out_dir / "mechanics" / variant / "repeat_1"
        _run_gpu_step(lambda: run_fps(binary, out_dir, manifest, variant, evidence, False),
                      manifest, out_dir)
        _run_gpu_step(lambda: run_fps(binary, out_dir, manifest, variant, evidence, True),
                      manifest, out_dir)
        repeats = spec["repeat_count"] if variant == spec["baseline"] else 1
        for repeat in range(1, repeats + 1):
            positions = out_dir / "mechanics" / variant / f"repeat_{repeat}" \
                / "route_positions.json"
            _run_gpu_step(
                lambda: run_capture(binary, out_dir, manifest, variant, repeat, positions),
                manifest, out_dir)


def _run_gpu_step(action: Callable[[], None], manifest: dict[str, Any],
                  out_dir: Path) -> None:
    preflight = check_capture_headroom()
    action()
    if not manifest["commands"]:
        raise RuntimeError("execution helper did not record its GPU command")
    manifest["commands"][-1]["gpu_preflight"] = preflight
    _write_manifest(out_dir, manifest)


def _write_report(spec: dict[str, Any], out_dir: Path,
                  manifest: dict[str, Any]) -> None:
    command = odiff_command()
    metrics = build_report(
        out_dir, command, variant_ids=tuple(spec["variants"]), title=spec["title"],
        scope=spec["scope"], review_prompt=spec["review_prompt"],
        baseline_id=spec["baseline"])
    manifest["odiff"] = {"command": command, "version": "4.5.0", "threshold": 0.1}
    manifest["visual_summary"] = {
        "repeat_noise_max_pct": max(row["max_diff_pct"] for row in metrics["repeat_noise"]),
        "candidate_mean_diff_pct": {
            row["variant"]: row["mean_diff_pct"]
            for row in metrics["candidate_comparisons"]
        },
    }
    feedback = out_dir / "operator_feedback.md"
    if not feedback.exists():
        feedback.write_text(spec["feedback_template"])
    if spec["route_drift"]:
        drift = _route_drift(out_dir, spec["baseline"], spec["repeat_count"])
        manifest["route_drift"] = drift
        (out_dir / "route_drift.json").write_text(json.dumps(drift, indent=2) + "\n")
    _write_commands(spec, out_dir)


def _route_drift(out_dir: Path, baseline: str, repeat_count: int) -> dict[str, Any]:
    root = out_dir / "mechanics" / baseline
    traces = [json.loads((root / f"repeat_{index}" / "physics_candidate.json").read_text())
              .get("route_state_trace", []) for index in range(1, repeat_count + 1)]
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
    return {"baseline": baseline, "determinism_assumed": False,
            "comparisons_to_repeat_1": comparisons}


def _write_commands(spec: dict[str, Any], out_dir: Path) -> None:
    relative = out_dir.relative_to(ROOT).as_posix()
    lines = [f"# {spec['title']} Commands", "", "Open matched views:", "",
             "```sh", f"firefox {relative}/index.html", "```", "",
             "Run the live walkthrough:", "", "```sh",
             "DISPLAY=:1 godot4 --path godot_walk "
             "--scene res://scenes/corridor_psx_design_candidate.tscn "
             f"-- --variant={spec['baseline']}", "```", "",
             "Reproduce this round into a fresh evidence directory:", "", "```sh",
             "DISPLAY=:1 python3 godot_walk/scripts/run_psx_design_round.py "
             f"--spec godot_walk/design_rounds/{spec['round_id']}.json "
             f"--out-dir {relative}-reproduction", "```", ""]
    (out_dir / "COMMANDS.md").write_text("\n".join(lines))


def _git_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, check=True)
    return result.stdout.strip()


def _write_manifest(out_dir: Path, manifest: dict[str, Any]) -> None:
    (out_dir / "review_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
