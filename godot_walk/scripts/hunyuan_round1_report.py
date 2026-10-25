"""Write a concise evidence summary for the round 1 review bundle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_report(
    out_dir: Path, manifest: dict[str, Any], metrics: dict[str, Any]
) -> None:
    mechanics = manifest["mechanics"]
    fps = _read_json(out_dir / mechanics["fps_report"])
    lines = _report_lines(manifest, metrics, fps)
    (out_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _report_lines(
    manifest: dict[str, Any], metrics: dict[str, Any], fps: dict[str, Any]
) -> list[str]:
    mechanics = manifest["mechanics"]
    maximum_noise = max(
        item["max_diff_pct"] for item in metrics["control_repeat_noise"]
    )
    return [
        "# Chainlink #151: Hunyuan-to-PSX Round 1",
        "",
        "Status: **awaiting operator review**. No candidate is auto-selected.",
        "",
        "## Review",
        "",
        "Open `index.html` for nine matched views of two treatments. Choose a candidate per view, record both variant decisions, and download `operator_feedback.json`. Rejecting both candidates is valid.",
        "",
        "## Scope And Provenance",
        "",
        "The visual input is the existing issue-147 Hunyuan GLB, generated from a direct frame-0152 source-video seed. No inference, retraining, or video generation ran. Frames 0085-0192 do not establish room count or unseen layout.",
        "",
        "Issue-150 bounds are an **uncalibrated design convention** only. `registration_accepted=false` and `scale_calibrated=false`. Hunyuan remains visual-only; collision is authored and separately validated.",
        "",
        "## Mechanical Evidence",
        "",
        f"Toolchain: Godot {manifest['toolchain']['godot']}, Python {manifest['toolchain']['python']}, {manifest['toolchain']['odiff']}.",
        *_walkability_lines(mechanics),
        f"- Capped `{fps['scene']}` sample: {fps['fps']:.2f} FPS, p95 {fps['p95_frame_ms']:.2f} ms, p99 {fps['p99_frame_ms']:.2f} ms over {fps['frames']} intervals.",
        "- Boundary and floor mutations are expected negative controls under `mechanics/negative_controls/`.",
        "- Route replay drift is measured and reported, not assumed deterministic.",
        "",
        "## Visual Diagnostics",
        "",
        f"ODiff threshold 0.1; maximum preserve-control repeat difference is {maximum_noise:.4f}% of pixels. Per-view deltas at or below the matched repeat-noise ceiling are inconclusive. Pixel change is not a quality score.",
        "",
        "The contact sheet and diff images provide evidence; they do not rank aesthetics.",
        "",
        "## Files",
        "",
        "- `candidate_contact_sheet.jpg` — paired captures.",
        "- `review_metrics.json` — matched ODiff deltas and repeat noise.",
        "- `round_manifest.json` — provenance and execution record.",
        "- `operator_feedback.json` — pending until the browser form is submitted.",
        "- `COMMANDS.md` — reproduction and walkthrough commands.",
    ]


def _walkability_lines(mechanics: dict[str, Any]) -> list[str]:
    lines = []
    for variant, details in mechanics["walkability_report"].items():
        report = details["report"]
        contacts = report.get("out_and_back", {}).get("safety_contacts", "not reported")
        lines.append(
            f"- `{variant}`: {len(report.get('failures', []))} verifier failures; {contacts} SafetyNet contacts."
        )
    return lines


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
