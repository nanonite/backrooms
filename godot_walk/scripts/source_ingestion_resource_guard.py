"""Strict host, swap, and VRAM policy for memory-offloaded source inference."""

from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GIB = 1024**3


@dataclass(frozen=True)
class ResourceLimits:
    policy_version: str = "hunyuan-sequential-offload-2"
    min_start_ram_bytes: int = 32 * GIB
    min_start_swap_free_bytes: int = 16 * GIB
    min_start_vram_bytes: int = 8 * GIB
    min_runtime_ram_bytes: int = 8 * GIB
    min_runtime_swap_free_bytes: int = 16 * GIB
    min_runtime_vram_bytes: int = 2 * GIB
    max_swap_growth_bytes: int = 64 * GIB
    max_execution_seconds: int = 2700
    sample_period_seconds: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_LIMITS = ResourceLimits()


class ResourceGuardError(RuntimeError):
    """A run was refused or stopped by the explicit resource policy."""

    def __init__(
        self,
        reason: str,
        *,
        snapshot: dict[str, Any] | None = None,
        limits: ResourceLimits | None = None,
    ) -> None:
        super().__init__(reason)
        self.snapshot = snapshot
        self.limits = limits


def capture_resources(process_group_id: int | None = None) -> dict[str, Any]:
    memory = _memory_values()
    gpu = _gpu_values()
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **memory,
        **gpu,
        "process_group_rss_bytes": _process_group_rss(process_group_id),
    }


def check_start_limits(
    sample: dict[str, Any], limits: ResourceLimits = DEFAULT_LIMITS
) -> None:
    requirements = (
        ("ram_available_bytes", limits.min_start_ram_bytes, "available host RAM"),
        ("swap_free_bytes", limits.min_start_swap_free_bytes, "free swap"),
        ("gpu_free_bytes", limits.min_start_vram_bytes, "free VRAM"),
    )
    for key, minimum, label in requirements:
        if sample[key] < minimum:
            raise ResourceGuardError(
                f"Inference preflight blocked: {label} is {sample[key]} bytes; needs {minimum} bytes",
                snapshot=sample,
                limits=limits,
            )


def runtime_stop_reason(
    sample: dict[str, Any],
    initial: dict[str, Any],
    limits: ResourceLimits = DEFAULT_LIMITS,
    external_gpu_pids: list[str] | None = None,
) -> str | None:
    checks = (
        ("ram_available_bytes", limits.min_runtime_ram_bytes, "host RAM"),
        ("swap_free_bytes", limits.min_runtime_swap_free_bytes, "free swap"),
        ("gpu_free_bytes", limits.min_runtime_vram_bytes, "free VRAM"),
    )
    for key, minimum, label in checks:
        if sample[key] < minimum:
            return f"{label} fell below {minimum} bytes"
    swap_growth = initial["swap_free_bytes"] - sample["swap_free_bytes"]
    if swap_growth > limits.max_swap_growth_bytes:
        return f"swap use grew beyond {limits.max_swap_growth_bytes} bytes"
    if external_gpu_pids:
        return "external GPU compute process appeared: " + ",".join(external_gpu_pids)
    return None


def external_compute_pids(process_group_id: int) -> list[str]:
    result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    )
    external = []
    for value in result.stdout.splitlines():
        pid_text = value.strip()
        if not pid_text:
            continue
        try:
            same_group = os.getpgid(int(pid_text)) == process_group_id
        except (ProcessLookupError, ValueError):
            same_group = False
        if not same_group:
            external.append(pid_text)
    return external


def _memory_values() -> dict[str, int]:
    values = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"MemAvailable", "SwapFree", "SwapTotal"}:
            values[key] = int(value.split()[0]) * 1024
    if set(values) != {"MemAvailable", "SwapFree", "SwapTotal"}:
        raise RuntimeError("Could not read host RAM and swap from /proc/meminfo")
    return {
        "ram_available_bytes": values["MemAvailable"],
        "swap_free_bytes": values["SwapFree"],
        "swap_total_bytes": values["SwapTotal"],
    }


def _gpu_values() -> dict[str, int]:
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=memory.free,memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    values = [int(item.strip()) for item in result.stdout.split(",")]
    if len(values) != 4:
        raise RuntimeError("Could not parse nvidia-smi resource snapshot")
    free_mib, used_mib, total_mib, utilization = values
    return {
        "gpu_free_bytes": free_mib * 1024**2,
        "gpu_used_bytes": used_mib * 1024**2,
        "gpu_total_bytes": total_mib * 1024**2,
        "gpu_utilization_pct": utilization,
    }


def _process_group_rss(process_group_id: int | None) -> int:
    if process_group_id is None:
        return 0
    result = subprocess.run(
        ["ps", "-eo", "pgid=,rss="], capture_output=True, text=True, check=True
    )
    return sum(
        int(rss_kib) * 1024
        for row in result.stdout.splitlines()
        if len(fields := row.split()) == 2 and int(fields[0]) == process_group_id
        for rss_kib in (fields[1],)
    )
