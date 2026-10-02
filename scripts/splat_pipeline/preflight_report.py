#!/usr/bin/env python3
"""Render a preflight result as the text an operator reads at 2am.

Formatting only: it takes finished capability and budget objects and prints
them. Keeping it apart from the probing means the prose can be reviewed without
running anything, and the probes can be tested without asserting on English.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

GIBIBYTE = 1024**3
HOUR = 3600


def _gib(value: int | float) -> str:
    """Format bytes as GiB with one decimal."""
    return f"{value / GIBIBYTE:.1f} GiB"


def _duration(seconds: float) -> str:
    """Format seconds as minutes, which is the unit a stage's cost is judged in."""
    return f"{seconds / 60:.1f} min"


def render_hardware(snapshot: Any, usable_vram_bytes: int) -> list[str]:
    """Render the machine identity and its measured resource envelope."""
    gpu = snapshot.primary_gpu
    lines = [
        "MACHINE",
        f"  host                 {snapshot.hostname}  ({snapshot.os_release}, kernel {snapshot.kernel})",
        f"  cpu                  {snapshot.cpu_model} / {snapshot.cpu_threads} threads",
        f"  nvidia driver        {snapshot.driver_version}",
    ]
    if gpu is None:
        lines.append("  gpu                  NONE DETECTED — reconstruction cannot run here")
    else:
        lines += [
            f"  gpu                  {gpu.name}",
            f"  vram total           {_gib(gpu.total_vram_bytes)}",
            f"  vram usable now      {_gib(usable_vram_bytes)}  (total minus what is already held)",
        ]
        if snapshot.vram_holders:
            holders = ", ".join(
                f"pid {p.pid} {_gib(p.used_vram_bytes)} ({Path(p.process_name).name})"
                for p in snapshot.vram_holders
            )
            lines.append(f"  vram held by         {holders}")
    lines += [
        f"  ram total            {_gib(snapshot.memory.total_bytes)}",
        f"  ram available now    {_gib(snapshot.memory.available_bytes)}",
    ]
    for filesystem in snapshot.filesystems:
        lines.append(
            f"  disk {filesystem.path:<16} {_gib(filesystem.free_bytes)} free of "
            f"{_gib(filesystem.total_bytes)}"
        )
    return lines


def render_tools(snapshot: Any) -> list[str]:
    """Render the pinned tool versions, marking anything unavailable."""
    lines = ["TOOLS (pinned)"]
    for name, version in sorted(snapshot.tools.items()):
        lines.append(f"  {name:<16} {version}")
    lines += [
        f"  {'interpreter':<16} {snapshot.interpreter}",
        f"  {'torch':<16} {snapshot.cuda.get('torch', 'unknown')} (cuda {snapshot.cuda.get('torch_cuda', 'unknown')})",
    ]
    return lines


def render_capabilities(capabilities: list[tuple[str, bool, str, str, str]]) -> list[str]:
    """Render each compute-API probe: verdict, evidence, and the fix if it failed."""
    lines = ["COMPUTE APIs (probed independently)"]
    for name, ok, evidence, error, remediation in capabilities:
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {name}: {evidence}")
        if not ok:
            lines.append(f"         cause:   {error}")
            lines.append(f"         action:  {remediation}")
    return lines


def render_verdicts(verdicts: list[Any]) -> list[str]:
    """Render the per-stage go/no-go verdicts with their headroom maths."""
    lines = ["STAGE BUDGETS"]
    for verdict in verdicts:
        status = "RUN" if verdict.fits else "BLOCKED"
        lines.append(
            f"  [{status}] {verdict.stage} ({verdict.compute_api}): needs "
            f"{_gib(verdict.required_vram_bytes)}, {_gib(verdict.usable_vram_bytes)} usable"
        )
        for blocker in verdict.blockers:
            lines.append(f"         {blocker}")
    return lines


def render_budget(budget: Any, measurements: list[Any]) -> list[str]:
    """Render the published training budget, stating plainly how it was obtained."""
    if budget is None:
        return [
            "TRAINING BUDGET",
            "  not published: no successful training run has been measured on this host",
        ]
    lines = [
        "TRAINING BUDGET (measured)",
        f"  scene               {budget.scene}",
        f"  gpu                 {budget.gpu_name} ({_gib(budget.total_vram_bytes)} total, "
        f"{_gib(budget.usable_vram_bytes)} usable)",
        f"  default budget      {_gib(budget.default_stage_vram_bytes)} stage VRAM, "
        f"{budget.default_splat_count:,} splats, {_duration(budget.default_elapsed_seconds)}",
        f"  supported maximum   {budget.supported_max_splats:,} splats",
        f"  maximum basis       {budget.max_basis}",
        f"  marginal cost       {budget.marginal_bytes_per_splat:.1f} bytes/splat "
        f"(fixed overhead {_gib(int(budget.fixed_overhead_bytes))})",
        f"  headroom retained   {budget.headroom_fraction:.0%}",
        "  caveats:",
    ]
    for caveat in budget.caveats:
        lines.append(f"    - {caveat}")
    return lines


def render_runtime_budget(runtime_budget: Any) -> list[str]:
    """Render the measured runtime budget, or say plainly that there isn't one."""
    if runtime_budget is None:
        return [
            "RUNTIME BUDGET",
            "  not published: no render stage has been measured on this project yet",
        ]
    lines = [
        "RUNTIME BUDGET (measured at the renderer)",
        f"  asset               {runtime_budget.splat_count:,} splats on {runtime_budget.gpu_name}",
        f"  resolution          {runtime_budget.resolution}",
        f"  stage VRAM          {_gib(runtime_budget.stage_vram_bytes)}",
        f"  frame rate          {runtime_budget.fps:.2f} fps",
        f"  marginal cost       {runtime_budget.marginal_bytes_per_splat:.1f} bytes/splat at runtime",
    ]
    if runtime_budget.frame_rate_is_vsync_limited:
        lines.append("  vsync limited       YES - the display caps this, not the renderer")
    lines.append("  notes:")
    for note in runtime_budget.notes:
        lines.append(f"    - {note}")
    return lines


def render_report(
    snapshot: Any,
    usable_vram_bytes: int,
    capabilities: list[tuple[str, bool, str, str, str]],
    verdicts: list[Any],
    budget: Any,
    runtime_budget: Any,
) -> str:
    """Return the whole preflight as one printable report."""
    sections = [
        render_hardware(snapshot, usable_vram_bytes),
        render_tools(snapshot),
        render_capabilities(capabilities),
        render_verdicts(verdicts),
        render_budget(budget, []),
        render_runtime_budget(runtime_budget),
    ]
    return "\n".join("\n".join(section) for section in sections)