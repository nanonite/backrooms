"""Static exit selection and the run-end card for the maze overlay (#233).

The exit is chosen once from the seed and never moves during a run (§6.4).  A
committed map may carry the choice in its own ``exit`` layer; maps generated
before that layer, including every committed map in this repository, derive the
same choice from ``(seed, attempt)`` without rewriting a byte.  Both paths use
the same per-cell keyed draw as the other layers::

    sha256("<seed>:<attempt>:exit:gmap-0.13.0:<cell_id>")

Selection order is part of the design, not an implementation detail:

1. Build the structural 3-8 re-roll targets from the level/ramp passage graph.
2. Prefer a cell outside every target, then a leaf, then the smallest total
   removed target size, then a generated room, then the keyed rank.
3. Only after the exit cell is fixed, mark the re-roll directions that the exit
   removes (``exit_inside``) and the threshold door itself
   (``exit_threshold_door``).

That order keeps the exit from silently removing the only re-roll door as often
as the map allows.  Where every cell is inside a target (seeds 32 and 279), the
leaf and smallest-loss tie-breaks keep a direction with a pool eligible.

Crossing the exit is recorded as one ``exit_entered`` trigger followed by one
``run_end`` mutation.  The end card is derived from the log and offers no next
seed and no next level: ``actions`` is always empty.
"""

from __future__ import annotations

import copy
import sys
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_mutation as mm
from gmap_keyed import keyed_rank

EXIT_LAYER_VERSION = "exit:gmap-0.13.0"
EXIT_LAYER_FIELD = "exit"
DRAW_PURPOSE = "exit-cell"
MIN_REROLL_CELLS = 3
MAX_REROLL_CELLS = 8
RUN_STREAM = "run:gmap-0.13.0"
SCHEMA_VERSION = 1
RUN_END_CHECKS = (
    "exit_threshold_crossed",
    "exit_static",
    "run_not_ended",
)


class ExitSelectionError(ValueError):
    """A map cannot carry a static exit under the v1 placement rules."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def walkable_ids(document: dict[str, Any]) -> list[str]:
    """Every traversable cell id, in document order (``role != "void"``)."""
    return [
        str(cell["cell_id"])
        for cell in document["cells"]
        if str(cell.get("role", "")) != "void"
    ]


def passage_pairs(document: dict[str, Any]) -> list[tuple[str, str]]:
    """The undirected level/ramp passage graph, excluding one-way drops.

    This is the graph the §4.5.9 feasibility measurement used: ``direct``
    non-drop edges over walkable cells.  A drop is a one-way vertical link and
    cannot be a re-roll door or a re-roll target boundary.
    """
    walkable = set(walkable_ids(document))
    pairs: set[tuple[str, str]] = set()
    for edge in document.get("edges", []):
        if edge.get("connector") != "direct":
            continue
        if edge.get("vertical") == "drop":
            continue
        left = str(edge.get("from", "")).split(":", 1)[0]
        right = str(edge.get("to", "")).split(":", 1)[0]
        if left == right or left not in walkable or right not in walkable:
            continue
        pairs.add((left, right) if left < right else (right, left))
    return sorted(pairs)


def adjacency(document: dict[str, Any]) -> dict[str, set[str]]:
    """Undirected walkable adjacency over :func:`passage_pairs`."""
    graph: dict[str, set[str]] = {cell_id: set() for cell_id in walkable_ids(document)}
    for left, right in passage_pairs(document):
        if left in graph and right in graph:
            graph[left].add(right)
            graph[right].add(left)
    return graph


def threshold_id(left: str, right: str) -> str:
    """Stable passage identity: the sorted cell pair (§9.3)."""
    return f"{min(left, right)}|{max(left, right)}"


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


def reroll_targets(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Every 3-8-cell departed component, one record per crossing direction.

    A bridge passage contributes two directions: the player may arrive from
    either side.  A non-bridge contributes none.  This is the structural form
    of §4.4 conditions 2 and 3; leaf, visibility and candidate-count checks
    belong to the re-roll slice.
    """
    graph = adjacency(document)
    targets: list[dict[str, Any]] = []
    for left, right in passage_pairs(document):
        for from_cell, to_cell in ((left, right), (right, left)):
            component = _component_without(graph, to_cell, from_cell)
            if component is None:
                continue
            size = len(component)
            if size < MIN_REROLL_CELLS or size > MAX_REROLL_CELLS:
                continue
            targets.append(
                {
                    "passage": [left, right],
                    "threshold_id": threshold_id(left, right),
                    "from_cell": from_cell,
                    "to_cell": to_cell,
                    "target_cells": sorted(component),
                    "target_size": size,
                }
            )
    targets.sort(key=lambda item: (item["from_cell"], item["to_cell"]))
    return targets


def _is_generated_cell(cell: dict[str, Any]) -> bool:
    return (
        not cell.get("module")
        and not cell.get("landmark")
        and not cell.get("diagonal_passage")
        and str(cell.get("role", "")) != "threshold"
    )


def exit_port(document: dict[str, Any], cell_id: str) -> dict[str, Any] | None:
    """The exit threshold doorway on ``cell_id``.

    A leaf has exactly one walkable passage, so the threshold is unambiguous.
    A non-leaf fallback prefers a level/ramp, open passage over a drop or a
    closed-visible one, then the smallest port id, so the choice is stable.
    """
    walkable = set(walkable_ids(document))
    if cell_id not in walkable:
        return None
    candidates: list[dict[str, Any]] = []
    for edge in document.get("edges", []):
        if edge.get("connector") != "direct":
            continue
        left = str(edge.get("from", "")).split(":", 1)[0]
        right = str(edge.get("to", "")).split(":", 1)[0]
        if left == cell_id and right in walkable:
            port_id, to_port_id, other = (
                str(edge["from"]),
                str(edge["to"]),
                right,
            )
        elif right == cell_id and left in walkable:
            port_id, to_port_id, other = (
                str(edge["to"]),
                str(edge["from"]),
                left,
            )
        else:
            continue
        candidates.append(
            {
                "port_id": port_id,
                "to_port_id": to_port_id,
                "from_cell": other,
                "threshold_id": threshold_id(cell_id, other),
                "vertical": str(edge.get("vertical", "level")),
                "connector": str(edge.get("connector", "direct")),
            }
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            item["vertical"] == "drop",
            item["connector"] == "closed_visible",
            item["port_id"],
        )
    )
    return candidates[0]


def _keyed_rank(seed: int, attempt: int, cell_id: str) -> bytes:
    return keyed_rank(seed, attempt, EXIT_LAYER_VERSION, cell_id)


def _seed_exit_record(
    document: dict[str, Any],
    cell_id: str,
    targets: list[dict[str, Any]],
    graph: dict[str, set[str]],
) -> dict[str, Any]:
    port = exit_port(document, cell_id)
    if port is None:
        raise ExitSelectionError(
            "exit_no_port", f"cell {cell_id} has no walkable threshold doorway"
        )
    hits = [
        {
            "from_cell": target["from_cell"],
            "to_cell": target["to_cell"],
            "target_size": target["target_size"],
        }
        for target in targets
        if cell_id in target["target_cells"]
    ]
    seed = int(document["seed"])
    attempt = int(document.get("attempt", 0))
    rank = _keyed_rank(seed, attempt, cell_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "layer_version": EXIT_LAYER_VERSION,
        "source": "seed",
        "cell_id": cell_id,
        "port_id": port["port_id"],
        "to_port_id": port["to_port_id"],
        "from_cell": port["from_cell"],
        "threshold_id": port["threshold_id"],
        "vertical": port["vertical"],
        "leaf": len(graph.get(cell_id, set())) == 1,
        "outside_targets": not hits,
        "targets_hit": hits,
        "removed_cells": sum(hit["target_size"] for hit in hits),
        "draw": {
            "stream": EXIT_LAYER_VERSION,
            "purpose": DRAW_PURPOSE,
            "rank": rank.hex(),
        },
    }


def _recorded_exit(document: dict[str, Any]) -> dict[str, Any] | None:
    """A valid ``exit`` layer is the authority for a regenerated map."""
    layer = document.get(EXIT_LAYER_FIELD)
    if not isinstance(layer, dict):
        return None
    if layer.get("layer_version") != EXIT_LAYER_VERSION:
        return None
    cell_id = layer.get("cell_id")
    if not isinstance(cell_id, str) or cell_id not in walkable_ids(document):
        return None
    graph = adjacency(document)
    targets = reroll_targets(document)
    record = _seed_exit_record(document, cell_id, targets, graph)
    if isinstance(layer.get("port_id"), str) and layer["port_id"]:
        record["port_id"] = layer["port_id"]
    if isinstance(layer.get("threshold_id"), str) and layer["threshold_id"]:
        record["threshold_id"] = layer["threshold_id"]
    record["source"] = "layer"
    return record


def select_exit(document: dict[str, Any]) -> dict[str, Any]:
    """Choose the one static exit for this map.

    The selection runs against the *pre-exit* target map on purpose.  Feeding
    the post-exit eligibility map back in would make the choice depend on
    itself and could hide the direction the exit removes.
    """
    recorded = _recorded_exit(document)
    if recorded is not None:
        return recorded
    targets = reroll_targets(document)
    graph = adjacency(document)
    cells = {str(cell["cell_id"]): cell for cell in document["cells"]}
    spawn = str(document["cells"][0]["cell_id"])
    hits: dict[str, int] = {}
    for target in targets:
        for cell_id in target["target_cells"]:
            hits[cell_id] = hits.get(cell_id, 0) + 1
    candidates = [
        cell_id
        for cell_id in walkable_ids(document)
        if cell_id != spawn
        and cell_id in cells
        and not cells[cell_id].get("landmark")
        and cell_id in graph
    ]
    if not candidates:
        raise ExitSelectionError(
            "no_exit_candidate", "the map has no walkable cell outside the spawn"
        )
    seed = int(document["seed"])
    attempt = int(document.get("attempt", 0))

    def rank(cell_id: str) -> tuple[int, int, int, int, bytes, str]:
        cell = cells[cell_id]
        leaf = 0 if len(graph[cell_id]) == 1 and exit_port(document, cell_id) else 1
        generated = 0 if _is_generated_cell(cell) else 1
        removed = sum(
            target["target_size"]
            for target in targets
            if cell_id in target["target_cells"]
        )
        return (
            hits.get(cell_id, 0),
            leaf,
            removed,
            generated,
            _keyed_rank(seed, attempt, cell_id),
            cell_id,
        )

    chosen = min(candidates, key=rank)
    return _seed_exit_record(document, chosen, targets, graph)


def reroll_eligibility(
    document: dict[str, Any],
    exit_record: dict[str, Any] | str | None = None,
) -> list[dict[str, Any]]:
    """Structural re-roll directions after the static exit is fixed.

    The exit cell removes every direction whose target contains it
    (``exit_inside``); the threshold passage itself is never a re-roll door
    (``exit_threshold_door``).  This function is the post-exit map the later
    slices consume; it is deliberately never an input to :func:`select_exit`.
    """
    exit_cell: str | None = None
    exit_threshold: str | None = None
    if isinstance(exit_record, str):
        exit_cell = exit_record
        port = exit_port(document, exit_cell)
        exit_threshold = port["threshold_id"] if port else None
    elif isinstance(exit_record, dict):
        value = exit_record.get("cell_id")
        if isinstance(value, str):
            exit_cell = value
        value = exit_record.get("threshold_id")
        if isinstance(value, str):
            exit_threshold = value
    result: list[dict[str, Any]] = []
    for target in reroll_targets(document):
        reasons: list[str] = []
        if exit_threshold is not None and target["threshold_id"] == exit_threshold:
            reasons.append("exit_threshold_door")
        if exit_cell is not None and exit_cell in target["target_cells"]:
            reasons.append("exit_inside")
        record = copy.deepcopy(target)
        record["eligible"] = not reasons
        record["reasons"] = reasons
        record["reason"] = reasons[0] if reasons else None
        result.append(record)
    return result


def plan_run(document: dict[str, Any]) -> dict[str, Any]:
    """Select the exit first, then evaluate the re-roll eligibility map."""
    exit_record = select_exit(document)
    eligibility = reroll_eligibility(document, exit_record)
    return {
        "seed": int(document["seed"]),
        "map_id": str(document.get("map_id", "")),
        "exit": exit_record,
        "eligibility": eligibility,
        "eligible_directions": [item for item in eligibility if item["eligible"]],
        "rejected_directions": [item for item in eligibility if not item["eligible"]],
    }


def run_end_spec(
    base: mm.BaseMap,
    exit_record: dict[str, Any],
    event_index: int,
    *,
    occurred_at_utc: str | None = None,
) -> dict[str, Any]:
    """The forced ``run_end`` mutation for crossing the static exit."""
    exit_cell = str(exit_record["cell_id"])
    if exit_cell not in base.cell_ids:
        raise ExitSelectionError(
            "unknown_exit_cell", f"exit {exit_cell} is not in the base map"
        )
    return mm.new_mutation(
        base,
        "run_end",
        event_index,
        target={
            "cell_id": exit_cell,
            "threshold_id": str(exit_record["threshold_id"]),
        },
        stream=RUN_STREAM,
        validation={"outcome": "accepted", "checks": list(RUN_END_CHECKS)},
        occurred_at_utc=occurred_at_utc,
    )


def end_card(base: mm.BaseMap, events: list[dict[str, Any]]) -> dict[str, Any]:
    """The end-card view derived only from the log; it offers no progression."""
    counters = mm.run_counters(events, base=base)
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "RUN ENDED",
        "seed": counters["seed"],
        "map_id": counters["map_id"],
        "rooms_visited": counters["rooms_visited"],
        "edits": counters["edits"],
        "rerolls": counters["rerolls"],
        "run_ended": counters["run_ended"],
        "ended_at_event": counters["ended_at_event"],
        "actions": [],
    }


class ExitRun:
    """In-memory run driver: entry triggers, one exit crossing, one end card."""

    def __init__(
        self,
        base: mm.BaseMap,
        exit_record: dict[str, Any] | None = None,
    ) -> None:
        self.base = base
        self.exit_record = (
            copy.deepcopy(exit_record) if exit_record is not None else select_exit(base.document)
        )
        self.exit_cell = str(self.exit_record["cell_id"])
        self.events: list[dict[str, Any]] = []
        self.overlay = mm.empty_overlay(base)
        self.previous_cell: str | None = None
        self._card: dict[str, Any] | None = None

    @property
    def ended(self) -> bool:
        return bool(self.overlay["run"]["ended"])

    @property
    def state_hash(self) -> str:
        return str(self.overlay["state_hash"])

    def restore(self, events: list[dict[str, Any]]) -> None:
        """Replay a saved log, then continue from it."""
        self.events = [copy.deepcopy(event) for event in events]
        self.overlay = mm.fold_events(self.base, self.events)
        self._card = None
        for event in reversed(self.events):
            trigger = event.get("trigger")
            if isinstance(trigger, dict) and event.get("record_kind") == "trigger":
                value = trigger.get("player_cell") or trigger.get("from_cell")
                if isinstance(value, str):
                    self.previous_cell = value
                    break

    def _append(self, spec: dict[str, Any]) -> dict[str, Any]:
        sealed = mm.seal_event(self.base, self.overlay, spec)
        self.overlay = mm.fold_event(self.base, self.overlay, sealed)
        self.events.append(sealed)
        self._card = None
        return sealed

    def enter_cell(
        self, cell_id: str, *, occurred_at_utc: str | None = None
    ) -> list[dict[str, Any]]:
        """Record one entry; the exit crossing also ends the run exactly once."""
        if cell_id not in self.base.cell_ids:
            raise ExitSelectionError(
                "unknown_cell", f"cell {cell_id} is not in the base map"
            )
        if self.ended:
            return []
        if cell_id == self.exit_cell:
            return self._cross_exit(occurred_at_utc=occurred_at_utc)
        trigger = self._append(
            mm.new_trigger(
                self.base,
                "room_entered",
                len(self.events) + 1,
                player_cell=cell_id,
                occurred_at_utc=occurred_at_utc,
            )
        )
        self.previous_cell = cell_id
        return [trigger]

    def _cross_exit(self, *, occurred_at_utc: str | None = None) -> list[dict[str, Any]]:
        trigger = self._append(
            mm.new_trigger(
                self.base,
                "exit_entered",
                len(self.events) + 1,
                player_cell=self.exit_cell,
                from_cell=self.previous_cell,
                occurred_at_utc=occurred_at_utc,
            )
        )
        end = self._append(
            run_end_spec(
                self.base,
                self.exit_record,
                len(self.events) + 1,
                occurred_at_utc=occurred_at_utc,
            )
        )
        return [trigger, end]

    def card(self) -> dict[str, Any]:
        if self._card is None:
            self._card = end_card(self.base, self.events)
        return copy.deepcopy(self._card)
