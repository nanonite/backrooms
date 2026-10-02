#!/usr/bin/env python3
"""Price a default Splatfacto run through the pinned nerfstudio interpreter.

Two things this module exists to get right, both discovered the hard way.

**Argument order.** Nerfstudio binds a positional group after each subcommand.
Method options go *before* the ``colmap`` dataparser name; dataparser options
such as ``--downscale-factor`` go *after* it. Mixing them up is reported as
"unrecognized option" and costs a whole run to discover.

**Bounded inputs.** nerfstudio 1.1.5's Splatfacto has no hard cap on Gaussian
count -- there is no ``--cap-max-num-splats``. The levers that exist are the
resolution factor and ``stop-split-at``, which freezes densification. Any bound
must therefore be stated as a *measured* splat count from a run that used a
lever, never as a configured cap.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from colmap_dataset import DatasetError, stage_dataset
from hardware_report import NERFSTUDIO_PYTHON, detect_tool_versions
from ply_vertex_count import vertex_count
from stage_benchmark import measure_command, print_measurement, record_failure
from stage_measurement import StageMeasurement

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_MISSING_TOOL = 2
EXIT_STAGE_FAILED = 3
EXIT_BAD_OUTPUT = 4

#: Nerfstudio's own defaults. Recorded verbatim so a reader can see that the
#: headline number is the *default* configuration, not a tuned one.
SPLATFACTO_DEFAULTS = {
    "max-num-iterations": "30000",
    "pipeline.model.sh-degree": "3",
    "pipeline.model.num-random": "50000",
    "pipeline.model.stop-split-at": "15000",
    "pipeline.datamanager.dataparser.downscale-factor": "None (max dimension < 1600px)",
    "mixed-precision": "False",
}

#: Nerfstudio's colmap dataparser defaults to ``<data>/colmap/sparse/0``. This
#: repo's COLMAP 3.10 + GLOMAP layout puts the model at ``<scene>/sparse/0``, so
#: the default here points at what the pipeline actually produces. Getting this
#: wrong fails with "Colmap path does not exist" before any GPU work happens.
DEFAULT_COLMAP_PATH = "sparse/0"


def build_splatfacto_command(
    data_dir: Path,
    output_dir: Path,
    iterations: str,
    downscale_factor: str | None,
    stop_split_at: int | None,
    colmap_path: str = DEFAULT_COLMAP_PATH,
) -> list[str]:
    """Return the argv for a default Splatfacto run, appending bounded overrides.

    Every flag is explicit even when it equals the documented default: the
    measurement has to be readable without consulting Nerfstudio's docs.
    """
    command = [
        NERFSTUDIO_PYTHON,
        "-m",
        "nerfstudio.scripts.train",
        "splatfacto",
        "--data",
        str(data_dir),
        "--output-dir",
        str(output_dir),
        "--vis",
        "tensorboard",
        "--experiment-name",
        "budget_probe",
        "--max-num-iterations",
        iterations,
    ]
    if stop_split_at is not None:
        command += ["--pipeline.model.stop-split-at", str(stop_split_at)]
    command += ["colmap", "--colmap-path", colmap_path]
    if downscale_factor is not None:
        command += ["--downscale-factor", str(downscale_factor)]
    return command


def find_exported_splat(output_dir: Path) -> Path | None:
    """Return the ``.ply`` nerfstudio wrote under ``output_dir``, if any."""
    candidates = sorted(output_dir.rglob("*.ply"))
    return candidates[-1] if candidates else None


def run_splatfacto(args, append_to_report) -> int:
    """Price one default Splatfacto run and append it to the report."""
    if not Path(args.data).is_dir():
        print(f"ERROR: --data directory not found: {args.data}", file=sys.stderr)
        return EXIT_USAGE
    if not Path(NERFSTUDIO_PYTHON).exists():
        print(
            f"ERROR: pinned nerfstudio interpreter missing: {NERFSTUDIO_PYTHON}\n"
            "       Install the nerfstudio conda env, or point NERFSTUDIO_PYTHON.",
            file=sys.stderr,
        )
        return EXIT_MISSING_TOOL
    try:
        staged = stage_dataset(args.data, _staging_path(args))
    except DatasetError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return EXIT_USAGE
    output_dir = Path(args.output_dir or (Path(args.data).parent / "budget_splatfacto"))
    measurement = _measure(args, staged, output_dir)
    print_measurement(measurement)
    if measurement.exit_code != EXIT_OK:
        record_failure(args.report, measurement, "splatfacto exited non-zero")
        print(f"ERROR: splatfacto exited {measurement.exit_code}; see {args.log}", file=sys.stderr)
        return EXIT_STAGE_FAILED
    if measurement.splat_count is None:
        print(f"ERROR: no .ply under {output_dir}", file=sys.stderr)
        return EXIT_BAD_OUTPUT
    append_to_report(args.report, measurement)
    return EXIT_OK


def _staging_path(args) -> Path:
    """Return where the nerfstudio-ready copy of the capture is built."""
    return Path(args.staging_dir) if args.staging_dir else Path(args.data).with_name(
        Path(args.data).name + "_ns"
    )


def _measure(args, staged, output_dir: Path) -> StageMeasurement:
    """Build the argv, run it under the sampler, and attach the splat count."""
    command = build_splatfacto_command(
        staged.staging_dir,
        output_dir,
        args.max_num_iterations,
        args.downscale_factor,
        args.stop_split_at,
        args.colmap_path,
    )
    settings = dict(SPLATFACTO_DEFAULTS)
    settings["downscale-factor"] = args.downscale_factor or str(staged.downscale_factor)
    settings["training-resolution"] = f"{staged.downscaled_size[0]}x{staged.downscaled_size[1]}"
    settings["input-resolution"] = f"{staged.image_size[0]}x{staged.image_size[1]}"
    settings["max-num-iterations"] = args.max_num_iterations
    settings["colmap-path"] = args.colmap_path
    if args.stop_split_at is not None:
        settings["stop-split-at"] = str(args.stop_split_at)
    print("staged dataset:", staged.to_dict(), flush=True)
    print("running:", shlex.join(command), flush=True)
    measurement = measure_command(
        label="splatfacto",
        command=command,
        log_path=Path(args.log),
        input_dir=staged.staging_dir,
        output_dir=output_dir,
        settings=settings,
        tool_versions=detect_tool_versions(),
        extras={"dataset": staged.to_dict()},
    )
    splat = find_exported_splat(output_dir)
    if splat is not None:
        object.__setattr__(measurement, "splat_count", vertex_count(splat))
    return measurement