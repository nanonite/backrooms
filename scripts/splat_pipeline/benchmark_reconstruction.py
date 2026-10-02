#!/usr/bin/env python3
"""Measure what a reconstruction stage actually costs on this machine.

Three subcommands, because there are three kinds of thing to price:

``splatfacto``
    Nerfstudio's default Splatfacto through the *pinned* interpreter, so the
    number recorded here is reproducible on another day and is not accidentally
    a different version's number.

``render``
    The Godot runtime stage: VRAM, wall time and the frame rate actually reached,
    at a resolution recorded with it.

``command``
    Anything else -- collision generation, import, a probe -- timed under the
    same sampler so every stage of the pipeline is priced by one mechanism.

Usage:
    python3 benchmark_reconstruction.py splatfacto --data <scene_dir> [--report FILE]
    python3 benchmark_reconstruction.py render --project <dir> --scene <res://path>
    python3 benchmark_reconstruction.py command --label <name> -- <command> [...]

Exit codes: 0 = measured, 1 = usage error, 2 = pinned tool missing,
3 = the measured command failed, 4 = expected splat output missing or unreadable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_benchmark
import splatfacto_benchmark
from hardware_report import GODOT_BINARY, detect_tool_versions
from stage_benchmark import (
    append_to_report,
    measure_command,
    parse_settings,
    print_measurement,
    record_failure,
    strip_separator,
)

EXIT_OK = 0
EXIT_STAGE_FAILED = 3


def run_arbitrary(args: argparse.Namespace) -> int:
    """Price an arbitrary collision/import/render command."""
    if not args.command:
        print("ERROR: no command given; pass one after --", file=sys.stderr)
        return splatfacto_benchmark.EXIT_USAGE
    measurement = measure_command(
        label=args.label,
        command=list(args.command),
        log_path=Path(args.log),
        input_dir=Path(args.input_dir) if args.input_dir else None,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        settings=dict(args.setting or []),
        tool_versions=detect_tool_versions(),
    )
    print_measurement(measurement)
    if measurement.exit_code != EXIT_OK:
        record_failure(args.report, measurement, f"{args.label} exited {measurement.exit_code}")
        return EXIT_STAGE_FAILED
    append_to_report(args.report, measurement)
    return EXIT_OK


def _add_splatfacto_arguments(subcommands: argparse._SubParsersAction) -> None:
    """Register the splatfacto subcommand."""
    defaults = splatfacto_benchmark.SPLATFACTO_DEFAULTS
    splatfacto = subcommands.add_parser("splatfacto", help="price a default Splatfacto run")
    splatfacto.add_argument("--data", required=True, help="capture dir with images/ and sparse/0/")
    splatfacto.add_argument("--output-dir", default="", help="where nerfstudio writes")
    splatfacto.add_argument("--log", default="splat_logs/budget_splatfacto.log")
    splatfacto.add_argument(
        "--max-num-iterations",
        default=defaults["max-num-iterations"],
        help="nerfstudio default is 30000",
    )
    splatfacto.add_argument(
        "--downscale-factor",
        default=None,
        help="dataparser resolution divisor; omit for nerfstudio's own default",
    )
    splatfacto.add_argument(
        "--stop-split-at",
        type=int,
        default=None,
        help="freeze densification at this step to bound Gaussian count",
    )
    splatfacto.add_argument(
        "--colmap-path",
        default=splatfacto_benchmark.DEFAULT_COLMAP_PATH,
        help="COLMAP model dir relative to --data",
    )
    splatfacto.add_argument("--staging-dir", default="", help="where the capture is staged")
    splatfacto.add_argument("--report", default="splat_logs/measurements.json")
    splatfacto.set_defaults(handler=lambda args: splatfacto_benchmark.run_splatfacto(args, append_to_report))


def _add_render_arguments(subcommands: argparse._SubParsersAction) -> None:
    """Register the render subcommand."""
    render = subcommands.add_parser("render", help="price the Godot runtime render stage")
    render.add_argument("--project", required=True, help="godot project directory")
    render.add_argument("--scene", required=True, help="res:// path of the scene to load")
    for flag in ("resolution", "frames", "warmup", "orbit-radius"):
        render.add_argument(f"--{flag}", default=render_benchmark.RENDER_DEFAULTS[flag])
    render.add_argument("--splat", default="", help="PLY whose Gaussian count to record")
    render.add_argument(
        "--label",
        default="render",
        help="measurement label; use a distinct one per asset so several survive in one report",
    )
    render.add_argument("--godot", default=GODOT_BINARY)
    render.add_argument("--log", default="splat_logs/benchmark_render.log")
    render.add_argument("--report", default="splat_logs/measurements.json")
    render.set_defaults(handler=render_benchmark.run_render)


def _add_command_arguments(subcommands: argparse._SubParsersAction) -> None:
    """Register the generic command subcommand."""
    arbitrary = subcommands.add_parser("command", help="price any other stage")
    arbitrary.add_argument("--label", required=True, help="collision / import / render")
    arbitrary.add_argument("--log", default="splat_logs/benchmark.log")
    arbitrary.add_argument("--input-dir", default="")
    arbitrary.add_argument("--output-dir", default="")
    arbitrary.add_argument("--report", default="splat_logs/measurements.json")
    arbitrary.add_argument(
        "--setting", action="append", default=[], metavar="KEY=VALUE", help="recorded setting"
    )
    arbitrary.add_argument("command", nargs=argparse.REMAINDER)
    arbitrary.set_defaults(handler=run_arbitrary)


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for every subcommand."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subcommands = parser.add_subparsers(dest="mode", required=True)
    _add_splatfacto_arguments(subcommands)
    _add_render_arguments(subcommands)
    _add_command_arguments(subcommands)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the requested subcommand."""
    args = build_parser().parse_args(argv)
    args.setting = parse_settings(getattr(args, "setting", []))
    args.command = strip_separator(getattr(args, "command", []))
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())