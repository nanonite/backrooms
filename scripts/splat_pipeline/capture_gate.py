#!/usr/bin/env python3
"""Validate a capture before reconstruction, and explain what it cannot support.

Runs the bounded sampling scan over a video, selects the frames a reconstruction
should use, measures what those frames cover and what they fail to explain, and
prints one verdict with the measurements behind it.

Usage:
    python3 scripts/splat_pipeline/capture_gate.py <video.mp4> [options]

Options:
    --budget PATH               JSON budget file (keys match SamplingBudget fields)
    --target-frames N           frames to select (default 150)
    --max-candidates N          frames scored before selection (default 240)
    --analysis-max-pixels N     pixels per analysed frame (default 230400)
    --max-sample-seconds F      ceiling for the sampling stage (default 120)
    --decode-mode MODE          auto | stream | seek (default auto)
    --staging-dir PATH          where frames will be written, for the disk estimate
    --json PATH                 write the full report as JSON
    -h, --help                  show this message

Exit codes:
    0  accepted, possibly with warnings
    1  usage error
    2  a prerequisite is missing (ffmpeg / ffprobe)
    3  rejected: this capture cannot support a coherent walkable scene
    4  the input could not be read or probed
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import capture_verdict
import sampling_budget
from candidate_scan import scan_capture
from frame_selection import select_frames
from geometry_consistency import classify_consistency
from matching_plan import MatchingPlan, build_plan, colmap_matching_commands
from resource_estimate import (
    ResourceEstimationError,
    ResourceEstimate,
    ResourceVerdict,
    estimate_selection,
    evaluate_resources,
    measure_host,
)
from sampling_budget import BudgetError, SamplingBudget
from video_probe import VideoMetadata, VideoProbeError, probe_video
from view_coverage import measure_coverage

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_MISSING_TOOL = 2
EXIT_REJECTED = 3
EXIT_UNREADABLE = 4

GIBIBYTE = 1024**3


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="capture_gate.py",
        description="Validate a capture for walkable-splat reconstruction.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video", help="path to the capture video")
    parser.add_argument("--budget", help="JSON budget file")
    parser.add_argument("--target-frames", type=int, help="frames to select")
    parser.add_argument("--max-candidates", type=int, help="frames scored before selection")
    parser.add_argument("--analysis-max-pixels", type=int, help="pixels per analysed frame")
    parser.add_argument("--max-sample-seconds", type=float, help="ceiling for the sampling stage")
    parser.add_argument("--decode-mode", choices=("auto", "stream", "seek"), help="decode strategy")
    parser.add_argument("--staging-dir", help="where frames will be written (default: video's directory)")
    parser.add_argument("--json", dest="json_path", help="write the full report as JSON")
    return parser.parse_args(argv)


def build_budget(args: argparse.Namespace) -> SamplingBudget:
    """Budget from defaults, then the JSON file, then the environment, then flags."""
    budget = sampling_budget.load_json(args.budget) if args.budget else sampling_budget.SamplingBudget()
    budget = sampling_budget.from_env(budget)
    overrides = {
        "target_frames": args.target_frames,
        "max_candidates": args.max_candidates,
        "analysis_max_pixels": args.analysis_max_pixels,
        "max_sample_seconds": args.max_sample_seconds,
        "decode_mode": args.decode_mode,
    }
    supplied = {name: value for name, value in overrides.items() if value is not None}
    return budget.with_overrides(**supplied) if supplied else budget


def plan_for(selected_count: int, budget: SamplingBudget) -> MatchingPlan:
    return build_plan(selected_count, budget.sequential_window, budget.retrieval_keyframes)


def estimate_for(
    metadata: VideoMetadata, frames: int, plan: MatchingPlan, budget: SamplingBudget, staging_dir: Path
) -> tuple[ResourceEstimate, ResourceVerdict]:
    """Estimate cost and compare it against this host before any work is spent."""
    estimate = estimate_selection(metadata, frames, plan, budget)
    free_disk, free_ram = measure_host(staging_dir)
    return estimate, evaluate_resources(estimate, free_disk, free_ram)


def run_gate(video: Path, budget: SamplingBudget, staging_dir: Path) -> dict:
    """Probe, estimate, scan, select and judge one capture. Returns the report dict."""
    started = time.monotonic()
    metadata = probe_video(video)
    early_plan = plan_for(budget.target_frames, budget)
    estimate, early_resources = estimate_for(metadata, budget.target_frames, early_plan, budget, staging_dir)
    if not early_resources.fits:
        return {
            "metadata": metadata.to_dict(),
            "budget": _budget_dict(budget),
            "stage": "preflight_estimate",
            "verdict": {
                "status": capture_verdict.STATUS_REJECTED,
                "findings": [
                    {
                        "code": "resource_budget_exceeded",
                        "severity": capture_verdict.SEVERITY_BLOCK,
                        "measured": "; ".join(early_resources.blockers),
                        "threshold": "estimate must fit free disk and RAM after headroom",
                        "cause": "the run would fail later, after sampling time is already spent",
                        "action": "; ".join(early_resources.actions),
                    }
                ],
                "limits": [],
                "notes": (),
            },
            "resource_estimate": estimate.to_dict(),
            "resource_verdict": early_resources.to_dict(),
            "seconds": round(time.monotonic() - started, 3),
        }
    scan = scan_capture(metadata, budget)
    selection = select_frames(
        scan.candidates,
        scan.size.width,
        budget.target_frames,
        budget.min_sharpness_ratio,
        budget.min_shift_fraction,
        scan.parallax_gap,
    )
    coverage = measure_coverage(
        scan.candidates, selection.selected, scan.size.width, metadata.duration_seconds, scan.parallax_gap
    )
    consistency = classify_consistency(scan.bursts)
    plan = plan_for(selection.count, budget)
    estimate, resources = estimate_for(metadata, selection.count, plan, budget, staging_dir)
    verdict = capture_verdict.judge_capture(
        metadata, scan, selection, coverage, consistency, resources, budget
    )
    return {
        "metadata": metadata.to_dict(),
        "budget": _budget_dict(budget),
        "stage": "scanned",
        "scan": scan.to_dict(),
        "selection": selection.to_dict(),
        "coverage": coverage.to_dict(),
        "consistency": consistency.to_dict(),
        "matching": plan.to_dict(),
        "matching_commands": list(colmap_matching_commands("<scene_dir>/database.db", plan)),
        "resource_estimate": estimate.to_dict(),
        "resource_verdict": resources.to_dict(),
        "verdict": verdict.to_dict(),
        "seconds": round(time.monotonic() - started, 3),
    }


def _budget_dict(budget: SamplingBudget) -> dict:
    from dataclasses import asdict

    return {key: value for key, value in asdict(budget).items() if key != "notes"}


def _gib(value: int) -> str:
    if value >= GIBIBYTE:
        return f"{value / GIBIBYTE:.1f} GiB"
    return f"{max(value, 0) / 1024**2:.0f} MiB"


def render_report(report: dict) -> str:
    """Render the gate report as text, in report order rather than dict order."""
    lines: list[str] = []
    lines += _render_input(report)
    lines += _render_budget(report)
    lines += _render_work(report)
    lines += _render_metrics(report)
    lines += _render_selection(report)
    lines += _render_coverage(report)
    lines += _render_matching(report)
    lines += _render_resources(report)
    lines += _render_verdict(report)
    return "\n".join(lines)


def _render_input(report: dict) -> list[str]:
    meta = report["metadata"]
    return [
        "=== INPUT ===",
        f"file:      {meta['path']}",
        f"resolution: {meta['width']}x{meta['height']} ({meta['total_pixels'] / 1e6:.2f} MP) {meta['codec']} {meta['pixel_format']}",
        f"duration:  {meta['duration_seconds']:.2f}s at {meta['fps']:.2f} fps, {meta['frame_count']} frames"
        + ("" if meta["frame_count_is_exact"] else " (count derived from rate and duration)"),
        "",
    ]


def _render_budget(report: dict) -> list[str]:
    budget = report["budget"]
    low, high = sampling_budget.hypothesis_range()
    return [
        "=== BUDGET ===",
        f"target frames {budget['target_frames']} (small-room hypothesis {low}-{high}, a starting point not a guarantee)",
        f"max candidates {budget['max_candidates']}, analysis pixels {budget['analysis_max_pixels']}, "
        f"sample ceiling {budget['max_sample_seconds']:.0f}s",
        f"min translation {budget['min_shift_fraction']:.1%} of frame width, cut limit "
        f"{budget['cut_distance_limit']:.2f} histogram distance",
        "",
    ]


def _render_work(report: dict) -> list[str]:
    lines = ["=== BOUNDED WORK ==="]
    scan = report.get("scan")
    if not scan:
        lines += ["(scan not run: the preflight estimate already refused this capture)", ""]
        return lines
    probe = scan["decode"]["probe"]
    candidates = scan["decode"]["candidates"]
    lines += [
        f"motion probe:  {probe['retained']} frames kept, {probe['visited']} visited, {probe['seconds']:.2f}s ({probe['reason']})",
        f"candidate pass: stride {scan['stride']}, {candidates['retained']} kept of {candidates['clip_frames']} "
        f"({candidates['retained_fraction']:.1%}), {candidates['visited']} frames visited, {candidates['seconds']:.2f}s",
        f"burst probe:   {scan['decode']['burst_frames_decoded']} contiguous frames for temporal consistency",
        f"total sampling: {scan['seconds']:.2f}s (ceiling {report['budget']['max_sample_seconds']:.0f}s)",
        "",
    ]
    return lines


def _render_metrics(report: dict) -> list[str]:
    scan = report.get("scan")
    if not scan:
        return []
    bursts = scan["bursts"]
    shifts = [c["translation_fraction"] for c in scan["candidates"] if c["translation_fraction"] is not None]
    sharpness = [c["sharpness"] for c in scan["candidates"]]
    cuts = sum(1 for c in scan["candidates"] if c["is_cut"])
    median_shift = sorted(shifts)[len(shifts) // 2] if shifts else 0.0
    gap = scan["parallax_gap"]
    return [
        "=== MEASURED ===",
        f"sharpness:     median {sorted(sharpness)[len(sharpness) // 2]:.0f}, "
        f"10th percentile {sorted(sharpness)[max(0, len(sharpness) // 10)] if sharpness else 0:.0f} "
        f"(variance of Laplacian at {scan['analysis_size']['width']}x{scan['analysis_size']['height']})",
        f"translation:   median {median_shift:.2%} of frame width over {gap} candidate gaps "
        f"({scan['motion_px_per_frame']:.2f} px per source frame)",
        f"scene cuts:    {cuts} detected among {len(scan['candidates'])} candidates",
        f"temporal consistency: {report['consistency']['classification']} -- {report['consistency']['evidence']}",
        f"burst residuals: median {bursts['median_residual_fraction']:.3f} of pixels, "
        f"90th percentile {bursts['p90_hot_block_fraction']:.3f} of blocks still changing",
        "",
    ]


def _render_selection(report: dict) -> list[str]:
    scan = report.get("scan")
    if not scan:
        return []
    selection = report["selection"]
    reasons = selection["excluded_by_reason"]
    reason_text = ", ".join(f"{count} {name}" for name, count in sorted(reasons.items())) or "none"
    lines = [
        "=== SELECTION ===",
        f"selected {selection['selected_count']} of {selection['eligible']} eligible "
        f"(scored {len(scan['candidates'])}) frames",
        f"excluded: {reason_text}",
    ]
    for note in report["verdict"]["notes"]:
        lines.append(f"note: {note}")
    lines.append("")
    return lines


def _render_coverage(report: dict) -> list[str]:
    coverage = report.get("coverage")
    if not coverage:
        return []
    return [
        "=== COVERAGE ===",
        f"camera travel {coverage['path_length_widths']:.2f} frame widths "
        f"(retained frames: {coverage['retained_path_length_widths']:.2f})",
        f"viewpoints: {coverage['viewpoint_bins']} distinct bins of 0.25 frame widths across "
        f"{coverage['selected_count']} frames, {coverage['distinct_directions']} directions of travel",
        f"retained span {coverage['selected_span_seconds']:.1f}s of {coverage['clip_span_seconds']:.1f}s ({coverage['span_fraction']:.0%})",
        f"the walkable volume cannot exceed this coverage; the splat is only reliable inside it",
        "",
    ]


def _render_matching(report: dict) -> list[str]:
    matching = report.get("matching")
    if not matching:
        return []
    lines = [
        "=== BOUNDED MATCHING ===",
        f"{matching['strategy']}: {matching['pairs']} pairs vs {matching['exhaustive_pairs']} exhaustive "
        f"({matching['reduction_factor']:.1f}x fewer)",
        matching["reason"],
    ]
    for note in matching["unmatched_notes"]:
        lines.append(f"limit: {note}")
    for command in report.get("matching_commands", []):
        lines.append(f"command: {command}")
    lines.append("")
    return lines


def _render_resources(report: dict) -> list[str]:
    estimate = report["resource_estimate"]
    verdict = report["resource_verdict"]
    lines = [
        "=== RESOURCE ESTIMATE (before reconstruction) ===",
        f"{estimate['frames']} frames at {estimate['source_resolution']}: "
        f"{_gib(estimate['frame_files_bytes'])} frames, {_gib(estimate['database_bytes'])} COLMAP database, "
        f"{_gib(estimate['sparse_model_bytes'])} sparse model",
        f"total {_gib(estimate['total_disk_bytes'])} with headroom; free {_gib(verdict['free_disk_bytes'])} disk, "
        f"{_gib(verdict['free_ram_bytes'])} RAM",
        f"matching {estimate['matching_pairs']} pairs ~= {estimate['matching_seconds'] / 60:.0f} min CPU; "
        f"sampling ~= {estimate['sampling_seconds']:.0f}s",
    ]
    for blocker in verdict["blockers"]:
        lines.append(f"blocker: {blocker}")
    lines.append("")
    return lines


def _render_verdict(report: dict) -> list[str]:
    verdict = report["verdict"]
    lines = [f"=== VERDICT: {verdict['status'].upper()} ==="]
    for finding in verdict["findings"]:
        lines.append(f"[{finding['severity']}] {finding['code']}")
        lines.append(f"    measured: {finding['measured']}")
        lines.append(f"    against:  {finding['threshold']}")
        lines.append(f"    why:      {finding['cause']}")
        lines.append(f"    do:       {finding['action']}")
    if verdict["limits"]:
        lines.append("--- not measured ---")
        for limit in verdict["limits"]:
            lines.append(f"limit: {limit}")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        budget = build_budget(args)
    except BudgetError as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return EXIT_USAGE
    video = Path(args.video).expanduser()
    if not video.is_file():
        sys.stderr.write(f"FAIL: file not found: {video}\n")
        return EXIT_USAGE
    staging_dir = Path(args.staging_dir).expanduser() if args.staging_dir else video.parent
    if not staging_dir.is_dir():
        sys.stderr.write(f"FAIL: staging directory not found: {staging_dir}\n")
        return EXIT_USAGE
    try:
        report = run_gate(video, budget, staging_dir)
    except VideoProbeError as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return EXIT_UNREADABLE
    except ResourceEstimationError as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return EXIT_MISSING_TOOL
    except RuntimeError as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return EXIT_MISSING_TOOL
    print(render_report(report))
    if args.json_path:
        Path(args.json_path).expanduser().write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return EXIT_REJECTED if report["verdict"]["status"] == capture_verdict.STATUS_REJECTED else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())