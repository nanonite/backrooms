#!/usr/bin/env python3
"""Tests for peak sampling and for the budget arithmetic built on top of it.

The budget is the part that decides whether a stage is allowed to start, so the
arithmetic is tested against exact byte counts rather than against whatever the
test machine happens to have. The sampler is tested by injecting readings: a
sampler bug that only shows up when the GPU is busy is a bug nobody will catch.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_resource_sampler.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import resource_sampler
from resource_sampler import ResourceSampler

GIBIBYTE = 1024**3


@pytest.fixture
def scripted_readings(monkeypatch):
    """Feed the sampler a fixed sequence, repeating the last entry forever."""

    def install(*readings):
        sequence = list(readings)
        state = {"index": 0}

        def fake_sample():
            index = min(state["index"], len(sequence) - 1)
            state["index"] += 1
            return sequence[index]

        monkeypatch.setattr(resource_sampler, "_sample_once", fake_sample)
        return state

    return install


# ---------------------------------------------------------------------------
# PeakUsage arithmetic
# ---------------------------------------------------------------------------


def _peak(peak_vram, baseline_vram, peak_ram, baseline_ram):
    return resource_sampler.PeakUsage(
        peak_vram_used_bytes=peak_vram,
        peak_gpu_utilization_percent=50,
        peak_ram_used_bytes=peak_ram,
        baseline_vram_used_bytes=baseline_vram,
        baseline_ram_used_bytes=baseline_ram,
        samples_taken=10,
        missed_samples=0,
        duration_seconds=10.0,
    )


def test_stage_vram_excludes_what_the_machine_already_held():
    peak = _peak(8 * GIBIBYTE, 2 * GIBIBYTE, 4 * GIBIBYTE, 1 * GIBIBYTE)

    assert peak.stage_vram_bytes == 6 * GIBIBYTE
    assert peak.stage_ram_bytes == 3 * GIBIBYTE


def test_a_stage_that_frees_memory_reports_zero_not_a_negative():
    peak = _peak(1 * GIBIBYTE, 4 * GIBIBYTE, 1 * GIBIBYTE, 4 * GIBIBYTE)

    assert peak.stage_vram_bytes == 0
    assert peak.stage_ram_bytes == 0


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def test_sampler_reports_the_maximum_it_observed(scripted_readings):
    scripted_readings(
        (2 * GIBIBYTE, 10, 1 * GIBIBYTE),
        (7 * GIBIBYTE, 90, 3 * GIBIBYTE),
        (5 * GIBIBYTE, 40, 2 * GIBIBYTE),
    )
    sampler = ResourceSampler(interval_seconds=0.01).start()
    import time

    time.sleep(0.1)
    peak = sampler.stop()

    assert peak.peak_vram_used_bytes >= 7 * GIBIBYTE
    assert peak.peak_gpu_utilization_percent >= 90
    assert peak.peak_ram_used_bytes >= 3 * GIBIBYTE


def test_sampler_records_the_first_reading_as_the_baseline(scripted_readings):
    scripted_readings((2 * GIBIBYTE, 10, 1 * GIBIBYTE), (9 * GIBIBYTE, 90, 3 * GIBIBYTE))

    sampler = ResourceSampler(interval_seconds=0.01).start()
    sampler.stop()

    assert sampler.peak.baseline_vram_used_bytes == 2 * GIBIBYTE
    assert sampler.peak.baseline_ram_used_bytes == 1 * GIBIBYTE


def test_stop_is_idempotent_so_finally_and_explicit_calls_agree(scripted_readings):
    scripted_readings((1 * GIBIBYTE, 5, 1 * GIBIBYTE))
    sampler = ResourceSampler(interval_seconds=0.01).start()

    first = sampler.stop()
    second = sampler.stop()

    assert second is first


def test_stopping_a_sampler_that_never_started_is_an_error():
    with pytest.raises(RuntimeError, match="never started"):
        ResourceSampler().stop()


def test_a_non_positive_interval_is_rejected():
    with pytest.raises(ValueError, match="must be positive"):
        ResourceSampler(interval_seconds=0)


def test_a_failed_counter_query_is_counted_as_a_miss_not_raised(monkeypatch):
    monkeypatch.setattr(resource_sampler, "_sample_once", lambda: None)
    monkeypatch.setattr(resource_sampler, "_baseline", lambda: (0, 0))
    sampler = ResourceSampler(interval_seconds=0.01).start()
    import time

    time.sleep(0.1)
    peak = sampler.stop()

    assert peak.missed_samples > 0
    assert peak.samples_taken == 0
    assert peak.peak_vram_used_bytes == 0


def test_context_manager_stops_the_sampler_even_when_the_stage_raises(scripted_readings):
    scripted_readings((1 * GIBIBYTE, 5, 1 * GIBIBYTE))

    with pytest.raises(ZeroDivisionError):
        with ResourceSampler(interval_seconds=0.01) as sampler:
            raise ZeroDivisionError

    assert sampler.peak is not None