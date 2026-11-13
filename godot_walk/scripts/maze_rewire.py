"""Derived-spec rebuild and reveal contract for the M6 re-roll (#236).

The M5 enumerator chooses a passage set ``P`` on the existing footprint. This
module turns the stored ``door_reroll`` event into a runtime room spec:

* remove only the doorway records for passages in ``E_T \\ P``;
* add one open doorway record for every passage in ``P \\ E_T`` at the stored
  center, reusing the cell envelope and the existing shape-room builder;
* copy every other field unchanged and bump ``passage_revision``;
* reject a doorway that does not fit its wall, overlaps a kept opening or cuts a
  content-pinned cell;
* validate F0-F2 on the current traversal graph.

The committed map and shape-room files are only read. The derived spec is an
in-memory copy; ``maze_rewire.gd`` is the runtime twin and
``fixtures/maze_rewire_v1.json`` is the shared fixture.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gmap_elevation as ge
import maze_doors as md
import maze_exit as me
import maze_follower as mf
import maze_reroll as mr
from deterministic_json import ROOT, canonical_bytes

RUNTIME_LAYER_VERSION = "maze-rewire-runtime-0.1.0"
STATE_HASH_PREFIX = "maze-rewire-state-0.1.0"
# Replay applies a stored ``P`` by its recorded algorithm version.  A newer
# enumerator must not reinterpret an older event, so this set is deliberately
# independent of the current ``rewire-1`` enumerator contract.
SUPPORTED_ALGORITHM_VERSIONS = frozenset({"rewire-1"})
PORT_PREFIX = "rw_"
DOOR_WIDTH_M = 1.4
DOOR_HEIGHT_M = 2.2
DOORWAY_MARGIN_M = 0.2
DOORWAY_COMPATIBILITY_TYPE = "maze_rewire_1_4m_v1"
INTERNAL_FLAG = "rewire_internal"
MIN_CEILING_CLEARANCE_M = 0.05
EPSILON = 1e-9

ALLOWED_SPEC_FIELDS = frozenset(
    {"doorways", "features", "degenerate_port_ids", "passage_revision"}
)
RUNTIME_CHECKS = (
    "F0",
    "F1",
    "F2",
    "geometry",
    "cell_identity",
    "not_visible",
)
SEEDS = (1, 2, 3, 32, 279)


def port_id(cell_id: str, other_cell_id: str) -> str:
    return f"{cell_id}:{PORT_PREFIX}{other_cell_id}"


def pair_key(left: str, right: str) -> str:
    return f"{left}|{right}" if left < right else f"{right}|{left}"


def pair_cells(key: str) -> tuple[str, str]:
    left, right = key.split("|", 1)
    return left, right


def _pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def wall_normal(
    cell: dict[str, Any], other: dict[str, Any], wall: dict[str, Any]
) -> tuple[float, float] | None:
    rect_cell = mr._rect(cell)
    rect_other = mr._rect(other)
    if rect_cell is None or rect_other is None:
        return None
    ax0, az0, ax1, az1 = rect_cell
    bx0, bz0, bx1, bz1 = rect_other
    if wall.get("axis") == "x":
        if abs(ax1 - bx0) <= EPSILON:
            return (1.0, 0.0)
        if abs(bx1 - ax0) <= EPSILON:
            return (-1.0, 0.0)
        return None
    if abs(az1 - bz0) <= EPSILON:
        return (0.0, 1.0)
    if abs(bz1 - az0) <= EPSILON:
        return (0.0, -1.0)
    return None


def doorway_record(
    cell_id: str,
    other_cell_id: str,
    event_record: dict[str, Any],
    cells: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    cell = cells.get(cell_id)
    other = cells.get(other_cell_id)
    if cell is None or other is None:
        return None
    wall = mr.shared_wall(cell, other)
    if wall is None:
        return None
    normal = wall_normal(cell, other, wall)
    if normal is None:
        return None
    center = event_record.get("center_xz")
    if not isinstance(center, list) or len(center) != 2:
        return None
    return {
        "port_id": port_id(cell_id, other_cell_id),
        "to_port_id": port_id(other_cell_id, cell_id),
        "to_cell_id": other_cell_id,
        "pos_xz": [float(center[0]), float(center[1])],
        "normal": [normal[0], normal[1]],
        "width_m": float(event_record.get("width_m", DOOR_WIDTH_M)),
        "height_m": float(event_record.get("height_m", DOOR_HEIGHT_M)),
        "sill_height_m": 0.0,
        "kind": "open",
        "vertical": "level",
        "compatibility_type": DOORWAY_COMPATIBILITY_TYPE,
        INTERNAL_FLAG: True,
    }


def _remove_doorway(spec: dict[str, Any], other_cell_id: str) -> list[str]:
    removed: list[str] = []
    kept: list[dict[str, Any]] = []
    for doorway in spec.get("doorways", []):
        if str(doorway.get("to_cell_id", "")) == other_cell_id:
            removed.append(str(doorway.get("port_id", "")))
            continue
        kept.append(doorway)
    spec["doorways"] = kept
    if not removed:
        return removed
    spec["features"] = [
        feature
        for feature in spec.get("features", [])
        if not (
            str(feature.get("kind", "")) == "doorway"
            and str(feature.get("feature_id", "")).removeprefix("doorway:") in removed
        )
    ]
    spec["degenerate_port_ids"] = [
        port for port in spec.get("degenerate_port_ids", []) if port not in removed
    ]
    return removed


def _add_doorway(
    spec: dict[str, Any], other_cell_id: str, record: dict[str, Any]
) -> bool:
    for doorway in spec.get("doorways", []):
        if str(doorway.get("to_cell_id", "")) == other_cell_id:
            return False
    spec.setdefault("doorways", []).append(record)
    spec.setdefault("features", []).append(
        {
            "feature_id": "doorway:" + str(record["port_id"]),
            "kind": "doorway",
            "sign": "symbol",
        }
    )
    return True


def _content_pinned(cell: dict[str, Any]) -> bool:
    return any(
        cell.get(key) is not None for key in ("module", "landmark", "diagonal_passage")
    )


def derive_specs(
    document: dict[str, Any],
    base_specs: dict[str, dict[str, Any]],
    event: dict[str, Any],
) -> dict[str, Any]:
    """Build the derived spec copy for every cell whose doorway set changes."""
    rewire = event.get("rewire")
    if not isinstance(rewire, dict):
        return {
            "ok": False,
            "reason": "rewire_invalid",
            "specs": {},
            "changed_cells": [],
        }
    before = {_pair(*pair) for pair in rewire.get("passages_before", [])}
    after = {_pair(*pair) for pair in rewire.get("passages_after", [])}
    record_by_pair = {
        _pair(str(record.get("cell_a", "")), str(record.get("cell_b", ""))): record
        for record in rewire.get("doorways", [])
        if str(record.get("action", "")) == "opened"
    }
    cells = mr.cells_by_id(document)
    working: dict[str, dict[str, Any]] = {}
    changed: set[str] = set()
    for key in sorted(before - after):
        left, right = key
        for cell_id, other in ((left, right), (right, left)):
            if cell_id not in base_specs:
                if cell_id in cells and _content_pinned(cells[cell_id]):
                    return {
                        "ok": False,
                        "reason": "content_pinned_change",
                        "specs": {},
                        "changed_cells": [],
                    }
                return {
                    "ok": False,
                    "reason": "missing_spec",
                    "specs": {},
                    "changed_cells": [],
                }
            spec = working.setdefault(cell_id, copy.deepcopy(base_specs[cell_id]))
            if not _remove_doorway(spec, other):
                return {
                    "ok": False,
                    "reason": "missing_doorway",
                    "specs": {},
                    "changed_cells": [],
                }
            changed.add(cell_id)
    for key in sorted(after - before):
        left, right = key
        event_record = record_by_pair.get(key)
        if event_record is None:
            return {
                "ok": False,
                "reason": "missing_doorway",
                "specs": {},
                "changed_cells": [],
            }
        for cell_id in (left, right):
            if cell_id not in base_specs:
                if cell_id in cells and _content_pinned(cells[cell_id]):
                    return {
                        "ok": False,
                        "reason": "content_pinned_change",
                        "specs": {},
                        "changed_cells": [],
                    }
                return {
                    "ok": False,
                    "reason": "missing_spec",
                    "specs": {},
                    "changed_cells": [],
                }
            if cell_id in cells and _content_pinned(cells[cell_id]):
                return {
                    "ok": False,
                    "reason": "content_pinned_change",
                    "specs": {},
                    "changed_cells": [],
                }
        for cell_id, other in ((left, right), (right, left)):
            spec = working.setdefault(cell_id, copy.deepcopy(base_specs[cell_id]))
            record = doorway_record(cell_id, other, event_record, cells)
            if record is None:
                return {
                    "ok": False,
                    "reason": "geometry_conflict",
                    "specs": {},
                    "changed_cells": [],
                }
            if not _add_doorway(spec, other, record):
                return {
                    "ok": False,
                    "reason": "doorway_conflict",
                    "specs": {},
                    "changed_cells": [],
                }
            changed.add(cell_id)
    result: dict[str, Any] = {}
    for cell_id, spec in working.items():
        spec["passage_revision"] = (
            int(base_specs[cell_id].get("passage_revision", 0)) + 1
        )
        result[cell_id] = spec
    return {"ok": True, "reason": "", "specs": result, "changed_cells": sorted(changed)}


def identity_issues(base: dict[str, Any], derived: dict[str, Any]) -> list[str]:
    """Fields that must not change between the base spec and the derived copy."""
    issues: list[str] = []
    for key in set(base) | set(derived):
        if key in ALLOWED_SPEC_FIELDS:
            continue
        if base.get(key) != derived.get(key):
            issues.append(f"{derived.get('cell_id', '')}:{key}")
    base_features = [
        feature
        for feature in base.get("features", [])
        if feature.get("kind") != "doorway"
    ]
    derived_features = [
        feature
        for feature in derived.get("features", [])
        if feature.get("kind") != "doorway"
    ]
    if base_features != derived_features:
        issues.append(f"{derived.get('cell_id', '')}:features")
    base_ports = set(base.get("degenerate_port_ids", []))
    if any(port not in base_ports for port in derived.get("degenerate_port_ids", [])):
        issues.append(f"{derived.get('cell_id', '')}:degenerate_port_ids")
    if (
        int(derived.get("passage_revision", 0))
        != int(base.get("passage_revision", 0)) + 1
    ):
        issues.append(f"{derived.get('cell_id', '')}:passage_revision")
    return issues


def _interval_on_wall(
    doorway: dict[str, Any], wall: dict[str, Any]
) -> tuple[float, float] | None:
    position = doorway.get("pos_xz")
    if not isinstance(position, list) or len(position) != 2:
        return None
    half = float(doorway.get("width_m", 0.0)) / 2.0
    if wall.get("axis") == "x":
        return (float(position[1]) - half, float(position[1]) + half)
    return (float(position[0]) - half, float(position[0]) + half)


def _overlaps_kept(
    doorway: dict[str, Any],
    cell_id: str,
    other_cell_id: str,
    specs: dict[str, dict[str, Any]],
    wall: dict[str, Any],
) -> bool:
    interval = _interval_on_wall(doorway, wall)
    if interval is None:
        return True
    for spec_cell in (cell_id, other_cell_id):
        spec = specs.get(spec_cell)
        if spec is None:
            continue
        for kept in spec.get("doorways", []):
            kept_to = str(kept.get("to_cell_id", ""))
            # Both sides of the new opening belong to the new pair.
            if (spec_cell == cell_id and kept_to == other_cell_id) or (
                spec_cell == other_cell_id and kept_to == cell_id
            ):
                continue
            kept_interval = _interval_on_wall(kept, wall)
            if kept_interval is None:
                continue
            position = kept.get("pos_xz")
            if not isinstance(position, list) or len(position) != 2:
                continue
            line = float(position[0]) if wall.get("axis") == "x" else float(position[1])
            if abs(line - float(wall.get("line", 0.0))) > 1e-6:
                continue
            separated = (
                interval[1] + DOORWAY_MARGIN_M <= kept_interval[0]
                or kept_interval[1] + DOORWAY_MARGIN_M <= interval[0]
            )
            if not separated:
                return True
    return False


def _ceiling_height(
    cell: dict[str, Any], specs: dict[str, dict[str, Any]], cell_id: str
) -> float:
    spec = specs.get(cell_id, {})
    value = float(spec.get("ceiling_height_m", 0.0))
    if value > 0.0:
        return value
    ceiling_range = cell.get("ceiling_range_m")
    if isinstance(ceiling_range, list) and ceiling_range:
        return float(ceiling_range[-1])
    return 0.0


def geometry_issues(
    document: dict[str, Any],
    base_specs: dict[str, dict[str, Any]],
    derived_specs: dict[str, dict[str, Any]],
    event: dict[str, Any],
) -> list[str]:
    """Geometry and identity checks for one accepted event; empty means valid."""
    issues: list[str] = []
    rewire = event.get("rewire", {})
    cells = mr.cells_by_id(document)
    for cell_id, derived in derived_specs.items():
        issues.extend(identity_issues(base_specs.get(cell_id, {}), derived))
    for record in rewire.get("doorways", []):
        if str(record.get("action", "")) != "opened":
            continue
        cell_a = str(record.get("cell_a", ""))
        cell_b = str(record.get("cell_b", ""))
        if cell_a not in cells or cell_b not in cells:
            issues.append("missing_cell")
            continue
        wall = mr.shared_wall(cells[cell_a], cells[cell_b])
        if wall is None or wall["length_m"] + EPSILON < mr.MIN_SHARED_WALL_M:
            issues.append(f"wall_too_short:{cell_a}|{cell_b}")
            continue
        if _content_pinned(cells[cell_a]) or _content_pinned(cells[cell_b]):
            issues.append(f"content_pinned_change:{cell_a}|{cell_b}")
            continue
        width = float(record.get("width_m", DOOR_WIDTH_M))
        center = record.get("center_xz")
        if not isinstance(center, list) or len(center) != 2 or width <= 0.0:
            issues.append(f"doorway_invalid:{cell_a}|{cell_b}")
            continue
        low = wall["start"] + DOORWAY_MARGIN_M + width / 2.0
        high = wall["end"] - DOORWAY_MARGIN_M - width / 2.0
        along = float(center[1]) if wall["axis"] == "x" else float(center[0])
        if low > high + EPSILON or along < low - EPSILON or along > high + EPSILON:
            issues.append(f"doorway_outside_wall:{cell_a}|{cell_b}")
            continue
        height = float(record.get("height_m", DOOR_HEIGHT_M))
        for cell_id in (cell_a, cell_b):
            ceiling = _ceiling_height(cells[cell_id], derived_specs, cell_id)
            if ceiling > 0.0 and height + MIN_CEILING_CLEARANCE_M > ceiling:
                issues.append(f"doorway_too_tall:{cell_a}|{cell_b}")
                break
        for cell_id, other in ((cell_a, cell_b), (cell_b, cell_a)):
            if cell_id not in derived_specs:
                issues.append(f"missing_spec:{cell_id}")
                continue
            normal = wall_normal(cells[cell_id], cells[other], wall)
            if normal is None:
                issues.append(f"missing_normal:{cell_id}")
                continue
            found = False
            for doorway in derived_specs[cell_id].get("doorways", []):
                if str(doorway.get("port_id", "")) != port_id(cell_id, other):
                    continue
                found = True
                if _overlaps_kept(doorway, cell_id, other, derived_specs, wall):
                    issues.append(f"doorway_overlap:{cell_a}|{cell_b}")
            if not found:
                issues.append(f"missing_doorway:{cell_id}")
    return issues


def apply_event_to_state(
    state: dict[str, Any], event: dict[str, Any]
) -> dict[str, Any]:
    """Refuse a stale event and apply its stored passage delta in order."""
    rewire = event.get("rewire")
    if not isinstance(rewire, dict):
        return {"ok": False, "reason": "rewire_invalid", "state": state}
    if str(rewire.get("algorithm_version", "")) not in SUPPORTED_ALGORITHM_VERSIONS:
        return {"ok": False, "reason": "unsupported_algorithm", "state": state}
    target = {str(cell) for cell in rewire.get("target_cells", [])}
    before = {_pair(*pair) for pair in rewire.get("passages_before", [])}
    after = {_pair(*pair) for pair in rewire.get("passages_after", [])}
    current = {pair for pair in state if pair[0] in target and pair[1] in target}
    if current != before:
        return {"ok": False, "reason": "passages_before_mismatch", "state": state}
    result = copy.deepcopy(state)
    for pair in before - after:
        result.pop(pair, None)
    for pair in after - before:
        result[pair] = {"vertical": "level"}
    return {"ok": True, "reason": "", "state": result}


def state_hash(
    state: dict[str, Any],
    revisions: dict[str, int],
    branch_epoch: int,
    reroll_serial: int,
) -> str:
    payload = STATE_HASH_PREFIX + "\n"
    payload += f"branch_epoch={branch_epoch}\n"
    payload += f"reroll_serial={reroll_serial}\n"
    for key in sorted(pair_key(*pair) for pair in state):
        left, right = pair_cells(key)
        payload += f"{key}={state[(left, right)].get('vertical', 'level')}\n"
    for cell_id in sorted(revisions):
        payload += f"{cell_id}={int(revisions[cell_id])}\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _directed_edges(state: dict[str, Any]) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for key in sorted(pair_key(*pair) for pair in state):
        left, right = pair_cells(key)
        record = state[(left, right)]
        if record.get("vertical") == "drop":
            edges.append(
                (str(record.get("upper", left)), str(record.get("lower", right)))
            )
        else:
            edges.append((left, right))
            edges.append((right, left))
    return edges


def _reachable(edges: list[tuple[str, str]], start: str) -> set[str]:
    graph: dict[str, set[str]] = {}
    for left, right in edges:
        graph.setdefault(left, set()).add(right)
    seen = {start}
    queue = [start]
    head = 0
    while head < len(queue):
        current = queue[head]
        head += 1
        for neighbour in sorted(graph.get(current, set())):
            if neighbour in seen:
                continue
            seen.add(neighbour)
            queue.append(neighbour)
    return seen


def f0_f1_f2(
    document: dict[str, Any],
    state: dict[str, Any],
    player_cell: str,
    exit_cell: str,
) -> dict[str, Any]:
    ids = sorted(
        cell["cell_id"] for cell in document["cells"] if cell.get("role") != "void"
    )
    edges = _directed_edges(state)
    failures: list[str] = []
    f0 = ge.strongly_connected(ids, edges)
    if not f0:
        failures.append("F0")
    from_player = _reachable(edges, player_cell)
    f1 = bool(exit_cell) and exit_cell in from_player
    if not f1:
        failures.append("F1")
    f2 = all(exit_cell in _reachable(edges, cell_id) for cell_id in from_player)
    if not f2:
        failures.append("F2")
    return {
        "F0": f0,
        "F1": f1,
        "F2": f2,
        "failures": failures,
        "reachable_from_player": sorted(from_player),
    }


def build_event(
    document: dict[str, Any],
    from_cell: str,
    to_cell: str,
    event_index: int,
    *,
    exit_cell: str | None = None,
    visible_cells: set[str] | None = None,
    reroll_serial: int = 1,
) -> dict[str, Any]:
    plan = mr.plan_reroll(
        document,
        from_cell,
        to_cell,
        event_index,
        exit_cell=exit_cell,
        visible_cells=visible_cells,
    )
    if not plan.get("ok"):
        return {
            "ok": False,
            "reason": plan.get("reason", "no_candidate"),
            "plan": plan,
            "event": {},
        }
    draw = plan["draw"]
    event = {
        "schema_version": 1,
        "event_index": event_index,
        "record_kind": "mutation",
        "event_type": "door_reroll",
        "target": {
            "cell_id": plan["root_cell_id"],
            "port_id": plan["threshold_id"],
            "threshold_id": plan["threshold_id"],
            "branch_root": plan["root_cell_id"],
            "door_threshold_id": plan["door_threshold_id"],
            "from_cell": from_cell,
            "to_cell": to_cell,
        },
        "stream": mr.EVENT_STREAM,
        "rewire": mr.rewire_block(document, plan, event_index),
        "draw": {
            "purpose": draw["purpose"],
            "index": draw["index"],
            "reroll_serial": reroll_serial,
            "branch_attempt": draw["chosen_rank"],
        },
        "validation": {
            "outcome": "accepted",
            "checks": list(plan.get("checks", [])) + list(RUNTIME_CHECKS),
        },
    }
    if visible_cells is not None:
        event["visibility"] = {
            "player_cell": to_cell,
            "visible_cells": sorted(visible_cells),
            "target_hidden": not bool(set(plan["target_cells"]) & set(visible_cells)),
        }
    return {"ok": True, "reason": "", "plan": plan, "event": event}


def load_specs(map_id: str) -> dict[str, dict[str, Any]]:
    root = ROOT / "godot_walk/room_catalog/shape_rooms" / map_id
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    return {
        str(entry["cell_id"]): json.loads(
            (root / str(entry["file"])).read_text(encoding="utf-8")
        )
        for entry in index["rooms"]
    }


def map_path(seed: int) -> Path:
    return (
        ROOT
        / "godot_walk/room_catalog/generative_maps"
        / f"gmap-{seed}-gmap-0.13.0.json"
    )


def _spec_projection(spec: dict[str, Any]) -> dict[str, Any]:
    doorways = []
    for doorway in sorted(
        spec.get("doorways", []), key=lambda item: str(item.get("port_id", ""))
    ):
        doorways.append(
            {
                "port_id": str(doorway.get("port_id", "")),
                "to_cell_id": str(doorway.get("to_cell_id", "")),
                "pos_xz": [float(value) for value in doorway.get("pos_xz", [])],
                "normal": [float(value) for value in doorway.get("normal", [])],
                "width_m": float(doorway.get("width_m", 0.0)),
                "height_m": float(doorway.get("height_m", 0.0)),
                "kind": str(doorway.get("kind", "")),
                "sill_height_m": float(doorway.get("sill_height_m", 0.0)),
                INTERNAL_FLAG: bool(doorway.get(INTERNAL_FLAG, False)),
            }
        )
    return {
        "cell_id": str(spec.get("cell_id", "")),
        "passage_revision": int(spec.get("passage_revision", 0)),
        "doorways": doorways,
    }


def _case(
    seed: int,
    from_cell: str,
    to_cell: str,
    event_index: int,
    *,
    visible: bool,
) -> dict[str, Any]:
    document = json.loads(map_path(seed).read_text(encoding="utf-8"))
    specs = load_specs(str(document["map_id"]))
    exit_record = me.select_exit(document)
    door = md.door_by_threshold(
        md.plan(document, specs, exit_record), mr.door_threshold_id(from_cell, to_cell)
    )
    visible_cells: set[str] | None = None
    if visible and door is not None:
        visible_cells = set(
            mf.visible_cells(
                document,
                to_cell,
                door_states={door["port_a"]: "latched", door["port_b"]: "latched"},
            )
        )
    built = build_event(
        document,
        from_cell,
        to_cell,
        event_index,
        exit_cell=str(exit_record.get("cell_id", "")),
        visible_cells=visible_cells,
    )
    if not built["ok"]:
        return {
            "map_id": str(document["map_id"]),
            "seed": seed,
            "from_cell": from_cell,
            "to_cell": to_cell,
            "event_index": event_index,
            "ok": False,
            "reason": built["reason"],
        }
    event = built["event"]
    base_state = mr.base_passage_state(document)
    applied = apply_event_to_state(base_state, event)
    derived = derive_specs(document, specs, event)
    issues = geometry_issues(document, specs, derived.get("specs", {}), event)
    graph = f0_f1_f2(
        document, applied["state"], to_cell, str(exit_record.get("cell_id", ""))
    )
    revisions = {
        cell_id: int(spec.get("passage_revision", 0))
        for cell_id, spec in derived.get("specs", {}).items()
    }
    rewire = event["rewire"]
    return {
        "map_id": str(document["map_id"]),
        "seed": seed,
        "from_cell": from_cell,
        "to_cell": to_cell,
        "event_index": event_index,
        "ok": bool(derived.get("ok", False))
        and not issues
        and all(graph[key] for key in ("F0", "F1", "F2")),
        "reason": (
            derived.get("reason", "")
            if not derived.get("ok", False)
            else (issues[0] if issues else "")
        ),
        "exit_cell": str(exit_record.get("cell_id", "")),
        "visible_cells": sorted(visible_cells) if visible_cells is not None else None,
        "threshold_id": str(rewire.get("threshold_id", "")),
        "door_threshold_id": str(event["target"].get("door_threshold_id", "")),
        "target_cells": list(rewire.get("target_cells", [])),
        "passages_before": rewire.get("passages_before", []),
        "passages_after": rewire.get("passages_after", []),
        "doorways": rewire.get("doorways", []),
        "changed_cells": derived.get("changed_cells", []),
        "passage_revisions": revisions,
        "derived_doorways": {
            cell_id: _spec_projection(spec)
            for cell_id, spec in derived.get("specs", {}).items()
        },
        "identity_issues": [
            issue
            for cell_id, spec in derived.get("specs", {}).items()
            for issue in identity_issues(specs.get(cell_id, {}), spec)
        ],
        "geometry_issues": issues,
        "f0_f1_f2": graph,
        "state_hash": state_hash(applied["state"], revisions, 1, 1),
        "event": event,
        "reroll_serial": 1,
        "branch_epoch": 1,
        "checks": list(event["validation"]["checks"]),
    }


def build_fixture() -> dict[str, Any]:
    """The M6 derived-spec fixture for the reachable and structural cases."""
    cases = {
        "seed32_runtime_c00_c01": _case(32, "c00", "c01", 2, visible=True),
        "seed279_c06_c11": _case(279, "c06", "c11", 2, visible=False),
        "seed279_c11_c02": _case(279, "c11", "c02", 2, visible=False),
        "seed1_no_candidate": _case(1, "c05", "c03", 2, visible=False),
        "seed2_no_candidate": _case(2, "c07", "c03", 2, visible=False),
    }
    return {
        "description": "M6 derived-spec, doorway geometry and F0-F2 fixture.",
        "layer_version": RUNTIME_LAYER_VERSION,
        "algorithm_version": mr.ALGORITHM_VERSION,
        "parameters": {
            "door_width_m": DOOR_WIDTH_M,
            "door_height_m": DOOR_HEIGHT_M,
            "doorway_margin_m": DOORWAY_MARGIN_M,
            "compatibility_type": DOORWAY_COMPATIBILITY_TYPE,
            "min_ceiling_clearance_m": MIN_CEILING_CLEARANCE_M,
            "runtime_checks": list(RUNTIME_CHECKS),
        },
        "summary": {
            "cases": len(cases),
            "ok_cases": sum(1 for case in cases.values() if case.get("ok")),
            "changed_cells": sum(
                len(case.get("changed_cells", [])) for case in cases.values()
            ),
        },
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fixture_parser = commands.add_parser("fixture", help="print the golden fixture")
    fixture_parser.add_argument("--out", help="write the fixture to this path")
    case_parser = commands.add_parser("case", help="plan one runtime case")
    case_parser.add_argument("--map", required=True)
    case_parser.add_argument("--from", dest="from_cell", required=True)
    case_parser.add_argument("--to", dest="to_cell", required=True)
    case_parser.add_argument("--event-index", type=int, default=1)
    args = parser.parse_args(argv)
    if args.command == "case":
        document = json.loads(Path(args.map).read_text(encoding="utf-8"))
        exit_record = me.select_exit(document)
        built = build_event(
            document,
            args.from_cell,
            args.to_cell,
            args.event_index,
            exit_cell=str(exit_record.get("cell_id", "")),
        )
        print(json.dumps(built, indent=2, sort_keys=True))
        return 0 if built["ok"] else 2
    fixture = build_fixture()
    payload = canonical_bytes(fixture)
    if args.out:
        Path(args.out).write_bytes(payload)
    else:
        sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
