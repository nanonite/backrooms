#!/usr/bin/env python3
"""Answer one question before any GPU work starts: can this machine do it?

Run this first in a pipeline stage or on a new workstation. It measures the
machine instead of trusting the project's notes about it, probes each compute
API the pipeline needs *independently* (CUDA for training, Vulkan for rendering,
WebGPU for collision), and turns recorded stage measurements into a budget.

Usage:
    python3 preflight_hardware.py                       # human report
    python3 preflight_hardware.py --json report.json    # machine-readable too
    python3 preflight_hardware.py --measurements <file> # publish a budget

Exit codes, chosen so a pipeline script can branch without parsing prose:
    0  every required capability passed and the default budget fits
    1  usage error
    2  CUDA training unusable  -- reconstruction cannot run here at all
    3  Vulkan unusable         -- nothing can be rendered or walked
    4  WebGPU unavailable      -- reconstruction is fine, collision is not
    5  the measured default budget does not fit the headroom-adjusted VRAM
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import preflight_report
from cuda_capability import CudaCapability, probe_cuda
from hardware_report import HardwareSnapshot, capture_snapshot
from published_budget import publish_budget
from runtime_budget import publish_runtime_budget
from resource_budget import (
    VRAM_HEADROOM_FRACTION,
    BudgetVerdict,
    evaluate_stage,
    vram_available_bytes,
)
from stage_measurement import StageMeasurement, read_measurements
from vulkan_capability import VulkanCapability, probe_vulkan
from webgpu_capability import WebGpuCapability, probe_webgpu

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NO_CUDA = 2
EXIT_NO_VULKAN = 3
EXIT_NO_WEBGPU = 4
EXIT_OVER_BUDGET = 5

DEFAULT_MEASUREMENTS = "splat_logs/measurements.json"
DEFAULT_FILESYSTEMS = ("/mnt/sharedOs", "/home")


def capability_rows(
    cuda: CudaCapability, vulkan: VulkanCapability, webgpu: WebGpuCapability
) -> list[tuple[str, bool, str, str, str]]:
    """Reduce the three probes to renderable rows: name, ok, evidence, error, fix."""
    return [
        (
            "CUDA training",
            cuda.usable,
            f"{cuda.device_name} (cc {cuda.compute_capability}), torch {cuda.torch_version}, "
            f"one backward pass OK, {_gib(cuda.free_vram_bytes)} free",
            cuda.error,
            cuda.remediation(),
        ),
        (
            "Vulkan rendering",
            vulkan.available,
            f"{vulkan.device_name} via {vulkan.source} (api {vulkan.api_version}, {vulkan.rendering_method})",
            vulkan.error,
            vulkan.remediation(),
        ),
        (
            "WebGPU collision",
            webgpu.available,
            f"{webgpu.adapter_name} via {webgpu.host}" if webgpu.available else "no adapter",
            webgpu.error,
            webgpu.remediation(),
        ),
    ]


def _gib(value: int) -> str:
    return f"{value / 1024**3:.1f} GiB"


def capability_problems(cuda: CudaCapability, vulkan: VulkanCapability, webgpu: WebGpuCapability) -> list[str]:
    """State every unverified capability, for the budget's caveat list."""
    problems = []
    if not cuda.usable:
        problems.append(f"CUDA training unverified: {cuda.error}")
    if not vulkan.available:
        problems.append(f"Vulkan rendering unverified: {vulkan.error}")
    if not webgpu.available:
        problems.append(
            "WebGPU collision unverified: no adapter on this host, so collision generation "
            "has no measured local support."
        )
    return problems


def budget_fits(budget: object | None, usable_vram_bytes: int) -> bool:
    """Return whether the measured default run leaves the headroom intact."""
    if budget is None:
        return True
    ceiling = usable_vram_bytes * (1.0 - VRAM_HEADROOM_FRACTION)
    return budget.default_stage_vram_bytes <= ceiling


def decide_exit_code(
    cuda: CudaCapability,
    vulkan: VulkanCapability,
    webgpu: WebGpuCapability,
    fits: bool,
) -> int:
    """Map probe results onto one exit code, most blocking problem first."""
    if not cuda.usable:
        return EXIT_NO_CUDA
    if not vulkan.available:
        return EXIT_NO_VULKAN
    if not webgpu.available:
        return EXIT_NO_WEBGPU
    return EXIT_OK if fits else EXIT_OVER_BUDGET


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--measurements", default=DEFAULT_MEASUREMENTS, help="stage measurements")
    parser.add_argument("--scene", default="", help="scene name recorded with the budget")
    parser.add_argument("--json", dest="json_path", default="", help="also write JSON here")
    parser.add_argument(
        "--filesystem",
        action="append",
        default=[],
        metavar="PATH",
        help="filesystem to report disk space for (repeatable)",
    )
    return parser


def api_name(stage: str) -> str:
    """Return the compute API a stage depends on, as the status map keys it."""
    from resource_budget import STAGE_REQUIREMENTS

    requirement = STAGE_REQUIREMENTS.get(stage)
    return requirement.compute_api if requirement else "cuda"


def _load_measurements(path: str) -> list[StageMeasurement]:
    """Read a measurement file, returning none when it does not exist yet."""
    if not path or not Path(path).exists():
        return []
    try:
        return read_measurements(path)
    except (KeyError, ValueError, json.JSONDecodeError):
        return []


def recorded_failures(measurements: list[StageMeasurement]) -> dict[str, StageMeasurement]:
    """Return the most recent failed attempt per label.

    A stage that was tried here and could not run must not be reported as RUN
    just because the card has room for it -- the resource verdict answers "is
    there space", and only a measured attempt answers "does it work".
    """
    failures: dict[str, StageMeasurement] = {}
    for measurement in measurements:
        if not measurement.succeeded and measurement.extras.get("failure"):
            failures[measurement.label] = measurement
    return failures


def apply_recorded_failures(
    verdicts: list[Any], measurements: list[StageMeasurement]
) -> list[Any]:
    """Re-issue each stage verdict with any recorded failure folded into it."""
    failures = recorded_failures(measurements)
    revised: list[Any] = []
    for verdict in verdicts:
        failure = failures.get(verdict.stage)
        if failure is None:
            revised.append(verdict)
            continue
        detail = failure.extras.get("log_tail", "")[-400:]
        revised.append(
            BudgetVerdict(
                stage=verdict.stage,
                fits=False,
                compute_api=verdict.compute_api,
                usable_vram_bytes=verdict.usable_vram_bytes,
                required_vram_bytes=verdict.required_vram_bytes,
                blockers=(
                    *verdict.blockers,
                    f"{verdict.stage} was attempted here and failed: {failure.extras['failure']}",
                    detail,
                ),
                actions=(
                    *verdict.actions,
                    f"See {failure.log_path}. Fix that failure before scheduling {verdict.stage}.",
                ),
            )
        )
    return revised


def _api_status(cuda: CudaCapability, vulkan: VulkanCapability, webgpu: WebGpuCapability) -> dict[str, tuple[bool, str, str]]:
    """Map each compute API to (available, probe name, error) for the verdicts."""
    return {
        "cuda": (cuda.usable, "CUDA training", cuda.error),
        "vulkan": (vulkan.available, "Vulkan rendering", vulkan.error),
        "webgpu": (webgpu.available, "WebGPU collision", webgpu.error),
    }


def run(args: argparse.Namespace) -> int:
    """Probe everything, print the report, and return the exit code."""
    snapshot: HardwareSnapshot = capture_snapshot(
        tuple(args.filesystem) or DEFAULT_FILESYSTEMS
    )
    cuda = probe_cuda()
    vulkan = probe_vulkan()
    webgpu = probe_webgpu()
    usable_vram = vram_available_bytes(snapshot, cuda)
    measurements = _load_measurements(args.measurements)
    free_disk = max((fs.free_bytes for fs in snapshot.filesystems), default=0)
    verdicts = [
        evaluate_stage(
            stage,
            usable_vram,
            snapshot.memory.available_bytes,
            free_disk,
            *_api_status(cuda, vulkan, webgpu)[api_name(stage)],
        )
        for stage in ("splatfacto", "collision", "import", "render")
    ]
    verdicts = apply_recorded_failures(verdicts, measurements)
    budget = publish_budget(
        scene=args.scene or "unnamed scene",
        measurements=measurements,
        snapshot=snapshot,
        usable_vram_bytes=usable_vram,
        capability_problems=capability_problems(cuda, vulkan, webgpu),
    )
    gpu_name = snapshot.primary_gpu.name if snapshot.primary_gpu else "unknown"
    runtime = publish_runtime_budget(measurements, gpu_name)
    fits = budget_fits(budget, usable_vram)
    print(
        preflight_report.render_report(
            snapshot,
            usable_vram,
            capability_rows(cuda, vulkan, webgpu),
            verdicts,
            budget,
            runtime,
        )
    )
    if args.json_path:
        _write_json(args.json_path, snapshot, usable_vram, cuda, vulkan, webgpu, verdicts, budget, runtime)
        print(f"\nwrote {args.json_path}")
    return decide_exit_code(cuda, vulkan, webgpu, fits)


def _write_json(
    path: str,
    snapshot: HardwareSnapshot,
    usable_vram: int,
    cuda: CudaCapability,
    vulkan: VulkanCapability,
    webgpu: WebGpuCapability,
    verdicts: list[object],
    budget: object | None,
    runtime: object | None,
) -> None:
    """Write the machine-readable form of the same report."""
    payload = {
        "hardware": snapshot.to_dict(),
        "usable_vram_bytes": usable_vram,
        "capabilities": {
            "cuda": cuda.to_dict(),
            "vulkan": vulkan.to_dict(),
            "webgpu": webgpu.to_dict(),
        },
        "verdicts": [verdict.to_dict() for verdict in verdicts],
        "training_budget": budget.to_dict() if budget is not None else None,
        "runtime_budget": runtime.to_dict() if runtime is not None else None,
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the preflight."""
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())