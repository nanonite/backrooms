"""Tests for M3 static exit selection and the run-end card (#233)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_exit as me
import maze_follower as mf
import maze_mutation as mm
from deterministic_json import ROOT, sha256_file

MAP_ROOT = ROOT / "godot_walk/room_catalog/generative_maps"
FIXTURE_PATH = ROOT / "godot_walk/fixtures/maze_exit_v1.json"
SEEDS = (1, 2, 3, 32, 279)
FIXED_TIME = "2026-11-13T00:00:00Z"


def map_path(seed: int) -> Path:
    return MAP_ROOT / f"gmap-{seed}-gmap-0.13.0.json"


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def documents() -> dict[int, dict]:
    return {
        seed: json.loads(map_path(seed).read_text(encoding="utf-8"))
        for seed in SEEDS
    }


def test_selection_is_stable_and_matches_the_shared_fixture(fixture, documents):
    assert fixture["layer_version"] == me.EXIT_LAYER_VERSION
    for seed in SEEDS:
        document = documents[seed]
        first = me.select_exit(document)
        second = me.select_exit(copy.deepcopy(document))
        assert first == second, f"seed {seed} is not deterministic"
        expected = fixture["maps"][str(seed)]["exit"]
        assert first["cell_id"] == expected["cell_id"]
        assert first["port_id"] == expected["port_id"]
        assert first["from_cell"] == expected["from_cell"]
        assert first["threshold_id"] == expected["threshold_id"]
        assert first["vertical"] == expected["vertical"]
        assert first["leaf"] is expected["leaf"]
        assert first["outside_targets"] is expected["outside_targets"]
        assert first["removed_cells"] == expected["removed_cells"]
        assert first["draw"]["rank"] == expected["rank"]
        assert first["source"] == "seed"


def test_target_map_matches_the_measured_directions(fixture, documents):
    total = 0
    for seed in SEEDS:
        targets = me.reroll_targets(documents[seed])
        expected = fixture["maps"][str(seed)]["targets"]
        assert [
            (target["from_cell"], target["to_cell"], target["target_size"])
            for target in targets
        ] == [
            (target["from_cell"], target["to_cell"], target["target_size"])
            for target in expected
        ]
        assert [target["target_cells"] for target in targets] == [
            target["target_cells"] for target in expected
        ]
        total += len(targets)
    # The §4.5.9 measurement: 11 directions across the five committed maps.
    assert total == 11
    assert len(me.reroll_targets(documents[3])) == 0


def test_selection_runs_before_eligibility(documents):
    for seed in SEEDS:
        plan = me.plan_run(documents[seed])
        exit_cell = plan["exit"]["cell_id"]
        eligible = plan["eligible_directions"]
        rejected = plan["rejected_directions"]
        assert all(exit_cell not in item["target_cells"] for item in eligible)
        for item in rejected:
            assert "exit_inside" in item["reasons"] or "exit_threshold_door" in item["reasons"]
        # The post-exit map is a strict subset of the pre-exit target map.
        assert len(eligible) + len(rejected) == len(me.reroll_targets(documents[seed]))
    # Seeds 1-3 can keep the exit outside every target; 32 and 279 cannot, and
    # the chosen cell then removes the fewest/smallest directions among leaves.
    assert me.select_exit(documents[1])["outside_targets"] is True
    assert me.select_exit(documents[2])["outside_targets"] is True
    assert me.select_exit(documents[3])["outside_targets"] is True
    assert me.select_exit(documents[32])["outside_targets"] is False
    assert me.select_exit(documents[279])["outside_targets"] is False
    assert me.select_exit(documents[32])["removed_cells"] == 6
    assert me.select_exit(documents[279])["removed_cells"] == 8
    # The rich seed 279 direction is the one the leaf exit removes, and the
    # other two pool directions stay eligible.
    rejected = me.plan_run(documents[279])["rejected_directions"]
    assert [(item["from_cell"], item["to_cell"]) for item in rejected] == [("c11", "c02")]
    assert len(me.plan_run(documents[279])["eligible_directions"]) == 3


def test_exit_cell_is_excluded_from_follower_edits(documents):
    for seed in SEEDS:
        base = mm.load_base(map_path(seed))
        exit_cell = me.select_exit(base.document)["cell_id"]
        controller = mf.FollowerController(base, exit_cell=exit_cell)
        route = _route(base.document, str(base.document["cells"][0]["cell_id"]))
        for cell_id in route:
            controller.enter_cell(cell_id, occurred_at_utc=FIXED_TIME)
        edited = {
            cell_id
            for cell_id, record in controller.overlay["cell_overrides"].items()
            if record
        }
        assert exit_cell not in edited
        assert all(
            event["target"]["cell_id"] != exit_cell
            for event in controller.events
            if event.get("event_type") == "follower_edit"
        )


def test_crossing_fires_one_run_end_and_one_end_card(documents):
    base = mm.load_base(map_path(279))
    exit_record = me.select_exit(base.document)
    run = me.ExitRun(base, exit_record)
    route = _route(base.document, str(base.document["cells"][0]["cell_id"]))
    for cell_id in route:
        if cell_id == run.exit_cell:
            continue
        run.enter_cell(cell_id, occurred_at_utc=FIXED_TIME)
        assert not run.ended
    assert run.card()["run_ended"] is False
    first = run.enter_cell(run.exit_cell, occurred_at_utc=FIXED_TIME)
    assert [event["event_type"] for event in first] == ["exit_entered", "run_end"]
    assert run.ended is True
    card = run.card()
    assert card["run_ended"] is True
    assert card["seed"] == 279
    assert card["rooms_visited"] == len(route)
    assert card["edits"] == 0
    assert card["rerolls"] == 0
    assert card["actions"] == []
    assert run.state_hash == run.overlay["state_hash"]

    # A second crossing is inert: no second trigger and no second card.
    assert run.enter_cell(run.exit_cell, occurred_at_utc=FIXED_TIME) == []
    events = run.events
    assert sum(1 for event in events if event["event_type"] == "run_end") == 1
    assert sum(1 for event in events if event["event_type"] == "exit_entered") == 1
    counters = mm.run_counters(events, base=base)
    assert counters["run_ended"] is True
    for field in ("seed", "rooms_visited", "edits", "rerolls", "run_ended"):
        assert card[field] == counters[field]
    assert card["ended_at_event"] == counters["ended_at_event"]


def test_counters_match_the_log_after_edits_and_a_crossing(documents):
    base = mm.load_base(map_path(279))
    exit_record = me.select_exit(base.document)
    exit_cell = exit_record["cell_id"]
    route = [cell for cell in _route(base.document, "c00") if cell != exit_cell]
    controller = mf.FollowerController(base, exit_cell=exit_cell)
    for cell_id in route:
        controller.enter_cell(cell_id, occurred_at_utc=FIXED_TIME)
    assert sum(
        1 for event in controller.events if event.get("event_type") == "follower_edit"
    ) >= 1
    run = me.ExitRun(base, exit_record)
    run.restore(controller.events)
    run.enter_cell(exit_cell, occurred_at_utc=FIXED_TIME)
    card = run.card()
    counters = mm.run_counters(run.events, base=base)
    for field in (
        "seed",
        "rooms_visited",
        "edits",
        "rerolls",
        "run_ended",
        "ended_at_event",
    ):
        assert card[field] == counters[field]
    assert card["edits"] == len(
        [event for event in run.events if event.get("event_type") == "follower_edit"]
    )


def test_end_card_offers_no_progression(documents):
    base = mm.load_base(map_path(279))
    run = me.ExitRun(base)
    run.enter_cell(run.exit_cell, occurred_at_utc=FIXED_TIME)
    card = run.card()
    assert card["actions"] == []
    forbidden = ("next_seed", "next_level", "next_run", "restart", "continue", "new_seed")
    assert not any(any(word in key for word in forbidden) for key in card)
    assert set(card) == {
        "schema_version",
        "title",
        "seed",
        "map_id",
        "rooms_visited",
        "edits",
        "rerolls",
        "run_ended",
        "ended_at_event",
        "actions",
    }


def test_map_bytes_are_unchanged_by_selection_and_a_run(documents):
    for seed in SEEDS:
        path = map_path(seed)
        before = sha256_file(path)
        document = json.loads(path.read_text(encoding="utf-8"))
        plan = me.plan_run(document)
        base = mm.load_base(path)
        run = me.ExitRun(base, plan["exit"])
        route = _route(document, str(document["cells"][0]["cell_id"]))
        for cell_id in route:
            run.enter_cell(cell_id, occurred_at_utc=FIXED_TIME)
        run.enter_cell(run.exit_cell, occurred_at_utc=FIXED_TIME)
        run.card()
        assert sha256_file(path) == before


def test_run_end_log_replays_to_the_same_state():
    base = mm.load_base(map_path(279))
    exit_record = me.select_exit(base.document)
    run = me.ExitRun(base, exit_record)
    route = _route(base.document, str(base.document["cells"][0]["cell_id"]))
    for cell_id in route:
        run.enter_cell(cell_id, occurred_at_utc=FIXED_TIME)
    run.enter_cell(run.exit_cell, occurred_at_utc=FIXED_TIME)
    replayed = mm.replay(base, run.events)
    assert replayed["state_hash"] == run.state_hash
    assert replayed["counters"] == mm.run_counters(run.events, base=base)
    assert me.end_card(base, run.events) == run.card()
    # Tampering with the recorded crossing is rejected, not reinterpreted.
    tampered = copy.deepcopy(run.events)
    tampered[-1]["target"]["cell_id"] = "c00"
    with pytest.raises((mm.EventRejected, mm.LogIntegrityError)):
        mm.fold_events(base, tampered)


def test_recorded_exit_layer_is_the_authority(documents):
    document = copy.deepcopy(documents[279])
    document["exit"] = {
        "layer_version": me.EXIT_LAYER_VERSION,
        "cell_id": "c11",
        "port_id": "c11:p0",
        "threshold_id": "c02|c11",
    }
    recorded = me.select_exit(document)
    assert recorded["source"] == "layer"
    assert recorded["cell_id"] == "c11"
    assert recorded["port_id"] == "c11:p0"
    assert recorded["threshold_id"] == "c02|c11"
    plan = me.plan_run(document)
    assert all(item["from_cell"] != "c11" or item["to_cell"] != "c02" for item in plan["eligible_directions"])


def test_threshold_door_is_never_a_reroll_direction(documents):
    document = copy.deepcopy(documents[279])
    document["exit"] = {
        "layer_version": me.EXIT_LAYER_VERSION,
        "cell_id": "c11",
        "port_id": "c11:p0",
        "threshold_id": "c02|c11",
    }
    plan = me.plan_run(document)
    for item in plan["eligibility"]:
        if item["threshold_id"] == "c02|c11":
            assert item["eligible"] is False
            assert "exit_threshold_door" in item["reasons"]
    assert plan["exit"]["cell_id"] not in [
        cell for item in plan["eligible_directions"] for cell in item["target_cells"]
    ]


def test_unknown_cells_and_missing_ports_fail_loudly(documents):
    broken = copy.deepcopy(documents[279])
    for cell in broken["cells"]:
        if cell["cell_id"] == "c09":
            cell["role"] = "void"
    assert me.exit_port(broken, "c09") is None
    run = me.ExitRun(mm.load_base(map_path(279)))
    with pytest.raises(me.ExitSelectionError):
        run.enter_cell("nope")


def _route(document: dict, start: str) -> list[str]:
    """Deterministic breadth-first visit order over the non-drop walkable graph."""
    graph = me.adjacency(document)
    order: list[str] = []
    seen = {start}
    queue = [start]
    while queue:
        current = queue.pop(0)
        order.append(current)
        for neighbour in sorted(graph.get(current, set())):
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return order
