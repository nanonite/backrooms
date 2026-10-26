"""Check the recorded full-layout route crosses the new socket both ways."""

from __future__ import annotations

import argparse
import json
from itertools import pairwise
from pathlib import Path
from typing import Any


def main() -> int:
    arguments = _arguments()
    physics = json.loads(arguments.physics.read_text(encoding="utf-8"))
    controls = json.loads(arguments.controls.read_text(encoding="utf-8"))
    failures = _failures(physics, controls)
    result = {
        "scene": physics.get("scene"),
        "placements": 4,
        "distinct_module_designs": 4,
        "out_and_back": physics.get("out_and_back", {}),
        "route_targets_reached": sum(
            bool(item.get("reached")) for item in physics.get("route_segments", [])
        ),
        "route_target_count": len(physics.get("route_segments", [])),
        "new_connection_crossings": _connection_crossings(
            physics.get("route_state_trace", [])
        ),
        "negative_controls": {
            "blocked_connector": controls.get(
                "blocked_connector_negative_control", False
            ),
            "missing_floor": controls.get("missing_floor_negative_control", {}),
            "open_boundary": controls.get("open_boundary_negative_control", {}),
        },
        "failures": failures,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    if arguments.output.exists():
        raise FileExistsError(
            f"Refusing to overwrite traversal analysis: {arguments.output}"
        )
    arguments.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics", required=True, type=Path)
    parser.add_argument("--controls", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _connection_crossings(trace: list[dict[str, Any]]) -> dict[str, Any]:
    seam_x = 28.56
    crossings = {"large_room_to_corridor": [], "corridor_to_large_room": []}
    for left, right in pairwise(trace):
        first = left.get("position", [])
        second = right.get("position", [])
        if len(first) != 3 or len(second) != 3:
            continue
        if not (2.1 <= first[2] <= 4.1 and 2.1 <= second[2] <= 4.1):
            continue
        _record_crossing(crossings, left, right, seam_x)
    return {
        "seam_x": seam_x,
        "large_room_to_corridor_count": len(crossings["large_room_to_corridor"]),
        "corridor_to_large_room_count": len(crossings["corridor_to_large_room"]),
        "large_room_to_corridor": crossings["large_room_to_corridor"],
        "corridor_to_large_room": crossings["corridor_to_large_room"],
    }


def _record_crossing(
    crossings: dict[str, list[dict[str, Any]]],
    left: dict[str, Any],
    right: dict[str, Any],
    seam_x: float,
) -> None:
    first = left["position"]
    second = right["position"]
    direction = None
    if first[0] < seam_x and second[0] >= seam_x:
        direction = "large_room_to_corridor"
    elif first[0] > seam_x and second[0] <= seam_x:
        direction = "corridor_to_large_room"
    if direction:
        crossings[direction].append(
            {"from": first, "to": second, "tick": right.get("tick")}
        )


def _failures(physics: dict[str, Any], controls: dict[str, Any]) -> list[str]:
    failures = list(physics.get("failures", []))
    trace = physics.get("out_and_back", {})
    if any(not item.get("reached") for item in physics.get("route_segments", [])):
        failures.append("one or more route targets were not reached")
    if trace.get("floor_fraction", 0.0) < 0.99 or trace.get("safety_contacts", 1) != 0:
        failures.append("route floor support or SafetyNet gate failed")
    crossings = _connection_crossings(physics.get("route_state_trace", []))
    if not crossings["large_room_to_corridor_count"]:
        failures.append("trace has no large-room-to-corridor crossing")
    if not crossings["corridor_to_large_room_count"]:
        failures.append("trace has no corridor-to-large-room crossing")
    if controls.get("blocked_connector_negative_control") is not True:
        failures.append("new connector negative control did not block traversal")
    for control in ("missing_floor_negative_control", "open_boundary_negative_control"):
        if not controls.get(control):
            failures.append(f"{control} did not run")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
