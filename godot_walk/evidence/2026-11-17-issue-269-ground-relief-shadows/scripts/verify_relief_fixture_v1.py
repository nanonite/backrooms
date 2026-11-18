"""Read-only integrity checks for the issue-269 authored relief/shadow fixture.

Verifies deterministic relief bounds, the flat collision policy, shadow/tree
pairing and a common shadow direction, matched views, false flags, and that no
accepted room, frozen contract or pinned project file was edited. It renders
nothing, makes no model calls, edits nothing and admits nothing to the catalog.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = SCRIPT_DIR.parent
FIXTURE_DIR = EVIDENCE_DIR / "fixture"
ROOT = EVIDENCE_DIR.parents[2]

ACCEPTED_RECORD = "godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json"
FREEZE_RECORD = "godot_walk/room_catalog/contract_freeze_v4.json"

REQUIRED_VIEWS = ("front", "side", "oblique", "close", "elevated")
FALSE_FLAGS = ("registration_accepted", "scale_calibrated", "operator_approved")


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


def height_at(x: float, z: float, drifts: list[dict[str, Any]], base: float) -> float:
    height = base
    for drift in drifts:
        dx = x - float(drift["center_x"])
        dz = z - float(drift["center_z"])
        sigma_x = float(drift["sigma_x"])
        sigma_z = float(drift["sigma_z"])
        exponent = -(
            dx * dx / (2 * sigma_x * sigma_x) + dz * dz / (2 * sigma_z * sigma_z)
        )
        height += float(drift["amplitude"]) * math.exp(exponent)
    return height


def collect_errors(fixture_dir: Path = FIXTURE_DIR, root: Path = ROOT) -> list[str]:
    """Return all integrity errors; an empty list means the fixture is consistent."""
    errors: list[str] = []
    try:
        relief = load(fixture_dir / "relief_spec_v1.json")
        shadows = load(fixture_dir / "shadow_spec_v1.json")
        views = load(fixture_dir / "views_v1.json")
        supplement = load(fixture_dir / "pinned_supplement_v1.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"Cannot read fixture record: {error}"]

    errors.extend(_check_relief(relief))
    errors.extend(_check_shadows(shadows))
    errors.extend(_check_views(views))
    errors.extend(_check_flags(relief, shadows, views))
    errors.extend(_check_notes(fixture_dir))
    errors.extend(_check_pinned(supplement, root))
    return errors


def _check_relief(relief: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    drifts = relief.get("drifts", [])
    if len(drifts) < 4:
        errors.append(
            f"Relief needs at least four authored drifts; found {len(drifts)}"
        )
    centers = [(float(d["center_x"]), float(d["center_z"])) for d in drifts]
    if len(set(centers)) != len(centers):
        errors.append("Relief drift centres are not distinct")
    sigmas = [(float(d["sigma_x"]), float(d["sigma_z"])) for d in drifts]
    if len(set(sigmas)) != len(sigmas):
        errors.append("Relief drift sigmas are not distinct (relief would be regular)")

    grid = relief.get("grid", {})
    step = float(grid.get("step", 0))
    if step <= 0:
        errors.append("Relief grid step must be positive")
        return errors
    columns = round((float(grid["max_x"]) - float(grid["min_x"])) / step) + 1
    rows = round((float(grid["max_z"]) - float(grid["min_z"])) / step) + 1
    heights = [
        height_at(
            float(grid["min_x"]) + column * step,
            float(grid["min_z"]) + row * step,
            drifts,
            float(relief.get("base_height", 0)),
        )
        for row in range(rows)
        for column in range(columns)
    ]
    if not heights:
        errors.append("Relief grid produced no sample heights")
        return errors
    bound = float(relief.get("visible_height_bound", 0))
    if bound <= 0:
        errors.append("visible_height_bound must be positive")
    elif max(abs(value) for value in heights) > bound + 1e-6:
        errors.append("Relief heights exceed the declared visible height bound")
    variation = max(heights) - min(heights)
    if variation < float(relief.get("min_relief_variation", 0)):
        errors.append(
            f"Relief variation {variation:.4f} is too shallow to read as relief"
        )

    collision = relief.get("collision", {})
    if collision.get("policy") != "flat":
        errors.append("Collision policy must be explicitly flat")
    if (
        abs(
            float(collision.get("center_y", 0))
            + float(collision.get("thickness", 0)) / 2
        )
        > 1e-6
    ):
        errors.append("Flat collider top is not at the declared surface_y=0")
    if float(collision.get("visual_collision_height_bound", 0)) != bound:
        errors.append("Collision height bound differs from the visible height bound")
    return errors


def _check_shadows(shadows: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    direction = shadows.get("shadow_direction_xz", [])
    if len(direction) != 2:
        errors.append("Shared shadow direction must be a 2-vector")
        return errors
    norm = math.hypot(float(direction[0]), float(direction[1]))
    common = (float(direction[0]) / norm, float(direction[1]) / norm)
    azimuth = math.degrees(math.atan2(common[1], common[0]))
    if abs(azimuth - float(shadows.get("shadow_direction_azimuth_deg", -1))) > 0.01:
        errors.append("Declared shadow azimuth does not match the direction vector")
    trees = shadows.get("trees", [])
    casts = shadows.get("shadows", [])
    tree_ids = [tree.get("id") for tree in trees]
    if len(set(tree_ids)) != len(tree_ids):
        errors.append("Tree ids are not unique")
    tree_by_id = {tree["id"]: tree for tree in trees}
    if len(casts) != len(trees):
        errors.append("There must be exactly one shadow per tree")
    seen: set[str] = set()
    minimum = float(shadows.get("min_shadow_length", 0))
    for cast in casts:
        tree_id = cast.get("tree_id")
        if tree_id not in tree_by_id:
            errors.append(
                f"Shadow {cast.get('id')} references an unknown tree {tree_id}"
            )
            continue
        if tree_id in seen:
            errors.append(f"Tree {tree_id} has more than one shadow")
        seen.add(tree_id)
        tree = tree_by_id[tree_id]
        if (
            abs(float(cast.get("origin_x")) - float(tree["x"])) > 1e-6
            or abs(float(cast.get("origin_z")) - float(tree["z"])) > 1e-6
        ):
            errors.append(f"Shadow {cast.get('id')} does not start at its tree base")
        vector = cast.get("direction_xz", [])
        if len(vector) != 2:
            errors.append(f"Shadow {cast.get('id')} has no direction vector")
            continue
        vector_norm = math.hypot(float(vector[0]), float(vector[1]))
        unit = (float(vector[0]) / vector_norm, float(vector[1]) / vector_norm)
        if math.dist(unit, common) > 1e-4:
            errors.append(
                f"Shadow {cast.get('id')} does not share the common direction"
            )
        length = float(cast.get("length", 0))
        if length < minimum or length < float(tree["trunk_height"]) * 1.2:
            errors.append(f"Shadow {cast.get('id')} is not long relative to its tree")
        if not 0 < float(cast.get("width_end")) < float(cast.get("width_start")):
            errors.append(f"Shadow {cast.get('id')} has an invalid taper")
    return errors


def _check_views(views: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    entries = views.get("views", [])
    ids = [view.get("id") for view in entries]
    for required in REQUIRED_VIEWS:
        if required not in ids:
            errors.append(f"Required matched view is missing: {required}")
    for view in entries:
        for key in ("position", "target"):
            value = view.get(key)
            if (
                not isinstance(value, list)
                or len(value) != 3
                or not all(isinstance(number, (int, float)) for number in value)
            ):
                errors.append(f"View {view.get('id')} has an invalid {key}")
    return errors


def _check_flags(*records: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for record in records:
        for flag in FALSE_FLAGS:
            if record.get("flags", {}).get(flag) is not False:
                errors.append(f"{record.get('record_id')}.{flag} must be false")
        if record.get("status") != "candidate_pending_review":
            errors.append(
                f"{record.get('record_id')} status must be candidate_pending_review"
            )
    return errors


def _check_notes(fixture_dir: Path) -> list[str]:
    errors: list[str] = []
    authored = fixture_dir / "authored_data_v1.md"
    limits = fixture_dir / "limitations_v1.md"
    if not authored.is_file():
        errors.append("Authored data record is missing")
    else:
        text = authored.read_text(encoding="utf-8").lower()
        for keyword in ("authored", "flat", "0.35", "uncalibrated"):
            if keyword not in text:
                errors.append(f"Authored data record does not state {keyword}")
    if not limits.is_file():
        errors.append("Limitations record is missing")
    else:
        text = limits.read_text(encoding="utf-8").lower()
        for keyword in ("relief", "shadow", "collision", "authored", "uncalibrated"):
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
        print("FAIL issue-269 relief fixture")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "PASS issue-269 relief fixture: deterministic relief bounds, flat collision, "
        "shadow/tree pairing, common direction, views, flags and pinned assets verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
