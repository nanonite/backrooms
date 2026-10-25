"""Build the Round 2 Hunyuan-to-PSX review bundle from guarded captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hunyuan_round1_contract import EXPECTED_HASHES, PROJECT, SCHEMA_DIR
from hunyuan_round1_operator_form import write_review_page
from hunyuan_round1_records import _route_drift, validate_document
from hunyuan_round1_visual_evidence import (
    build_metrics,
    draw_variant_contact_sheet,
    validate_captures,
)
from hunyuan_round2_contract import (
    OUT,
    ROUND_ID,
    ROUND_ONE,
    TEXTURE,
    VARIANTS,
    VIEW_IDS,
)

BASELINE = VARIANTS[0]
CANDIDATE = VARIANTS[1]
TEXTURE_SHA256 = "7bb880ae7b4ce91ac5720f8ad136b7403da2c4983e0e71cb6e05239dfcfc5a01"


def main() -> int:
    out_dir = _arguments()
    _validate_sources()
    repeats = {BASELINE: (1, 2, 3), CANDIDATE: (1,)}
    frames = validate_captures(out_dir, VARIANTS, VIEW_IDS, repeats)
    metrics = build_metrics(
        out_dir,
        round_id=ROUND_ID,
        variants=VARIANTS,
        view_ids=VIEW_IDS,
        baseline_variant=BASELINE,
        candidate_variant=CANDIDATE,
        scope="Column-only authored box and direct source-face texture; floor, ceiling, walls, room bounds, and collision are held constant.",
    )
    draw_variant_contact_sheet(out_dir, VARIANTS, VIEW_IDS)
    manifest = _build_manifest(out_dir, frames, metrics)
    _write_bundle_records(out_dir, manifest, metrics)
    print(f"REVIEW_BUNDLE_READY: {out_dir / 'index.html'}")
    return 0


def _arguments() -> Path:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT)
    out_dir = parser.parse_args().out_dir.resolve()
    if not out_dir.is_dir():
        parser.error(f"Round output directory does not exist: {out_dir}")
    return out_dir


def _validate_sources() -> None:
    root = Path(__file__).resolve().parents[2]
    for relative, expected in EXPECTED_HASHES.items():
        if _sha256(root / relative) != expected:
            raise ValueError(f"Protected source hash mismatch: {relative}")
    if _sha256(TEXTURE) != TEXTURE_SHA256:
        raise ValueError(f"Round 2 source-face texture hash mismatch: {TEXTURE}")


def _build_manifest(
    out_dir: Path,
    frames: dict[str, dict[str, Any]],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    manifest = _read_json(ROUND_ONE / "round_manifest.json")
    specs = [_read_variant(variant) for variant in VARIANTS]
    execution = _read_json(out_dir / "execution_log.json")
    mechanics = _mechanics_record(out_dir)
    manifest.update(
        {
            "round_id": ROUND_ID,
            "issue": 151,
            "status": "awaiting_operator_review",
            "parent_round_id": "hunyuan-psx-r1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "variants": specs,
            "capture": _capture_record(frames),
            "toolchain": execution["toolchain"],
            "mechanics": mechanics,
            "visual_metrics": {
                "path": "review_metrics.json",
                "odiff_threshold": metrics["odiff_threshold"],
                "interpretation": metrics["interpretation"],
                "noise_rule": metrics["rule"],
            },
            "review_bundle": {
                "index": "index.html",
                "contact_sheet": "candidate_contact_sheet.jpg",
                "layout": "candidate_layout.svg",
                "commands": "COMMANDS.md",
                "capture_directories": [f"captures/{variant}" for variant in VARIANTS],
            },
            "operator_feedback": {
                "path": "operator_feedback.json",
                "status": "pending_operator_review",
            },
            "execution_log": "execution_log.json",
        }
    )
    manifest["provenance"]["source_video"]["role"] += (
        "; Round 2 texture crop references the column face in frame 0152"
    )
    manifest["convention"]["registration_accepted"] = False
    manifest["convention"]["scale_calibrated"] = False
    validate_document(manifest, SCHEMA_DIR / "hunyuan_round.schema.json")
    return manifest


def _capture_record(frames: dict[str, dict[str, Any]]) -> dict[str, Any]:
    capture = _read_json(ROUND_ONE / "round_manifest.json")["capture"]
    capture["frames"] = frames
    capture["view_ids"] = list(VIEW_IDS)
    capture["replay_note"] = (
        "Three baseline route runs measure run-to-run drift; physics determinism is not assumed."
    )
    return capture


def _mechanics_record(out_dir: Path) -> dict[str, Any]:
    walkability = {}
    for variant in VARIANTS:
        path = out_dir / "mechanics" / variant / "repeat_1" / "physics_candidate.json"
        walkability[variant] = {
            "path": path.relative_to(out_dir).as_posix(),
            "report": _read_json(path),
        }
    return {
        "walkability_report": walkability,
        "replay_drift": _route_drift(out_dir),
        "expected_negative_controls": [
            {
                "mutation": mutation,
                "path": f"mechanics/negative_controls/physics_candidate_broken_{mutation}.json",
                "failed_closed": True,
            }
            for mutation in ("boundary", "floor")
        ],
        "fps_report": f"mechanics/{CANDIDATE}/repeat_1/fps_{CANDIDATE}_capped.json",
    }


def _read_variant(variant: str) -> dict[str, Any]:
    path = PROJECT / "design_variants" / "hunyuan" / "round-2" / f"{variant}.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    document = _read_json(path)
    validate_document(document, path.parent.parent / "variant.schema.json")
    return document


def _write_bundle_records(
    out_dir: Path, manifest: dict[str, Any], metrics: dict[str, Any]
) -> None:
    pending_feedback = {
        "schema_version": 1,
        "round_id": ROUND_ID,
        "status": "pending_operator_review",
        "reviewer_timestamp": None,
    }
    feedback_schema = SCHEMA_DIR / "operator_feedback.schema.json"
    validate_document(pending_feedback, feedback_schema)
    _write_json(out_dir / "round_manifest.json", manifest)
    _write_json(out_dir / "operator_feedback.json", pending_feedback)
    write_review_page(out_dir, metrics, ROUND_ID, VARIANTS, VIEW_IDS)
    _write_layout(out_dir / "candidate_layout.svg")
    _write_commands(out_dir / "COMMANDS.md")
    _write_report(out_dir, manifest, metrics)


def _write_layout(path: Path) -> None:
    path.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="430" viewBox="0 0 900 430">
<rect width="900" height="430" fill="#f4f4ee"/>
<text x="32" y="40" font-family="sans-serif" font-size="22" font-weight="700" fill="#202724">#151 Round 2 | Column-only proposal</text>
<text x="32" y="68" font-family="sans-serif" font-size="14" fill="#843f34">Uncalibrated authored bounds. The diagram is not a recovered floor plan.</text>
<rect x="110" y="105" width="305" height="255" fill="#dedbcf" stroke="#313b35" stroke-width="3"/>
<rect x="232" y="203" width="57" height="44" fill="#bac1b5" stroke="#426d62" stroke-width="3"/>
<rect x="228" y="199" width="65" height="52" fill="none" stroke="#ad503c" stroke-width="2" stroke-dasharray="6 4"/>
<path d="M142 328 L142 120 L360 120" fill="none" stroke="#356f67" stroke-width="3" stroke-dasharray="8 6"/>
<text x="110" y="386" font-family="sans-serif" font-size="13" fill="#29332e">Existing room bounds and test route; dimensions remain uncalibrated.</text>
<text x="455" y="128" font-family="sans-serif" font-size="16" font-weight="700" fill="#29332e">Round 2 changes</text>
<text x="455" y="160" font-family="sans-serif" font-size="14" fill="#29332e">Control: current Hunyuan column.</text>
<text x="455" y="184" font-family="sans-serif" font-size="14" fill="#29332e">Candidate: authored box at the same obstacle bounds,</text>
<text x="455" y="206" font-family="sans-serif" font-size="14" fill="#29332e">with a direct crop from the visible frame-0152 face.</text>
<text x="455" y="248" font-family="sans-serif" font-size="14" fill="#29332e">Floor, ceiling, walls, route, and collision stay fixed.</text>
<text x="455" y="272" font-family="sans-serif" font-size="14" fill="#29332e">No registration or scale claim; no unseen space added.</text>
<rect x="456" y="315" width="22" height="18" fill="#bac1b5" stroke="#426d62" stroke-width="2"/><text x="488" y="329" font-family="sans-serif" font-size="13" fill="#29332e">shared column obstacle bounds</text>
<rect x="456" y="346" width="22" height="18" fill="none" stroke="#ad503c" stroke-width="2" stroke-dasharray="5 3"/><text x="488" y="360" font-family="sans-serif" font-size="13" fill="#29332e">authored visual cover in candidate only</text>
</svg>
""",
        encoding="utf-8",
    )


def _write_commands(path: Path) -> None:
    path.write_text(
        """# Chainlink #151 Round 2

## Run

From the workspace root:

```bash
python3 godot_walk/scripts/run_hunyuan_psx_round2.py
```

The runner uses the GPU headroom guard before every capture and FPS run, applies a 300-second timeout, measures resource peaks, and refuses to overwrite an existing evidence folder.

## Review

The review server serves the bundle locally and accepts validated feedback directly into this folder:

```bash
python3 godot_walk/scripts/hunyuan_review_server.py --bundle-dir godot_walk/evidence/2026-10-21-issue-151-round-2
```

Open `http://127.0.0.1:8765/` and use **Submit feedback to workspace**. No variant is auto-selected.

## Walkthrough

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/hunyuan_psx_round2.tscn -- --variant=preserve_hunyuan
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/hunyuan_psx_round2.tscn -- --variant=column_box_source_face
```

""",
        encoding="utf-8",
    )


def _write_report(
    out_dir: Path, manifest: dict[str, Any], metrics: dict[str, Any]
) -> None:
    fps = _read_json(out_dir / manifest["mechanics"]["fps_report"])
    max_noise = max(item["max_diff_pct"] for item in metrics["control_repeat_noise"])
    changes = "\n".join(
        f"- `{view['view_id']}`: {view['diff_pct']:.3f}% changed pixels; "
        f"repeat-noise ceiling {view['control_repeat_noise_ceiling_pct']:.3f}%"
        for view in metrics["variant_pixel_deltas"]
    )
    lines = [
        "# Chainlink #151: Hunyuan-to-PSX Round 2",
        "",
        "Status: **awaiting operator review**. No candidate is auto-selected.",
        "",
        "## Hypothesis",
        "",
        "A full axis-aligned column box with a directly sampled frame-0152 face texture may read more clearly than the incomplete Hunyuan column while preserving the user's accepted floor and ceiling.",
        "",
        "Only the column visual treatment changes. The floor, ceiling, walls, camera poses, route, room bounds, and collision are held constant. The candidate box is visual-only; the existing column obstacle remains the sole column collider.",
        "",
        "## Provenance",
        "",
        "The 320 x 400 column texture is a direct crop from `data/scenes/corridor_travel/images/frame_0152.jpg`, pixels x=780..1099 and y=300..699. It is not recolored or generated. `registration_accepted=false` and `scale_calibrated=false` remain unchanged.",
        "",
        "## Mechanical Evidence",
        "",
        f"- Candidate capped FPS: {fps['fps']:.2f}; p95 {fps['p95_frame_ms']:.2f} ms; p99 {fps['p99_frame_ms']:.2f} ms.",
        "- Both variants use the same authored room collision and bounded walk route.",
        "- Boundary and floor negative controls are expected to fail closed.",
        "- Replay drift is reported as measured, not treated as deterministic.",
        "",
        "## Visual Diagnostics",
        "",
        f"ODiff threshold 0.1. Maximum baseline repeat difference: {max_noise:.4f}%. A change at or below the per-view repeat-noise ceiling is inconclusive; pixel change is not a quality score.",
        "",
        changes,
        "",
        "## Operator Review",
        "",
        "Use `index.html` for the nine matched views. The form submits directly to this bundle when served with `hunyuan_review_server.py`; it does not rank or promote a candidate.",
        "",
        "## Files",
        "",
        "- `candidate_contact_sheet.jpg` — matched control/candidate captures.",
        "- `review_metrics.json` — ODiff values and measured repeat noise.",
        "- `round_manifest.json` — provenance, variant specs, mechanics, and run record.",
        "- `operator_feedback.json` — pending until operator submission.",
        "- `candidate_layout.svg` — authored, uncalibrated column-only diagram.",
    ]
    (out_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
