#!/usr/bin/env python3
"""The record one benchmarked stage leaves behind.

A measurement is only worth keeping if someone else can tell *what was run*,
*on what*, and *how long it took* without re-deriving it from a shell history.
So a :class:`StageMeasurement` carries the exact argv, the pinned interpreter
and tool versions in force, the peak resources, and the inputs/outputs that
bound it.

Serialisation is explicit rather than ``asdict``-by-default so the JSON is a
stable contract that ``resource_budget.py`` can consume years later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from resource_sampler import PeakUsage

#: Bumped when the record layout changes incompatibly.
MEASUREMENT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StageMeasurement:
    """One stage's cost, in time, memory, disk and output terms."""

    label: str
    command: list[str]
    interpreter: str
    exit_code: int
    elapsed_seconds: float
    peak: PeakUsage
    input_bytes: int
    output_bytes: int
    splat_count: int | None
    tool_versions: dict[str, str]
    settings: dict[str, str] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)
    log_path: str = ""

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON contract for this measurement."""
        return {
            "schema_version": MEASUREMENT_SCHEMA_VERSION,
            "label": self.label,
            "command": list(self.command),
            "interpreter": self.interpreter,
            "exit_code": self.exit_code,
            "succeeded": self.succeeded,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
            "splat_count": self.splat_count,
            "tool_versions": dict(self.tool_versions),
            "settings": dict(self.settings),
            "extras": dict(self.extras),
            "log_path": self.log_path,
            "peak": {
                "peak_vram_used_bytes": self.peak.peak_vram_used_bytes,
                "stage_vram_bytes": self.peak.stage_vram_bytes,
                "peak_gpu_utilization_percent": self.peak.peak_gpu_utilization_percent,
                "peak_ram_used_bytes": self.peak.peak_ram_used_bytes,
                "stage_ram_bytes": self.peak.stage_ram_bytes,
                "baseline_vram_used_bytes": self.peak.baseline_vram_used_bytes,
                "baseline_ram_used_bytes": self.peak.baseline_ram_used_bytes,
                "samples_taken": self.peak.samples_taken,
                "missed_samples": self.peak.missed_samples,
                "duration_seconds": round(self.peak.duration_seconds, 3),
            },
        }


def peak_from_dict(data: dict[str, Any]) -> PeakUsage:
    """Rebuild a :class:`PeakUsage` from :meth:`StageMeasurement.to_dict` output."""
    return PeakUsage(
        peak_vram_used_bytes=int(data["peak_vram_used_bytes"]),
        peak_gpu_utilization_percent=int(data["peak_gpu_utilization_percent"]),
        peak_ram_used_bytes=int(data["peak_ram_used_bytes"]),
        baseline_vram_used_bytes=int(data["baseline_vram_used_bytes"]),
        baseline_ram_used_bytes=int(data["baseline_ram_used_bytes"]),
        samples_taken=int(data["samples_taken"]),
        missed_samples=int(data["missed_samples"]),
        duration_seconds=float(data["duration_seconds"]),
    )


def measurement_from_dict(data: dict[str, Any]) -> StageMeasurement:
    """Rebuild a :class:`StageMeasurement` from its JSON form."""
    return StageMeasurement(
        label=data["label"],
        command=list(data["command"]),
        interpreter=data["interpreter"],
        exit_code=int(data["exit_code"]),
        elapsed_seconds=float(data["elapsed_seconds"]),
        peak=peak_from_dict(data["peak"]),
        input_bytes=int(data["input_bytes"]),
        output_bytes=int(data["output_bytes"]),
        splat_count=data.get("splat_count"),
        tool_versions=dict(data.get("tool_versions", {})),
        settings=dict(data.get("settings", {})),
        extras=dict(data.get("extras", {})),
        log_path=data.get("log_path", ""),
    )


def write_measurements(path: str | Path, measurements: list[StageMeasurement]) -> Path:
    """Write a measurement set as JSON, creating parent directories."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": MEASUREMENT_SCHEMA_VERSION,
        "stages": [measurement.to_dict() for measurement in measurements],
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return destination


def read_measurements(path: str | Path) -> list[StageMeasurement]:
    """Read a measurement set written by :func:`write_measurements`."""
    payload = json.loads(Path(path).read_text())
    return [measurement_from_dict(stage) for stage in payload["stages"]]