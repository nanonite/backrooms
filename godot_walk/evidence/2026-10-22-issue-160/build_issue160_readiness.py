"""Record #160 provenance and mechanical readiness without accepting modules."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[2]
MECHANICS = EVIDENCE / "mechanics"
ROOM_NAMES = ("column", "pocket", "assembly")
NEGATIVE_CASES = (
    "column-floor", "column-boundary", "pocket-floor", "pocket-boundary",
    "assembly-floor", "assembly-boundary",
)
NEW_FILES = (
    "godot_walk/scripts/issue160_glb.py",
    "godot_walk/scripts/build_issue160_bounded_visual.py",
    "godot_walk/scripts/issue160_room_geometry.gd",
    "godot_walk/scripts/issue160_bounded_column_room.gd",
    "godot_walk/scripts/issue160_pocket_room.gd",
    "godot_walk/scripts/issue160_assembled_walkthrough.gd",
    "godot_walk/scripts/capture_issue160.gd",
    "godot_walk/scripts/test_issue160.gd",
    "godot_walk/scripts/run_issue160_gpu.py",
    "godot_walk/scenes/issue160_bounded_column_room.tscn",
    "godot_walk/scenes/issue160_bounded_pocket_room.tscn",
    "godot_walk/scenes/issue160_column_connector.tscn",
    "godot_walk/scenes/issue160_pocket_connector.tscn",
    "godot_walk/scenes/issue160_assembled_walkthrough.tscn",
)
REFERENCE_FILES = (
    "godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/early_pocket_visual.glb",
    "godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/early_pocket_collision.glb",
    "godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/early_pocket_scene_report.json",
    "godot_walk/scenes/library_column_room.tscn",
    "godot_walk/scenes/library_pocket_room.tscn",
    "godot_walk/scripts/library_column_room.gd",
    "godot_walk/scripts/library_pocket_room.gd",
    "godot_walk/scripts/hunyuan_psx_column_box.gd",
    "godot_walk/scripts/hunyuan_psx_round3.gd",
    "godot_walk/assets/psx_extension/textures/hunyuan_round3_column_front.png",
)
SHELL_DEFINITIONS = (
    "godot_walk/scripts/issue160_room_geometry.gd",
    "godot_walk/scripts/issue160_bounded_column_room.gd",
    "godot_walk/scenes/issue160_bounded_column_room.tscn",
)
COLLISION_DEFINITIONS = (
    "godot_walk/scripts/issue160_room_geometry.gd",
    "godot_walk/scripts/issue160_bounded_column_room.gd",
    "godot_walk/scripts/issue160_pocket_room.gd",
    "godot_walk/scripts/issue160_assembled_walkthrough.gd",
    "godot_walk/scenes/issue160_bounded_column_room.tscn",
    "godot_walk/scenes/issue160_bounded_pocket_room.tscn",
    "godot_walk/scenes/issue160_column_connector.tscn",
    "godot_walk/scenes/issue160_pocket_connector.tscn",
    "godot_walk/scenes/issue160_assembled_walkthrough.tscn",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _digest(relative_path: str) -> str:
    digest = hashlib.sha256()
    with (ROOT / relative_path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _declared_protected_inputs() -> list[dict[str, str]]:
    manifest_path = "godot_walk/evidence/2026-10-20-issue-150/module_manifest.json"
    manifest = _read_json(ROOT / manifest_path)
    declared = []
    for asset in manifest["assets"].values():
        declared.append({"path": asset["path"], "expected_sha256": asset["sha256"]})
    for item in manifest["source_evidence"]:
        declared.append({"path": item["path"], "expected_sha256": item["sha256"]})
    declared.extend(
        [
            {"path": manifest["route_report_path"], "expected_sha256": manifest["route_report_sha256"]},
            {"path": manifest["capture_poses_path"], "expected_sha256": manifest["capture_poses_sha256"]},
        ]
    )
    return [
        {**item, "actual_sha256": _digest(item["path"]),
         "verified": _digest(item["path"]) == item["expected_sha256"]}
        for item in _deduplicate(declared)
    ]


def _deduplicate(items: list[dict[str, str]]) -> list[dict[str, str]]:
    unique = {}
    for item in items:
        unique[item["path"]] = item
    return list(unique.values())


def _physics_metrics(name: str) -> dict[str, Any]:
    physics = _read_json(MECHANICS / name / "physics_candidate.json")
    if physics["failures"]:
        raise ValueError(f"Final physics run failed for {name}: {physics['failures']}")
    return {
        "failures": physics["failures"],
        "out_and_back": physics["out_and_back"],
        "boundary_pushes": physics["boundary_pushes"],
        "walkable_area": physics["walkable_area"],
        "route_segments_reached": all(segment["reached"] for segment in physics["route_segments"]),
    }


def _negative_controls() -> dict[str, dict[str, Any]]:
    controls = {}
    for name in NEGATIVE_CASES:
        path = MECHANICS / f"negative-{name}" / f"physics_candidate_broken_{name.split('-')[-1]}.json"
        data = _read_json(path)
        if not data["failures"]:
            raise ValueError(f"Negative control did not fail: {name}")
        controls[name] = {"expected_failure_observed": True, "failures": data["failures"]}
    return controls


def _fps_metrics(name: str) -> dict[str, Any]:
    path = MECHANICS / name / f"fps_issue160_{name}_capped.json"
    data = _read_json(path)
    return {key: data[key] for key in ("fps", "p95_frame_ms", "p99_frame_ms", "frames", "poses", "capped_at_60")}


def _resource_runs() -> dict[str, dict[str, Any]]:
    required = ("captures-reviewed", "fps-column", "fps-pocket", "fps-assembly")
    paths = {label: EVIDENCE / "resource_runs" / f"{label}.json" for label in required}
    missing = [label for label, path in paths.items() if not path.exists()]
    if missing:
        raise ValueError(f"Missing resource records: {missing}")
    result = {label: _read_json(path) for label, path in paths.items()}
    if any(record["return_code"] != 0 or record["timed_out"] for record in result.values()):
        raise ValueError("One or more GPU evidence runs failed or timed out")
    return result


def build() -> None:
    protected = _declared_protected_inputs()
    if not all(item["verified"] for item in protected):
        raise ValueError("A #150 protected source/reference hash does not match its manifest")
    visual_derivative = _read_json(EVIDENCE / "visual_derivative.json")
    captures = _read_json(EVIDENCE / "capture_manifest.json")
    provenance = {
        "issue": 160,
        "reference_manifest": "godot_walk/evidence/2026-10-20-issue-150/module_manifest.json",
        "protected_inputs": protected,
        "additional_references": [
            {"path": path, "sha256": _digest(path)} for path in REFERENCE_FILES
        ],
        "new_implementation_files": [
            {"path": path, "sha256": _digest(path)} for path in NEW_FILES
        ],
        "bounded_visual": visual_derivative,
        "candidate_asset_hashes": {
            "visual": {
                "path": "godot_walk/evidence/2026-10-22-issue-160/bounded_hunyuan_visual.glb",
                "sha256": visual_derivative["output_sha256"],
            },
            "authored_shell_definition_sources": [
                {"path": path, "sha256": _digest(path)} for path in SHELL_DEFINITIONS
            ],
            "authored_collision_definition_sources": [
                {"path": path, "sha256": _digest(path)} for path in COLLISION_DEFINITIONS
            ],
            "capture_images": [
                {
                    "id": record["id"],
                    "path": "godot_walk/" + record["path"].removeprefix("res://"),
                    "sha256": _digest("godot_walk/" + record["path"].removeprefix("res://")),
                }
                for record in captures
            ],
            "collision_hash_semantics": (
                "Authored Godot collision shapes are procedural; hashes identify their "
                "scene/script definitions, not a separately exported collision GLB."
            ),
        },
        "preservation": "No listed source, accepted standalone scene, or reference asset is modified by this candidate.",
    }
    (EVIDENCE / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    if len(captures) != 15:
        raise ValueError(f"Expected 15 matched visual captures, found {len(captures)}")
    readiness = {
        "issue": 160,
        "status": "mechanically_tested_visual_operator_review_pending",
        "generation_ready": False,
        "catalog_admission": False,
        "operator_accepted": False,
        "registration_accepted": False,
        "scale_calibrated": False,
        "observed_openings": [],
        "authored_sockets": [
            {"id": "column_east_v1", "center_local": [3.5, -1.27099049, 3.1], "normal_local": [1, 0, 0], "clear_size": [2.0, 2.1]},
            {"id": "pocket_west_v1", "center_local": [0.0, -1.27099049, 6.9], "normal_local": [-1, 0, 0], "clear_size": [2.0, 2.1]},
        ],
        "tested_connectors": [
            {"id": "column_east__pocket_west_v1", "mechanical_status": "pass", "operator_visual_status": "pending"}
        ],
        "modules": {name: _physics_metrics(name) for name in ROOM_NAMES},
        "negative_controls": _negative_controls(),
        "fps": {name: _fps_metrics(name) for name in ROOM_NAMES},
        "capture_count": len(captures),
        "resource_runs": _resource_runs(),
        "evidence": {
            "report": "REPORT.md",
            "layout": "authored_assembly_layout.svg",
            "contact_sheet": "contact_sheet.jpg",
            "interactive_review": "index.html",
            "provenance": "provenance.json",
        },
    }
    (EVIDENCE / "room_readiness.json").write_text(json.dumps(readiness, indent=2) + "\n")


if __name__ == "__main__":
    build()
