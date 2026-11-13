"""Tests for the M9 follower presence cues (#239)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_cues as mc
import maze_doors as md
import maze_exit as me
import maze_mutation as mm
from deterministic_json import ROOT, sha256_file

MAP_DIRECTORY = ROOT / "godot_walk/room_catalog/generative_maps"
SEEDS = (1, 2, 3, 32, 279)
FIXED_TIME = "2026-11-13T00:00:00Z"


def map_path(seed: int) -> Path:
    return MAP_DIRECTORY / f"gmap-{seed}-gmap-0.13.0.json"


def load(seed: int) -> mm.BaseMap:
    return mm.load_base(map_path(seed))


def bfs_order(document: dict) -> list[str]:
    cells = {
        cell["cell_id"]: cell
        for cell in document["cells"]
        if cell.get("role") != "void"
    }
    graph = {cell_id: set() for cell_id in cells}
    for edge in document.get("edges", []):
        if edge.get("connector") != "direct":
            continue
        left = str(edge["from"]).partition(":")[0]
        right = str(edge["to"]).partition(":")[0]
        if left in graph and right in graph and left != right:
            graph[left].add(right)
            graph[right].add(left)
    order: list[str] = []
    if str(document["cells"][0]["cell_id"]) not in graph:
        return order
    seen = {str(document["cells"][0]["cell_id"])}
    queue = [str(document["cells"][0]["cell_id"])]
    head = 0
    while head < len(queue):
        current = queue[head]
        head += 1
        order.append(current)
        for neighbor in sorted(graph[current]):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            queue.append(neighbor)
    return order


def door_record(document: dict, threshold: str) -> dict:
    plan = md.plan(document, {}, {})
    for door in plan["doors"]:
        if door["threshold_id"] == threshold:
            return door
    raise AssertionError(f"door {threshold} is missing")


def position_of(document: dict, cell_id: str) -> tuple[float, float, float]:
    for cell in document["cells"]:
        if cell["cell_id"] == cell_id:
            return mc.cell_position(cell)
    raise AssertionError(f"cell {cell_id} is missing")


def test_volume_falls_with_distance_and_clamps():
    near = mc.volume_at_distance(1.0)
    middle = mc.volume_at_distance(4.0)
    far = mc.volume_at_distance(64.0)
    assert math.isclose(near, mc.STEP_BASE_VOLUME_DB)
    assert math.isclose(
        middle, mc.STEP_BASE_VOLUME_DB - 2.0 * mc.ROLLOFF_DB_PER_DOUBLING
    )
    assert far == mc.STEP_MIN_VOLUME_DB
    assert near > middle > far


def test_cell_position_uses_floor_and_centre():
    document = load(279).document
    cell = next(cell for cell in document["cells"] if cell["cell_id"] == "c01")
    position = mc.cell_position(cell)
    assert position[1] == pytest.approx(
        float(cell["floor_y"]) + mc.CELL_SOURCE_HEIGHT_M
    )
    assert position[0] == pytest.approx(6.5)
    assert position[2] == pytest.approx(-5.0)


@pytest.mark.parametrize("seed", SEEDS)
def test_step_source_is_one_or_two_hops(seed):
    base = load(seed)
    order = bfs_order(base.document)
    player_cell = order[min(5, len(order) - 1)]
    source = mc.select_step_source(
        base, player_cell=player_cell, event_index=9, exit_cell=""
    )
    assert source is not None
    distances = mc.graph_distances(base.document, player_cell, max_depth=2)
    assert distances[source] in (1, 2)
    assert source != player_cell


def test_step_source_prefers_the_distant_ring():
    base = load(279)
    player_cell = "c06"
    source = mc.select_step_source(
        base, player_cell=player_cell, event_index=5, exit_cell=""
    )
    distances = mc.graph_distances(base.document, player_cell, max_depth=2)
    assert source is not None
    assert distances[source] == 2


def test_no_step_cue_before_the_first_four_rooms():
    base = load(279)
    player_cell = "c01"
    player_position = position_of(base.document, player_cell)
    plan = mc.plan_step_cue(
        base,
        player_cell=player_cell,
        player_position=player_position,
        event_index=5,
        visit_count=4,
    )
    assert plan is None


def test_step_cue_is_deterministic_with_one_to_three_steps():
    base = load(279)
    player_cell = "c01"
    player_position = position_of(base.document, player_cell)
    first = mc.plan_step_cue(
        base,
        player_cell=player_cell,
        player_position=player_position,
        event_index=5,
        visit_count=5,
    )
    second = mc.plan_step_cue(
        base,
        player_cell=player_cell,
        player_position=player_position,
        event_index=5,
        visit_count=5,
    )
    assert first is not None and second is not None
    assert first == second
    assert 1 <= first.steps <= 3
    assert first.graph_distance in (1, 2)
    assert first.distance_m > 0.0
    assert first.volume_db == pytest.approx(mc.volume_at_distance(first.distance_m))
    assert first.volume_db <= mc.STEP_BASE_VOLUME_DB
    assert first.volume_db >= mc.STEP_MIN_VOLUME_DB
    assert first.cooldown_s in range(mc.MIN_GAP_SECONDS, mc.MAX_GAP_SECONDS + 1)
    assert set(first.checks) == {
        "after_four_rooms",
        "graph_distance_one_to_two",
        "one_cue_per_edit",
        "volume_by_distance",
        "audio_only",
        "inert_cue",
    }


def test_cooldown_is_in_range_and_deterministic():
    base = load(32)
    values = [mc.cooldown_seconds(base, index) for index in range(1, 12)]
    assert all(mc.MIN_GAP_SECONDS <= value <= mc.MAX_GAP_SECONDS for value in values)
    assert values == [mc.cooldown_seconds(base, index) for index in range(1, 12)]


def test_mandatory_door_pair_and_reopen_share_the_latch():
    base = load(279)
    door = door_record(base.document, "c06|c11")
    player_position = position_of(base.document, "c11")
    close = mc.plan_door_cue(
        base.document,
        mc.DOOR_CLOSE,
        door,
        player_position=player_position,
        cooldown_s=9,
    )
    latch = mc.plan_door_cue(
        base.document,
        mc.LOCK_CLICK,
        door,
        player_position=player_position,
        cooldown_s=9,
        volume_db=close.volume_db,
        delay_s=mc.LOCK_DELAY_SECONDS,
    )
    reopen = mc.plan_door_cue(
        base.document,
        mc.DOOR_REOPEN,
        door,
        player_position=player_position,
        cooldown_s=9,
    )
    assert close.kind == mc.DOOR_CLOSE
    assert latch.kind == mc.LOCK_CLICK
    assert reopen.kind == mc.DOOR_REOPEN
    assert close.target == {"threshold_id": "c06|c11"}
    assert close.latch_sample == mc.DOOR_CLOSE_SAMPLE
    assert latch.latch_sample == mc.LOCK_CLICK_SAMPLE
    assert reopen.latch_sample == latch.latch_sample
    assert reopen.tail_sample == mc.ROOM_TONE_SAMPLE
    assert reopen.tail_sample != reopen.latch_sample
    assert latch.delay_s == pytest.approx(mc.LOCK_DELAY_SECONDS)
    assert reopen.tail_delay_s == pytest.approx(mc.REOPEN_TAIL_DELAY_SECONDS)
    assert reopen.volume_db <= close.volume_db
    assert "same_latch_as_lock_click" in reopen.checks
    assert "room_tone_tail" in reopen.checks
    assert close.distance_m == pytest.approx(latch.distance_m)
    assert mc.DOOR_MIN_VOLUME_DB <= reopen.volume_db <= 0.0


def test_cue_events_are_inert_and_keep_the_state_hash():
    base = load(279)
    door = door_record(base.document, "c06|c11")
    player_position = position_of(base.document, "c01")
    track = mc.CueTrack(base, exit_cell="c09")
    for cell_id in ["c00", "c01", "c02", "c04", "c03"]:
        track.enter_cell(cell_id)
    track.advance(12.0)
    plan = track.request_step(
        player_position=player_position, event_index=5, quiet=True
    )
    assert plan is not None
    track.latch_door(door, player_position=player_position, event_index=6)
    track.advance(3.0)
    track.reopen_door(door, player_position=player_position, event_index=7)
    assert [event["event_type"] for event in track.events] == [
        "follower_cue",
        "follower_cue",
        "follower_cue",
        "follower_cue",
    ]
    assert all("change" not in event for event in track.events)
    assert all("rewire" not in event for event in track.events)
    assert all(event["target"] for event in track.events)
    assert track.state_hash_unchanged()
    sealed = mm.seal_log(base, track.events)
    assert [event["event_type"] for event in sealed] == [
        "follower_cue",
    ] * 4
    overlay = mm.fold_events(base, sealed)
    assert overlay["state_hash"] == mm.empty_overlay(base)["state_hash"]
    assert overlay["cell_overrides"] == {}
    assert overlay["door_overrides"] == {}
    assert overlay["run"]["ended"] is False


def test_cue_track_obeys_visit_quiet_and_cooldown_gates():
    base = load(279)
    player_position = position_of(base.document, "c01")
    track = mc.CueTrack(base, exit_cell="c09")
    assert track.visit_count == 0
    for cell_id in ["c00", "c01", "c02", "c04"]:
        track.enter_cell(cell_id)
    track.advance(4.0)
    assert track.request_step(player_position=player_position, event_index=5) is None
    track.enter_cell("c03")
    track.advance(1.0)
    assert (
        track.request_step(player_position=player_position, event_index=5) is not None
    )
    cooldown_end = track.next_allowed_s
    assert cooldown_end > track.clock_s
    assert track.request_step(player_position=player_position, event_index=6) is None
    track.advance(cooldown_end - track.clock_s - 0.01)
    assert track.request_step(player_position=player_position, event_index=7) is None
    track.advance(0.02)
    assert (
        track.request_step(player_position=player_position, event_index=8) is not None
    )
    track.next_allowed_s = track.clock_s
    assert (
        track.request_step(player_position=player_position, event_index=9, quiet=False)
        is None
    )
    track.next_allowed_s = track.clock_s
    assert (
        track.request_step(player_position=player_position, event_index=10, quiet=True)
        is not None
    )


def test_map_bytes_are_unchanged():
    for seed in SEEDS:
        path = map_path(seed)
        before = sha256_file(path)
        base = load(seed)
        player_cell = bfs_order(base.document)[5]
        mc.plan_step_cue(
            base,
            player_cell=player_cell,
            player_position=position_of(base.document, player_cell),
            event_index=5,
            visit_count=5,
        )
        door = door_record(base.document, "c06|c11") if seed == 279 else None
        if door is not None:
            mc.plan_door_cue(
                base.document,
                mc.DOOR_REOPEN,
                door,
                player_position=position_of(base.document, "c11"),
                cooldown_s=8,
            )
        assert sha256_file(path) == before


def test_exit_selection_does_not_depend_on_cues():
    document = load(279).document
    selection = me.select_exit(document)
    assert selection["cell_id"] == "c09"
    assert mc.select_step_source(
        load(279), player_cell="c01", event_index=5, exit_cell="c09"
    ) not in (None, "c09")
