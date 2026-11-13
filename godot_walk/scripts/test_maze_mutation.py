"""Tests for the M1 mutation overlay core and replay (#231)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_mutation as mm
from deterministic_json import ROOT, sha256_file

MAP_PATH = ROOT / "godot_walk/room_catalog/generative_maps/gmap-279-gmap-0.13.0.json"
FOLLOWER_STREAM = "follower:gmap-0.13.0"
REROLL_STREAM = "door-reroll:gmap-0.13.0"
RUN_STREAM = "run:gmap-0.13.0"


@pytest.fixture(scope="module")
def base() -> mm.BaseMap:
    return mm.load_base(MAP_PATH)


def trigger(base: mm.BaseMap, index: int, cell: str) -> dict:
    return mm.new_trigger(base, "room_entered", index, player_cell=cell)


def follower_edit(
    base: mm.BaseMap,
    index: int,
    cell: str,
    *,
    before: object = 0,
    after: object | None = None,
    validation: dict | None = None,
    stream: str = FOLLOWER_STREAM,
) -> dict:
    purpose = f"lamp-state:{index}"
    value = mm.draw_for_event(base.seed, base.attempt, index, stream, cell, purpose)
    return mm.new_mutation(
        base,
        "follower_edit",
        index,
        target={"cell_id": cell},
        stream=stream,
        change=mm.change_block(
            "lamp_state", "maze-change-0.1.0", before, value if after is None else after
        ),
        draw={"purpose": purpose, "value": value},
        validation=validation,
    )


def base_log(base: mm.BaseMap) -> list[dict]:
    return [
        trigger(base, 1, "c00"),
        trigger(base, 2, "c04"),
        trigger(base, 3, "c01"),
        trigger(base, 4, "c02"),
        trigger(base, 5, "c03"),
        trigger(base, 6, "c07"),
    ]


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
            for event in events
        ),
        encoding="utf-8",
    )


def test_committed_base_loads_with_a_raw_file_hash(base):
    assert base.map_id == "gmap-279-gmap-0.13.0"
    assert base.generator_version == "gmap-0.13.0"
    assert base.seed == 279
    assert base.attempt == 0
    assert base.base_map_sha256 == sha256_file(MAP_PATH)
    assert base.identity["catalog_snapshot_sha256"] == (
        base.document["catalog_snapshot"]["sha256"]
    )
    assert "c00" in base.cell_ids


def test_empty_overlay_state_hash_is_deterministic_and_base_bound(base):
    first = mm.empty_overlay(base)
    second = mm.empty_overlay(base)
    assert first == second
    assert first["state_hash"] == mm.state_hash(first)
    changed = copy.deepcopy(first)
    changed["cell_overrides"]["c00"] = {"lamp_state": "off"}
    assert mm.state_hash(changed) != first["state_hash"]


def test_fold_is_deterministic_and_jsonl_round_trips(base, tmp_path):
    events = base_log(base)
    events.append(follower_edit(base, 7, "c04", before=0, after="off"))
    events.append(
        mm.new_mutation(
            base,
            "door_reroll",
            8,
            target={"threshold_id": "c04:p1", "branch_root": "c05"},
            stream=REROLL_STREAM,
            rewire={
                "algorithm_version": "rewire-1",
                "target_cells": ["c05"],
                "passages_before": [["c04", "c05"]],
                "passages_after": [],
            },
        )
    )
    events.append(
        mm.new_mutation(
            base,
            "run_end",
            9,
            target={"cell_id": "c12"},
            stream=RUN_STREAM,
        )
    )
    first = mm.seal_log(base, events)
    second = mm.seal_log(base, copy.deepcopy(events))
    assert first == second
    overlay = mm.fold_events(base, first)
    assert overlay == mm.fold_events(base, second)
    assert overlay["run"] == {
        "ended": True,
        "exit_cell": "c12",
        "ended_at_event": 9,
    }

    log_path = tmp_path / "events.jsonl"
    for event in first:
        mm.append_event(log_path, event)
    assert mm.read_events(log_path) == first
    assert mm.fold_events(base, log_path) == overlay
    replayed = mm.replay(base, log_path)
    assert replayed["state_hash"] == overlay["state_hash"]
    assert replayed["overlay"] == overlay


def test_event_order_matters_for_the_log_and_for_state(base):
    first = follower_edit(base, 1, "c04", before=0, after="a")
    second = follower_edit(base, 2, "c04", before="a", after="b")
    sealed = mm.seal_log(base, [first, second])
    swapped = [sealed[1], sealed[0]]
    with pytest.raises(mm.LogIntegrityError) as error:
        mm.fold_events(base, swapped)
    assert error.value.code == "event_order"

    renumbered = [copy.deepcopy(sealed[1]), copy.deepcopy(sealed[0])]
    renumbered[0]["event_index"] = 1
    renumbered[1]["event_index"] = 2
    with pytest.raises(mm.LogIntegrityError) as error:
        mm.fold_events(base, renumbered)
    assert error.value.code == "prev_state_hash_mismatch"

    forward = mm.fold_events(base, mm.seal_log(base, [first, second]))
    backward = mm.fold_events(
        base,
        mm.seal_log(
            base,
            [
                follower_edit(base, 1, "c04", before=0, after="b"),
                follower_edit(base, 2, "c04", before="b", after="a"),
            ],
        ),
    )
    assert forward["state_hash"] != backward["state_hash"]
    assert forward["cell_overrides"]["c04"]["lamp_state"] != (
        backward["cell_overrides"]["c04"]["lamp_state"]
    )


def test_trigger_only_cadence_matches_the_full_log(base):
    events = base_log(base)
    events.extend(
        [
            follower_edit(base, 7, "c04", before=0, after="off"),
            mm.new_mutation(
                base,
                "follower_cue",
                8,
                target={"cell_id": "c04"},
                stream="follower:gmap-0.13.0",
            ),
            trigger(base, 9, "c08"),
            trigger(base, 10, "c10"),
        ]
    )
    sealed = mm.seal_log(base, events)
    triggers_only = [event for event in sealed if event["record_kind"] == "trigger"]
    full_cadence = mm.reconstruct_cadence(sealed)
    assert full_cadence == mm.reconstruct_cadence(triggers_only)
    assert full_cadence["distinct_visited_cells"] == 8
    assert full_cadence["beats"] == [5]
    assert full_cadence["next_edit_at"] == 9
    assert full_cadence["interval"] == 4
    assert "lamp_state" in full_cadence["allowed_classes"]
    assert full_cadence["structural_interval"] is None


def test_rejected_event_is_inert_but_keeps_its_place(base):
    rejected = follower_edit(
        base,
        2,
        "c04",
        before=0,
        after="rejected",
        validation={
            "outcome": "rejected",
            "reason": "target_visible",
            "checks": ["target_hidden"],
        },
    )
    sealed = mm.seal_log(base, [trigger(base, 1, "c00"), rejected])
    overlay = mm.fold_events(base, sealed)
    assert overlay["cell_overrides"] == {}
    assert sealed[1]["state_hash"] == sealed[1]["prev_state_hash"]
    assert sealed[1]["state_hash"] == sealed[0]["state_hash"]
    counters = mm.run_counters(sealed, base=base)
    assert counters["rejected"] == 1
    assert counters["edits"] == 0

    accepted_at_two = follower_edit(base, 2, "c04", before=0)
    accepted_at_three = follower_edit(base, 3, "c04", before=0)
    without_rejection = mm.fold_events(
        base, mm.seal_log(base, [trigger(base, 1, "c00"), accepted_at_two])
    )
    with_rejection = mm.fold_events(
        base,
        mm.seal_log(
            base,
            [
                trigger(base, 1, "c00"),
                follower_edit(
                    base,
                    2,
                    "c04",
                    after="rejected",
                    validation={"outcome": "rejected", "reason": "target_visible"},
                ),
                accepted_at_three,
            ],
        ),
    )
    assert without_rejection["state_hash"] != with_rejection["state_hash"]
    assert without_rejection["cell_overrides"]["c04"]["lamp_state"] != (
        with_rejection["cell_overrides"]["c04"]["lamp_state"]
    )


def test_base_hash_mismatch_is_rejected(base):
    sealed = mm.seal_log(base, [trigger(base, 1, "c00")])
    tampered = copy.deepcopy(sealed)
    tampered[0]["base"]["base_map_sha256"] = "0" * 64
    with pytest.raises(mm.BaseMismatchError):
        mm.fold_events(base, tampered)


def test_tampered_change_and_hash_chain_are_rejected(base):
    sealed = mm.seal_log(base, [trigger(base, 1, "c00"), follower_edit(base, 2, "c04")])
    tampered_change = copy.deepcopy(sealed)
    tampered_change[1]["change"]["after"] = "tampered"
    with pytest.raises(mm.LogIntegrityError) as error:
        mm.fold_events(base, tampered_change)
    assert error.value.code == "state_hash_mismatch"

    tampered_link = copy.deepcopy(sealed)
    tampered_link[1]["prev_state_hash"] = "f" * 64
    with pytest.raises(mm.LogIntegrityError) as error:
        mm.fold_events(base, tampered_link)
    assert error.value.code == "prev_state_hash_mismatch"

    tampered_draw = copy.deepcopy(sealed)
    tampered_draw[1]["draw"]["value"] += 1
    with pytest.raises(mm.LogIntegrityError) as error:
        mm.fold_events(base, tampered_draw)
    assert error.value.code == "draw_mismatch"


def test_rewire_block_round_trips_without_interpretation(base, tmp_path):
    opaque = {
        "algorithm_version": "rewire-1",
        "target_cells": ["c05", "c06"],
        "passages_before": [["c04", "c05"]],
        "passages_after": [],
        "future_field": {"nested": [1, 2, 3], "relaxed": False},
    }
    event = mm.new_mutation(
        base,
        "door_reroll",
        2,
        target={"threshold_id": "c04:p1", "branch_root": "c05"},
        stream=REROLL_STREAM,
        rewire=opaque,
    )
    sealed = mm.seal_log(base, [trigger(base, 1, "c04"), event])
    overlay = mm.fold_events(base, sealed)
    assert overlay["passage_overrides"] == {"c04:p1": opaque}
    assert sealed[1]["rewire"] == opaque

    log_path = tmp_path / "events.jsonl"
    for record in sealed:
        mm.append_event(log_path, record)
    assert mm.read_events(log_path)[1]["rewire"] == opaque


def test_follower_edit_rejects_rewire_and_trigger_rejects_payload(base):
    event = follower_edit(base, 1, "c04")
    event["rewire"] = {"algorithm_version": "rewire-1"}
    codes = {error["code"] for error in mm.event_errors(event, base=base)}
    assert "rewire_forbidden" in codes

    trigger_event = trigger(base, 1, "c00")
    trigger_event["change"] = mm.change_block("lamp_state", "v1", 0, 1)
    codes = {error["code"] for error in mm.event_errors(trigger_event, base=base)}
    assert "trigger_field_forbidden" in codes

    reserved = follower_edit(base, 1, "c04")
    reserved["event_type"] = "exit_move"
    codes = {error["code"] for error in mm.event_errors(reserved, base=base)}
    assert "reserved_event_type" in codes


def test_map_file_is_never_written_by_replay(base, tmp_path):
    before_bytes = MAP_PATH.read_bytes()
    before_hash = sha256_file(MAP_PATH)
    before_stat = MAP_PATH.stat()
    events = mm.seal_log(
        base,
        [
            trigger(base, 1, "c00"),
            follower_edit(base, 2, "c04"),
            mm.new_mutation(
                base,
                "door_reroll",
                3,
                target={"threshold_id": "c04:p1"},
                stream=REROLL_STREAM,
                rewire={"algorithm_version": "rewire-1"},
            ),
        ],
    )
    log_path = tmp_path / "events.jsonl"
    for event in events:
        mm.append_event(log_path, event)
    assert mm.replay(base, mm.read_events(log_path))["ok"] is True
    assert mm.main(["replay", "--map", str(MAP_PATH), "--log", str(log_path)]) == 0

    assert MAP_PATH.read_bytes() == before_bytes
    assert sha256_file(MAP_PATH) == before_hash
    assert MAP_PATH.stat().st_mtime_ns == before_stat.st_mtime_ns


def test_jsonl_reader_rejects_partial_and_blank_records(tmp_path):
    partial = tmp_path / "partial.jsonl"
    partial.write_text('{"schema_version": 1}', encoding="utf-8")
    with pytest.raises(mm.LogFormatError) as error:
        mm.read_events(partial)
    assert error.value.code == "log_partial"

    blank = tmp_path / "blank.jsonl"
    blank.write_text('{"schema_version": 1}\n\n', encoding="utf-8")
    with pytest.raises(mm.LogFormatError) as error:
        mm.read_events(blank)
    assert error.value.code == "log_blank_line"


def test_append_event_requires_contiguous_index_and_unique_id(base, tmp_path):
    log_path = tmp_path / "events.jsonl"
    sealed = mm.seal_log(base, [trigger(base, 1, "c00")])
    mm.append_event(log_path, sealed[0])
    with pytest.raises(mm.LogIntegrityError) as error:
        mm.append_event(log_path, sealed[0])
    assert error.value.code == "event_order"

    duplicate = copy.deepcopy(sealed[0])
    duplicate["event_index"] = 2
    with pytest.raises(mm.LogIntegrityError) as error:
        mm.append_event(log_path, duplicate)
    assert error.value.code == "event_duplicate"


def test_append_sealed_fills_the_next_index_and_chain(base, tmp_path):
    log_path = tmp_path / "events.jsonl"
    first = trigger(base, 1, "c00")
    first.pop("event_index")
    first.pop("event_id")
    sealed_first = mm.append_sealed(log_path, base, first)
    assert sealed_first["event_index"] == 1
    assert sealed_first["event_id"] == "trg-gmap-279-gmap-0.13.0-000001"

    second = follower_edit(base, 2, "c04")
    second.pop("event_index")
    second.pop("event_id")
    sealed_second = mm.append_sealed(log_path, base, second)
    assert sealed_second["event_index"] == 2
    assert sealed_second["prev_state_hash"] == sealed_first["state_hash"]

    overlay = mm.fold_events(base, mm.read_events(log_path))
    assert (
        overlay["cell_overrides"]["c04"]["lamp_state"]
        == sealed_second["change"]["after"]
    )


def test_draw_for_event_is_keyed_to_every_input(base):
    first = mm.draw_for_event(279, 0, 1, FOLLOWER_STREAM, "c04", "lamp-state:1")
    assert first == mm.draw_for_event(279, 0, 1, FOLLOWER_STREAM, "c04", "lamp-state:1")
    for changed in (
        mm.draw_for_event(280, 0, 1, FOLLOWER_STREAM, "c04", "lamp-state:1"),
        mm.draw_for_event(279, 1, 1, FOLLOWER_STREAM, "c04", "lamp-state:1"),
        mm.draw_for_event(279, 0, 2, FOLLOWER_STREAM, "c04", "lamp-state:1"),
        mm.draw_for_event(279, 0, 1, "other:stream", "c04", "lamp-state:1"),
        mm.draw_for_event(279, 0, 1, FOLLOWER_STREAM, "c05", "lamp-state:1"),
        mm.draw_for_event(279, 0, 1, FOLLOWER_STREAM, "c04", "lamp-state:2"),
    ):
        assert changed != first
    event = follower_edit(base, 1, "c04")
    assert mm.draw_for_record(event, "lamp-state:1") == first

    reroll = mm.new_mutation(
        base,
        "door_reroll",
        1,
        target={"cell_id": "c04", "threshold_id": "c04:p1"},
        stream=REROLL_STREAM,
        rewire={"algorithm_version": "rewire-1"},
    )
    assert mm.event_target_key(reroll) == "c04:p1"
    assert mm.draw_for_record(reroll, "candidate") == mm.draw_for_event(
        279, 0, 1, REROLL_STREAM, "c04:p1", "candidate"
    )


def test_run_counters_are_derived_from_the_log(base):
    rejected = follower_edit(
        base,
        8,
        "c10",
        after="rejected",
        validation={"outcome": "rejected", "reason": "target_hidden"},
    )
    events = base_log(base)
    events.extend(
        [
            follower_edit(base, 7, "c04", before=0, after="off"),
            rejected,
            mm.new_mutation(
                base,
                "door_reroll",
                9,
                target={"threshold_id": "c04:p1"},
                stream=REROLL_STREAM,
                rewire={"algorithm_version": "rewire-1"},
            ),
            mm.new_mutation(
                base,
                "run_end",
                10,
                target={"cell_id": "c12"},
                stream=RUN_STREAM,
            ),
        ]
    )
    sealed = mm.seal_log(base, events)
    counters = mm.run_counters(sealed, base=base)
    assert counters["seed"] == 279
    assert counters["map_id"] == "gmap-279-gmap-0.13.0"
    assert counters["records"] == 10
    assert counters["triggers"] == 6
    assert counters["mutations"] == 4
    assert counters["accepted"] == 3
    assert counters["rejected"] == 1
    assert counters["edits"] == 1
    assert counters["rerolls"] == 1
    assert counters["rooms_visited"] == 6
    assert counters["run_ended"] is True
    assert counters["ended_at_event"] == 10


def test_replay_cli_prints_the_state_and_rejects_tamper(base, tmp_path, capsys):
    events = mm.seal_log(base, [trigger(base, 1, "c00"), follower_edit(base, 2, "c04")])
    log_path = tmp_path / "events.jsonl"
    for event in events:
        mm.append_event(log_path, event)
    expected = mm.fold_events(base, events)["state_hash"]

    assert mm.main(["replay", "--map", str(MAP_PATH), "--log", str(log_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["state_hash"] == expected
    assert output["counters"]["edits"] == 1

    assert mm.main(["cadence", "--log", str(log_path)]) == 0
    cadence = json.loads(capsys.readouterr().out)
    assert cadence["distinct_visited_cells"] == 1
    assert cadence["beats"] == []
    assert cadence["next_edit_at"] is None

    tampered = copy.deepcopy(events)
    tampered[1]["change"]["after"] = "tampered"
    write_jsonl(log_path, tampered)
    assert mm.main(["replay", "--map", str(MAP_PATH), "--log", str(log_path)]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False
    assert error["code"] == "state_hash_mismatch"
