#!/usr/bin/env python3
"""Tests for the #103 candidate CLI (``clean_candidate.py``).

The CLI is the part a reviewer will re-run, so what it is checked for is the
promises the report makes: the input really is the shipped #100 result (digest
check), every stage's counts add up, the output keeps the property layout, and
the node translation compensates for GDGS re-centring the smaller cloud.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_clean_candidate.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clean_candidate
import clean_splat
import splat_frame
from test_splat_cleanup import MANIFEST, raw_for, write_ply

#: Godot-world positions: three splats that form one structure, one floater.
ROOM = [[0.0, -1.0, 0.0], [0.2, -1.0, 0.0], [0.0, -1.0, 0.2]]
FLOATER = [6.0, 0.5, 6.0]


def build_input(tmp_path: Path) -> tuple[Path, splat_frame.PlyToWorld]:
    """Write a tiny source PLY whose points are placed in world space."""
    contract = splat_frame.FrameContract.load(MANIFEST)
    rows = [
        dict(
            zip(("x", "y", "z"), raw_for(point, contract.ply_to_world)),
            opacity=4.0,
            scale_0=-4.0,
            scale_1=-4.0,
            scale_2=-4.0,
        )
        for point in ROOM + [FLOATER]
    ]
    source = tmp_path / "baseline.ply"
    write_ply(source, rows)
    return source, contract.ply_to_world


def base_args(source: Path, tmp_path: Path) -> list[str]:
    """Return the minimal CLI arguments for one run."""
    return [
        "--ply", str(source),
        "--manifest", str(MANIFEST),
        "--out", str(tmp_path / "candidate.ply"),
        "--report", str(tmp_path / "candidate.report.json"),
    ]


def run_cli(argv: list[str]) -> dict:
    """Run the CLI exactly as a reviewer would and return its report."""
    return clean_candidate.run(clean_candidate.parse_args(argv))


class TestStages:
    def test_no_stage_keeps_every_vertex(self, tmp_path):
        source, mapping = build_input(tmp_path)
        report = run_cli(base_args(source, tmp_path))
        assert report["input"]["splat_count"] == 4
        assert report["output"]["splat_count"] == 4
        assert report["removed"]["total"] == 0
        assert set(report["removed"]["per_stage"].values()) == {0}
        assert report["params"]["stages"] == []

    def test_component_stage_drops_the_isolated_floater(self, tmp_path):
        source, _ = build_input(tmp_path)
        report = run_cli(base_args(source, tmp_path) + ["--voxel-m", "0.5", "--min-component-splats", "2"])
        assert report["output"]["splat_count"] == 3
        assert report["removed"]["per_stage"]["component"] == 1
        assert report["components"]["component_count"] == 2

    def test_opacity_and_extent_stages_are_explicit(self, tmp_path):
        source, _ = build_input(tmp_path)
        report = run_cli(
            base_args(source, tmp_path) + ["--min-opacity", "0.9", "--max-extent-m", "0.2"]
        )
        assert report["params"]["min_opacity"] == 0.9
        assert report["params"]["max_extent_m"] == 0.2
        assert set(report["params"]["stages"]) == {"extent", "opacity"}
        assert report["removed"]["total"] == 0  # every synthetic splat survives both

    def test_views_stage_demands_its_auxiliary_data(self, tmp_path):
        source, _ = build_input(tmp_path)
        with pytest.raises(SystemExit):
            run_cli(base_args(source, tmp_path) + ["--min-views", "1"])


class TestProvenance:
    def test_baseline_digest_is_verified_and_recorded(self, tmp_path):
        source, _ = build_input(tmp_path)
        baseline = tmp_path / "baseline.report.json"
        baseline.write_text(
            json.dumps({"output": {"digests": {"sha256": clean_splat.file_digests(source)["sha256"]}}})
        )
        report = run_cli(base_args(source, tmp_path) + ["--baseline-report", str(baseline)])
        provenance = report["input"]["provenance"]
        assert provenance["checked"] is True
        assert provenance["baseline_output_sha256"] == provenance["input_sha256"]

    def test_a_different_input_than_the_recorded_result_is_refused(self, tmp_path):
        source, _ = build_input(tmp_path)
        baseline = tmp_path / "baseline.report.json"
        baseline.write_text(json.dumps({"output": {"digests": {"sha256": "deadbeef"}}}))
        with pytest.raises(SystemExit):
            run_cli(base_args(source, tmp_path) + ["--baseline-report", str(baseline)])

    def test_report_carries_input_and_output_digests(self, tmp_path):
        source, _ = build_input(tmp_path)
        report = run_cli(base_args(source, tmp_path))
        assert report["input"]["digests"]["sha256"] == clean_splat.file_digests(source)["sha256"]
        assert report["output"]["digests"]["sha256"] == clean_splat.file_digests(
            tmp_path / "candidate.ply"
        )["sha256"]


class TestOutput:
    def test_output_keeps_the_property_layout_and_only_changes_the_count(self, tmp_path):
        source, _ = build_input(tmp_path)
        run_cli(base_args(source, tmp_path) + ["--voxel-m", "0.5", "--min-component-splats", "2"])
        source_header = clean_splat.read_raw_ply(source)
        output_header = clean_splat.read_raw_ply(tmp_path / "candidate.ply")
        assert output_header[0] == source_header[0]
        assert output_header[1].shape[0] == 3

    def test_node_translation_compensates_for_re_centring(self, tmp_path):
        source, mapping = build_input(tmp_path)
        report = run_cli(base_args(source, tmp_path) + ["--voxel-m", "0.5", "--min-component-splats", "2"])
        header, table, _ = clean_splat.read_raw_ply(tmp_path / "candidate.ply")
        index = {name: position for position, name in enumerate(header)}
        centroid = np.column_stack(
            [table[:, index["x"]], table[:, index["y"]], table[:, index["z"]]]
        ).astype(np.float64).mean(axis=0)
        expected = clean_splat.node_translation_world(
            centroid, np.asarray(mapping.origin_ply_units), mapping
        )
        assert np.allclose(report["node_translation_world"], expected, atol=1e-6)
        assert report["filtered_centroid_ply"] == pytest.approx(centroid.tolist())

    def test_empty_result_is_refused(self, tmp_path):
        source, _ = build_input(tmp_path)
        with pytest.raises(SystemExit):
            run_cli(base_args(source, tmp_path) + ["--min-opacity", "0.999999999"])
