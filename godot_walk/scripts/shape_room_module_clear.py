"""gmap-0.4.0: keep a parent room's walls off the planes of its library module's boundary (issue 190).

A library room's wall stands on its cell's boundary lines and overhangs the joint by a few
centimetres. A parent wall that runs along such a line right up to the joint (an arm end whose
side lies on the module's side line) puts two same-facing faces in one plane over the overhang.
The map cannot know the arms, so the shape room picks arm widths whose outline avoids it.
"""

from __future__ import annotations

from typing import Any

from gmap_geometry import polygon_rect
from poetics_geometry import Point

OVERHANG_M = 0.5  # same margin as the map's module placement rule (gmap_modules.OVERHANG_MARGIN_M)
EPS = 1e-6


def module_sides(document: dict[str, Any], cell: dict[str, Any]) -> list[tuple[tuple[float, ...], tuple[int, int]]]:
    """(module cell rectangle, this cell's outward normal toward it) for each library module joined to `cell`."""
    cells = {c["cell_id"]: c for c in document["cells"]}
    normals = {p["port_id"]: tuple(p["normal"]) for p in cell["required_ports"]}
    found = []
    for edge in document["edges"]:
        for mine, other in ((edge["from"], edge["to"]), (edge["to"], edge["from"])):
            neighbour = cells[other.split(":")[0]]
            if mine in normals and neighbour.get("module"):
                found.append((tuple(polygon_rect(neighbour["envelope_xz"])), normals[mine]))
    return found


def outline_conflicts(outline: list[Point], sides: list[tuple[tuple[float, ...], tuple[int, int]]]) -> bool:
    """True when an outline edge perpendicular to a joint lies on one of the module's side lines, with the
    room on the far side of that line from the module, and reaches within the overhang margin of the joint.
    (A wall whose room is on the module's side faces back to back with the library wall: no z-fight.)"""
    for rect, normal in sides:
        across = 1 if normal[1] else 0  # coordinate that is constant along the joint line
        contact = (rect[across + 2] if normal[across] < 0 else rect[across])
        side = 1 - across  # axis of the module's two side lines, constant along an edge that runs across the joint
        for a, b in zip(outline, outline[1:] + outline[:1]):
            if abs(a[side] - b[side]) > EPS or abs(a[across] - b[across]) < EPS:
                continue  # not an edge that runs across the joint
            step = b[across] - a[across]  # counter-clockwise ring: the room lies to the left of a -> b
            room_side = (-1 if step > 0 else 1) if side == 0 else (1 if step > 0 else -1)
            on_low, on_high = abs(a[side] - rect[side]) < EPS, abs(a[side] - rect[side + 2]) < EPS
            if not ((on_low and room_side < 0) or (on_high and room_side > 0)):
                continue  # the room lies on the module's side of its line: faces are back to back
            toward = max(a[across], b[across]) if normal[across] > 0 else min(a[across], b[across])  # end nearest the joint
            gap = (contact - toward) if normal[across] > 0 else (toward - contact)
            if gap < OVERHANG_M - EPS:
                return True
    return False


# Box top planes (metres above the floor) of each usable library room, measured headless on the
# instanced scenes (#190). A parent wall top on one of them would share a plane with the library's.
LIBRARY_TOP_PLANES: dict[str, tuple[float, ...]] = {
    "godot_early_pocket_single_west_v1": (1.124, 1.129),
    "godot_later_bay_column_bounded_v1": (1.129,),
    "godot_gopro_industrial_hall_south_socket_v1": (3.975, 4.01, 4.56, 4.78, 4.84, 4.98, 5.0),
    "video_ccf9722164a0bdc8_debris_window_rock_north_socket_v1": (2.4, 3.86, 3.895, 3.96, 3.97, 4.08, 4.2),
}
PLANE_TOLERANCE_M = 0.02


def module_top_planes(document: dict[str, Any], cell: dict[str, Any]) -> list[float]:
    """Top planes of the library modules joined to `cell`."""
    cells = {c["cell_id"]: c for c in document["cells"]}
    ports = {p["port_id"] for p in cell["required_ports"]}
    return [
        plane
        for edge in document["edges"]
        for mine, other in ((edge["from"], edge["to"]), (edge["to"], edge["from"]))
        if mine in ports and cells[other.split(":")[0]].get("module")
        for plane in LIBRARY_TOP_PLANES.get(cells[other.split(":")[0]]["module"]["module_id"], ())
    ]


def clear_ceiling(ceiling: float, low: float, high: float, planes: list[float]) -> float:
    """`ceiling`, or the nearest 0.1 m step in [low, high] whose wall tops avoid every plane."""
    for step in (0.0, 0.1, -0.1, 0.2, -0.2, 0.3, -0.3):
        height = round(ceiling + step, 1)
        if low - 1e-9 <= height <= high + 1e-9 and all(abs(height - plane) >= PLANE_TOLERANCE_M for plane in planes):
            return height
    return ceiling
