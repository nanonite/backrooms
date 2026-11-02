"""CPU-only tests for Hunyuan resource thresholds and process supervision."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from source_ingestion_process import run_guarded_process
from source_ingestion_resource_guard import (
    DEFAULT_LIMITS,
    GIB,
    ResourceGuardError,
    ResourceLimits,
    check_start_limits,
    runtime_stop_reason,
)


def sample(
    *,
    ram: int = 40 * GIB,
    swap: int = 20 * GIB,
    vram: int = 10 * GIB,
    swap_total: int = 24 * GIB,
    gpu_used: int = 1 * GIB,
) -> dict[str, int | str]:
    return {
        "timestamp_utc": "2026-10-27T00:00:00+00:00",
        "ram_available_bytes": ram,
        "swap_free_bytes": swap,
        "swap_total_bytes": swap_total,
        "gpu_free_bytes": vram,
        "gpu_used_bytes": gpu_used,
        "gpu_total_bytes": 12 * GIB,
        "gpu_utilization_pct": 0,
        "process_group_rss_bytes": 123,
    }


class ResourceGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.limits = ResourceLimits(
            min_start_ram_bytes=16 * GIB,
            min_start_swap_free_bytes=8 * GIB,
            min_start_vram_bytes=6 * GIB,
            min_runtime_ram_bytes=8 * GIB,
            min_runtime_swap_free_bytes=8 * GIB,
            min_runtime_vram_bytes=2 * GIB,
            max_swap_growth_bytes=1 * GIB,
            max_execution_seconds=30,
            sample_period_seconds=0.01,
        )

    def test_default_swap_growth_budget_uses_large_but_bounded_headroom(self) -> None:
        self.assertEqual(64 * GIB, DEFAULT_LIMITS.max_swap_growth_bytes)
        self.assertEqual(16 * GIB, DEFAULT_LIMITS.min_runtime_swap_free_bytes)
        start = sample(swap=90 * GIB, swap_total=100 * GIB)
        within_growth_budget = sample(swap=26 * GIB, swap_total=100 * GIB)
        exceeded_growth_budget = sample(swap=25 * GIB, swap_total=100 * GIB)
        self.assertIsNone(runtime_stop_reason(within_growth_budget, start))
        self.assertIn(
            "swap use grew",
            runtime_stop_reason(exceeded_growth_budget, start) or "",
        )

    def test_preflight_blocks_each_resource_independently(self) -> None:
        cases = (
            (sample(ram=15 * GIB), "available host RAM"),
            (sample(swap=7 * GIB), "free swap"),
            (sample(vram=5 * GIB), "free VRAM"),
        )
        for snapshot, expected in cases:
            with (
                self.subTest(expected=expected),
                self.assertRaisesRegex(ResourceGuardError, expected),
            ):
                check_start_limits(snapshot, self.limits)

    def test_runtime_monitor_stops_on_memory_swap_vram_and_external_gpu_use(self):
        start = sample()
        cases = (
            (sample(ram=7 * GIB), [], "host RAM"),
            (sample(swap=7 * GIB), [], "free swap"),
            (sample(vram=1 * GIB), [], "free VRAM"),
            (sample(swap=start["swap_free_bytes"] - 2 * GIB), [], "swap use grew"),
            (sample(), ["54321"], "external GPU compute"),
        )
        for current, external, expected in cases:
            with self.subTest(expected=expected):
                reason = runtime_stop_reason(current, start, self.limits, external)
                self.assertIn(expected, reason or "")

    def test_preflight_failure_does_not_launch_child_or_mark_attempt_started(self):
        popen = Mock()
        starts = []
        blocked_snapshot = sample(ram=1 * GIB)
        result = run_guarded_process(
            [sys.executable, "-c", "raise SystemExit(0)"],
            cwd=tempfile.gettempdir(),
            environment=os.environ.copy(),
            timeout_seconds=10,
            on_start=starts.append,
            limits=self.limits,
            snapshotter=lambda _group: blocked_snapshot,
            popen=popen,
        )

        self.assertEqual("blocked", result["status"])
        self.assertIn("host RAM", result["stop_reason"])
        self.assertEqual([], starts)
        popen.assert_not_called()

    def test_runtime_resource_drop_terminates_child_and_records_samples(self):
        snapshots = iter((sample(), sample(ram=7 * GIB)))
        starts = []
        with tempfile.TemporaryDirectory() as directory:
            result = run_guarded_process(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                cwd=directory,
                environment=os.environ.copy(),
                timeout_seconds=10,
                on_start=starts.append,
                limits=self.limits,
                snapshotter=lambda _group: next(snapshots),
                external_processes=lambda _group: [],
                sample_period_seconds=0.01,
                sleep=lambda _seconds: time.sleep(0.01),
            )

        self.assertEqual("stopped_by_guard", result["status"])
        self.assertIn("host RAM", result["stop_reason"])
        self.assertEqual(1, len(starts))
        self.assertEqual(2, result["resources"]["sample_count"])
        self.assertEqual(self.limits.as_dict(), result["resources"]["policy"])

    def test_hard_timeout_terminates_child(self):
        class FakeClock:
            def __init__(self):
                self.value = 0.0

            def now(self):
                return self.value

            def sleep(self, seconds):
                self.value += seconds
                time.sleep(0.01)

        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            result = run_guarded_process(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                cwd=directory,
                environment=os.environ.copy(),
                timeout_seconds=0.02,
                on_start=lambda _snapshot: None,
                limits=self.limits,
                snapshotter=lambda _group: sample(),
                external_processes=lambda _group: [],
                sample_period_seconds=0.01,
                sleep=clock.sleep,
                clock=clock.now,
            )

        self.assertEqual("stopped_by_guard", result["status"])
        self.assertEqual("hard inference timeout reached", result["stop_reason"])
        self.assertEqual(124, result["return_code"])


if __name__ == "__main__":
    unittest.main()
