"""Read-only integrity checks for the issue-271 bench material fallback fixture.

Verifies that the authored fallback is recorded with explicit parameters, that no
robe crop is assigned to the bench in the candidate, that the statue plinth and
all geometry/collision declarations are unchanged relative to the reference, that
both comparison scenes share one non-branch-dependent geometry script, that the
required close/wider views exist, and that accepted, frozen and pinned files were
not edited. It renders nothing, makes no model calls, edits nothing and admits
nothing to the catalog.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = SCRIPT_DIR.parent
FIXTURE_DIR = EVIDENCE_DIR / "fixture"
ROOT = EVIDENCE_DIR.parents[2]

ACCEPTED_RECORD = "godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json"
CROP_MANIFEST = "godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/textures/crop_manifest.json"
FREEZE_RECORD = "godot_walk/room_catalog/contract_freeze_v4.json"
FALSE_FLAGS = ("registration_accepted", "scale_calibrated", "operator_approved")
REQUIRED_VIEWS = ("bench_close", "wider_scene", "bench_oblique", "plinth_check")
BENCH_ORIGIN = (0.0, 0.8, 0.0)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def repo_file(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Path escapes repository: {relative}")
    return path


def _numbers(value: Any, count: int) -> list[float] | None:
    if not isinstance(value, list) or len(value) != count:
        return None
    if not all(isinstance(item, (int, float)) for item in value):
        return None
    return [float(item) for item in value]


def collect_errors(fixture_dir: Path = FIXTURE_DIR, root: Path = ROOT) -> list[str]:
    """Return all integrity errors; an empty list means the fixture is consistent."""
    errors: list[str] = []
    try:
        decision = load(fixture_dir / "bench_material_decision_v1.json")
        geometry = load(fixture_dir / "bench_geometry_v1.json")
        views = load(fixture_dir / "views_v1.json")
        supplement = load(fixture_dir / "pinned_supplement_v1.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"Cannot read fixture record: {error}"]

    errors.extend(_check_decision(decision, root))
    errors.extend(_check_geometry(geometry, decision))
    errors.extend(_check_scene_pair(fixture_dir, root, decision))
    errors.extend(_check_views(views))
    errors.extend(_check_notes(fixture_dir))
    errors.extend(_check_pinned(supplement, root))
    return errors


def _check_decision(decision: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    authored = decision.get("authored_material", {})
    if authored.get("origin") != "project_authored":
        errors.append("Authored material origin must be project_authored")
    if authored.get("intended_role") != "stone_like_bench_surface":
        errors.append("Authored material needs an explicit intended role")
    if authored.get("source_pixels_observed_for_this_surface") is not False:
        errors.append(
            "Record must state no source pixels were observed for this surface"
        )
    if authored.get("no_claim_authored_pixels_observed_in_source") is not True:
        errors.append(
            "Record must explicitly disclaim observed authored pixels in source"
        )
    if authored.get("source_faithfulness_claimed") is not False:
        errors.append("Record must not claim source faithfulness for the fallback")

    params = authored.get("parameters", {})
    color = _numbers(params.get("albedo_color_rgba"), 4)
    if color is None or not all(0.0 <= item <= 1.0 for item in color):
        errors.append("Authored material needs an explicit albedo_color_rgba")
    if params.get("albedo_texture") is not None:
        errors.append("Authored fallback must not use an albedo texture")
    if params.get("shading_mode") != "unshaded":
        errors.append("Authored fallback shading mode must be recorded")
    if not isinstance(params.get("roughness"), (int, float)):
        errors.append("Authored fallback roughness must be recorded")

    crop = decision.get("source_crop_evidence", {})
    if crop.get("assigned_to_bench_in_candidate") is not False:
        errors.append(
            "The robe crop must not be assigned to the bench in the candidate"
        )
    if crop.get("assigned_to_statue_plinth_in_both_views") is not True:
        errors.append("The robe crop must remain on the unchanged statue plinth")
    if crop.get("source_pixel_bounds_xyxy") != [200, 280, 380, 470]:
        errors.append("Robe crop bounds must match the accepted crop plan")
    try:
        manifest = load(repo_file(CROP_MANIFEST))
    except (ValueError, OSError, json.JSONDecodeError) as error:
        errors.append(f"Cannot read crop manifest: {error}")
    else:
        recorded = next(
            (
                item
                for item in manifest.get("crops", [])
                if item.get("name") == "stone_robe"
            ),
            None,
        )
        if recorded is None or recorded.get("sha256") != crop.get("crop_sha256"):
            errors.append("Robe crop hash does not match the accepted crop manifest")

    try:
        accepted_text = repo_file(ACCEPTED_RECORD).read_text(encoding="utf-8")
    except (ValueError, OSError, UnicodeDecodeError) as error:
        errors.append(f"Cannot read accepted record: {error}")
    else:
        if "stone_bench_surface" not in accepted_text:
            errors.append(
                "Accepted record no longer labels the robe crop stone_bench_surface"
            )

    assignments = decision.get("bench_assignments", [])
    if len(assignments) != 16:
        errors.append(f"Expected 16 bench assignments, found {len(assignments)}")
    stone_count = 0
    for item in assignments:
        part = item.get("part", "<unnamed>")
        candidate_key = item.get("candidate_material_key")
        if candidate_key == "bench_stone":
            stone_count += 1
            if item.get("reference_material_key") != "stone":
                errors.append(f"{part} must reference the shared stone material")
            if item.get("reference_material_origin") != "source_crop:stone_robe":
                errors.append(f"{part} reference origin must be the robe crop")
            if item.get("candidate_material_origin") != "project_authored":
                errors.append(f"{part} candidate origin must be project_authored")
            if item.get("changed_relative_to_reference") is not True:
                errors.append(f"{part} must be marked as changed")
        elif candidate_key == "post":
            if item.get("reference_material_key") != "post":
                errors.append(f"{part} must keep the local post material")
            if item.get("candidate_material_origin") != "project_authored_solid":
                errors.append(f"{part} candidate origin must remain an authored solid")
            if item.get("changed_relative_to_reference") is not False:
                errors.append(f"{part} must be marked unchanged")
        else:
            errors.append(
                f"{part} has an unknown candidate material key: {candidate_key}"
            )
    if stone_count != 12:
        errors.append(
            f"Expected 12 stone bench parts moved to the fallback, found {stone_count}"
        )
    if decision.get("robe_crop_bench_assignments_in_candidate") != 0:
        errors.append("Candidate must have zero robe-crop bench assignments")

    plinth = decision.get("statue_plinth", {})
    if plinth.get("unchanged_relative_to_reference") is not True:
        errors.append("Statue plinth must be declared unchanged")
    if plinth.get("material_key_in_both_views") != "stone":
        errors.append("Statue plinth must keep the shared stone material")
    if plinth.get("material_origin_in_both_views") != "source_crop:stone_robe":
        errors.append("Statue plinth must keep the robe crop in both views")

    geometry_state = decision.get("geometry_and_collision", {})
    if geometry_state.get("unchanged_relative_to_reference") is not True:
        errors.append("Geometry and collision must be declared unchanged")
    preserved = decision.get("preserved", {})
    if preserved.get("accepted_room_and_frozen_files_unchanged") is not True:
        errors.append("Record must state accepted and frozen files are unchanged")
    if preserved.get("catalog_admission") is not False:
        errors.append("Record must not imply catalog admission")
    if preserved.get("ledger_events_written") is not False:
        errors.append("Record must not claim ledger events were written")
    errors.extend(_check_flags(decision, "decision"))
    if decision.get("status") != "candidate_pending_review":
        errors.append("Decision status must be candidate_pending_review")
    if decision.get("preview_only") is not True:
        errors.append("Decision must be marked as a preview only")
    return errors


def _check_geometry(geometry: dict[str, Any], decision: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if geometry.get("unchanged_relative_to_reference") is not True:
        errors.append("Geometry record must declare unchanged_relative_to_reference")
    if geometry.get("geometry_not_branch_dependent") is not True:
        errors.append("Geometry must not depend on the bench material mode")
    if geometry.get("collision_not_branch_dependent") is not True:
        errors.append("Collision must not depend on the bench material mode")
    parts = geometry.get("bench_parts", [])
    expected_names = [
        item.get("part") for item in decision.get("bench_assignments", [])
    ]
    if [item.get("part") for item in parts] != expected_names:
        errors.append("Geometry bench parts do not match the decision assignments")
    for item in parts:
        part = item.get("part", "<unnamed>")
        if _numbers(item.get("center"), 3) is None:
            errors.append(f"{part} has an invalid center")
        if item.get("kind") == "box" and _numbers(item.get("size"), 3) is None:
            errors.append(f"{part} box has an invalid size")
        if item.get("kind") == "cylinder" and (
            not isinstance(item.get("radius"), (int, float))
            or not isinstance(item.get("height"), (int, float))
        ):
            errors.append(f"{part} cylinder has invalid radius/height")
    colliders = {item.get("name"): item for item in geometry.get("colliders", [])}
    for name in (
        "WalkableFloor",
        "StoneBenchCollision",
        "StatueCollision",
        "SafetyNet",
    ):
        entry = colliders.get(name)
        if (
            entry is None
            or not isinstance(entry.get("parent"), str)
            or _numbers(entry.get("center"), 3) is None
            or _numbers(entry.get("size"), 3) is None
        ):
            errors.append(f"Collider {name} is missing or malformed")
    bench_collision = colliders.get("StoneBenchCollision", {})
    if bench_collision.get("center") != [0.0, 0.8, -0.1]:
        errors.append("Bench collision center differs from the accepted reference")
    if bench_collision.get("size") != [3.6, 1.6, 1.9]:
        errors.append("Bench collision size differs from the accepted reference")
    plinth = geometry.get("statue_plinth", {})
    if plinth.get("center") != [-4.6, 0.28, 0.8] or plinth.get("size") != [
        1.2,
        0.56,
        1.1,
    ]:
        errors.append("Statue plinth geometry differs from the accepted reference")
    if geometry.get("tree_collider_count") != 18:
        errors.append("Reference tree collider count must remain 18")
    return errors


def _function_body(script: str, name: str) -> str:
    match = re.search(rf"^func {re.escape(name)}\(.*?\).*:\n", script, re.MULTILINE)
    if match is None:
        return ""
    tail = script[match.end() :]
    next_function = re.search(r"^func ", tail, re.MULTILINE)
    return tail[: next_function.start()] if next_function else tail


def _check_scene_pair(
    fixture_dir: Path, root: Path, decision: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    reference_path = fixture_dir / "bench_reference_v1.tscn"
    candidate_path = fixture_dir / "bench_candidate_v1.tscn"
    script_path = fixture_dir / "bench_fixture_v1.gd"
    for path in (reference_path, candidate_path, script_path):
        if not path.is_file():
            errors.append(f"Missing fixture file: {path.name}")
    if errors:
        return errors

    reference = reference_path.read_text(encoding="utf-8")
    candidate = candidate_path.read_text(encoding="utf-8")
    script = script_path.read_text(encoding="utf-8")

    def normalize(text: str) -> str:
        return "\n".join(
            line
            for line in text.splitlines()
            if not line.startswith("bench_material_mode")
            and not line.startswith("[node name=")
        )

    if normalize(reference) != normalize(candidate):
        errors.append(
            "Comparison scenes differ beyond the bench material mode property"
        )
    if 'bench_material_mode = "reference"' not in reference:
        errors.append("Reference scene must set bench_material_mode=reference")
    if 'bench_material_mode = "candidate"' not in candidate:
        errors.append("Candidate scene must set bench_material_mode=candidate")
    if script_path.name not in reference or script_path.name not in candidate:
        errors.append("Both scenes must instantiate the one shared fixture script")

    if script.count("func _bench_surface_material(") != 1:
        errors.append("Exactly one bench surface material selector is required")
    bench_body = _function_body(script, "_build_stone_bench")
    statue_body = _function_body(script, "_build_stone_statue")
    collision_body = _function_body(script, "_add_collision_box")
    if "_bench_surface_material()" not in bench_body:
        errors.append("Bench construction must use the selectable surface material")
    if "bench_material_mode" in bench_body:
        errors.append("Bench geometry must not branch on the material mode")
    if "materials.stone" not in statue_body or "_bench_surface_material" in statue_body:
        errors.append("Statue plinth must keep the reference stone material")
    if "bench_material_mode" in statue_body or "bench_material_mode" in collision_body:
        errors.append("Statue and collision construction must not branch on the mode")

    expected_color = decision["authored_material"]["parameters"]["albedo_color_rgba"]
    match = re.search(r"const AUTHORED_BENCH_COLOR := Color\(([^)]*)\)", script)
    if match is None:
        errors.append("Shared script must declare AUTHORED_BENCH_COLOR")
    else:
        actual = [float(value.strip()) for value in match.group(1).split(",")]
        if actual != [float(value) for value in expected_color]:
            errors.append(
                "Script authored color does not match the recorded parameters"
            )
    return errors


def _check_views(views: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    entries = views.get("views", [])
    by_id = {view.get("id"): view for view in entries}
    for required in REQUIRED_VIEWS:
        if required not in by_id:
            errors.append(f"Required comparison view is missing: {required}")
    for view in entries:
        for key in ("position", "target"):
            if _numbers(view.get(key), 3) is None:
                errors.append(f"View {view.get('id')} has an invalid {key}")
    positions: list[tuple[float, ...]] = []
    for view in entries:
        vector = _numbers(view.get("position"), 3)
        if vector is not None:
            positions.append(tuple(vector))
    if len(set(positions)) != len(positions):
        errors.append("Comparison view positions must be distinct")
    if all(name in by_id for name in ("bench_close", "wider_scene")):
        close = _numbers(by_id["bench_close"].get("position"), 3)
        wide = _numbers(by_id["wider_scene"].get("position"), 3)
        if (
            close is not None
            and wide is not None
            and math.dist(close, BENCH_ORIGIN) >= math.dist(wide, BENCH_ORIGIN)
        ):
            errors.append("bench_close must be nearer the bench than wider_scene")
    plinth = _numbers(by_id.get("plinth_check", {}).get("target"), 3)
    if plinth is None or abs(plinth[0] + 4.6) > 0.01 or abs(plinth[2] - 0.8) > 0.01:
        errors.append("plinth_check must look at the unchanged statue plinth")
    errors.extend(_check_flags(views, "views"))
    return errors


def _check_flags(record: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    for flag in FALSE_FLAGS:
        if record.get("flags", {}).get(flag) is not False:
            errors.append(f"{label}.{flag} must be false")
    return errors


def _check_notes(fixture_dir: Path) -> list[str]:
    errors: list[str] = []
    authored = fixture_dir / "authored_data_v1.md"
    limits = fixture_dir / "limitations_v1.md"
    if not authored.is_file():
        errors.append("Authored data record is missing")
    else:
        text = authored.read_text(encoding="utf-8").lower()
        for keyword in (
            "authored",
            "uncalibrated",
            "project_authored",
            "robe",
            "plinth",
            "geometry",
            "collision",
            "context",
        ):
            if keyword not in text:
                errors.append(f"Authored data record does not state {keyword}")
    if not limits.is_file():
        errors.append("Limitations record is missing")
    else:
        text = limits.read_text(encoding="utf-8").lower()
        for keyword in (
            "visual-only",
            "candidate",
            "operator",
            "uncalibrated",
            "collision",
            "plinth",
        ):
            if keyword not in text:
                errors.append(f"Limitations record does not state {keyword}")
    return errors


def _check_pinned(supplement: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    records = (
        (
            ACCEPTED_RECORD,
            [
                item
                for item in load(repo_file(ACCEPTED_RECORD))["resolved_adaptation"][
                    "dependencies"
                ]
            ],
        ),
        (FREEZE_RECORD, list(load(repo_file(FREEZE_RECORD))["files"].values())),
    )
    for label, entries in records:
        for entry in entries:
            relative = entry["path"]
            try:
                path = repo_file(relative)
            except ValueError as error:
                errors.append(f"{label}: {error}")
                continue
            if not path.is_file():
                errors.append(f"{label}: pinned file does not resolve: {relative}")
            elif sha256_file(path) != entry["sha256"]:
                errors.append(f"{label}: pinned file was edited: {relative}")
    for relative, expected in supplement.get("files", {}).items():
        try:
            path = repo_file(relative)
        except ValueError as error:
            errors.append(f"pinned supplement: {error}")
            continue
        if not path.is_file():
            errors.append(f"pinned supplement: file does not resolve: {relative}")
        elif sha256_file(path) != expected:
            errors.append(f"pinned supplement: file was edited: {relative}")
    return errors


def main() -> int:
    errors = collect_errors()
    if errors:
        print("FAIL issue-271 bench fixture")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "PASS issue-271 bench fixture: authored fallback parameters, zero robe-crop "
        "bench assignments, unchanged plinth/geometry/collision, shared non-branching "
        "script, close/wider views, false flags and pinned assets verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
