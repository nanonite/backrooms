#!/usr/bin/env python3
"""Tests for the preflight's decisions: what blocks, what is reported, what is published.

The probes themselves need real hardware, so they are injected here. What is
tested is the part that must be right even so: that a missing API blocks the
stage that needs it, that the exit code names the most blocking problem, and
that a budget is never published from a run that failed.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_preflight_hardware.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import preflight_hardware as preflight
from cuda_capability import CudaCapability
from vulkan_capability import VulkanCapability
from webgpu_capability import WebGpuCapability

GIBIBYTE = 1024**3


def working_cuda():
    return CudaCapability(True, True, "RTX 4070 Ti", "8.9", 12 * GIBIBYTE, 9 * GIBIBYTE, 16, "2.3.1", "12.1", "")


def working_vulkan():
    return VulkanCapability(True, "1.4.329", "RTX 4070 Ti", "NVIDIA", "Forward+", "godot", "")


def working_webgpu():
    return WebGpuCapability(True, "NVIDIA", "vulkan", "wgpu-py", "")


def broken_cuda(error="CUDA driver version is insufficient"):
    return CudaCapability(False, False, "", "", 0, 0, 0, "", "", error)


def broken_vulkan(error="Could not create Vulkan device"):
    return VulkanCapability(False, "", "", "", "", "godot", error)


def broken_webgpu(error="navigator.gpu is undefined"):
    return WebGpuCapability(False, "", "", "none", error)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_everything_present_and_the_budget_fits_is_zero():
    assert preflight.decide_exit_code(working_cuda(), working_vulkan(), working_webgpu(), True) == 0


def test_no_cuda_training_beats_every_other_problem():
    code = preflight.decide_exit_code(broken_cuda(), broken_vulkan(), broken_webgpu(), True)

    assert code == 2


def test_no_vulkan_is_reported_before_the_missing_webgpu():
    code = preflight.decide_exit_code(working_cuda(), broken_vulkan(), broken_webgpu(), True)

    assert code == 3


def test_missing_webgpu_is_reported_when_everything_else_works():
    code = preflight.decide_exit_code(working_cuda(), working_vulkan(), broken_webgpu(), True)

    assert code == 4


def test_an_over_budget_default_is_reported_even_when_all_apis_pass():
    code = preflight.decide_exit_code(working_cuda(), working_vulkan(), working_webgpu(), False)

    assert code == 5


def test_each_exit_code_is_distinct():
    codes = {
        preflight.decide_exit_code(working_cuda(), working_vulkan(), working_webgpu(), True),
        preflight.decide_exit_code(broken_cuda(), working_vulkan(), working_webgpu(), True),
        preflight.decide_exit_code(working_cuda(), broken_vulkan(), working_webgpu(), True),
        preflight.decide_exit_code(working_cuda(), working_vulkan(), broken_webgpu(), True),
        preflight.decide_exit_code(working_cuda(), working_vulkan(), working_webgpu(), False),
    }

    assert len(codes) == 5


# ---------------------------------------------------------------------------
# Capability rows
# ---------------------------------------------------------------------------


def test_a_working_probe_reports_no_remediation_to_act_on():
    rows = preflight.capability_rows(working_cuda(), working_vulkan(), working_webgpu())

    assert all(ok for _, ok, _, _, _ in rows)
    assert all(not fix for _, _, _, _, fix in rows)


def test_a_failing_probe_carries_its_cause_and_a_specific_action():
    rows = preflight.capability_rows(working_cuda(), working_vulkan(), broken_webgpu())

    failed = [row for row in rows if not row[1]][0]
    assert failed[0] == "WebGPU collision"
    assert failed[3] == "navigator.gpu is undefined"
    assert "splat-transform" in failed[4]


def test_a_missing_torch_names_the_interpreter_rather_than_saying_only_no_torch():
    cuda = broken_cuda("No module named 'torch'")

    rows = preflight.capability_rows(cuda, working_vulkan(), working_webgpu())

    assert "nerfstudio" in rows[0][4]


# ---------------------------------------------------------------------------
# Budget publication guard
# ---------------------------------------------------------------------------


class _Budget:
    default_stage_vram_bytes = 10 * GIBIBYTE


def test_no_measured_budget_is_treated_as_fitting_rather_than_failing():
    assert preflight.budget_fits(None, 1 * GIBIBYTE)


def test_a_measured_budget_that_eats_the_headroom_is_reported_as_over():
    assert not preflight.budget_fits(_Budget(), 9 * GIBIBYTE)


# ---------------------------------------------------------------------------
# Capability problems feed the caveats
# ---------------------------------------------------------------------------


def test_every_unverified_capability_is_named():
    problems = preflight.capability_problems(working_cuda(), working_vulkan(), broken_webgpu())

    assert len(problems) == 1
    assert "WebGPU" in problems[0]


def test_a_fully_working_host_has_no_capability_problems():
    assert preflight.capability_problems(working_cuda(), working_vulkan(), working_webgpu()) == []


# ---------------------------------------------------------------------------
# API mapping
# ---------------------------------------------------------------------------


def test_each_stage_is_mapped_to_the_api_its_requirement_names():
    status = preflight._api_status(working_cuda(), working_vulkan(), working_webgpu())

    for stage in ("splatfacto", "collision", "import", "render"):
        api = preflight.api_name(stage)
        assert api in status


def test_an_unknown_stage_falls_back_rather_than_raising():
    assert preflight.api_name("teleport") == "cuda"


# ---------------------------------------------------------------------------
# Argument surface
# ---------------------------------------------------------------------------


def test_filesystem_paths_are_repeatable():
    args = preflight.build_parser().parse_args(["--filesystem", "/a", "--filesystem", "/b"])

    assert args.filesystem == ["/a", "/b"]


def test_a_missing_measurement_file_yields_no_measurements_rather_than_an_error(tmp_path):
    assert preflight._load_measurements(str(tmp_path / "absent.json")) == []


def test_a_corrupt_measurement_file_is_treated_as_absent(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")

    assert preflight._load_measurements(str(broken)) == []


def test_no_output_path_means_no_measurements_are_loaded():
    assert preflight._load_measurements("") == []


@pytest.mark.parametrize(
    ("probe_name", "working", "broken"),
    [
        ("CUDA training", working_cuda, broken_cuda),
        ("Vulkan rendering", working_vulkan, broken_vulkan),
        ("WebGPU collision", working_webgpu, broken_webgpu),
    ],
)
def test_each_api_is_reported_as_unavailable_rather_than_silently_assumed(
    probe_name, working, broken
):
    healthy = {
        "CUDA training": working_cuda,
        "Vulkan rendering": working_vulkan,
        "WebGPU collision": working_webgpu,
    }
    degraded = {**healthy, probe_name: broken}

    rows = preflight.capability_rows(
        degraded["CUDA training"](), degraded["Vulkan rendering"](), degraded["WebGPU collision"]()
    )
    verdicts = {name: ok for name, ok, _, _, _ in rows}

    assert verdicts[probe_name] is False
    assert sum(verdicts.values()) == 2

# ---------------------------------------------------------------------------
# Recorded failures override a green resource verdict
# ---------------------------------------------------------------------------


def _failed(label, reason="exited non-zero", log_path="splat_logs/stage.log"):
    from resource_sampler import PeakUsage
    from stage_measurement import StageMeasurement

    return StageMeasurement(
        label=label,
        command=["x"],
        interpreter="x",
        exit_code=1,
        elapsed_seconds=1.0,
        peak=PeakUsage(0, 0, 0, 0, 0, 1, 0, 1.0),
        input_bytes=0,
        output_bytes=0,
        splat_count=None,
        tool_versions={},
        extras={"failure": reason, "log_tail": "the compiler said no"},
        log_path=log_path,
    )


def test_a_stage_attempted_and_failed_is_not_reported_as_runnable():
    from resource_budget import BudgetVerdict

    verdict = BudgetVerdict("splatfacto", True, "cuda", 9, 4, (), ())
    measurements = [_failed("splatfacto")]

    revised = preflight.apply_recorded_failures([verdict], measurements)[0]

    assert revised.fits is False


def test_a_recorded_failure_carries_the_log_line_that_explained_it():
    from resource_budget import BudgetVerdict

    verdict = BudgetVerdict("splatfacto", True, "cuda", 9, 4, (), ())

    revised = preflight.apply_recorded_failures([verdict], [_failed("splatfacto")])[0]

    assert any("the compiler said no" in blocker for blocker in revised.blockers)


def test_a_recorded_failure_points_at_the_log_to_fix():
    from resource_budget import BudgetVerdict

    verdict = BudgetVerdict("collision", True, "webgpu", 9, 2, (), ())
    failed = _failed("collision", log_path="splat_logs/collision.log")

    revised = preflight.apply_recorded_failures([verdict], [failed])[0]

    assert any("splat_logs/collision.log" in action for action in revised.actions)


def test_a_stage_with_no_recorded_failure_keeps_its_verdict():
    from resource_budget import BudgetVerdict

    verdict = BudgetVerdict("render", True, "vulkan", 9, 2, (), ())

    revised = preflight.apply_recorded_failures([verdict], [_failed("splatfacto")])[0]

    assert revised is verdict


def test_only_failed_measurements_count_as_recorded_failures():
    from stage_measurement import StageMeasurement

    succeeded = StageMeasurement(
        label="splatfacto",
        command=["x"],
        interpreter="x",
        exit_code=0,
        elapsed_seconds=1.0,
        peak=PeakUsageStub(),
        input_bytes=0,
        output_bytes=0,
        splat_count=10,
        tool_versions={},
    )

    assert preflight.recorded_failures([succeeded]) == {}


class PeakUsageStub:
    """Minimal stand-in so a successful measurement needs no real sampler."""

    peak_vram_used_bytes = 0
    stage_vram_bytes = 0
