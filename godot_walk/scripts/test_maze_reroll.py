"""Tests for M5 rewire-1 passage-graph enumeration (#235)."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_mutation as mm
import maze_reroll as mr
from deterministic_json import ROOT, sha256_file

MAP_ROOT = ROOT / "godot_walk/room_catalog/generative_maps"
FIXTURE_PATH = ROOT / "godot_walk/fixtures/maze_reroll_v1.json"
PROJECT = ROOT / "godot_walk"
RUNNER = "res://scripts/test_issue235_reroll.gd"
SEEDS = (1, 2, 3, 32, 279)
FIXED_TIME = "2026-11-13T00:00:00Z"


def map_path(seed: int) -> Path:
    return MAP_ROOT / f"gmap-{seed}-gmap-0.13.0.json"


@pytest.fixture(scope="module")
def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def documents() -> dict[int, dict[str, Any]]:
    return {
        seed: json.loads(map_path(seed).read_text(encoding="utf-8")) for seed in SEEDS
    }


@pytest.fixture(scope="module")
def bases() -> dict[int, mm.BaseMap]:
    return {seed: mm.load_base(map_path(seed)) for seed in SEEDS}


def _plan(
    document: dict[str, Any],
    from_cell: str,
    to_cell: str,
    event_index: int = 1,
    **kwargs: Any,
) -> dict[str, Any]:
    return mr.plan_reroll(document, from_cell, to_cell, event_index, **kwargs)


def test_golden_fixture_is_not_stale(fixture):
    assert fixture == mr.build_fixture()


def test_five_seed_golden_counts(fixture):
    summary = fixture["summary"]
    assert summary["directions"] == 11
    assert summary["directions_with_pool"] == 5
    assert summary["spawn_pinned_pool_directions"] == 2
    assert summary["seed_3_directions"] == 0
    assert summary["seed_279_rich_hard"] == 13
    assert summary["seed_279_rich_in_tolerance"] == 3

    rows = {
        (int(seed), direction["from_cell"], direction["to_cell"]): direction
        for seed, record in fixture["maps"].items()
        for direction in record["directions"]
    }
    expected = {
        (1, "c05", "c03"): (5, 0, 0, []),
        (2, "c07", "c03"): (4, 0, 0, []),
        (32, "c00", "c01"): (8, 4, 2, [1, 2]),
        (32, "c01", "c00"): (6, 3, 2, [1, 2]),
        (32, "c03", "c00"): (5, 0, 0, []),
        (32, "c05", "c01"): (4, 0, 0, []),
        (32, "c08", "c03"): (3, 0, 0, []),
        (279, "c02", "c11"): (8, 13, 3, [1, 2]),
        (279, "c04", "c06"): (4, 0, 0, []),
        (279, "c06", "c11"): (5, 3, 2, [1, 2]),
        (279, "c11", "c02"): (6, 3, 2, [1, 2]),
    }
    for key, (size, hard, in_tolerance, edit_range) in expected.items():
        row = rows[key]
        assert row["target_size"] == size, key
        assert row["hard_valid"] == hard, key
        assert row["in_tolerance"] == in_tolerance, key
        assert row["edit_range"] == edit_range, key
    assert len(rows) == 11
    assert rows[(32, "c00", "c01")]["spawn_in_target"] is True
    assert rows[(32, "c01", "c00")]["spawn_in_target"] is False
    pool_directions = [row for row in rows.values() if row["in_tolerance"] >= 2]
    assert len(pool_directions) == 5
    assert sum(1 for row in pool_directions if not row["spawn_in_target"]) == 2
    assert not any(seed == 3 for seed, _, _ in rows)


def test_worked_example_c1_c2_c3_and_shortlist(documents):
    plan = _plan(documents[32], "c01", "c00", 1)
    assert plan["ok"] and plan["threshold_id"] == "c00:p0"
    assert plan["door_threshold_id"] == "c00|c01"
    assert plan["target_cells"] == ["c01", "c02", "c05", "c10", "c11", "c12"]
    assert len(plan["candidates"]) == 3
    names = {
        candidate["key"]: f"C{index}"
        for index, candidate in enumerate(plan["candidates"], start=1)
    }
    shortlist = [names[candidate["key"]] for candidate in plan["shortlist"]]
    assert shortlist == ["C1", "C2"]
    chosen = names[plan["chosen"]["key"]]
    assert chosen == "C2" and plan["chosen_rank"] == 2
    by_name = {names[candidate["key"]]: candidate for candidate in plan["candidates"]}
    assert by_name["C1"]["edit_distance"] == 1
    assert by_name["C1"]["shape"]["leaves"] == 3
    assert by_name["C1"]["shape"]["loops"] == 1
    assert by_name["C2"]["edit_distance"] == 2
    assert by_name["C2"]["shape"]["max_depth"] == 3
    assert by_name["C3"]["shape_violations"] > 0
    assert "C3" not in shortlist
    assert by_name["C3"]["passages"] == {
        ("c01", "c02"),
        ("c01", "c05"),
        ("c01", "c10"),
        ("c05", "c11"),
        ("c10", "c12"),
    }


def test_seeded_draw_is_stable_and_bounded(documents):
    first = _plan(documents[32], "c01", "c00", 1)
    second = _plan(documents[32], "c01", "c00", 1)
    assert first["chosen"]["key"] == second["chosen"]["key"]
    assert first["chosen_rank"] == second["chosen_rank"] == 2
    picks = {
        _plan(documents[32], "c01", "c00", event_index)["chosen"]["key"]
        for event_index in (1, 2, 3, 4, 5, 6)
    }
    assert len(picks) > 1
    for event_index in range(1, 8):
        plan = _plan(documents[32], "c01", "c00", event_index)
        assert 1 <= plan["chosen_rank"] <= len(plan["shortlist"])
        assert plan["chosen"] in plan["shortlist"]


def test_event_replay_is_deterministic_and_keeps_candidate_hash(bases, documents):
    base = bases[32]
    plan = _plan(documents[32], "c01", "c00", 1)
    spec = mr.rewire_event_spec(base, plan, 1, occurred_at_utc=FIXED_TIME)
    sealed = mm.seal_event(base, mm.empty_overlay(base), spec)
    overlay = mm.fold_event(base, mm.empty_overlay(base), sealed)
    replayed = mm.fold_events(base, [json.loads(json.dumps(sealed))])
    assert overlay["state_hash"] == replayed["state_hash"]
    assert sealed["rewire"]["candidate_set_hash"] == plan["candidate_set_hash"]
    assert sealed["rewire"]["candidate_count"] == 3
    assert sealed["rewire"]["shortlist_size"] == 2
    assert sealed["target"]["threshold_id"] == "c00:p0"
    assert sealed["target"]["branch_root"] == "c01"
    assert sealed["draw"]["branch_attempt"] == 2
    assert overlay["passage_overrides"]["c00:p0"]["passages_after"] == [
        ["c01", "c02"],
        ["c01", "c10"],
        ["c05", "c10"],
        ["c05", "c11"],
        ["c10", "c12"],
    ]


def test_every_hard_candidate_satisfies_r0_to_r11(documents):
    for seed, document in documents.items():
        before = copy.deepcopy(document)
        for direction in mr.enumerate_directions(document):
            plan = _plan(document, direction["from_cell"], direction["to_cell"], 1)
            if not plan["ok"]:
                continue
            target = set(plan["target_cells"])
            edges = plan["edges_before"]
            mandatory = plan["mandatory"]
            baseline = plan["shape_before"]
            min_edit, max_edit = mr.TIERS[plan["reroll_index"]]
            for candidate in plan["candidates"]:
                passages = candidate["passages"]
                assert {cell for pair in passages for cell in pair} == target
                assert candidate["edit_distance"] == len(passages ^ edges)
                assert min_edit <= candidate["edit_distance"] <= max_edit
                assert candidate["retained_fraction"] >= mr.MIN_RETAINED
                assert mandatory <= passages
                assert passages != edges
                assert mr._connected(passages, target, plan["root_cell_id"])
                assert mr._strongly_connected(
                    passages, target, mr.base_passage_state(document)
                )
                assert mr._passes_hard_invariants(
                    passages,
                    candidate,
                    edges,
                    mandatory,
                    target,
                    plan["root_cell_id"],
                    mr.base_passage_state(document),
                    plan["reroll_index"],
                    None,
                    plan["to_cell"],
                )
                degree = mr._degree(passages, plan["root_cell_id"])
                assert max(degree.values()) <= mr.MAX_DEGREE
                assert candidate["shape"] == mr.shape_metrics(
                    passages, target, plan["root_cell_id"]
                )
                assert candidate["shape_violations"] == mr.shape_violations(
                    candidate["shape"], baseline, plan["reroll_index"]
                )
        assert document == before, f"seed {seed} map document was mutated"


def test_tier_escalation_uses_the_edit_bounds(documents):
    first = _plan(documents[32], "c01", "c00", 1, reroll_index=1)
    assert {candidate["edit_distance"] for candidate in first["candidates"]} == {1, 2}
    assert first["consistency_relaxed"] is False
    second = _plan(documents[32], "c01", "c00", 1, reroll_index=2)
    assert second["ok"] is True
    assert {candidate["edit_distance"] for candidate in second["candidates"]} == {2}
    assert second["consistency_relaxed"] is True
    third = _plan(documents[32], "c01", "c00", 1, reroll_index=3)
    assert third["ok"] is False and third["reason"] == "no_candidate_in_tier"
    unsupported = _plan(documents[32], "c01", "c00", 1, algorithm_version="rewire-2")
    assert unsupported["ok"] is False
    assert unsupported["reason"] == "unsupported_algorithm"


def test_shortlist_relaxes_explicitly_on_a_thin_shape_pool():
    positions = {
        0: (0.0, 0.0),
        1: (3.0, 0.0),
        2: (6.0, 0.0),
        3: (0.0, 3.0),
        4: (3.0, 3.0),
        5: (6.0, 3.0),
    }
    document = _grid_document(
        6,
        path=[(0, 1), (1, 2), (2, 5), (5, 4), (4, 3), (3, 99)],
        positions=positions,
    )
    plan = _plan(document, "c03", "c99", 1)
    assert plan["ok"] is True
    assert len(plan["candidates"]) == 11
    in_tolerance = [
        candidate
        for candidate in plan["candidates"]
        if candidate["shape_violations"] == 0
    ]
    assert len(in_tolerance) == 1
    assert plan["consistency_relaxed"] is True
    assert len(plan["shortlist"]) == 8
    assert plan["shortlist"][0] is in_tolerance[0]


def test_python_and_gdscript_agree_on_the_shared_fixture(tmp_path):
    godot = shutil.which("godot4") or shutil.which("godot")
    if godot is None:
        pytest.skip("Godot is required for the GDScript parity check")
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "godot-data")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "godot-config")
    result = subprocess.run(
        [
            godot,
            "--headless",
            "--path",
            str(PROJECT),
            "--script",
            RUNNER,
        ],
        cwd=PROJECT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ISSUE235_REROLL: PASS" in result.stdout
    for marker in (
        "directions=11",
        "pool=5",
        "spawn_pinned=2",
        "seed279_hard=13",
        "seed279_shortlist=3",
        "seed32_chosen=C2",
    ):
        assert marker in result.stdout


def test_negative_cases_fail_closed(documents):
    corridor = _grid_document(5, path=[(0, 1), (1, 2), (2, 3), (3, 4), (4, 99)])
    assert _plans_nothing(corridor, "c04", "c99")

    tree = _grid_document(
        4,
        path=[(0, 1), (1, 2), (1, 3), (3, 99)],
        positions={0: (0.0, 0.0), 1: (3.0, 0.0), 2: (6.0, 0.0), 3: (3.0, 3.0)},
    )
    assert _plans_nothing(tree, "c03", "c99")

    two_cells = _grid_document(2, path=[(0, 1), (1, 99)])
    too_small = _plan(two_cells, "c01", "c99", 1)
    assert too_small["ok"] is False and too_small["reason"] == "target_too_small"

    drop = _drop_document()
    drop_plan = _plan(drop, "c00", "c99", 1)
    assert drop_plan["ok"] is False and drop_plan["reason"] == "drop_door"
    assert not any(
        (item["from_cell"], item["to_cell"]) == ("c00", "c99")
        for item in mr.enumerate_directions(drop)
    )

    visible = _plan(documents[32], "c01", "c00", 1, visible_cells={"c02"})
    assert visible["ok"] is False and visible["reason"] == "visible_target"

    exit_inside = _plan(documents[32], "c01", "c00", 1, exit_cell="c10")
    assert exit_inside["ok"] is False and exit_inside["reason"] == "exit_inside"
    exit_outside = _plan(documents[32], "c01", "c00", 1, exit_cell="c03")
    assert exit_outside["ok"] is True

    module_plan = _plan(documents[32], "c01", "c00", 1)
    assert ("c10", "c12") in module_plan["mandatory"]
    for candidate in module_plan["candidates"]:
        assert ("c10", "c12") in candidate["passages"]
    broken = {
        pair
        for pair in module_plan["candidates"][0]["passages"]
        if pair != ("c10", "c12")
    }
    broken_candidate = mr._candidate(
        broken,
        module_plan["edges_before"],
        module_plan["mandatory"],
        set(module_plan["target_cells"]),
        module_plan["root_cell_id"],
        mr.base_passage_state(documents[32]),
        module_plan["shape_before"],
        1,
        32,
        0,
    )
    assert not mr._passes_hard_invariants(
        broken,
        broken_candidate,
        module_plan["edges_before"],
        module_plan["mandatory"],
        set(module_plan["target_cells"]),
        module_plan["root_cell_id"],
        mr.base_passage_state(documents[32]),
        1,
        None,
        "c00",
    )

    spawn_island = _plan(documents[32], "c00", "c01", 1)
    assert spawn_island["ok"] is True
    assert spawn_island["spawn_in_target"] is True

    seed_one = _plan(documents[1], "c05", "c03", 1)
    assert seed_one["ok"] is False and not seed_one["candidates"]
    with pytest.raises(mr.RerollError):
        mr.rewire_event_spec(bases_for_seed_one(), seed_one, 1)
    rejected = mr.rejected_rewire_event_spec(
        bases_for_seed_one(), seed_one, 1, occurred_at_utc=FIXED_TIME
    )
    assert rejected["validation"]["outcome"] == "rejected"


def bases_for_seed_one() -> mm.BaseMap:
    return mm.load_base(map_path(1))


def test_stacked_rerolls_use_the_folded_current_state(documents, bases):
    document = documents[279]
    base = bases[279]
    map_before = map_path(279).read_bytes()
    map_hash_before = sha256_file(map_path(279))
    first = _plan(document, "c06", "c11", 1)
    assert first["ok"] is True
    first_event = mm.seal_event(
        base,
        mm.empty_overlay(base),
        mr.rewire_event_spec(base, first, 1, occurred_at_utc=FIXED_TIME),
    )
    overlay = mm.fold_event(base, mm.empty_overlay(base), first_event)
    state = mr.current_passage_state(document, [first_event])

    second = _plan(document, "c11", "c02", 2, state=state)
    assert second["ok"] is True
    assert set(first["target_cells"]) & set(second["target_cells"])
    current_in_target = {
        pair
        for pair in state
        if pair[0] in second["target_cells"] and pair[1] in second["target_cells"]
    }
    assert second["edges_before"] == current_in_target
    second_event = mm.seal_event(
        base,
        overlay,
        mr.rewire_event_spec(base, second, 2, occurred_at_utc=FIXED_TIME),
    )
    final = mm.fold_events(base, [first_event, second_event])
    assert final["state_hash"] == second_event["state_hash"]
    assert second_event["prev_state_hash"] == first_event["state_hash"]

    stale_state = mr.base_passage_state(document)
    with pytest.raises(mr.RerollError):
        mr.apply_rewire_event(stale_state, second_event)
    assert map_path(279).read_bytes() == map_before
    assert sha256_file(map_path(279)) == map_hash_before


def test_map_bytes_are_never_written(documents, bases):
    for seed in SEEDS:
        path = map_path(seed)
        before = path.read_bytes()
        before_hash = sha256_file(path)
        for direction in mr.enumerate_directions(documents[seed]):
            _plan(documents[seed], direction["from_cell"], direction["to_cell"], 1)
        assert path.read_bytes() == before
        assert sha256_file(path) == before_hash


def _plans_nothing(document: dict[str, Any], from_cell: str, to_cell: str) -> bool:
    plan = _plan(document, from_cell, to_cell, 1)
    return plan["ok"] is False and not plan["candidates"]


def _cell(cell_id: str, x: float, z: float, size: float = 3.0) -> dict[str, Any]:
    return {
        "cell_id": cell_id,
        "envelope_xz": [[x, z], [x + size, z], [x + size, z + size], [x, z + size]],
        "floor_y": 0.0,
        "role": "ground",
    }


def _grid_document(
    count: int,
    *,
    path: list[tuple[int, int]],
    positions: dict[int, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    if positions is None:
        positions = {index: (index * 3.0, 0.0) for index in range(count)}
    positions = dict(positions)
    positions[99] = (count * 3.0, 0.0)
    cells = [_cell(f"c{index:02d}", *positions[index]) for index in range(count)]
    cells.append(_cell("c99", *positions[99]))
    edges = []
    for first, second in path:
        edges.append(
            {
                "connector": "direct",
                "from": f"c{first:02d}:p0",
                "to": f"c{second:02d}:p0",
                "vertical": "level",
            }
        )
    return {
        "map_id": "synthetic-reroll",
        "generator_version": "gmap-0.13.0",
        "seed": 7,
        "attempt": 0,
        "cells": cells,
        "edges": edges,
    }


def _drop_document() -> dict[str, Any]:
    cells = [
        _cell("c00", 0.0, 0.0),
        _cell("c01", 3.0, 0.0),
        _cell("c02", 6.0, 0.0),
        _cell("c03", 9.0, 0.0),
        _cell("c99", 0.0, 3.0),
    ]
    cells[4]["floor_y"] = -1.5
    edges = [
        {
            "connector": "direct",
            "from": "c00:p0",
            "to": "c01:p0",
            "vertical": "level",
        },
        {
            "connector": "direct",
            "from": "c01:p0",
            "to": "c02:p0",
            "vertical": "level",
        },
        {
            "connector": "direct",
            "from": "c02:p0",
            "to": "c03:p0",
            "vertical": "level",
        },
        {
            "connector": "direct",
            "from": "c00:p1",
            "to": "c99:p0",
            "vertical": "drop",
            "drop": {
                "drop_m": 1.5,
                "upper_cell_id": "c00",
                "lower_cell_id": "c99",
            },
        },
    ]
    return {
        "map_id": "synthetic-drop",
        "generator_version": "gmap-0.13.0",
        "seed": 9,
        "attempt": 0,
        "cells": cells,
        "edges": edges,
    }
