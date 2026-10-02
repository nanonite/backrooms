#!/usr/bin/env python3
"""Tests for publishing a budget from measurements, and for refusing to invent one.

The single most important case here is the negative one: given no successful
training run, ``publish_budget`` must return nothing rather than a number. A
budget assembled from a failed run is exactly the unmeasured performance claim
this work exists to prevent.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_published_budget.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from published_budget import publish_budget
from runtime_budget import publish_runtime_budget
from splat_cost import (
    MIN_SPLAT_SPREAD,
    cost_points,
    fixed_overhead_bytes,
    is_bounded,
    marginal_bytes_per_splat,
    median_render_fps,
)
from resource_sampler import PeakUsage
from stage_measurement import StageMeasurement

GIBIBYTE = 1024**3


class GpuStub:
    name = "NVIDIA GeForce RTX 4070 Ti"
    total_vram_bytes = 12 * GIBIBYTE
    free_vram_bytes = 9 * GIBIBYTE


class SnapshotStub:
    primary_gpu = GpuStub()


def make_measurement(splat_count, stage_vram, label="splatfacto", bounded=False, settings=None):
    """Return a successful training measurement with the given cost."""
    resolved = dict(settings or {})
    resolved.setdefault("stop-split-at", "1000" if bounded else "15000")
    return StageMeasurement(
        label=label,
        command=["ns-train", "splatfacto"],
        interpreter="ns-train",
        exit_code=0,
        elapsed_seconds=600.0,
        peak=PeakUsage(
            peak_vram_used_bytes=stage_vram + 2 * GIBIBYTE,
            peak_gpu_utilization_percent=95,
            peak_ram_used_bytes=stage_vram + 4 * GIBIBYTE,
            baseline_vram_used_bytes=2 * GIBIBYTE,
            baseline_ram_used_bytes=4 * GIBIBYTE,
            samples_taken=600,
            missed_samples=0,
            duration_seconds=600.0,
        ),
        input_bytes=0,
        output_bytes=1 * GIBIBYTE,
        splat_count=splat_count,
        tool_versions={"nerfstudio": "1.1.5"},
        settings=resolved,
    )


def failing_measurement():
    """Return a measurement of a run that died."""
    return StageMeasurement(
        label="splatfacto",
        command=["ns-train"],
        interpreter="ns-train",
        exit_code=1,
        elapsed_seconds=90.0,
        peak=PeakUsage(1, 1, 1, 0, 0, 9, 0, 90.0),
        input_bytes=0,
        output_bytes=0,
        splat_count=None,
        tool_versions={},
    )


# ---------------------------------------------------------------------------
# Refusing to invent a number
# ---------------------------------------------------------------------------


def test_no_successful_run_publishes_nothing():
    budget = publish_budget("scene", [failing_measurement()], SnapshotStub(), 9 * GIBIBYTE, [])

    assert budget is None


def test_no_runs_at_all_publishes_nothing():
    assert publish_budget("scene", [], SnapshotStub(), 9 * GIBIBYTE, []) is None


def test_a_failed_run_is_not_treated_as_a_cost_point():
    assert cost_points([failing_measurement()]) == []


# ---------------------------------------------------------------------------
# The default budget
# ---------------------------------------------------------------------------


def test_default_budget_reports_the_measured_run_not_the_largest():
    bounded = make_measurement(900_000, 3 * GIBIBYTE, bounded=True)
    unbounded = make_measurement(2_000_000, 6 * GIBIBYTE, bounded=False)

    budget = publish_budget("scene", [bounded, unbounded], SnapshotStub(), 9 * GIBIBYTE, [])

    assert budget.default_splat_count == 2_000_000
    assert budget.default_stage_vram_bytes == 6 * GIBIBYTE


# ---------------------------------------------------------------------------
# The supported maximum
# ---------------------------------------------------------------------------


def test_a_measured_bounded_run_is_reported_as_measured_not_projected():
    measurements = [
        make_measurement(2_000_000, 6 * GIBIBYTE, bounded=False),
        make_measurement(4_000_000, 9 * GIBIBYTE, bounded=True),
    ]

    budget = publish_budget("scene", measurements, SnapshotStub(), 9 * GIBIBYTE, [])

    assert budget.supported_max_splats == 4_000_000
    assert "measured" in budget.max_basis


def test_a_single_run_cannot_support_a_maximum_claim():
    budget = publish_budget(
        "scene", [make_measurement(2_000_000, 6 * GIBIBYTE)], SnapshotStub(), 9 * GIBIBYTE, []
    )

    assert "unavailable" in budget.max_basis


def test_two_runs_too_close_in_splat_count_yield_no_slope():
    points = cost_points(
        [make_measurement(1_000_000, 5 * GIBIBYTE), make_measurement(1_000_100, 6 * GIBIBYTE)]
    )

    assert marginal_bytes_per_splat(points) == 0.0


def test_slope_is_measured_from_the_furthest_apart_runs():
    points = cost_points(
        [
            make_measurement(1_000_000, 4 * GIBIBYTE),
            make_measurement(2_000_000, 5 * GIBIBYTE),
            make_measurement(4_000_000, 8 * GIBIBYTE),
        ]
    )
    slope = marginal_bytes_per_splat(points)

    assert slope == pytest.approx((8 - 4) * GIBIBYTE / 3_000_000)
    assert slope > 0


def test_fixed_overhead_never_goes_negative():
    points = cost_points([make_measurement(4_000_000, 1 * GIBIBYTE)])

    assert fixed_overhead_bytes(points, 10_000.0) >= 0.0


def test_minimum_splat_spread_is_large_enough_to_be_meaningful():
    assert MIN_SPLAT_SPREAD >= 50_000


# ---------------------------------------------------------------------------
# Bounded vs unbounded
# ---------------------------------------------------------------------------


def test_the_default_stop_split_at_counts_as_unbounded():
    assert not is_bounded({"stop-split-at": "15000"})


def test_an_earlier_stop_split_at_counts_as_bounded():
    assert is_bounded({"stop-split-at": "1000"})


def test_a_measurement_without_the_setting_is_treated_as_unbounded():
    assert not is_bounded({})


# ---------------------------------------------------------------------------
# Caveats
# ---------------------------------------------------------------------------


def test_unmeasured_collision_and_import_are_named_in_the_caveats():
    budget = publish_budget(
        "scene", [make_measurement(2_000_000, 6 * GIBIBYTE)], SnapshotStub(), 9 * GIBIBYTE, []
    )

    caveats = " ".join(budget.caveats)
    assert "collision" in caveats
    assert "import" in caveats


def test_render_measurements_do_not_satisfy_the_training_caveat_check():
    """A render run measures the runtime, not reconstruction; it must not clear a gap."""
    render = make_measurement(182_569, 1 * GIBIBYTE, label="render_corridor")

    budget = publish_budget(
        "scene", [make_measurement(2_000_000, 6 * GIBIBYTE), render], SnapshotStub(), 9 * GIBIBYTE, []
    )

    assert budget.default_splat_count == 2_000_000
    assert budget.default_stage_vram_bytes == 6 * GIBIBYTE


def test_capability_problems_are_carried_into_the_caveats():
    budget = publish_budget(
        "scene",
        [make_measurement(2_000_000, 6 * GIBIBYTE)],
        SnapshotStub(),
        9 * GIBIBYTE,
        ["WebGPU collision unverified: no adapter on this host"],
    )

    assert any("WebGPU" in caveat for caveat in budget.caveats)


def test_a_successful_render_run_removes_it_from_the_caveats():
    render = make_measurement(0, 1 * GIBIBYTE, label="render")
    measurements = [make_measurement(2_000_000, 6 * GIBIBYTE), render]

    budget = publish_budget("scene", measurements, SnapshotStub(), 9 * GIBIBYTE, [])

    assert not any("render" in caveat for caveat in budget.caveats)


# ---------------------------------------------------------------------------
# Render frame rate
# ---------------------------------------------------------------------------


def test_median_render_fps_ignores_render_runs_that_did_not_report_one():
    assert median_render_fps([make_measurement(0, 1, label="render")]) == 0.0


def test_median_render_fps_takes_the_median_not_the_mean():
    def with_fps(fps):
        measurement = make_measurement(0, 1 * GIBIBYTE, label="render")
        return StageMeasurement(
            **{**measurement.__dict__, "extras": {"fps": fps}, "settings": {"resolution": "1280x720"}}
        )

    result = median_render_fps([with_fps(10.0), with_fps(60.0), with_fps(60.0)])

    assert result == 60.0

# ---------------------------------------------------------------------------
# Runtime budget
# ---------------------------------------------------------------------------


def render_measurement(splat_count, stage_vram, fps, resolution="1280x720", label="render_corridor"):
    """Return a successful render measurement with a measured frame rate."""
    base = make_measurement(splat_count, stage_vram, label=label)
    return StageMeasurement(
        **{**base.__dict__, "settings": {"resolution": resolution}, "extras": {"fps": fps}}
    )


def test_no_render_measurements_publishes_no_runtime_budget():
    measurements = [make_measurement(2_000_000, 6 * GIBIBYTE)]

    assert publish_runtime_budget(measurements, "RTX 4070 Ti") is None


def test_a_render_run_without_an_fps_publishes_no_runtime_budget():
    measurements = [make_measurement(182_569, GIBIBYTE, label="render_corridor")]

    assert publish_runtime_budget(measurements, "RTX 4070 Ti") is None


def test_the_runtime_budget_is_taken_from_the_largest_measured_asset():
    measurements = [
        render_measurement(52_034, int(0.22 * GIBIBYTE), 60.16),
        render_measurement(182_569, int(0.29 * GIBIBYTE), 60.12),
    ]

    budget = publish_runtime_budget(measurements, "RTX 4070 Ti")

    assert budget.splat_count == 182_569
    assert budget.fps == 60.12


def test_a_frame_rate_at_the_display_refresh_is_labelled_vsync_limited():
    measurements = [render_measurement(182_569, GIBIBYTE, 60.12)]

    assert publish_runtime_budget(measurements, "RTX 4070 Ti").frame_rate_is_vsync_limited


def test_a_frame_rate_far_below_refresh_is_not_called_vsync_limited():
    measurements = [render_measurement(182_569, GIBIBYTE, 22.0)]

    assert not publish_runtime_budget(measurements, "RTX 4070 Ti").frame_rate_is_vsync_limited


def test_the_runtime_budget_names_the_resolution_it_was_measured_at():
    measurements = [render_measurement(182_569, GIBIBYTE, 60.0, resolution="1920x1080")]

    assert "1920x1080" in publish_runtime_budget(measurements, "RTX 4070 Ti").resolution


def test_a_vsync_limited_result_says_it_does_not_show_headroom():
    measurements = [render_measurement(182_569, GIBIBYTE, 60.12)]

    notes = " ".join(publish_runtime_budget(measurements, "RTX 4070 Ti").notes)

    assert "does not show how much headroom is left" in notes


def test_render_points_derive_a_marginal_cost_across_assets():
    measurements = [
        render_measurement(52_034, int(0.10 * GIBIBYTE), 60.0),
        render_measurement(182_569, int(0.30 * GIBIBYTE), 60.0),
    ]

    assert publish_runtime_budget(measurements, "RTX 4070 Ti").marginal_bytes_per_splat > 0
