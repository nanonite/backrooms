"""Follower lamp edits, visibility gate and cadence wiring for the maze (#232).

M2 of the #223 overlay chain.  It builds on the M1 event core in
``maze_mutation`` and adds the cheapest visible edit class: one generated
room's lamp state or flicker seed.  The committed map is only ever read; the
edit lives in the overlay as a per-cell ``lamp_state``/``lamp_flicker`` record.

The scheduler is counted in distinct visited cells and reconstructed from the
trigger records, exactly as M1 defines it.  A beat only fires when the target
is outside ``visible_cells(player_cell)``; if no eligible hidden target exists,
the beat is dropped and no mutation event is logged.

This module is the headless reference.  ``maze_visibility.gd`` and
``maze_light_controller.gd`` are the runtime equivalents used by the assembly.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import maze_mutation as mm
import maze_surface as ms

RULE = "maze_follower"
STREAM = "follower:gmap-0.13.0"
LIGHT_LAYER_VERSION = "maze-light-0.1.0"
REVERB_LAYER_VERSION = "maze-reverb-0.1.0"

# Two doorway hops is the provisional cheap proxy for the out-of-sight rule
# (§5.3, §9.6).  It is deliberately conservative about what a doorway exposes,
# but it is not a camera test; the renderer backstop belongs to a later slice.
DEFAULT_VISIBILITY_DEPTH = 2

VISIBLE_CONNECTORS = frozenset({"direct", "closed_visible"})
VISIBLE_DOOR_STATES = frozenset({"open", "closed_visible"})
WALKABLE_ROLE = "ground"
VOID_ROLE = "void"

LAMP_STATES = ("on", "flicker", "dead")
LAMP_CLASSES = ("lamp_state", "lamp_flicker")
# §5.4 order for M8: the cheapest atmospheric edit first, then the M2 lamps,
# then the surface layers.  The provisional curve has no weights yet; the
# class is a uniform keyed draw over the feasible classes (M14 may tune it).
IMPLEMENTED_CLASSES = (
    "reverb",
    "lamp_state",
    "lamp_flicker",
    "wear",
    "surface_variant",
)
CLASS_DRAW_PURPOSE = "edit-class"
MAX_FLICKER_SEED = (1 << 31) - 1


class FollowerEditError(ValueError):
    """A follower edit or visibility input is malformed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class LampEditPlan:
    """One deterministic follower edit ready to become a mutation record."""

    target_cell: str
    change: dict[str, Any]
    draw: dict[str, Any]
    visibility: dict[str, Any]


@dataclass(frozen=True)
class FollowerEditPlan:
    """One M8 follower edit of any implemented class."""

    target_cell: str
    change: dict[str, Any]
    draw: dict[str, Any] | None
    visibility: dict[str, Any]


def _cells(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for cell in document.get("cells", []):
        if isinstance(cell, dict) and isinstance(cell.get("cell_id"), str):
            result[cell["cell_id"]] = cell
    return result


def _is_walkable(cell: dict[str, Any]) -> bool:
    return str(cell.get("role", WALKABLE_ROLE)) != VOID_ROLE


def _door_state(
    cell: dict[str, Any],
    port_id: str,
    door_states: dict[str, str] | None,
) -> str:
    if door_states is not None and port_id in door_states:
        return str(door_states[port_id])
    for door in cell.get("doors", []):
        if isinstance(door, dict) and str(door.get("port_id", "")) == port_id:
            return str(door.get("state", "open"))
    return "open"


def visible_adjacency(
    document: dict[str, Any], door_states: dict[str, str] | None = None
) -> dict[str, set[str]]:
    """Graph of openings the visibility proxy may look through."""
    cells = _cells(document)
    adjacency: dict[str, set[str]] = {
        cell_id: set() for cell_id, cell in cells.items() if _is_walkable(cell)
    }
    for edge in document.get("edges", []):
        if not isinstance(edge, dict):
            continue
        if str(edge.get("connector", "")) not in VISIBLE_CONNECTORS:
            continue
        from_port = str(edge.get("from", ""))
        to_port = str(edge.get("to", ""))
        left = from_port.partition(":")[0]
        right = to_port.partition(":")[0]
        if left not in adjacency or right not in adjacency or left == right:
            continue
        if _door_state(cells[left], from_port, door_states) not in VISIBLE_DOOR_STATES:
            continue
        if _door_state(cells[right], to_port, door_states) not in VISIBLE_DOOR_STATES:
            continue
        adjacency[left].add(right)
        adjacency[right].add(left)
    return adjacency


def traversal_adjacency(document: dict[str, Any]) -> dict[str, set[str]]:
    """Passable direct edges, used only for the degree preference."""
    cells = _cells(document)
    adjacency: dict[str, set[str]] = {
        cell_id: set() for cell_id, cell in cells.items() if _is_walkable(cell)
    }
    for edge in document.get("edges", []):
        if not isinstance(edge, dict) or edge.get("connector") != "direct":
            continue
        left = str(edge.get("from", "")).partition(":")[0]
        right = str(edge.get("to", "")).partition(":")[0]
        if left in adjacency and right in adjacency and left != right:
            adjacency[left].add(right)
            adjacency[right].add(left)
    return adjacency


def visible_cells(
    document: dict[str, Any],
    player_cell: str,
    *,
    depth: int = DEFAULT_VISIBILITY_DEPTH,
    door_states: dict[str, str] | None = None,
) -> list[str]:
    """Bounded graph walk through open and ``closed_visible`` openings."""
    if depth < 0:
        return []
    adjacency = visible_adjacency(document, door_states)
    if player_cell not in adjacency:
        return []
    seen = {player_cell}
    discovered = [player_cell]
    frontier = [player_cell]
    for _ in range(depth):
        next_frontier: list[str] = []
        for current in frontier:
            for neighbor in sorted(adjacency[current]):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                discovered.append(neighbor)
                next_frontier.append(neighbor)
        frontier = next_frontier
        if not frontier:
            break
    return sorted(discovered)


def cell_is_hidden(
    document: dict[str, Any],
    player_cell: str,
    target_cell: str,
    *,
    depth: int = DEFAULT_VISIBILITY_DEPTH,
    door_states: dict[str, str] | None = None,
) -> bool:
    """True when the target is not the current cell and is out of the proxy view."""
    if not target_cell or target_cell == player_cell:
        return False
    return target_cell not in visible_cells(
        document, player_cell, depth=depth, door_states=door_states
    )


def _lamps(cell: dict[str, Any]) -> list[dict[str, Any]]:
    light = cell.get("light")
    if not isinstance(light, dict):
        return []
    lamps = light.get("lamps")
    if not isinstance(lamps, list):
        return []
    return [lamp for lamp in lamps if isinstance(lamp, dict)]


def _lamp_index(lamp: dict[str, Any]) -> int:
    value = lamp.get("lamp_index")
    if type(value) is not int or value < 0:
        raise FollowerEditError("lamp_invalid", "lamp_index is not a non-negative int")
    return value


def lamp_state_record(cell: dict[str, Any]) -> list[dict[str, int | str]]:
    """The per-cell lamp state list used by the ``lamp_state`` override."""
    record = [
        {"lamp_index": _lamp_index(lamp), "state": str(lamp.get("state", "on"))}
        for lamp in _lamps(cell)
    ]
    return sorted(record, key=lambda entry: int(entry["lamp_index"]))


def lamp_flicker_record(cell: dict[str, Any]) -> list[dict[str, int]]:
    """The per-cell flicker-seed list used by the ``lamp_flicker`` override."""
    record = [
        {
            "lamp_index": _lamp_index(lamp),
            "flicker_seed": int(lamp.get("flicker_seed", 0)),
        }
        for lamp in _lamps(cell)
    ]
    return sorted(record, key=lambda entry: int(entry["lamp_index"]))


def light_eligible_cells(document: dict[str, Any]) -> set[str]:
    """Generated cells a lamp edit may rewrite (never module or landmark cells)."""
    return {
        cell_id
        for cell_id, cell in _cells(document).items()
        if _is_walkable(cell)
        and not cell.get("module")
        and not cell.get("landmark")
        and bool(_lamps(cell))
    }


def _record_entries(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise FollowerEditError("override_invalid", f"{field} override is not a list")
    entries: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise FollowerEditError("override_invalid", f"{field} entry is not an object")
        entries.append(entry)
    return entries


def effective_lamp_states(
    base: mm.BaseMap, overlay: dict[str, Any], cell_id: str
) -> list[dict[str, int | str]]:
    """Base lamp records with the folded ``lamp_state``/``lamp_flicker`` overlay."""
    cells = _cells(base.document)
    if cell_id not in cells:
        raise FollowerEditError("unknown_cell", f"cell {cell_id} is not in the base map")
    lamps = {
        _lamp_index(lamp): {
            "lamp_index": _lamp_index(lamp),
            "state": str(lamp.get("state", "on")),
            "flicker_seed": int(lamp.get("flicker_seed", 0)),
        }
        for lamp in _lamps(cells[cell_id])
    }
    override = overlay.get("cell_overrides", {}).get(cell_id, {})
    if not isinstance(override, dict):
        raise FollowerEditError("override_invalid", f"cell {cell_id} override is not an object")
    for entry in _record_entries(override.get("lamp_state", []), "lamp_state"):
        index = entry.get("lamp_index")
        state = entry.get("state")
        if type(index) is not int or index not in lamps:
            raise FollowerEditError("override_invalid", f"unknown lamp {index}")
        if state not in LAMP_STATES:
            raise FollowerEditError("override_invalid", f"unknown lamp state {state}")
        lamps[index]["state"] = str(state)
    for entry in _record_entries(override.get("lamp_flicker", []), "lamp_flicker"):
        index = entry.get("lamp_index")
        seed = entry.get("flicker_seed")
        if type(index) is not int or index not in lamps:
            raise FollowerEditError("override_invalid", f"unknown lamp {index}")
        if type(seed) is not int or seed < 0:
            raise FollowerEditError("override_invalid", f"invalid flicker seed {seed}")
        lamps[index]["flicker_seed"] = int(seed)
    return [lamps[index] for index in sorted(lamps)]


def _override_value(
    overlay: dict[str, Any], cell_id: str, change_class: str, fallback: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    override = overlay.get("cell_overrides", {}).get(cell_id, {})
    if isinstance(override, dict) and change_class in override:
        value = override[change_class]
        if isinstance(value, list):
            return copy.deepcopy(value)
    return copy.deepcopy(fallback)


def last_edited_cell(events: Iterable[dict[str, Any]]) -> str | None:
    """The most recent accepted follower-edit target, if any."""
    result: str | None = None
    for event in events:
        if not isinstance(event, dict) or event.get("record_kind") != "mutation":
            continue
        if event.get("event_type") != "follower_edit":
            continue
        if mm._event_outcome(event) != "accepted":
            continue
        target = event.get("target")
        if isinstance(target, dict) and isinstance(target.get("cell_id"), str):
            result = target["cell_id"]
    return result


def _ranked_target(
    base: mm.BaseMap,
    events: list[dict[str, Any]],
    candidates: Iterable[str],
    *,
    event_index: int,
    stream: str,
) -> str | None:
    """Keyed rank: passed 1-3 rooms ago, then degree 2+, then the draw."""
    candidate_list = list(candidates)
    if not candidate_list:
        return None
    visited = mm.visited_cells(events)
    position = {cell_id: index for index, cell_id in enumerate(visited)}
    degrees = traversal_adjacency(base.document)

    def rank(cell_id: str) -> tuple[int, int, int]:
        age = len(visited) - 1 - position.get(cell_id, 0)
        recent = 0 if 1 <= age <= 3 else 1
        degree = 0 if len(degrees.get(cell_id, set())) >= 2 else 1
        keyed = mm.draw_for_event(
            base.seed,
            base.attempt,
            event_index,
            stream,
            cell_id,
            "target",
        )
        return recent, degree, keyed

    return min(candidate_list, key=rank)


def select_lamp_target(
    base: mm.BaseMap,
    overlay: dict[str, Any],
    events: Iterable[dict[str, Any]],
    *,
    player_cell: str,
    event_index: int,
    exit_cell: str | None = None,
    visibility_depth: int = DEFAULT_VISIBILITY_DEPTH,
    door_states: dict[str, str] | None = None,
    stream: str = STREAM,
) -> str | None:
    """Pick the hidden, previously visited cell for one lamp edit.

    Preference order is: passed 1-3 rooms ago, degree 2 or more, then a stable
    keyed rank.  Spawn, exit, current, module, landmark, the last edited cell
    and every visible cell are excluded.
    """
    event_list = list(events)
    document = base.document
    cells = _cells(document)
    visited = mm.visited_cells(event_list)
    if not visited:
        return None
    spawn = str(document["cells"][0]["cell_id"])
    eligible = light_eligible_cells(document)
    if exit_cell is not None:
        eligible.discard(exit_cell)
    last_edited = last_edited_cell(event_list)
    visible = set(
        visible_cells(
            document,
            player_cell,
            depth=visibility_depth,
            door_states=door_states,
        )
    )
    candidates = [
        cell_id
        for cell_id in visited
        if cell_id != player_cell
        and cell_id != spawn
        and cell_id != last_edited
        and cell_id in eligible
        and cell_id not in visible
        and cell_id in cells
    ]
    return _ranked_target(
        base, event_list, candidates, event_index=event_index, stream=stream
    )


def _choose_lamp_edit(
    base: mm.BaseMap,
    overlay: dict[str, Any],
    *,
    target_cell: str,
    event_index: int,
    stream: str,
    force_class: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cell = _cells(base.document)[target_cell]
    lamps = _lamps(cell)
    if not lamps:
        raise FollowerEditError("lamp_missing", f"cell {target_cell} has no lamps")
    states_before = _override_value(
        overlay, target_cell, "lamp_state", lamp_state_record(cell)
    )
    flicker_before = _override_value(
        overlay, target_cell, "lamp_flicker", lamp_flicker_record(cell)
    )
    by_index = {int(entry["lamp_index"]): entry for entry in states_before}
    indices = sorted(by_index)
    value = mm.draw_for_event(
        base.seed, base.attempt, event_index, stream, target_cell, "lamp-edit"
    )
    classes = [force_class] if force_class is not None else list(LAMP_CLASSES)
    if any(change_class not in LAMP_CLASSES for change_class in classes):
        raise FollowerEditError("change_class_invalid", str(force_class))
    change_class = classes[value % len(classes)]
    if change_class == "lamp_flicker":
        flickering = [
            index for index in indices if by_index[index]["state"] == "flicker"
        ]
        if not flickering:
            change_class = "lamp_state"
            classes = ["lamp_state"]
        else:
            lamp_index = flickering[(value >> 8) % len(flickering)]
    if change_class == "lamp_state":
        lamp_index = indices[(value >> 8) % len(indices)]
        current_state = str(by_index[lamp_index]["state"])
        alternatives = [state for state in LAMP_STATES if state != current_state]
        next_state = alternatives[(value >> 24) % len(alternatives)]
        after_states = copy.deepcopy(states_before)
        for entry in after_states:
            if int(entry["lamp_index"]) == lamp_index:
                entry["state"] = next_state
        change = mm.change_block(
            "lamp_state", LIGHT_LAYER_VERSION, states_before, after_states
        )
    else:
        current_seed = next(
            int(entry["flicker_seed"])
            for entry in flicker_before
            if int(entry["lamp_index"]) == lamp_index
        )
        next_seed = (value >> 64) % MAX_FLICKER_SEED
        if next_seed == current_seed:
            next_seed = (next_seed + 1) % MAX_FLICKER_SEED
        after_flicker = copy.deepcopy(flicker_before)
        for entry in after_flicker:
            if int(entry["lamp_index"]) == lamp_index:
                entry["flicker_seed"] = next_seed
        change = mm.change_block(
            "lamp_flicker", LIGHT_LAYER_VERSION, flicker_before, after_flicker
        )
    draw = {"purpose": "lamp-edit", "value": value}
    return change, draw


def _cell_override(overlay: dict[str, Any], cell_id: str) -> dict[str, Any]:
    override = overlay.get("cell_overrides", {}).get(cell_id, {})
    if not isinstance(override, dict):
        raise FollowerEditError("override_invalid", f"cell {cell_id} override is not an object")
    return override


def effective_reverb(base: mm.BaseMap, overlay: dict[str, Any], cell_id: str) -> bool:
    """Base wet/dry flag with the folded per-cell ``reverb`` override."""
    cell = _cells(base.document).get(cell_id)
    if cell is None:
        raise FollowerEditError("unknown_cell", f"cell {cell_id} is not in the base map")
    value = _cell_override(overlay, cell_id).get("reverb")
    if value is None:
        value = cell.get("reverb")
    if type(value) is not bool:
        raise FollowerEditError("reverb_invalid", f"cell {cell_id} has no boolean reverb")
    return value


def reverb_eligible_cells(document: dict[str, Any]) -> set[str]:
    """Walkable cells with a boolean reverb layer; modules may take this edit."""
    return {
        cell_id
        for cell_id, cell in _cells(document).items()
        if _is_walkable(cell)
        and type(cell.get("reverb")) is bool
        and not cell.get("landmark")
    }


def wear_eligible_cells(document: dict[str, Any]) -> set[str]:
    """Generated cells whose base wear can still move up one level."""
    return {
        cell_id
        for cell_id, cell in _cells(document).items()
        if _is_walkable(cell)
        and not cell.get("module")
        and not cell.get("landmark")
        and type(cell.get("wear")) is int
        and int(cell["wear"]) < ms.MAX_WEAR
    }


def effective_wear(base: mm.BaseMap, overlay: dict[str, Any], cell_id: str) -> int:
    """Base wear with the folded per-cell ``wear`` override."""
    cell = _cells(base.document).get(cell_id)
    if cell is None:
        raise FollowerEditError("unknown_cell", f"cell {cell_id} is not in the base map")
    try:
        return ms.effective_wear(cell, _cell_override(overlay, cell_id))
    except ms.SurfaceError as error:
        raise FollowerEditError(error.code, error.message) from error


def effective_surface_variants(
    base: mm.BaseMap, overlay: dict[str, Any], cell_id: str
) -> dict[str, str]:
    """Base variants with the folded per-cell ``surface_variant`` override.

    Raises when the palette is unknown or a selected variant is not offered by
    that palette: the check the proposal calls palette-compatible validation.
    """
    cell = _cells(base.document).get(cell_id)
    if cell is None:
        raise FollowerEditError("unknown_cell", f"cell {cell_id} is not in the base map")
    try:
        return ms.effective_variants(
            base.document, cell, _cell_override(overlay, cell_id)
        )
    except ms.SurfaceError as error:
        raise FollowerEditError(error.code, error.message) from error


def _variant_state(
    base: mm.BaseMap, overlay: dict[str, Any], cell_id: str
) -> tuple[dict[str, Any], dict[str, str], list[str]] | None:
    """The palette, effective variants and forward surfaces, or ``None``."""
    cell = _cells(base.document).get(cell_id)
    if cell is None:
        return None
    try:
        palette = ms.palette_for_cell(base.document, cell)
        variants = ms.effective_variants(
            base.document, cell, _cell_override(overlay, cell_id)
        )
        surfaces = ms.escalatable_from_variants(variants, palette)
    except ms.SurfaceError:
        return None
    return palette, variants, surfaces


def surface_variant_eligible_cells(document: dict[str, Any]) -> set[str]:
    """Generated cells with a palette-compatible variant that can move forward."""
    result: set[str] = set()
    try:
        registry = ms.palette_registry(document)
    except ms.SurfaceError:
        return result
    for cell_id, cell in _cells(document).items():
        if (
            not _is_walkable(cell)
            or cell.get("module")
            or cell.get("landmark")
        ):
            continue
        try:
            palette = ms.palette_for_cell(document, cell, registry=registry)
            if ms.escalatable_surfaces(cell, palette):
                result.add(cell_id)
        except ms.SurfaceError:
            continue
    return result


def _target_context(
    base: mm.BaseMap,
    events: Iterable[dict[str, Any]],
    *,
    player_cell: str,
    exit_cell: str | None,
    visibility_depth: int,
    door_states: dict[str, str] | None,
) -> tuple[list[str], str, str | None, set[str]]:
    event_list = list(events)
    document = base.document
    visited = mm.visited_cells(event_list)
    spawn = str(document["cells"][0]["cell_id"])
    last_edited = last_edited_cell(event_list)
    visible = set(
        visible_cells(
            document,
            player_cell,
            depth=visibility_depth,
            door_states=door_states,
        )
    )
    return visited, spawn, last_edited, visible


def _class_eligible(
    base: mm.BaseMap,
    overlay: dict[str, Any],
    cell_id: str,
    change_class: str,
    *,
    player_cell: str,
    exit_cell: str | None,
    spawn: str,
    last_edited: str | None,
    visible: set[str],
    cells: dict[str, dict[str, Any]],
) -> bool:
    """Every §5.3/§5.5 exclusion plus the class's own layer requirement."""
    if (
        cell_id == player_cell
        or cell_id == spawn
        or cell_id == exit_cell
        or cell_id == last_edited
        or cell_id in visible
    ):
        return False
    cell = cells.get(cell_id)
    if cell is None or not _is_walkable(cell) or cell.get("landmark"):
        return False
    if change_class == "reverb":
        return type(cell.get("reverb")) is bool
    if cell.get("module"):
        return False
    if change_class in LAMP_CLASSES:
        return bool(_lamps(cell))
    if change_class == "wear":
        if cell_id not in wear_eligible_cells(base.document):
            return False
        try:
            return effective_wear(base, overlay, cell_id) < ms.MAX_WEAR
        except FollowerEditError:
            return False
    if change_class == "surface_variant":
        state = _variant_state(base, overlay, cell_id)
        return state is not None and bool(state[2])
    return False


def _select_class_target(
    base: mm.BaseMap,
    overlay: dict[str, Any],
    events: Iterable[dict[str, Any]],
    change_class: str,
    *,
    player_cell: str,
    event_index: int,
    exit_cell: str | None = None,
    visibility_depth: int = DEFAULT_VISIBILITY_DEPTH,
    door_states: dict[str, str] | None = None,
    stream: str = STREAM,
) -> str | None:
    event_list = list(events)
    visited, spawn, last_edited, visible = _target_context(
        base,
        event_list,
        player_cell=player_cell,
        exit_cell=exit_cell,
        visibility_depth=visibility_depth,
        door_states=door_states,
    )
    cells = _cells(base.document)
    candidates = [
        cell_id
        for cell_id in visited
        if _class_eligible(
            base,
            overlay,
            cell_id,
            change_class,
            player_cell=player_cell,
            exit_cell=exit_cell,
            spawn=spawn,
            last_edited=last_edited,
            visible=visible,
            cells=cells,
        )
    ]
    return _ranked_target(
        base, event_list, candidates, event_index=event_index, stream=stream
    )


def select_reverb_target(
    base: mm.BaseMap,
    overlay: dict[str, Any],
    events: Iterable[dict[str, Any]],
    *,
    player_cell: str,
    event_index: int,
    exit_cell: str | None = None,
    visibility_depth: int = DEFAULT_VISIBILITY_DEPTH,
    door_states: dict[str, str] | None = None,
    stream: str = STREAM,
) -> str | None:
    """The hidden visited cell whose wet/dry flag may flip."""
    return _select_class_target(
        base,
        overlay,
        events,
        "reverb",
        player_cell=player_cell,
        event_index=event_index,
        exit_cell=exit_cell,
        visibility_depth=visibility_depth,
        door_states=door_states,
        stream=stream,
    )


def select_wear_target(
    base: mm.BaseMap,
    overlay: dict[str, Any],
    events: Iterable[dict[str, Any]],
    *,
    player_cell: str,
    event_index: int,
    exit_cell: str | None = None,
    visibility_depth: int = DEFAULT_VISIBILITY_DEPTH,
    door_states: dict[str, str] | None = None,
    stream: str = STREAM,
) -> str | None:
    """The hidden visited generated cell whose wear may rise by one."""
    return _select_class_target(
        base,
        overlay,
        events,
        "wear",
        player_cell=player_cell,
        event_index=event_index,
        exit_cell=exit_cell,
        visibility_depth=visibility_depth,
        door_states=door_states,
        stream=stream,
    )


def select_surface_variant_target(
    base: mm.BaseMap,
    overlay: dict[str, Any],
    events: Iterable[dict[str, Any]],
    *,
    player_cell: str,
    event_index: int,
    exit_cell: str | None = None,
    visibility_depth: int = DEFAULT_VISIBILITY_DEPTH,
    door_states: dict[str, str] | None = None,
    stream: str = STREAM,
) -> str | None:
    """The hidden visited cell with a palette-compatible variant step."""
    return _select_class_target(
        base,
        overlay,
        events,
        "surface_variant",
        player_cell=player_cell,
        event_index=event_index,
        exit_cell=exit_cell,
        visibility_depth=visibility_depth,
        door_states=door_states,
        stream=stream,
    )


def choose_edit_class(
    base: mm.BaseMap,
    *,
    feasible: Iterable[str],
    event_index: int,
    player_cell: str,
    stream: str = STREAM,
) -> str | None:
    """Keyed uniform draw over the classes that have an eligible target."""
    classes = list(feasible)
    if not classes:
        return None
    value = mm.draw_for_event(
        base.seed,
        base.attempt,
        event_index,
        stream,
        player_cell,
        CLASS_DRAW_PURPOSE,
    )
    return classes[value % len(classes)]


def _choose_reverb_edit(
    base: mm.BaseMap, overlay: dict[str, Any], *, target_cell: str
) -> tuple[dict[str, Any], None]:
    before = effective_reverb(base, overlay, target_cell)
    change = mm.change_block(
        "reverb", REVERB_LAYER_VERSION, before, not before
    )
    return change, None


def _choose_wear_edit(
    base: mm.BaseMap, overlay: dict[str, Any], *, target_cell: str
) -> tuple[dict[str, Any], None]:
    before = effective_wear(base, overlay, target_cell)
    if before >= ms.MAX_WEAR:
        raise FollowerEditError("wear_capped", f"cell {target_cell} is already worn out")
    change = mm.change_block("wear", ms.SURFACE_LAYER_VERSION, before, before + 1)
    return change, None


def _choose_surface_variant_edit(
    base: mm.BaseMap,
    overlay: dict[str, Any],
    *,
    target_cell: str,
    event_index: int,
    stream: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cell = _cells(base.document)[target_cell]
    try:
        palette = ms.palette_for_cell(base.document, cell)
        before = ms.effective_variants(
            base.document, cell, _cell_override(overlay, target_cell)
        )
        surfaces = ms.escalatable_from_variants(before, palette)
    except ms.SurfaceError as error:
        raise FollowerEditError(error.code, error.message) from error
    if not surfaces:
        raise FollowerEditError(
            "variant_capped", f"cell {target_cell} has no surface to wear further"
        )
    value = mm.draw_for_event(
        base.seed,
        base.attempt,
        event_index,
        stream,
        target_cell,
        "variant-surface",
    )
    surface = surfaces[value % len(surfaces)]
    after = ms.surface_change(cell, surface, before, palette)
    if after is None:
        raise FollowerEditError(
            "variant_capped", f"cell {target_cell} surface {surface} cannot advance"
        )
    change = mm.change_block(
        "surface_variant", ms.SURFACE_LAYER_VERSION, before, after
    )
    return change, {"purpose": "variant-surface", "value": value}


def validation_checks(change_class: str) -> list[str]:
    """The audit checks recorded in one accepted M8 follower edit."""
    checks = [
        "cadence_beat",
        "target_hidden",
        "not_current_cell",
        "not_spawn_or_exit",
    ]
    if change_class in LAMP_CLASSES:
        checks.append("lamp_override_only")
    elif change_class == "reverb":
        checks.extend(["reverb_override_only", "reverb_flip"])
    elif change_class == "wear":
        checks.extend(["wear_override_only", "wear_capped"])
    elif change_class == "surface_variant":
        checks.extend(["surface_variant_override_only", "palette_compatible"])
    return checks


def plan_follower_edit(
    base: mm.BaseMap,
    overlay: dict[str, Any],
    events: Iterable[dict[str, Any]],
    *,
    player_cell: str,
    event_index: int,
    exit_cell: str | None = None,
    visibility_depth: int = DEFAULT_VISIBILITY_DEPTH,
    door_states: dict[str, str] | None = None,
    stream: str = STREAM,
    target_cell: str | None = None,
    force_class: str | None = None,
) -> FollowerEditPlan | None:
    """Plan the M8 edit for the current cadence beat, or drop the beat.

    The class is a keyed draw over the implemented classes that have at least
    one eligible hidden target.  A forced class or target is for tests and
    negative controls; the normal scheduler uses neither.
    """
    event_list = list(events)
    count = current_entry_visit_count(event_list)
    if count is None:
        return None
    cadence = mm.reconstruct_cadence(event_list)
    if count not in cadence["beats"]:
        return None
    allowed = [
        change_class
        for change_class in IMPLEMENTED_CLASSES
        if change_class in cadence["allowed_classes"]
    ]
    if force_class is not None:
        allowed = [force_class] if force_class in allowed else []
    if not allowed:
        return None
    entry_index = 0
    for event in reversed(event_list):
        trigger = event.get("trigger") if isinstance(event, dict) else None
        if (
            isinstance(trigger, dict)
            and trigger.get("player_cell") == player_cell
            and event.get("record_kind") == "trigger"
        ):
            entry_index = int(event["event_index"])
            break
    if entry_index == 0 and event_list:
        entry_index = int(event_list[-1]["event_index"])
    if any(
        event.get("record_kind") == "mutation"
        and event.get("event_type") == "follower_edit"
        and mm._event_outcome(event) == "accepted"
        and int(event["event_index"]) > entry_index
        for event in event_list
    ):
        return None
    visited, spawn, last_edited, visible = _target_context(
        base,
        event_list,
        player_cell=player_cell,
        exit_cell=exit_cell,
        visibility_depth=visibility_depth,
        door_states=door_states,
    )
    cells = _cells(base.document)
    if player_cell not in cells or not visited:
        return None
    targets: dict[str, str] = {}
    if target_cell is not None:
        for change_class in allowed:
            if _class_eligible(
                base,
                overlay,
                target_cell,
                change_class,
                player_cell=player_cell,
                exit_cell=exit_cell,
                spawn=spawn,
                last_edited=last_edited,
                visible=visible,
                cells=cells,
            ):
                targets[change_class] = target_cell
    else:
        for change_class in allowed:
            target = _select_class_target(
                base,
                overlay,
                event_list,
                change_class,
                player_cell=player_cell,
                event_index=event_index,
                exit_cell=exit_cell,
                visibility_depth=visibility_depth,
                door_states=door_states,
                stream=stream,
            )
            if target is not None:
                targets[change_class] = target
    feasible = [change_class for change_class in allowed if change_class in targets]
    if not feasible:
        return None
    change_class = force_class or choose_edit_class(
        base,
        feasible=feasible,
        event_index=event_index,
        player_cell=player_cell,
        stream=stream,
    )
    if change_class is None:
        return None
    target = targets[change_class]
    if change_class in LAMP_CLASSES:
        change, draw = _choose_lamp_edit(
            base,
            overlay,
            target_cell=target,
            event_index=event_index,
            stream=stream,
            force_class=change_class,
        )
    elif change_class == "reverb":
        change, draw = _choose_reverb_edit(base, overlay, target_cell=target)
    elif change_class == "wear":
        change, draw = _choose_wear_edit(base, overlay, target_cell=target)
    else:
        change, draw = _choose_surface_variant_edit(
            base,
            overlay,
            target_cell=target,
            event_index=event_index,
            stream=stream,
        )
    visibility = {
        "player_cell": player_cell,
        "target_hidden": True,
        "visible_cells": sorted(visible),
    }
    return FollowerEditPlan(
        target_cell=target,
        change=change,
        draw=draw,
        visibility=visibility,
    )


def current_entry_visit_count(events: Iterable[dict[str, Any]]) -> int | None:
    """Distinct-visit count when the latest trigger introduced a new cell.

    A return to an already visited room does not introduce a new cell, so it
    cannot re-fire the beat that its first entry already consumed.
    """
    seen: set[str] = set()
    count = 0
    last_new_index: int | None = None
    last_trigger_index: int | None = None
    for event in events:
        if not isinstance(event, dict) or event.get("record_kind") != "trigger":
            continue
        trigger = event.get("trigger")
        if (
            not isinstance(trigger, dict)
            or trigger.get("kind") not in mm.VISIT_TRIGGER_KINDS
        ):
            continue
        last_trigger_index = int(event["event_index"])
        cell = trigger.get("player_cell") or trigger.get("from_cell")
        if not isinstance(cell, str) or not cell or cell in seen:
            continue
        seen.add(cell)
        count += 1
        last_new_index = int(event["event_index"])
    if last_trigger_index is None or last_new_index != last_trigger_index:
        return None
    return count


def plan_lamp_edit(
    base: mm.BaseMap,
    overlay: dict[str, Any],
    events: Iterable[dict[str, Any]],
    *,
    player_cell: str,
    event_index: int,
    exit_cell: str | None = None,
    visibility_depth: int = DEFAULT_VISIBILITY_DEPTH,
    door_states: dict[str, str] | None = None,
    stream: str = STREAM,
    target_cell: str | None = None,
    force_class: str | None = None,
) -> LampEditPlan | None:
    """Plan the edit for the current cadence beat, or return ``None`` to drop it."""
    event_list = list(events)
    count = current_entry_visit_count(event_list)
    if count is None:
        return None
    cadence = mm.reconstruct_cadence(event_list)
    if count not in cadence["beats"]:
        return None
    allowed = [item for item in cadence["allowed_classes"] if item in LAMP_CLASSES]
    if force_class is not None:
        allowed = [force_class] if force_class in allowed else []
    if not allowed:
        return None
    entry_index = 0
    for event in reversed(event_list):
        trigger = event.get("trigger") if isinstance(event, dict) else None
        if (
            isinstance(trigger, dict)
            and trigger.get("player_cell") == player_cell
            and event.get("record_kind") == "trigger"
        ):
            entry_index = int(event["event_index"])
            break
    if entry_index == 0 and event_list:
        entry_index = int(event_list[-1]["event_index"])
    if any(
        event.get("record_kind") == "mutation"
        and event.get("event_type") == "follower_edit"
        and mm._event_outcome(event) == "accepted"
        and int(event["event_index"]) > entry_index
        for event in event_list
    ):
        return None
    cells = _cells(base.document)
    target = target_cell or select_lamp_target(
        base,
        overlay,
        event_list,
        player_cell=player_cell,
        event_index=event_index,
        exit_cell=exit_cell,
        visibility_depth=visibility_depth,
        door_states=door_states,
        stream=stream,
    )
    if target is None or target not in cells:
        return None
    spawn = str(base.document["cells"][0]["cell_id"])
    contests = {
        "current": target == player_cell,
        "spawn": target == spawn,
        "exit": exit_cell is not None and target == exit_cell,
        "module": bool(cells[target].get("module")),
        "landmark": bool(cells[target].get("landmark")),
        "no_lamps": not _lamps(cells[target]),
        "last_edited": target == last_edited_cell(event_list),
    }
    if any(contests.values()):
        return None
    if not cell_is_hidden(
        base.document,
        player_cell,
        target,
        depth=visibility_depth,
        door_states=door_states,
    ):
        return None
    change, draw = _choose_lamp_edit(
        base,
        overlay,
        target_cell=target,
        event_index=event_index,
        stream=stream,
        force_class=force_class,
    )
    visibility = {
        "player_cell": player_cell,
        "target_hidden": True,
        "visible_cells": visible_cells(
            base.document,
            player_cell,
            depth=visibility_depth,
            door_states=door_states,
        ),
    }
    return LampEditPlan(
        target_cell=target,
        change=change,
        draw=draw,
        visibility=visibility,
    )


class FollowerController:
    """In-memory M8 controller: trigger log, overlay, cadence and follower edits."""

    def __init__(
        self,
        base: mm.BaseMap,
        *,
        exit_cell: str | None = None,
        visibility_depth: int = DEFAULT_VISIBILITY_DEPTH,
        stream: str = STREAM,
    ) -> None:
        self.base = base
        self.exit_cell = exit_cell
        self.visibility_depth = visibility_depth
        self.stream = stream
        self.events: list[dict[str, Any]] = []
        self.overlay = mm.empty_overlay(base)

    def restore(self, events: Iterable[dict[str, Any]]) -> None:
        """Replay a saved log, then continue from it."""
        self.events = [copy.deepcopy(event) for event in events]
        self.overlay = mm.fold_events(self.base, self.events)

    @property
    def state_hash(self) -> str:
        return str(self.overlay["state_hash"])

    def lamp_states(self, cell_id: str) -> list[dict[str, int | str]]:
        return effective_lamp_states(self.base, self.overlay, cell_id)

    def reverb_enabled(self, cell_id: str) -> bool:
        return effective_reverb(self.base, self.overlay, cell_id)

    def wear(self, cell_id: str) -> int:
        return effective_wear(self.base, self.overlay, cell_id)

    def surface_variants(self, cell_id: str) -> dict[str, str]:
        return effective_surface_variants(self.base, self.overlay, cell_id)

    def override_record(self, cell_id: str) -> dict[str, Any]:
        return copy.deepcopy(
            self.overlay.get("cell_overrides", {}).get(cell_id, {})
        )

    def enter_cell(
        self, cell_id: str, *, occurred_at_utc: str | None = None
    ) -> list[dict[str, Any]]:
        """Append the entry trigger and, on a cadence beat, one follower edit."""
        if cell_id not in self.base.cell_ids:
            raise FollowerEditError(
                "unknown_cell", f"cell {cell_id} is not in the base map"
            )
        if self.events:
            trigger = self.events[-1].get("trigger")
            if isinstance(trigger, dict) and trigger.get("player_cell") == cell_id:
                return []
        added: list[dict[str, Any]] = []
        trigger_spec = mm.new_trigger(
            self.base,
            "room_entered",
            len(self.events) + 1,
            player_cell=cell_id,
            occurred_at_utc=occurred_at_utc,
        )
        sealed_trigger = mm.seal_event(self.base, self.overlay, trigger_spec)
        self.overlay = mm.fold_event(self.base, self.overlay, sealed_trigger)
        self.events.append(sealed_trigger)
        added.append(sealed_trigger)
        plan = plan_follower_edit(
            self.base,
            self.overlay,
            self.events,
            player_cell=cell_id,
            event_index=len(self.events) + 1,
            exit_cell=self.exit_cell,
            visibility_depth=self.visibility_depth,
            stream=self.stream,
        )
        if plan is None:
            return added
        mutation = {
            "target": {"cell_id": plan.target_cell},
            "stream": self.stream,
            "change": plan.change,
            "visibility": plan.visibility,
            "validation": {
                "outcome": "accepted",
                "checks": validation_checks(str(plan.change["class"])),
            },
        }
        if plan.draw is not None:
            mutation["draw"] = plan.draw
        mutation_spec = mm.new_mutation(
            self.base,
            "follower_edit",
            len(self.events) + 1,
            occurred_at_utc=occurred_at_utc,
            **mutation,
        )
        sealed_mutation = mm.seal_event(self.base, self.overlay, mutation_spec)
        self.overlay = mm.fold_event(self.base, self.overlay, sealed_mutation)
        self.events.append(sealed_mutation)
        added.append(sealed_mutation)
        return added
