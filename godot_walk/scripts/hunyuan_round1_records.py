"""Build provenance, mechanics, and replay-drift records for round 1."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hunyuan_round1_contract import (
    EXPECTED_HASHES,
    PROJECT,
    ROUND_ID,
    VARIANTS,
    VIEW_IDS,
)
from jsonschema import Draft202012Validator

VARIANT_FILES = {
    "preserve_hunyuan": "round-1-preserve.json",
    "source_surface_cleanup": "round-1-source-surface-cleanup.json",
}


def build_round_manifest(
    out_dir: Path, frames: dict[str, dict[str, Any]], metrics: dict[str, Any]
) -> dict[str, Any]:
    variants = _load_variant_specs()
    return {
        "schema_version": 1,
        "round_id": ROUND_ID,
        "issue": 151,
        "status": "awaiting_operator_review",
        "parent_round_id": None,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": _provenance(),
        "convention": _convention(),
        "variants": variants,
        "capture": _capture_record(frames),
        "toolchain": _load_toolchain(out_dir),
        "mechanics": build_mechanics_record(out_dir),
        "visual_metrics": {
            "path": "review_metrics.json",
            "odiff_threshold": metrics["odiff_threshold"],
            "interpretation": metrics["interpretation"],
            "noise_rule": metrics["rule"],
        },
        "review_bundle": _review_bundle(),
        "operator_feedback": {
            "path": "operator_feedback.json",
            "status": "pending_operator_review",
        },
        "execution_log": "execution_log.json",
    }


def _load_variant_specs() -> list[dict[str, Any]]:
    variant_dir = PROJECT / "design_variants" / "hunyuan"
    specs = []
    for variant in VARIANTS:
        path = variant_dir / VARIANT_FILES[variant]
        document = json.loads(path.read_text(encoding="utf-8"))
        validate_document(document, variant_dir / "variant.schema.json")
        specs.append(document)
    return specs


def _provenance() -> dict[str, Any]:
    return {
        "source_video": {
            "path": "data/scenes/corridor_travel/video.mp4",
            "sha256": EXPECTED_HASHES["data/scenes/corridor_travel/video.mp4"],
            "role": "original source footage; frames 0085-0192 inform the candidate visual context",
        },
        "seed_frame": {
            "path": "data/scenes/corridor_travel/images/frame_0152.jpg",
            "sha256": EXPECTED_HASHES[
                "data/scenes/corridor_travel/images/frame_0152.jpg"
            ],
            "role": "direct source-video seed; frame 0152 at 6.2916667 s, 1920x1080",
        },
        "hunyuan_asset": {
            "path": "godot_walk/evidence/2026-10-20-issue-147/hunyuan_layers.glb",
            "sha256": EXPECTED_HASHES[
                "godot_walk/evidence/2026-10-20-issue-147/hunyuan_layers.glb"
            ],
            "role": "two-layer Hunyuan visual-only GLB; no collision",
        },
        "generation": _generation_record(),
    }


def _generation_record() -> dict[str, Any]:
    return {
        "model": "HunyuanWorld-1.0 Panogen + SceneGen",
        "commit": "57fa9f3a79eae1079c279968cdb9d82c75fa7c86",
        "panorama": {
            "seed": 42,
            "width": 1280,
            "height": 640,
            "steps": 50,
            "guidance_scale": 30.0,
            "fov_degrees": 75.9346600492,
            "output_sha256": "135dd2a83e4865c2516d8d66a2b1670ba6dd65fbef9c7204438cc62e45f3d3d5",
        },
        "scene_generation": {
            "seed": 42,
            "scene_class": "indoor",
            "foreground_layer_1": ["columns"],
            "fp8": True,
            "offload_mode": "sequential",
        },
        "reused_output": True,
    }


def _convention() -> dict[str, Any]:
    return {
        "registration_accepted": False,
        "scale_calibrated": False,
        "bounds_m": {
            "x": [-5.4, 4.5],
            "z": [-5.0, 8.8],
            "floor_y": -1.27099049,
            "ceiling_y": 1.12900951,
        },
        "transform_source": "issue-150 uncalibrated convention; reused only as a design coordinate system",
        "visual_collision_policy": "Hunyuan visual only; collision authored and separately validated",
    }


def _capture_record(frames: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "resolution": [960, 540],
        "fov_degrees": 75.0,
        "settle_frames": 12,
        "view_ids": list(VIEW_IDS),
        "replay_note": "Three preserve_hunyuan route runs are compared for measured drift; physics determinism is not assumed.",
        "camera_pose_source": "issue-150 four end views and four column-face views, plus frame-0152 camera anchor",
        "frames": frames,
    }


def _load_toolchain(out_dir: Path) -> dict[str, Any]:
    execution = _read_json(out_dir / "execution_log.json")
    return execution["toolchain"]


def _review_bundle() -> dict[str, Any]:
    return {
        "index": "index.html",
        "contact_sheet": "candidate_contact_sheet.jpg",
        "layout": "candidate_layout.svg",
        "commands": "COMMANDS.md",
        "capture_directories": [f"captures/{variant}" for variant in VARIANTS],
    }


def build_mechanics_record(out_dir: Path) -> dict[str, Any]:
    walkability = {variant: _load_walk_report(out_dir, variant) for variant in VARIANTS}
    return {
        "walkability_report": walkability,
        "replay_drift": _route_drift(out_dir),
        "expected_negative_controls": _negative_controls(),
        "fps_report": "mechanics/source_surface_cleanup/repeat_1/fps_source_surface_cleanup_capped.json",
    }


def _load_walk_report(out_dir: Path, variant: str) -> dict[str, Any]:
    path = out_dir / "mechanics" / variant / "repeat_1" / "physics_candidate.json"
    return {"path": path.relative_to(out_dir).as_posix(), "report": _read_json(path)}


def _negative_controls() -> list[dict[str, Any]]:
    return [
        {
            "mutation": mutation,
            "path": f"mechanics/negative_controls/physics_candidate_broken_{mutation}.json",
            "failed_closed": True,
        }
        for mutation in ("boundary", "floor")
    ]


def _route_drift(out_dir: Path) -> dict[str, Any]:
    traces = [_trace(out_dir, repeat) for repeat in (1, 2, 3)]
    baseline = traces[0]
    comparisons = [
        _compare_trace(baseline, trace, repeat)
        for repeat, trace in zip((2, 3), traces[1:])
    ]
    return {
        "baseline_repeat": 1,
        "comparisons": comparisons,
        "interpretation": "Measured run-to-run drift only; no deterministic-physics claim.",
    }


def _trace(out_dir: Path, repeat: int) -> list[dict[str, Any]]:
    path = (
        out_dir
        / "mechanics"
        / "preserve_hunyuan"
        / f"repeat_{repeat}"
        / "physics_candidate.json"
    )
    return _read_json(path)["route_state_trace"]


def _compare_trace(
    baseline: list[dict[str, Any]], trace: list[dict[str, Any]], repeat: int
) -> dict[str, Any]:
    count = min(len(baseline), len(trace))
    drift = max(
        (_position_distance(baseline[i], trace[i]) for i in range(count)), default=0.0
    )
    return {
        "repeat": repeat,
        "base_ticks": len(baseline),
        "repeat_ticks": len(trace),
        "matched_ticks": count,
        "tick_counts_match": len(baseline) == len(trace),
        "max_position_drift_m": drift,
    }


def _position_distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    a, b = left["position"], right["position"]
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_pending_feedback() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "round_id": ROUND_ID,
        "status": "pending_operator_review",
        "reviewer_timestamp": None,
    }


def validate_document(document: dict[str, Any], schema_path: Path) -> None:
    schema = _read_json(schema_path)
    Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(document)


def validate_feedback_for_round(
    feedback: dict[str, Any], manifest: dict[str, Any]
) -> None:
    if feedback.get("status") != "confirmed":
        return
    if feedback.get("round_id") != manifest.get("round_id"):
        raise ValueError("Feedback round_id does not match the round manifest")
    _validate_decision_coverage(feedback, manifest)


def _validate_decision_coverage(
    feedback: dict[str, Any], manifest: dict[str, Any]
) -> None:
    expected_views = _unique_ids(
        manifest.get("capture", {}).get("view_ids", []), "manifest view"
    )
    expected_variants = _unique_ids(
        [variant.get("variant_id") for variant in manifest.get("variants", [])],
        "manifest variant",
    )
    view_ids = _unique_ids(
        [choice.get("view_id") for choice in feedback.get("view_choices", [])],
        "feedback view",
    )
    variant_ids = _unique_ids(
        [
            decision.get("variant_id")
            for decision in feedback.get("variant_decisions", [])
        ],
        "feedback variant",
    )
    if set(view_ids) != set(expected_views):
        raise ValueError("Feedback must cover every manifest view exactly once")
    if set(variant_ids) != set(expected_variants):
        raise ValueError("Feedback must decide every manifest variant exactly once")
    allowed_choices = set(expected_variants) | {"tie", "none"}
    choices = {choice.get("choice") for choice in feedback["view_choices"]}
    if not choices <= allowed_choices:
        raise ValueError("View choices must name a manifest variant, tie, or none")


def _unique_ids(values: list[Any], label: str) -> list[str]:
    if not values or any(not isinstance(value, str) or not value for value in values):
        raise ValueError(f"{label} IDs must be non-empty strings")
    if len(values) != len(set(values)):
        raise ValueError(f"{label} IDs must be unique")
    return list(values)
