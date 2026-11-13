"""Door leaf and lock-behind state for the maze overlay (#234).

M4 of the #223 overlay chain.  A door is a stable threshold between two
walkable cells: ``threshold_id = "<cell_a>|<cell_b>"``.  The committed map keeps
its own ``doors[]`` placeholders and is never edited; the runtime registry in
:func:`plan` is derived from the map's edges and the generated shape-room specs,
and the live state lives in the overlay's ``door_overrides`` map (M1).

The slice adds no re-roll.  It answers three questions:

* which generated doorways can carry a procedural leaf (a ramp only when the
  leaf fits its landing without rebuilding the ramp, a drop never, and a
  library doorway never);
* on which crossings may the leaf close and latch behind the player.  The
  provisional Q13 default is eligible-only: the crossing must be a bridge, have
  a 3-8-cell departed component, have a leaf, and leave the exit outside that
  component and reachable with the door closed;
* how the latch and the manual open are recorded, replayed and hashed.

The locked door is always openable from the player's side, so a latch never
removes the exit route.  The committed map bytes are only ever read.

This module is the headless reference.  ``maze_doors.gd`` is the runtime twin;
``godot_walk/fixtures/maze_doors_v1.json`` is the shared fixture both test.
"""

from __future__ import annotations

import copy
import hashlib
import sys
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_exit as me
import maze_follower as mf
import maze_mutation as mm

RULE = "maze_doors"
SCHEMA_VERSION = 1
LAYER_VERSION = "maze-door-0.1.0"
EVENT_STREAM = "door:gmap-0.13.0"
STATE_HASH_PREFIX = "maze-door-state-0.1.0"
STATES = ("open", "latched")
DEFAULT_STATE = "open"
MIN_LEAF_WIDTH_M = 0.6
MIN_LEAF_HEIGHT_M = 1.0
SILL_TOLERANCE_M = 1e-3

LOCK_CHECKS = (
    "leaf_fits",
    "bridge",
    "target_size",
    "exit_outside_target",
    "exit_reachable_closed",
)
OPEN_CHECKS = ("door_latched", "player_on_current_side")

# Crossing rejection reasons, in the order they are recorded.
REASON_ORDER = (
    "library_doorway",
    "no_leaf",
    "rewire_internal",
    "drop_door",
    "missing_doorway",
    "ramp_no_landing",
    "small_port",
    "exit_threshold_door",
    "exit_cell_door",
    "not_bridge",
    "target_too_small",
    "target_too_large",
    "exit_inside",
)


class DoorPlanError(ValueError):
    """A door registry cannot be built for this map."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _cells(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for cell in document.get("cells", []):
        if isinstance(cell, dict) and isinstance(cell.get("cell_id"), str):
            result[cell["cell_id"]] = cell
    return result


def _is_library(cell: dict[str, Any]) -> bool:
    return isinstance(cell.get("module"), dict)


def _doorway(spec: dict[str, Any] | None, port_id: str) -> dict[str, Any] | None:
    if not isinstance(spec, dict):
        return None
    for doorway in spec.get("doorways", []):
        if isinstance(doorway, dict) and str(doorway.get("port_id", "")) == port_id:
            return doorway
    return None


def _ramp_record(spec: dict[str, Any] | None, port_id: str) -> dict[str, Any] | None:
    if not isinstance(spec, dict):
        return None
    for ramp in spec.get("ramps", []):
        if isinstance(ramp, dict) and str(ramp.get("port_id", "")) == port_id:
            return ramp
    return None


def _sill(doorway: dict[str, Any]) -> float:
    return float(doorway.get("sill_height_m", 0.0))


def leaf_fit(
    vertical: str,
    spec_a: dict[str, Any] | None,
    spec_b: dict[str, Any] | None,
    door_a: dict[str, Any] | None,
    door_b: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """Can one vertical leaf fill this port without rebuilding the ramp?"""
    if vertical == "drop":
        return False, "drop_door"
    if door_a is None or door_b is None:
        return False, "missing_doorway"
    if door_a.get("rewire_internal") or door_b.get("rewire_internal"):
        return False, "rewire_internal"
    width = min(float(door_a.get("width_m", 0.0)), float(door_b.get("width_m", 0.0)))
    height = min(
        float(door_a.get("height_m", 0.0)), float(door_b.get("height_m", 0.0))
    )
    if width < MIN_LEAF_WIDTH_M or height < MIN_LEAF_HEIGHT_M:
        return False, "small_port"
    if vertical != "ramp":
        if abs(_sill(door_a)) > SILL_TOLERANCE_M or abs(
            _sill(door_b)
        ) > SILL_TOLERANCE_M:
            return False, "ramp_no_landing"
        return True, None
    # A ramp door has one flat landing at the top of the ramp: the lower side
    # records the sill and a ramp whose rise lands exactly at that sill.  If
    # either record is missing or inconsistent, the leaf would need the ramp
    # rebuilt, so the door is skipped.
    lower_side = None
    for spec, doorway in (
        (spec_a, door_a),
        (spec_b, door_b),
    ):
        if _sill(doorway) > SILL_TOLERANCE_M:
            lower_side = (spec, doorway)
            break
    if lower_side is None:
        return False, "ramp_no_landing"
    spec, doorway = lower_side
    ramp = _ramp_record(spec, str(doorway.get("port_id", "")))
    if ramp is None:
        return False, "ramp_no_landing"
    if abs(float(ramp.get("rise_m", 0.0)) - _sill(doorway)) > SILL_TOLERANCE_M:
        return False, "ramp_no_landing"
    if float(ramp.get("run_m", 0.0)) <= 0.0:
        return False, "ramp_no_landing"
    return True, None


def _component_without(
    graph: dict[str, set[str]], start: str, blocked: str
) -> set[str] | None:
    """The component of ``start`` after removing the direct edge start-blocked."""
    if start not in graph:
        return None
    seen = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for neighbour in sorted(graph[current]):
            if current == start and neighbour == blocked:
                continue
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    if blocked in seen:
        return None
    return seen


def target_hash(cells: Any) -> str:
    """Canonical hash of one crossing's departed-cell set."""
    joined = "\n".join(sorted(str(cell) for cell in cells))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _crossing(
    graph: dict[str, set[str]],
    exit_cell: str | None,
    exit_threshold: str | None,
    door: dict[str, Any],
    from_cell: str,
    to_cell: str,
) -> dict[str, Any]:
    """One player movement ``from_cell -> to_cell``.

    ``from_cell`` is the departed cell and ``to_cell`` the arrival cell, so the
    target is the component of ``from_cell`` after removing the door (§4.6).
    """
    threshold = door["threshold_id"]
    reasons: list[str] = []
    if door["kind"] == "library":
        reasons.append("library_doorway")
    elif door["vertical"] == "drop":
        reasons.append("drop_door")
    elif not door["leaf"]:
        reasons.append(str(door["leaf_reason"] or "no_leaf"))
    if threshold == exit_threshold:
        reasons.append("exit_threshold_door")
    elif exit_cell is not None and exit_cell in (door["cell_a"], door["cell_b"]):
        reasons.append("exit_cell_door")
    component = _component_without(graph, from_cell, to_cell)
    target_cells: list[str] = []
    if component is None:
        reasons.append("not_bridge")
        target_size = 0
    else:
        target_cells = sorted(component)
        target_size = len(target_cells)
        if target_size < me.MIN_REROLL_CELLS:
            reasons.append("target_too_small")
        elif target_size > me.MAX_REROLL_CELLS:
            reasons.append("target_too_large")
        if exit_cell is not None and exit_cell in component:
            reasons.append("exit_inside")
    reasons.sort(key=REASON_ORDER.index)
    return {
        "from_cell": from_cell,
        "to_cell": to_cell,
        "target_cells": target_cells,
        "target_size": target_size,
        "target_hash": target_hash(target_cells),
        "eligible": not reasons,
        "reasons": reasons,
    }


def _door_record(
    edge: dict[str, Any],
    cells: dict[str, dict[str, Any]],
    specs: dict[str, dict[str, Any]],
    graph: dict[str, set[str]],
    exit_cell: str | None,
    exit_threshold: str | None,
) -> dict[str, Any] | None:
    port_a = str(edge.get("from", ""))
    port_b = str(edge.get("to", ""))
    cell_a = port_a.partition(":")[0]
    cell_b = port_b.partition(":")[0]
    if cell_a == cell_b or cell_a not in cells or cell_b not in cells:
        return None
    if str(cells[cell_a].get("role", "")) == "void":
        return None
    if str(cells[cell_b].get("role", "")) == "void":
        return None
    if cell_b < cell_a:
        cell_a, cell_b = cell_b, cell_a
        port_a, port_b = port_b, port_a
    library = _is_library(cells[cell_a]) or _is_library(cells[cell_b])
    spec_a = specs.get(cell_a)
    spec_b = specs.get(cell_b)
    door_a = _doorway(spec_a, port_a)
    door_b = _doorway(spec_b, port_b)
    vertical = str(edge.get("vertical", "level"))
    kind = "library" if library else "generated"
    if library:
        leaf, leaf_reason = False, "library_doorway"
    else:
        leaf, leaf_reason = leaf_fit(vertical, spec_a, spec_b, door_a, door_b)
    door: dict[str, Any] = {
        "threshold_id": me.threshold_id(cell_a, cell_b),
        "cell_a": cell_a,
        "cell_b": cell_b,
        "port_a": port_a,
        "port_b": port_b,
        "vertical": vertical,
        "kind": kind,
        "leaf": leaf,
        "leaf_reason": leaf_reason,
        "leaf_side": cell_a if leaf else None,
        "leaf_port": port_a if leaf else None,
        "exit_threshold": me.threshold_id(cell_a, cell_b) == exit_threshold,
    }
    door["crossings"] = [
        _crossing(graph, exit_cell, exit_threshold, door, cell_a, cell_b),
        _crossing(graph, exit_cell, exit_threshold, door, cell_b, cell_a),
    ]
    return door


def plan(
    document: dict[str, Any],
    specs: dict[str, dict[str, Any]],
    exit_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the runtime door registry and the eligible lock-behind crossings."""
    if not isinstance(document, dict) or not isinstance(document.get("cells"), list):
        raise DoorPlanError("document_invalid", "map document has no cells")
    exit_data = (
        copy.deepcopy(exit_record)
        if isinstance(exit_record, dict) and exit_record
        else me.select_exit(document)
    )
    exit_cell = str(exit_data.get("cell_id", "")) or None
    exit_threshold = str(exit_data.get("threshold_id", "")) or None
    cells = _cells(document)
    graph = me.adjacency(document)
    doors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for edge in document.get("edges", []):
        if not isinstance(edge, dict) or edge.get("connector") != "direct":
            continue
        record = _door_record(
            edge, cells, specs, graph, exit_cell, exit_threshold
        )
        if record is None or record["threshold_id"] in seen:
            continue
        seen.add(record["threshold_id"])
        doors.append(record)
    doors.sort(key=lambda door: door["threshold_id"])
    eligible = [
        {"threshold_id": door["threshold_id"], "from_cell": crossing["from_cell"],
         "to_cell": crossing["to_cell"]}
        for door in doors
        for crossing in door["crossings"]
        if crossing["eligible"]
    ]
    skipped = [
        {"threshold_id": door["threshold_id"], "reason": door["leaf_reason"]}
        for door in doors
        if not door["leaf"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "layer_version": LAYER_VERSION,
        "map_id": str(document.get("map_id", "")),
        "seed": int(document.get("seed", 0)),
        "exit_cell": exit_cell or "",
        "exit_threshold_id": exit_threshold or "",
        "doors": doors,
        "eligible_crossings": eligible,
        "skipped_doors": skipped,
        "stats": {
            "doors": len(doors),
            "generated": sum(1 for door in doors if door["kind"] == "generated"),
            "library": sum(1 for door in doors if door["kind"] == "library"),
            "leaf_capable": sum(1 for door in doors if door["leaf"]),
            "eligible_crossings": len(eligible),
        },
    }


def projection(plan_data: dict[str, Any]) -> dict[str, Any]:
    """The compact cross-language contract stored in the shared fixture."""
    doors = []
    for door in plan_data.get("doors", []):
        crossings = []
        for crossing in door.get("crossings", []):
            crossings.append(
                {
                    key: crossing[key]
                    for key in (
                        "from_cell",
                        "to_cell",
                        "target_size",
                        "target_hash",
                        "eligible",
                        "reasons",
                    )
                }
            )
        doors.append(
            {
                key: door[key]
                for key in (
                    "threshold_id",
                    "cell_a",
                    "cell_b",
                    "port_a",
                    "port_b",
                    "vertical",
                    "kind",
                    "leaf",
                    "leaf_reason",
                    "leaf_side",
                    "leaf_port",
                    "exit_threshold",
                )
            }
            | {"crossings": crossings}
        )
    return {
        "schema_version": plan_data.get("schema_version"),
        "layer_version": plan_data.get("layer_version"),
        "map_id": plan_data.get("map_id"),
        "seed": plan_data.get("seed"),
        "exit_cell": plan_data.get("exit_cell"),
        "exit_threshold_id": plan_data.get("exit_threshold_id"),
        "doors": doors,
        "eligible_crossings": copy.deepcopy(plan_data.get("eligible_crossings", [])),
        "skipped_doors": copy.deepcopy(plan_data.get("skipped_doors", [])),
        "stats": copy.deepcopy(plan_data.get("stats", {})),
    }


def door_by_threshold(plan_data: dict[str, Any], threshold: str) -> dict[str, Any] | None:
    for door in plan_data.get("doors", []):
        if door["threshold_id"] == threshold:
            return door
    return None


def crossing_for(
    plan_data: dict[str, Any], from_cell: str, to_cell: str
) -> dict[str, Any] | None:
    for door in plan_data.get("doors", []):
        for crossing in door.get("crossings", []):
            if crossing["from_cell"] == from_cell and crossing["to_cell"] == to_cell:
                return {"door": door, "crossing": crossing}
    return None


def states_from_overlay(
    plan_data: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, str]:
    """Merge the base door registry with the overlay's live ``door_overrides``."""
    overrides = overlay.get("door_overrides", {}) if isinstance(overlay, dict) else {}
    states: dict[str, str] = {}
    for door in plan_data.get("doors", []):
        value = overrides.get(door["threshold_id"], {})
        state = value.get("state", DEFAULT_STATE) if isinstance(value, dict) else DEFAULT_STATE
        states[door["threshold_id"]] = state if state in STATES else DEFAULT_STATE
    return states


def fold_states(plan_data: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, str]:
    """Replay the door subset of a log into door states (no seals needed)."""
    states = {door["threshold_id"]: DEFAULT_STATE for door in plan_data.get("doors", [])}
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("record_kind") not in (None, "mutation"):
            continue
        if event.get("event_type") not in ("door_lock", "door_unlock"):
            continue
        validation = event.get("validation")
        if isinstance(validation, dict) and validation.get("outcome") == "rejected":
            continue
        target = event.get("target")
        if not isinstance(target, dict):
            continue
        threshold = target.get("threshold_id")
        if not isinstance(threshold, str) or threshold not in states:
            continue
        change = event.get("change")
        if not isinstance(change, dict):
            continue
        before = change.get("before")
        after = change.get("after")
        if before is not None and before != states[threshold]:
            raise DoorPlanError(
                "change_before_mismatch",
                f"door {threshold} is {states[threshold]}, event says {before}",
            )
        if after not in STATES:
            continue
        states[threshold] = after
    return states


def state_hash(states: dict[str, str]) -> str:
    """Canonical cross-language hash of the live door states."""
    payload = STATE_HASH_PREFIX + "\n"
    for threshold in sorted(states):
        payload += f"{threshold}={states[threshold]}\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def port_states(plan_data: dict[str, Any], states: dict[str, str]) -> dict[str, str]:
    """Door state keyed by both ports, for ``maze_follower.visible_cells``."""
    result: dict[str, str] = {}
    for door in plan_data.get("doors", []):
        state = states.get(door["threshold_id"], DEFAULT_STATE)
        if state == DEFAULT_STATE:
            continue
        result[door["port_a"]] = state
        result[door["port_b"]] = state
    return result


def _reachable(
    document: dict[str, Any], start: str, goal: str, blocked: set[str]
) -> bool:
    if not start or not goal:
        return False
    graph = me.adjacency(document)
    for left, right in me.passage_pairs(document):
        if me.threshold_id(left, right) in blocked:
            graph[left].discard(right)
            graph[right].discard(left)
    if start not in graph or goal not in graph:
        return False
    seen = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        if current == goal:
            return True
        for neighbour in sorted(graph[current]):
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return goal in seen


def exit_reachable(
    document: dict[str, Any],
    exit_cell: str,
    start_cell: str,
    blocked_thresholds: set[str] | None = None,
) -> bool:
    """Is the exit reachable while every blocked door is treated as closed?"""
    return _reachable(document, start_cell, exit_cell, blocked_thresholds or set())


def lock_spec(
    base: mm.BaseMap,
    door: dict[str, Any],
    from_cell: str,
    to_cell: str,
    event_index: int,
    *,
    occurred_at_utc: str | None = None,
    visibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The forced ``door_lock`` mutation for one eligible crossing."""
    return mm.new_mutation(
        base,
        "door_lock",
        event_index,
        target={
            "threshold_id": door["threshold_id"],
            "from_cell": from_cell,
            "to_cell": to_cell,
        },
        stream=EVENT_STREAM,
        change=mm.change_block("state", LAYER_VERSION, "open", "latched"),
        validation={"outcome": "accepted", "checks": list(LOCK_CHECKS)},
        visibility=visibility,
        occurred_at_utc=occurred_at_utc,
    )


def rejected_lock_spec(
    base: mm.BaseMap,
    door: dict[str, Any],
    from_cell: str,
    to_cell: str,
    event_index: int,
    *,
    reason: str = "exit_route_removed",
    occurred_at_utc: str | None = None,
) -> dict[str, Any]:
    """A latch refused because closing the door would break a hard invariant."""
    return mm.new_mutation(
        base,
        "door_lock",
        event_index,
        target={
            "threshold_id": door["threshold_id"],
            "from_cell": from_cell,
            "to_cell": to_cell,
        },
        stream=EVENT_STREAM,
        change=mm.change_block("state", LAYER_VERSION, "open", "latched"),
        validation={
            "outcome": "rejected",
            "reason": reason,
            "checks": [reason],
        },
        occurred_at_utc=occurred_at_utc,
    )


def open_spec(
    base: mm.BaseMap,
    door: dict[str, Any],
    from_cell: str,
    event_index: int,
    *,
    occurred_at_utc: str | None = None,
) -> dict[str, Any]:
    """The manual-open ``door_unlock`` mutation from the player's side."""
    return mm.new_mutation(
        base,
        "door_unlock",
        event_index,
        target={"threshold_id": door["threshold_id"], "from_cell": from_cell},
        stream=EVENT_STREAM,
        change=mm.change_block("state", LAYER_VERSION, "latched", "open"),
        validation={"outcome": "accepted", "checks": list(OPEN_CHECKS)},
        occurred_at_utc=occurred_at_utc,
    )


def door_counters(events: list[dict[str, Any]]) -> dict[str, int]:
    locks = 0
    opens = 0
    rejected = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type")
        if event_type not in ("door_lock", "door_unlock"):
            continue
        validation = event.get("validation")
        if isinstance(validation, dict) and validation.get("outcome") == "rejected":
            rejected += 1
            continue
        if event_type == "door_lock":
            locks += 1
        else:
            opens += 1
    return {"locks": locks, "opens": opens, "rejected": rejected}


class DoorRun:
    """In-memory run driver: cross, latch, open, save and restore."""

    def __init__(
        self,
        base: mm.BaseMap,
        specs: dict[str, dict[str, Any]],
        exit_record: dict[str, Any] | None = None,
        plan_data: dict[str, Any] | None = None,
        *,
        occurred_at_utc: str | None = None,
    ) -> None:
        self.base = base
        self.specs = specs
        self.plan = (
            copy.deepcopy(plan_data)
            if plan_data is not None
            else plan(base.document, specs, exit_record)
        )
        self.exit_cell = str(self.plan.get("exit_cell", ""))
        self.events: list[dict[str, Any]] = []
        self.overlay = mm.empty_overlay(base)
        self.states = {
            door["threshold_id"]: DEFAULT_STATE for door in self.plan["doors"]
        }
        self.current_cell: str | None = None
        self.previous_cell: str | None = None
        self.occurred_at_utc = occurred_at_utc

    @property
    def state_hash(self) -> str:
        return state_hash(self.states)

    @property
    def ended(self) -> bool:
        return bool(self.overlay["run"]["ended"])

    def restore(self, events: list[dict[str, Any]]) -> None:
        self.events = [copy.deepcopy(event) for event in events]
        self.overlay = mm.fold_events(self.base, self.events)
        self.states = fold_states(self.plan, self.events)
        self.current_cell = None
        self.previous_cell = None
        for event in reversed(self.events):
            if event.get("record_kind") == "trigger":
                trigger = event.get("trigger", {})
                value = trigger.get("player_cell") or trigger.get("from_cell")
                if isinstance(value, str):
                    self.current_cell = value
                    break

    def _append(self, spec: dict[str, Any]) -> dict[str, Any]:
        sealed = mm.seal_event(self.base, self.overlay, spec)
        self.overlay = mm.fold_event(self.base, self.overlay, sealed)
        self.events.append(sealed)
        return sealed

    def _visibility_for(
        self, player_cell: str, target_cell: str, threshold: str
    ) -> dict[str, Any]:
        door_states: dict[str, str] = {}
        for door in self.plan["doors"]:
            if door["threshold_id"] == threshold:
                door_states[door["port_a"]] = "latched"
                door_states[door["port_b"]] = "latched"
        visible = mf.visible_cells(
            self.base.document, player_cell, door_states=door_states
        )
        return {
            "player_cell": player_cell,
            "target_hidden": target_cell not in visible,
            "visible_cells": visible,
        }

    def enter_cell(self, cell_id: str) -> list[dict[str, Any]]:
        if cell_id not in self.base.cell_ids:
            raise DoorPlanError("unknown_cell", f"cell {cell_id} is not in the map")
        if self.ended:
            return []
        records: list[dict[str, Any]] = []
        previous = self.current_cell
        trigger = self._append(
            mm.new_trigger(
                self.base,
                "room_entered",
                len(self.events) + 1,
                player_cell=cell_id,
                from_cell=previous,
                occurred_at_utc=self.occurred_at_utc,
            )
        )
        records.append(trigger)
        if previous is not None and previous != cell_id and cell_id != self.exit_cell:
            found = crossing_for(self.plan, previous, cell_id)
            if found is not None and found["crossing"]["eligible"]:
                records.append(self._latch(found["door"], previous, cell_id))
        self.previous_cell = previous
        self.current_cell = cell_id
        return records

    def _latch(
        self, door: dict[str, Any], from_cell: str, to_cell: str
    ) -> dict[str, Any]:
        threshold = door["threshold_id"]
        blocked = {threshold}
        if not exit_reachable(
            self.base.document, self.exit_cell, to_cell, blocked
        ):
            return self._append(
                rejected_lock_spec(
                    self.base,
                    door,
                    from_cell,
                    to_cell,
                    len(self.events) + 1,
                    occurred_at_utc=self.occurred_at_utc,
                )
            )
        visibility = self._visibility_for(to_cell, from_cell, threshold)
        if not visibility["target_hidden"]:
            return self._append(
                rejected_lock_spec(
                    self.base,
                    door,
                    from_cell,
                    to_cell,
                    len(self.events) + 1,
                    reason="visible_target",
                    occurred_at_utc=self.occurred_at_utc,
                )
            )
        event = self._append(
            lock_spec(
                self.base,
                door,
                from_cell,
                to_cell,
                len(self.events) + 1,
                occurred_at_utc=self.occurred_at_utc,
                visibility=visibility,
            )
        )
        self.states[threshold] = "latched"
        return event

    def open_door(self, threshold: str, from_cell: str | None = None) -> bool:
        door = door_by_threshold(self.plan, threshold)
        if door is None or self.states.get(threshold) != "latched":
            return False
        side = from_cell or self.current_cell or ""
        if side not in (door["cell_a"], door["cell_b"]):
            return False
        self._append(
            open_spec(
                self.base,
                door,
                side,
                len(self.events) + 1,
                occurred_at_utc=self.occurred_at_utc,
            )
        )
        self.states[threshold] = "open"
        return True

    def counters(self) -> dict[str, int]:
        return door_counters(self.events)
