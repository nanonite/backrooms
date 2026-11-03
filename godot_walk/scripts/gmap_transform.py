"""Quarter-turn placement of a library module in map coordinates (issue 188).

A placement is (rotation_deg, translation_xz): a module-local point p lands at
R(p) + translation_xz, where R turns the (x, z) plane by `rotation_deg / 90` quarter turns
as (x, z) -> (-z, x). The Godot assembly applies the same placement as
`rotation.y = -deg_to_rad(rotation_deg)` and `position = (tx, floor_offset, tz)`.
"""

from __future__ import annotations

from gmap_library import Point


def rotate_vector(vector: Point, quarter_turns: int) -> Point:
    x, z = vector
    for _ in range(quarter_turns % 4):
        x, z = -z, x
    return x, z


def rotate_point(point: Point, centre: Point, quarter_turns: int) -> Point:
    dx, dz = rotate_vector((point[0] - centre[0], point[1] - centre[1]), quarter_turns)
    return centre[0] + dx, centre[1] + dz


def world_point(point: Point, rotation_deg: int, translation: Point) -> Point:
    x, z = rotate_vector(point, rotation_deg // 90)
    return x + translation[0], z + translation[1]
