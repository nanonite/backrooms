"""Mechanical fit of one module against one generative-map cell.

Pure geometry, no I/O and no judgement. A module is tried at yaw 0/90/180/270
(Godot Y rotation: x' = x cos + z sin, z' = -x sin + z cos) and at every 1 m
lattice translation whose rotated footprint stays inside the cell envelope.
Each required cell port is joined to a tested socket of the same compatibility
type (within 0.5 m, equal outward normal) or else to a port slot whose edge
contains the port (adapter work). A placement is a fit only when every
required port is covered.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterator

from integration_polygons import polygon_within, rotate
from poetics_geometry import TOLERANCE_M, bbox_of, open_ring, segment_distance, signed_area

Point = tuple[float, float]

ROTATIONS_DEG = (0, 90, 180, 270)
LATTICE_M = 1.0
SOCKET_MATCH_M = 0.5
SLOT_CONTAIN_M = 0.05
NORMAL_DOT_MIN = 0.99
SLACK_WEIGHT = 0.1


@dataclass(frozen=True)
class SocketGeom:
    socket_id: str
    position: Point
    normal: Point
    compatibility_type: str


@dataclass(frozen=True)
class SlotGeom:
    slot_id: str
    start: Point
    end: Point
    normal: Point


@dataclass(frozen=True)
class ModuleGeometry:
    footprint: list[Point]
    sockets: list[SocketGeom]  # tested sockets only: the only ones layout may use
    slots: list[SlotGeom]


@dataclass(frozen=True)
class PortCover:
    port_id: str
    kind: str  # "socket" or "adapter"
    ref: str  # socket_id or slot_id


@dataclass(frozen=True)
class Fit:
    cell_id: str
    yaw_deg: int
    translation: Point
    score: float
    covers: tuple[PortCover, ...]
    slack_m2: float


@dataclass(frozen=True)
class CellOutcome:
    """Best fit of one cell, plus why no fit exists when `fit` is None."""

    cell_id: str
    fit: Fit | None
    footprint_fitted: bool


def placements(footprint: list[Point], envelope: list[Point]) -> Iterator[tuple[int, Point, list[Point]]]:
    """Yield (yaw, translation, placed footprint) for each footprint that fits."""
    env_min_x, env_min_z, env_max_x, env_max_z = bbox_of(envelope)
    for yaw in ROTATIONS_DEG:
        rotated = [rotate(p, yaw) for p in footprint]
        min_x, min_z, max_x, max_z = bbox_of(rotated)
        x_range = range(
            math.ceil((env_min_x - min_x - TOLERANCE_M) / LATTICE_M),
            math.floor((env_max_x - max_x + TOLERANCE_M) / LATTICE_M) + 1,
        )
        z_range = range(
            math.ceil((env_min_z - min_z - TOLERANCE_M) / LATTICE_M),
            math.floor((env_max_z - max_z + TOLERANCE_M) / LATTICE_M) + 1,
        )
        for ix in x_range:
            for iz in z_range:
                shift = (ix * LATTICE_M, iz * LATTICE_M)
                placed = [(x + shift[0], z + shift[1]) for x, z in rotated]
                if polygon_within(placed, envelope):
                    yield yaw, shift, placed


def _same_direction(a: Point, b: Point) -> bool:
    return a[0] * b[0] + a[1] * b[1] >= NORMAL_DOT_MIN


def _place(point: Point, yaw: int, shift: Point) -> Point:
    x, z = rotate(point, yaw)
    return (x + shift[0], z + shift[1])


def cover_ports(
    ports: list[dict[str, Any]], geometry: ModuleGeometry, yaw: int, shift: Point
) -> tuple[list[PortCover], list[str]]:
    """Cover each port by a tested socket, else a port slot. Returns (covers, uncovered)."""
    used: set[str] = set()
    covers: list[PortCover] = []
    uncovered: list[str] = []
    for port in sorted(ports, key=lambda item: item["port_id"]):
        position, normal = tuple(port["pos_xz"]), tuple(port["normal"])
        socket = _nearest_socket(port, position, normal, geometry, yaw, shift, used)
        if socket is not None:
            used.add(f"socket:{socket}")
            covers.append(PortCover(port["port_id"], "socket", socket))
            continue
        slot = _containing_slot(position, normal, geometry, yaw, shift, used)
        if slot is not None:
            used.add(f"slot:{slot}")
            covers.append(PortCover(port["port_id"], "adapter", slot))
        else:
            uncovered.append(port["port_id"])
    return covers, uncovered


def _nearest_socket(port, position, normal, geometry, yaw, shift, used) -> str | None:
    best: tuple[float, str] | None = None
    for socket in geometry.sockets:
        if (
            f"socket:{socket.socket_id}" in used
            or socket.compatibility_type != port["compatibility_type"]
            or not _same_direction(rotate(socket.normal, yaw), normal)
        ):
            continue
        placed = _place(socket.position, yaw, shift)
        distance = math.hypot(placed[0] - position[0], placed[1] - position[1])
        if distance <= SOCKET_MATCH_M and (best is None or (distance, socket.socket_id) < best):
            best = (distance, socket.socket_id)
    return None if best is None else best[1]


def _containing_slot(position, normal, geometry, yaw, shift, used) -> str | None:
    for slot in sorted(geometry.slots, key=lambda item: item.slot_id):
        if f"slot:{slot.slot_id}" in used or not _same_direction(rotate(slot.normal, yaw), normal):
            continue
        start, end = _place(slot.start, yaw, shift), _place(slot.end, yaw, shift)
        if segment_distance(position, start, end) <= SLOT_CONTAIN_M:
            return slot.slot_id
    return None


def score_fit(covers: list[PortCover], required: int, slack: float, envelope_area: float) -> float:
    by_socket = sum(1 for cover in covers if cover.kind == "socket")
    by_adapter = len(covers) - by_socket
    coverage = (by_socket * 2 + by_adapter) / (2 * required)
    return round(coverage - SLACK_WEIGHT * (slack / envelope_area), 9)


def best_fit_for_cell(cell: dict[str, Any], geometry: ModuleGeometry) -> CellOutcome:
    """Best placement in one cell: highest score, then lowest yaw, x, z."""
    envelope = open_ring(cell["envelope_xz"])
    envelope_area = abs(signed_area(envelope))
    module_area = abs(signed_area(geometry.footprint))
    ports = cell["required_ports"]
    best: Fit | None = None
    fitted = False
    for yaw, shift, _placed in placements(geometry.footprint, envelope):
        fitted = True
        if not ports:
            continue
        covers, uncovered = cover_ports(ports, geometry, yaw, shift)
        if uncovered:
            continue
        slack = max(0.0, envelope_area - module_area)
        score = score_fit(covers, len(ports), slack, envelope_area)
        candidate = Fit(cell["cell_id"], yaw, shift, score, tuple(covers), round(slack, 6))
        if best is None or _rank(candidate) < _rank(best):
            best = candidate
    return CellOutcome(cell["cell_id"], best, fitted)


def _rank(fit: Fit) -> tuple[float, int, float, float]:
    return (-fit.score, fit.yaw_deg, fit.translation[0], fit.translation[1])


def top_fits(
    cells: list[dict[str, Any]], geometry: ModuleGeometry, limit: int = 5
) -> tuple[list[Fit], bool]:
    """Best fit per cell, top `limit` overall; also whether any footprint fitted anywhere."""
    outcomes = [best_fit_for_cell(cell, geometry) for cell in cells]
    fits = sorted(
        (item.fit for item in outcomes if item.fit is not None),
        key=lambda fit: (-fit.score, fit.cell_id, fit.yaw_deg, fit.translation),
    )
    return fits[:limit], any(item.footprint_fitted for item in outcomes)
