"""Door re-roll passage-graph enumerator for the #235 overlay slice.

M5 of the #223 overlay chain.  This module is the headless ``rewire-1``
reference: it freezes a departed component ``T``, builds the passage universe
``H_T`` and the mandatory pin set ``M_T``, enumerates every passage graph on the
same footprint, applies the hard invariants R0-R11, ranks the survivors by shape
consistency, builds the shortlist and makes the seeded draw.

The slice deliberately creates no runtime geometry.  The committed map is only
read; the event's ``passages_after`` is the authority for replay.  Doorway
placement is stored as pure metadata so the M6 rebuild can apply it without
re-enumerating.

Vocabulary follows proposal section 4.5 exactly:

* ``E_T`` is the current passage set of the target (the base map or the folded
  result of earlier re-rolls).
* ``H_T`` is every current passage plus every same-floor shared wall of at
  least ``MIN_SHARED_WALL_M``.
* ``M_T`` is the mandatory set: vertical passages, passages incident to a
  module, landmark or diagonal cell, and the exit-cell pins in v1.
* ``P`` is a candidate passage set with ``M_T <= P <= H_T``.

The spawn cell is a content-pinned island under the decided Q10 rule: the cell,
room and marker stay, while its incident passages may change.  The exit cell is
excluded from every target: runtime callers pass ``exit_cell`` and an exit inside
the departed component fails closed.  The §4.5.9 golden fixture is the pre-exit
structural measurement, because the committed maps predate the M3 exit layer.
The full-``A`` 3-8 rule ships here; the deferred Q9 3-8 prefix selector is a
tuning option and is not part of this slice.

Headless golden fixture::

    python godot_walk/scripts/maze_reroll.py fixture
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_exit as me
import maze_mutation as mm
from deterministic_json import ROOT, canonical_bytes

ALGORITHM_VERSION = "rewire-1"
EVENT_STREAM = "door-reroll:gmap-0.13.0"
DOORWAY_STREAM = "doorway:rewire-1"

MIN_REROLL_CELLS = 3
MAX_REROLL_CELLS = 8
MAX_DEGREE = 4
MIN_SHARED_WALL_M = 1.8
DOOR_WIDTH_M = 1.4
DOOR_HEIGHT_M = 2.2
DOORWAY_MARGIN_M = 0.2
MIN_RETAINED = 0.5
CANDIDATE_SHORTLIST = 8
MIN_REROLL_ALTERNATIVES = 2
MAX_REROLLS_PER_RUN = 3
MAX_REROLLS_PER_DOOR = 1
MAX_H_UNIVERSE = 16

TIERS: dict[int, tuple[int, int]] = {
    1: (1, 2),
    2: (2, 4),
    3: (3, 6),
}
SHAPE_TOLERANCES: dict[int, dict[str, float]] = {
    1: {
        "leaves": 1,
        "loops": 1,
        "max_depth": 1,
        "mean_depth": 0.75,
        "degree_histogram": 2,
        "door_count": 2,
    },
    2: {
        "leaves": 1,
        "loops": 1,
        "max_depth": 2,
        "mean_depth": 1.0,
        "degree_histogram": 3,
        "door_count": 3,
    },
    3: {
        "leaves": 2,
        "loops": 2,
        "max_depth": 3,
        "mean_depth": 1.5,
        "degree_histogram": 4,
        "door_count": 4,
    },
}
SHAPE_WEIGHTS = {
    "leaves": 2,
    "loops": 3,
    "max_depth": 1,
    "mean_depth": 2,
    "degree_histogram": 2,
    "door_count": 1,
    "retained": 2,
}
HARD_CHECKS = (
    "R0_same_footprint",
    "R1_connected",
    "R2_strongly_connected",
    "R3_degree_limit",
    "R4_pins",
    "R5_retained_fraction",
    "R6_edit_bounds",
    "R7_no_content_change",
    "R8_geometry",
    "R9_visibility",
    "R10_exit_reachable",
    "R11_change_is_real",
)
SEEDS = (1, 2, 3, 32, 279)


class RerollError(ValueError):
    """A target or event is not a valid ``rewire-1`` re-roll."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def cells_by_id(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(cell["cell_id"]): cell
        for cell in document.get("cells", [])
        if isinstance(cell, dict) and isinstance(cell.get("cell_id"), str)
    }


def spawn_cell_id(document: dict[str, Any]) -> str:
    cells = document.get("cells", [])
    return str(cells[0]["cell_id"]) if cells else ""


def _cell_of(port_id: str) -> str:
    return port_id.split(":", 1)[0]


def base_passage_state(
    document: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Every traversable direct passage, keyed by its sorted cell pair."""
    cells = cells_by_id(document)
    state: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in document.get("edges", []):
        if not isinstance(edge, dict) or edge.get("connector") != "direct":
            continue
        left = _cell_of(str(edge.get("from", "")))
        right = _cell_of(str(edge.get("to", "")))
        if left == right or left not in cells or right not in cells:
            continue
        if str(cells[left].get("role", "")) == "void":
            continue
        if str(cells[right].get("role", "")) == "void":
            continue
        pair = _pair(left, right)
        record: dict[str, Any] = {"vertical": str(edge.get("vertical", "level"))}
        if record["vertical"] == "drop":
            drop = edge.get("drop") if isinstance(edge.get("drop"), dict) else {}
            record["upper"] = str(drop.get("upper_cell_id", left))
            record["lower"] = str(drop.get("lower_cell_id", right))
        state[pair] = record
    return state


def _pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def _normalize_state(
    state: dict[tuple[str, str], dict[str, Any]] | set[tuple[str, str]] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    if state is None:
        return {}
    if isinstance(state, set):
        return {pair: {"vertical": "level"} for pair in state}
    return {_pair(*pair): copy.deepcopy(record) for pair, record in state.items()}


def current_passage_state(
    document: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Base passages plus every accepted ``door_reroll`` event, in order."""
    state = base_passage_state(document)
    for event in events or []:
        if not isinstance(event, dict):
            continue
        if event.get("record_kind") != "mutation":
            continue
        if event.get("event_type") != "door_reroll":
            continue
        validation = event.get("validation")
        if isinstance(validation, dict) and validation.get("outcome") == "rejected":
            continue
        apply_rewire_event(state, event)
    return state


def apply_rewire_event(
    state: dict[tuple[str, str], dict[str, Any]], event: dict[str, Any]
) -> None:
    """Apply one stored ``passages_after`` delta, refusing a stale ``before``."""
    rewire = event.get("rewire")
    if not isinstance(rewire, dict):
        raise RerollError("rewire_invalid", "door_reroll event has no rewire block")
    target = {str(cell) for cell in rewire.get("target_cells", [])}
    before = {_pair(*pair) for pair in rewire.get("passages_before", [])}
    after = {_pair(*pair) for pair in rewire.get("passages_after", [])}
    current = {pair for pair in state if pair[0] in target and pair[1] in target}
    if current != before:
        raise RerollError(
            "passages_before_mismatch",
            "event passages_before do not match the folded current state",
        )
    for pair in before - after:
        state.pop(pair, None)
    for pair in after - before:
        state[pair] = {"vertical": "level"}


def undirected_graph(
    state: dict[tuple[str, str], dict[str, Any]],
    *,
    include_drops: bool = False,
) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for pair, record in state.items():
        if record.get("vertical") == "drop" and not include_drops:
            continue
        left, right = pair
        graph.setdefault(left, set()).add(right)
        graph.setdefault(right, set()).add(left)
    return graph


def target_component(
    state: dict[tuple[str, str], dict[str, Any]],
    from_cell: str,
    to_cell: str,
) -> set[str] | None:
    """The departed component after removing the crossed passage."""
    graph = undirected_graph(state)
    if from_cell not in graph:
        return None
    seen = {from_cell}
    queue = [from_cell]
    while queue:
        current = queue.pop(0)
        for neighbour in sorted(graph.get(current, ())):
            if current == from_cell and neighbour == to_cell:
                continue
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return None if to_cell in seen else seen


def _rect(cell: dict[str, Any]) -> tuple[float, float, float, float] | None:
    envelope = cell.get("envelope_xz")
    if not isinstance(envelope, list) or len(envelope) != 4:
        return None
    points: list[tuple[float, float]] = []
    for point in envelope:
        if not isinstance(point, list) or len(point) != 2:
            return None
        points.append((float(point[0]), float(point[1])))
    xs = sorted({point[0] for point in points})
    zs = sorted({point[1] for point in points})
    if len(xs) != 2 or len(zs) != 2:
        return None
    x0, x1 = xs
    z0, z1 = zs
    for x, z in points:
        if (x, z) not in ((x0, z0), (x0, z1), (x1, z0), (x1, z1)):
            return None
    return x0, z0, x1, z1


def shared_wall(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any] | None:
    """The longest axis-aligned shared wall segment between two rectangular cells."""
    rect_a = _rect(first)
    rect_b = _rect(second)
    if rect_a is None or rect_b is None:
        return None
    ax0, az0, ax1, az1 = rect_a
    bx0, bz0, bx1, bz1 = rect_b
    walls: list[dict[str, Any]] = []
    if abs(ax1 - bx0) <= 1e-9 or abs(bx1 - ax0) <= 1e-9:
        line = ax1 if abs(ax1 - bx0) <= 1e-9 else ax0
        start, end = max(az0, bz0), min(az1, bz1)
        if end > start:
            walls.append(
                {
                    "axis": "x",
                    "line": line,
                    "start": start,
                    "end": end,
                    "length_m": end - start,
                }
            )
    if abs(az1 - bz0) <= 1e-9 or abs(bz1 - az0) <= 1e-9:
        line = az1 if abs(az1 - bz0) <= 1e-9 else az0
        start, end = max(ax0, bx0), min(ax1, bx1)
        if end > start:
            walls.append(
                {
                    "axis": "z",
                    "line": line,
                    "start": start,
                    "end": end,
                    "length_m": end - start,
                }
            )
    if not walls:
        return None
    return max(walls, key=lambda wall: wall["length_m"])


def is_content_pinned(cell: dict[str, Any]) -> bool:
    """A module, landmark or diagonal cell keeps its exact incident passages."""
    return bool(
        cell.get("module") or cell.get("landmark") or cell.get("diagonal_passage")
    )


def build_universe(
    document: dict[str, Any],
    target_cells: set[str],
    root_cell: str,
    state: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    """Build ``E_T``, ``H_T`` and the internal mandatory pin set ``M_T``."""
    cells = cells_by_id(document)
    target = sorted(target_cells)
    edges = {
        pair for pair in state if pair[0] in target_cells and pair[1] in target_cells
    }
    mandatory: set[tuple[str, str]] = set()
    for pair in edges:
        record = state[pair]
        if record.get("vertical") in ("ramp", "drop"):
            mandatory.add(pair)
        if is_content_pinned(cells[pair[0]]) or is_content_pinned(cells[pair[1]]):
            mandatory.add(pair)
    universe = set(edges)
    for left, right in itertools.combinations(target, 2):
        pair = (left, right)
        if pair in universe:
            continue
        if is_content_pinned(cells[left]) or is_content_pinned(cells[right]):
            continue
        if float(cells[left].get("floor_y", 0.0)) != float(
            cells[right].get("floor_y", 0.0)
        ):
            continue
        wall = shared_wall(cells[left], cells[right])
        if wall is not None and wall["length_m"] + 1e-9 >= MIN_SHARED_WALL_M:
            universe.add(pair)
    if len(universe) > MAX_H_UNIVERSE:
        raise RerollError(
            "target_too_large",
            f"|H_T| = {len(universe)} exceeds {MAX_H_UNIVERSE}",
        )
    return {
        "target_cells": target,
        "root_cell_id": root_cell,
        "edges_before": edges,
        "universe": universe,
        "mandatory": mandatory,
        "variable": sorted(universe - mandatory),
    }


def _degree(passages: set[tuple[str, str]], root_cell: str) -> dict[str, int]:
    degree: dict[str, int] = {}
    for left, right in passages:
        degree[left] = degree.get(left, 0) + 1
        degree[right] = degree.get(right, 0) + 1
    degree[root_cell] = degree.get(root_cell, 0) + 1
    return degree


def _connected(
    passages: set[tuple[str, str]], target_cells: set[str], root: str
) -> bool:
    graph: dict[str, set[str]] = {cell: set() for cell in target_cells}
    for left, right in passages:
        graph[left].add(right)
        graph[right].add(left)
    seen = {root}
    queue = [root]
    while queue:
        current = queue.pop(0)
        for neighbour in graph[current]:
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return seen == target_cells


def _strongly_connected(
    passages: set[tuple[str, str]],
    target_cells: set[str],
    state: dict[tuple[str, str], dict[str, Any]],
) -> bool:
    directed: dict[str, set[str]] = {cell: set() for cell in target_cells}
    for pair in passages:
        record = state.get(pair, {"vertical": "level"})
        left, right = pair
        if record.get("vertical") == "drop":
            upper = str(record.get("upper", left))
            lower = str(record.get("lower", right))
            if upper in directed and lower in directed:
                directed[upper].add(lower)
        else:
            if left in directed and right in directed:
                directed[left].add(right)
                directed[right].add(left)
    for start in target_cells:
        seen = {start}
        queue = [start]
        while queue:
            current = queue.pop(0)
            for neighbour in directed[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        if seen != target_cells:
            return False
    return True


def _depths(
    passages: set[tuple[str, str]], target_cells: set[str], root: str
) -> dict[str, int]:
    graph: dict[str, set[str]] = {cell: set() for cell in target_cells}
    for left, right in passages:
        graph[left].add(right)
        graph[right].add(left)
    depth = {root: 0}
    queue = [root]
    while queue:
        current = queue.pop(0)
        for neighbour in sorted(graph[current]):
            if neighbour not in depth:
                depth[neighbour] = depth[current] + 1
                queue.append(neighbour)
    return depth


def shape_metrics(
    passages: set[tuple[str, str]],
    target_cells: set[str],
    root_cell: str,
) -> dict[str, Any]:
    degree = _degree(passages, root_cell)
    depth = _depths(passages, target_cells, root_cell)
    leaves = sum(1 for cell in target_cells if degree.get(cell, 0) == 1)
    loops = len(passages) - (len(target_cells) - 1)
    histogram: dict[int, int] = {}
    for cell in target_cells:
        value = degree.get(cell, 0)
        histogram[value] = histogram.get(value, 0) + 1
    mean_depth = sum(depth.values()) / len(target_cells)
    return {
        "leaves": leaves,
        "loops": loops,
        "degree_histogram": histogram,
        "max_depth": max(depth.values()),
        "mean_depth": mean_depth,
        "door_count": len(passages) + 1,
    }


def _histogram_l1(first: dict[int, int], second: dict[int, int]) -> int:
    keys = set(first) | set(second)
    return sum(abs(first.get(key, 0) - second.get(key, 0)) for key in keys)


def shape_violations(shape: dict[str, Any], baseline: dict[str, Any], tier: int) -> int:
    tolerance = SHAPE_TOLERANCES[tier]
    violations = 0
    for field in ("leaves", "loops", "max_depth", "door_count"):
        if abs(shape[field] - baseline[field]) > tolerance[field]:
            violations += 1
    if abs(shape["mean_depth"] - baseline["mean_depth"]) > tolerance["mean_depth"]:
        violations += 1
    if (
        _histogram_l1(shape["degree_histogram"], baseline["degree_histogram"])
        > tolerance["degree_histogram"]
    ):
        violations += 1
    return violations


def shape_score(
    shape: dict[str, Any], baseline: dict[str, Any], retained_fraction: float
) -> float:
    score = (
        SHAPE_WEIGHTS["leaves"] * abs(shape["leaves"] - baseline["leaves"])
        + SHAPE_WEIGHTS["loops"] * abs(shape["loops"] - baseline["loops"])
        + SHAPE_WEIGHTS["max_depth"] * abs(shape["max_depth"] - baseline["max_depth"])
        + SHAPE_WEIGHTS["mean_depth"]
        * abs(shape["mean_depth"] - baseline["mean_depth"])
        + SHAPE_WEIGHTS["degree_histogram"]
        * _histogram_l1(shape["degree_histogram"], baseline["degree_histogram"])
        + SHAPE_WEIGHTS["door_count"]
        * abs(shape["door_count"] - baseline["door_count"])
        + SHAPE_WEIGHTS["retained"] * (1.0 - retained_fraction)
    )
    return round(score, 6)


def passage_key(passages: set[tuple[str, str]]) -> str:
    return ";".join(f"{left}-{right}" for left, right in sorted(passages))


def keyed_candidate_rank(
    seed: int, attempt: int, passages: set[tuple[str, str]]
) -> str:
    key = f"{seed}:{attempt}:{EVENT_STREAM}:{ALGORITHM_VERSION}:{passage_key(passages)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def candidate_set_hash(candidates: list[dict[str, Any]]) -> str:
    payload = "\n".join(sorted(candidate["key"] for candidate in candidates))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _candidate(
    passages: set[tuple[str, str]],
    edges_before: set[tuple[str, str]],
    mandatory: set[tuple[str, str]],
    target_cells: set[str],
    root_cell: str,
    state: dict[tuple[str, str], dict[str, Any]],
    baseline: dict[str, Any],
    tier: int,
    seed: int,
    attempt: int,
) -> dict[str, Any]:
    edit_distance = len(passages ^ edges_before)
    retained = len(passages & edges_before) / len(edges_before) if edges_before else 0.0
    shape = shape_metrics(passages, target_cells, root_cell)
    violations = shape_violations(shape, baseline, tier)
    return {
        "passages": passages,
        "key": passage_key(passages),
        "edit_distance": edit_distance,
        "retained_fraction": retained,
        "shape": shape,
        "shape_violations": violations,
        "shape_score": shape_score(shape, baseline, retained),
        "keyed_rank": keyed_candidate_rank(seed, attempt, passages),
        "pinned_passages": set(mandatory),
    }


def _passes_hard_invariants(
    passages: set[tuple[str, str]],
    candidate: dict[str, Any],
    edges_before: set[tuple[str, str]],
    mandatory: set[tuple[str, str]],
    target_cells: set[str],
    root_cell: str,
    state: dict[tuple[str, str], dict[str, Any]],
    tier: int,
    exit_cell: str | None,
    reachable_from: str,
) -> bool:
    min_edit, max_edit = TIERS[tier]
    if not mandatory <= passages:
        return False
    if passages == edges_before:
        return False
    if not min_edit <= candidate["edit_distance"] <= max_edit:
        return False
    if candidate["retained_fraction"] < MIN_RETAINED:
        return False
    if not _connected(passages, target_cells, root_cell):
        return False
    if not _strongly_connected(passages, target_cells, state):
        return False
    if max(_degree(passages, root_cell).values()) > MAX_DEGREE:
        return False
    if exit_cell is not None and exit_cell not in target_cells:
        graph = _graph_after(state, passages, target_cells)
        if not _reachable(graph, reachable_from, exit_cell):
            return False
    return True


def _graph_after(
    state: dict[tuple[str, str], dict[str, Any]],
    passages: set[tuple[str, str]],
    target_cells: set[str],
) -> dict[str, set[str]]:
    graph = undirected_graph(state)
    for pair in [
        pair for pair in state if pair[0] in target_cells and pair[1] in target_cells
    ]:
        graph[pair[0]].discard(pair[1])
        graph[pair[1]].discard(pair[0])
    for left, right in passages:
        graph.setdefault(left, set()).add(right)
        graph.setdefault(right, set()).add(left)
    return graph


def _reachable(graph: dict[str, set[str]], start: str, goal: str) -> bool:
    if start not in graph or goal not in graph:
        return False
    seen = {start}
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current == goal:
            return True
        for neighbour in graph.get(current, ()):
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return goal in seen


def _sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate["shape_violations"],
            candidate["edit_distance"],
            candidate["shape_score"],
            candidate["keyed_rank"],
        ),
    )


def shortlist_for(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    in_tolerance = [
        candidate for candidate in candidates if candidate["shape_violations"] == 0
    ]
    if len(in_tolerance) >= MIN_REROLL_ALTERNATIVES:
        return in_tolerance[:CANDIDATE_SHORTLIST], False
    limit = max(
        MIN_REROLL_ALTERNATIVES,
        min(CANDIDATE_SHORTLIST, len(candidates)),
    )
    return candidates[:limit], True


def threshold_port(document: dict[str, Any], from_cell: str, to_cell: str) -> str:
    """The pinned B-side port for the crossing ``from_cell -> to_cell``."""
    for edge in document.get("edges", []):
        if not isinstance(edge, dict) or edge.get("connector") != "direct":
            continue
        left = _cell_of(str(edge.get("from", "")))
        right = _cell_of(str(edge.get("to", "")))
        if left == from_cell and right == to_cell:
            return str(edge["to"])
        if right == from_cell and left == to_cell:
            return str(edge["from"])
    raise RerollError("not_bridge", f"{from_cell} -> {to_cell} has no passage")


def door_threshold_id(from_cell: str, to_cell: str) -> str:
    return me.threshold_id(from_cell, to_cell)


def analyze_target(
    document: dict[str, Any],
    from_cell: str,
    to_cell: str,
    *,
    reroll_index: int = 1,
    exit_cell: str | None = None,
    visible_cells: set[str] | None = None,
    state: dict[tuple[str, str], dict[str, Any]] | None = None,
    algorithm_version: str = ALGORITHM_VERSION,
) -> dict[str, Any]:
    """Enumerate one direction without making the seeded choice."""
    if algorithm_version != ALGORITHM_VERSION:
        return _rejected("unsupported_algorithm", from_cell, to_cell)
    if reroll_index not in TIERS:
        return _rejected("unsupported_algorithm", from_cell, to_cell)
    cells = cells_by_id(document)
    if from_cell not in cells or to_cell not in cells:
        return _rejected("not_bridge", from_cell, to_cell)
    current = (
        _normalize_state(state) if state is not None else base_passage_state(document)
    )
    crossing = current.get(_pair(from_cell, to_cell))
    if crossing is None:
        return _rejected("not_bridge", from_cell, to_cell)
    if crossing.get("vertical") == "drop":
        return _rejected("drop_door", from_cell, to_cell)
    target_cells = target_component(current, from_cell, to_cell)
    if target_cells is None:
        return _rejected("not_bridge", from_cell, to_cell)
    if len(target_cells) < MIN_REROLL_CELLS:
        return _rejected("target_too_small", from_cell, to_cell, target_cells)
    if len(target_cells) > MAX_REROLL_CELLS:
        return _rejected("target_too_large", from_cell, to_cell, target_cells)
    if exit_cell is not None and exit_cell in target_cells:
        return _rejected("exit_inside", from_cell, to_cell, target_cells)
    if visible_cells is not None and target_cells & set(visible_cells):
        return _rejected("visible_target", from_cell, to_cell, target_cells)
    universe = build_universe(document, target_cells, from_cell, current)
    seed = int(document["seed"])
    attempt = int(document.get("attempt", 0))
    baseline = shape_metrics(universe["edges_before"], target_cells, from_cell)
    candidates: list[dict[str, Any]] = []
    raw_count = 0
    for bits in range(1 << len(universe["variable"])):
        chosen = {
            pair
            for index, pair in enumerate(universe["variable"])
            if bits & (1 << index)
        }
        passages = universe["mandatory"] | chosen
        if passages == universe["edges_before"]:
            continue
        raw_count += 1
        candidate = _candidate(
            passages,
            universe["edges_before"],
            universe["mandatory"],
            target_cells,
            from_cell,
            current,
            baseline,
            reroll_index,
            seed,
            attempt,
        )
        if not _passes_hard_invariants(
            passages,
            candidate,
            universe["edges_before"],
            universe["mandatory"],
            target_cells,
            from_cell,
            current,
            reroll_index,
            exit_cell,
            to_cell,
        ):
            continue
        candidates.append(candidate)
    candidates = _sort_candidates(candidates)
    reason = ""
    shortlist: list[dict[str, Any]] = []
    relaxed = False
    checks = [
        name
        for name in HARD_CHECKS
        if name != "R9_visibility" or visible_cells is not None
    ]
    if len(candidates) == 0:
        reason = "no_candidate_in_tier" if raw_count else "no_candidate"
    elif len(candidates) < MIN_REROLL_ALTERNATIVES:
        reason = "below_min_alternatives"
    else:
        shortlist, relaxed = shortlist_for(candidates)
    return {
        "ok": not reason,
        "reason": reason,
        "algorithm_version": algorithm_version,
        "from_cell": from_cell,
        "to_cell": to_cell,
        "threshold_id": threshold_port(document, from_cell, to_cell),
        "door_threshold_id": door_threshold_id(from_cell, to_cell),
        "root_cell_id": from_cell,
        "target_cells": sorted(target_cells),
        "target_size": len(target_cells),
        "spawn_cell_id": spawn_cell_id(document),
        "spawn_in_target": spawn_cell_id(document) in target_cells,
        "edges_before": universe["edges_before"],
        "universe": universe["universe"],
        "mandatory": universe["mandatory"],
        "variable": universe["variable"],
        "shape_before": baseline,
        "candidates": candidates,
        "shortlist": shortlist,
        "consistency_relaxed": relaxed,
        "candidate_set_hash": candidate_set_hash(candidates),
        "checks": checks,
        "reroll_index": reroll_index,
    }


def _rejected(
    code: str,
    from_cell: str,
    to_cell: str,
    target_cells: set[str] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "reason": code,
        "algorithm_version": ALGORITHM_VERSION,
        "from_cell": from_cell,
        "to_cell": to_cell,
        "target_cells": sorted(target_cells or ()),
        "target_size": len(target_cells or ()),
        "candidates": [],
        "shortlist": [],
        "consistency_relaxed": False,
        "candidate_set_hash": candidate_set_hash([]),
        "checks": [],
        "edges_before": set(),
        "universe": set(),
        "mandatory": set(),
        "variable": [],
    }


def choose_candidate(
    analysis: dict[str, Any],
    event_index: int,
    *,
    seed: int | None = None,
    attempt: int | None = None,
) -> dict[str, Any]:
    """The §4.5.6 seeded draw over the ranked shortlist."""
    if not analysis.get("ok") or not analysis.get("shortlist"):
        raise RerollError(
            str(analysis.get("reason") or "no_candidate"),
            f"{analysis.get('from_cell')} -> {analysis.get('to_cell')} has no shortlist",
        )
    if seed is None or attempt is None:
        raise RerollError("draw_invalid", "seed and attempt are required")
    threshold = str(analysis["threshold_id"])
    key = (
        f"{seed}:{attempt}:{event_index}:{EVENT_STREAM}:"
        f"{threshold}:{ALGORITHM_VERSION}:choose"
    )
    value = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)
    index = value % len(analysis["shortlist"])
    return {
        "value": value,
        "index": index,
        "chosen_rank": index + 1,
        "chosen": analysis["shortlist"][index],
        "purpose": f"{ALGORITHM_VERSION}:choose",
    }


def plan_reroll(
    document: dict[str, Any],
    from_cell: str,
    to_cell: str,
    event_index: int,
    *,
    seed: int | None = None,
    attempt: int | None = None,
    reroll_index: int = 1,
    exit_cell: str | None = None,
    visible_cells: set[str] | None = None,
    state: dict[tuple[str, str], dict[str, Any]] | None = None,
    algorithm_version: str = ALGORITHM_VERSION,
) -> dict[str, Any]:
    """Enumerate, rank, shortlist and draw one re-roll."""
    analysis = analyze_target(
        document,
        from_cell,
        to_cell,
        reroll_index=reroll_index,
        exit_cell=exit_cell,
        visible_cells=visible_cells,
        state=state,
        algorithm_version=algorithm_version,
    )
    if not analysis["ok"]:
        return analysis
    draw = choose_candidate(
        analysis,
        event_index,
        seed=int(document["seed"]) if seed is None else seed,
        attempt=int(document.get("attempt", 0)) if attempt is None else attempt,
    )
    analysis = copy.deepcopy(analysis)
    analysis["draw"] = draw
    analysis["chosen"] = draw["chosen"]
    analysis["chosen_rank"] = draw["chosen_rank"]
    return analysis


def _keyed_uniform(
    seed: int,
    attempt: int,
    event_index: int,
    threshold: str,
    cell_a: str,
    cell_b: str,
) -> float:
    key = (
        f"{seed}:{attempt}:{event_index}:{DOORWAY_STREAM}:{threshold}:{cell_a}:{cell_b}"
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:13]
    return int(digest, 16) / float(16**13)


def doorway_records(
    document: dict[str, Any],
    analysis: dict[str, Any],
    event_index: int,
) -> list[dict[str, Any]]:
    """Pure doorway metadata for every changed shared wall; no runtime geometry."""
    cells = cells_by_id(document)
    passages_before = analysis["edges_before"]
    passages_after = analysis["chosen"]["passages"]
    seed = int(document["seed"])
    attempt = int(document.get("attempt", 0))
    threshold = str(analysis["threshold_id"])
    records: list[dict[str, Any]] = []
    for pair in sorted(passages_after ^ passages_before):
        cell_a, cell_b = pair
        if pair in passages_before:
            records.append({"cell_a": cell_a, "cell_b": cell_b, "action": "closed"})
            continue
        wall = shared_wall(cells[cell_a], cells[cell_b])
        if wall is None or wall["length_m"] + 1e-9 < MIN_SHARED_WALL_M:
            raise RerollError(
                "geometry_conflict", f"{cell_a}-{cell_b} has no doorway span"
            )
        low = wall["start"] + DOORWAY_MARGIN_M + DOOR_WIDTH_M / 2
        high = wall["end"] - DOORWAY_MARGIN_M - DOOR_WIDTH_M / 2
        if low > high + 1e-9:
            raise RerollError(
                "geometry_conflict", f"{cell_a}-{cell_b} is too short for a doorway"
            )
        along = _keyed_uniform(seed, attempt, event_index, threshold, cell_a, cell_b)
        center = min(max(wall["start"] + along * wall["length_m"], low), high)
        center_xz = (
            [round(wall["line"], 6), round(center, 6)]
            if wall["axis"] == "x"
            else [round(center, 6), round(wall["line"], 6)]
        )
        records.append(
            {
                "cell_a": cell_a,
                "cell_b": cell_b,
                "action": "opened",
                "center_xz": center_xz,
                "width_m": DOOR_WIDTH_M,
                "height_m": DOOR_HEIGHT_M,
            }
        )
    return records


def rewire_block(
    document: dict[str, Any],
    analysis: dict[str, Any],
    event_index: int,
) -> dict[str, Any]:
    """The §4.5.8 event payload for one accepted re-roll."""
    chosen = analysis["chosen"]
    doorways = doorway_records(document, analysis, event_index)
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "target_cells": list(analysis["target_cells"]),
        "root_cell_id": analysis["root_cell_id"],
        "threshold_id": analysis["threshold_id"],
        "passages_before": _pair_list(analysis["edges_before"]),
        "passages_after": _pair_list(chosen["passages"]),
        "pinned_passages": _pair_list(analysis["mandatory"]),
        "doorways": doorways,
        "edit_distance": chosen["edit_distance"],
        "retained_fraction": chosen["retained_fraction"],
        "shape_before": _shape_payload(analysis["shape_before"]),
        "shape_after": _shape_payload(chosen["shape"]),
        "shape_score": chosen["shape_score"],
        "candidate_count": len(analysis["candidates"]),
        "shortlist_size": len(analysis["shortlist"]),
        "chosen_rank": analysis["chosen_rank"],
        "consistency_relaxed": analysis["consistency_relaxed"],
        "candidate_set_hash": analysis["candidate_set_hash"],
    }


def _pair_list(passages: set[tuple[str, str]]) -> list[list[str]]:
    return [[left, right] for left, right in sorted(passages)]


def _shape_payload(shape: dict[str, Any]) -> dict[str, Any]:
    return {
        "leaves": shape["leaves"],
        "loops": shape["loops"],
        "degree_histogram": {
            str(key): shape["degree_histogram"][key]
            for key in sorted(shape["degree_histogram"])
        },
        "max_depth": shape["max_depth"],
        "mean_depth": shape["mean_depth"],
        "door_count": shape["door_count"],
    }


def rewire_event_spec(
    base: mm.BaseMap,
    plan: dict[str, Any],
    event_index: int,
    *,
    reroll_serial: int = 1,
    visibility: dict[str, Any] | None = None,
    occurred_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the sealed-ready ``door_reroll`` mutation for an accepted plan."""
    if not plan.get("ok"):
        raise RerollError(
            str(plan.get("reason") or "no_candidate"),
            "a rejected plan cannot produce an accepted event",
        )
    draw = plan["draw"]
    target = {
        "cell_id": plan["root_cell_id"],
        "port_id": plan["threshold_id"],
        "threshold_id": plan["threshold_id"],
        "branch_root": plan["root_cell_id"],
        "door_threshold_id": plan["door_threshold_id"],
        "from_cell": plan["from_cell"],
        "to_cell": plan["to_cell"],
    }
    return mm.new_mutation(
        base,
        "door_reroll",
        event_index,
        target=target,
        stream=EVENT_STREAM,
        rewire=rewire_block(base.document, plan, event_index),
        draw={
            "purpose": draw["purpose"],
            "value": draw["value"],
            "reroll_serial": reroll_serial,
            "branch_attempt": plan["chosen_rank"],
        },
        validation={
            "outcome": "accepted",
            "checks": list(plan.get("checks", HARD_CHECKS)),
        },
        visibility=visibility,
        occurred_at_utc=occurred_at_utc,
    )


def rejected_rewire_event_spec(
    base: mm.BaseMap,
    plan: dict[str, Any],
    event_index: int,
    *,
    occurred_at_utc: str | None = None,
) -> dict[str, Any]:
    """A fail-closed attempt; it changes no passage and never latches a door."""
    reason = str(plan.get("reason") or "no_candidate")
    rewire = {
        "algorithm_version": ALGORITHM_VERSION,
        "target_cells": list(plan.get("target_cells", [])),
        "root_cell_id": plan.get("root_cell_id", plan.get("from_cell", "")),
        "threshold_id": plan.get("threshold_id", ""),
        "passages_before": _pair_list(plan.get("edges_before", set())),
        "candidate_count": len(plan.get("candidates", [])),
        "shortlist_size": len(plan.get("shortlist", [])),
        "consistency_relaxed": bool(plan.get("consistency_relaxed", False)),
        "candidate_set_hash": plan.get("candidate_set_hash", candidate_set_hash([])),
    }
    target = {
        "cell_id": str(plan.get("root_cell_id") or plan.get("from_cell", "")),
        "port_id": str(plan.get("threshold_id", "")),
        "threshold_id": str(plan.get("threshold_id", "")),
        "branch_root": str(plan.get("root_cell_id") or plan.get("from_cell", "")),
        "door_threshold_id": str(plan.get("door_threshold_id", "")),
        "from_cell": str(plan.get("from_cell", "")),
        "to_cell": str(plan.get("to_cell", "")),
    }
    if not target["threshold_id"]:
        target["threshold_id"] = door_threshold_id(
            target["from_cell"], target["to_cell"]
        )
        target["port_id"] = target["threshold_id"]
    return mm.new_mutation(
        base,
        "door_reroll",
        event_index,
        target=target,
        stream=EVENT_STREAM,
        rewire=rewire,
        validation={
            "outcome": "rejected",
            "reason": reason,
            "checks": [reason],
        },
        occurred_at_utc=occurred_at_utc,
    )


def direction_report(
    document: dict[str, Any],
    from_cell: str,
    to_cell: str,
    *,
    exit_cell: str | None = None,
    reroll_index: int = 1,
    state: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compact structural record for the five-seed golden fixture."""
    analysis = analyze_target(
        document,
        from_cell,
        to_cell,
        reroll_index=reroll_index,
        exit_cell=exit_cell,
        state=state,
    )
    edits = sorted(candidate["edit_distance"] for candidate in analysis["candidates"])
    return {
        "threshold_id": analysis.get("threshold_id", ""),
        "door_threshold_id": analysis.get("door_threshold_id", ""),
        "from_cell": from_cell,
        "to_cell": to_cell,
        "target_cells": analysis.get("target_cells", []),
        "target_size": analysis.get("target_size", 0),
        "spawn_in_target": bool(analysis.get("spawn_in_target", False)),
        "h_universe": _pair_list(analysis.get("universe", set())),
        "mandatory_passages": _pair_list(analysis.get("mandatory", set())),
        "variable_count": len(analysis.get("variable", [])),
        "hard_valid": len(analysis.get("candidates", [])),
        "in_tolerance": sum(
            1
            for candidate in analysis.get("candidates", [])
            if candidate["shape_violations"] == 0
        ),
        "shortlist_size": len(analysis.get("shortlist", [])),
        "consistency_relaxed": bool(analysis.get("consistency_relaxed", False)),
        "edit_range": [edits[0], edits[-1]] if edits else [],
        "reason": analysis.get("reason", ""),
    }


def enumerate_directions(
    document: dict[str, Any],
    *,
    exit_cell: str | None = None,
    reroll_index: int = 1,
    state: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Every bridge direction whose departed component is 3-8 cells."""
    current = (
        _normalize_state(state) if state is not None else base_passage_state(document)
    )
    reports: list[dict[str, Any]] = []
    for left, right in sorted(
        {_pair(*pair) for pair in current if current[pair].get("vertical") != "drop"}
    ):
        for from_cell, to_cell in ((left, right), (right, left)):
            target = target_component(current, from_cell, to_cell)
            if (
                target is None
                or not MIN_REROLL_CELLS <= len(target) <= MAX_REROLL_CELLS
            ):
                continue
            reports.append(
                direction_report(
                    document,
                    from_cell,
                    to_cell,
                    exit_cell=exit_cell,
                    reroll_index=reroll_index,
                    state=current,
                )
            )
    reports.sort(key=lambda item: (item["from_cell"], item["to_cell"]))
    return reports


def _candidate_projection(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "passages_after": _pair_list(candidate["passages"]),
        "edit_distance": candidate["edit_distance"],
        "retained_milli": round(candidate["retained_fraction"] * 1000),
        "shape": _shape_projection(candidate["shape"]),
        "shape_violations": candidate["shape_violations"],
        "shape_score_micro": round(candidate["shape_score"] * 1_000_000),
    }


def _shape_projection(shape: dict[str, Any]) -> dict[str, Any]:
    return {
        "leaves": shape["leaves"],
        "loops": shape["loops"],
        "max_depth": shape["max_depth"],
        "mean_depth_milli": round(shape["mean_depth"] * 1000),
        "door_count": shape["door_count"],
        "degree_histogram": [
            [degree, count]
            for degree, count in sorted(shape["degree_histogram"].items())
        ],
    }


def projection(plan: dict[str, Any]) -> dict[str, Any]:
    """Cross-language contract used by the GDScript parity test."""
    return {
        "ok": bool(plan.get("ok")),
        "reason": str(plan.get("reason") or ""),
        "target_cells": list(plan.get("target_cells", [])),
        "root_cell_id": str(plan.get("root_cell_id", "")),
        "threshold_id": str(plan.get("threshold_id", "")),
        "door_threshold_id": str(plan.get("door_threshold_id", "")),
        "h_universe": _pair_list(plan.get("universe", set())),
        "mandatory_passages": _pair_list(plan.get("mandatory", set())),
        "variable_count": len(plan.get("variable", [])),
        "passages_before": _pair_list(plan.get("edges_before", set())),
        "pinned_passages": _pair_list(plan.get("mandatory", set())),
        "candidate_count": len(plan.get("candidates", [])),
        "in_tolerance_count": sum(
            1
            for candidate in plan.get("candidates", [])
            if candidate["shape_violations"] == 0
        ),
        "shortlist_size": len(plan.get("shortlist", [])),
        "consistency_relaxed": bool(plan.get("consistency_relaxed", False)),
        "shape_before": _shape_projection(plan["shape_before"])
        if "shape_before" in plan
        else {},
        "shortlist": [
            _candidate_projection(candidate) for candidate in plan.get("shortlist", [])
        ],
        "chosen": _candidate_projection(plan["chosen"]) if plan.get("chosen") else None,
        "chosen_rank": int(plan.get("chosen_rank", 0)),
        "candidate_set_hash": str(plan.get("candidate_set_hash", "")),
    }


def build_fixture() -> dict[str, Any]:
    """The committed five-seed golden fixture and parity cases."""
    maps: dict[str, Any] = {}
    for seed in SEEDS:
        path = (
            ROOT
            / "godot_walk/room_catalog/generative_maps"
            / (f"gmap-{seed}-gmap-0.13.0.json")
        )
        document = json.loads(path.read_text(encoding="utf-8"))
        directions = enumerate_directions(document)
        pool_directions = [
            item
            for item in directions
            if item["in_tolerance"] >= MIN_REROLL_ALTERNATIVES
        ]
        spawn_pinned_pools = [
            item for item in pool_directions if not item["spawn_in_target"]
        ]
        maps[str(seed)] = {
            "map_id": str(document["map_id"]),
            "seed": seed,
            "attempt": int(document.get("attempt", 0)),
            "spawn_cell_id": spawn_cell_id(document),
            "directions": directions,
            "direction_count": len(directions),
            "directions_with_pool": len(pool_directions),
            "spawn_pinned_pool_directions": len(spawn_pinned_pools),
        }
    seed32 = json.loads(
        (
            ROOT / "godot_walk/room_catalog/generative_maps/gmap-32-gmap-0.13.0.json"
        ).read_text(encoding="utf-8")
    )
    seed279 = json.loads(
        (
            ROOT / "godot_walk/room_catalog/generative_maps/gmap-279-gmap-0.13.0.json"
        ).read_text(encoding="utf-8")
    )
    worked = plan_reroll(seed32, "c01", "c00", 1)
    rich = plan_reroll(seed279, "c02", "c11", 1)
    names = {
        candidate["key"]: f"C{index}"
        for index, candidate in enumerate(worked["candidates"], start=1)
    }
    worked_rows = []
    for candidate in worked["candidates"]:
        worked_rows.append(
            {
                "name": names[candidate["key"]],
                "passages_after": _pair_list(candidate["passages"]),
                "edit_distance": candidate["edit_distance"],
                "retained_milli": round(candidate["retained_fraction"] * 1000),
                "shape": _shape_projection(candidate["shape"]),
                "shape_violations": candidate["shape_violations"],
                "in_shortlist": candidate in worked["shortlist"],
            }
        )
    parity_cases = []
    for name, document, from_cell, to_cell in (
        ("seed32_worked_example", seed32, "c01", "c00"),
        ("seed32_spawn_island", seed32, "c00", "c01"),
        ("seed279_rich", seed279, "c02", "c11"),
        ("seed279_spawn_island", seed279, "c11", "c02"),
        ("seed279_ramp_door", seed279, "c06", "c11"),
        (
            "seed1_no_candidate",
            json.loads(
                (
                    ROOT
                    / "godot_walk/room_catalog/generative_maps/gmap-1-gmap-0.13.0.json"
                ).read_text(encoding="utf-8")
            ),
            "c05",
            "c03",
        ),
    ):
        parity_cases.append(
            {
                "name": name,
                "map_id": str(document["map_id"]),
                "from_cell": from_cell,
                "to_cell": to_cell,
                "event_index": 1,
                "expected": projection(plan_reroll(document, from_cell, to_cell, 1)),
            }
        )
    return {
        "description": (
            "M5 rewire-1 five-seed golden fixture and Python/GDScript parity cases."
        ),
        "layer_version": f"reroll:{ALGORITHM_VERSION}",
        "algorithm_version": ALGORITHM_VERSION,
        "stream": EVENT_STREAM,
        "parameters": {
            "min_reroll_cells": MIN_REROLL_CELLS,
            "max_reroll_cells": MAX_REROLL_CELLS,
            "max_degree": MAX_DEGREE,
            "min_shared_wall_m": MIN_SHARED_WALL_M,
            "min_retained": MIN_RETAINED,
            "candidate_shortlist": CANDIDATE_SHORTLIST,
            "min_reroll_alternatives": MIN_REROLL_ALTERNATIVES,
            "max_rerolls_per_run": MAX_REROLLS_PER_RUN,
            "max_rerolls_per_door": MAX_REROLLS_PER_DOOR,
            "tiers": {str(key): list(value) for key, value in TIERS.items()},
            "shape_tolerances": {
                str(key): value for key, value in SHAPE_TOLERANCES.items()
            },
        },
        "summary": {
            "directions": sum(item["direction_count"] for item in maps.values()),
            "directions_with_pool": sum(
                item["directions_with_pool"] for item in maps.values()
            ),
            "spawn_pinned_pool_directions": sum(
                item["spawn_pinned_pool_directions"] for item in maps.values()
            ),
            "seed_3_directions": maps["3"]["direction_count"],
            "seed_279_rich_hard": len(rich["candidates"]),
            "seed_279_rich_in_tolerance": sum(
                1
                for candidate in rich["candidates"]
                if candidate["shape_violations"] == 0
            ),
        },
        "maps": maps,
        "worked_example": {
            "seed": 32,
            "from_cell": "c01",
            "to_cell": "c00",
            "event_index": 1,
            "threshold_id": worked["threshold_id"],
            "door_threshold_id": worked["door_threshold_id"],
            "candidates": worked_rows,
            "shortlist": [names[candidate["key"]] for candidate in worked["shortlist"]],
            "chosen": names[worked["chosen"]["key"]],
            "chosen_rank": worked["chosen_rank"],
            "consistency_relaxed": worked["consistency_relaxed"],
            "projection": projection(worked),
        },
        "seed_279_rich": projection(rich),
        "parity_cases": parity_cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fixture_parser = commands.add_parser("fixture", help="print the golden fixture")
    fixture_parser.add_argument("--out", help="write the fixture to this path")
    plan_parser = commands.add_parser("plan", help="plan one direction")
    plan_parser.add_argument("--map", required=True)
    plan_parser.add_argument("--from", dest="from_cell", required=True)
    plan_parser.add_argument("--to", dest="to_cell", required=True)
    plan_parser.add_argument("--event-index", type=int, default=1)
    args = parser.parse_args(argv)
    if args.command == "plan":
        document = json.loads(Path(args.map).read_text(encoding="utf-8"))
        result = plan_reroll(document, args.from_cell, args.to_cell, args.event_index)
        print(json.dumps(projection(result), indent=2, sort_keys=True))
        return 0 if result.get("ok") else 2
    fixture = build_fixture()
    payload = canonical_bytes(fixture)
    if args.out:
        Path(args.out).write_bytes(payload)
    else:
        sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
