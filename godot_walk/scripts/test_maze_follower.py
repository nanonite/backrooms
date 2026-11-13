"""Tests for the M2 follower lamp edit, visibility gate and cadence (#232)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_follower as mf
import maze_mutation as mm
from deterministic_json import ROOT, sha256_file

MAP_PATH = ROOT / "godot_walk/room_catalog/generative_maps/gmap-279-gmap-0.13.0.json"
# Five distinct rooms; from c03 the first two are hidden at the M2 proxy depth.
ROUTE = ["c00", "c01", "c02", "c04", "c03"]
FIXED_TIME = "2026-11-13T00:00:00Z"


@pytest.fixture(scope="module")
def base() -> mm.BaseMap:
    return mm.load_base(MAP_PATH)


def enter(controller: mf.FollowerController, cells: list[str]) -> None:
    for cell in cells:
        controller.enter_cell(cell, occurred_at_utc=FIXED_TIME)


def trigger_events(base: mm.BaseMap, cells: list[str]) -> list[dict]:
    specs = [
        mm.new_trigger(
            base,
            "room_entered",
            index,
            player_cell=cell,
            occurred_at_utc=FIXED_TIME,
        )
        for index, cell in enumerate(cells, start=1)
    ]
    return mm.seal_log(base, specs)


def test_visibility_proxy_bounds_voids_and_closed_visible(base):
    assert mf.visible_cells(base.document, "c00", depth=1) == ["c00", "c01", "c02", "c04"]
    assert "c02" in mf.visible_cells(base.document, "c03", depth=2)
    assert mf.cell_is_hidden(base.document, "c09", "c02", depth=2)
    assert not mf.cell_is_hidden(base.document, "c09", "c02", depth=3)
    assert "c13" not in mf.visible_cells(base.document, "c09", depth=2)
    assert not mf.cell_is_hidden(base.document, "c00", "c00")
    closed = mf.visible_cells(base.document, "c03", depth=1, door_states={"c03:p1": "closed"})
    assert "c07" not in closed


def test_lamp_records_and_effective_override_are_per_cell(base):
    c04 = next(cell for cell in base.document["cells"] if cell["cell_id"] == "c04")
    c05 = next(cell for cell in base.document["cells"] if cell["cell_id"] == "c05")
    states = mf.lamp_state_record(c04)
    assert states[0] == {"lamp_index": 0, "state": "flicker"}
    overlay = mm.empty_overlay(base)
    changed = copy.deepcopy(states)
    changed[0]["state"] = "dead"
    overlay["cell_overrides"]["c04"] = {"lamp_state": changed}
    effective = mf.effective_lamp_states(base, overlay, "c04")
    assert effective[0]["state"] == "dead"
    assert mf.effective_lamp_states(base, overlay, "c05") == [
        {
            "lamp_index": int(lamp["lamp_index"]),
            "state": str(lamp["state"]),
            "flicker_seed": int(lamp["flicker_seed"]),
        }
        for lamp in c05["light"]["lamps"]
    ]
    seeds = mf.lamp_flicker_record(c04)
    flicker = copy.deepcopy(seeds)
    flicker[0]["flicker_seed"] = 1234
    overlay["cell_overrides"]["c04"]["lamp_flicker"] = flicker
    assert mf.effective_lamp_states(base, overlay, "c04")[0]["flicker_seed"] == 1234


def test_controller_first_edit_is_a_hidden_lamp_left_behind(base):
    controller = mf.FollowerController(base)
    enter(controller, ROUTE[:4])
    assert [event["record_kind"] for event in controller.events] == ["trigger"] * 4
    assert controller.overlay["cell_overrides"] == {}
    enter(controller, [ROUTE[4]])
    edits = [
        event
        for event in controller.events
        if event.get("record_kind") == "mutation"
        and event.get("event_type") == "follower_edit"
    ]
    assert len(edits) == 1
    edit = edits[0]
    assert edit["target"]["cell_id"] == "c04"
    assert edit["change"]["class"] in mf.LAMP_CLASSES
    assert edit["change"]["layer_version"] == mf.LIGHT_LAYER_VERSION
    assert edit["change"]["before"][2] == {"lamp_index": 2, "state": "on"}
    assert edit["change"]["after"][2] == {"lamp_index": 2, "state": "flicker"}
    assert edit["visibility"] == {
        "player_cell": "c03",
        "target_hidden": True,
        "visible_cells": mf.visible_cells(base.document, "c03", depth=2),
    }
    assert edit["validation"]["outcome"] == "accepted"
    assert edit["draw"]["purpose"] == "lamp-edit"
    assert edit["draw"]["value"] == mm.draw_for_event(
        base.seed, base.attempt, edit["event_index"],
        mf.STREAM, "c04", "lamp-edit",
    )
    assert set(controller.overlay["cell_overrides"]) == {"c04"}
    assert controller.override_record("c04")
    assert controller.override_record("c05") == {}
    # The folded record is the new effective light, and the base map is untouched.
    effective = controller.lamp_states("c04")
    assert [entry["state"] for entry in effective] != [
        entry["state"] for entry in mf.lamp_state_record(
            next(cell for cell in base.document["cells"] if cell["cell_id"] == "c04")
        )
    ]
    assert sha256_file(MAP_PATH) == base.base_map_sha256


def test_controller_replay_is_deterministic_and_reproducible(base):
    first = mf.FollowerController(base)
    enter(first, ROUTE)
    second = mf.FollowerController(base)
    enter(second, ROUTE)
    assert first.events == second.events
    assert first.overlay == second.overlay
    replay = mm.replay(base, first.events)
    assert replay["state_hash"] == first.state_hash
    assert replay["overlay"] == first.overlay
    restored = mf.FollowerController(base)
    restored.restore(first.events)
    assert restored.overlay == first.overlay
    assert restored.events == first.events


def test_no_hidden_target_drops_the_beat(base):
    controller = mf.FollowerController(base, visibility_depth=10)
    enter(controller, ROUTE)
    assert all(event["record_kind"] == "trigger" for event in controller.events)
    assert controller.overlay["cell_overrides"] == {}
    cadence = mm.reconstruct_cadence(controller.events)
    assert cadence["distinct_visited_cells"] == 5
    assert cadence["beats"] == [5]


def test_target_selection_excludes_exit_spawn_and_the_last_edit(base):
    events = trigger_events(base, ROUTE)
    overlay = mm.empty_overlay(base)
    ordinary = mf.select_lamp_target(
        base, overlay, events, player_cell="c03", event_index=6
    )
    assert ordinary == "c04"
    with_exit = mf.select_lamp_target(
        base, overlay, events, player_cell="c03", event_index=6, exit_cell="c04"
    )
    assert with_exit == "c01"
    assert "c12" not in mf.light_eligible_cells(base.document)
    assert "c00" in mf.light_eligible_cells(base.document)
    controller = mf.FollowerController(base)
    enter(controller, ROUTE)
    assert mf.last_edited_cell(controller.events) == "c04"
    assert mf.select_lamp_target(
        base, controller.overlay, controller.events, player_cell="c03", event_index=7
    ) == "c01"


def test_lamp_flicker_edit_changes_only_the_seed(base):
    events = trigger_events(base, ROUTE)
    overlay = mm.empty_overlay(base)
    plan = mf.plan_lamp_edit(
        base,
        overlay,
        events,
        player_cell="c03",
        event_index=6,
        target_cell="c04",
        force_class="lamp_flicker",
    )
    assert plan is not None
    assert plan.change["class"] == "lamp_flicker"
    before = plan.change["before"]
    after = plan.change["after"]
    assert before[0]["flicker_seed"] != after[0]["flicker_seed"]
    assert [entry["lamp_index"] for entry in before] == [
        entry["lamp_index"] for entry in after
    ]
    mutation = mm.new_mutation(
        base,
        "follower_edit",
        6,
        target={"cell_id": plan.target_cell},
        stream=mf.STREAM,
        change=plan.change,
        draw=plan.draw,
        visibility=plan.visibility,
    )
    sealed = mm.seal_event(base, overlay, mutation)
    folded = mm.fold_event(base, overlay, sealed)
    assert folded["cell_overrides"]["c04"]["lamp_flicker"] == after
    assert "lamp_state" not in folded["cell_overrides"]["c04"]
    effective = mf.effective_lamp_states(base, folded, "c04")
    assert effective[0]["state"] == "flicker"
    assert effective[0]["flicker_seed"] == after[0]["flicker_seed"]


def test_second_beat_adds_another_cell_and_never_repeats_the_last_edit(base):
    controller = mf.FollowerController(base)
    enter(controller, ROUTE + ["c11", "dp00", "c05", "c06"])
    edits = [
        event
        for event in controller.events
        if event.get("record_kind") == "mutation"
        and event.get("event_type") == "follower_edit"
    ]
    assert len(edits) == 2
    targets = [event["target"]["cell_id"] for event in edits]
    assert targets[0] == "c04"
    assert targets[1] != targets[0]
    assert set(controller.overlay["cell_overrides"]) == set(targets)
    counters = mm.run_counters(controller.events, base=base)
    assert counters["edits"] == 2
    assert counters["rooms_visited"] == 9


def test_reentry_does_not_reconsume_the_same_beat(base):
    controller = mf.FollowerController(base)
    enter(controller, ROUTE)
    edits = [
        event for event in controller.events if event.get("event_type") == "follower_edit"
    ]
    assert len(edits) == 1
    before = len(controller.events)
    enter(controller, ["c02", "c03"])
    assert len(controller.events) == before + 2
    assert not any(
        event.get("event_type") == "follower_edit"
        for event in controller.events[before:]
    )
    assert mf.current_entry_visit_count(controller.events) is None


def test_invalid_cells_and_override_records_are_rejected(base):
    controller = mf.FollowerController(base)
    with pytest.raises(mf.FollowerEditError):
        controller.enter_cell("not-a-cell", occurred_at_utc=FIXED_TIME)
    overlay = copy.deepcopy(controller.overlay)
    overlay["cell_overrides"]["c04"] = {
        "lamp_state": [{"lamp_index": 99, "state": "dead"}]
    }
    with pytest.raises(mf.FollowerEditError):
        mf.effective_lamp_states(base, overlay, "c04")
    assert json.loads(json.dumps(overlay)) == overlay
