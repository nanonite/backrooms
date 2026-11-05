"""Versioned regular-polygon landmark contracts for gmap-0.7.0."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gmap_grow import Vec
else:
    Vec = tuple[int, int]

LANDMARK_STREAM = "landmark:gmap-0.7.0"
LANDMARK_PROBABILITY = 0.5
LANDMARK_WEIGHTS = (
    ("rotunda16", 3),
    ("dodecagon", 2),
    ("octagon_regular", 2),
    ("hexagon", 1),
)
PORT_TYPE = "level_doorway_2m_v1"
LANDMARKS: dict[str, dict[str, Any]] = {
    "octagon_regular": {
        "sides": 8,
        "envelope": (8, 8),
        "inradius": 4.0,
        "rotation": 0.0,
    },
    "dodecagon": {"sides": 12, "envelope": (12, 12), "inradius": 6.0, "rotation": 0.0},
    "rotunda16": {"sides": 16, "envelope": (16, 16), "inradius": 8.0, "rotation": 0.0},
    "hexagon": {"sides": 6, "envelope": (10, 8), "inradius": 4.0, "rotation": 30.0},
}
EPS = 1e-7


def rng_for(seed: int, attempt: int) -> random.Random:
    """Named independent stream; placement variants share one class and target step."""
    import hashlib

    digest = hashlib.sha256(f"{seed}:{attempt}:{LANDMARK_STREAM}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big"))


def draw_plan(seed: int, attempt: int, cell_target: int) -> dict[str, Any] | None:
    rng = rng_for(seed, attempt)
    if rng.random() >= LANDMARK_PROBABILITY:
        return None
    pick = rng.randrange(sum(weight for _, weight in LANDMARK_WEIGHTS))
    landmark_class = LANDMARK_WEIGHTS[-1][0]
    for candidate, weight in LANDMARK_WEIGHTS:
        if pick < weight:
            landmark_class = candidate
            break
        pick -= weight
    rotation = 90.0 * rng.randrange(2) if landmark_class == "hexagon" else 0.0
    return {
        "class": landmark_class,
        "target_step": rng.randrange(1, cell_target),
        "rotation_deg": rotation,
    }


def rotation_for(plan: dict[str, Any]) -> float:
    base = float(LANDMARKS[plan["class"]]["rotation"])
    return (base + float(plan["rotation_deg"])) % 360.0


def envelope_size(plan: dict[str, Any]) -> tuple[int, int]:
    width, depth = LANDMARKS[plan["class"]]["envelope"]
    return (
        (depth, width)
        if float(plan.get("rotation_deg", 0.0)) % 180.0
        else (width, depth)
    )


def port_normals(plan: dict[str, Any]) -> list[Vec]:
    if plan["class"] == "hexagon":
        return (
            [(0, 1), (0, -1)]
            if float(plan.get("rotation_deg", 0.0)) % 180.0 == 0
            else [(1, 0), (-1, 0)]
        )
    return [(1, 0), (0, 1), (-1, 0), (0, -1)]


def inradius(plan: dict[str, Any]) -> float:
    return float(LANDMARKS[plan["class"]]["inradius"])


def circumradius(plan: dict[str, Any]) -> float:
    return inradius(plan) / math.cos(math.pi / int(LANDMARKS[plan["class"]]["sides"]))


def facet_length(plan: dict[str, Any]) -> float:
    sides = int(LANDMARKS[plan["class"]]["sides"])
    return 2.0 * inradius(plan) * math.tan(math.pi / sides)


def normal_for_facet(index: int, plan: dict[str, Any]) -> Vec:
    sides = int(LANDMARKS[plan["class"]]["sides"])
    # Vertices start at rotation + pi/N, so edge i's outward normal is
    # rotation + 2*pi*(i+1)/N.
    angle = math.radians(rotation_for(plan)) + 2.0 * math.pi * (index + 1) / sides
    return round(math.cos(angle), 6), round(math.sin(angle), 6)


def port_facet_indices(plan: dict[str, Any]) -> list[int]:
    allowed = port_normals(plan)
    return [
        index
        for index in range(int(LANDMARKS[plan["class"]]["sides"]))
        if any(
            math.dist(normal_for_facet(index, plan), normal) <= EPS
            for normal in allowed
        )
    ]


def regular_polygon(
    center: tuple[float, float], plan: dict[str, Any]
) -> list[list[float]]:
    sides, radius = int(LANDMARKS[plan["class"]]["sides"]), circumradius(plan)
    rotation = math.radians(rotation_for(plan)) + math.pi / sides
    return [
        [
            round(center[0] + radius * math.cos(rotation + i * 2 * math.pi / sides), 6)
            + 0.0,
            round(center[1] + radius * math.sin(rotation + i * 2 * math.pi / sides), 6)
            + 0.0,
        ]
        for i in range(sides)
    ]


def cell_landmark(plan: dict[str, Any], status: str = "placed") -> dict[str, Any]:
    return {
        "class": plan["class"],
        "inradius_m": inradius(plan),
        "circumradius_m": round(circumradius(plan), 6),
        "rotation_deg": rotation_for(plan),
        "port_facet_indices": port_facet_indices(plan),
        "status": status,
    }


def map_landmark(
    plan: dict[str, Any],
    status: str,
    cell_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    record = {**cell_landmark(plan, status), "target_step": int(plan["target_step"])}
    if cell_id is not None:
        record["cell_id"] = cell_id
    if reason is not None:
        record["reason"] = reason
    return record
