#!/usr/bin/env python3
"""Peak-usage tracking for a single pipeline stage.

A stage's cost is its *peak*, not its average: Splatfacto densifies until it
runs out of VRAM, so an average over the run understates what actually
happened and an average over a run that OOMs describes nothing. This samples
GPU and host counters on a fixed interval for the duration of a stage and
returns the maxima observed.

The sampler is deliberately tolerant -- a failed counter query is recorded as
a gap, not an exception -- because a benchmark must still report elapsed time
and disk when the machine is too contended to answer every poll.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from resource_probe import GpuProcess, read_memory, query_gpu_processes, query_gpus

#: How often to poll counters. One second is fine-grained enough to catch the
#: densification peak and coarse enough not to perturb the stage being timed.
DEFAULT_SAMPLE_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True)
class PeakUsage:
    """The maxima observed across a sampling window.

    ``peak_vram_used_bytes`` includes whatever other jobs already held, so
    subtract the pre-stage reading to get this stage's own cost.
    """

    peak_vram_used_bytes: int
    peak_gpu_utilization_percent: int
    peak_ram_used_bytes: int
    baseline_vram_used_bytes: int
    baseline_ram_used_bytes: int
    samples_taken: int
    missed_samples: int
    duration_seconds: float

    @property
    def stage_vram_bytes(self) -> int:
        """VRAM this stage added on top of what the machine already held."""
        return max(0, self.peak_vram_used_bytes - self.baseline_vram_used_bytes)

    @property
    def stage_ram_bytes(self) -> int:
        """Host RAM this stage added on top of what the machine already held."""
        return max(0, self.peak_ram_used_bytes - self.baseline_ram_used_bytes)


def _sample_once() -> tuple[int, int, int] | None:
    """Return ``(vram_used, gpu_util, ram_used)`` or None if a counter failed."""
    try:
        gpu = query_gpus()
        memory = read_memory()
    except (RuntimeError, OSError, ValueError):
        return None
    if not gpu:
        return None
    return gpu[0].used_vram_bytes, gpu[0].utilization_percent, memory.used_bytes


def _baseline() -> tuple[int, int]:
    """Return ``(vram_used, ram_used)`` before a stage starts, or (0, 0)."""
    sample = _sample_once()
    if sample is None:
        return 0, 0
    return sample[0], sample[2]


class ResourceSampler:
    """Sample GPU and RAM counters on a background thread for one stage.

    Use as a context manager so the sampler is always stopped, including when
    the stage raises::

        with ResourceSampler() as sampler:
            run_stage()
        print(sampler.peak.stage_vram_bytes)
    """

    def __init__(self, interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS) -> None:
        if interval_seconds <= 0:
            raise ValueError("sample interval must be positive")
        self._interval = interval_seconds
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = 0.0
        self._baseline_vram = 0
        self._baseline_ram = 0
        self._peak_vram = 0
        self._peak_util = 0
        self._peak_ram = 0
        self._samples = 0
        self._missed = 0
        self.peak: PeakUsage | None = None

    def _run(self) -> None:
        """Poll until stopped, folding each reading into the running maxima."""
        while not self._stop.is_set():
            sample = _sample_once()
            with self._lock:
                if sample is None:
                    self._missed += 1
                else:
                    self._samples += 1
                    self._peak_vram = max(self._peak_vram, sample[0])
                    self._peak_util = max(self._peak_util, sample[1])
                    self._peak_ram = max(self._peak_ram, sample[2])
            self._stop.wait(self._interval)

    def start(self) -> "ResourceSampler":
        """Take the baseline reading and begin sampling. Idempotent per instance."""
        if self._thread is not None:
            return self
        self._baseline_vram, self._baseline_ram = _baseline()
        self._peak_vram, self._peak_ram = self._baseline_vram, self._baseline_ram
        self._started_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="resource-sampler", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> PeakUsage:
        """Stop sampling and return the maxima observed.

        Idempotent, so a ``finally`` block and an explicit call can both stop
        the sampler without the second call raising.
        """
        if self._thread is None:
            if self.peak is None:
                raise RuntimeError("sampler was never started")
            return self.peak
        self._stop.set()
        self._thread.join(timeout=self._interval * 2 + 5)
        self._thread = None
        with self._lock:
            self.peak = PeakUsage(
                peak_vram_used_bytes=self._peak_vram,
                peak_gpu_utilization_percent=self._peak_util,
                peak_ram_used_bytes=self._peak_ram,
                baseline_vram_used_bytes=self._baseline_vram,
                baseline_ram_used_bytes=self._baseline_ram,
                samples_taken=self._samples,
                missed_samples=self._missed,
                duration_seconds=time.monotonic() - self._started_at,
            )
        return self.peak

    def __enter__(self) -> "ResourceSampler":
        return self.start()

    def __exit__(self, *_exception: object) -> None:
        self.stop()


def attribute_vram_holders() -> tuple[GpuProcess, ...]:
    """Return the processes holding VRAM right now, for a contention note.

    Purely informational: the preflight names the holders so an operator can
    decide what to stop, and never proposes killing anything.
    """
    return query_gpu_processes()


def read_baseline_ram(meminfo_path: Path = Path("/proc/meminfo")) -> int:
    """Return current host RAM usage in bytes; 0 when the kernel is unreadable."""
    try:
        return read_memory(meminfo_path).used_bytes
    except (OSError, ValueError):
        return 0