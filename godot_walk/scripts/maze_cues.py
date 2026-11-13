"""Follower presence cues for the maze overlay (M9, #239).

The follower is audio-only and occasional: it is never rendered, never
simulated as a body and never chases the player.  This module is the headless
reference for the cue plan and its auditable event record.  It deliberately
does not assert anything about audible output; the operator listen is the
human step.

The cue rules are from ``docs/MAZE_DYNAMICS_PROPOSAL.md`` section 8:

* no cues before the first four rooms;
* one optional cue per follower edit at most;
* at least 8-15 seconds between optional cues, drawn from the same
  ``(seed, attempt, event_index, stream, target, purpose)`` key as the rest of
  the overlay;
* ``follower_step`` is a 1-3 step cue from a cell one or two graph hops away,
  with volume falling by distance;
* ``door_close`` and ``lock_click`` are mandatory on an eligible door;
* ``door_reopen`` is the same latch as ``lock_click`` plus a low room-tone
  tail.  It is never a different door sound.

Cue records are inert ``follower_cue`` mutations.  They are accepted by the M1
event core, stored in the log and folded without changing the overlay state.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

import maze_mutation as mm

RULE = "maze_follower_cues"
STREAM = "follower-cues:gmap-0.13.0"

FOLLOWER_STEP = "follower_step"
DOOR_CLOSE = "door_close"
LOCK_CLICK = "lock_click"
DOOR_REOPEN = "door_reopen"
CUE_KINDS = (FOLLOWER_STEP, DOOR_CLOSE, LOCK_CLICK, DOOR_REOPEN)
MANDATORY_DOOR_CUES = (DOOR_CLOSE, LOCK_CLICK)

# §8.4 pacing defaults.  These are provisional tuning values for the operator
# walk (M14), not a design decision.
FIRST_CUE_VISIT = 5
MIN_GAP_SECONDS = 8
MAX_GAP_SECONDS = 15
MIN_STEPS = 1
MAX_STEPS = 3
STEP_SPACING_SECONDS = 0.35
LOCK_DELAY_SECONDS = 0.12
REOPEN_TAIL_DELAY_SECONDS = 0.28
QUIET_SPEED_MPS = 0.25
QUIET_WAIT_SECONDS = 4.0

# §8.3 mix defaults: fixed lowpass and distance attenuation, no source-room
# reverb probe in v1.
LOWPASS_HZ = 1600.0
REFERENCE_DISTANCE_M = 1.0
STEP_BASE_VOLUME_DB = -12.0
DOOR_BASE_VOLUME_DB = -8.0
TAIL_VOLUME_OFFSET_DB = -6.0
ROLLOFF_DB_PER_DOUBLING = 6.0
STEP_MIN_VOLUME_DB = -45.0
DOOR_MIN_VOLUME_DB = -35.0
MAX_DISTANCE_M = 40.0
CELL_SOURCE_HEIGHT_M = 1.0

STEP_SAMPLE = "res://audio/footsteps/default/body/default_body_01.wav"
STEP_TRANSIENT_SAMPLE = (
    "res://audio/footsteps/default/transient_soft/default_transient_soft_01.wav"
)
DOOR_CLOSE_SAMPLE = (
    "res://audio/footsteps/land/transient_hard/land_transient_hard_01.wav"
)
LOCK_CLICK_SAMPLE = (
    "res://audio/footsteps/metal/transient_hard/metal_transient_hard_01.wav"
)
ROOM_TONE_SAMPLE = "res://audio/footsteps/land/body/land_body_01.wav"


class CuePlanError(ValueError):
    """A cue request is malformed or has no valid source."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CuePlan:
    """One deterministic cue ready to be recorded or played."""

    kind: str
    target: dict[str, str]
    position: tuple[float, float, float]
    graph_distance: int
    distance_m: float
    volume_db: float
    steps: int
    step_spacing_s: float
    delay_s: float
    tail_delay_s: float
    latch_sample: str
    tail_sample: str
    cooldown_s: int
    checks: tuple[str, ...]


def _cells(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for cell in document.get("cells", []):
        if isinstance(cell, dict) and isinstance(cell.get("cell_id"), str):
            result[str(cell["cell_id"])] = cell
    return result


def _is_walkable(cell: dict[str, Any]) -> bool:
    return str(cell.get("role", "ground")) != "void"


def cell_center(cell: dict[str, Any]) -> tuple[float, float]:
    """The envelope centre used as a cue source in the horizontal plane."""
    points = cell.get("envelope_xz", [])
    if not isinstance(points, list) or not points:
        raise CuePlanError("cell_envelope_missing", "cell has no envelope")
    total_x = 0.0
    total_z = 0.0
    for point in points:
        if not isinstance(point, list) or len(point) < 2:
            raise CuePlanError(
                "cell_envelope_invalid", "cell envelope point is invalid"
            )
        total_x += float(point[0])
        total_z += float(point[1])
    count = float(len(points))
    return total_x / count, total_z / count


def cell_position(cell: dict[str, Any]) -> tuple[float, float, float]:
    """A cue source position: envelope centre just above the cell floor."""
    x, z = cell_center(cell)
    return x, float(cell.get("floor_y", 0.0)) + CELL_SOURCE_HEIGHT_M, z


def distance_m(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> float:
    return math.dist(left, right)


def volume_at_distance(
    distance: float,
    *,
    base_db: float = STEP_BASE_VOLUME_DB,
    minimum_db: float = STEP_MIN_VOLUME_DB,
) -> float:
    """Fixed distance attenuation: -6 dB per doubling from one metre."""
    effective = max(float(distance), REFERENCE_DISTANCE_M)
    value = base_db - ROLLOFF_DB_PER_DOUBLING * math.log2(
        effective / REFERENCE_DISTANCE_M
    )
    return max(value, minimum_db)


def cooldown_seconds(
    base: mm.BaseMap,
    event_index: int,
    *,
    stream: str = STREAM,
) -> int:
    """A deterministic 8-15 second gap for one optional cue."""
    draw = mm.draw_for_event(
        base.seed,
        base.attempt,
        event_index,
        stream,
        "cue",
        "cooldown",
    )
    return MIN_GAP_SECONDS + draw % (MAX_GAP_SECONDS - MIN_GAP_SECONDS + 1)


def traversal_adjacency(document: dict[str, Any]) -> dict[str, set[str]]:
    """Undirected direct passages, including one-way drop links."""
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


def graph_distances(
    document: dict[str, Any], start: str, *, max_depth: int = 2
) -> dict[str, int]:
    """Bounded breadth-first graph distance from ``start``."""
    adjacency = traversal_adjacency(document)
    if start not in adjacency:
        return {}
    distances = {start: 0}
    frontier = [start]
    for depth in range(1, max_depth + 1):
        next_frontier: list[str] = []
        for current in frontier:
            for neighbor in sorted(adjacency[current]):
                if neighbor in distances:
                    continue
                distances[neighbor] = depth
                next_frontier.append(neighbor)
        frontier = next_frontier
        if not frontier:
            break
    return distances


def select_step_source(
    base: mm.BaseMap,
    *,
    player_cell: str,
    event_index: int,
    exit_cell: str | None = None,
    stream: str = STREAM,
) -> str | None:
    """Pick a cell one or two graph hops away, preferring the distant ring."""
    distances = graph_distances(base.document, player_cell, max_depth=2)
    cells = _cells(base.document)
    candidates = [
        cell_id
        for cell_id, hops in distances.items()
        if hops in (1, 2)
        and cell_id != player_cell
        and cell_id != exit_cell
        and cell_id in cells
        and _is_walkable(cells[cell_id])
    ]
    if not candidates:
        return None
    distant = [cell_id for cell_id in candidates if distances[cell_id] == 2]
    pool = distant or candidates
    return min(
        pool,
        key=lambda cell_id: mm.draw_for_event(
            base.seed,
            base.attempt,
            event_index,
            stream,
            cell_id,
            "step-source",
        ),
    )


def _step_count(
    base: mm.BaseMap, source_cell: str, event_index: int, stream: str
) -> int:
    draw = mm.draw_for_event(
        base.seed,
        base.attempt,
        event_index,
        stream,
        source_cell,
        "step-count",
    )
    return MIN_STEPS + draw % (MAX_STEPS - MIN_STEPS + 1)


def plan_step_cue(
    base: mm.BaseMap,
    *,
    player_cell: str,
    player_position: tuple[float, float, float],
    event_index: int,
    visit_count: int,
    exit_cell: str | None = None,
    stream: str = STREAM,
) -> CuePlan | None:
    """Plan one optional presence cue for a follower edit.

    Returns ``None`` for the first four rooms, when no cell is one or two hops
    away, or when the nearest possible source is too far for the cue mix.
    Timing and the quiet-player preference are enforced by the caller.
    """
    if visit_count < FIRST_CUE_VISIT:
        return None
    source = select_step_source(
        base,
        player_cell=player_cell,
        event_index=event_index,
        exit_cell=exit_cell,
        stream=stream,
    )
    if source is None:
        return None
    cells = _cells(base.document)
    position = cell_position(cells[source])
    measured = distance_m(player_position, position)
    if measured > MAX_DISTANCE_M:
        return None
    hops = graph_distances(base.document, player_cell, max_depth=2)[source]
    steps = _step_count(base, source, event_index, stream)
    return CuePlan(
        kind=FOLLOWER_STEP,
        target={"cell_id": source},
        position=position,
        graph_distance=hops,
        distance_m=measured,
        volume_db=volume_at_distance(measured),
        steps=steps,
        step_spacing_s=STEP_SPACING_SECONDS,
        delay_s=0.0,
        tail_delay_s=0.0,
        latch_sample=STEP_TRANSIENT_SAMPLE,
        tail_sample=STEP_SAMPLE,
        cooldown_s=cooldown_seconds(base, event_index, stream=stream),
        checks=(
            "after_four_rooms",
            "graph_distance_one_to_two",
            "one_cue_per_edit",
            "volume_by_distance",
            "audio_only",
            "inert_cue",
        ),
    )


def _door_position(
    document: dict[str, Any], door: dict[str, Any]
) -> tuple[float, float, float]:
    cells = _cells(document)
    for port_field in ("port_a", "port_b"):
        port_id = str(door.get(port_field, ""))
        cell_id = port_id.partition(":")[0]
        cell = cells.get(cell_id)
        if cell is None:
            continue
        for port in cell.get("required_ports", []):
            if str(port.get("port_id", "")) != port_id:
                continue
            pos = port.get("pos_xz")
            if isinstance(pos, list) and len(pos) >= 2:
                return (
                    float(pos[0]),
                    float(cell.get("floor_y", 0.0)) + CELL_SOURCE_HEIGHT_M,
                    float(pos[1]),
                )
        return cell_position(cell)
    raise CuePlanError("door_position_missing", "door has no usable port position")


def plan_door_cue(
    document: dict[str, Any],
    kind: str,
    door: dict[str, Any],
    *,
    player_position: tuple[float, float, float],
    cooldown_s: int = 0,
    volume_db: float | None = None,
    delay_s: float = 0.0,
) -> CuePlan:
    """Plan one mandatory door cue.  Door cues bypass the optional cadence."""
    if kind not in (DOOR_CLOSE, LOCK_CLICK, DOOR_REOPEN):
        raise CuePlanError("cue_kind_invalid", f"unknown door cue {kind}")
    position = _door_position(document, door)
    measured = distance_m(player_position, position)
    if volume_db is None:
        volume_db = volume_at_distance(
            measured,
            base_db=DOOR_BASE_VOLUME_DB,
            minimum_db=DOOR_MIN_VOLUME_DB,
        )
    checks: tuple[str, ...]
    if kind == DOOR_CLOSE:
        checks = (
            "mandatory_door_contract",
            "door_close_before_latch",
            "volume_by_distance",
            "audio_only",
            "inert_cue",
        )
    elif kind == LOCK_CLICK:
        checks = (
            "mandatory_door_contract",
            "lock_click_after_close",
            "volume_by_distance",
            "audio_only",
            "inert_cue",
        )
    else:
        checks = (
            "mandatory_door_contract",
            "same_latch_as_lock_click",
            "room_tone_tail",
            "volume_by_distance",
            "audio_only",
            "inert_cue",
        )
    return CuePlan(
        kind=kind,
        target={"threshold_id": str(door.get("threshold_id", ""))},
        position=position,
        graph_distance=0,
        distance_m=measured,
        volume_db=volume_db,
        steps=0,
        step_spacing_s=0.0,
        delay_s=delay_s,
        tail_delay_s=REOPEN_TAIL_DELAY_SECONDS if kind == DOOR_REOPEN else 0.0,
        latch_sample=LOCK_CLICK_SAMPLE
        if kind in (LOCK_CLICK, DOOR_REOPEN)
        else DOOR_CLOSE_SAMPLE,
        tail_sample=ROOM_TONE_SAMPLE if kind == DOOR_REOPEN else "",
        cooldown_s=cooldown_s,
        checks=checks,
    )


def cue_payload(plan: CuePlan, *, player_cell: str = "") -> dict[str, Any]:
    """Serialise one plan into the auditable ``cue`` block."""
    payload: dict[str, Any] = {
        "kind": plan.kind,
        "target": copy.deepcopy(plan.target),
        "position": [round(value, 6) for value in plan.position],
        "graph_distance": plan.graph_distance,
        "distance_m": round(plan.distance_m, 6),
        "volume_db": round(plan.volume_db, 6),
        "steps": plan.steps,
        "step_spacing_s": plan.step_spacing_s,
        "delay_s": plan.delay_s,
        "tail_delay_s": plan.tail_delay_s,
        "latch_sample": plan.latch_sample,
        "tail_sample": plan.tail_sample,
        "cooldown_s": plan.cooldown_s,
        "visible_nodes": 0,
    }
    if player_cell:
        payload["player_cell"] = player_cell
    return payload


def cue_event_spec(
    base: mm.BaseMap,
    plan: CuePlan,
    *,
    event_index: int,
    player_cell: str = "",
    source_event_index: int | None = None,
    outcome: str = "accepted",
) -> dict[str, Any]:
    """Build the inert ``follower_cue`` mutation record for one plan."""
    event = mm.new_mutation(
        base,
        "follower_cue",
        event_index,
        target=plan.target,
        stream=STREAM,
        validation={"outcome": outcome, "checks": list(plan.checks)},
    )
    event["cue"] = cue_payload(plan, player_cell=player_cell)
    if source_event_index is not None:
        event["source_event_index"] = source_event_index
    return event


@dataclass
class CueTrack:
    """Small deterministic timing gate used by the Python reference tests.

    The runtime equivalent is ``maze_follower_cues.gd``.  This track applies
    the same visit, quiet-player and 8-15 second rules without a scene tree.
    """

    base: mm.BaseMap
    exit_cell: str | None = None
    stream: str = STREAM
    clock_s: float = 0.0
    visit_count: int = 0
    current_cell: str = ""
    next_allowed_s: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)
    visited: set[str] = field(default_factory=set)

    def advance(self, seconds: float) -> None:
        self.clock_s += max(0.0, float(seconds))

    def enter_cell(self, cell_id: str) -> None:
        self.current_cell = cell_id
        self.visited.add(cell_id)
        self.visit_count = len(self.visited)

    def ready(self) -> bool:
        return self.clock_s >= self.next_allowed_s

    def request_step(
        self,
        *,
        player_position: tuple[float, float, float],
        event_index: int,
        quiet: bool = True,
    ) -> CuePlan | None:
        """One optional cue for one edit, or ``None`` when it is suppressed."""
        if self.visit_count < FIRST_CUE_VISIT or not quiet or not self.ready():
            return None
        plan = plan_step_cue(
            self.base,
            player_cell=self.current_cell,
            player_position=player_position,
            event_index=event_index,
            visit_count=self.visit_count,
            exit_cell=self.exit_cell,
            stream=self.stream,
        )
        if plan is None:
            return None
        self.next_allowed_s = self.clock_s + plan.cooldown_s
        self.events.append(
            cue_event_spec(
                self.base,
                plan,
                event_index=len(self.events) + 1,
                player_cell=self.current_cell,
                source_event_index=event_index,
            )
        )
        return plan

    def latch_door(
        self,
        door: dict[str, Any],
        *,
        player_position: tuple[float, float, float],
        event_index: int,
    ) -> list[CuePlan]:
        """Mandatory door_close followed by lock_click."""
        cooldown = cooldown_seconds(self.base, event_index, stream=self.stream)
        close = plan_door_cue(
            self.base.document,
            DOOR_CLOSE,
            door,
            player_position=player_position,
            cooldown_s=cooldown,
        )
        latch = plan_door_cue(
            self.base.document,
            LOCK_CLICK,
            door,
            player_position=player_position,
            cooldown_s=cooldown,
            volume_db=close.volume_db,
            delay_s=LOCK_DELAY_SECONDS,
        )
        for plan in (close, latch):
            self.events.append(
                cue_event_spec(
                    self.base,
                    plan,
                    event_index=len(self.events) + 1,
                    player_cell=self.current_cell,
                    source_event_index=event_index,
                )
            )
        self.next_allowed_s = self.clock_s + close.cooldown_s
        return [close, latch]

    def reopen_door(
        self,
        door: dict[str, Any],
        *,
        player_position: tuple[float, float, float],
        event_index: int,
    ) -> CuePlan:
        """The re-roll reveal: the same latch plus a room-tone tail."""
        plan = plan_door_cue(
            self.base.document,
            DOOR_REOPEN,
            door,
            player_position=player_position,
            cooldown_s=cooldown_seconds(self.base, event_index, stream=self.stream),
        )
        self.events.append(
            cue_event_spec(
                self.base,
                plan,
                event_index=len(self.events) + 1,
                player_cell=self.current_cell,
                source_event_index=event_index,
            )
        )
        self.next_allowed_s = self.clock_s + plan.cooldown_s
        return plan

    def state_hash_unchanged(self) -> bool:
        """A cue log folds into the empty overlay without changing its hash."""
        before = mm.empty_overlay(self.base)["state_hash"]
        sealed = mm.seal_log(self.base, self.events)
        after = mm.fold_events(self.base, sealed)["state_hash"]
        return before == after
