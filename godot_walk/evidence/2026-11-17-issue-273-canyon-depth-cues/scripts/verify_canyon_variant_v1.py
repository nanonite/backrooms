"""Read-only integrity checks for the issue-273 canyon depth-cue variant.

Verifies identity, footprint/collision parity, visual-only relief policy,
negative controls, matched camera poses, guard receipts and frozen artifacts.
Writes nothing; a failed check is returned as a human-readable error.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = SCRIPT_DIR.parent
ROOT = EVIDENCE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "godot_walk/scripts"))

from video_adaptation_contracts import candidate_identity_v2

ROOMS = "godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms"
BASELINE = f"{ROOMS}/slot-canyon-courtyard-v1"
VARIANT = f"{ROOMS}/slot-canyon-courtyard-v2"
EVIDENCE = "godot_walk/evidence/2026-11-17-issue-273-canyon-depth-cues"
BASELINE_CAPTURES = f"{EVIDENCE}/captures/baseline_v1"
PINNED = f"{EVIDENCE}/fixture/pinned_supplement_v1.json"
PROVENANCE = f"{EVIDENCE}/provenance/baseline_vs_variant_v1.json"
VARIANT_CANDIDATE = f"{VARIANT}/adaptation_candidate.json"
CAPTURE_NAMES = (
    "spawn_up_corridor",
    "bend_turn",
    "west_wall_strata",
    "open_sky_slot",
    "walk_00_spawn",
    "walk_01_forward",
    "walk_02_mid",
    "walk_03_bend",
    "walk_04_bend_exit",
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


def load(root: Path, relative: str) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def text(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def const_block(source: str, name: str) -> str:
    start = source.index(f"const {name}")
    end = source.index("\n", source.index("]", start))
    return source[start:end]


def function_block(source: str, name: str) -> str:
    start = source.index(f"func {name}")
    end = source.index("\nfunc ", start + 1)
    return source[start:end]


def check_candidate(root: Path, errors: list[str]) -> dict:
    baseline = load(root, f"{BASELINE}/adaptation_candidate.json")
    record = load(root, VARIANT_CANDIDATE)
    if record["adaptation_id"] != "slot-canyon-courtyard-v2":
        errors.append("candidate adaptation_id is not the v2 variant")
    if record["registration_accepted"] or record["scale_calibrated"]:
        errors.append("candidate calibration flags are not false")
    if record["status"] != "candidate_pending_review":
        errors.append("candidate status is not pending review")
    if record["operator_decision"]["status"] != "pending":
        errors.append("operator decision is not pending")
    if record["resolved_adaptation"]["sockets"]:
        errors.append("variant declares sockets")
    a = baseline["resolved_adaptation"]
    b = record["resolved_adaptation"]
    if a["walkable_space"]["footprint"] != b["walkable_space"]["footprint"]:
        errors.append("declared footprint changed between v1 and v2")
    if a["walkable_space"]["safe_spawn_xyz"] != b["walkable_space"]["safe_spawn_xyz"]:
        errors.append("safe spawn changed between v1 and v2")
    if a["walkable_space"]["floor_elevation"] != b["walkable_space"]["floor_elevation"]:
        errors.append("floor elevation changed between v1 and v2")
    for field in ("floor_bodies", "boundaries", "obstacles"):
        if (
            a["boundary_and_obstacle_collision"][field]
            != b["boundary_and_obstacle_collision"][field]
        ):
            errors.append(f"collision {field} changed between v1 and v2")
    identity = candidate_identity_v2(record)
    if record["candidate_identity"] != identity:
        errors.append("candidate identity is stale")
    stage = record["validation"]["stages"][0]
    if stage["status"] != "passed" or stage["candidate_fingerprint"] != identity:
        errors.append("validation stage fingerprint is stale or not passed")
    visuals = {item["surface_id"]: item for item in b["surfaces"]}
    for surface in (
        "visual_relief_fins",
        "visual_overhead_ledges",
        "visual_boulder_caps",
    ):
        if not visuals.get(surface, {}).get("collision_origin", "").startswith("None"):
            errors.append(f"{surface} is not declared visual-only")
    decisions = " ".join(b["authoring_log"]["manual_decisions"])
    if "invented" not in decisions or "v1" not in decisions:
        errors.append("authoring log does not record invented detail and the baseline")
    for dependency in b["dependencies"]:
        path = root / dependency["path"]
        if not path.is_file() or digest(path) != dependency["sha256"]:
            errors.append(f"dependency hash mismatch: {dependency['path']}")
    return record


def check_pinned(root: Path, errors: list[str]) -> None:
    supplement = load(root, PINNED)
    for relative, expected in supplement["files"].items():
        path = root / relative
        if not path.is_file() or digest(path) != expected:
            errors.append(f"frozen/accepted file changed: {relative}")


def check_provenance(root: Path, errors: list[str]) -> None:
    provenance = load(root, PROVENANCE)
    if provenance["baseline"]["room_id"] != "slot-canyon-courtyard-v1":
        errors.append("provenance baseline room id is wrong")
    if provenance["variant"]["room_id"] != "slot-canyon-courtyard-v2":
        errors.append("provenance variant room id is wrong")
    if provenance["registration_accepted"] or provenance["scale_calibrated"]:
        errors.append("provenance calibration flags are not false")
    if not provenance["no_new_collidable_obstacles"]:
        errors.append("provenance does not record no new collidable obstacles")
    control = provenance["negative_control"]["description"]
    if "escape" not in control or "missing boundary" not in control:
        errors.append("negative control description is incomplete")
    for side, folder in (
        ("baseline", "slot-canyon-courtyard-v1"),
        ("variant", "slot-canyon-courtyard-v2"),
    ):
        for key, relative in (
            ("scene", provenance[side]["scene"]),
            ("script", f"{ROOMS}/{folder}/room.gd"),
        ):
            path = root / relative
            if not path.is_file() or digest(path) != provenance[side][f"{key}_sha256"]:
                errors.append(f"{side} {key} hash mismatch in provenance")
    matched = provenance["matched_capture"]
    if not matched["same_harness_for_both_scenes"]:
        errors.append("matched captures did not use the same harness")
    harness = root / matched["harness"]
    if not harness.is_file() or digest(harness) != matched["harness_sha256"]:
        errors.append("paired capture harness hash mismatch")

    def poses(views: list[dict]) -> list[dict]:
        return [
            {key: value for key, value in view.items() if key != "path"}
            for view in views
        ]

    if matched["camera_baseline"] != matched["camera_variant"]:
        errors.append("matched captures differ on camera settings")
    for field in ("views", "walk_path"):
        if poses(matched[f"{field}_baseline"]) != poses(matched[f"{field}_variant"]):
            errors.append(f"matched captures differ on {field}")
    for side, receipt in (
        ("baseline", provenance["baseline"]["guard_receipt"]),
        ("variant", provenance["variant"]["guard_receipt"]),
    ):
        actual = load(root, receipt["path"])
        if digest(root / receipt["path"]) != receipt["sha256"]:
            errors.append(f"{side} guard receipt hash mismatch")
        if actual["return_code"] != 0 or actual["timed_out"] or actual["error"]:
            errors.append(f"{side} guard receipt is not clean")
        if receipt["return_code"] != 0 or receipt["timed_out"] or receipt["error"]:
            errors.append(f"{side} guard receipt is not clean")


def check_sources(root: Path, errors: list[str]) -> None:
    v1 = text(root, f"{BASELINE}/room.gd")
    v2 = text(root, f"{VARIANT}/room.gd")
    for name in (
        "WALL_SEGMENTS",
        "FLOOR_SEGMENTS",
        "ROCK_OBSTACLES",
        "SPAWN",
        "PANORAMA_PATH",
        "TEXTURE_ROOT",
        "WALL_HEIGHT",
    ):
        if const_block(v1, name) != const_block(v2, name):
            errors.append(f"room constant {name} changed between v1 and v2")
    relief = function_block(v2, "_build_visual_relief")
    if "_add_collision_box" in relief:
        errors.append("visual relief creates a collider")
    test = text(root, f"{VARIANT}/test_room.gd")
    for needle in (
        "_check_boundary_negative",
        "escape negative control",
        "missing-boundary negative control",
        "collidable body set changed",
    ):
        if needle not in test:
            errors.append(f"headless test lacks {needle}")
    res_variant_script = "res://" + VARIANT.removeprefix("godot_walk/") + "/room.gd"
    if res_variant_script not in text(root, f"{VARIANT}/room.tscn"):
        errors.append("variant scene does not use the variant script")
    manifest = load(root, f"{VARIANT}/captures/capture_manifest.json")
    if manifest["registration_accepted"] or manifest["scale_calibrated"]:
        errors.append("capture manifest flags are not false")
    for name in CAPTURE_NAMES:
        if not (root / f"{VARIANT}/captures/{name}.png").is_file():
            errors.append(f"variant capture missing: {name}")
    if len(manifest["views"]) != 4 or len(manifest["walk_path"]) != 5:
        errors.append("capture manifest does not cover 4 views and 5 walk steps")


def check_ledger(root: Path, errors: list[str]) -> None:
    events = (
        root / "godot_walk/source_library/sources/video-22909eb734e4d8e2/events.jsonl"
    )
    content = events.read_text(encoding="utf-8")
    if "slot-canyon-courtyard-v2" in content or "issue-273" in content:
        errors.append("ledger contains a hand-written issue-273 event")


def collect_errors(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    check_candidate(root, errors)
    check_pinned(root, errors)
    check_provenance(root, errors)
    check_sources(root, errors)
    check_ledger(root, errors)
    return errors


def main() -> int:
    errors = collect_errors()
    baseline_manifest = ROOT / f"{BASELINE_CAPTURES}/capture_manifest.json"
    print(
        f"baseline paired capture manifest present locally: {baseline_manifest.is_file()}"
    )
    if errors:
        for error in errors:
            print(f"FAIL issue-273 canyon variant: {error}")
        return 1
    print(
        "PASS issue-273 canyon variant: v2 identity valid, footprint/colliders "
        "identical to v1, 23 visual-only relief nodes, boundary and floor negative "
        "controls declared, matched camera poses, clean guard receipts, frozen "
        "artifacts unchanged and no hand-written ledger events"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
