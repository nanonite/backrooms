"""Deterministic map-driven light assignment for gmap-0.8.0 (#198)."""

from __future__ import annotations

import hashlib
import random
from collections import deque
from copy import deepcopy
from typing import Any

from gmap_library import Library

RULE = "light_layer"
STREAM = "light:gmap-0.8.0"
DARK_WING_PROBABILITY = 0.35
LAMP_STATE_BUCKETS = ((80, "on"), (92, "flicker"), (100, "dead"))
TIER_WEIGHTS = ((15, "dim"), (85, "normal"), (100, "bright"))
TEMPERATURE_RANGE_K = (3800, 5200)


def rng_for(seed: int, attempt: int) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{attempt}:{STREAM}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big"))


def _module_roles(library: Library) -> dict[tuple[str, int], str | None]:
    return {(item.module_id, item.version): item.form_role for item in library.modules}


def _graph(document: dict[str, Any]) -> dict[str, set[str]]:
    walkable = {cell["cell_id"] for cell in document["cells"] if cell["role"] != "void"}
    graph = {cell_id: set() for cell_id in walkable}
    for edge in document["edges"]:
        if edge["connector"] != "direct":
            continue
        left, right = edge["from"].split(":")[0], edge["to"].split(":")[0]
        if left in graph and right in graph:
            graph[left].add(right)
            graph[right].add(left)
    return graph


def _eligible_cells(document: dict[str, Any]) -> set[str]:
    return {
        cell["cell_id"]
        for cell in document["cells"]
        if cell["role"] != "void"
        and not cell.get("module")
        and not cell.get("landmark")
        and not cell.get("diagonal_passage")
        and cell["cell_id"] != document["cells"][0]["cell_id"]
    }


def _draw_dark_wing(document: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    if rng.random() >= DARK_WING_PROBABILITY:
        return {"status": "not_selected", "cell_ids": []}
    eligible, graph = _eligible_cells(document), _graph(document)
    starts = sorted(cell_id for cell_id in eligible if graph[cell_id] & eligible)
    if not starts:
        return {
            "status": "unavailable",
            "cell_ids": [],
            "reason": "no_connected_candidate_pair",
        }
    target_size = rng.choice((2, 3))
    start = rng.choice(starts)
    chosen = [start]
    while len(chosen) < target_size:
        frontier = sorted(
            (set().union(*(graph[cell] for cell in chosen)) & eligible) - set(chosen)
        )
        if not frontier:
            break
        chosen.append(rng.choice(frontier))
    if len(chosen) < 2:
        return {
            "status": "unavailable",
            "cell_ids": [],
            "reason": "no_connected_candidate_pair",
        }
    return {"status": "placed", "cell_ids": sorted(chosen)}


def _library_joint_cells(document: dict[str, Any], library: Library) -> set[str]:
    roles = _module_roles(library)
    figures = {
        cell["cell_id"]
        for cell in document["cells"]
        if cell.get("module")
        and roles.get((cell["module"]["module_id"], cell["module"]["version"]))
        == "figure"
    }
    graph = _graph(document)
    return (
        set().union(*(graph.get(cell_id, set()) for cell_id in figures))
        if figures
        else set()
    )


def _lamp_counts(document: dict[str, Any]) -> dict[str, int]:
    """Use the authoritative shape builder so map indices match generated lamp positions."""
    from shape_room import edge_links
    from shape_room_spec import build_spec

    links = edge_links(document)
    counts = {}
    for cell in document["cells"]:
        if cell["role"] == "void" or cell.get("module"):
            continue
        spec = build_spec(document, "0" * 64, cell, "shape_room_pending", links)
        counts[cell["cell_id"]] = len(spec["lamps_xz"])
    return counts


def _draw_weighted(rng: random.Random, buckets: tuple[tuple[int, str], ...]) -> str:
    draw = rng.randrange(100)
    return next(label for limit, label in buckets if draw < limit)


def _cell_light(
    rng: random.Random,
    count: int,
    tier: str,
    landmark: bool,
    dark_wing: bool,
) -> dict[str, Any]:
    states = [
        "on" if landmark else _draw_weighted(rng, LAMP_STATE_BUCKETS)
        for _ in range(count)
    ]
    if dark_wing and count:
        dead_count = count // 2 + 1
        for lamp_index in rng.sample(range(count), dead_count):
            states[lamp_index] = "dead"
    lamps = [
        {
            "lamp_index": lamp_index,
            "state": state,
            "flicker_seed": rng.randrange(1 << 31),
        }
        for lamp_index, state in enumerate(states)
    ]
    return {
        "tier": tier,
        "color_temp_k": rng.randint(*TEMPERATURE_RANGE_K),
        "lamps": lamps,
    }


def assign_light(document: dict[str, Any], library: Library) -> None:
    """Attach the v0.8 light layer without consuming any geometry/layout RNG stream."""
    rng = rng_for(document["seed"], document.get("attempt", 0))
    dark_wing = _draw_dark_wing(document, rng)
    wing = set(dark_wing["cell_ids"])
    near_library = _library_joint_cells(document, library)
    counts = _lamp_counts(document)
    for cell in sorted(document["cells"], key=lambda item: item["cell_id"]):
        if cell["role"] == "void":
            continue
        landmark = bool(cell.get("landmark"))
        is_spawn = cell["cell_id"] == document["cells"][0]["cell_id"]
        tier = _draw_weighted(rng, TIER_WEIGHTS)
        if landmark or cell["cell_id"] in near_library:
            tier = "bright"
        if is_spawn and tier == "dim":
            tier = "normal"
        if cell["cell_id"] in wing:
            tier = "dim"
        cell["light"] = _cell_light(
            rng, counts.get(cell["cell_id"], 0), tier, landmark, cell["cell_id"] in wing
        )
    document["dark_wing"] = dark_wing


def _light_graph_connected(cell_ids: list[str], graph: dict[str, set[str]]) -> bool:
    allowed = set(cell_ids)
    if not allowed or not allowed <= graph.keys():
        return False
    visited = {cell_ids[0]}
    queue = deque([cell_ids[0]])
    while queue:
        current = queue.popleft()
        for neighbor in sorted((graph[current] & allowed) - visited):
            visited.add(neighbor)
            queue.append(neighbor)
    return visited == allowed


def light_errors(document: dict[str, Any], library: Library) -> list[dict[str, str]]:
    """Check deterministic state, graph constraints, and authoritative lamp coverage."""
    expected = deepcopy(document)
    for cell in expected["cells"]:
        cell.pop("light", None)
    expected.pop("dark_wing", None)
    assign_light(expected, library)
    errors: list[dict[str, str]] = []
    if document.get("dark_wing") != expected["dark_wing"]:
        errors.append(
            _error("dark_wing_mismatch", "dark wing differs from its named stream")
        )
    expected_by_id = {cell["cell_id"]: cell for cell in expected["cells"]}
    graph = _graph(document)
    wing = document.get("dark_wing", {}).get("cell_ids", [])
    by_id = {cell["cell_id"]: cell for cell in document["cells"]}
    unknown = sorted(set(wing) - set(by_id))
    if unknown:
        errors.append(
            _error("dark_wing_unknown_cell", "unknown cell IDs: " + ", ".join(unknown))
        )
    elif wing and not _light_graph_connected(wing, graph):
        errors.append(_error("dark_wing_not_connected", ", ".join(wing)))
    spawn_id = document["cells"][0]["cell_id"]
    for cell_id in wing:
        cell = by_id.get(cell_id, {})
        if (
            cell_id == spawn_id
            or cell.get("landmark")
            or cell.get("module")
            or cell.get("role") == "void"
        ):
            errors.append(_error("dark_wing_ineligible_cell", cell_id))
    if spawn_id in wing:
        errors.append(_error("dark_wing_contains_spawn", spawn_id))
    for cell in document["cells"]:
        if cell["role"] == "void":
            if "light" in cell:
                errors.append(_error("void_has_light", cell["cell_id"]))
            continue
        actual, wanted = cell.get("light"), expected_by_id[cell["cell_id"]].get("light")
        if actual != wanted:
            errors.append(_error("light_assignment_mismatch", cell["cell_id"]))
        if actual is None:
            continue
        if cell.get("landmark") and any(
            lamp["state"] != "on" for lamp in actual.get("lamps", [])
        ):
            errors.append(_error("landmark_lamp_not_on", cell["cell_id"]))
        if cell["cell_id"] == spawn_id and actual.get("tier") == "dim":
            errors.append(_error("spawn_is_dark", spawn_id))
        if cell["cell_id"] in wing and actual.get("tier") != "dim":
            errors.append(_error("dark_wing_tier", cell["cell_id"]))
        if cell["cell_id"] in wing and actual.get("lamps"):
            dead = sum(lamp["state"] == "dead" for lamp in actual["lamps"])
            if dead <= len(actual["lamps"]) / 2:
                errors.append(
                    _error("dark_wing_lamps_not_mostly_dead", cell["cell_id"])
                )
    return errors


def _error(code: str, message: str) -> dict[str, str]:
    return {"rule": RULE, "code": code, "message": message}
