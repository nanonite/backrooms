"""Route and envelope calculations for the fixed #164 layout."""

from __future__ import annotations

from typing import Any


def build_walk_route_xz() -> list[list[float]]:
    return [
        [-3.5, 0.0],
        [-3.4, 2.6],
        [-1.8, 2.6],
        [2.4, 2.6],
        [2.4, 3.1],
        [3.3, 3.1],
        [4.3, 3.1],
        [6.5, 3.1],
        [8.7, 3.1],
        [9.5, 3.1],
        [12.5, 3.1],
        [16.56, 3.1],
        [18.56, 3.1],
        [18.56, 0.5],
        [22.56, 0.5],
        [26.56, 0.5],
        [26.56, 3.1],
    ]


def measure_walk_envelope(layout: dict[str, Any], snapshot: dict[str, Any]) -> list[float]:
    modules = {item["id"]: item for item in snapshot["modules"]}
    points = []
    for placement in layout["placements"]:
        module = modules[placement["module_id"]]
        x, _, z = placement["transform"]["position"]
        for local_x, local_z in module["visual_placement_envelope_xz"]:
            if placement["transform"]["yaw_degrees"] == 180:
                local_x, local_z = -local_x, -local_z
            points.append([x + local_x, z + local_z])
    minimum_x = min(point[0] for point in points)
    minimum_z = min(point[1] for point in points)
    maximum_x = max(point[0] for point in points)
    maximum_z = max(point[1] for point in points)
    return [minimum_x, minimum_z, maximum_x - minimum_x, maximum_z - minimum_z]
