#!/usr/bin/env python3
"""Low-level readers for the counters the preflight and the benchmark need.

Everything here returns a snapshot of *now*. Nothing here decides whether a
number is good enough -- that judgement lives in ``resource_budget.py`` so the
readers stay testable against fake files and fake command output.

Deliberately reading ``nvidia-smi`` instead of asking torch: the pipeline runs
its heavy stages in a separate interpreter, and the amount of VRAM actually
*usable right now* is smaller than the card's total whenever a display server
or another job already holds an allocation. Total VRAM is not a budget.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: ``/proc/meminfo`` exposes sizes in kibibytes; every reader here converts to
#: bytes so no caller has to remember which unit a number arrived in.
KIBIBYTE = 1024

#: Seconds to wait for a counter query before treating the tool as unavailable.
COUNTER_QUERY_TIMEOUT_SECONDS = 10

#: Both counter queries run with ``nounits``, under which ``nvidia-smi`` reports
#: every memory field in mebibytes and percentages as bare numbers.
MIBIBYTE = 1024**2

NVIDIA_SMI = "nvidia-smi"

_MEMINFO_TOTAL = "MemTotal"
_MEMINFO_AVAILABLE = "MemAvailable"

_GPU_QUERY_FIELDS = (
    "index",
    "name",
    "memory.total",
    "memory.used",
    "memory.free",
    "utilization.gpu",
    "temperature.gpu",
)

_COMPUTE_PROCESS_FIELDS = ("pid", "process_name", "used_gpu_memory")


@dataclass(frozen=True)
class MemoryReading:
    """Host RAM in bytes, as reported by the kernel at one instant."""

    total_bytes: int
    available_bytes: int

    @property
    def used_bytes(self) -> int:
        return self.total_bytes - self.available_bytes


@dataclass(frozen=True)
class GpuReading:
    """One GPU's instantaneous state, in bytes / percent / celsius."""

    index: int
    name: str
    total_vram_bytes: int
    used_vram_bytes: int
    free_vram_bytes: int
    utilization_percent: int
    temperature_celsius: int


@dataclass(frozen=True)
class GpuProcess:
    """A process currently holding VRAM. Attribution only, never a kill list."""

    pid: int
    process_name: str
    used_vram_bytes: int


@dataclass(frozen=True)
class FilesystemReading:
    """Space on the filesystem backing ``path``."""

    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int


def parse_gpu_csv(text: str) -> list[GpuReading]:
    """Parse ``nvidia-smi`` CSV rows into :class:`GpuReading` values.

    Expects the ``nounits`` form used by :func:`_run_nvidia_smi`, so memory
    columns are mebibytes. Kept separate from the subprocess call so tests can
    drive it with captured output instead of needing a GPU attached.
    """
    readings: list[GpuReading] = []
    for row in text.strip().splitlines():
        cells = [cell.strip() for cell in row.split(",")]
        if len(cells) != len(_GPU_QUERY_FIELDS):
            continue
        readings.append(
            GpuReading(
                index=int(cells[0]),
                name=cells[1],
                total_vram_bytes=int(cells[2]) * MIBIBYTE,
                used_vram_bytes=int(cells[3]) * MIBIBYTE,
                free_vram_bytes=int(cells[4]) * MIBIBYTE,
                utilization_percent=int(cells[5]),
                temperature_celsius=int(cells[6]),
            )
        )
    return readings


def parse_compute_process_csv(text: str) -> tuple[GpuProcess, ...]:
    """Parse ``nvidia-smi --query-compute-apps`` output, skipping error rows."""
    processes: list[GpuProcess] = []
    for row in text.strip().splitlines():
        cells = [cell.strip() for cell in row.split(",")]
        if len(cells) != len(_COMPUTE_PROCESS_FIELDS):
            continue
        if not cells[0].isdigit():
            continue
        processes.append(
            GpuProcess(
                pid=int(cells[0]),
                process_name=cells[1],
                used_vram_bytes=int(cells[2]) * MIBIBYTE,
            )
        )
    return tuple(processes)


def parse_meminfo(text: str) -> MemoryReading:
    """Extract total/available RAM from ``/proc/meminfo`` content."""
    values = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key in (_MEMINFO_TOTAL, _MEMINFO_AVAILABLE):
            values[key] = int(rest.split()[0]) * KIBIBYTE
    if _MEMINFO_TOTAL not in values or _MEMINFO_AVAILABLE not in values:
        raise ValueError("meminfo is missing MemTotal or MemAvailable")
    return MemoryReading(total_bytes=values[_MEMINFO_TOTAL], available_bytes=values[_MEMINFO_AVAILABLE])


def read_memory(meminfo_path: Path = Path("/proc/meminfo")) -> MemoryReading:
    """Read host RAM. Raises OSError if the kernel interface is unreadable."""
    return parse_meminfo(meminfo_path.read_text())


def _run_nvidia_smi(arguments: list[str]) -> str:
    """Run ``nvidia-smi`` with CSV output, raising on a non-zero exit."""
    completed = subprocess.run(
        [NVIDIA_SMI, *arguments, "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=COUNTER_QUERY_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "nvidia-smi failed")
    return completed.stdout


def query_gpus() -> tuple[GpuReading, ...]:
    """Return the instantaneous state of every NVIDIA GPU, or raise."""
    fields = ",".join(_GPU_QUERY_FIELDS)
    return tuple(parse_gpu_csv(_run_nvidia_smi(["--query-gpu=" + fields])))


def query_gpu_processes() -> tuple[GpuProcess, ...]:
    """Return the processes currently holding VRAM, or an empty tuple."""
    fields = ",".join(_COMPUTE_PROCESS_FIELDS)
    try:
        return parse_compute_process_csv(_run_nvidia_smi(["--query-compute-apps=" + fields]))
    except (RuntimeError, subprocess.TimeoutExpired, FileNotFoundError):
        return ()


def filesystem_usage(path: str | Path) -> FilesystemReading:
    """Return the filesystem backing ``path``, or raise OSError if unreachable."""
    usage = shutil.disk_usage(str(path))
    return FilesystemReading(
        path=str(path),
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
    )


def directory_size(path: str | Path) -> int:
    """Return the total size in bytes of every regular file under ``path``.

    Used to price a stage's disk cost. Missing entries are skipped rather than
    raised: a stage log can vanish mid-measurement without invalidating the
    rest of the reading.
    """
    root = Path(path)
    if not root.is_dir():
        return 0
    total = 0
    for entry in root.rglob("*"):
        try:
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def parse_nvidia_driver_version(text: str) -> str:
    """Pull the driver version out of ``nvidia-smi`` header output."""
    match = re.search(r"Driver Version:\s*(\S+)", text)
    return match.group(1) if match else "unknown"


def nvidia_driver_version() -> str:
    """Return the NVIDIA driver version string, or ``unknown`` if unavailable."""
    completed = subprocess.run(
        [NVIDIA_SMI], capture_output=True, text=True, timeout=COUNTER_QUERY_TIMEOUT_SECONDS
    )
    return parse_nvidia_driver_version(completed.stdout)