"""Tests for the M8 follower edit classes (#238)."""

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
import maze_surface as ms
from deterministic_json import ROOT, sha256_file

MAP_DIRECTORY = ROOT / "godot_walk/room_catalog/generative_maps"
SEEDS = (1, 2, 3, 32, 279)
FIXED_TIME = "2026-11-13T00:00:00Z"
# The reference route and the first three edits per seed.  The GDScript
# runtime pins the same table; a drift means the two implementations diverged.
EXPECTED_EDITS = {
    1: [("reverb", "c01"), ("lamp_state", "c07"), ("reverb", "c06")],
    2: [("lamp_state", "c05"), ("lamp_state", "c06"), ("surface_variant", "dp00")],
    3: [("lamp_state", "c04"), ("lamp_state", "c05"), ("wear", "c11")],
    32: [("lamp_state", "c06"), ("lamp_state", "c08"), ("reverb", "c09")],
    279: [("lamp_state", "c04"), ("lamp_state", "dp00"), ("reverb", "c10")],
}
M2_ROUTE = ["c00", "c01", "c02", "c04", "c03"]


def map_path(seed: int) -> Path:
    return MAP_DIRECTORY / f"gmap-{seed}-gmap-0.13.0.json"


@pytest.fixture(scope="module")
def base() -> mm.BaseMap:
    return mm.load_base(map_path(279))


def bfs_order(document: dict) -> list[str]:
    cells = {
        cell["cell_id"]: cell
        for cell in document["cells"]
        if cell.get("role") != "void"
    }
    graph = {cell_id: set() for cell_id in cells}
    for edge in document.get("edges", []):
        if edge.get("connector") not in ("direct", "closed_visible"):
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


def run_follower(seed: int, wanted: int = 3) -> mf.FollowerController:
    loaded = mm.load_base(map_path(seed))
    exit_cell = str(me.select_exit(loaded.document)["cell_id"])
    controller = mf.FollowerController(loaded, exit_cell=exit_cell)
    for cell_id in bfs_order(loaded.document):
        controller.enter_cell(cell_id, occurred_at_utc=FIXED_TIME)
        if edit_count(controller) >= wanted:
            break
    return controller


def edit_count(controller: mf.FollowerController) -> int:
    return sum(
        1 for event in controller.events if event.get("event_type") == "follower_edit"
    )


def controller_edits(controller: mf.FollowerController) -> list[dict]:
    return [
        event
        for event in controller.events
        if event.get("event_type") == "follower_edit"
    ]


def trigger_events(base: mm.BaseMap, route: list[str]) -> list[dict]:
    specs = [
        mm.new_trigger(
            base, "room_entered", index, player_cell=cell, occurred_at_utc=FIXED_TIME
        )
        for index, cell in enumerate(route, start=1)
    ]
    return mm.seal_log(base, specs)


def effective_snapshot(base: mm.BaseMap, overlay: dict) -> dict:
    result = {}
    for cell_id, cell in mf._cells(base.document).items():
        if not mf._is_walkable(cell):
            continue
        record = {}
        if mf._lamps(cell):
            record["lamps"] = mf.effective_lamp_states(base, overlay, cell_id)
        if type(cell.get("reverb")) is bool:
            record["reverb"] = mf.effective_reverb(base, overlay, cell_id)
        if type(cell.get("wear")) is int:
            record["wear"] = mf.effective_wear(base, overlay, cell_id)
        if cell.get("surface_variants") is not None:
            record["variants"] = mf.effective_surface_variants(base, overlay, cell_id)
        result[cell_id] = record
    return result


def test_first_edit_keeps_the_m2_lamp_golden(base):
    controller = mf.FollowerController(base, exit_cell="c09")
    for cell_id in M2_ROUTE:
        controller.enter_cell(cell_id, occurred_at_utc=FIXED_TIME)
    edits = controller_edits(controller)
    assert len(edits) == 1
    edit = edits[0]
    assert edit["change"]["class"] == "lamp_state"
    assert edit["target"]["cell_id"] == "c04"
    assert edit["change"]["after"][2] == {"lamp_index": 2, "state": "flicker"}
    assert edit["validation"]["checks"] == mf.validation_checks("lamp_state")


def test_reference_route_uses_every_m8_class():
    seen = set()
    for seed in SEEDS:
        controller = run_follower(seed)
        actual = [
            (event["change"]["class"], event["target"]["cell_id"])
            for event in controller_edits(controller)
        ]
        assert actual == EXPECTED_EDITS[seed], (seed, actual)
        seen.update(change_class for change_class, _cell in actual)
    assert {"reverb", "lamp_state", "wear", "surface_variant"} <= seen


def test_reverb_edit_flips_only_its_target_cell(base):
    events = trigger_events(base, M2_ROUTE)
    overlay = mm.empty_overlay(base)
    plan = mf.plan_follower_edit(
        base,
        overlay,
        events,
        player_cell="c03",
        event_index=6,
        exit_cell="c09",
        force_class="reverb",
        target_cell="c04",
    )
    assert plan is not None
    assert plan.change["class"] == "reverb"
    assert plan.change["layer_version"] == mf.REVERB_LAYER_VERSION
    assert plan.change["before"] is True
    assert plan.change["after"] is False
    assert plan.draw is None
    mutation = mm.new_mutation(
        base,
        "follower_edit",
        6,
        target={"cell_id": plan.target_cell},
        stream=mf.STREAM,
        change=plan.change,
        visibility=plan.visibility,
        validation={"outcome": "accepted", "checks": mf.validation_checks("reverb")},
    )
    sealed = mm.seal_event(base, overlay, mutation)
    folded = mm.fold_event(base, overlay, sealed)
    assert folded["cell_overrides"] == {"c04": {"reverb": False}}
    assert mf.effective_reverb(base, folded, "c04") is False
    empty = mm.empty_overlay(base)
    assert mf.effective_reverb(base, folded, "c05") == mf.effective_reverb(
        base, empty, "c05"
    )
    assert sha256_file(map_path(279)) == base.base_map_sha256


def test_wear_edit_increments_once_and_is_capped(base):
    route = bfs_order(base.document)[:13]
    events = trigger_events(base, route)
    overlay = mm.empty_overlay(base)
    target = "c01"
    plan = mf.plan_follower_edit(
        base,
        overlay,
        events,
        player_cell=route[-1],
        event_index=len(events) + 1,
        force_class="wear",
        target_cell=target,
    )
    assert plan is not None
    assert plan.change["class"] == "wear"
    assert plan.change["layer_version"] == ms.SURFACE_LAYER_VERSION
    assert (plan.change["before"], plan.change["after"]) == (0, 1)
    sealed = mm.seal_event(
        base,
        overlay,
        mm.new_mutation(
            base,
            "follower_edit",
            6,
            target={"cell_id": plan.target_cell},
            stream=mf.STREAM,
            change=plan.change,
            visibility=plan.visibility,
        ),
    )
    folded = mm.fold_event(base, overlay, sealed)
    assert mf.effective_wear(base, folded, target) == 1
    second = mf.plan_follower_edit(
        base,
        folded,
        events,
        player_cell=route[-1],
        event_index=len(events) + 1,
        force_class="wear",
        target_cell=target,
    )
    assert second is not None
    assert (second.change["before"], second.change["after"]) == (1, 2)
    worn_out = copy.deepcopy(folded)
    worn_out["cell_overrides"][target] = {"wear": 2}
    assert (
        mf.plan_follower_edit(
            base,
            worn_out,
            events,
            player_cell=route[-1],
            event_index=len(events) + 1,
            force_class="wear",
            target_cell=target,
        )
        is None
    )
    assert "c02" not in mf.wear_eligible_cells(base.document)
    assert "c02" in mf._cells(base.document)


def test_surface_variant_edit_moves_one_surface_within_palette(base):
    route = bfs_order(base.document)[:13]
    events = trigger_events(base, route)
    overlay = mm.empty_overlay(base)
    plan = mf.plan_follower_edit(
        base,
        overlay,
        events,
        player_cell=route[-1],
        event_index=len(events) + 1,
        force_class="surface_variant",
        target_cell="c01",
    )
    assert plan is not None
    assert plan.change["class"] == "surface_variant"
    before = plan.change["before"]
    after = plan.change["after"]
    changed = [surface for surface in ms.SURFACES if before[surface] != after[surface]]
    assert len(changed) == 1
    surface = changed[0]
    cell = mf._cells(base.document)["c01"]
    palette = ms.palette_for_cell(base.document, cell)
    assert ms.next_variant(surface, before[surface], palette) == after[surface]
    assert (
        after[surface] in palette["surfaces"][surface]["variants"]
    )
    sealed = mm.seal_event(
        base,
        overlay,
        mm.new_mutation(
            base,
            "follower_edit",
            len(events) + 1,
            target={"cell_id": plan.target_cell},
            stream=mf.STREAM,
            change=plan.change,
            draw=plan.draw,
            visibility=plan.visibility,
        ),
    )
    folded = mm.fold_event(base, overlay, sealed)
    assert folded["cell_overrides"]["c01"]["surface_variant"] == after
    assert mf.effective_surface_variants(base, folded, "c01") == after
    assert mf.effective_surface_variants(base, folded, "c02") == (
        mf.effective_surface_variants(base, overlay, "c02")
    )


def test_each_edit_changes_only_its_target_cell():
    for seed in SEEDS:
        controller = run_follower(seed)
        edits = controller_edits(controller)
        for event in edits:
            index = int(event["event_index"])
            before = mm.fold_events(controller.base, controller.events[: index - 1])
            after = mm.fold_events(controller.base, controller.events[:index])
            before_snapshot = effective_snapshot(controller.base, before)
            after_snapshot = effective_snapshot(controller.base, after)
            changed = [
                cell_id
                for cell_id in before_snapshot
                if before_snapshot[cell_id] != after_snapshot[cell_id]
            ]
            assert changed == [event["target"]["cell_id"]], (seed, event)
        targets = {event["target"]["cell_id"] for event in edits}
        assert set(controller.overlay["cell_overrides"]) == targets
        base_snapshot = effective_snapshot(
            controller.base, mm.empty_overlay(controller.base)
        )
        for cell_id, record in effective_snapshot(
            controller.base, controller.overlay
        ).items():
            if cell_id in targets:
                assert record != base_snapshot[cell_id], (seed, cell_id)
            else:
                assert record == base_snapshot[cell_id], (seed, cell_id)
        assert sha256_file(map_path(seed)) == controller.base.base_map_sha256


def test_replay_and_restore_reproduce_the_m8_overlay():
    for seed in SEEDS:
        first = run_follower(seed)
        second = run_follower(seed)
        assert first.events == second.events
        assert first.overlay == second.overlay
        replay = mm.replay(first.base, first.events)
        assert replay["overlay"] == first.overlay
        assert replay["state_hash"] == first.state_hash
        restored = mf.FollowerController(first.base, exit_cell=first.exit_cell)
        restored.restore(first.events)
        assert restored.overlay == first.overlay


def test_module_cells_take_reverb_only(base):
    module_cell = next(
        cell["cell_id"] for cell in base.document["cells"] if cell.get("module")
    )
    assert module_cell in mf.reverb_eligible_cells(base.document)
    assert module_cell not in mf.light_eligible_cells(base.document)
    assert module_cell not in mf.wear_eligible_cells(base.document)
    assert module_cell not in mf.surface_variant_eligible_cells(base.document)


def test_landmark_and_void_cells_are_never_eligible(base):
    landmark_base = mm.load_base(map_path(2))
    assert "c02" in mf._cells(landmark_base.document)
    assert "c02" not in mf.reverb_eligible_cells(landmark_base.document)
    assert "c02" not in mf.light_eligible_cells(landmark_base.document)
    assert "c02" not in mf.wear_eligible_cells(landmark_base.document)
    assert "c02" not in mf.surface_variant_eligible_cells(landmark_base.document)
    assert "c13" not in mf.reverb_eligible_cells(base.document)


def test_forced_classes_respect_the_cadence_band(base):
    events = trigger_events(base, M2_ROUTE)
    overlay = mm.empty_overlay(base)
    for forced in ("wear", "surface_variant"):
        assert (
            mf.plan_follower_edit(
                base,
                overlay,
                events,
                player_cell="c03",
                event_index=6,
                exit_cell="c09",
                force_class=forced,
            )
            is None
        )
    cadence = mm.reconstruct_cadence(events)
    assert "reverb" in cadence["allowed_classes"]
    assert "wear" not in cadence["allowed_classes"]


def test_exit_spawn_and_last_edit_are_excluded(base):
    events = trigger_events(base, M2_ROUTE)
    overlay = mm.empty_overlay(base)
    for target in ("c00", "c04", "c03"):
        assert (
            mf.plan_follower_edit(
                base,
                overlay,
                events,
                player_cell="c03",
                event_index=6,
                exit_cell="c04",
                force_class="reverb",
                target_cell=target,
            )
            is None
        ), target
    controller = run_follower(279, wanted=2)
    first_target = controller_edits(controller)[0]["target"]["cell_id"]
    assert first_target == "c04"
    second = controller_edits(controller)[1]
    assert second["target"]["cell_id"] != first_target


def test_palette_incompatible_override_is_rejected(base):
    overlay = copy.deepcopy(mm.empty_overlay(base))
    overlay["cell_overrides"]["c04"] = {
        "surface_variant": {
            "floor": "pristine",
            "wall": "clean",
            "ceiling": "clean",
            "trim": "clean",
        }
    }
    with pytest.raises(mf.FollowerEditError) as error:
        mf.effective_surface_variants(base, overlay, "c04")
    assert error.value.code in ("surface_invalid", "variant_invalid")


def test_every_event_records_its_visibility_and_checks():
    for seed in SEEDS:
        controller = run_follower(seed)
        for event in controller_edits(controller):
            assert event["event_index"] > 1
            assert event["visibility"]["player_cell"] != event["target"]["cell_id"]
            assert event["visibility"]["target_hidden"] is True
            checks = event["validation"]["checks"]
            assert checks == mf.validation_checks(event["change"]["class"])
            change_class = event["change"]["class"]
            if change_class == "surface_variant":
                assert "palette_compatible" in checks
                assert event["draw"]["purpose"] == "variant-surface"
            elif change_class.startswith("lamp_"):
                assert event["draw"]["purpose"] == "lamp-edit"
            else:
                assert "draw" not in event


def test_committed_map_is_text_and_unchanged():
    path = map_path(279)
    assert json.loads(path.read_text(encoding="utf-8"))["map_id"] == "gmap-279-gmap-0.13.0"
    assert path.read_text(encoding="utf-8").strip()
    assert sha256_file(path) == mm.load_base(path).base_map_sha256
