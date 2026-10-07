#!/usr/bin/env python3
"""Tests for the #103 candidate cleanup decisions.

The properties that matter for a filter that deletes splats from a shipped
asset:

* every threshold is an explicit parameter (no percentiles, no data-derived
  cuts), so a report can reproduce the kept set by itself;
* each stage's rejected splats are attributed to the first stage that rejects
  them, so the per-stage counts sum to ``input - kept``;
* the multi-view stage demands view counts instead of silently skipping;
* the spatial stage is a property of the input cloud, not of the survivors;
* the same inputs produce the same kept set -- no sampling, no RNG.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_splat_filter.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import splat_components
import splat_filter
from splat_filter import CandidateParams, STAGES, compute_keep_mask


def scene() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return a room-like blob, a floater, and per-splat opacity/extent/views."""
    room = np.array([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [0.0, 0.1, 0.0]])
    floater = np.array([[5.0, 5.0, 5.0]])
    world = np.vstack([room, floater])
    opacity = np.array([0.9, 0.9, 0.01, 0.9])
    extent = np.array([0.05, 0.05, 0.05, 4.0])
    views = np.array([6, 6, 6, 0])
    return world, opacity, extent, views


class TestCandidateParams:
    def test_defaults_disable_every_stage(self):
        params = CandidateParams()
        assert params.stage_enabled() == (False, False, False, False)
        assert params.to_json()["stages"] == []

    def test_negative_thresholds_are_rejected(self):
        with pytest.raises(ValueError):
            CandidateParams(min_views=-1)
        with pytest.raises(ValueError):
            CandidateParams(min_component_splats=-1)
        with pytest.raises(ValueError):
            CandidateParams(min_extent_m=-0.1)

    def test_voxel_pitch_must_be_positive(self):
        with pytest.raises(ValueError):
            CandidateParams(voxel_m=0.0)

    def test_opacity_floor_must_be_below_one(self):
        with pytest.raises(ValueError):
            CandidateParams(min_opacity=1.0)

    def test_extent_band_must_be_ordered(self):
        with pytest.raises(ValueError):
            CandidateParams(min_extent_m=0.4, max_extent_m=0.2)

    def test_stage_enabled_follows_the_recorded_order(self):
        params = CandidateParams(min_views=2, min_component_splats=10, max_extent_m=0.3, min_opacity=0.1)
        assert params.stage_enabled() == (True, True, True, True)
        assert params.to_json()["stages"] == list(STAGES)


class TestKeepMask:
    def test_no_stage_keeps_everything(self):
        world, opacity, extent, views = scene()
        keep, removed = compute_keep_mask(world, opacity, extent, CandidateParams(), views)
        assert keep.all()
        assert removed == {stage: 0 for stage in STAGES}

    def test_views_stage_drops_splats_no_camera_saw(self):
        world, opacity, extent, views = scene()
        keep, removed = compute_keep_mask(world, opacity, extent, CandidateParams(min_views=1), views)
        assert keep.tolist() == [True, True, True, False]
        assert removed == {"views": 1, "component": 0, "extent": 0, "opacity": 0}

    def test_views_stage_without_counts_is_an_error(self):
        world, opacity, extent, _ = scene()
        with pytest.raises(ValueError):
            compute_keep_mask(world, opacity, extent, CandidateParams(min_views=1), None)

    def test_component_stage_drops_the_isolated_floater(self):
        world, opacity, extent, views = scene()
        params = CandidateParams(voxel_m=0.25, min_component_splats=2)
        keep, removed = compute_keep_mask(world, opacity, extent, params, views)
        assert keep.tolist() == [True, True, True, False]
        assert removed["component"] == 1

    def test_extent_and_opacity_stage_attributions_are_disjoint(self):
        world, opacity, extent, views = scene()
        params = CandidateParams(max_extent_m=0.3, min_opacity=0.5)
        keep, removed = compute_keep_mask(world, opacity, extent, params, views)
        # Point 2 is faint, point 3 is giant: each is counted once, by its own stage.
        assert keep.tolist() == [True, True, False, False]
        assert removed == {"views": 0, "component": 0, "extent": 1, "opacity": 1}
        assert sum(removed.values()) == len(keep) - int(keep.sum())

    def test_min_extent_band_drops_subpixel_splats(self):
        world, opacity, extent, views = scene()
        keep, removed = compute_keep_mask(world, opacity, extent, CandidateParams(min_extent_m=0.1), views)
        assert keep.tolist() == [False, False, False, True]
        assert removed["extent"] == 3

    def test_component_membership_comes_from_the_input_cloud(self):
        # The bridge point (no views) is dropped by the views stage, but the two
        # survivors must keep the *input cloud's* component membership: labelling
        # the survivors instead would split the chain and delete them too.
        world = np.array([[0.0, 0.0, 0.0], [0.4, 0.0, 0.0], [0.8, 0.0, 0.0]])
        opacity = np.full(3, 0.9)
        extent = np.full(3, 0.05)
        views = np.array([3, 0, 3])
        params = CandidateParams(min_views=1, voxel_m=0.5, min_component_splats=3)
        keep, removed = compute_keep_mask(world, opacity, extent, params, views)
        assert keep.tolist() == [True, False, True]
        assert removed == {"views": 1, "component": 0, "extent": 0, "opacity": 0}

    def test_shape_mismatch_is_rejected(self):
        params = CandidateParams()
        with pytest.raises(ValueError):
            compute_keep_mask(np.zeros((3, 2)), np.zeros(3), np.zeros(3), params)
        with pytest.raises(ValueError):
            compute_keep_mask(np.zeros((3, 3)), np.zeros(2), np.zeros(3), params)

    def test_repeated_runs_produce_the_same_mask(self):
        world, opacity, extent, views = scene()
        params = CandidateParams(min_views=1, voxel_m=0.25, min_component_splats=2, min_opacity=0.5)
        first, first_counts = compute_keep_mask(world, opacity, extent, params, views)
        second, second_counts = compute_keep_mask(world, opacity, extent, params, views)
        assert np.array_equal(first, second)
        assert first_counts == second_counts


class TestComponentLabelling:
    def test_two_separate_blobs_get_two_labels(self):
        points = np.array([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [5.0, 0.0, 0.0]])
        labels = splat_components.label_components(points, 0.5)
        assert labels[0] == labels[1]
        assert labels[0] != labels[2]

    def test_points_within_one_pitch_are_connected(self):
        points = np.array([[0.0, 0.0, 0.0], [0.4, 0.4, 0.4]])
        assert len(set(splat_components.label_components(points, 0.5).tolist())) == 1

    def test_lowering_the_pitch_can_only_split(self):
        chain = np.array([[i * 0.3, 0.0, 0.0] for i in range(4)])
        coarse = splat_components.label_components(chain, 0.5)
        fine = splat_components.label_components(chain, 0.15)
        assert len(set(coarse.tolist())) == 1
        assert len(set(fine.tolist())) > 1

    def test_labels_are_deterministic(self):
        rng = np.random.default_rng(7)
        points = rng.uniform(-3.0, 3.0, size=(500, 3))
        first = splat_components.label_components(points, 0.4)
        second = splat_components.label_components(points, 0.4)
        assert np.array_equal(first, second)

    def test_component_sizes_sum_to_the_point_count(self):
        points = np.array([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [9.0, 0.0, 0.0]])
        labels = splat_components.label_components(points, 0.5)
        sizes = splat_components.component_sizes(labels)
        assert int(sizes.sum()) == len(points)
        assert sorted(sizes.tolist(), reverse=True) == [2, 1]

    def test_invalid_inputs_are_rejected(self):
        with pytest.raises(ValueError):
            splat_components.label_components(np.zeros((3, 3)), 0.0)
        with pytest.raises(ValueError):
            splat_components.label_components(np.zeros((3, 2)), 0.5)
        with pytest.raises(ValueError):
            splat_components.label_components(np.zeros((0, 3)), 0.5)
        with pytest.raises(ValueError):
            splat_components.component_sizes(np.array([]))
