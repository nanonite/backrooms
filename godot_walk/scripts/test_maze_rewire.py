"""Tests for the M6 re-roll rebuild and reveal contract (#236)."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_doors as md
import maze_exit as me
import maze_follower as mf
import maze_reroll as mr
import maze_rewire as mw
from deterministic_json import ROOT, sha256_file

FIXTURE_PATH = ROOT / "godot_walk/fixtures/maze_rewire_v1.json"
SEEDS = (1, 2, 3, 32, 279)


def map_path(seed: int) -> Path:
    return (
        ROOT
        / "godot_walk/room_catalog/generative_maps"
        / f"gmap-{seed}-gmap-0.13.0.json"
    )


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@cache
def _document(seed: int) -> dict:
    return json.loads(map_path(seed).read_text(encoding="utf-8"))


@cache
def _specs(seed: int) -> dict:
    return mw.load_specs(str(_document(seed)["map_id"]))


@pytest.fixture(scope="module")
def documents() -> dict[int, dict]:
    return {seed: _document(seed) for seed in SEEDS}


@pytest.fixture(scope="module")
def specs() -> dict[int, dict]:
    return {seed: _specs(seed) for seed in SEEDS}


def _case(seed: int, from_cell: str, to_cell: str, event_index: int, *, visible: bool):
    document = _document(seed)
    spec_data = _specs(seed)
    exit_record = me.select_exit(document)
    visible_cells = None
    if visible:
        door = md.door_by_threshold(
            md.plan(document, spec_data, exit_record),
            mr.door_threshold_id(from_cell, to_cell),
        )
        visible_cells = set(
            mf.visible_cells(
                document,
                to_cell,
                door_states={
                    door["port_a"]: "latched",
                    door["port_b"]: "latched",
                },
            )
        )
    return mw.build_event(
        document,
        from_cell,
        to_cell,
        event_index,
        exit_cell=str(exit_record.get("cell_id", "")),
        visible_cells=visible_cells,
    )


def test_fixture_is_not_stale(fixture):
    assert fixture == mw.build_fixture()


def test_runtime_case_rebuilds_only_the_changed_cells(fixture, documents, specs):
    case = fixture["cases"]["seed32_runtime_c00_c01"]
    assert case["ok"] is True
    assert case["changed_cells"] == ["c03", "c04", "c06"]
    assert case["passage_revisions"] == {"c03": 1, "c04": 1, "c06": 1}
    assert case["target_cells"] == [
        "c00",
        "c03",
        "c04",
        "c06",
        "c07",
        "c08",
        "c09",
        "c13",
    ]
    assert case["f0_f1_f2"]["F0"] is True
    assert case["f0_f1_f2"]["F1"] is True
    assert case["f0_f1_f2"]["F2"] is True
    assert case["geometry_issues"] == []
    assert case["identity_issues"] == []
    assert (
        case["state_hash"]
        == "ccd2de1afc771b346d5e853e04ea1b5858573caefa268649ce79b62eef2e8f51"
    )
    before = {tuple(pair) for pair in case["passages_before"]}
    after = {tuple(pair) for pair in case["passages_after"]}
    assert before - after == {("c03", "c04")}
    assert after - before == {("c04", "c06")}
    assert all(
        pair[0] in case["changed_cells"] or pair[1] in case["changed_cells"]
        for pair in after ^ before
    )
    base = copy.deepcopy(specs[32])
    built = _case(32, "c00", "c01", 2, visible=True)
    assert built["ok"] is True
    derived = mw.derive_specs(documents[32], specs[32], built["event"])
    assert derived["ok"] is True
    assert derived["changed_cells"] == ["c03", "c04", "c06"]
    for cell_id, spec in derived["specs"].items():
        assert mw.identity_issues(specs[32][cell_id], spec) == []
        assert spec["passage_revision"] == 1
        assert spec["cell_id"] == cell_id
    assert specs[32] == base


def test_stored_passages_are_applied_without_re_enumeration(documents, specs):
    plan = mr.plan_reroll(
        documents[32],
        "c00",
        "c01",
        2,
        exit_cell=str(me.select_exit(documents[32]).get("cell_id", "")),
    )
    alternate = copy.deepcopy(plan)
    alternate["chosen"] = plan["shortlist"][0]
    alternate["chosen_rank"] = 1
    event = {
        "schema_version": 1,
        "event_index": 2,
        "record_kind": "mutation",
        "event_type": "door_reroll",
        "target": {
            "door_threshold_id": "c00|c01",
            "from_cell": "c00",
            "to_cell": "c01",
        },
        "rewire": mr.rewire_block(documents[32], alternate, 2),
        "validation": {"outcome": "accepted", "checks": []},
    }
    state = mr.base_passage_state(documents[32])
    applied = mw.apply_event_to_state(state, event)
    assert applied["ok"] is True
    stored = {tuple(pair) for pair in event["rewire"]["passages_after"]}
    current = {
        pair
        for pair in applied["state"]
        if pair[0] in event["rewire"]["target_cells"]
        and pair[1] in event["rewire"]["target_cells"]
    }
    assert current == stored
    assert ("c03", "c04") in stored
    assert ("c04", "c06") in stored
    derived = mw.derive_specs(documents[32], specs[32], event)
    assert derived["ok"] is True
    assert mw.geometry_issues(documents[32], specs[32], derived["specs"], event) == []
    assert derived["changed_cells"] == ["c04", "c06"]
    revisions = {
        cell_id: spec["passage_revision"] for cell_id, spec in derived["specs"].items()
    }
    assert revisions == {"c04": 1, "c06": 1}
    graph = mw.f0_f1_f2(documents[32], applied["state"], "c01", "c02")
    assert graph["F0"] is True and graph["F1"] is True and graph["F2"] is True


def test_no_visible_change_while_the_leaf_is_closed(documents, specs):
    exit_record = me.select_exit(documents[32])
    plan = md.plan(documents[32], specs[32], exit_record)
    door = md.door_by_threshold(plan, "c00|c01")
    assert door is not None
    visible = set(
        mf.visible_cells(
            documents[32],
            "c01",
            door_states={door["port_a"]: "latched", door["port_b"]: "latched"},
        )
    )
    target = set(
        mr.plan_reroll(
            documents[32], "c00", "c01", 2, exit_cell=exit_record["cell_id"]
        )["target_cells"]
    )
    assert target & visible == set()
    rejected = mr.plan_reroll(
        documents[32],
        "c00",
        "c01",
        2,
        exit_cell=exit_record["cell_id"],
        visible_cells={"c03"},
    )
    assert rejected["ok"] is False and rejected["reason"] == "visible_target"


def test_f0_f1_f2_reject_a_disconnected_rebuild(documents, specs):
    case = _case(32, "c00", "c01", 2, visible=False)
    assert case["ok"] is True
    event = case["event"]
    broken = copy.deepcopy(event)
    broken["rewire"]["passages_after"] = [
        list(pair) for pair in event["rewire"]["pinned_passages"]
    ]
    applied = mw.apply_event_to_state(mr.base_passage_state(documents[32]), broken)
    assert applied["ok"] is True
    graph = mw.f0_f1_f2(documents[32], applied["state"], "c01", "c02")
    assert graph["F0"] is False


def test_geometry_rejects_a_corner_or_a_tall_doorway(documents, specs):
    case = _case(32, "c00", "c01", 2, visible=False)
    event = case["event"]
    derived = mw.derive_specs(documents[32], specs[32], event)
    assert derived["ok"] is True
    corner = copy.deepcopy(event)
    for record in corner["rewire"]["doorways"]:
        if record["action"] == "opened":
            wall = mr.shared_wall(
                mr.cells_by_id(documents[32])[record["cell_a"]],
                mr.cells_by_id(documents[32])[record["cell_b"]],
            )
            record["center_xz"] = [wall["start"], wall["line"]]
    assert any(
        issue.startswith("doorway_outside_wall")
        for issue in mw.geometry_issues(
            documents[32], specs[32], derived["specs"], corner
        )
    )
    tall = copy.deepcopy(event)
    for record in tall["rewire"]["doorways"]:
        if record["action"] == "opened":
            record["height_m"] = 10.0
    assert any(
        issue.startswith("doorway_too_tall")
        for issue in mw.geometry_issues(
            documents[32], specs[32], derived["specs"], tall
        )
    )


def test_geometry_rejects_an_overlapping_kept_opening():
    wall = {"axis": "x", "line": 0.0, "start": 0.0, "end": 6.0}
    new = {
        "port_id": "c00:rw_c01",
        "to_cell_id": "c01",
        "pos_xz": [0.0, 3.0],
        "width_m": 1.4,
    }
    kept = {
        "port_id": "c00:p0",
        "to_cell_id": "c02",
        "pos_xz": [0.0, 4.0],
        "width_m": 2.0,
    }
    other = {
        "port_id": "c01:rw_c00",
        "to_cell_id": "c00",
        "pos_xz": [0.0, 3.0],
        "width_m": 1.4,
    }
    specs = {"c00": {"doorways": [new, kept]}, "c01": {"doorways": [other]}}
    assert mw._overlaps_kept(new, "c00", "c01", specs, wall) is True


def test_geometry_rejects_a_content_pinned_change(documents, specs):
    event = {
        "rewire": {
            "algorithm_version": "rewire-1",
            "target_cells": ["c10", "c12"],
            "passages_before": [["c10", "c12"]],
            "passages_after": [],
            "doorways": [{"cell_a": "c10", "cell_b": "c12", "action": "closed"}],
        }
    }
    derived = mw.derive_specs(documents[32], specs[32], event)
    assert derived["ok"] is False and derived["reason"] == "content_pinned_change"


def test_cell_identity_rejects_a_layer_change(documents, specs):
    case = _case(32, "c00", "c01", 2, visible=False)
    derived = mw.derive_specs(documents[32], specs[32], case["event"])
    assert mw.identity_issues(specs[32]["c04"], derived["specs"]["c04"]) == []
    changed = copy.deepcopy(derived["specs"]["c04"])
    changed["ceiling_height_m"] = 4.0
    assert mw.identity_issues(specs[32]["c04"], changed) == ["c04:ceiling_height_m"]
    changed_light = copy.deepcopy(derived["specs"]["c04"])
    changed_light["light"]["color_temp_k"] = 1
    assert mw.identity_issues(specs[32]["c04"], changed_light) == ["c04:light"]


def test_negative_cases_and_spawn_island(documents, specs):
    visible = mr.plan_reroll(
        documents[32],
        "c00",
        "c01",
        2,
        exit_cell=me.select_exit(documents[32])["cell_id"],
        visible_cells={"c03"},
    )
    assert visible["ok"] is False and visible["reason"] == "visible_target"
    exit_inside = mr.plan_reroll(
        documents[32],
        "c01",
        "c00",
        2,
        exit_cell="c02",
    )
    assert exit_inside["ok"] is False and exit_inside["reason"] == "exit_inside"
    spawn = mr.plan_reroll(
        documents[32],
        "c00",
        "c01",
        2,
        exit_cell=me.select_exit(documents[32])["cell_id"],
    )
    assert spawn["ok"] is True and spawn["spawn_in_target"] is True
    no_candidate = _case(1, "c05", "c03", 2, visible=False)
    assert (
        no_candidate["ok"] is False and no_candidate["reason"] == "no_candidate_in_tier"
    )
    two_cells = mr.plan_reroll(
        {
            "map_id": "synthetic",
            "seed": 1,
            "cells": [
                {
                    "cell_id": "c00",
                    "role": "ground",
                    "floor_y": 0.0,
                    "envelope_xz": [[0, 0], [3, 0], [3, 3], [0, 3]],
                },
                {
                    "cell_id": "c01",
                    "role": "ground",
                    "floor_y": 0.0,
                    "envelope_xz": [[3, 0], [6, 0], [6, 3], [3, 3]],
                },
                {
                    "cell_id": "c02",
                    "role": "ground",
                    "floor_y": 0.0,
                    "envelope_xz": [[6, 0], [9, 0], [9, 3], [6, 3]],
                },
            ],
            "edges": [
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
            ],
        },
        "c00",
        "c01",
        1,
    )
    assert two_cells["ok"] is False and two_cells["reason"] == "target_too_small"


def test_gdscript_rebuild_reports_pass(tmp_path):
    godot = shutil.which("godot4") or shutil.which("godot")
    if godot is None:
        pytest.skip("Godot is required for the GDScript runtime check")
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "godot-data")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "godot-config")
    result = subprocess.run(
        [
            godot,
            "--headless",
            "--path",
            str(ROOT / "godot_walk"),
            "--script",
            "res://scripts/test_issue236_rewire.gd",
            "--",
            "--map=res://room_catalog/generative_maps/gmap-32-gmap-0.13.0.json",
            "--rooms=res://room_catalog/shape_rooms/gmap-32-gmap-0.13.0/index.json",
        ],
        cwd=ROOT / "godot_walk",
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ISSUE236_REWIRE: PASS" in result.stdout
    for marker in ("changed=3", "rebuilt=3", "rerolled=true", "hidden=true"):
        assert marker in result.stdout


def test_map_bytes_and_specs_are_never_written(documents):
    for seed in SEEDS:
        path = map_path(seed)
        before = path.read_bytes()
        before_hash = sha256_file(path)
        document = documents[seed]
        for direction in mr.enumerate_directions(document):
            plan = mr.plan_reroll(
                document,
                direction["from_cell"],
                direction["to_cell"],
                1,
                exit_cell=me.select_exit(document)["cell_id"],
            )
            if plan["ok"]:
                event = mw.build_event(
                    document,
                    direction["from_cell"],
                    direction["to_cell"],
                    1,
                    exit_cell=me.select_exit(document)["cell_id"],
                )["event"]
                derived = mw.derive_specs(
                    document, mw.load_specs(str(document["map_id"])), event
                )
                assert derived["ok"] is True
        assert path.read_bytes() == before
        assert sha256_file(path) == before_hash
