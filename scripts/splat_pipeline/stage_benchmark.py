#!/usr/bin/env python3
"""Price one reconstruction run under a sampler, and record what it cost.

Every stage of the pipeline is measured the same way -- one command, one sampler,
one record -- so the numbers are comparable and a reader can tell whether a stage
was expensive or merely different from the others.

A failed run is recorded too, annotated with the tail of its log. A stage that
was attempted and could not run is a different fact from one nobody tried, and
the error line is what the next attempt has to address.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from resource_probe import directory_size
from resource_sampler import ResourceSampler
from stage_measurement import StageMeasurement, read_measurements, write_measurements

GIBIBYTE = 1024**3

#: Lines of a stage log kept in a failure record. Enough to carry a compiler or
#: driver error, short enough not to turn the report into a log dump.
LOG_TAIL_LINES = 12


def measure_command(
    label: str,
    command: list[str],
    log_path: Path,
    input_dir: Path | None,
    output_dir: Path | None,
    settings: dict[str, str],
    tool_versions: dict[str, str],
    extras: dict[str, object] | None = None,
) -> StageMeasurement:
    """Run ``command`` once, sampling resources, and return what it cost."""
    input_bytes = directory_size(input_dir) if input_dir else 0
    before = directory_size(output_dir) if output_dir else 0
    with ResourceSampler() as sampler:
        exit_code = stream_to_log(command, log_path)
    peak = sampler.stop()
    after = directory_size(output_dir) if output_dir else 0
    return StageMeasurement(
        label=label,
        command=command,
        interpreter=str(command[0]),
        exit_code=exit_code,
        elapsed_seconds=peak.duration_seconds,
        peak=peak,
        input_bytes=input_bytes,
        output_bytes=max(0, after - before),
        splat_count=None,
        tool_versions=tool_versions,
        settings=settings,
        extras=extras or {},
        log_path=str(log_path),
    )


def parse_settings(pairs: list[str]) -> list[tuple[str, str]]:
    """Turn ``KEY=VALUE`` strings into pairs, dropping anything without a ``=``.

    A setting with no ``=`` is dropped rather than recorded: half a key in the
    report reads as a value somebody chose.
    """
    return [tuple(pair.split("=", 1)) for pair in pairs if "=" in pair]


def strip_separator(tokens: list[str]) -> list[str]:
    """Remove the ``--`` argparse leaves at the head of a remainder."""
    return [token for token in tokens if token != "--"]


def stream_to_log(command: list[str], log_path: Path) -> int:
    """Run ``command`` with its output appended to ``log_path``; return exit code.

    The argv is echoed into the log first, so a log recovered from a failed run
    still says what was run -- a stack trace without its command line is a
    mystery.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        log.write(("\n$ " + shlex.join(command) + "\n").encode())
        log.flush()
        completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    return completed.returncode


def append_to_report(report_path: str, measurement: StageMeasurement) -> None:
    """Add a measurement to the report, replacing any earlier run of the same label."""
    existing = read_measurements(report_path) if Path(report_path).exists() else []
    kept = [stage for stage in existing if stage.label != measurement.label]
    destination = write_measurements(report_path, [*kept, measurement])
    print(f"recorded in {destination}")


def log_tail(log_path: Path, lines: int = LOG_TAIL_LINES) -> str:
    """Return the last meaningful lines of a stage log, for the failure record."""
    try:
        content = log_path.read_text(errors="replace").replace("\r", "\n").splitlines()
    except OSError:
        return ""
    meaningful = [line.strip() for line in content if line.strip()]
    return " | ".join(meaningful[-lines:])[-2000:]


def record_failure(report_path: str, measurement: StageMeasurement, reason: str) -> None:
    """Store a failed measurement, annotated with why it failed."""
    annotated = StageMeasurement(
        **{
            **measurement.__dict__,
            "extras": {
                **measurement.extras,
                "failure": reason,
                "log_tail": log_tail(Path(measurement.log_path)),
            },
        }
    )
    append_to_report(report_path, annotated)


def print_measurement(measurement: StageMeasurement) -> None:
    """Print a measurement in the units an operator decides with."""
    print(f"[{measurement.label}] exit={measurement.exit_code}")
    print(f"  elapsed            {measurement.elapsed_seconds:.1f} s")
    print(f"  peak VRAM (total)  {measurement.peak.peak_vram_used_bytes / GIBIBYTE:.2f} GiB")
    print(f"  peak VRAM (stage)  {measurement.peak.stage_vram_bytes / GIBIBYTE:.2f} GiB")
    print(f"  peak RAM (stage)   {measurement.peak.stage_ram_bytes / GIBIBYTE:.2f} GiB")
    print(f"  disk written       {measurement.output_bytes / GIBIBYTE:.3f} GiB")
    if measurement.splat_count is not None:
        print(f"  splats             {measurement.splat_count:,}")
    if measurement.peak.missed_samples:
        print(f"  MISSED SAMPLES     {measurement.peak.missed_samples}")