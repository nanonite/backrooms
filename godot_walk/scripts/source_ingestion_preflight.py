"""Hunyuan preflight with graphics-only GPU rows filtered out.

The PSX design-round preflight in ``psx_design_round_resources`` is pinned by
accepted adaptation evidence, so the ingestion path keeps those thresholds in
one source-ingestion-specific module instead of rewriting recorded hashes.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

from psx_design_round_resources import (
    MIN_RENDER_RAM_BYTES,
    MIN_RENDER_VRAM_BYTES,
    RAM_HEADROOM_FRACTION,
    VRAM_HEADROOM_FRACTION,
    _active_named_jobs,
    _available_ram_bytes,
    _compute_apps,
    _gpu_process_name,
    _gpu_snapshot,
)

INGESTION_GUARD_POLICY_VERSION = "2.2.0"
GRAPHICS_ONLY_PROCESS_TYPE = "G"
GPU_PROCESS_POLICY = (
    "block compute contexts (type C or C+G); ignore graphics-only contexts"
)


class GpuProcessBlockedError(RuntimeError):
    """A compute context blocked the step; records the graphics rows it ignored."""

    def __init__(
        self, reason: str, ignored_graphics: list[dict[str, str]]
    ) -> None:
        super().__init__(reason)
        self.ignored_graphics_processes = ignored_graphics


def check_ingestion_headroom() -> dict[str, Any]:
    """Refuse a GPU step when a compute process or tight memory competes."""
    _require_no_named_jobs()
    gpu_processes = _gpu_process_scan()
    _require_no_compute_processes(gpu_processes)
    gpu = _gpu_snapshot()
    compute_apps = _require_no_compute_apps()
    ram_available = _available_ram_bytes()
    vram_after_headroom, ram_after_headroom = _headroom_budgets(
        gpu, ram_available
    )
    return {
        "guard_policy_version": INGESTION_GUARD_POLICY_VERSION,
        "gpu_process_policy": GPU_PROCESS_POLICY,
        **gpu,
        "compute_apps": compute_apps,
        "ignored_graphics_processes": gpu_processes["ignored_graphics"],
        "ram_available_bytes": ram_available,
        "vram_after_headroom_bytes": vram_after_headroom,
        "ram_after_headroom_bytes": ram_after_headroom,
        "vram_headroom_fraction": VRAM_HEADROOM_FRACTION,
        "ram_headroom_fraction": RAM_HEADROOM_FRACTION,
    }


def _require_no_named_jobs() -> None:
    active_jobs = _active_named_jobs()
    if active_jobs:
        raise RuntimeError(
            "GPU preflight blocked by active job(s): " + ", ".join(active_jobs)
        )


def _require_no_compute_processes(
    gpu_processes: dict[str, list[dict[str, str]]],
) -> None:
    blocked = gpu_processes["blocked"]
    if blocked:
        raise GpuProcessBlockedError(
            "GPU preflight blocked by active GPU process(es): "
            + ", ".join(_describe_gpu_process(row) for row in blocked),
            gpu_processes["ignored_graphics"],
        )


def _require_no_compute_apps() -> list[dict[str, str]]:
    compute_apps = _compute_apps()
    if compute_apps:
        names = ", ".join(app["process"] for app in compute_apps)
        raise RuntimeError(
            f"GPU preflight blocked by active compute process(es): {names}"
        )
    return compute_apps


def _headroom_budgets(
    gpu: dict[str, int], ram_available: int
) -> tuple[int, int]:
    vram_after_headroom = int(gpu["free_vram_bytes"] * (1 - VRAM_HEADROOM_FRACTION))
    ram_after_headroom = int(ram_available * (1 - RAM_HEADROOM_FRACTION))
    if vram_after_headroom < MIN_RENDER_VRAM_BYTES:
        raise RuntimeError(
            "GPU preflight blocked: free VRAM is below the render budget after headroom"
        )
    if ram_after_headroom < MIN_RENDER_RAM_BYTES:
        raise RuntimeError(
            "GPU preflight blocked: available RAM is below the render budget "
            "after headroom"
        )
    return vram_after_headroom, ram_after_headroom


def _gpu_process_scan() -> dict[str, list[dict[str, str]]]:
    """Classify pmon rows by context type and owning process group.

    A graphics-only row (type G) is a desktop compositor or application with
    no compute context: it does not compete for inference VRAM, so it is
    recorded for the guard receipt and ignored. Compute rows (type C or C+G)
    still block unless they belong to the running process group.
    """
    result = subprocess.run(
        ["nvidia-smi", "pmon", "-c", "1"], capture_output=True, text=True, check=True
    )
    blocked = []
    ignored_graphics = []
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) < 10 or columns[0].startswith("#"):
            continue
        process_type = columns[2]
        pid = columns[1]
        command = _gpu_process_name(pid, columns[9])
        row = {"pid": pid, "type": process_type, "command": command}
        if process_type == GRAPHICS_ONLY_PROCESS_TYPE:
            ignored_graphics.append(row)
        elif not _same_process_group(pid):
            blocked.append(row)
    return {"blocked": blocked, "ignored_graphics": ignored_graphics}


def _describe_gpu_process(row: dict[str, str]) -> str:
    return f"pid={row['pid']} type={row['type']} command={row['command']}"


def _same_process_group(pid: str) -> bool:
    try:
        return os.getpgid(int(pid)) == os.getpgrp()
    except (OSError, ValueError):
        return False
