#!/usr/bin/env python3
"""Run the pinned PlayCanvas ``splat-transform`` CLI and record what it did.

Two facts about this tool drove the design, and both were established by running
it on this host rather than by reading its documentation:

* **The collision features are GPU-only.**  ``.voxel.json`` output,
  ``--collision-mesh``, ``--filter-cluster`` and ``--filter-floaters`` all go
  through WebGPU, and ``-g cpu`` is refused for them.  So "collision generation
  is unavailable here" is a question about adapters, and the only honest probe is
  the tool's own ``--list-gpus``.  That probe *passes* on this host even though
  the Python ``wgpu`` module used for the #89 preflight could not find an
  adapter: the tool enumerates Vulkan through Node's own bindings and reports
  ``[0] NVIDIA GeForce RTX 4070 Ti``.  :func:`probe_adapters` records that
  distinction instead of collapsing both probes into one "GPU: yes/no".

* **The output frame is not the input frame.**  See
  :mod:`collision_params`; the tool writes its voxel grid and collision mesh in
  the PlayCanvas engine frame, a 180-degree rotation about z of the source PLY.

Every stage is parsed out of the tool's own progress output and returned as a
:class:`ToolRun`, so the recorded benchmark carries the tool's numbers rather
than a re-derivation of them.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from collision_params import CollisionSettings

#: The pinned release.  Collision support has changed shape across releases, so
#: an unpinned tool would make every recorded number unreproducible.
PINNED_PACKAGE = "@playcanvas/splat-transform"
PINNED_VERSION = "3.9.0"

#: Command that installs the pinned release next to the pipeline scripts.
INSTALL_COMMAND = "npm install %s@%s" % (PINNED_PACKAGE, PINNED_VERSION)

#: Environment variable pointing at a directory containing ``node_modules``.
NODE_MODULES_ENV = "SPLAT_TRANSFORM_NODE_MODULES"

#: Seconds before a stage is treated as hung rather than slow.  The measured
#: whole-pipeline run takes 3.5 s; an hour is not a slow run, it is a failure
#: that has not reported itself.
STAGE_TIMEOUT_S = 3600

_PATTERNS = {
    "version": re.compile(r"^splat-transform v([0-9][^\s(]*)"),
    "peak": re.compile(r"\[peak cpu=([\d.]+)([MG])B gpu=([\d.]+)([MG])B"),
    "gaussians": re.compile(r"^\s*·\s*([\d.]+[KM]?)\s+gaussians"),
    "removed": re.compile(r"removed\s+([\d.]+[KM]?)\s+gaussians"),
    "cluster": re.compile(r"cluster is\s+([\d,]+)\s+of\s+([\d,]+)\s+blocks"),
    # The tool prints counts as '20.1K'/'5.34K'; the suffix and the decimal point
    # both have to be consumed or '20.1K' parses as 20. 'pre-merged' and 'merged'
    # are anchored apart because one line contains the other's text.
    "pre_triangles": re.compile(r"pre-merged triangles:\s*([\d.]+[KM]?)"),
    "pre_vertices": re.compile(r"pre-merged vertices:\s*([\d.]+[KM]?)"),
    "triangles": re.compile(r"(?:^|·\s)merged triangles:\s*([\d.]+[KM]?)"),
    "vertices": re.compile(r"(?:^|·\s)merged vertices:\s*([\d.]+[KM]?)"),
    "octree_depth": re.compile(r"octree depth:\s*(\d+)"),
    "mixed_leaves": re.compile(r"mixed leaves:\s*([\d,]+)"),
    "seed_warning": re.compile(r"seed \(([^)]*)\) unoccupied"),
    "exterior_skipped": re.compile(r"skipping exterior fill"),
    "carve_skipped": re.compile(r"skipping carve|no navigable cells"),
    "error": re.compile(r"^\s*(?:✗|!)?\s*(?:✗\s*)?Error:\s*(.+)$"),
    "warning": re.compile(r"^\s*!\s*(.+)$"),
}


class SplatTransformUnavailable(RuntimeError):
    """Raised when the pinned tool cannot be located or has no usable GPU."""


class CollisionStageFailed(RuntimeError):
    """Raised when the tool ran but refused or failed a stage."""


@dataclass(frozen=True)
class ToolRun:
    """Everything one invocation of the pinned tool reported."""

    argv: tuple[str, ...]
    version: str
    elapsed_s: float
    peak_cpu_bytes: int
    peak_gpu_bytes: int
    gaussians_in: int
    gaussians_out: int
    gaussians_removed: int
    cluster_blocks_kept: int
    cluster_blocks_total: int
    pre_merge_triangles: int
    pre_merge_vertices: int
    triangles: int
    vertices: int
    octree_depth: int
    mixed_leaves: int
    seed_was_unoccupied: bool
    exterior_fill_skipped: bool
    carve_skipped: bool
    warnings: tuple[str, ...]
    files: dict[str, int]

    def to_json(self) -> dict:
        """Return a JSON-serialisable record, omitting metrics a run did not reach."""
        record = {
            "argv": list(self.argv),
            "version": self.version,
            "elapsed_s": round(self.elapsed_s, 3),
            "peak_cpu_bytes": self.peak_cpu_bytes,
            "peak_gpu_bytes": self.peak_gpu_bytes,
            "gaussians_in": self.gaussians_in,
            "gaussians_out": self.gaussians_out,
            "gaussians_removed": self.gaussians_removed,
            "cluster_blocks": [self.cluster_blocks_kept, self.cluster_blocks_total],
            "collision_mesh": {
                "pre_merge_triangles": self.pre_merge_triangles,
                "pre_merge_vertices": self.pre_merge_vertices,
                "triangles": self.triangles,
                "vertices": self.vertices,
            },
            "octree_depth": self.octree_depth,
            "mixed_leaves": self.mixed_leaves,
            "seed_was_unoccupied": self.seed_was_unoccupied,
            "exterior_fill_skipped": self.exterior_fill_skipped,
            "carve_skipped": self.carve_skipped,
            "warnings": list(self.warnings),
            "files": dict(self.files),
        }
        return {key: value for key, value in record.items() if value not in (None, {}, [])}


@dataclass
class ParsedOutput:
    """Structured view of the tool's stdout, accumulated across its progress lines."""

    version: str = ""
    peak_cpu_bytes: int = 0
    peak_gpu_bytes: int = 0
    gaussians: list[int] = field(default_factory=list)
    gaussians_removed: int = 0
    gaussians_out: int = 0
    cluster: tuple[int, int] | None = None
    pre_merge_triangles: int = 0
    pre_merge_vertices: int = 0
    triangles: int = 0
    vertices: int = 0
    octree_depth: int = 0
    mixed_leaves: int = 0
    seed_was_unoccupied: bool = False
    exterior_fill_skipped: bool = False
    carve_skipped: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    files: dict[str, int] = field(default_factory=dict)


def resolve_cli(node_modules: str | Path | None = None) -> Path:
    """Locate the pinned CLI entry point, with an actionable error when absent.

    Resolution order is the explicit ``node_modules`` argument, then
    :data:`NODE_MODULES_ENV`, then a ``node_modules`` beside the pipeline scripts.
    A global npm install is deliberately *not* searched: a globally resolved copy
    is whatever version someone last installed, which is exactly the drift the
    pin exists to prevent.
    """
    candidates = []
    if node_modules:
        candidates.append(Path(node_modules))
    if os.environ.get(NODE_MODULES_ENV):
        candidates.append(Path(os.environ[NODE_MODULES_ENV]))
    candidates.append(Path(__file__).resolve().parent / "node_modules")
    relative = Path(PINNED_PACKAGE.split("/", 1)[0]) / PINNED_PACKAGE.split("/", 1)[1] / "bin" / "cli.mjs"
    for root in candidates:
        entry = root / relative
        if entry.exists():
            return entry
    raise SplatTransformUnavailable(
        "the pinned %s@%s CLI is not installed.\n"
        "Install it and re-run:\n  cd %s && %s\n"
        "or point %s at a node_modules directory that already contains it."
        % (PINNED_PACKAGE, PINNED_VERSION, Path(__file__).resolve().parent, INSTALL_COMMAND, NODE_MODULES_ENV)
    )


def installed_version(cli: str | Path) -> str:
    """Return the version string the installed CLI reports for itself."""
    result = subprocess.run(
        [shutil.which("node") or "node", str(cli), "--version"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    match = _PATTERNS["version"].search(result.stdout + result.stderr)
    if match is None:
        raise SplatTransformUnavailable(
            "%s did not report a version (exit %d): %s"
            % (cli, result.returncode, (result.stdout + result.stderr).strip()[:400])
        )
    return match.group(1)


def probe_adapters(cli: str | Path) -> list[str]:
    """Return the GPU adapters the tool can see, or raise with the reason why not.

    This is the probe that decides whether collision generation is possible at
    all.  It reports failure as an exception rather than an empty list because
    "no adapters" and "one adapter" mean opposite things for this pipeline, and a
    caller that treats them the same will claim a bounded fallback that does not
    exist.
    """
    result = subprocess.run(
        [shutil.which("node") or "node", str(cli), "--list-gpus"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    combined = result.stdout + result.stderr
    adapters = [
        line.strip()[3:].strip()
        for line in combined.splitlines()
        if re.match(r"^\[\d+\]", line.strip())
    ]
    if not adapters:
        raise SplatTransformUnavailable(
            "%s listed no GPU adapters, so the GPU-only collision features "
            "(--filter-cluster, .voxel.json, --collision-mesh) cannot run. "
            "splat-transform reaches the GPU through WebGPU-over-Vulkan; on Linux "
            "that needs an NVIDIA driver exposing a Vulkan ICD (the GRID driver on "
            "cloud instances, not the compute-only Tesla driver).\nTool said:\n%s"
            % (cli, combined.strip()[:800])
        )
    return adapters


def build_argv(
    cli: str | Path,
    input_ply: str | Path,
    output_stem: str | Path,
    settings: CollisionSettings,
    metres_per_unit: float,
) -> tuple[str, ...]:
    """Return the exact argument vector for one collision run.

    The input splat is scaled by ``metres_per_unit`` in place so every downstream
    option is in calibrated metres.  Without it the tool's own defaults -- a 5 cm
    voxel, a 1.6 m capsule, a 1 m cluster grid -- would silently be 5.128x too
    small, which produces a mesh that looks plausible and blocks a player three
    metres wide.
    """
    seed = ",".join("%.4g" % value for value in settings.seed_engine_frame_m)
    return (
        shutil.which("node") or "node",
        str(cli),
        "--memory",
        "-w",
        str(input_ply),
        "-s",
        "%.17g" % metres_per_unit,
        "--filter-cluster",
        "%.6g,%.6g,%.6g" % (settings.cluster_resolution_m, settings.cluster_opacity, settings.cluster_min_contribution),
        "--seed-pos",
        seed,
        "%s.voxel.json" % output_stem,
        "--voxel-size",
        "%.6g" % settings.voxel_size_m,
        "--voxel-opacity",
        "%.6g" % settings.voxel_opacity,
        "--voxel-external-fill",
        "%.6g" % settings.exterior_fill_radius_m,
        "--voxel-carve",
        "%.6g,%.6g" % (settings.capsule_height_m, settings.capsule_radius_m),
        "--collision-mesh",
        settings.mesh_shape,
    )


def run_collision(
    cli: str | Path,
    input_ply: str | Path,
    output_stem: str | Path,
    settings: CollisionSettings,
    metres_per_unit: float,
    timeout_s: int = STAGE_TIMEOUT_S,
) -> ToolRun:
    """Run the full collision pipeline once and return what the tool reported.

    Raises :class:`CollisionStageFailed` with the tool's own message when it
    refuses, so the recorded verdict names the real cause -- an unsealed shell, a
    mutable grid over the 32-bit limit, an absent adapter -- instead of a
    generic failure a reader has to guess at.
    """
    argv = build_argv(cli, input_ply, output_stem, settings, metres_per_unit)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired as error:
        raise CollisionStageFailed(
            "splat-transform did not finish within %d s; its last output was:\n%s"
            % (timeout_s, (error.stdout or "")[-800:])
        ) from error
    elapsed = time.monotonic() - started
    combined = completed.stdout + completed.stderr
    parsed = parse_output(combined)
    _raise_for_failure(completed.returncode, parsed, combined)
    stem = Path(output_stem)
    files = {
        path.name: path.stat().st_size
        for path in (Path(str(stem) + ".voxel.json"), Path(str(stem) + ".voxel.bin"), Path(str(stem) + ".collision.glb"))
        if path.exists()
    }
    return ToolRun(
        argv=tuple(argv),
        version=parsed.version,
        elapsed_s=elapsed,
        peak_cpu_bytes=parsed.peak_cpu_bytes,
        peak_gpu_bytes=parsed.peak_gpu_bytes,
        gaussians_in=parsed.gaussians_out + parsed.gaussians_removed,
        gaussians_out=parsed.gaussians_out,
        gaussians_removed=parsed.gaussians_removed,
        cluster_blocks_kept=parsed.cluster[0] if parsed.cluster else 0,
        cluster_blocks_total=parsed.cluster[1] if parsed.cluster else 0,
        pre_merge_triangles=parsed.pre_merge_triangles,
        pre_merge_vertices=parsed.pre_merge_vertices,
        triangles=parsed.triangles or parsed.pre_merge_triangles,
        vertices=parsed.vertices or parsed.pre_merge_vertices,
        octree_depth=parsed.octree_depth,
        mixed_leaves=parsed.mixed_leaves,
        seed_was_unoccupied=parsed.seed_was_unoccupied,
        exterior_fill_skipped=parsed.exterior_fill_skipped,
        carve_skipped=parsed.carve_skipped,
        warnings=tuple(parsed.warnings),
        files=files,
    )


def parse_output(text: str) -> ParsedOutput:
    """Turn the tool's progress output into a :class:`ParsedOutput`."""
    parsed = ParsedOutput()
    for line in text.splitlines():
        _match_line(parsed, line)
    return parsed


def _match_line(parsed: ParsedOutput, line: str) -> None:
    """Fold one output line into ``parsed``, first match wins per category."""
    for name, pattern in _PATTERNS.items():
        match = pattern.search(line)
        if match is None:
            continue
        _apply_match(parsed, name, match)


def _apply_match(parsed: ParsedOutput, name: str, match: re.Match) -> None:
    """Record one regex match against the right field."""
    if name == "version":
        parsed.version = parsed.version or match.group(1)
    elif name == "peak":
        parsed.peak_cpu_bytes = max(parsed.peak_cpu_bytes, _megabytes(match.group(1), match.group(2)))
        parsed.peak_gpu_bytes = max(parsed.peak_gpu_bytes, _megabytes(match.group(3), match.group(4)))
    elif name == "gaussians":
        parsed.gaussians.append(_count(match.group(1)))
        parsed.gaussians_out = parsed.gaussians[-1]
    elif name == "removed":
        parsed.gaussians_removed = _count(match.group(1))
    elif name == "cluster":
        parsed.cluster = (_count(match.group(1)), _count(match.group(2)))
    elif name == "pre_triangles":
        parsed.pre_merge_triangles = _count(match.group(1))
    elif name == "triangles":
        parsed.triangles = _count(match.group(1))
    elif name == "pre_vertices":
        parsed.pre_merge_vertices = _count(match.group(1))
    elif name == "vertices":
        parsed.vertices = _count(match.group(1))
    elif name == "octree_depth":
        parsed.octree_depth = int(match.group(1))
    elif name == "mixed_leaves":
        parsed.mixed_leaves = _count(match.group(1))
    elif name == "seed_warning":
        parsed.seed_was_unoccupied = True
    elif name == "exterior_skipped":
        parsed.exterior_fill_skipped = True
    elif name == "carve_skipped":
        parsed.carve_skipped = True
    elif name == "error":
        parsed.errors.append(match.group(1).strip())
    elif name == "warning":
        parsed.warnings.append(match.group(1).strip())


def _raise_for_failure(returncode: int, parsed: ParsedOutput, combined: str) -> None:
    """Turn a non-zero exit or a reported error into an actionable exception."""
    if parsed.errors:
        raise CollisionStageFailed(
            "splat-transform refused the run: %s\nLast output:\n%s"
            % ("; ".join(parsed.errors), _tail(combined))
        )
    if returncode != 0:
        raise CollisionStageFailed(
            "splat-transform exited %d without a message.\nOutput:\n%s" % (returncode, _tail(combined))
        )


def _megabytes(value: str, unit: str) -> int:
    """Convert a reported ``123.4M``-style memory figure to bytes."""
    scale = 1024 ** 2 if unit == "M" else 1024 ** 3
    return int(float(value) * scale)


def _count(value: str) -> int:
    """Convert a reported ``183K``-style count to an integer."""
    text = value.replace(",", "")
    if text.endswith("K"):
        return int(float(text[:-1]) * 1000)
    if text.endswith("M"):
        return int(float(text[:-1]) * 1_000_000)
    return int(float(text))


def _tail(text: str, limit: int = 2000) -> str:
    """Return the last ``limit`` characters of captured tool output."""
    return text[-limit:]