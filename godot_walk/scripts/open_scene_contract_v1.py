"""Read-only validator for the versioned open-scene coverage contract v1.

CPU-only and synthetic-fixture friendly. It checks a finite supported coverage
footprint, a safe spawn, an unknown exterior, no wall ring, no observed coverage
edge, classified obstacles, and a declared traversal policy with a coverage
indication. It does not implement runtime traversal, admit anything to the room
catalog, or reinterpret the frozen enclosed-room contract.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "godot_walk/room_catalog/open_scene_coverage_v1.schema.json"

CONTRACT_ID = "godot_open_scene_coverage"
CONTRACT_VERSION = "1.0.0"
SCHEMA_VERSION = 1
DEFAULT_TRAVERSAL_POLICY = "stop"
TRAVERSAL_POLICIES = ("stop", "return")
ROOM_CONTRACT_ID = "godot_video_room_completion"

_TOLERANCE = 1e-9


class OpenSceneContractError(ValueError):
    """An open-scene candidate record is invalid."""


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def default_traversal_policy(
    text: str = "Coverage limit reached — no mapped ground beyond this point.",
    kind: str = "coverage_limit_reached",
) -> dict[str, Any]:
    """Return the contract-default policy declaration (stop)."""
    return {
        "policy": DEFAULT_TRAVERSAL_POLICY,
        "coverage_indication": {"kind": kind, "player_facing_text": text},
    }


def validate(record: Any) -> list[str]:
    """Return all validation errors for a candidate record (empty when valid)."""
    if not isinstance(record, dict):
        return ["Open-scene candidate must be a JSON object"]
    if record.get("contract_id") == ROOM_CONTRACT_ID:
        return [
            "Enclosed room-contract records cannot be validated as open-scene candidates"
        ]
    errors: list[str] = []
    errors.extend(_explicit_errors(record))
    validator = jsonschema.Draft202012Validator(load_schema())
    errors.extend(
        f"schema: {list(error.absolute_path)}: {error.message}"
        for error in sorted(
            validator.iter_errors(record), key=lambda item: list(item.absolute_path)
        )
    )
    errors.extend(_spatial_errors(record))
    return errors


def _explicit_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if record.get("contract_id") != CONTRACT_ID:
        errors.append(f"Unknown contract id {record.get('contract_id')!r}")
    if record.get("contract_version") != CONTRACT_VERSION:
        errors.append("Unsupported open-scene contract version")
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("Unsupported open-scene schema version")
    if record.get("scene_category") != "open_world":
        errors.append("Open-scene candidates must declare scene_category 'open_world'")
    if record.get("status") == "accepted_reference":
        errors.append(
            "A candidate fixture cannot be an accepted reference; operator acceptance is a separate gate"
        )
    if (
        record.get("registration_accepted") is True
        or record.get("scale_calibrated") is True
    ):
        errors.append(
            "Both calibration flags must remain false in open-scene candidates"
        )
    if record.get("catalog_scope", "not_admitted_pending_integration_design") != (
        "not_admitted_pending_integration_design"
    ):
        errors.append("Open-scene candidates are not admitted to the room catalog")

    if "exterior_classification" not in record:
        errors.append("Missing exterior classification")
    elif record["exterior_classification"] != "unknown":
        errors.append(
            "Exterior classification must be 'unknown'; the source continuation is not observed safe ground"
        )

    errors.extend(_boundary_errors(record))
    errors.extend(_visual_errors(record))
    errors.extend(_obstacle_errors(record))
    errors.extend(_policy_errors(record))
    return errors


def _boundary_errors(record: dict[str, Any]) -> list[str]:
    boundary = record.get("boundary")
    if not isinstance(boundary, dict):
        return (
            ["Missing boundary declaration"]
            if boundary is None
            else ["Boundary declaration must be an object"]
        )
    errors: list[str] = []
    if boundary.get("wall_ring_present") is True:
        errors.append("Open-scene coverage must not declare a wall ring")
    if boundary.get("boundary_collider_present") is True:
        errors.append("Open-scene coverage must not declare a boundary collider")
    if boundary.get("edge_is_observed_geometry") is True:
        errors.append("The coverage edge must not be represented as observed geometry")
    exits = boundary.get("exits")
    if not isinstance(exits, list):
        errors.append("Boundary exits must be a list")
    return errors


def _visual_errors(record: dict[str, Any]) -> list[str]:
    horizon = record.get("visual_horizon")
    if not isinstance(horizon, dict):
        return (
            ["Missing visual horizon declaration"]
            if horizon is None
            else ["Visual horizon declaration must be an object"]
        )
    errors: list[str] = []
    if horizon.get("open_sky") is not True:
        errors.append("Visual horizon must declare open_sky true")
    if horizon.get("visual_only") is not True:
        errors.append("Distant scenery must be declared visual_only")
    if horizon.get("is_observed_geometry") is not False:
        errors.append("Visual horizon must not be declared observed geometry")
    return errors


def _obstacle_errors(record: dict[str, Any]) -> list[str]:
    obstacles = record.get("obstacles")
    if not isinstance(obstacles, list):
        return ["Obstacles must be a list"]
    errors: list[str] = []
    for index, obstacle in enumerate(obstacles):
        if not isinstance(obstacle, dict):
            errors.append(f"obstacles[{index}] must be an object")
            continue
        if obstacle.get("is_coverage_edge") is True:
            errors.append(
                f"obstacles[{index}] marks the coverage edge as an obstacle; "
                "a coverage limit needs separate evidence to be an observed obstacle"
            )
        if obstacle.get("provenance") == "observed":
            evidence = obstacle.get("evidence_ref")
            if not isinstance(evidence, str) or not evidence:
                errors.append(
                    f"obstacles[{index}] declares observed provenance without an evidence_ref"
                )
            elif evidence.startswith("synthetic:"):
                errors.append(
                    f"obstacles[{index}] cannot claim observed provenance from synthetic evidence"
                )
    return errors


def _policy_errors(record: dict[str, Any]) -> list[str]:
    policy = record.get("traversal_policy")
    if policy is None:
        return [
            "Missing traversal_policy declaration; the contract default is 'stop' but v1 records must declare it"
        ]
    if not isinstance(policy, dict):
        return ["traversal_policy must be an object"]
    errors: list[str] = []
    if "policy" not in policy:
        errors.append(
            "Missing traversal policy value; the contract default is 'stop' but v1 records must declare it"
        )
    elif policy["policy"] not in TRAVERSAL_POLICIES:
        errors.append(
            f"Unknown traversal policy {policy['policy']!r}; expected one of {list(TRAVERSAL_POLICIES)}"
        )
    indication = policy.get("coverage_indication")
    if indication is None:
        errors.append("Missing coverage indication for the traversal policy")
    elif not isinstance(indication, dict):
        errors.append("coverage_indication must be an object")
    elif (
        not isinstance(indication.get("player_facing_text"), str)
        or not indication["player_facing_text"]
    ):
        errors.append("Coverage indication requires non-empty player_facing_text")
    return errors


def _spatial_errors(record: dict[str, Any]) -> list[str]:
    coverage = record.get("coverage")
    spawn = record.get("safe_spawn_xyz")
    if not isinstance(coverage, dict) or not isinstance(spawn, list):
        return []
    vertices = coverage.get("vertices_xz")
    floor = coverage.get("floor_elevation")
    if not isinstance(vertices, list) or not isinstance(floor, (int, float)):
        return []
    errors: list[str] = []
    polygon_errors = _polygon_errors(vertices)
    errors.extend(polygon_errors)
    if len(spawn) != 3 or not all(_is_number(value) for value in spawn):
        errors.append("safe_spawn_xyz must be three finite numbers")
        return errors
    if not math.isclose(float(spawn[1]), float(floor), abs_tol=_TOLERANCE):
        errors.append("safe_spawn_xyz is not at the declared floor elevation")
    if not polygon_errors and not _strictly_inside(
        (float(spawn[0]), float(spawn[2])), vertices
    ):
        errors.append(
            "safe_spawn_xyz is not strictly inside the finite coverage footprint (on edge or outside)"
        )
    return errors


def _polygon_errors(vertices: list[Any]) -> list[str]:
    if len(vertices) < 4:
        return ["Coverage footprint requires at least four vertices"]
    errors: list[str] = []
    for index, vertex in enumerate(vertices):
        if (
            not isinstance(vertex, (list, tuple))
            or len(vertex) != 2
            or not all(_is_number(value) for value in vertex)
        ):
            errors.append(f"Coverage vertex {index} must be two finite numbers")
    if errors:
        return errors
    points = [(float(vertex[0]), float(vertex[1])) for vertex in vertices]
    area = 0.0
    for index, point in enumerate(points):
        x1, z1 = point
        x2, z2 = points[(index + 1) % len(points)]
        if math.isclose(x1, x2, abs_tol=_TOLERANCE) and math.isclose(
            z1, z2, abs_tol=_TOLERANCE
        ):
            errors.append(f"Coverage edge {index} has zero length")
        elif not (
            math.isclose(x1, x2, abs_tol=_TOLERANCE)
            or math.isclose(z1, z2, abs_tol=_TOLERANCE)
        ):
            errors.append(f"Coverage edge {index} is not axis-aligned (XZ)")
        area += x1 * z2 - x2 * z1
    if abs(area) / 2.0 <= _TOLERANCE:
        errors.append("Coverage footprint has no finite area")
    return errors


def _strictly_inside(point: tuple[float, float], vertices: list[Any]) -> bool:
    px, pz = point
    inside = False
    count = len(vertices)
    for index in range(count):
        x1, z1 = float(vertices[index][0]), float(vertices[index][1])
        x2, z2 = (
            float(vertices[(index + 1) % count][0]),
            float(vertices[(index + 1) % count][1]),
        )
        if _on_segment(px, pz, x1, z1, x2, z2):
            return False
        if (z1 > pz) != (z2 > pz):
            crossing = (x2 - x1) * (pz - z1) / (z2 - z1) + x1
            if px < crossing:
                inside = not inside
    return inside


def _on_segment(
    px: float, pz: float, x1: float, z1: float, x2: float, z2: float
) -> bool:
    if math.isclose(x1, x2, abs_tol=_TOLERANCE):
        return (
            math.isclose(px, x1, abs_tol=_TOLERANCE)
            and min(z1, z2) - _TOLERANCE <= pz <= max(z1, z2) + _TOLERANCE
        )
    return (
        math.isclose(pz, z1, abs_tol=_TOLERANCE)
        and min(x1, x2) - _TOLERANCE <= px <= max(x1, x2) + _TOLERANCE
    )


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_file(path: Path) -> dict[str, Any]:
    """Load and validate a candidate file, returning the record."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OpenSceneContractError(
            f"Cannot read candidate {path}: {error}"
        ) from error
    errors = validate(record)
    if errors:
        raise OpenSceneContractError(f"{path}: " + "; ".join(errors))
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser(
        "validate", help="Validate open-scene candidate files"
    )
    check.add_argument("paths", type=Path, nargs="+")
    arguments = parser.parse_args(argv)
    failures = 0
    for path in arguments.paths:
        errors = _errors_for_path(path)
        if errors:
            failures += 1
            print(f"FAIL {path}:")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"PASS {path}")
    return 1 if failures else 0


def _errors_for_path(path: Path) -> list[str]:
    if not path.is_file():
        return [f"Cannot read candidate {path}"]
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"Cannot read candidate {path}: {error}"]
    return validate(record)


if __name__ == "__main__":
    raise SystemExit(main())
