"""Read-only integrity checks for the issue-270 finite horizon-ring fixture.

Verifies finite world-fixed ring geometry, a static infinity sky, no collision,
a bounded camera path, the disabled baseline views, a threshold angular parallax
shift, false flags, and that no accepted room, frozen contract or pinned project
file was edited. It renders nothing, makes no model calls, edits nothing and
admits nothing to the catalog.
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
SOURCE_REFERENCE = ACCEPTED_RECORD

REQUIRED_VIEWS = ("translate_a", "translate_b", "rotated", "seam_check")
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


def collect_errors(fixture_dir: Path = FIXTURE_DIR, root: Path = ROOT) -> list[str]:
    """Return all integrity errors; an empty list means the fixture is consistent."""
    errors: list[str] = []
    try:
        spec = load(fixture_dir / "horizon_spec_v1.json")
        views = load(fixture_dir / "views_v1.json")
        supplement = load(fixture_dir / "pinned_supplement_v1.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"Cannot read fixture record: {error}"]

    errors.extend(_check_ring(spec))
    errors.extend(_check_views(spec, views))
    errors.extend(_check_parallax(spec, views))
    errors.extend(_check_flags(spec, views))
    errors.extend(_check_notes(fixture_dir))
    errors.extend(_check_pinned(supplement, root))
    return errors


def _check_ring(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    ring = spec.get("ring", {})
    count = int(ring.get("segment_count", 0))
    if count < 8:
        errors.append(f"Ring needs at least eight panels; found {count}")
    if float(ring.get("radius", 0)) <= 0:
        errors.append("Ring radius must be positive")
    if (
        float(ring.get("panel_width", 0)) <= 0
        or float(ring.get("panel_thickness", 0)) <= 0
    ):
        errors.append("Ring panel width and thickness must be positive")

    heights = spec.get("panel_heights", [])
    if len(heights) != count:
        errors.append(f"Panel heights count {len(heights)} != segment count {count}")
    if any(float(value) <= 0 for value in heights):
        errors.append("Every authored panel height must be positive")
    if len({round(float(value), 3) for value in heights}) < 6:
        errors.append("Panel heights are not irregular enough to read as a silhouette")

    collision = spec.get("collision", {})
    if collision.get("policy") != "none":
        errors.append("Horizon collision policy must be explicitly none")

    sky = spec.get("sky", {})
    if sky.get("rendered_at") != "infinity":
        errors.append("Static sky must be rendered at infinity")
    if sky.get("type") != "procedural_gradient_sky":
        errors.append("Static sky type must be a procedural gradient")

    path = spec.get("camera_path", {})
    if path.get("bounded") is not True:
        errors.append("Camera path must declare bounded=true")
    if float(path.get("min_x", 0)) >= float(path.get("max_x", 0)):
        errors.append("Camera path min_x must be below max_x")

    parallax = spec.get("parallax", {})
    if float(parallax.get("min_angular_shift_deg", 0)) <= 0:
        errors.append("Parallax threshold must be positive")
    sampled = int(parallax.get("sampled_panel_index", -1))
    if not 0 <= sampled < count:
        errors.append("Sampled parallax panel index is out of range")

    reference = spec.get("source_reference", {}).get("path")
    if reference != SOURCE_REFERENCE:
        errors.append(
            "Source reference path does not match the named snow-garden record"
        )
    return errors


def _vectors(view: dict[str, Any]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    position = tuple(float(value) for value in view.get("position", []))
    target = tuple(float(value) for value in view.get("target", []))
    return position, target


def _direction(
    position: tuple[float, ...], target: tuple[float, ...]
) -> tuple[float, ...]:
    delta = tuple(target[i] - position[i] for i in range(3))
    length = math.sqrt(sum(component * component for component in delta)) or 1.0
    return tuple(component / length for component in delta)


def _check_views(spec: dict[str, Any], views: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    entries = views.get("views", [])
    by_id = {view.get("id"): view for view in entries}
    for required in REQUIRED_VIEWS:
        if required not in by_id:
            errors.append(f"Required comparison view is missing: {required}")
    for view in entries:
        for key in ("position", "target"):
            value = view.get(key)
            if (
                not isinstance(value, list)
                or len(value) != 3
                or not all(isinstance(number, (int, float)) for number in value)
            ):
                errors.append(f"View {view.get('id')} has an invalid {key}")

    steps = views.get("movement_sequence", {}).get("steps", [])
    if len(steps) < 3:
        errors.append("Movement sequence needs at least three recorded steps")

    if all(name in by_id for name in ("translate_a", "translate_b", "rotated")):
        a, b, rotated = by_id["translate_a"], by_id["translate_b"], by_id["rotated"]
        pa, ta = _vectors(a)
        pb, tb = _vectors(b)
        pr, tr = _vectors(rotated)
        if math.dist(_direction(pa, ta), _direction(pb, tb)) > 1e-6:
            errors.append("translate_a and translate_b must share one orientation")
        if abs(pb[0] - pa[0]) < 5.0:
            errors.append("The two camera positions are not clearly separated")
        if math.dist(pr, pa) > 1e-6:
            errors.append("Rotated view must hold the translate_a position in place")
        if math.dist(_direction(pr, tr), _direction(pa, ta)) < 0.5:
            errors.append("Rotated view must change orientation")

    path = spec.get("camera_path", {})
    minimum, maximum = float(path.get("min_x", 0)), float(path.get("max_x", 0))
    height, depth = float(path.get("y", 0)), float(path.get("z", 0))
    for entry in list(entries) + list(steps):
        if entry.get("on_path") is False:
            continue
        position, _ = _vectors(entry)
        if not minimum - 1e-6 <= position[0] <= maximum + 1e-6:
            errors.append(f"View {entry.get('id')} leaves the bounded path")
        if abs(position[1] - height) > 1e-6 or abs(position[2] - depth) > 1e-6:
            errors.append(f"View {entry.get('id')} leaves the authored path height/z")
    return errors


def _check_parallax(spec: dict[str, Any], views: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    by_id = {view.get("id"): view for view in views.get("views", [])}
    if not all(name in by_id for name in ("translate_a", "translate_b")):
        return errors
    ring = spec.get("ring", {})
    count = int(ring.get("segment_count", 0))
    index = int(spec.get("parallax", {}).get("sampled_panel_index", -1))
    if not count or not 0 <= index < count:
        return errors
    theta = 2 * math.pi * index / count
    point = (
        float(ring.get("center_x", 0)) + float(ring.get("radius", 0)) * math.cos(theta),
        0.0,
        float(ring.get("center_z", 0)) + float(ring.get("radius", 0)) * math.sin(theta),
    )
    angles: list[float] = []
    for name in ("translate_a", "translate_b"):
        position, target = _vectors(by_id[name])
        forward = _direction(position, target)
        right = (
            forward[1] * 0 - forward[2] * 1,
            forward[2] * 0 - forward[0] * 0,
            forward[0] * 1 - forward[1] * 0,
        )
        right_length = (
            math.sqrt(sum(component * component for component in right)) or 1.0
        )
        right = tuple(component / right_length for component in right)
        delta = tuple(point[i] - position[i] for i in range(3))
        horizontal = sum(delta[i] * right[i] for i in range(3))
        along = sum(delta[i] * forward[i] for i in range(3))
        angles.append(math.degrees(math.atan2(horizontal, along)))
    shift = abs(angles[0] - angles[1])
    if shift < float(spec.get("parallax", {}).get("min_angular_shift_deg", 0)):
        errors.append(
            f"Finite horizon parallax shift {shift:.3f} deg is below the threshold"
        )
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
        for keyword in ("authored", "uncalibrated", "infinity", "collision", "context"):
            if keyword not in text:
                errors.append(f"Authored data record does not state {keyword}")
    if not limits.is_file():
        errors.append("Limitations record is missing")
    else:
        text = limits.read_text(encoding="utf-8").lower()
        for keyword in (
            "visual-only",
            "finite",
            "collision",
            "uncalibrated",
            "seam",
            "operator",
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
        print("FAIL issue-270 horizon fixture")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "PASS issue-270 horizon fixture: finite world-fixed ring, static infinity sky, "
        "no collision, bounded path, disabled baseline, parallax, false flags and pinned assets verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
