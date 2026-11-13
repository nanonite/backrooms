"""Run save, restore and room-cache contract for the M7 overlay slice (#237).

The runtime state is still a pure function of the base map and the ordered event
log.  A save therefore stores only:

* the base identity, including the raw ``base_map_sha256`` (and the optional
  catalog snapshot hash); and
* the ordered event log.

It deliberately stores no candidate pool, no precomputed shortlist and no
overlay snapshot.  A pending re-roll is ephemeral: on restore it is enumerated
again from the accepted ``door_lock`` record, using the current folded passage
state and the next event index.  Once a ``door_reroll`` record exists, replay
applies its stored ``P`` and never re-enumerates.

The room-cache key is the streaming contract from proposal sections 4.7 and
9.7.  A cell whose ``passage_revision`` changed is a cache miss even when every
other field and the cell ID are unchanged.

Headless checks::

    python godot_walk/scripts/maze_run_save.py check --map PATH --save PATH
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_mutation as mm
import maze_reroll as mr
import maze_rewire as mw
from deterministic_json import ROOT, resolve_cli_path

SAVE_SCHEMA_VERSION = 1
SAVE_KIND = "maze-run-save"
SAVE_VERSION = "maze-run-save-0.1.0"
CACHE_KEY_VERSION = "maze-room-cache-0.1.0"

SAVE_FIELDS = frozenset(
    {"schema_version", "save_kind", "save_version", "base", "event_log"}
)
POOL_FIELDS = frozenset(
    {"pool", "pool_hash", "pool_sha256", "candidate_pool", "candidate_pool_hash"}
)


class RunSaveError(ValueError):
    """A save document is missing, stale, tampered with or from another base."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def base_identity(base: mm.BaseMap | dict[str, Any]) -> dict[str, Any]:
    """The stable base block stored in a save; never a pool or overlay hash."""
    if isinstance(base, mm.BaseMap):
        return base.identity
    return copy.deepcopy(base)


def build_save(base: mm.BaseMap, events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Validate and package a base identity plus an ordered event log."""
    event_log = [copy.deepcopy(event) for event in events]
    mm.fold_events(base, event_log)
    save = {
        "schema_version": SAVE_SCHEMA_VERSION,
        "save_kind": SAVE_KIND,
        "save_version": SAVE_VERSION,
        "base": base.identity,
        "event_log": event_log,
    }
    return _validate_save(save, base)


def validate_save(save: Any, base: mm.BaseMap) -> dict[str, Any]:
    """Validate a save against ``base`` and return a deep copy."""
    try:
        return _validate_save(save, base)
    except mm.BaseMismatchError:
        raise
    except mm.MutationLogError as error:
        raise RunSaveError("event_log_invalid", error.message) from error


def _validate_save(save: Any, base: mm.BaseMap) -> dict[str, Any]:
    if not isinstance(save, dict):
        raise RunSaveError("save_invalid", "save is not an object")
    unknown = set(save) - SAVE_FIELDS
    if unknown:
        code = "pool_forbidden" if unknown & POOL_FIELDS else "save_field_unknown"
        raise RunSaveError(code, f"unexpected save field(s): {sorted(unknown)}")
    if save.get("schema_version") != SAVE_SCHEMA_VERSION:
        raise RunSaveError("schema_version_unsupported", "save schema_version")
    if save.get("save_kind") != SAVE_KIND:
        raise RunSaveError("save_kind_invalid", "save_kind is not maze-run-save")
    if save.get("save_version") != SAVE_VERSION:
        raise RunSaveError("save_version_unsupported", "save_version")
    stored_base = save.get("base")
    if not isinstance(stored_base, dict):
        raise RunSaveError("base_invalid", "save base is not an object")
    if not mm._is_base_identity(base, stored_base):
        raise mm.BaseMismatchError(
            "base_mismatch", "save base does not match the current map"
        )
    event_log = save.get("event_log")
    if not isinstance(event_log, list):
        raise RunSaveError("event_log_invalid", "event_log is not a list")
    mm.fold_events(base, event_log)
    return copy.deepcopy(save)


def read_save(path: Path, base: mm.BaseMap, root: Path = ROOT) -> dict[str, Any]:
    """Read and validate a save file without writing anything."""
    save_path = resolve_cli_path(Path(path), root)
    if not save_path.is_file():
        raise RunSaveError("save_missing", f"save {save_path} does not exist")
    try:
        save = json.loads(save_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RunSaveError(
            "save_invalid", f"cannot read save {save_path}: {error}"
        ) from error
    return validate_save(save, base)


def write_save(path: Path, base: mm.BaseMap, save: dict[str, Any]) -> Path:
    """Validate then atomically replace a UTF-8 JSON save file."""
    checked = validate_save(save, base)
    save_path = Path(path)
    if save_path.is_symlink():
        raise RunSaveError("save_unsafe", f"refusing to write through {save_path}")
    save_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{save_path.name}.", suffix=".tmp", dir=save_path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                checked,
                stream,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, save_path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return save_path


def restore_rewire_state(
    document: dict[str, Any],
    specs: dict[str, dict[str, Any]],
    events: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Replay accepted door re-rolls into the passage state and revision map.

    This is the Python twin of ``MazeRewireRuntime.restore_events``.  It starts
    at the base and folds each accepted event in order, bumping the revision
    from the *current* spec so stacked re-rolls stay valid.
    """
    state = mr.base_passage_state(document)
    current_specs = copy.deepcopy(specs)
    revisions: dict[str, int] = {}
    accepted: list[dict[str, Any]] = []
    branch_epoch = 0
    reroll_serial = 0
    for event in events:
        if not isinstance(event, dict):
            raise RunSaveError("event_log_invalid", "event is not an object")
        if event.get("record_kind") != "mutation":
            continue
        if event.get("event_type") != "door_reroll":
            continue
        validation = event.get("validation")
        if isinstance(validation, dict) and validation.get("outcome") == "rejected":
            continue
        applied = mw.apply_event_to_state(state, event)
        if not applied.get("ok"):
            raise RunSaveError(
                "event_replay_failed", str(applied.get("reason", "rewire_invalid"))
            )
        derived = mw.derive_specs(document, current_specs, event)
        if not derived.get("ok"):
            raise RunSaveError(
                "event_replay_failed", str(derived.get("reason", "derive_failed"))
            )
        state = applied["state"]
        for cell_id, spec in derived["specs"].items():
            current_specs[cell_id] = spec
            revisions[cell_id] = int(spec.get("passage_revision", 0))
        accepted.append(copy.deepcopy(event))
        branch_epoch += 1
        reroll_serial += 1
    return {
        "state": state,
        "specs": current_specs,
        "revisions": revisions,
        "accepted": accepted,
        "branch_epoch": branch_epoch,
        "reroll_serial": reroll_serial,
        "state_hash": mw.state_hash(state, revisions, branch_epoch, reroll_serial),
    }


def accepted_thresholds(events: Iterable[dict[str, Any]]) -> set[str]:
    """Thresholds with one accepted re-roll in this log."""
    result: set[str] = set()
    for event in events:
        if not isinstance(event, dict) or event.get("event_type") != "door_reroll":
            continue
        validation = event.get("validation")
        if isinstance(validation, dict) and validation.get("outcome") == "rejected":
            continue
        threshold = _door_threshold(event)
        if threshold:
            result.add(threshold)
    return result


def rejected_thresholds(events: Iterable[dict[str, Any]]) -> set[str]:
    """Thresholds blocked by a rejected re-roll in this log."""
    result: set[str] = set()
    for event in events:
        if not isinstance(event, dict) or event.get("event_type") != "door_reroll":
            continue
        validation = event.get("validation")
        if isinstance(validation, dict) and validation.get("outcome") == "rejected":
            threshold = _door_threshold(event)
            if threshold:
                result.add(threshold)
    return result


def pending_rerolls(
    document: dict[str, Any],
    events: Iterable[dict[str, Any]],
    *,
    exit_cell: str | None = None,
    visible_for: Callable[[str], Iterable[str]] | None = None,
    reroll_index: int = 1,
) -> dict[str, dict[str, Any]]:
    """Re-enumerate every latched door with no committed re-roll.

    The rank is drawn with ``len(events) + 1`` because the pending list is
    ephemeral and the commit will be the next record.  The save file never
    carries this list, so a reload cannot resurrect a stale shortlist.
    """
    event_list = list(events)
    state = mr.current_passage_state(document, event_list)
    resolved = accepted_thresholds(event_list)
    blocked = rejected_thresholds(event_list)
    next_index = len(event_list) + 1
    pending: dict[str, dict[str, Any]] = {}
    for event in event_list:
        if not isinstance(event, dict) or event.get("event_type") != "door_lock":
            continue
        validation = event.get("validation")
        if isinstance(validation, dict) and validation.get("outcome") == "rejected":
            continue
        threshold = _door_threshold(event)
        if not threshold or threshold in pending:
            continue
        if threshold in resolved or threshold in blocked:
            continue
        target = event.get("target")
        if not isinstance(target, dict):
            continue
        from_cell = str(target.get("from_cell", ""))
        to_cell = str(target.get("to_cell", ""))
        if not from_cell or not to_cell:
            continue
        visible = set(visible_for(threshold)) if visible_for is not None else None
        pending[threshold] = mr.plan_reroll(
            document,
            from_cell,
            to_cell,
            next_index,
            exit_cell=exit_cell,
            visible_cells=visible,
            state=state,
            reroll_index=reroll_index,
        )
    return pending


def _door_threshold(event: dict[str, Any]) -> str:
    target = event.get("target")
    if not isinstance(target, dict):
        return ""
    for field in ("door_threshold_id", "threshold_id"):
        value = target.get(field)
        if isinstance(value, str) and value:
            return value
    return ""


class RoomCache:
    """Small revision-aware room cache used by the runtime and the tests."""

    def __init__(self) -> None:
        self.entries: dict[str, Any] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self.entries:
            self.misses += 1
            return default
        self.hits += 1
        return self.entries[key]

    def put(self, key: str, value: Any) -> None:
        self.entries[key] = value

    def has(self, key: str) -> bool:
        return key in self.entries

    def clear(self) -> None:
        self.entries.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "version": CACHE_KEY_VERSION,
            "entries": len(self.entries),
            "hits": self.hits,
            "misses": self.misses,
        }


def room_cache_key(
    base: mm.BaseMap | dict[str, Any],
    branch_epoch: int,
    passage_revision: int,
    content_revision: int,
    cell_id: str,
) -> str:
    """The cache key from proposal sections 4.7 and 9.7."""
    identity = base_identity(base)
    return "|".join(
        (
            CACHE_KEY_VERSION,
            str(identity.get("map_id", "")),
            str(identity.get("base_map_sha256", "")),
            str(int(branch_epoch)),
            str(int(passage_revision)),
            str(int(content_revision)),
            str(cell_id),
        )
    )


def _parse_visible(values: str) -> set[str]:
    return {value for value in values.split(",") if value}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check_parser = commands.add_parser("check", help="validate a saved run")
    check_parser.add_argument("--map", required=True)
    check_parser.add_argument("--save", required=True)
    check_parser.add_argument("--exit-cell", default="")
    check_parser.add_argument("--visible", default="")
    args = parser.parse_args(argv)
    try:
        base = mm.load_base(Path(args.map))
        save = read_save(Path(args.save), base)
        restored = restore_rewire_state(
            base.document,
            mw.load_specs(base.map_id),
            save["event_log"],
        )
        pending = pending_rerolls(
            base.document,
            save["event_log"],
            exit_cell=args.exit_cell or None,
            visible_for=(
                (lambda _threshold: _parse_visible(args.visible))
                if args.visible
                else None
            ),
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "state_hash": restored["state_hash"],
                    "events": len(save["event_log"]),
                    "pending": sorted(pending),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (RunSaveError, mm.MutationLogError) as error:
        print(
            json.dumps(
                {"ok": False, "code": error.code, "message": error.message},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
