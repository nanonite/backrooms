#!/usr/bin/env python3
"""Tests for the fixed-view render metrics (#103).

The metrics are the numbers the report leans on, so they are checked against
images whose answer is known by construction: a half-black frame, a frame that
changed by a known number of pixels, and a run whose headings do not match.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_render_metrics.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import render_metrics
from render_metrics import black_fraction, build_report, changed_stats, compare_runs


def frame(width: int, height: int, value: int) -> np.ndarray:
    """Return a solid colour frame."""
    return np.full((height, width, 3), value, dtype=np.uint8)


def save(path: Path, array: np.ndarray) -> Path:
    """Write one capture PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array, "RGB").save(path)
    return path


def run_dir(root: Path, name: str, headings: dict[str, np.ndarray]) -> Path:
    """Write a capture run in the layout the capture script produces."""
    for heading, array in headings.items():
        save(root / name / "spawn_headings" / ("spawn_%s.png" % heading), array)
    return root / name


class TestImageMetrics:
    def test_black_fraction_counts_only_background(self):
        image = frame(4, 4, 8)
        assert black_fraction(image) == pytest.approx(1.0)
        image[0:2] = 200
        assert black_fraction(image) == pytest.approx(0.5)

    def test_black_threshold_is_inclusive_below(self):
        image = np.full((1, 4, 3), 19, dtype=np.uint8)
        image[0, 0] = 20
        assert black_fraction(image, threshold=20) == pytest.approx(0.75)

    def test_changed_stats_split_dark_and_bright_moves(self):
        before = frame(10, 10, 8)
        after = before.copy()
        after[0:2, 0:5] = 200  # 10 pixels dark -> bright
        after[5:7, 0:5] = 8  # unchanged
        after[8, 0:5] = 30  # delta 22 is below the threshold: not a change
        stats = changed_stats(before, after, threshold=32, black_threshold=20)
        assert stats["changed_pct"] == pytest.approx(10.0)
        assert stats["went_bright_pct"] == pytest.approx(10.0)
        assert stats["went_dark_pct"] == pytest.approx(0.0)

    def test_went_dark_is_measured_from_the_before_frame(self):
        before = frame(10, 10, 200)
        after = before.copy()
        after[0:4, :] = 8
        stats = changed_stats(before, after)
        assert stats["went_dark_pct"] == pytest.approx(40.0)
        assert stats["changed_pct"] == pytest.approx(40.0)

    def test_changes_at_or_below_the_threshold_are_noise(self):
        before = frame(2, 2, 100)
        after = before.copy()
        after[0, 0] = 132  # delta 32 is not > 32
        assert changed_stats(before, after, threshold=32)["changed_pct"] == 0.0

    def test_mismatched_shapes_are_rejected(self):
        with pytest.raises(ValueError):
            changed_stats(frame(4, 4, 0), frame(4, 5, 0))


class TestCompareRuns:
    def test_headings_are_matched_by_name(self, tmp_path):
        dark = frame(8, 8, 8)
        bright = frame(8, 8, 200)
        left = run_dir(tmp_path, "before", {"n": dark, "s": dark})
        right = run_dir(tmp_path, "after", {"n": bright, "s": dark})
        result = compare_runs(left, right)
        assert result["spawn_s.png"]["black_left_pct"] == pytest.approx(100.0)
        assert result["spawn_s.png"]["changed_pct"] == 0.0
        assert result["spawn_n.png"]["black_right_pct"] == 0.0
        assert result["spawn_n.png"]["went_dark_pct"] == 0.0
        assert result["spawn_n.png"]["went_bright_pct"] == pytest.approx(100.0)

    def test_a_missing_heading_is_an_error(self, tmp_path):
        big = frame(8, 8, 8)
        left = run_dir(tmp_path, "before", {"n": big, "w": big})
        right = run_dir(tmp_path, "after", {"n": big})
        with pytest.raises(ValueError):
            compare_runs(left, right)

    def test_an_empty_run_is_an_error(self, tmp_path):
        left = run_dir(tmp_path, "before", {"n": frame(8, 8, 8)})
        (tmp_path / "after").mkdir()
        with pytest.raises(FileNotFoundError):
            compare_runs(left, tmp_path / "after")


class TestFloaterStats:
    def test_label_components_finds_shapes_and_separates_them(self):
        mask = np.zeros((6, 6), dtype=bool)
        mask[1, 1] = True  # speck A
        mask[4:6, 4] = True  # speck B (diagonal of A does not merge)
        mask[0:2, 3] = True  # touches the top border
        labels = render_metrics.label_components(mask)
        assert labels.max() == 3
        assert labels[1, 1] != labels[4, 4]
        assert labels[1, 1] != labels[0, 3]
        # background stays 0 and every run pixel is labelled
        assert (labels[3, :] == 0).all()
        assert labels[1, 1] > 0 and labels[5, 4] > 0

    def test_diagonal_pixels_are_not_one_component(self):
        mask = np.zeros((4, 4), dtype=bool)
        mask[1, 1] = True
        mask[2, 2] = True  # 4-connectivity: a corner touch is two components
        labels = render_metrics.label_components(mask)
        assert labels[1, 1] != labels[2, 2]

    def test_border_component_and_main_structure_are_not_floaters(self):
        image = frame(40, 40, 8)
        image[:, 0:6] = 200  # left wall: the largest component, touches border
        image[10:20, 10:20] = 200  # a 100 px island in the void: a floater
        stats = render_metrics.floater_stats(image)
        assert stats["floater_blobs"] == 1
        assert stats["floater_px"] == 100
        assert stats["floater_largest_px"] == 100

    def test_smaller_than_min_px_is_speckle_not_a_floater(self):
        image = frame(40, 40, 8)
        image[0, :] = 200  # main structure along the top border
        image[20:23, 20:23] = 200  # 9 px < FLOATER_MIN_PX
        stats = render_metrics.floater_stats(image, min_px=100)
        assert stats["floater_blobs"] == 0
        assert stats["floater_px"] == 0

    def test_a_border_touching_blob_is_structure_not_a_floater(self):
        image = frame(40, 40, 8)
        image[0:4, 0:4] = 200  # corner of the wall: touches two borders
        stats = render_metrics.floater_stats(image)
        assert stats["floater_blobs"] == 0

    def test_an_empty_void_reports_zero(self):
        stats = render_metrics.floater_stats(frame(8, 8, 8))
        assert stats == {"floater_px": 0, "floater_blobs": 0, "floater_largest_px": 0}


class TestBuildReport:
    def test_report_carries_deltas_thresholds_and_means(self, tmp_path):
        dark = frame(8, 8, 8)
        bright = frame(8, 8, 200)
        left = run_dir(tmp_path, "before", {"n": dark, "s": dark})
        right = run_dir(tmp_path, "after", {"n": bright, "s": dark})
        report = build_report(left, right, repeat_dir=None, threshold=32, black_threshold=20)
        north = report["headings"]["spawn_n.png"]
        assert north["black_before_pct"] == pytest.approx(100.0)
        assert north["black_after_pct"] == 0.0
        assert north["black_delta_pct"] == pytest.approx(-100.0)
        assert north["went_dark_pct"] == 0.0
        south = report["headings"]["spawn_s.png"]
        assert south["black_after_pct"] == pytest.approx(100.0)
        assert south["changed_pct"] == 0.0
        assert report["thresholds"] == {"black": 20, "changed": 32}
        assert "mean" in report
        assert north["before_floater_px"] == 0
        assert north["after_floater_px"] == 0
        assert "noise_floor" not in report

    def test_report_carries_per_heading_and_mean_floater_counts(self, tmp_path):
        def with_blob(value: int) -> np.ndarray:
            image = frame(40, 40, 8)
            image[:, 0:6] = 200  # wall: largest component, touches the border
            if value:
                image[20:30, 20:30] = 200  # 100 px floater
            return image

        left = run_dir(tmp_path, "before", {"n": with_blob(1)})
        right = run_dir(tmp_path, "after", {"n": with_blob(0)})
        report = build_report(left, right, repeat_dir=None, threshold=32, black_threshold=20)
        north = report["headings"]["spawn_n.png"]
        assert north["before_floater_px"] == 100
        assert north["before_floater_blobs"] == 1
        assert north["after_floater_px"] == 0
        assert north["after_floater_blobs"] == 0
        assert report["mean"]["before_floater_px"] == 100
        assert report["mean"]["after_floater_px"] == 0
        assert report["mean"]["before_floater_blobs"] == 1

    def test_repeat_capture_adds_a_measured_noise_floor(self, tmp_path):
        dark = frame(8, 8, 8)
        left = run_dir(tmp_path, "before", {"n": dark})
        right = run_dir(tmp_path, "after", {"n": frame(8, 8, 200)})
        repeat = run_dir(tmp_path, "before_repeat", {"n": dark})
        report = build_report(left, right, repeat_dir=repeat, threshold=32, black_threshold=20)
        assert report["noise_floor"]["max_changed_pct"] == 0.0
        assert report["noise_floor"]["headings"]["spawn_n.png"]["changed_pct"] == 0.0
        assert report["noise_floor"]["mean_floater_px"] == 0.0

    def test_cli_writes_the_json_and_prints_the_table(self, tmp_path, capsys):
        big = frame(8, 8, 8)
        left = run_dir(tmp_path, "before", {"n": big})
        right = run_dir(tmp_path, "after", {"n": frame(8, 8, 200)})
        out = tmp_path / "metrics.json"
        code = render_metrics.main(
            ["--before", str(left), "--after", str(right), "--out", str(out)]
        )
        assert code == 0
        assert out.exists()
        assert "spawn_n.png" in capsys.readouterr().out
