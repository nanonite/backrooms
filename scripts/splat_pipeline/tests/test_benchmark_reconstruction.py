#!/usr/bin/env python3
"""Tests for the measurement record and the benchmark's command construction.

An argv that is silently malformed costs a full training run before it reports
itself, so the ordering rules that nerfstudio's CLI enforces -- method options
before the dataparser name, dataparser options after it -- are asserted here
rather than discovered at 2am.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_benchmark_reconstruction.py -v
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import benchmark_reconstruction as bench
import render_benchmark
import splatfacto_benchmark
from ply_vertex_count import PlyHeaderError, vertex_count
from resource_sampler import PeakUsage
from stage_benchmark import log_tail, record_failure
from stage_measurement import (
    MEASUREMENT_SCHEMA_VERSION,
    StageMeasurement,
    read_measurements,
    write_measurements,
)

GIBIBYTE = 1024**3


def make_measurement(label="splatfacto", exit_code=0, **overrides):
    """Return a measurement with sensible defaults for the fields tests care about."""
    defaults = {
        "command": ["ns-train", "splatfacto"],
        "interpreter": "ns-train",
        "exit_code": exit_code,
        "elapsed_seconds": 12.5,
        "peak": PeakUsage(3 * GIBIBYTE, 90, 5 * GIBIBYTE, GIBIBYTE, GIBIBYTE, 12, 0, 12.5),
        "input_bytes": 100,
        "output_bytes": 200,
        "splat_count": 1234,
        "tool_versions": {"nerfstudio": "1.1.5"},
        "settings": {"stop-split-at": "15000"},
        "extras": {},
        "log_path": "splat_logs/x.log",
    }
    return StageMeasurement(label=label, **{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Splatfacto argv
# ---------------------------------------------------------------------------


def _command(*args, **kwargs):
    defaults = {
        "data_dir": Path("scene"),
        "output_dir": Path("out"),
        "iterations": "30000",
        "downscale_factor": None,
        "stop_split_at": None,
    }
    return splatfacto_benchmark.build_splatfacto_command(**{**defaults, **kwargs})


def test_method_options_precede_the_dataparser_name():
    command = _command()

    assert command.index("--output-dir") < command.index("colmap")


def test_the_dataparser_option_follows_its_name():
    """nerfstudio parses everything after the dataparser name as a dataparser option."""
    command = _command(colmap_path="sparse/0")

    assert command.index("colmap") < command.index("--colmap-path")


def test_the_repo_layout_is_passed_because_nerfstudio_defaults_to_colmap_sparse_0():
    command = _command()

    assert command[command.index("--colmap-path") + 1] == "sparse/0"
    assert splatfacto_benchmark.DEFAULT_COLMAP_PATH == "sparse/0"


def test_the_downscale_factor_is_omitted_so_nerfstudio_resolves_its_own_default():
    command = _command()

    assert "--downscale-factor" not in command


def test_an_explicit_downscale_factor_is_appended_after_the_dataparser():
    command = _command(downscale_factor="2")

    assert command.index("colmap") < command.index("--downscale-factor")
    assert command[command.index("--downscale-factor") + 1] == "2"


def test_bounding_densification_uses_the_flag_nerfstudio_actually_has():
    command = _command(stop_split_at=1000)

    assert "--cap-max-num-splats" not in command
    assert command[command.index("--pipeline.model.stop-split-at") + 1] == "1000"


def test_the_interpreter_is_pinned_before_the_module():
    command = _command()

    assert command[0].endswith("bin/python")
    assert command[1:4] == ["-m", "nerfstudio.scripts.train", "splatfacto"]


def test_the_default_step_count_is_nerfstudios_own_default():
    command = _command()

    assert command[command.index("--max-num-iterations") + 1] == "30000"
    assert splatfacto_benchmark.SPLATFACTO_DEFAULTS["max-num-iterations"] == "30000"


# ---------------------------------------------------------------------------
# Render argv and output parsing
# ---------------------------------------------------------------------------


def test_render_command_carries_the_resolution_it_measures_at():
    command = render_benchmark.build_render_command(
        "godot", Path("godot_walk"), "res://a.tscn", "1920x1080", "300", "60", "1.0"
    )

    assert command[command.index("--resolution") + 1] == "1920x1080"


def test_render_command_runs_the_project_fps_script():
    command = render_benchmark.build_render_command(
        "godot", Path("godot_walk"), "res://a.tscn", "1280x720", "300", "60", "1.0"
    )

    assert "res://scripts/measure_fps.gd" in command


def test_a_render_line_is_parsed_into_fps():
    payload = render_benchmark.parse_fps_json('noise\nFPS_JSON {"fps": 60.12, "frames": 300}\n')

    assert payload["fps"] == 60.12


def test_output_without_a_render_line_yields_no_fps_rather_than_a_guess():
    assert render_benchmark.parse_fps_json("Vulkan 1.4.329 - Forward+ - Using Device #0") == {}


# ---------------------------------------------------------------------------
# Measurement record
# ---------------------------------------------------------------------------


def test_a_record_round_trips_through_json(tmp_path):
    path = write_measurements(tmp_path / "m.json", [make_measurement()])

    restored = read_measurements(path)[0]

    assert restored.label == "splatfacto"
    assert restored.splat_count == 1234
    assert restored.peak.peak_vram_used_bytes == 3 * GIBIBYTE
    assert restored.settings["stop-split-at"] == "15000"


def test_the_record_declares_a_schema_version(tmp_path):
    path = write_measurements(tmp_path / "m.json", [make_measurement()])

    assert json.loads(path.read_text())["schema_version"] == MEASUREMENT_SCHEMA_VERSION


def test_a_record_keeps_the_exact_argv_so_a_run_can_be_repeated(tmp_path):
    measurement = make_measurement(command=["ns-train", "splatfacto", "--data", "scene"])

    path = write_measurements(tmp_path / "m.json", [measurement])

    assert read_measurements(path)[0].command == measurement.command


def test_a_failed_measurement_is_still_a_record(tmp_path):
    path = write_measurements(tmp_path / "m.json", [make_measurement(exit_code=1, splat_count=None)])

    restored = read_measurements(path)[0]

    assert not restored.succeeded
    assert restored.splat_count is None


def test_record_failure_keeps_the_log_tail_as_the_reason(tmp_path):
    log = tmp_path / "stage.log"
    log.write_text("loading\n" + "the actual error\n")

    record_failure(str(tmp_path / "m.json"), make_measurement(log_path=str(log), exit_code=1), "exited 1")

    restored = read_measurements(tmp_path / "m.json")[0]
    assert restored.extras["failure"] == "exited 1"
    assert "the actual error" in restored.extras["log_tail"]


def test_log_tail_of_a_missing_log_is_empty_not_an_error(tmp_path):
    assert log_tail(tmp_path / "absent.log") == ""


def test_a_splat_count_is_read_from_the_ply_header(tmp_path):
    ply = tmp_path / "a.ply"
    ply.write_bytes(
        b"ply\nformat binary_little_endian 1.0\nelement vertex 42\n"
        b"property float x\nproperty float y\nproperty float z\nend_header\n"
    )

    assert render_benchmark.splat_count(str(ply)) == 42


def test_a_real_splat_asset_reports_a_plausible_count():
    """The committed asset must parse without needing the reader's dependencies."""
    asset = Path(__file__).resolve().parents[3] / "godot_walk/assets/corridor_splat/corridor.ply"

    if not asset.is_file():
        pytest.skip("corridor.ply is not present in this checkout")

    assert vertex_count(asset) > 100_000


def test_a_file_that_is_not_a_ply_raises_rather_than_reporting_zero(tmp_path):
    not_a_ply = tmp_path / "a.ply"
    not_a_ply.write_bytes(b"not a ply at all")

    with pytest.raises(PlyHeaderError, match="magic"):
        vertex_count(not_a_ply)


def test_a_ply_without_a_vertex_element_is_refused(tmp_path):
    no_vertex = tmp_path / "a.ply"
    no_vertex.write_bytes(b"ply\nformat ascii 1.0\nelement face 3\nend_header\n")

    with pytest.raises(PlyHeaderError, match="element vertex"):
        vertex_count(no_vertex)


def test_an_unterminated_header_is_refused_rather_than_guessed(tmp_path):
    truncated = tmp_path / "a.ply"
    truncated.write_bytes(b"ply\nelement vertex 7\n")

    with pytest.raises(PlyHeaderError, match="end_header"):
        vertex_count(truncated)


def test_the_benchmark_returns_no_count_for_an_unreadable_splat(tmp_path):
    broken = tmp_path / "a.ply"
    broken.write_bytes(b"garbage")

    assert render_benchmark.splat_count(str(broken)) is None


def test_a_missing_splat_file_yields_no_count_rather_than_zero():
    assert render_benchmark.splat_count("/nonexistent/a.ply") is None


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_the_render_subcommand_exists_and_defaults_to_a_stated_resolution():
    args = bench.build_parser().parse_args(["render", "--project", "p", "--scene", "s"])

    assert args.resolution == "1280x720"
    assert render_benchmark.RENDER_DEFAULTS["resolution"] == "1280x720"


def test_separate_render_assets_can_be_recorded_under_distinct_labels():
    parser = bench.build_parser()

    first = parser.parse_args(["render", "--project", "p", "--scene", "s", "--label", "render_a"])
    second = parser.parse_args(["render", "--project", "p", "--scene", "s", "--label", "render_b"])

    assert first.label != second.label


def test_a_missing_required_subcommand_is_a_usage_error():
    with pytest.raises(SystemExit):
        bench.build_parser().parse_args([])


def test_a_separator_is_stripped_from_the_measured_command():
    args = bench.build_parser().parse_args(["command", "--label", "x", "--", "echo", "hi"])

    assert bench.strip_separator(args.command) == ["echo", "hi"]


def test_settings_are_parsed_as_key_value_pairs():
    assert bench.parse_settings(["res=1280x720"]) == [("res", "1280x720")]


def test_a_setting_without_a_equals_sign_is_dropped_rather_than_recorded_garbage():
    assert bench.parse_settings(["res", "res=1280x720"]) == [("res", "1280x720")]