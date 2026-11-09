"""Deterministic floor levels, ramps and one-way ledge drops for gmap-0.10.0 (#201).

The elevation layer runs after the gmap-0.9.0 surface layer. It assigns one
floor level per walkable cell, one vertical kind per edge, raises the ceiling of
every lower room a ramp or drop opens into, and keeps the directed walk graph
strongly connected. Geometry, light, palette and surface records are otherwise
untouched: generated rooms stay local (floor at y = 0) and the assembly offsets
them by ``floor_y``.

A drop is one-way from its upper cell to its lower cell. It is only accepted
when the upper cell stays reachable from the lower one, so every cell can still
reach every other cell through the directed graph.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import deque
from collections.abc import Iterable
from copy import deepcopy
from typing import Any

RULE = "elevation_layer"
STREAM = "elevation:gmap-0.10.0"
LEVELS = (-3.0, -1.5, 0.0, 1.5, 3.0)
CHANGE_PROBABILITY = 0.30
DROP_PROBABILITY = 0.20  # a subset of the changes: P(drop) = 0.20, P(ramp) = 0.10
DROP_CHOICES = (1.5, 3.0, 4.5)
RAMP_RISE_M = 1.5
RAMP_MIN_RUN_M = 3.2
RAMP_RUN_M = 3.25  # 1.5 m rise over 3.25 m run: 24.78 degrees
RAMP_MAX_ANGLE_DEG = 25.0
RAMP_WIDTH_M = 2.2
RAMP_END_MARGIN_M = 0.25
CLEARANCE_M = 2.6
LOOP_BUDGET = 3
EPS = 1e-9


def rng_for(seed: int, attempt: int) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{attempt}:{STREAM}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big"))


def edge_cells(edge: dict[str, Any]) -> tuple[str, str]:
    return edge["from"].split(":")[0], edge["to"].split(":")[0]


def edge_key(edge: dict[str, Any]) -> tuple[str, str]:
    return tuple(sorted(edge_cells(edge)))  # type: ignore[return-value]


def walkable_ids(document: dict[str, Any]) -> list[str]:
    return [cell["cell_id"] for cell in document["cells"] if cell["role"] != "void"]


def tree_edges(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        edge
        for edge in document["edges"]
        if edge.get("connector") == "direct" and edge.get("kind") not in ("diagonal", "elevation_loop")
    ]


def strongly_connected(cell_ids: Iterable[str], edges: Iterable[tuple[str, str]]) -> bool:
    """True when every listed cell reaches every other through the directed edges.

    Reusable over any map graph: callers pass the directed edge list rather than
    letting the generator bury the test in its own bookkeeping, so a mutation can
    re-check that an exit stays reachable after every change.
    """
    ids = sorted(set(cell_ids))
    if not ids:
        return True
    graph: dict[str, list[str]] = {cell_id: [] for cell_id in ids}
    reverse: dict[str, list[str]] = {cell_id: [] for cell_id in ids}
    for left, right in edges:
        if left in graph and right in graph:
            graph[left].append(right)
            reverse[right].append(left)
    for neighbours in graph.values():
        neighbours.sort()
    for neighbours in reverse.values():
        neighbours.sort()

    order = _finish_order(ids, graph)
    seen: set[str] = set()
    components = 0
    for start in reversed(order):
        if start in seen:
            continue
        components += 1
        stack = [start]
        seen.add(start)
        while stack:
            current = stack.pop()
            for neighbour in reverse[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
    return components == 1


def _finish_order(cell_ids: list[str], graph: dict[str, list[str]]) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []
    for start in cell_ids:
        if start in seen:
            continue
        seen.add(start)
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            current, index = stack.pop()
            neighbours = graph[current]
            if index < len(neighbours):
                stack.append((current, index + 1))
                neighbour = neighbours[index]
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append((neighbour, 0))
            else:
                order.append(current)
    return order


def directed_edges(document: dict[str, Any]) -> list[tuple[str, str]]:
    """Traversal graph: drop edges go upper -> lower only; everything else goes both ways."""
    cells = {cell["cell_id"]: cell for cell in document["cells"]}
    result: list[tuple[str, str]] = []
    for edge in document["edges"]:
        if edge.get("connector") != "direct":
            continue
        left, right = edge_cells(edge)
        if left not in cells or right not in cells:
            continue
        if cells[left]["role"] == "void" or cells[right]["role"] == "void":
            continue
        if edge.get("vertical") == "drop":
            drop = edge.get("drop", {})
            upper = drop.get("upper_cell_id", left)
            lower = drop.get("lower_cell_id", right)
            result.append((str(upper), str(lower)))
        else:
            result.append((left, right))
            result.append((right, left))
    return result


def directed_reachable(document: dict[str, Any], start: str) -> set[str]:
    graph: dict[str, set[str]] = {cell_id: set() for cell_id in walkable_ids(document)}
    for left, right in directed_edges(document):
        if left in graph and right in graph:
            graph[left].add(right)
    reached = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbour in sorted(graph[current] - reached):
            reached.add(neighbour)
            queue.append(neighbour)
    return reached


def drop_has_return_route(document: dict[str, Any], upper: str, lower: str) -> bool:
    """True when the lower cell still reaches the upper one through the directed graph."""
    return upper in directed_reachable(document, lower)


def _rect(cell: dict[str, Any]) -> tuple[float, float, float, float]:
    points = cell["envelope_xz"]
    xs = [float(point[0]) for point in points]
    zs = [float(point[1]) for point in points]
    return min(xs), min(zs), max(xs), max(zs)


def _cell_capacity(cell: dict[str, Any]) -> float:
    """Highest ceiling this cell can take without rebuilding a fixed-height room."""
    if cell.get("module") or cell.get("landmark") or cell.get("diagonal_passage"):
        return float(cell["ceiling_range_m"][1])
    return float(cell["ceiling_range_m"][1])


def _port_for_cell(edge: dict[str, Any], cell_id: str) -> str:
    return edge["from"] if edge["from"].split(":")[0] == cell_id else edge["to"]


def _port_record(document: dict[str, Any], port_id: str) -> dict[str, Any]:
    for cell in document["cells"]:
        for port in cell["required_ports"]:
            if port["port_id"] == port_id:
                return port
    return {}


def ramp_fits(document: dict[str, Any], edge: dict[str, Any], lower_id: str) -> bool:
    """A 1.5 m ramp fits inside the lower cell along the doorway axis."""
    cells = {cell["cell_id"]: cell for cell in document["cells"]}
    lower = cells[lower_id]
    if lower.get("module") or lower.get("landmark") or lower.get("diagonal_passage"):
        return False
    if _cell_capacity(lower) + EPS < RAMP_RISE_M + CLEARANCE_M:
        return False
    port = _port_record(document, _port_for_cell(edge, lower_id))
    if not port:
        return False
    normal = port["normal"]
    x0, z0, x1, z1 = _rect(lower)
    depth = (x1 - x0) if abs(float(normal[0])) > 0.5 else (z1 - z0)
    width = (z1 - z0) if abs(float(normal[0])) > 0.5 else (x1 - x0)
    return (
        depth + EPS >= RAMP_MIN_RUN_M + RAMP_END_MARGIN_M
        and width + EPS >= RAMP_WIDTH_M + 0.2
    )


def drop_fits(document: dict[str, Any], lower_id: str, drop_m: float) -> bool:
    cells = {cell["cell_id"]: cell for cell in document["cells"]}
    lower = cells[lower_id]
    if lower.get("module") or lower.get("diagonal_passage"):
        return False
    if not (1.5 - EPS <= drop_m <= 4.5 + EPS):
        return False
    return _cell_capacity(lower) + EPS >= drop_m + CLEARANCE_M


def _drop_candidate(parent_floor: float, rng: random.Random) -> tuple[float, float] | None:
    options = [
        level
        for level in LEVELS
        if 1.5 - EPS <= abs(level - parent_floor) <= 4.5 + EPS
    ]
    if not options:
        return None
    child = rng.choice(options)
    return child, abs(child - parent_floor)


def _ramp_candidate(parent_floor: float, rng: random.Random) -> float | None:
    options = [level for level in LEVELS if abs(level - parent_floor) == 1.5]
    return rng.choice(options) if options else None


def _lock_paths(document: dict[str, Any], adjacency: dict[str, set[str]], edges: dict[tuple[str, str], dict[str, Any]]) -> set[tuple[str, str]]:
    """Lock every tree edge that keeps a diagonal link or a landmark at one level."""
    locked: set[tuple[str, str]] = set()
    cells = {cell["cell_id"]: cell for cell in document["cells"]}
    for edge in tree_edges(document):
        left, right = edge_cells(edge)
        if (
            cells[left].get("module")
            or cells[right].get("module")
            or cells[left].get("landmark")
            or cells[right].get("landmark")
            or cells[left].get("diagonal_passage")
            or cells[right].get("diagonal_passage")
        ):
            locked.add(edge_key(edge))
    for cell in document["cells"]:
        passage = cell.get("diagonal_passage")
        if not passage:
            continue
        path = _tree_path(adjacency, passage["from_cell_id"], passage["to_cell_id"])
        for left, right in path:
            locked.add(tuple(sorted((left, right))))
    return locked


def _tree_path(adjacency: dict[str, set[str]], start: str, finish: str) -> list[tuple[str, str]]:
    previous: dict[str, str] = {start: start}
    queue = deque([start])
    while queue and finish not in previous:
        current = queue.popleft()
        for neighbour in sorted(adjacency.get(current, set())):
            if neighbour not in previous:
                previous[neighbour] = current
                queue.append(neighbour)
    if finish not in previous:
        return []
    path: list[tuple[str, str]] = []
    current = finish
    while current != start:
        parent = previous[current]
        path.append((parent, current))
        current = parent
    return path


def _tree_order(
    root: str, adjacency: dict[str, set[str]]
) -> list[tuple[str, str]]:
    order: list[tuple[str, str]] = []
    seen = {root}
    queue = deque([root])
    while queue:
        current = queue.popleft()
        for neighbour in sorted(adjacency.get(current, set())):
            if neighbour in seen:
                continue
            seen.add(neighbour)
            order.append((current, neighbour))
            queue.append(neighbour)
    return order


def assign_elevation(document: dict[str, Any]) -> None:
    """Attach the v0.10 elevation layer; deterministic and idempotent over its own fields."""
    cells = {cell["cell_id"]: cell for cell in document["cells"]}
    root = document["cells"][0]["cell_id"]
    tree = tree_edges(document)
    adjacency: dict[str, set[str]] = {cell_id: set() for cell_id in walkable_ids(document)}
    for edge in tree:
        left, right = edge_cells(edge)
        if left in adjacency and right in adjacency:
            adjacency[left].add(right)
            adjacency[right].add(left)
    locked = _lock_paths(document, adjacency, {edge_key(edge): edge for edge in tree})
    order = _tree_order(root, adjacency)

    floors: dict[str, float] = {root: 0.0}
    changes: dict[tuple[str, str], float] = {}
    planned_footprints: dict[str, list[tuple[float, float, float, float]]] = {}
    rng = rng_for(int(document["seed"]), int(document.get("attempt", 0)))

    for parent, child in order:
        key = tuple(sorted((parent, child)))
        if key in locked:
            floors[child] = floors[parent]
            continue
        change = rng.random() < CHANGE_PROBABILITY
        if not change:
            floors[child] = floors[parent]
            continue
        options = [
            level
            for level in LEVELS
            if abs(level - floors[parent]) == RAMP_RISE_M
        ]
        if not options:
            floors[child] = floors[parent]
            continue
        target = rng.choice(options)
        lower = parent if floors[parent] < target else child
        edge = _edge_for(document, key)
        if edge and ramp_fits(document, edge, lower):
            footprint = _ramp_footprint(document, edge, lower)
            if not any(
                _rects_overlap(footprint, other)
                for other in planned_footprints.get(lower, [])
            ):
                floors[child] = target
                changes[key] = abs(target - floors[parent])
                planned_footprints.setdefault(lower, []).append(footprint)
            else:
                floors[child] = floors[parent]
        else:
            floors[child] = floors[parent]

    for cell in document["cells"]:
        if cell["cell_id"] not in floors and cell.get("diagonal_passage"):
            passage = cell["diagonal_passage"]
            floors[cell["cell_id"]] = floors.get(
                passage["from_cell_id"], floors.get(passage["to_cell_id"], 0.0)
            )
    for cell in document["cells"]:
        if cell["cell_id"] not in floors:
            floors[cell["cell_id"]] = _void_floor(document, cell["cell_id"], floors)

    for cell in document["cells"]:
        cell["floor_y"] = floors[cell["cell_id"]]

    if "elevation_loops" not in document:
        add_loop_edges(document, floors, rng, adjacency, {key: 1.5 for key in changes})

    verticals: dict[tuple[str, str], dict[str, Any]] = {}
    for parent, child in order:
        key = tuple(sorted((parent, child)))
        if key not in changes:
            verticals[key] = {"vertical": "level"}
            continue
        delta = changes[key]
        upper, lower = (parent, child) if floors[parent] > floors[child] else (child, parent)
        edge = _edge_for(document, key)
        drop = {
            "upper_cell_id": upper,
            "lower_cell_id": lower,
            "drop_m": delta,
        }
        candidate = {**verticals, key: {"vertical": "drop", "drop": drop}}
        if (
            drop_fits(document, lower, delta)
            and _drop_landing_clear(
                document,
                edge,
                lower,
                delta,
                _planned_ramp_footprints(document, changes, skip=key),
            )
            and strongly_connected(
                walkable_ids(document), _graph_with(document, candidate)
            )
        ):
            verticals[key] = {"vertical": "drop", "drop": drop}
        else:
            verticals[key] = {
                "vertical": "ramp",
                "ramp": {
                    "lower_cell_id": lower,
                    "upper_cell_id": upper,
                    "rise_m": RAMP_RISE_M,
                    "run_m": RAMP_RUN_M,
                    "width_m": RAMP_WIDTH_M,
                    "angle_deg": round(
                        math.degrees(math.atan2(RAMP_RISE_M, RAMP_RUN_M)), 6
                    ),
                },
            }

    for edge in document["edges"]:
        key = edge_key(edge)
        if key in verticals:
            edge.update(verticals[key])
        elif edge.get("kind") == "elevation_loop":
            continue
        else:
            edge["vertical"] = "level"

    for edge in document["edges"]:
        if edge.get("vertical") not in ("ramp", "drop"):
            continue
        record = edge.get("ramp") or edge.get("drop") or {}
        lower_id = str(record.get("lower_cell_id", ""))
        upper_id = str(record.get("upper_cell_id", ""))
        rise = float(record.get("rise_m", record.get("drop_m", 0.0)))
        if lower_id not in cells or upper_id not in cells:
            continue
        lower = cells[lower_id]
        if lower.get("module") or lower.get("diagonal_passage"):
            continue
        required = rise + CLEARANCE_M
        lower["ceiling_range_m"][0] = max(float(lower["ceiling_range_m"][0]), required)
        lower["ceiling_range_m"][1] = max(float(lower["ceiling_range_m"][1]), required)

    document["elevation"] = {
        "stream": STREAM,
        "levels_m": list(LEVELS),
        "change_probability": CHANGE_PROBABILITY,
        "drop_probability": DROP_PROBABILITY,
        "ramp_rise_m": RAMP_RISE_M,
        "ramp_min_run_m": RAMP_MIN_RUN_M,
        "clearance_m": CLEARANCE_M,
    }


def _drop_landing_clear(
    document: dict[str, Any],
    edge: dict[str, Any],
    lower_id: str,
    drop_m: float,
    planned: dict[str, list[tuple[float, float, float, float]]] | None = None,
) -> bool:
    """True when no ramp already occupies the lower cell's drop landing area."""
    lower_port = _port_record(document, _port_for_cell(edge, lower_id))
    if not lower_port:
        return False
    normal = (float(lower_port["normal"][0]), float(lower_port["normal"][1]))
    inward = (-normal[0], -normal[1])
    start = (float(lower_port["pos_xz"][0]), float(lower_port["pos_xz"][1]))
    reach = max(2.6, drop_m * 1.5)
    landing = _footprint(start, inward, 2.4, reach)
    for footprint in (planned or {}).get(lower_id, []):
        if _rects_overlap(landing, footprint):
            return False
    for other in document["edges"]:
        ramp = other.get("ramp")
        if not ramp or str(ramp.get("lower_cell_id", "")) != lower_id:
            continue
        if edge_key(other) == edge_key(edge):
            continue
        port = _port_record(document, _port_for_cell(other, lower_id))
        if not port:
            continue
        other_normal = (float(port["normal"][0]), float(port["normal"][1]))
        other_inward = (-other_normal[0], -other_normal[1])
        other_start = (float(port["pos_xz"][0]), float(port["pos_xz"][1]))
        footprint = _footprint(
            other_start,
            other_inward,
            float(ramp.get("width_m", RAMP_WIDTH_M)),
            float(ramp.get("run_m", RAMP_RUN_M)),
        )
        if _rects_overlap(landing, footprint):
            return False
    return True


def _ramp_footprint(
    document: dict[str, Any], edge: dict[str, Any], lower_id: str
) -> tuple[float, float, float, float]:
    port = _port_record(document, _port_for_cell(edge, lower_id))
    if not port:
        return (0.0, 0.0, 0.0, 0.0)
    normal = (float(port["normal"][0]), float(port["normal"][1]))
    return _footprint(
        (float(port["pos_xz"][0]), float(port["pos_xz"][1])),
        (-normal[0], -normal[1]),
        RAMP_WIDTH_M,
        RAMP_RUN_M,
    )


def _planned_ramp_footprints(
    document: dict[str, Any],
    changes: dict[tuple[str, str], float],
    skip: tuple[str, str] | None = None,
) -> dict[str, list[tuple[float, float, float, float]]]:
    planned: dict[str, list[tuple[float, float, float, float]]] = {}
    for edge in tree_edges(document):
        key = edge_key(edge)
        if key not in changes or key == skip:
            continue
        left, right = edge_cells(edge)
        lower = left if _floor(document, left) < _floor(document, right) else right
        planned.setdefault(lower, []).append(_ramp_footprint(document, edge, lower))
    return planned


def _floor(document: dict[str, Any], cell_id: str) -> float:
    for cell in document["cells"]:
        if cell["cell_id"] == cell_id:
            return float(cell.get("floor_y", 0.0))
    return 0.0


def _footprint(
    start: tuple[float, float], inward: tuple[float, float], width: float, reach: float
) -> tuple[float, float, float, float]:
    lateral = (-inward[1], inward[0])
    end = (start[0] + inward[0] * reach, start[1] + inward[1] * reach)
    half = width / 2.0
    points = [
        (start[0] + lateral[0] * half, start[1] + lateral[1] * half),
        (start[0] - lateral[0] * half, start[1] - lateral[1] * half),
        (end[0] + lateral[0] * half, end[1] + lateral[1] * half),
        (end[0] - lateral[0] * half, end[1] - lateral[1] * half),
    ]
    xs = [point[0] for point in points]
    zs = [point[1] for point in points]
    return min(xs), min(zs), max(xs), max(zs)


def _rects_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return min(a[2], b[2]) - max(a[0], b[0]) > EPS and min(a[3], b[3]) - max(a[1], b[1]) > EPS


def _graph_with(document: dict[str, Any], verticals: dict[tuple[str, str], dict[str, Any]]) -> list[tuple[str, str]]:
    view = deepcopy(document)
    for edge in view["edges"]:
        key = edge_key(edge)
        if key in verticals:
            edge.update(verticals[key])
        elif edge.get("kind") == "elevation_loop":
            edge["vertical"] = "level"
    return directed_edges(view)


def _loop_candidates(
    document: dict[str, Any], floors: dict[str, float]
) -> list[tuple[str, str, int]]:
    cells = {cell["cell_id"]: cell for cell in document["cells"] if cell["role"] != "void"}
    existing = {
        tuple(sorted(edge_cells(edge)))
        for edge in document["edges"]
        if edge.get("connector") == "direct"
    }
    candidates: list[tuple[str, str, int]] = []
    ids = sorted(cells)
    for index, left in enumerate(ids):
        for right in ids[index + 1 :]:
            if (left, right) in existing:
                continue
            left_cell, right_cell = cells[left], cells[right]
            if any(
                cell.get("module")
                or cell.get("landmark")
                or cell.get("diagonal_passage")
                or cell.get("diagonal_link_chamfer")
                for cell in (left_cell, right_cell)
            ):
                continue
            delta = abs(floors.get(left, 0.0) - floors.get(right, 0.0))
            if delta > RAMP_RISE_M + EPS:
                continue
            shared = _shared_boundary(left_cell, right_cell)
            if shared is None or shared[2] - shared[1] + EPS < 3.0:
                continue
            candidates.append((left, right, int(shared[2] - shared[1])))
    return candidates


def _shared_boundary(
    left: dict[str, Any], right: dict[str, Any]
) -> tuple[str, float, float] | None:
    lx0, lz0, lx1, lz1 = _rect(left)
    rx0, rz0, rx1, rz1 = _rect(right)
    if abs(lx1 - rx0) <= EPS or abs(lx0 - rx1) <= EPS:
        lo, high = max(lz0, rz0), min(lz1, rz1)
        return ("x", lo, high) if high - lo > EPS else None
    if abs(lz1 - rz0) <= EPS or abs(lz0 - rz1) <= EPS:
        lo, high = max(lx0, rx0), min(lx1, rx1)
        return ("z", lo, high) if high - lo > EPS else None
    return None


def _ports_far_enough(document: dict[str, Any], left: str, right: str, pos: tuple[float, float]) -> bool:
    for cell in document["cells"]:
        if cell["cell_id"] not in (left, right):
            continue
        for port in cell["required_ports"]:
            if math.dist(port["pos_xz"], pos) < 2.5 - EPS:
                return False
    return True


def _stage2_unchanged(cell: dict[str, Any], port: dict[str, Any]) -> bool:
    from gmap_stage2 import cell_eligible
    from shape_room_stage2 import STAGE2_CLASSES

    expected = set(cell["allowed_primitives"]) & set(STAGE2_CLASSES)
    candidate = {**cell, "required_ports": [*cell["required_ports"], port]}
    if set(cell_eligible(candidate)) != expected:
        return False
    target = cell.get("shape_class_target")
    return target is None or target in cell_eligible(candidate)


def add_loop_edges(
    document: dict[str, Any],
    floors: dict[str, float],
    rng: random.Random,
    adjacency: dict[str, set[str]],
    changes: dict[tuple[str, str], float],
) -> None:
    """Add non-tree loops that give tree drops a return route.

    A loop is level when its endpoints share a floor and a ramp when they are
    one level apart (the lower room must fit the ramp). Candidates whose tree
    path crosses a planned level change are preferred.
    """
    candidates = _loop_candidates(document, floors)
    planned = _planned_ramp_footprints(document, changes)
    rng.shuffle(candidates)
    changed = set(changes)
    ranked: list[tuple[int, str, str, int]] = []
    for left, right, length in candidates:
        path = set(_tree_path(adjacency, left, right))
        ranked.append((len(path & changed), left, right, length))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    cells = {cell["cell_id"]: cell for cell in document["cells"]}
    used: list[dict[str, Any]] = []
    for _overlap, left, right, _length in ranked:
        if len(used) >= LOOP_BUDGET:
            break
        shared = _shared_boundary(cells[left], cells[right])
        if shared is None:
            continue
        axis, lo, high = shared
        if axis == "x":
            lx0, _lz0, lx1, _lz1 = _rect(cells[left])
            rx0, _rz0, _rx1, _rz1 = _rect(cells[right])
            boundary = lx1 if abs(lx1 - rx0) <= EPS else lx0
            pos = (boundary, round((lo + high) / 2.0 * 2.0) / 2.0)
            normal_left = (1.0, 0.0) if abs(lx1 - rx0) <= EPS else (-1.0, 0.0)
        else:
            _lx0, lz0, _lx1, lz1 = _rect(cells[left])
            _rx0, rz0, _rx1, _rz1 = _rect(cells[right])
            boundary = lz1 if abs(lz1 - rz0) <= EPS else lz0
            pos = (round((lo + high) / 2.0 * 2.0) / 2.0, boundary)
            normal_left = (0.0, 1.0) if abs(lz1 - rz0) <= EPS else (0.0, -1.0)
        if not _ports_far_enough(document, left, right, pos):
            continue
        number = len(used)
        left_port = {
            "port_id": f"{left}:e{number}",
            "pos_xz": [pos[0], pos[1]],
            "normal": [normal_left[0], normal_left[1]],
            "compatibility_type": "level_doorway_2m_v1",
            "placement": "standard",
        }
        right_port = {
            "port_id": f"{right}:e{number}",
            "pos_xz": [pos[0], pos[1]],
            "normal": [-normal_left[0], -normal_left[1]],
            "compatibility_type": "level_doorway_2m_v1",
            "placement": "standard",
        }
        if not _stage2_unchanged(cells[left], left_port) or not _stage2_unchanged(
            cells[right], right_port
        ):
            continue
        cells[left]["required_ports"].append(left_port)
        cells[right]["required_ports"].append(right_port)
        edge = {
            "from": left_port["port_id"],
            "to": right_port["port_id"],
            "connector": "direct",
            "kind": "elevation_loop",
            "vertical": "level",
        }
        delta = abs(floors.get(left, 0.0) - floors.get(right, 0.0))
        if delta > EPS:
            lower = left if floors[left] < floors[right] else right
            upper = right if lower == left else left
            footprint = _ramp_footprint(document, edge, lower) if ramp_fits(
                document, edge, lower
            ) else (0.0, 0.0, 0.0, 0.0)
            overlaps = any(
                _rects_overlap(footprint, other)
                for other in planned.get(lower, [])
            )
            for other in document["edges"]:
                if (
                    other.get("ramp")
                    and str(other["ramp"]["lower_cell_id"]) == lower
                    and _rects_overlap(
                        footprint, _ramp_footprint(document, other, lower)
                    )
                ):
                    overlaps = True
            if footprint[2] > footprint[0] and not overlaps:
                edge["vertical"] = "ramp"
                edge["ramp"] = {
                    "lower_cell_id": lower,
                    "upper_cell_id": upper,
                    "rise_m": RAMP_RISE_M,
                    "run_m": RAMP_RUN_M,
                    "width_m": RAMP_WIDTH_M,
                    "angle_deg": round(
                        math.degrees(math.atan2(RAMP_RISE_M, RAMP_RUN_M)), 6
                    ),
                }
            else:
                cells[left]["required_ports"].remove(left_port)
                cells[right]["required_ports"].remove(right_port)
                continue
        document["edges"].append(edge)
        used.append(
            {"from_cell_id": left, "to_cell_id": right, "port_id": left_port["port_id"]}
        )
    document["edges"].sort(key=lambda edge: (edge["from"], edge["to"]))
    document["elevation_loops"] = {
        "budget": LOOP_BUDGET,
        "used": len(used),
        "pairs": used,
    }


def strip_elevation(document: dict[str, Any]) -> dict[str, Any]:
    """Base copy with every elevation artifact removed, for deterministic re-derivation."""
    result = deepcopy(document)
    result.pop("elevation", None)
    result.pop("elevation_loops", None)
    loop_ports = {
        edge["from"]
        for edge in result["edges"]
        if edge.get("kind") == "elevation_loop"
    } | {
        edge["to"]
        for edge in result["edges"]
        if edge.get("kind") == "elevation_loop"
    }
    result["edges"] = [
        edge for edge in result["edges"] if edge.get("kind") != "elevation_loop"
    ]
    for cell in result["cells"]:
        cell.pop("floor_y", None)
        cell["required_ports"] = [
            port for port in cell["required_ports"] if port["port_id"] not in loop_ports
        ]
    for edge in result["edges"]:
        edge.pop("vertical", None)
        edge.pop("ramp", None)
        edge.pop("drop", None)
    return result


def _edge_for(document: dict[str, Any], key: tuple[str, str]) -> dict[str, Any]:
    for edge in tree_edges(document):
        if edge_key(edge) == key:
            return edge
    return {}


def _void_floor(document: dict[str, Any], cell_id: str, floors: dict[str, float]) -> float:
    for edge in document["edges"]:
        if edge.get("connector") != "closed_visible":
            continue
        left, right = edge_cells(edge)
        other = right if left == cell_id else left if right == cell_id else ""
        if other and other in floors:
            return floors[other]
    return 0.0


def elevation_errors(document: dict[str, Any]) -> list[dict[str, str]]:
    """All elevation errors for a gmap-0.10.0 document."""
    cells = {cell["cell_id"]: cell for cell in document["cells"]}
    errors: list[dict[str, str]] = []
    walkable = walkable_ids(document)
    if not walkable:
        return [_error("elevation_no_walkable_cells", "map has no walkable cells")]
    spawn = document["cells"][0]["cell_id"]
    for cell in document["cells"]:
        floor = cell.get("floor_y")
        if floor not in LEVELS:
            errors.append(_error("elevation_floor_invalid", cell["cell_id"]))
        low, high = cell.get("ceiling_range_m", [0.0, 0.0])
        if not cell.get("module") and float(low) + EPS < CLEARANCE_M:
            errors.append(_error("elevation_ceiling_clearance", cell["cell_id"]))
        if float(high) + EPS < float(low):
            errors.append(_error("elevation_ceiling_range", cell["cell_id"]))
    if cells[spawn].get("floor_y") != 0.0:
        errors.append(_error("elevation_spawn_not_zero", spawn))

    for edge in document["edges"]:
        vertical = edge.get("vertical")
        if vertical not in ("level", "ramp", "drop"):
            errors.append(_error("elevation_vertical_missing", edge["from"]))
            continue
        left, right = edge_cells(edge)
        if left not in cells or right not in cells:
            continue
        left_floor = float(cells[left].get("floor_y", 0.0))
        right_floor = float(cells[right].get("floor_y", 0.0))
        if vertical == "level":
            if abs(left_floor - right_floor) > EPS:
                errors.append(_error("elevation_level_floors_differ", edge["from"]))
            continue
        record = edge.get(vertical)
        if not isinstance(record, dict):
            errors.append(_error("elevation_record_missing", edge["from"]))
            continue
        lower_id = str(record.get("lower_cell_id", ""))
        upper_id = str(record.get("upper_cell_id", ""))
        if lower_id not in (left, right) or upper_id not in (left, right) or lower_id == upper_id:
            errors.append(_error("elevation_record_cells", edge["from"]))
            continue
        lower_floor = float(cells[lower_id].get("floor_y", 0.0))
        upper_floor = float(cells[upper_id].get("floor_y", 0.0))
        rise = float(record.get("rise_m", record.get("drop_m", 0.0)))
        if upper_floor - lower_floor <= EPS:
            errors.append(_error("elevation_record_direction", edge["from"]))
        if vertical == "ramp":
            if abs((upper_floor - lower_floor) - RAMP_RISE_M) > EPS:
                errors.append(_error("elevation_ramp_rise", edge["from"]))
            run = float(record.get("run_m", 0.0))
            if run + EPS < RAMP_MIN_RUN_M:
                errors.append(_error("elevation_ramp_run", edge["from"]))
            angle = math.degrees(math.atan2(rise, run)) if run > 0 else 90.0
            if angle > RAMP_MAX_ANGLE_DEG + 1e-6:
                errors.append(_error("elevation_ramp_angle", edge["from"]))
            if not ramp_fits(document, edge, lower_id):
                errors.append(_error("elevation_ramp_fit", edge["from"]))
        else:
            if not (1.5 - EPS <= rise <= 4.5 + EPS):
                errors.append(_error("elevation_drop_range", edge["from"]))
        if lower_floor + float(cells[lower_id]["ceiling_range_m"][1]) + EPS < upper_floor + CLEARANCE_M:
            errors.append(_error("elevation_room_clearance", lower_id))

    for cell in document["cells"]:
        if cell.get("landmark") or cell.get("diagonal_passage"):
            for edge in document["edges"]:
                left, right = edge_cells(edge)
                if cell["cell_id"] not in (left, right) or edge.get("connector") != "direct":
                    continue
                if abs(float(cells[left].get("floor_y", 0.0)) - float(cells[right].get("floor_y", 0.0))) > EPS:
                    errors.append(_error("elevation_link_level", cell["cell_id"]))

    if not strongly_connected(walkable, directed_edges(document)):
        errors.append(_error("elevation_graph_not_strongly_connected", "directed walk graph"))

    expected = strip_elevation(document)
    assign_elevation(expected)
    expected_cells = {cell["cell_id"]: cell for cell in expected["cells"]}
    expected_edges = {
        (edge["from"], edge["to"]): edge for edge in expected["edges"]
    }
    if set(expected_edges) != {(edge["from"], edge["to"]) for edge in document["edges"]}:
        errors.append(_error("elevation_loop_mismatch", "edge set"))
    for cell in document["cells"]:
        reference = expected_cells[cell["cell_id"]]
        if cell.get("floor_y") != reference.get("floor_y"):
            errors.append(_error("elevation_assignment_mismatch", cell["cell_id"]))
        if cell.get("ceiling_range_m") != reference.get("ceiling_range_m"):
            errors.append(_error("elevation_ceiling_mismatch", cell["cell_id"]))
    for edge in document["edges"]:
        reference = expected_edges.get((edge["from"], edge["to"]), {})
        for field in ("vertical", "ramp", "drop", "kind"):
            if edge.get(field) != reference.get(field):
                errors.append(_error("elevation_assignment_mismatch", edge["from"]))
                break
    if document.get("elevation_loops") != expected.get("elevation_loops"):
        errors.append(_error("elevation_loop_mismatch", "loop metadata"))
    for field in ("stream", "levels_m", "change_probability", "drop_probability", "ramp_rise_m", "ramp_min_run_m", "clearance_m"):
        if document.get("elevation", {}).get(field) != expected.get("elevation", {}).get(field):
            errors.append(_error("elevation_metadata_mismatch", field))
    return errors


def distribution(document: dict[str, Any]) -> dict[str, Any]:
    """Report the level, ramp and drop counts used by the evidence report."""
    levels: dict[str, int] = {}
    for cell in document["cells"]:
        if cell["role"] == "void":
            continue
        key = f"{float(cell.get('floor_y', 0.0)):+.1f}"
        levels[key] = levels.get(key, 0) + 1
    verticals = {"level": 0, "ramp": 0, "drop": 0}
    for edge in document["edges"]:
        verticals[str(edge.get("vertical", "level"))] = verticals.get(
            str(edge.get("vertical", "level")), 0
        ) + 1
    return {"levels": dict(sorted(levels.items())), "edges": verticals}


def _error(code: str, message: str) -> dict[str, str]:
    return {"rule": RULE, "code": code, "message": message}
