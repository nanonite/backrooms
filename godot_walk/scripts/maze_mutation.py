"""Deterministic mutation-overlay core and headless replay for the maze (#231).

The runtime state of a maze is a pure function of its base map and one ordered
append-only event log::

    O_0 = empty overlay
    O_n = fold_events(base, E[1..n])

The base map is only ever read.  The overlay keeps the live divergence from it
and the log keeps the history that produced the divergence.  Both mutation and
trigger records live in the same JSONL file; ``event_index`` is the only
ordering that feeds a draw.  ``occurred_at_utc`` is bookkeeping and is never a
draw input.

This slice implements the core only: the event envelope, keyed event draws, the
overlay fold, a chained state hash, the JSONL reader/appender, trigger-based
cadence reconstruction and a replay CLI.  It deliberately does not build a
runtime maze, a lamp controller or a door re-roll.  The ``rewire`` block from
the proposal is reserved: it is accepted, stored verbatim and never interpreted
here.

The event/key construction follows the map generator's keyed layers::

    sha256("<seed>:<attempt>:<event_index>:<stream>:<target>:<purpose>")

so replaying the same base and log always produces the same draws and the same
state hash.

Headless replay::

    python godot_walk/scripts/maze_mutation.py replay --map PATH --log PATH
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import (
    ROOT,
    canonical_bytes,
    resolve_cli_path,
    sha256_bytes,
    sha256_file,
)

SCHEMA_VERSION = 1
RULE = "maze_mutation"
STATE_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
CHANGE_CLASS_PATTERN = re.compile(r"[a-z][a-z0-9_]*")

RECORD_KINDS = frozenset({"trigger", "mutation"})
TRIGGER_KINDS = frozenset(
    {
        "room_entered",
        "player_opened_door",
        "door_opened",
        "door_closed",
        "exit_entered",
        "cell_unloaded",
        "save_restore",
        "debug",
    }
)
VISIT_TRIGGER_KINDS = frozenset({"room_entered", "save_restore", "exit_entered"})
MUTATION_EVENT_TYPES = frozenset(
    {
        "follower_edit",
        "door_lock",
        "door_unlock",
        "door_reroll",
        "breadcrumb",
        "follower_cue",
        "run_end",
        "repair",
    }
)
RESERVED_EVENT_TYPES = frozenset({"exit_move"})
CHANGE_EVENT_TYPES = frozenset(
    {"follower_edit", "door_lock", "door_unlock", "breadcrumb", "repair"}
)
DOOR_CHANGE_EVENT_TYPES = frozenset({"door_lock", "door_unlock"})
INERT_EVENT_TYPES = frozenset({"follower_cue"})

# Cadence is counted in distinct visited cells, not seconds (§5.4).  The
# numbers are provisional tuning defaults until the operator walk (M14).
FIRST_EDIT_AT_VISITS = 5
CADENCE_BANDS: tuple[tuple[int, int | None, int | None, tuple[str, ...]], ...] = (
    (0, 4, None, ()),
    (5, 9, 4, ("lamp_state", "lamp_flicker", "reverb")),
    (
        10,
        14,
        3,
        (
            "lamp_state",
            "lamp_flicker",
            "reverb",
            "wear",
            "surface_variant",
            "door_lock",
        ),
    ),
    (
        15,
        24,
        2,
        (
            "lamp_state",
            "lamp_flicker",
            "reverb",
            "wear",
            "surface_variant",
            "door_lock",
            "palette",
            "dark_wing",
        ),
    ),
    (
        25,
        None,
        2,
        (
            "lamp_state",
            "lamp_flicker",
            "reverb",
            "wear",
            "surface_variant",
            "door_lock",
            "palette",
            "dark_wing",
        ),
    ),
)
STRUCTURAL_EDIT_MIN_VISITS = 25
STRUCTURAL_EDIT_INTERVAL = 6


class MutationLogError(ValueError):
    """Base class for mutation-log and event-envelope failures."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EventRejected(MutationLogError):
    """An event does not satisfy the envelope or the fold's local rules."""

    def __init__(self, errors: Sequence[dict[str, str]]) -> None:
        self.errors = list(errors)
        first = self.errors[0] if self.errors else {"code": "invalid", "message": ""}
        super().__init__(first["code"], first["message"])


class LogIntegrityError(MutationLogError):
    """The log order, hash chain, draw or base identity has been tampered with."""


class BaseMismatchError(LogIntegrityError):
    """An event was generated against a different base map identity."""


class LogFormatError(MutationLogError):
    """A JSONL file is missing, partial or not a sequence of objects."""


@dataclass(frozen=True)
class BaseMap:
    """The immutable identity and document of the map a log replays against."""

    document: dict[str, Any]
    base_map_sha256: str
    map_id: str
    generator_version: str
    seed: int
    attempt: int
    catalog_snapshot_sha256: str | None = None

    @classmethod
    def from_document(cls, document: dict[str, Any], base_map_sha256: str) -> BaseMap:
        if not isinstance(document, dict):
            raise MutationLogError("base_invalid", "map document is not an object")
        for field in ("map_id", "generator_version"):
            if not isinstance(document.get(field), str) or not document[field]:
                raise MutationLogError("base_invalid", f"map is missing {field}")
        if not _is_non_negative_int(document.get("seed")):
            raise MutationLogError("base_invalid", "map seed is invalid")
        attempt = document.get("attempt", 0)
        if not _is_non_negative_int(attempt):
            raise MutationLogError("base_invalid", "map attempt is invalid")
        if not _is_sha256(base_map_sha256):
            raise MutationLogError("base_invalid", "base map hash is invalid")
        snapshot = document.get("catalog_snapshot")
        snapshot_hash = snapshot.get("sha256") if isinstance(snapshot, dict) else None
        if snapshot_hash is not None and not _is_sha256(snapshot_hash):
            raise MutationLogError("base_invalid", "catalog snapshot hash is invalid")
        return cls(
            document=document,
            base_map_sha256=base_map_sha256,
            map_id=document["map_id"],
            generator_version=document["generator_version"],
            seed=int(document["seed"]),
            attempt=int(attempt),
            catalog_snapshot_sha256=snapshot_hash,
        )

    @property
    def identity(self) -> dict[str, Any]:
        identity: dict[str, Any] = {
            "map_id": self.map_id,
            "base_map_sha256": self.base_map_sha256,
            "generator_version": self.generator_version,
            "seed": self.seed,
            "attempt": self.attempt,
        }
        if self.catalog_snapshot_sha256 is not None:
            identity["catalog_snapshot_sha256"] = self.catalog_snapshot_sha256
        return identity

    @property
    def cell_ids(self) -> frozenset[str]:
        return frozenset(
            cell["cell_id"]
            for cell in self.document.get("cells", [])
            if isinstance(cell, dict) and isinstance(cell.get("cell_id"), str)
        )


def load_base(map_path: Path, root: Path = ROOT) -> BaseMap:
    """Read a committed map and compute its raw-file base hash."""
    path = resolve_cli_path(Path(map_path), root)
    if not path.is_file():
        raise MutationLogError("base_missing", f"map {path} does not exist")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MutationLogError(
            "base_invalid", f"cannot read map {path}: {error}"
        ) from error
    return BaseMap.from_document(document, sha256_file(path))


def draw_for_event(
    seed: int,
    attempt: int,
    event_index: int,
    stream: str,
    target: str,
    purpose: str,
) -> int:
    """The §3.3 keyed draw for one event, as a 256-bit integer."""
    key = f"{seed}:{attempt}:{event_index}:{stream}:{target}:{purpose}"
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest(), "big")


def draw_for_record(
    event: dict[str, Any], purpose: str, *, target: str | None = None
) -> int:
    """Draw addressed by an event's own base, index, stream and target."""
    base = event["base"]
    record_target = target if target is not None else event_target_key(event)
    return draw_for_event(
        int(base["seed"]),
        int(base["attempt"]),
        int(event["event_index"]),
        event["stream"],
        record_target,
        purpose,
    )


def event_target_key(event: dict[str, Any]) -> str:
    """Stable target string for an event draw: cell, threshold, marker or root."""
    target = event.get("target")
    if not isinstance(target, dict):
        raise MutationLogError("target_invalid", "event has no target object")
    ordered = ("cell_id", "threshold_id", "marker_id", "branch_root")
    if event.get("event_type") in {"door_reroll", "door_lock", "door_unlock"}:
        ordered = ("threshold_id", "cell_id", "marker_id", "branch_root")
    for field in ordered:
        value = target.get(field)
        if isinstance(value, str) and value:
            return value
    raise MutationLogError("target_invalid", "event target has no stable identity")


def event_id_for(base: BaseMap, event_index: int, record_kind: str) -> str:
    prefix = "trg" if record_kind == "trigger" else "mut"
    return f"{prefix}-{base.map_id}-{event_index:06d}"


def utc_now() -> str:
    """Bookkeeping timestamp; it is deliberately never a draw input."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def change_block(
    change_class: str,
    layer_version: str,
    before: Any,
    after: Any,
) -> dict[str, Any]:
    """Build the follower-edit ``change`` envelope (§3.2)."""
    return {
        "class": change_class,
        "layer_version": layer_version,
        "before": copy.deepcopy(before),
        "after": copy.deepcopy(after),
    }


def new_trigger(
    base: BaseMap,
    kind: str,
    event_index: int,
    *,
    player_cell: str | None = None,
    from_cell: str | None = None,
    occurred_at_utc: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Build a trigger record; hashes are filled by :func:`seal_event`."""
    trigger: dict[str, Any] = {"kind": kind}
    if player_cell is not None:
        trigger["player_cell"] = player_cell
    if from_cell is not None:
        trigger["from_cell"] = from_cell
    return {
        "schema_version": SCHEMA_VERSION,
        "event_index": event_index,
        "event_id": event_id or event_id_for(base, event_index, "trigger"),
        "record_kind": "trigger",
        "event_type": kind,
        "occurred_at_utc": occurred_at_utc or utc_now(),
        "base": base.identity,
        "trigger": trigger,
    }


def new_mutation(
    base: BaseMap,
    event_type: str,
    event_index: int,
    *,
    target: dict[str, Any],
    stream: str,
    change: dict[str, Any] | None = None,
    rewire: dict[str, Any] | None = None,
    draw: dict[str, Any] | None = None,
    visibility: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    occurred_at_utc: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Build a mutation record; hashes are filled by :func:`seal_event`."""
    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_index": event_index,
        "event_id": event_id or event_id_for(base, event_index, "mutation"),
        "record_kind": "mutation",
        "event_type": event_type,
        "occurred_at_utc": occurred_at_utc or utc_now(),
        "base": base.identity,
        "target": copy.deepcopy(target),
        "stream": stream,
        "validation": validation or {"outcome": "accepted", "checks": []},
    }
    if change is not None:
        event["change"] = copy.deepcopy(change)
    if rewire is not None:
        event["rewire"] = copy.deepcopy(rewire)
    if draw is not None:
        event["draw"] = copy.deepcopy(draw)
    if visibility is not None:
        event["visibility"] = copy.deepcopy(visibility)
    return event


def event_errors(
    event: Any,
    *,
    base: BaseMap | dict[str, Any] | None = None,
    require_seal: bool = False,
) -> list[dict[str, str]]:
    """All envelope errors for one record, as sorted error dictionaries."""
    if not isinstance(event, dict):
        return [_error("event_not_object", "event is not an object")]
    errors: list[dict[str, str]] = []
    errors += _identity_errors(event)
    errors += _base_errors(event.get("base"), base)
    record_kind = event.get("record_kind")
    if record_kind not in RECORD_KINDS:
        errors.append(_error("record_kind_invalid", str(record_kind)))
    elif record_kind == "trigger":
        errors += _trigger_errors(event)
    else:
        errors += _mutation_errors(event)
    if require_seal:
        errors += _seal_errors(event)
    errors += _json_errors(event)
    return errors


def _identity_errors(event: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if event.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            _error("schema_version_unsupported", str(event.get("schema_version")))
        )
    if not _is_positive_int(event.get("event_index")):
        errors.append(_error("event_index_invalid", str(event.get("event_index"))))
    if not isinstance(event.get("event_id"), str) or not event["event_id"]:
        errors.append(_error("event_id_invalid", "event_id must be a non-empty string"))
    if not isinstance(event.get("event_type"), str) or not event["event_type"]:
        errors.append(
            _error("event_type_invalid", "event_type must be a non-empty string")
        )
    if (
        not isinstance(event.get("occurred_at_utc"), str)
        or not event["occurred_at_utc"]
    ):
        errors.append(_error("occurred_at_invalid", "occurred_at_utc is missing"))
    return errors


def _base_errors(
    base_value: Any, base: BaseMap | dict[str, Any] | None
) -> list[dict[str, str]]:
    if not isinstance(base_value, dict):
        return [_error("base_invalid", "base must be an object")]
    errors: list[dict[str, str]] = []
    for field in ("map_id", "generator_version"):
        if not isinstance(base_value.get(field), str) or not base_value[field]:
            errors.append(_error("base_invalid", f"base.{field} is invalid"))
    if not _is_sha256(base_value.get("base_map_sha256")):
        errors.append(_error("base_invalid", "base.base_map_sha256 is invalid"))
    if not _is_non_negative_int(base_value.get("seed")):
        errors.append(_error("base_invalid", "base.seed is invalid"))
    if not _is_non_negative_int(base_value.get("attempt")):
        errors.append(_error("base_invalid", "base.attempt is invalid"))
    snapshot = base_value.get("catalog_snapshot_sha256")
    if snapshot is not None and not _is_sha256(snapshot):
        errors.append(_error("base_invalid", "base.catalog_snapshot_sha256 is invalid"))
    if base is not None and not _is_base_identity(base, base_value):
        errors.append(
            _error("base_mismatch", "event base does not match the replay base")
        )
    return errors


def _trigger_errors(event: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if event.get("event_type") not in TRIGGER_KINDS:
        errors.append(_error("trigger_type_invalid", str(event.get("event_type"))))
    trigger = event.get("trigger")
    if not isinstance(trigger, dict):
        return errors + [_error("trigger_invalid", "trigger must be an object")]
    if trigger.get("kind") not in TRIGGER_KINDS:
        errors.append(_error("trigger_kind_invalid", str(trigger.get("kind"))))
    for field in ("player_cell", "from_cell"):
        value = trigger.get(field)
        if value is not None and (not isinstance(value, str) or not value):
            errors.append(_error("trigger_cell_invalid", field))
    for field in ("target", "stream", "draw", "change", "rewire"):
        if field in event:
            errors.append(_error("trigger_field_forbidden", field))
    validation = event.get("validation")
    if validation is not None:
        errors += _validation_errors(validation)
    return errors


def _mutation_errors(event: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    event_type = event.get("event_type")
    if event_type in RESERVED_EVENT_TYPES:
        errors.append(_error("reserved_event_type", str(event_type)))
    elif event_type not in MUTATION_EVENT_TYPES:
        errors.append(_error("event_type_invalid", str(event_type)))
    target = event.get("target")
    errors += _target_errors(target)
    if not isinstance(event.get("stream"), str) or not event["stream"]:
        errors.append(_error("stream_invalid", "stream must be a non-empty string"))
    validation = event.get("validation")
    if not isinstance(validation, dict):
        errors.append(_error("validation_invalid", "mutation needs a validation block"))
    else:
        errors += _validation_errors(validation)
    draw = event.get("draw")
    if draw is not None:
        errors += _draw_errors(draw)
    visibility = event.get("visibility")
    if visibility is not None:
        errors += _visibility_errors(visibility)
    errors += _mutation_payload_errors(event_type, target, event)
    return errors


def _target_errors(target: Any) -> list[dict[str, str]]:
    if not isinstance(target, dict):
        return [_error("target_invalid", "mutation needs a target object")]
    errors: list[dict[str, str]] = []
    identities = ("cell_id", "threshold_id", "marker_id")
    found = False
    for field in identities:
        value = target.get(field)
        if value is None:
            continue
        found = True
        if not isinstance(value, str) or not value:
            errors.append(_error("target_invalid", field))
    if not found:
        errors.append(_error("target_invalid", "target has no stable identity"))
    return errors


def _mutation_payload_errors(
    event_type: Any, target: Any, event: dict[str, Any]
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    has_change = "change" in event
    has_rewire = "rewire" in event
    if event_type == "follower_edit":
        if not has_change:
            errors.append(_error("change_required", "follower_edit needs change"))
        if has_rewire:
            errors.append(_error("rewire_forbidden", "follower_edit has no rewire"))
        if not isinstance(target, dict) or not isinstance(target.get("cell_id"), str):
            errors.append(_error("target_invalid", "follower_edit needs a cell"))
    elif event_type == "door_reroll":
        if not has_rewire:
            errors.append(_error("rewire_required", "door_reroll needs rewire"))
        if has_change:
            errors.append(_error("change_forbidden", "door_reroll has no change"))
        if not isinstance(target, dict) or not isinstance(
            target.get("threshold_id"), str
        ):
            errors.append(_error("target_invalid", "door_reroll needs a threshold"))
    elif event_type in INERT_EVENT_TYPES:
        if has_change or has_rewire:
            errors.append(_error("payload_forbidden", f"{event_type} is inert"))
    elif event_type == "run_end":
        if has_change or has_rewire:
            errors.append(_error("payload_forbidden", "run_end changes no layer"))
        if not isinstance(target, dict) or not isinstance(target.get("cell_id"), str):
            errors.append(_error("target_invalid", "run_end needs an exit cell"))
    elif event_type in CHANGE_EVENT_TYPES:
        if not has_change:
            errors.append(_error("change_required", f"{event_type} needs change"))
        if has_rewire:
            errors.append(_error("rewire_forbidden", f"{event_type} has no rewire"))
    if has_change:
        errors += _change_errors(event["change"])
    if has_rewire:
        errors += _rewire_errors(event["rewire"])
    if (
        event_type in DOOR_CHANGE_EVENT_TYPES
        and isinstance(target, dict)
        and not isinstance(target.get("threshold_id"), str)
    ):
        errors.append(_error("target_invalid", f"{event_type} needs a threshold"))
    return errors


def _change_errors(change: Any) -> list[dict[str, str]]:
    if not isinstance(change, dict):
        return [_error("change_invalid", "change must be an object")]
    errors: list[dict[str, str]] = []
    change_class = change.get("class")
    if not isinstance(change_class, str) or not CHANGE_CLASS_PATTERN.fullmatch(
        change_class
    ):
        errors.append(_error("change_invalid", "change.class is invalid"))
    if not isinstance(change.get("layer_version"), str) or not change["layer_version"]:
        errors.append(_error("change_invalid", "change.layer_version is missing"))
    for field in ("before", "after"):
        if field not in change:
            errors.append(_error("change_invalid", f"change.{field} is missing"))
    if "before" in change and "after" in change and change["before"] == change["after"]:
        errors.append(_error("change_not_real", "change before equals after"))
    return errors


def _rewire_errors(rewire: Any) -> list[dict[str, str]]:
    if not isinstance(rewire, dict):
        return [_error("rewire_invalid", "rewire must be an object")]
    # Reserved in M1: the block is stored and replayed verbatim.  Its internal
    # fields belong to the re-roll slice and are deliberately not interpreted.
    return []


def _draw_errors(draw: Any) -> list[dict[str, str]]:
    if not isinstance(draw, dict):
        return [_error("draw_invalid", "draw must be an object")]
    errors: list[dict[str, str]] = []
    if not isinstance(draw.get("purpose"), str) or not draw["purpose"]:
        errors.append(_error("draw_invalid", "draw.purpose is missing"))
    if "value" in draw and not _is_non_negative_int(draw["value"]):
        errors.append(_error("draw_invalid", "draw.value is not an integer"))
    for field in ("reroll_serial", "branch_attempt"):
        if field in draw and not _is_non_negative_int(draw[field]):
            errors.append(_error("draw_invalid", f"draw.{field} is not an integer"))
    return errors


def _visibility_errors(visibility: Any) -> list[dict[str, str]]:
    if not isinstance(visibility, dict):
        return [_error("visibility_invalid", "visibility must be an object")]
    errors: list[dict[str, str]] = []
    player_cell = visibility.get("player_cell")
    if player_cell is not None and (
        not isinstance(player_cell, str) or not player_cell
    ):
        errors.append(_error("visibility_invalid", "visibility.player_cell"))
    target_hidden = visibility.get("target_hidden")
    if target_hidden is not None and type(target_hidden) is not bool:
        errors.append(_error("visibility_invalid", "visibility.target_hidden"))
    visible_cells = visibility.get("visible_cells")
    if visible_cells is not None and (
        not isinstance(visible_cells, list)
        or not all(isinstance(cell, str) and cell for cell in visible_cells)
    ):
        errors.append(_error("visibility_invalid", "visibility.visible_cells"))
    return errors


def _validation_errors(validation: Any) -> list[dict[str, str]]:
    if not isinstance(validation, dict):
        return [_error("validation_invalid", "validation must be an object")]
    errors: list[dict[str, str]] = []
    outcome = validation.get("outcome")
    if outcome not in ("accepted", "rejected"):
        errors.append(_error("validation_invalid", "validation.outcome"))
    if outcome == "rejected" and (
        not isinstance(validation.get("reason"), str) or not validation["reason"]
    ):
        errors.append(
            _error("validation_reason_missing", "rejected event needs reason")
        )
    checks = validation.get("checks")
    if checks is not None and (
        not isinstance(checks, list)
        or not all(isinstance(check, str) and check for check in checks)
    ):
        errors.append(_error("validation_invalid", "validation.checks"))
    return errors


def _seal_errors(event: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for field in ("prev_state_hash", "state_hash"):
        if not _is_sha256(event.get(field)):
            errors.append(_error("sealed_hash_invalid", field))
    return errors


def _json_errors(value: Any) -> list[dict[str, str]]:
    try:
        json.dumps(value, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as error:
        return [_error("json_invalid", str(error))]
    return []


def _is_base_identity(base: BaseMap | dict[str, Any], value: dict[str, Any]) -> bool:
    identity = base.identity if isinstance(base, BaseMap) else base
    for field in (
        "map_id",
        "base_map_sha256",
        "generator_version",
        "seed",
        "attempt",
    ):
        if identity.get(field) != value.get(field):
            return False
    snapshot = value.get("catalog_snapshot_sha256")
    return not (
        snapshot is not None and snapshot != identity.get("catalog_snapshot_sha256")
    )


def empty_overlay(base: BaseMap | dict[str, Any]) -> dict[str, Any]:
    """The empty overlay O_0, including its genesis state hash."""
    identity = base.identity if isinstance(base, BaseMap) else copy.deepcopy(base)
    overlay: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "base": identity,
        "cell_overrides": {},
        "door_overrides": {},
        "passage_overrides": {},
        "breadcrumbs": {},
        "run": {"ended": False, "exit_cell": None, "ended_at_event": None},
    }
    overlay["state_hash"] = state_hash(overlay)
    return overlay


def state_hash(overlay: dict[str, Any]) -> str:
    """Deterministic SHA-256 of an overlay, excluding the hash field itself."""
    payload = {key: value for key, value in overlay.items() if key != "state_hash"}
    return sha256_bytes(canonical_bytes(payload))


def seal_event(
    base: BaseMap,
    overlay: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    """Fill envelope identity and hashes, and verify the event folds cleanly.

    A ``validation.outcome`` of ``rejected`` produces an inert record whose
    ``state_hash`` equals ``prev_state_hash``.  It still consumes its event
    index, so later draws differ from a run without the rejected attempt.
    """
    sealed = copy.deepcopy(event)
    sealed.setdefault("schema_version", SCHEMA_VERSION)
    sealed.setdefault("base", base.identity)
    record_kind = sealed.get("record_kind", "mutation")
    event_index = sealed.get("event_index")
    if not _is_positive_int(event_index):
        raise EventRejected([_error("event_index_invalid", str(event_index))])
    sealed.setdefault("event_id", event_id_for(base, event_index, record_kind))
    sealed.setdefault("occurred_at_utc", utc_now())
    if sealed.get("record_kind") == "mutation" and "validation" not in sealed:
        sealed["validation"] = {"outcome": "accepted", "checks": []}
    errors = event_errors(sealed, base=base, require_seal=False)
    if errors:
        _raise_event_errors(errors)
    previous = overlay["state_hash"]
    if "prev_state_hash" in sealed and sealed["prev_state_hash"] != previous:
        raise LogIntegrityError(
            "prev_state_hash_mismatch", "event was sealed against another state"
        )
    sealed["prev_state_hash"] = previous
    outcome = _event_outcome(sealed)
    if outcome == "rejected":
        sealed["state_hash"] = previous
        return sealed
    next_overlay = _fold_accepted(base, copy.deepcopy(overlay), sealed)
    sealed["state_hash"] = state_hash(next_overlay)
    return sealed


def fold_events(
    base: BaseMap, events: Iterable[dict[str, Any]] | str | Path
) -> dict[str, Any]:
    """Fold an ordered event log into the overlay and verify every hash link.

    ``events`` may be an iterable of records or a path to a JSONL log.
    """
    event_list = _event_source(events)
    overlay = empty_overlay(base)
    seen_event_ids: set[str] = set()
    for expected_index, event in enumerate(event_list, start=1):
        errors = event_errors(event, base=base, require_seal=True)
        if errors:
            _raise_event_errors(errors)
        if event["event_index"] != expected_index:
            raise LogIntegrityError(
                "event_order",
                f"expected event_index {expected_index}, got {event['event_index']}",
            )
        if event["event_id"] in seen_event_ids:
            raise LogIntegrityError("event_duplicate", event["event_id"])
        seen_event_ids.add(event["event_id"])
        overlay = fold_event(base, overlay, event)
    return overlay


def fold_event(
    base: BaseMap, overlay: dict[str, Any], event: dict[str, Any]
) -> dict[str, Any]:
    """Fold one sealed event into a copy of ``overlay``."""
    errors = event_errors(event, base=base, require_seal=True)
    if errors:
        _raise_event_errors(errors)
    if event["prev_state_hash"] != overlay["state_hash"]:
        raise LogIntegrityError(
            "prev_state_hash_mismatch",
            f"event {event['event_index']} does not follow the current state",
        )
    if _event_outcome(event) == "rejected":
        if event["state_hash"] != event["prev_state_hash"]:
            raise LogIntegrityError(
                "rejected_event_changed_state",
                f"rejected event {event['event_index']} advanced the state",
            )
        return overlay
    next_overlay = _fold_accepted(base, copy.deepcopy(overlay), event)
    expected = state_hash(next_overlay)
    if event["state_hash"] != expected:
        raise LogIntegrityError(
            "state_hash_mismatch",
            f"event {event['event_index']} records a different state hash",
        )
    next_overlay["state_hash"] = expected
    return next_overlay


def _fold_accepted(
    base: BaseMap, overlay: dict[str, Any], event: dict[str, Any]
) -> dict[str, Any]:
    if event["record_kind"] == "trigger":
        return overlay
    event_type = event["event_type"]
    if event_type in INERT_EVENT_TYPES:
        return overlay
    _verify_recorded_draw(event)
    if event_type == "run_end":
        _apply_run_end(base, overlay, event)
    elif event_type == "door_reroll":
        _apply_rewire(overlay, event)
    else:
        _apply_change(base, overlay, event)
    return overlay


def _verify_recorded_draw(event: dict[str, Any]) -> None:
    draw = event.get("draw")
    if not isinstance(draw, dict) or "value" not in draw:
        return
    target = event_target_key(event)
    expected = draw_for_record(event, draw["purpose"], target=target)
    if int(draw["value"]) != expected:
        raise LogIntegrityError(
            "draw_mismatch",
            f"event {event['event_index']} records a draw that is not keyed to its target",
        )


def _apply_run_end(
    base: BaseMap, overlay: dict[str, Any], event: dict[str, Any]
) -> None:
    if overlay["run"]["ended"]:
        raise EventRejected(
            [_error("run_already_ended", f"event {event['event_index']}")]
        )
    exit_cell = event["target"]["cell_id"]
    if exit_cell not in base.cell_ids:
        raise EventRejected(
            [_error("unknown_cell", f"exit {exit_cell} is not in the base map")]
        )
    overlay["run"] = {
        "ended": True,
        "exit_cell": exit_cell,
        "ended_at_event": event["event_index"],
    }


def _apply_rewire(overlay: dict[str, Any], event: dict[str, Any]) -> None:
    threshold_id = event["target"]["threshold_id"]
    if threshold_id in overlay["passage_overrides"]:
        raise EventRejected([_error("duplicate_reroll", f"threshold {threshold_id}")])
    # Reserved opaque block: copy it into the overlay without reading its
    # fields.  A later re-roll slice owns their interpretation.
    overlay["passage_overrides"][threshold_id] = copy.deepcopy(event["rewire"])


def _apply_change(
    base: BaseMap, overlay: dict[str, Any], event: dict[str, Any]
) -> None:
    change = event["change"]
    change_class = change["class"]
    target = event["target"]
    if event["event_type"] == "breadcrumb" and "marker_id" in target:
        bucket = overlay["breadcrumbs"]
        key = target["marker_id"]
    elif "cell_id" in target:
        cell_id = target["cell_id"]
        if cell_id not in base.cell_ids:
            raise EventRejected(
                [_error("unknown_cell", f"cell {cell_id} is not in the base map")]
            )
        bucket = overlay["cell_overrides"].setdefault(cell_id, {})
        key = change_class
    elif "threshold_id" in target:
        bucket = overlay["door_overrides"].setdefault(target["threshold_id"], {})
        key = change_class
    else:
        raise EventRejected([_error("target_invalid", f"event {event['event_index']}")])
    if key in bucket and bucket[key] != change["before"]:
        raise LogIntegrityError(
            "change_before_mismatch",
            f"event {event['event_index']} does not continue the current value",
        )
    bucket[key] = copy.deepcopy(change["after"])


def _event_outcome(event: dict[str, Any]) -> str:
    if event.get("record_kind") == "trigger":
        return "accepted"
    validation = event.get("validation")
    if not isinstance(validation, dict):
        return "accepted"
    outcome = validation.get("outcome")
    return outcome if outcome in ("accepted", "rejected") else "accepted"


def _raise_event_errors(errors: Sequence[dict[str, str]]) -> None:
    for error in errors:
        if error["code"] == "base_mismatch":
            raise BaseMismatchError(error["code"], error["message"])
    raise EventRejected(errors)


def _event_source(
    events: Iterable[dict[str, Any]] | str | Path,
) -> list[dict[str, Any]]:
    if isinstance(events, (str, Path)):
        return read_events(Path(events))
    return list(events)


def read_events(path: Path) -> list[dict[str, Any]]:
    """Read a strict append-only JSONL event log."""
    log_path = Path(path)
    if not log_path.is_file():
        raise LogFormatError("log_missing", f"log {log_path} does not exist")
    content = log_path.read_text(encoding="utf-8")
    if content and not content.endswith("\n"):
        raise LogFormatError("log_partial", f"log {log_path} ends mid-record")
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            raise LogFormatError(
                "log_blank_line", f"log {log_path} has a blank line at {line_number}"
            )
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise LogFormatError(
                "log_invalid_json", f"log line {line_number}: {error}"
            ) from error
        if not isinstance(event, dict):
            raise LogFormatError(
                "log_invalid_record", f"log line {line_number} is not an object"
            )
        events.append(event)
    return events


def append_event(path: Path, event: dict[str, Any]) -> None:
    """Append one sealed event, refusing partial files and non-contiguous order."""
    log_path = Path(path)
    if log_path.is_symlink():
        raise LogFormatError("log_unsafe", f"refusing to append through {log_path}")
    errors = event_errors(event, require_seal=True)
    if errors:
        _raise_event_errors(errors)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            stream.seek(0)
            content = stream.read()
            if content and not content.endswith("\n"):
                raise LogFormatError("log_partial", f"log {log_path} ends mid-record")
            lines = content.splitlines()
            expected_index = len(lines) + 1
            if event["event_index"] != expected_index:
                raise LogIntegrityError(
                    "event_order",
                    f"expected event_index {expected_index}, got {event['event_index']}",
                )
            existing_ids: set[Any] = set()
            for line_number, existing_line in enumerate(lines, start=1):
                if not existing_line.strip():
                    raise LogFormatError(
                        "log_blank_line",
                        f"log {log_path} has a blank line at {line_number}",
                    )
                try:
                    existing = json.loads(existing_line)
                except json.JSONDecodeError as error:
                    raise LogFormatError(
                        "log_invalid_json", f"log line {line_number}: {error}"
                    ) from error
                if isinstance(existing, dict):
                    existing_ids.add(existing.get("event_id"))
            if event["event_id"] in existing_ids:
                raise LogIntegrityError("event_duplicate", event["event_id"])
            line = json.dumps(
                event,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            stream.seek(0, os.SEEK_END)
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def append_sealed(path: Path, base: BaseMap, event: dict[str, Any]) -> dict[str, Any]:
    """Seal one event against the current log, append it, and return it."""
    log_path = Path(path)
    events = read_events(log_path) if log_path.exists() else []
    overlay = fold_events(base, events)
    spec = copy.deepcopy(event)
    spec.setdefault("event_index", len(events) + 1)
    if spec["event_index"] != len(events) + 1:
        raise LogIntegrityError(
            "event_order",
            f"expected event_index {len(events) + 1}, got {spec['event_index']}",
        )
    sealed = seal_event(base, overlay, spec)
    append_event(log_path, sealed)
    return sealed


def seal_log(base: BaseMap, events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Seal a list of in-memory events in order, for tests and headless harnesses."""
    overlay = empty_overlay(base)
    sealed: list[dict[str, Any]] = []
    for position, event in enumerate(events, start=1):
        spec = copy.deepcopy(event)
        spec.setdefault("event_index", position)
        if spec["event_index"] != position:
            raise LogIntegrityError(
                "event_order",
                f"expected event_index {position}, got {spec['event_index']}",
            )
        sealed_event = seal_event(base, overlay, spec)
        overlay = fold_event(base, overlay, sealed_event)
        sealed.append(sealed_event)
    return sealed


def replay(
    base: BaseMap, events: Iterable[dict[str, Any]] | str | Path
) -> dict[str, Any]:
    """Replay a log and return the overlay, counters and cadence."""
    event_list = _event_source(events)
    overlay = fold_events(base, event_list)
    return {
        "ok": True,
        "state_hash": overlay["state_hash"],
        "overlay": overlay,
        "counters": run_counters(event_list, base=base),
        "cadence": reconstruct_cadence(event_list),
    }


def visited_cells(events: Iterable[dict[str, Any]]) -> list[str]:
    """Distinct visited cells in first-entry order, from trigger records only."""
    visited: list[str] = []
    seen: set[str] = set()
    for event in events:
        if not isinstance(event, dict) or event.get("record_kind") != "trigger":
            continue
        trigger = event.get("trigger")
        if (
            not isinstance(trigger, dict)
            or trigger.get("kind") not in VISIT_TRIGGER_KINDS
        ):
            continue
        cell = trigger.get("player_cell") or trigger.get("from_cell")
        if isinstance(cell, str) and cell and cell not in seen:
            visited.append(cell)
            seen.add(cell)
    return visited


def cadence_band(
    visited_count: int,
) -> tuple[int, int | None, int | None, tuple[str, ...]]:
    """The cadence row that contains ``visited_count``."""
    for minimum, maximum, interval, classes in CADENCE_BANDS:
        if visited_count >= minimum and (maximum is None or visited_count <= maximum):
            return minimum, maximum, interval, classes
    return CADENCE_BANDS[-1]


def cadence_beats(visited_count: int) -> list[int]:
    """Visit counts where the trigger cadence schedules an edit beat."""
    beats: list[int] = []
    last_beat: int | None = None
    for count in range(1, max(0, visited_count) + 1):
        while True:
            target = (
                FIRST_EDIT_AT_VISITS
                if last_beat is None
                else _next_beat_after(last_beat)
            )
            if target is None or count < target:
                break
            beats.append(target)
            last_beat = target
    return beats


def _next_beat_after(last_beat: int) -> int | None:
    interval = cadence_band(last_beat)[2]
    return last_beat + interval if interval is not None else None


def reconstruct_cadence(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Reconstruct the scheduler from triggers; mutation records are ignored."""
    event_list = list(events)
    visited = visited_cells(event_list)
    count = len(visited)
    beats = cadence_beats(count)
    last_beat = beats[-1] if beats else None
    allowed = list(cadence_band(count)[3])
    if count < FIRST_EDIT_AT_VISITS:
        next_edit_at: int | None = None
    elif last_beat is not None:
        next_edit_at = _next_beat_after(last_beat)
    else:
        next_edit_at = FIRST_EDIT_AT_VISITS
    return {
        "distinct_visited_cells": count,
        "visited_cells": visited,
        "beats": beats,
        "last_beat_at": last_beat,
        "next_edit_at": next_edit_at,
        "interval": cadence_band(last_beat)[2] if last_beat is not None else None,
        "allowed_classes": allowed,
        "structural_interval": (
            STRUCTURAL_EDIT_INTERVAL if count >= STRUCTURAL_EDIT_MIN_VISITS else None
        ),
    }


def run_counters(
    events: Iterable[dict[str, Any]], *, base: BaseMap | None = None
) -> dict[str, Any]:
    """End-card counters derived from the log, never from runtime memory."""
    event_list = list(events)
    accepted = {"follower_edit": 0, "door_reroll": 0, "door_lock": 0, "door_unlock": 0}
    rejected = 0
    ended_at: int | None = None
    for event in event_list:
        if event.get("record_kind") != "mutation":
            continue
        if _event_outcome(event) == "rejected":
            rejected += 1
            continue
        event_type = event.get("event_type")
        if event_type in accepted:
            accepted[event_type] += 1
        if event_type == "run_end" and ended_at is None:
            ended_at = event["event_index"]
    seed = base.seed if base is not None else _seed_from_events(event_list)
    map_id = base.map_id if base is not None else _map_id_from_events(event_list)
    return {
        "seed": seed,
        "map_id": map_id,
        "records": len(event_list),
        "triggers": sum(
            1 for event in event_list if event.get("record_kind") == "trigger"
        ),
        "mutations": sum(
            1 for event in event_list if event.get("record_kind") == "mutation"
        ),
        "accepted": sum(
            1
            for event in event_list
            if event.get("record_kind") == "mutation"
            and _event_outcome(event) == "accepted"
        ),
        "rejected": rejected,
        "edits": accepted["follower_edit"],
        "rerolls": accepted["door_reroll"],
        "locks": accepted["door_lock"],
        "unlocks": accepted["door_unlock"],
        "rooms_visited": len(visited_cells(event_list)),
        "run_ended": ended_at is not None,
        "ended_at_event": ended_at,
        "last_event_index": event_list[-1]["event_index"] if event_list else 0,
    }


def _seed_from_events(events: list[dict[str, Any]]) -> int | None:
    for event in events:
        base = event.get("base")
        if isinstance(base, dict) and isinstance(base.get("seed"), int):
            return base["seed"]
    return None


def _map_id_from_events(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        base = event.get("base")
        if isinstance(base, dict) and isinstance(base.get("map_id"), str):
            return base["map_id"]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    replay_parser = commands.add_parser("replay", help="replay a map and its event log")
    replay_parser.add_argument("--map", required=True, help="committed map JSON")
    replay_parser.add_argument("--log", required=True, help="JSONL mutation log")
    replay_parser.add_argument(
        "--no-overlay", action="store_true", help="omit the full overlay from output"
    )
    cadence_parser = commands.add_parser(
        "cadence", help="reconstruct cadence from trigger records"
    )
    cadence_parser.add_argument("--log", required=True, help="JSONL mutation log")
    args = parser.parse_args(argv)
    try:
        if args.command == "cadence":
            result = reconstruct_cadence(read_events(Path(args.log)))
        else:
            base = load_base(Path(args.map))
            result = replay(base, read_events(Path(args.log)))
            if args.no_overlay:
                result.pop("overlay")
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    except MutationLogError as error:
        print(
            json.dumps(
                {"ok": False, "code": error.code, "message": error.message},
                sort_keys=True,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


def _is_positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _is_non_negative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and STATE_HASH_PATTERN.fullmatch(value) is not None


def _error(code: str, message: str) -> dict[str, str]:
    return {"rule": RULE, "code": code, "message": message}


if __name__ == "__main__":
    raise SystemExit(main())
