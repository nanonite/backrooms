#!/usr/bin/env python3
"""Price the runtime render stage: GPU cost, wall time and frame rate.

A frame rate is only a claim when the resolution it was measured at travels with
it, so the resolution, frame count and warmup are recorded alongside the number.

The probe orbits the viewpoint rather than holding one camera fixed. Every real
walkthrough changes what the splat is asked to draw; measuring a single static
camera measures a single lucky culling result, which is how a renderer with no
headroom looks perfect.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from hardware_report import detect_tool_versions, resolve_binary
from ply_vertex_count import PlyHeaderError, vertex_count
from resource_probe import directory_size
from resource_sampler import ResourceSampler
from stage_benchmark import append_to_report, print_measurement
from stage_measurement import StageMeasurement

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_MISSING_TOOL = 2
EXIT_STAGE_FAILED = 3

#: A frame rate is only meaningful with the resolution it was measured at, so the
#: render stage records it alongside the frame count and warmup that produced it.
RENDER_DEFAULTS = {
    "resolution": "1280x720",
    "frames": "300",
    "warmup": "60",
    "orbit-radius": "1.0",
}

FPS_JSON_PREFIX = "FPS_JSON "


def build_render_command(
    godot_binary: str,
    project_dir: Path,
    scene: str,
    resolution: str,
    frames: str,
    warmup: str,
    orbit_radius: str,
) -> list[str]:
    """Return the argv for a Godot render probe of ``scene`` at ``resolution``."""
    return [
        godot_binary,
        "--path",
        str(project_dir),
        "--resolution",
        resolution,
        "--script",
        "res://scripts/measure_fps.gd",
        "--",
        f"--scene={scene}",
        f"--frames={frames}",
        f"--warmup={warmup}",
        f"--orbit-radius={orbit_radius}",
    ]


def parse_fps_json(text: str) -> dict[str, float]:
    """Return the probe's JSON payload, or an empty dict when it never printed one."""
    for line in text.splitlines():
        if line.startswith(FPS_JSON_PREFIX):
            return json.loads(line.removeprefix(FPS_JSON_PREFIX))
    return {}


def splat_count(splat_path: str) -> int | None:
    """Return the Gaussian count of a PLY, or None when it cannot be read."""
    if not splat_path or not Path(splat_path).is_file():
        return None
    try:
        return vertex_count(splat_path)
    except (PlyHeaderError, ValueError):
        return None


def run_render(args) -> int:
    """Price the runtime render stage: GPU, wall time, and the frame rate reached."""
    godot_binary = resolve_binary(args.godot, (args.godot,))
    if not Path(godot_binary).exists():
        print(f"ERROR: godot binary not found: {args.godot}", file=sys.stderr)
        return EXIT_MISSING_TOOL
    project_dir = Path(args.project)
    if not (project_dir / "project.godot").is_file():
        print(f"ERROR: no project.godot in {project_dir}", file=sys.stderr)
        return EXIT_USAGE
    command = build_render_command(
        godot_binary,
        project_dir,
        args.scene,
        args.resolution,
        args.frames,
        args.warmup,
        args.orbit_radius,
    )
    with ResourceSampler() as sampler:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    peak = sampler.stop()
    output = (completed.stdout or "") + (completed.stderr or "")
    Path(args.log).parent.mkdir(parents=True, exist_ok=True)
    Path(args.log).write_text(output)
    payload = parse_fps_json(output)
    measurement = _measurement(args, godot_binary, command, completed.returncode, peak, payload)
    print_measurement(measurement)
    if not payload:
        print(f"ERROR: render probe printed no FPS_JSON; see {args.log}", file=sys.stderr)
        return EXIT_STAGE_FAILED
    print(f"  fps                {payload['fps']:.2f} at {args.resolution}")
    append_to_report(args.report, measurement)
    return EXIT_OK


def _measurement(args, godot_binary, command, exit_code, peak, payload) -> StageMeasurement:
    """Assemble the render record, including the asset's Gaussian count."""
    splat = args.splat if args.splat and Path(args.splat).exists() else ""
    return StageMeasurement(
        label=args.label,
        command=command,
        interpreter=godot_binary,
        exit_code=exit_code,
        elapsed_seconds=peak.duration_seconds,
        peak=peak,
        input_bytes=directory_size(splat) if splat else 0,
        output_bytes=0,
        splat_count=splat_count(args.splat),
        tool_versions=detect_tool_versions(),
        settings={
            "resolution": args.resolution,
            "frames": args.frames,
            "warmup": args.warmup,
            "orbit-radius": args.orbit_radius,
            "scene": args.scene,
        },
        extras={"fps": float(payload["fps"])} if payload else {},
        log_path=str(args.log),
    )