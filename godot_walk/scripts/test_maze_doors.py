"""Tests for M4 door leaves and lock-behind state (#234)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_doors as md
import maze_exit as me
import maze_follower as mf
import maze_mutation as mm
from deterministic_json import ROOT, sha256_file

MAP_ROOT = ROOT / "godot_walk/room_catalog/generative_maps"
ROOM_ROOT = ROOT / "godot_walk/room_catalog/shape_rooms"
FIXTURE_PATH = ROOT / "godot_walk/fixtures/maze_doors_v1.json"
SEEDS = (1, 2, 3, 32, 279)
FIXED_TIME = "2026-11-13T00:00:00Z"


def map_path(seed: int) -> Path:
    return MAP_ROOT / f"gmap-{seed}-gmap-0.13.0.json"


def rooms_path(seed: int) -> Path:
    return ROOM_ROOT / f"gmap-{seed}-gmap-0.13.0"


def load_specs(seed: int) -> dict[str, dict[str, Any]]:
    index = json.loads((rooms_path(seed) / "index.json").read_text(encoding="utf-8"))
    return {
        entry["cell_id"]: json.loads(
            (rooms_path(seed) / entry["file"]).read_text(encoding="utf-8")
        )
        for entry in index["rooms"]
    }


@pytest.fixture(scope="module")
def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def documents() -> dict[int, dict[str, Any]]:
    return {
        seed: json.loads(map_path(seed).read_text(encoding="utf-8"))
        for seed in SEEDS
    }


@pytest.fixture(scope="module")
def specs() -> dict[int, dict[str, dict[str, Any]]]:
    return {seed: load_specs(seed) for seed in SEEDS}


@pytest.fixture(scope="module")
def bases() -> dict[int, mm.BaseMap]:
    return {seed: mm.load_base(map_path(seed)) for seed in SEEDS}


def _plan(seed: int, documents: dict[int, dict[str, Any]],
          specs: dict[int, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    return md.plan(documents[seed], specs[seed], me.select_exit(documents[seed]))


def _crossing(
    door: dict[str, Any], from_cell: str, to_cell: str
) -> dict[str, Any]:
    for crossing in door["crossings"]:
        if crossing["from_cell"] == from_cell and crossing["to_cell"] == to_cell:
            return crossing
    raise AssertionError(f"{door['threshold_id']} has no crossing {from_cell}->{to_cell}")


def _first_eligible(plan: dict[str, Any]) -> dict[str, Any] | None:
    if not plan["eligible_crossings"]:
        return None
    return plan["eligible_crossings"][0]


def _run_crossing(
    base: mm.BaseMap,
    plan: dict[str, Any],
    crossing: dict[str, Any],
) -> md.DoorRun:
    run = md.DoorRun(base, {}, plan_data=plan, occurred_at_utc=FIXED_TIME)
    run.enter_cell(crossing["from_cell"])
    run.enter_cell(crossing["to_cell"])
    return run


def test_plan_matches_the_shared_fixture(fixture, documents, specs):
    for seed in SEEDS:
        plan = _plan(seed, documents, specs)
        assert md.projection(plan) == fixture["maps"][str(seed)]["plan"]
        assert plan["layer_version"] == fixture["layer_version"]


def test_crossing_target_is_the_departed_component(documents, specs):
    for seed in SEEDS:
        plan = _plan(seed, documents, specs)
        graph = me.adjacency(documents[seed])
        for door in plan["doors"]:
            for crossing in door["crossings"]:
                component = md._component_without(
                    graph, crossing["from_cell"], crossing["to_cell"]
                )
                expected = [] if component is None else sorted(component)
                assert crossing["target_cells"] == expected
                assert crossing["target_size"] == len(expected)
                assert crossing["target_hash"] == md.target_hash(expected)
                assert crossing["eligible"] == (not crossing["reasons"])
                if crossing["eligible"]:
                    assert 3 <= crossing["target_size"] <= 8
                    assert plan["exit_cell"] not in crossing["target_cells"]


def test_library_and_drop_doors_are_skipped(documents, specs, bases):
    for seed in SEEDS:
        plan = _plan(seed, documents, specs)
        library = [door for door in plan["doors"] if door["kind"] == "library"]
        assert library, f"seed {seed} has no library doorway to check"
        for door in library:
            assert door["leaf"] is False
            assert door["leaf_reason"] == "library_doorway"
            assert not any(crossing["eligible"] for crossing in door["crossings"])
        for door in plan["doors"]:
            if door["vertical"] != "drop":
                continue
            assert door["leaf"] is False
            assert door["leaf_reason"] == "drop_door"
            assert not any(crossing["eligible"] for crossing in door["crossings"])
        for door in plan["doors"]:
            if door["kind"] != "library":
                continue
            crossing = door["crossings"][0]
            run = _run_crossing(bases[seed], plan, crossing)
            assert run.states[door["threshold_id"]] == "open"
            assert md.door_counters(run.events)["locks"] == 0
            assert run.open_door(door["threshold_id"], crossing["to_cell"]) is False


def test_ramp_leaf_fit_and_the_missing_landing_negative(documents, specs, bases):
    plan = _plan(2, documents, specs)
    ramp = md.door_by_threshold(plan, "c03|c07")
    assert ramp is not None and ramp["vertical"] == "ramp" and ramp["leaf"] is True
    crossing = _first_eligible(plan)
    assert crossing is not None
    run = _run_crossing(bases[2], plan, crossing)
    assert run.states["c03|c07"] == "latched"

    broken = copy.deepcopy(specs[2])
    lower = ramp["cell_b"]
    broken[lower]["ramps"] = [
        item for item in broken[lower].get("ramps", [])
        if item.get("port_id") != ramp["port_b"]
    ]
    broken_plan = md.plan(documents[2], broken, me.select_exit(documents[2]))
    broken_door = md.door_by_threshold(broken_plan, "c03|c07")
    assert broken_door["leaf"] is False
    assert broken_door["leaf_reason"] == "ramp_no_landing"
    assert not any(item["eligible"] for item in broken_door["crossings"])
    assert not any(
        crossing["threshold_id"] == "c03|c07"
        for crossing in broken_plan["eligible_crossings"]
    )


def test_drop_door_never_latches(documents, specs, bases):
    plan = _plan(279, documents, specs)
    drop = md.door_by_threshold(plan, "c00|c02")
    assert drop is not None and drop["vertical"] == "drop"
    assert drop["leaf"] is False and drop["leaf_reason"] == "drop_door"
    crossing = drop["crossings"][0]
    run = _run_crossing(bases[279], plan, crossing)
    assert run.states["c00|c02"] == "open"
    assert md.door_counters(run.events)["locks"] == 0


def test_latch_records_one_event_and_folds_into_the_overlay(documents, specs, bases):
    for seed in SEEDS:
        plan = _plan(seed, documents, specs)
        eligible = plan["eligible_crossings"]
        if not eligible:
            assert seed == 3
            continue
        crossing = eligible[0]
        door = md.door_by_threshold(plan, crossing["threshold_id"])
        run = _run_crossing(bases[seed], plan, crossing)
        assert run.states[door["threshold_id"]] == "latched"
        assert md.door_counters(run.events)["locks"] == 1
        overlay = run.overlay
        assert overlay["door_overrides"][door["threshold_id"]]["state"] == "latched"
        assert overlay["cell_overrides"] == {}
        assert overlay["state_hash"] == mm.fold_events(bases[seed], run.events)["state_hash"]
        event = next(item for item in run.events if item["event_type"] == "door_lock")
        assert event["target"]["threshold_id"] == door["threshold_id"]
        assert event["target"]["from_cell"] == crossing["from_cell"]
        assert event["change"]["class"] == "state"
        assert event["change"]["after"] == "latched"
        assert event["validation"]["checks"] == list(md.LOCK_CHECKS)


def test_closed_leaf_occludes_the_departed_side(documents, specs):
    plan = _plan(279, documents, specs)
    crossing = plan["eligible_crossings"][0]
    door = md.door_by_threshold(plan, crossing["threshold_id"])
    run = md.DoorRun(
        mm.load_base(map_path(279)), specs[279], plan_data=plan,
        occurred_at_utc=FIXED_TIME,
    )
    run.enter_cell(crossing["from_cell"])
    assert not mf.cell_is_hidden(
        documents[279], crossing["to_cell"], crossing["from_cell"]
    )
    run.enter_cell(crossing["to_cell"])
    port_states = md.port_states(plan, run.states)
    assert port_states[door["port_a"]] == "latched"
    assert port_states[door["port_b"]] == "latched"
    assert mf.cell_is_hidden(
        documents[279],
        crossing["to_cell"],
        crossing["from_cell"],
        door_states=port_states,
    )
    assert crossing["from_cell"] not in mf.visible_cells(
        documents[279], crossing["to_cell"], door_states=port_states
    )


def test_exit_is_not_lock_behind_eligible_and_stays_reachable(documents, specs, bases):
    for seed in SEEDS:
        plan = _plan(seed, documents, specs)
        exit_threshold = plan["exit_threshold_id"]
        exit_door = md.door_by_threshold(plan, exit_threshold)
        assert exit_door is not None
        assert exit_door["exit_threshold"] is True
        assert not any(crossing["eligible"] for crossing in exit_door["crossings"])
        assert md.exit_reachable(
            documents[seed], plan["exit_cell"],
            str(documents[seed]["cells"][0]["cell_id"]), set(),
        )
        for crossing in plan["eligible_crossings"]:
            run = _run_crossing(bases[seed], plan, crossing)
            assert run.states[crossing["threshold_id"]] == "latched"
            assert md.exit_reachable(
                documents[seed],
                plan["exit_cell"],
                crossing["to_cell"],
                {crossing["threshold_id"]},
            )
        run = md.DoorRun(bases[seed], specs[seed], plan_data=plan,
                         occurred_at_utc=FIXED_TIME)
        cells = ("c00", plan["exit_cell"]) if seed != 3 else ()
        for cell in cells:
            run.enter_cell(cell)
        if seed != 3:
            assert md.door_counters(run.events)["locks"] == 0


def test_manual_open_only_from_the_current_side(documents, specs, bases):
    plan = _plan(279, documents, specs)
    crossing = plan["eligible_crossings"][0]
    door = md.door_by_threshold(plan, crossing["threshold_id"])
    run = _run_crossing(bases[279], plan, crossing)
    assert run.open_door(door["threshold_id"], "not_a_cell") is False
    assert run.states[door["threshold_id"]] == "latched"
    assert run.open_door(door["threshold_id"]) is True
    assert run.states[door["threshold_id"]] == "open"
    assert run.overlay["door_overrides"][door["threshold_id"]]["state"] == "open"
    assert md.door_counters(run.events) == {"locks": 1, "opens": 1, "rejected": 0}
    assert run.open_door(door["threshold_id"]) is False
    unlock = next(item for item in run.events if item["event_type"] == "door_unlock")
    assert unlock["change"]["before"] == "latched"
    assert unlock["change"]["after"] == "open"


def test_save_restore_round_trip(documents, specs, bases):
    plan = _plan(279, documents, specs)
    crossing = plan["eligible_crossings"][0]
    door = md.door_by_threshold(plan, crossing["threshold_id"])
    run = _run_crossing(bases[279], plan, crossing)
    saved = json.loads(json.dumps(run.events))
    restored = md.DoorRun(bases[279], specs[279], plan_data=plan,
                          occurred_at_utc=FIXED_TIME)
    restored.restore(saved)
    assert restored.states == run.states
    assert restored.state_hash == run.state_hash
    assert restored.overlay["state_hash"] == run.overlay["state_hash"]
    assert restored.events == run.events
    assert run.open_door(door["threshold_id"], crossing["to_cell"]) is True
    assert restored.open_door(door["threshold_id"], crossing["to_cell"]) is True
    assert restored.overlay["state_hash"] == run.overlay["state_hash"]
    assert restored.state_hash == run.state_hash


def test_fixture_replay_matches(documents, specs):
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for seed in SEEDS:
        plan = _plan(seed, documents, specs)
        replay = fixture["maps"][str(seed)]["replay"]
        states = md.fold_states(plan, replay["events"])
        assert states == replay["states"]
        assert md.state_hash(states) == replay["state_hash"]


def test_map_bytes_are_never_written(bases, documents, specs):
    for seed in SEEDS:
        path = map_path(seed)
        before = path.read_bytes()
        before_hash = sha256_file(path)
        plan = _plan(seed, documents, specs)
        md.projection(plan)
        crossing = _first_eligible(plan)
        if crossing is not None:
            _run_crossing(bases[seed], plan, crossing)
        assert path.read_bytes() == before
        assert sha256_file(path) == before_hash
