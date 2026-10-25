"""Fail-closed GPU/RAM preflight and lightweight run resource sampling."""

from __future__ import annotations

import os
import re
import resource
import subprocess
import threading
from pathlib import Path
from typing import Any

GIB = 1024**3
VRAM_HEADROOM_FRACTION = 0.20
RAM_HEADROOM_FRACTION = 0.25
MIN_RENDER_VRAM_BYTES = 2 * GIB
MIN_RENDER_RAM_BYTES = GIB
GPU_SAMPLE_SECONDS = 0.5
GPU_GUARD_POLICY_VERSION = "2.1.0"
GPU_DESKTOP_PROCESS_ALLOWLIST = frozenset(
    {
        "code",
        "discord",
        "eeschema",
        "firefox",
        "firmware-update",
        "gnome-shell",
        "kicad",
        "kitty",
        "nautilus",
        "obsidian",
        "snapd-desktop-integration",
        "xorg",
        "xwayland",
    }
)


def check_capture_headroom() -> dict[str, Any]:
    """Refuse a GPU step when another job is active or memory is tight."""
    active_jobs = _active_named_jobs()
    if active_jobs:
        raise RuntimeError(
            "GPU preflight blocked by active job(s): " + ", ".join(active_jobs)
        )
    gpu_jobs = _active_gpu_jobs()
    if gpu_jobs:
        raise RuntimeError(
            "GPU preflight blocked by active GPU process(es): " + ", ".join(gpu_jobs)
        )
    gpu = _gpu_snapshot()
    compute_apps = _compute_apps()
    if compute_apps:
        names = ", ".join(app["process"] for app in compute_apps)
        raise RuntimeError(
            f"GPU preflight blocked by active compute process(es): {names}"
        )
    ram_available = _available_ram_bytes()
    vram_after_headroom = int(gpu["free_vram_bytes"] * (1 - VRAM_HEADROOM_FRACTION))
    ram_after_headroom = int(ram_available * (1 - RAM_HEADROOM_FRACTION))
    if vram_after_headroom < MIN_RENDER_VRAM_BYTES:
        raise RuntimeError(
            "GPU preflight blocked: free VRAM is below the render budget after headroom"
        )
    if ram_after_headroom < MIN_RENDER_RAM_BYTES:
        raise RuntimeError(
            "GPU preflight blocked: available RAM is below the render budget after headroom"
        )
    return {
        "guard_policy_version": GPU_GUARD_POLICY_VERSION,
        **gpu,
        "compute_apps": compute_apps,
        "ram_available_bytes": ram_available,
        "vram_after_headroom_bytes": vram_after_headroom,
        "ram_after_headroom_bytes": ram_after_headroom,
        "vram_headroom_fraction": VRAM_HEADROOM_FRACTION,
        "ram_headroom_fraction": RAM_HEADROOM_FRACTION,
    }


def _active_named_jobs() -> list[str]:
    result = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,comm=,args="],
        capture_output=True,
        text=True,
        check=True,
    )
    rows = _process_rows(result.stdout)
    ancestors = _ancestor_pids(rows)
    matches = []
    for pid, row in rows.items():
        if pid in ancestors:
            continue
        lowered = " ".join((row["name"], row["args"]))
        if "hunyuan_review_server.py" in lowered:
            continue
        if re.search(r"hunyuan|hunyuanworld|qemu-system|(^|\s)qemu(\s|$)", lowered):
            matches.append(row["line"])
    return matches


def _process_rows(output: str) -> dict[int, dict[str, Any]]:
    rows = {}
    for line in output.splitlines():
        fields = line.strip().split(maxsplit=3)
        if len(fields) != 4:
            continue
        pid, parent, name, arguments = fields
        rows[int(pid)] = {
            "parent": int(parent),
            "name": name.lower(),
            "args": arguments.lower(),
            "line": line.strip(),
        }
    return rows


def _ancestor_pids(rows: dict[int, dict[str, Any]]) -> set[int]:
    ancestors = set()
    current = os.getpid()
    while current in rows and current not in ancestors:
        ancestors.add(current)
        current = rows[current]["parent"]
    return ancestors


def _gpu_snapshot() -> dict[str, int]:
    command = [
        "nvidia-smi",
        "--query-gpu=memory.free,memory.total,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    rows = [
        line.strip().split(",") for line in result.stdout.splitlines() if line.strip()
    ]
    if not rows or len(rows[0]) != 3:
        raise RuntimeError("GPU preflight could not parse nvidia-smi output")
    free_mib, total_mib, utilization = (int(value.strip()) for value in rows[0])
    return {
        "free_vram_bytes": free_mib * 1024**2,
        "total_vram_bytes": total_mib * 1024**2,
        "utilization_pct": utilization,
    }


def _active_gpu_jobs() -> list[str]:
    result = subprocess.run(
        ["nvidia-smi", "pmon", "-c", "1"], capture_output=True, text=True, check=True
    )
    jobs = []
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) < 10 or columns[0].startswith("#"):
            continue
        process_type = columns[2]
        pid = columns[1]
        command = columns[9]
        process_name = _gpu_process_name(pid, command)
        if process_type == "C" or process_name not in GPU_DESKTOP_PROCESS_ALLOWLIST:
            jobs.append(f"pid={pid} type={process_type} command={process_name}")
    return jobs


def _gpu_process_name(pid: str, fallback: str) -> str:
    try:
        executable = Path(f"/proc/{pid}/exe").resolve(strict=True).name
    except OSError:
        executable = fallback.split(maxsplit=1)[0].rsplit("/", maxsplit=1)[-1]
    return executable.lower()


def _compute_apps() -> list[dict[str, str]]:
    command = [
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    apps = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",", maxsplit=2)]
        if len(parts) != 3:
            raise RuntimeError("GPU preflight could not parse compute-process output")
        apps.append({"pid": parts[0], "process": parts[1], "used_memory_mib": parts[2]})
    return apps


def _available_ram_bytes() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("GPU preflight cannot read MemAvailable from /proc/meminfo")


class PeakResourceSampler:
    """Sample total NVIDIA memory and collect the runner's largest child RSS."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._baseline = _used_vram_bytes()
        self._peak = self._baseline
        self._sampling_error: str | None = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> dict[str, int]:
        self._stop.set()
        self._thread.join()
        if self._sampling_error:
            raise RuntimeError(f"GPU memory sampling failed: {self._sampling_error}")
        max_rss = int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024)
        return {
            "peak_child_rss_bytes": max_rss,
            "gpu_memory_start_bytes": self._baseline,
            "peak_gpu_memory_used_bytes": self._peak,
            "peak_gpu_memory_delta_bytes": max(0, self._peak - self._baseline),
            "gpu_sample_period_ms": int(GPU_SAMPLE_SECONDS * 1000),
        }

    def _sample(self) -> None:
        while not self._stop.is_set():
            try:
                self._peak = max(self._peak, _used_vram_bytes())
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                self._sampling_error = str(error)
                return
            self._stop.wait(GPU_SAMPLE_SECONDS)


def _used_vram_bytes() -> int:
    command = ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not values:
        raise RuntimeError("nvidia-smi returned no GPU memory readings")
    return int(values[0]) * 1024**2
