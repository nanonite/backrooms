"""Growth-time diagonal sites for gmap-0.6.1 (#196)."""

from __future__ import annotations

import hashlib
import random
from typing import Any

from gmap_diagonal import (
    CHAMFER_M,
    CLEAR_WIDTH_M,
    CLEARANCE_M,
    WALL_M,
    _passage_polygon,
    _point_on_cut,
    _rect_intersects_polygon,
)
from gmap_geometry import rect_polygon
from shape_room_chamfer import (
    apply_cuts,
    approach_issues,
    clearance_ok,
    cut_issues,
    port_edge,
)

SITE_PROBABILITY = 0.35
SITE_STREAM = "diagonal-sites:gmap-0.6.1"


def rng_for(seed: int, attempt: int, layout_variant: int = 0) -> random.Random:
    digest = hashlib.sha256(
        f"{seed}:{attempt}:{layout_variant}:{SITE_STREAM}".encode()
    ).digest()
    return random.Random(int.from_bytes(digest, "big"))


def reserved_cell_ids(zones: list[dict[str, Any]]) -> set[str]:
    return {cell_id for zone in zones for cell_id in zone["endpoint_ids"]}


def record_site(draft: Any, pair: dict[str, Any]) -> None:
    draft.reserved_diagonal_zones.append(
        {"site_id": f"ds{len(draft.reserved_diagonal_zones):02d}", **pair}
    )


def corners(rect: tuple[float, float, float, float]) -> list[list[float]]:
    x0, z0, x1, z1 = rect
    return [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]


def record_cell(
    cell: Any, rect: tuple[float, float, float, float] | None = None
) -> dict[str, Any]:
    return {
        "cell_id": cell.cell_id,
        "envelope_xz": rect_polygon(rect or cell.rect),
        "role": cell.role,
        "module": cell.module,
        "required_ports": [
            {
                "port_id": p.port_id,
                "pos_xz": list(p.pos),
                "normal": list(p.normal),
                "compatibility_type": p.compatibility_type,
                "placement": p.placement,
            }
            for p in cell.ports
        ],
    }


def source_cut_ok(cell: dict[str, Any], index: int, sx: int, sz: int) -> bool:
    ring = cell["envelope_xz"]
    corner = ring[index]
    position = _point_on_cut(cell, list(corner), sx, sz)
    port = {
        "port_id": "candidate",
        "pos_xz": position,
        "normal": [sx / 2**0.5, sz / 2**0.5],
    }
    if any(
        _distance(position, p["pos_xz"]) < 2.0 - 1e-7 for p in cell["required_ports"]
    ):
        return False
    final = apply_cuts([(float(x), float(z)) for x, z in ring], {index: CHAMFER_M})
    edge = port_edge(final, port)
    return (
        not cut_issues(
            [(float(x), float(z)) for x, z in ring],
            cell["required_ports"],
            {index: CHAMFER_M},
        )
        and edge is not None
        and _distance(final[edge], final[(edge + 1) % len(final)])
        >= CLEAR_WIDTH_M + 1.0
        and not approach_issues(final, [port])
        and clearance_ok(final)
    )


def _distance(a: list[float], b: list[float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _candidate(
    a: dict[str, Any], b: dict[str, Any], occupied: list[dict[str, Any]]
) -> dict[str, Any] | None:
    ar, br = a["envelope_xz"], b["envelope_xz"]
    if min(_width(ar), _depth(ar), _width(br), _depth(br)) < 4.0:
        return None
    for ia, ca in enumerate(ar):
        for ib, cb in enumerate(br):
            dx, dz = cb[0] - ca[0], cb[1] - ca[1]
            if abs(dx) != 1 or abs(dz) != 1:
                continue
            sx, sz = int(dx), int(dz)
            if not source_cut_ok(a, ia, sx, sz) or not source_cut_ok(b, ib, -sx, -sz):
                continue
            start, finish = _point_on_cut(a, ca, sx, sz), _point_on_cut(b, cb, -sx, -sz)
            if _distance(start, finish) < 2.0:
                continue
            zone = _passage_polygon(
                start, finish, CLEAR_WIDTH_M / 2 + WALL_M + CLEARANCE_M
            )
            if any(_rect_intersects_polygon(item["rect"], zone) for item in occupied):
                continue
            return {
                "endpoint_ids": [a["cell_id"], b["cell_id"]],
                "corner_indices": [ia, ib],
                "corner_xz": [ca, cb],
                "start_xz": start,
                "finish_xz": finish,
                "clearance_polygon_xz": zone,
            }
    return None


def _width(ring: list[list[float]]) -> float:
    return max(p[0] for p in ring) - min(p[0] for p in ring)


def _depth(ring: list[list[float]]) -> float:
    return max(p[1] for p in ring) - min(p[1] for p in ring)


def site_for_rect(
    draft: Any, parent: Any, child: Any, rect: tuple[float, float, float, float]
) -> dict[str, Any] | None:
    from gmap_geometry import polygon_rect

    parent_port = next((p for p in child.ports), None)
    if parent_port is None:
        return None
    reserved_ids = reserved_cell_ids(draft.reserved_diagonal_zones)
    records = [
        record_cell(cell)
        for cell in draft.cells.values()
        if cell.role in ("ground", "figure")
        and not cell.module
        and cell.cell_id not in reserved_ids
    ]
    child_record = record_cell(child, rect)
    child_record["required_ports"] = [
        {
            "port_id": parent_port.port_id,
            "pos_xz": list(parent_port.pos),
            "normal": list(parent_port.normal),
        }
    ]
    occupied = []
    for cell in draft.cells.values():
        bounds = polygon_rect(rect_polygon(cell.rect))
        if bounds is not None:
            occupied.append({"cell_id": cell.cell_id, "rect": bounds})
    candidates = []
    for existing in records:
        if existing["cell_id"] in (parent.cell_id, child.cell_id):
            continue
        pair = _candidate(
            existing,
            child_record,
            [
                item
                for item in occupied
                if item["cell_id"] not in (existing["cell_id"], child.cell_id)
            ],
        )
        if pair is None:
            continue
        if any(
            _rect_intersects_polygon(
                polygon_rect(rect_polygon(cell.rect)), pair["clearance_polygon_xz"]
            )
            for cell in draft.cells.values()
            if cell.cell_id not in pair["endpoint_ids"]
        ):
            continue
        if any(
            _polygons_intersect(
                pair["clearance_polygon_xz"], zone["clearance_polygon_xz"]
            )
            for zone in draft.reserved_diagonal_zones
        ):
            continue
        candidates.append(pair)
    return (
        min(candidates, key=lambda item: (item["endpoint_ids"], item["corner_indices"]))
        if candidates
        else None
    )


def _polygons_intersect(left: list[list[float]], right: list[list[float]]) -> bool:
    for polygon, other in ((left, right), (right, left)):
        for index, point in enumerate(polygon):
            following = polygon[(index + 1) % len(polygon)]
            axis = (-(following[1] - point[1]), following[0] - point[0])
            projections = [p[0] * axis[0] + p[1] * axis[1] for p in polygon]
            other_projection = [p[0] * axis[0] + p[1] * axis[1] for p in other]
            if (
                min(max(projections), max(other_projection))
                - max(min(projections), min(other_projection))
                <= 1e-7
            ):
                return False
    return True
