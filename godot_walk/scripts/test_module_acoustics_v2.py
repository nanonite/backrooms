"""Issue #216 checks for measured module acoustics v0.2.0."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT
from module_acoustics import check_v2, load_v2
from module_acoustics_v2 import METRIC_FIELDS, PROBE_RESULTS

PROJECT = ROOT / "godot_walk"
RUNNER = "res://scripts/probe_module_acoustics.gd"


def test_v2_document_and_hash_pins_are_valid() -> None:
    document = load_v2()
    assert check_v2() == []
    assert document["generator_version"] == "module-acoustics-0.2.0"
    assert document["probe_method"]["module_count"] == 11
    assert document["operator_listening"] == "pending"


def test_every_admitted_module_has_measured_probe_values() -> None:
    document = load_v2()
    report = json.loads((ROOT / PROBE_RESULTS).read_text(encoding="utf-8"))
    assert set(document["modules"]) == set(report["modules"])
    for key, record in document["modules"].items():
        assert record["probe"]["provenance"] == "measured", key
        assert record["profile"]["path"]
        assert record["absorption"]["status"] == "unknown"
        assert all(math.isfinite(record["probe"][field]) for field in METRIC_FIELDS)
        assert record["probe"]["evidence"][0]["path"] == PROBE_RESULTS.as_posix()


def test_measurements_match_a_second_headless_probe_run(tmp_path: Path) -> None:
    godot = shutil.which("godot4") or shutil.which("godot")
    if godot is None:
        pytest.skip("Godot is required to repeat the #205 module probe")
    output = tmp_path / "module_acoustics_probe_rerun.json"
    env = _godot_environment(tmp_path)
    result = subprocess.run(
        [godot, "--headless", "--path", str(PROJECT), "--script", RUNNER,
         "--", f"--output={output}"],
        cwd=PROJECT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ISSUE216_MODULE_ACOUSTICS modules=11" in result.stdout
    _compare_measurements(load_v2(), json.loads(output.read_text(encoding="utf-8")))


def _godot_environment(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "godot-data")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "godot-config")
    return env


def _compare_measurements(document: dict, rerun: dict) -> None:
    assert set(document["modules"]) == set(rerun["modules"])
    tolerances = document["reproducibility"]
    for key, expected in document["modules"].items():
        actual = rerun["modules"][key]["metrics"]
        for field in METRIC_FIELDS:
            tolerance = _tolerance(field, tolerances)
            assert math.isclose(expected["probe"][field], actual[field], abs_tol=tolerance), key


def _tolerance(field: str, tolerances: dict) -> float:
    if field == "openness":
        return tolerances["openness_tolerance"]
    if field in {"mean_distance_m", "max_distance_m", "ceiling_height_m"}:
        return tolerances["distance_tolerance_m"]
    return tolerances["reverb_parameter_tolerance"]
