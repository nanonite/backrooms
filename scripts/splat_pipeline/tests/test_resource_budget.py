#!/usr/bin/env python3
"""Tests for the budget verdict: what fits, and what an operator is told to do.

The failure these guard against is a green tick that means nothing. A stage must
be blocked when its compute API is missing even though the card has plenty of
room, and it must be blocked when the measured peak eats into the headroom that
was deliberately retained. Both are cheap to get wrong and expensive to discover
during a half-hour training run.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_resource_budget.py -v
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resource_budget import (
    GIBIBYTE,
    RAM_HEADROOM_FRACTION,
    VRAM_HEADROOM_FRACTION,
    evaluate_stage,
    vram_available_bytes,
)

ROOMY_VRAM = 10 * GIBIBYTE
ROOMY_RAM = 64 * GIBIBYTE
ROOMY_DISK = 500 * GIBIBYTE


def _snapshot_stub(free_vram):
    class Gpu:
        free_vram_bytes = free_vram

    class Snapshot:
        primary_gpu = Gpu()

    return Snapshot()


def _capability_stub(free_vram):
    class Capability:
        pass

    capability = Capability()
    capability.free_vram_bytes = free_vram
    return capability


# ---------------------------------------------------------------------------
# Which VRAM number is the budget
# ---------------------------------------------------------------------------


def test_usable_vram_is_the_lower_of_the_card_and_torch_views():
    snapshot = _snapshot_stub(9 * GIBIBYTE)
    capability = _capability_stub(7 * GIBIBYTE)

    assert vram_available_bytes(snapshot, capability) == 7 * GIBIBYTE


def test_a_capability_probe_that_reported_nothing_does_not_zero_the_budget():
    snapshot = _snapshot_stub(9 * GIBIBYTE)
    capability = _capability_stub(0)

    assert vram_available_bytes(snapshot, capability) == 9 * GIBIBYTE


# ---------------------------------------------------------------------------
# Fits / does not fit
# ---------------------------------------------------------------------------


def test_a_comfortable_machine_runs_every_stage():
    verdict = evaluate_stage("splatfacto", ROOMY_VRAM, ROOMY_RAM, ROOMY_DISK)

    assert verdict.fits
    assert verdict.blockers == ()


def test_headroom_is_retained_so_the_last_slice_of_vram_is_never_spent():
    """A card with only just over the floor is still blocked: the floor is not the budget."""
    usable = int(4.5 * GIBIBYTE)

    verdict = evaluate_stage("splatfacto", usable, ROOMY_RAM, ROOMY_DISK)

    assert not verdict.fits
    assert "headroom" in verdict.blockers[0]


def test_the_headroom_boundary_is_exactly_where_the_maths_says():
    """At floor / (1 - headroom) usable bytes the stage just fits, by construction."""
    usable = int(4 * GIBIBYTE / (1.0 - VRAM_HEADROOM_FRACTION))

    assert evaluate_stage("splatfacto", usable, ROOMY_RAM, ROOMY_DISK).fits


def test_a_card_with_no_room_blocks_the_training_stage_with_an_actionable_message():
    verdict = evaluate_stage("splatfacto", 2 * GIBIBYTE, ROOMY_RAM, ROOMY_DISK)

    assert not verdict.fits
    assert "VRAM" in verdict.blockers[0]
    assert any("--stop-split-at" in action for action in verdict.actions)


def test_a_stage_whose_compute_api_is_missing_is_blocked_even_with_free_memory():
    verdict = evaluate_stage(
        "collision",
        ROOMY_VRAM,
        ROOMY_RAM,
        ROOMY_DISK,
        api_available=False,
        api_name="WebGPU collision",
        api_error="no adapter",
    )

    assert not verdict.fits
    assert any("webgpu is unavailable" in blocker for blocker in verdict.blockers)


def test_an_unavailable_api_names_the_probe_to_go_fix():
    verdict = evaluate_stage(
        "collision", ROOMY_VRAM, ROOMY_RAM, ROOMY_DISK, api_available=False, api_name="WebGPU collision"
    )

    assert any("WebGPU collision" in action for action in verdict.actions)


def test_insufficient_ram_is_reported_separately_from_insufficient_vram():
    verdict = evaluate_stage("splatfacto", ROOMY_VRAM, 4 * GIBIBYTE, ROOMY_DISK)

    assert not verdict.fits
    assert any("RAM" in blocker for blocker in verdict.blockers)


def test_a_full_disk_blocks_before_the_run_starts():
    verdict = evaluate_stage("splatfacto", ROOMY_VRAM, ROOMY_RAM, 1 * GIBIBYTE)

    assert not verdict.fits
    assert any("free disk" in blocker for blocker in verdict.blockers)


def test_an_unknown_stage_is_refused_rather_than_defaulting_to_allowed():
    verdict = evaluate_stage("teleport", ROOMY_VRAM, ROOMY_RAM, ROOMY_DISK)

    assert not verdict.fits
    assert "unknown stage" in verdict.blockers[0]


def test_headroom_fractions_are_a_real_fraction_of_the_total():
    assert 0.0 < VRAM_HEADROOM_FRACTION < 1.0
    assert 0.0 < RAM_HEADROOM_FRACTION < 1.0


def test_collision_and_training_demand_different_apis():
    training = evaluate_stage("splatfacto", ROOMY_VRAM, ROOMY_RAM, ROOMY_DISK)
    collision = evaluate_stage("collision", ROOMY_VRAM, ROOMY_RAM, ROOMY_DISK)

    assert training.compute_api == "cuda"
    assert collision.compute_api == "webgpu"
    assert training.compute_api != collision.compute_api