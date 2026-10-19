#!/usr/bin/env python3
"""Focused tests for deciding whether splat planes are room boundaries."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import measure_splat_frame


def test_rejects_strong_internal_pair_and_uses_weaker_enclosing_pair(monkeypatch):
    strengths = {0: 12.0, 1: 9.0}
    pairs = {
        0: (SimpleNamespace(offset=0.2), SimpleNamespace(offset=0.4)),
        1: (SimpleNamespace(offset=-3.0), SimpleNamespace(offset=3.0)),
    }
    monkeypatch.setattr(
        measure_splat_frame.splat_geometry,
        "measure_plane_strength",
        lambda _points, _normals, axis: strengths[axis],
    )
    monkeypatch.setattr(
        measure_splat_frame.splat_geometry,
        "measure_plane_pair",
        lambda _points, _normals, axis, _bin_width, _separation: pairs[axis],
    )
    cameras = np.array([[-2.0, -1.0, 0.0], [2.0, 1.0, 0.0]])

    axis, note = measure_splat_frame._width_axis(None, None, 2, cameras, 0.1)

    assert axis == 1
    assert note == ""


def test_reports_internal_pair_when_it_does_not_enclose_camera_path(monkeypatch):
    strengths = {0: 9.0, 1: 0.0}
    monkeypatch.setattr(
        measure_splat_frame.splat_geometry,
        "measure_plane_strength",
        lambda _points, _normals, axis: strengths[axis],
    )
    monkeypatch.setattr(
        measure_splat_frame.splat_geometry,
        "measure_plane_pair",
        lambda *_args: (SimpleNamespace(offset=0.2), SimpleNamespace(offset=0.4)),
    )
    cameras = np.array([[-2.0, 0.0, 0.0], [2.0, 0.0, 0.0]])

    axis, note = measure_splat_frame._width_axis(None, None, 2, cameras, 0.1)

    assert axis == -1
    assert "axis x planes 0.200..0.400" in note
    assert "camera range -2.000..2.000" in note
