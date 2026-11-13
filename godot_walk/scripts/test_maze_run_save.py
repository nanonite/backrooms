"""Tests for the M7 re-roll save, restore and cache contract (#237)."""

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
import maze_mutation as mm
import maze_reroll as mr
import maze_rewire as mw
import maze_run_save as rs
from deterministic_json import ROOT, sha256_file

FIXED_TIME = "2026-11-13T00:00:00Z"
MAP_32 = ROOT / "godot_walk/room_catalog/generative_maps/gmap-32-gmap-0.13.0.json"
MAP_279 = ROOT / "godot_walk/room_catalog/generative_maps/gmap-279-gmap-0.13.0.json"


@cache
def _document(seed: int) -> dict:
    path = (
        ROOT
        / "godot_walk/room_catalog/generative_maps"
        / f"gmap-{seed}-gmap-0.13.0.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def _specs(seed: int) -> dict:
    return mw.load_specs(str(_document(seed)["map_id"]))


def _base(seed: int) -> mm.BaseMap:
    return mm.load_base(
        ROOT
        / "godot_walk/room_catalog/generative_maps"
        / f"gmap-{seed}-gmap-0.13.0.json"
    )


def _visible_for(seed: int, from_cell: str, to_cell: str) -> set[str]:
    document = _document(seed)
    plan = md.plan(document, _specs(seed), me.select_exit(document))
    door = md.door_by_threshold(plan, mr.door_threshold_id(from_cell, to_cell))
    ports = {
        str(door["port_a"]): "latched",
        str(door["port_b"]): "latched",
    }
    return set(mf.visible_cells(document, to_cell, door_states=ports))


def _seed32_lock_and_reroll():
    document = _document(32)
    base = _base(32)
    exit_cell = str(me.select_exit(document)["cell_id"])
    visible = _visible_for(32, "c00", "c01")
    plan = mr.plan_reroll(
        document,
        "c00",
        "c01",
        2,
        exit_cell=exit_cell,
        visible_cells=visible,
    )
    assert plan["ok"] is True
    door = md.door_by_threshold(
        md.plan(document, _specs(32), me.select_exit(document)),
        "c00|c01",
    )
    lock = md.lock_spec(base, door, "c00", "c01", 1, occurred_at_utc=FIXED_TIME)
    reroll = mr.rewire_event_spec(
        base,
        plan,
        2,
        visibility={
            "player_cell": "c01",
            "visible_cells": sorted(visible),
            "target_hidden": True,
        },
        occurred_at_utc=FIXED_TIME,
    )
    return plan, mm.seal_log(base, [lock, reroll]), (lock, reroll)


def test_save_round_trip_stores_base_and_log_without_a_pool(tmp_path):
    base = _base(32)
    _plan, sealed, _specs_in = _seed32_lock_and_reroll()
    save = rs.build_save(base, sealed)
    assert set(save) == rs.SAVE_FIELDS
    assert save["base"] == base.identity
    assert save["event_log"] == sealed
    assert not (set(save) & rs.POOL_FIELDS)
    save_path = tmp_path / "run-save.json"
    rs.write_save(save_path, base, save)
    loaded = rs.read_save(save_path, base)
    assert loaded == save
    assert rs.build_save(base, loaded["event_log"]) == save


def test_save_rejects_another_base_and_a_pool_hash(tmp_path):
    base = _base(32)
    _plan, sealed, _specs_in = _seed32_lock_and_reroll()
    save = rs.build_save(base, sealed)
    with pytest.raises(mm.BaseMismatchError):
        rs.build_save(_base(1), save["event_log"])
    tampered = copy.deepcopy(save)
    tampered["base"]["base_map_sha256"] = "0" * 64
    with pytest.raises(mm.BaseMismatchError):
        rs.validate_save(tampered, base)
    with_pool = copy.deepcopy(save)
    with_pool["pool_hash"] = "f" * 64
    with pytest.raises(rs.RunSaveError) as error:
        rs.validate_save(with_pool, base)
    assert error.value.code == "pool_forbidden"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(mm.BaseMismatchError):
        rs.read_save(path, base)


def test_saved_log_restores_the_same_p_and_state_hash():
    document = _document(32)
    base = _base(32)
    map_before = MAP_32.read_bytes()
    map_hash_before = sha256_file(MAP_32)
    plan, sealed, _specs_in = _seed32_lock_and_reroll()
    save = rs.build_save(base, sealed)
    restored = rs.restore_rewire_state(document, _specs(32), save["event_log"])
    assert restored["state_hash"] == (
        "ccd2de1afc771b346d5e853e04ea1b5858573caefa268649ce79b62eef2e8f51"
    )
    assert restored["branch_epoch"] == 1 and restored["reroll_serial"] == 1
    assert restored["revisions"] == {"c03": 1, "c04": 1, "c06": 1}
    stored = sealed[-1]["rewire"]["passages_after"]
    current = {
        mw.pair_key(*pair)
        for pair in restored["state"]
        if pair[0] in sealed[-1]["rewire"]["target_cells"]
        and pair[1] in sealed[-1]["rewire"]["target_cells"]
    }
    assert current == {mw.pair_key(*pair) for pair in stored}
    assert {tuple(pair) for pair in plan["chosen"]["passages"]} == {
        tuple(pair) for pair in stored
    }
    assert MAP_32.read_bytes() == map_before
    assert sha256_file(MAP_32) == map_hash_before


def test_pending_door_reenumerates_from_the_door_lock_after_reload(tmp_path):
    document = _document(32)
    base = _base(32)
    exit_cell = str(me.select_exit(document)["cell_id"])
    visible = _visible_for(32, "c00", "c01")
    door = md.door_by_threshold(
        md.plan(document, _specs(32), me.select_exit(document)),
        "c00|c01",
    )
    lock = md.lock_spec(base, door, "c00", "c01", 1, occurred_at_utc=FIXED_TIME)
    locked_log = mm.seal_log(base, [lock])
    save = rs.build_save(base, locked_log)
    assert "pending" not in save
    path = tmp_path / "pending.json"
    rs.write_save(path, base, save)
    loaded = rs.read_save(path, base)
    before = rs.pending_rerolls(
        document,
        locked_log,
        exit_cell=exit_cell,
        visible_for=lambda _threshold: visible,
    )
    after = rs.pending_rerolls(
        document,
        loaded["event_log"],
        exit_cell=exit_cell,
        visible_for=lambda _threshold: visible,
    )
    assert before["c00|c01"]["ok"] is True
    assert (
        after["c00|c01"]["chosen"]["passages"]
        == before["c00|c01"]["chosen"]["passages"]
    )
    assert after["c00|c01"]["draw"] == before["c00|c01"]["draw"]
    assert (
        after["c00|c01"]["candidate_set_hash"]
        == before["c00|c01"]["candidate_set_hash"]
    )


def test_save_reload_at_the_door_produces_the_same_p_and_state_hash():
    document = _document(32)
    base = _base(32)
    exit_cell = str(me.select_exit(document)["cell_id"])
    visible = _visible_for(32, "c00", "c01")
    door = md.door_by_threshold(
        md.plan(document, _specs(32), me.select_exit(document)),
        "c00|c01",
    )
    lock = md.lock_spec(base, door, "c00", "c01", 1, occurred_at_utc=FIXED_TIME)
    locked = mm.seal_log(base, [lock])
    pending_before = rs.pending_rerolls(
        document,
        locked,
        exit_cell=exit_cell,
        visible_for=lambda _threshold: visible,
    )["c00|c01"]
    reroll_spec = mr.rewire_event_spec(
        base,
        pending_before,
        2,
        visibility={
            "player_cell": "c01",
            "visible_cells": sorted(visible),
            "target_hidden": True,
        },
        occurred_at_utc=FIXED_TIME,
    )
    reroll = mm.seal_event(base, mm.fold_events(base, locked), reroll_spec)
    direct = rs.restore_rewire_state(document, _specs(32), [*locked, reroll])
    save = rs.build_save(base, [*locked])
    pending_after = rs.pending_rerolls(
        document,
        save["event_log"],
        exit_cell=exit_cell,
        visible_for=lambda _threshold: visible,
    )["c00|c01"]
    reloaded_spec = mr.rewire_event_spec(
        base,
        pending_after,
        2,
        visibility={
            "player_cell": "c01",
            "visible_cells": sorted(visible),
            "target_hidden": True,
        },
        occurred_at_utc=FIXED_TIME,
    )
    reloaded_event = mm.seal_event(base, mm.fold_events(base, locked), reloaded_spec)
    assert (
        reloaded_event["rewire"]["passages_after"] == reroll["rewire"]["passages_after"]
    )
    assert reloaded_event["draw"] == reroll["draw"]
    restored = rs.restore_rewire_state(document, _specs(32), [*locked, reloaded_event])
    assert restored["state_hash"] == direct["state_hash"]
    assert restored["state_hash"] == (
        "ccd2de1afc771b346d5e853e04ea1b5858573caefa268649ce79b62eef2e8f51"
    )


def test_replay_uses_the_stored_p_when_the_enumerator_changes(monkeypatch):
    _plan, sealed, _specs_in = _seed32_lock_and_reroll()
    event = sealed[-1]
    state = mr.current_passage_state(_document(32), sealed[:-1])
    monkeypatch.setattr(mr, "ALGORITHM_VERSION", "rewire-2")
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
    unknown = copy.deepcopy(event)
    unknown["rewire"]["algorithm_version"] = "rewire-9"
    rejected = mw.apply_event_to_state(state, unknown)
    assert rejected["ok"] is False and rejected["reason"] == "unsupported_algorithm"


def test_changed_passage_revision_is_a_cache_miss():
    base = _base(32)
    cache = rs.RoomCache()
    base_key = rs.room_cache_key(base, 0, 0, 0, "c04")
    assert base_key == rs.room_cache_key(base.identity, 0, 0, 0, "c04")
    cache.put(base_key, {"cell_id": "c04", "passage_revision": 0})
    assert cache.get(base_key) == {"cell_id": "c04", "passage_revision": 0}
    assert cache.stats() == {
        "version": rs.CACHE_KEY_VERSION,
        "entries": 1,
        "hits": 1,
        "misses": 0,
    }
    for changed in (
        rs.room_cache_key(base, 0, 1, 0, "c04"),
        rs.room_cache_key(base, 1, 0, 0, "c04"),
        rs.room_cache_key(base, 0, 0, 1, "c04"),
        rs.room_cache_key(
            {**base.identity, "base_map_sha256": "0" * 64}, 0, 0, 0, "c04"
        ),
    ):
        assert changed != base_key
        assert cache.get(changed) is None
    assert cache.stats() == {
        "version": rs.CACHE_KEY_VERSION,
        "entries": 1,
        "hits": 1,
        "misses": 4,
    }


def test_stacked_rerolls_survive_save_and_restore():
    document = _document(279)
    base = _base(279)
    map_before = MAP_279.read_bytes()
    map_hash_before = sha256_file(MAP_279)
    exit_cell = str(me.select_exit(document)["cell_id"])
    first = mr.plan_reroll(document, "c06", "c11", 1, exit_cell=exit_cell)
    first_event = mm.seal_event(
        base,
        mm.empty_overlay(base),
        mr.rewire_event_spec(base, first, 1, occurred_at_utc=FIXED_TIME),
    )
    after_first = rs.restore_rewire_state(document, _specs(279), [first_event])
    second = mr.plan_reroll(
        document,
        "c11",
        "c02",
        2,
        exit_cell=exit_cell,
        state=after_first["state"],
    )
    assert second["ok"] is True
    assert set(first["target_cells"]) & set(second["target_cells"])
    current = {
        pair
        for pair in after_first["state"]
        if pair[0] in second["target_cells"] and pair[1] in second["target_cells"]
    }
    assert second["edges_before"] == current
    second_spec = mr.rewire_event_spec(base, second, 2, occurred_at_utc=FIXED_TIME)
    second_event = mm.seal_event(base, mm.fold_events(base, [first_event]), second_spec)
    direct = rs.restore_rewire_state(document, _specs(279), [first_event, second_event])
    save_one = rs.build_save(base, [first_event])
    restored_one = rs.restore_rewire_state(document, _specs(279), save_one["event_log"])
    assert restored_one["state_hash"] == after_first["state_hash"]
    second_from_save = mr.plan_reroll(
        document,
        "c11",
        "c02",
        2,
        exit_cell=exit_cell,
        state=restored_one["state"],
    )
    assert second_from_save["chosen"]["passages"] == second["chosen"]["passages"]
    save_two = rs.build_save(base, [first_event, second_event])
    restored_two = rs.restore_rewire_state(document, _specs(279), save_two["event_log"])
    assert restored_two["state_hash"] == direct["state_hash"]
    assert restored_two["revisions"] == direct["revisions"]
    assert MAP_279.read_bytes() == map_before
    assert sha256_file(MAP_279) == map_hash_before


def test_gdscript_save_restore_reports_pass(tmp_path):
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
            "res://scripts/test_issue237_save_restore.gd",
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
    assert "ISSUE237_SAVE_RESTORE: PASS" in result.stdout
    for marker in (
        "pending=true",
        "restored=true",
        "same_p=true",
        "same_hash=true",
        "cache_miss=true",
        "map_sha256=unchanged",
    ):
        assert marker in result.stdout
