"""Port-pattern primitives and the arm/hub rectangles that realise them (shape stage 1)."""

from __future__ import annotations

from typing import Any

ARM_WIDTH_MIN_M = 3
Rect = tuple[float, float, float, float]
SIDE_BY_NORMAL = {(1, 0): "east", (-1, 0): "west", (0, 1): "north", (0, -1): "south"}
OPPOSITE = {"east": "west", "west": "east", "north": "south", "south": "north"}


def port_sides(ports: list[dict[str, Any]]) -> list[str]:
    sides = []
    for port in ports:
        side = SIDE_BY_NORMAL.get(tuple(port["normal"]))
        if side is None:
            raise ValueError(f"port {port['port_id']} normal is not axis-aligned")
        sides.append(side)
    return sides


def primitive_for(ports: list[dict[str, Any]]) -> str:
    """Pattern name per proposal section 5 from the ports' envelope sides."""
    sides = port_sides(ports)
    if not sides:
        raise ValueError("a walkable cell needs at least one port")
    if len(sides) == 1:
        return "dead_end"
    if len(set(sides)) < len(sides):
        return "u_shape"
    if len(sides) == 2:
        return "straight" if OPPOSITE[sides[0]] == sides[1] else "l_shape"
    return "t_shape" if len(sides) == 3 else "cross"


def arm_width_range(envelope: Rect) -> tuple[int, int]:
    shortest = min(envelope[2] - envelope[0], envelope[3] - envelope[1])
    return ARM_WIDTH_MIN_M, max(ARM_WIDTH_MIN_M, int(shortest) - 1)


def span_around(centre: float, width: float, low: float, high: float) -> tuple[float, float]:
    """Interval of `width` centred on `centre`, shifted just enough to fit [low, high]."""
    start = min(max(centre - width / 2, low), high - width)
    return start, start + width


def snap_half(value: float) -> float:
    return round(value * 2) / 2


def mean_or(values: list[float], fallback: float) -> float:
    return sum(values) / len(values) if values else fallback


def hub_centre(envelope: Rect, ports: list[dict[str, Any]], width: float) -> tuple[float, float]:
    """Point where the arms meet: x from the north/south ports, z from the east/west ports."""
    x0, z0, x1, z1 = envelope
    runs_z = [p["pos_xz"][0] for p in ports if p["normal"][1]]
    runs_x = [p["pos_xz"][1] for p in ports if p["normal"][0]]
    centre_x = snap_half(mean_or(runs_z, (x0 + x1) / 2))
    centre_z = snap_half(mean_or(runs_x, (z0 + z1) / 2))
    half = width / 2
    return min(max(centre_x, x0 + half), x1 - half), min(max(centre_z, z0 + half), z1 - half)


def arm_and_bar(
    envelope: Rect, port: dict[str, Any], width: float, hub: tuple[float, float]
) -> list[Rect]:
    x0, z0, x1, z1 = envelope
    px, pz = port["pos_xz"]
    half = width / 2
    if port["normal"][1]:
        a0, a1 = span_around(px, width, x0, x1)
        arm = (a0, min(pz, hub[1]), a1, max(pz, hub[1]))
        bar = (min(a0, hub[0] - half), hub[1] - half, max(a1, hub[0] + half), hub[1] + half)
        return [arm, bar]
    a0, a1 = span_around(pz, width, z0, z1)
    arm = (min(px, hub[0]), a0, max(px, hub[0]), a1)
    bar = (hub[0] - half, min(a0, hub[1] - half), hub[0] + half, max(a1, hub[1] + half))
    return [arm, bar]


def dead_end_rect(envelope: Rect, port: dict[str, Any], width: float) -> Rect:
    """A single arm from the port's wall to the opposite wall of the envelope."""
    x0, z0, x1, z1 = envelope
    px, pz = port["pos_xz"]
    if port["normal"][1]:
        a0, a1 = span_around(px, width, x0, x1)
        return a0, z0, a1, z1
    a0, a1 = span_around(pz, width, z0, z1)
    return x0, a0, x1, a1


def arm_rects(envelope: Rect, ports: list[dict[str, Any]], width: float) -> list[Rect]:
    """Arms from every port to a shared hub, with cross-bars; all inside the envelope."""
    if len(ports) == 1:
        return [dead_end_rect(envelope, ports[0], width)]
    hub = hub_centre(envelope, ports, width)
    rects: list[Rect] = [(hub[0] - width / 2, hub[1] - width / 2, hub[0] + width / 2, hub[1] + width / 2)]
    for port in ports:
        rects.extend(arm_and_bar(envelope, port, width, hub))
    return rects
