#!/usr/bin/env python3
"""Tests for the bounded-sampling modules: budgets, metrics, selection, plans.

These cover the pure-numpy parts of the gate. Decoding is exercised separately in
``test_capture_fixtures.py`` against generated clips, because a decode test needs
ffmpeg and a clip, and a unit test that needs both stops being a unit test.

Run from ``scripts/splat_pipeline``:
    python3 -m pytest tests/test_capture_gate.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camera_path import build_camera_path, distance_between, integration_gap
from candidate_scan import CandidateFrame
from frame_metrics import (
    TranslationEstimate,
    estimate_translation,
    histogram_distance,
    intensity_histogram,
    is_scene_cut,
    laplacian_variance,
    pool_mean,
    residual_fractions,
    residual_map,
)
from frame_selection import (
    REASON_BLUR,
    REASON_CUT,
    REASON_OVER_BUDGET,
    REASON_REDUNDANT,
    select_frames,
    sharpness_reference,
)
from geometry_consistency import (
    CONSISTENT,
    INCOHERENT,
    MOVING_CONTENT,
    UNMEASURED,
    classify_consistency,
)
from matching_plan import (
    STRATEGY_RETRIEVAL,
    build_plan,
    choose_keyframe_count,
    exhaustive_pairs,
    retrieval_pairs,
    sequential_pairs,
)
from sampling_budget import (
    BudgetError,
    SamplingBudget,
    choose_decode_mode,
    decode_costs,
    estimated_analysis_bytes,
    from_env,
    hypothesis_range,
    load_json,
)
from view_coverage import measure_coverage

TRANSLATION_WIDTH = 64


def make_translation(dx: int, dy: int = 0, width: int = TRANSLATION_WIDTH) -> TranslationEstimate:
    return TranslationEstimate(
        dx_px=dx,
        dy_px=dy,
        frame_width_px=width,
        change_before_px=40.0,
        change_after_px=2.0,
        residual_fraction=0.05,
        hot_block_fraction=0.02,
    )


def make_candidate(
    index: int,
    dx: int | None = 4,
    sharpness: float = 100.0,
    is_cut: bool = False,
    cut_distance: float = 0.02,
    hot_block_fraction: float = 0.02,
    residual_fraction: float = 0.05,
) -> CandidateFrame:
    translation = None if dx is None else make_translation(dx)
    if translation is not None:
        translation = TranslationEstimate(
            dx_px=translation.dx_px,
            dy_px=translation.dy_px,
            frame_width_px=TRANSLATION_WIDTH,
            change_before_px=40.0,
            change_after_px=40.0 * residual_fraction,
            residual_fraction=residual_fraction,
            hot_block_fraction=hot_block_fraction,
        )
    return CandidateFrame(
        index=index,
        timestamp=index / 24.0,
        sharpness=sharpness,
        luma=120.0,
        cut_distance=cut_distance,
        is_cut=is_cut,
        cut_signal="fixture cut" if is_cut else "",
        translation=translation,
    )


# --------------------------------------------------------------------------
# frame_metrics
# --------------------------------------------------------------------------


def test_laplacian_variance_scores_a_flat_frame_as_zero():
    flat = np.full((64, 64), 120, dtype=np.uint8)
    assert laplacian_variance(flat) == 0.0


def test_laplacian_variance_is_higher_for_a_sharper_frame():
    rng = np.random.default_rng(4)
    soft = rng.normal(120, 6, (64, 64))
    hard = rng.normal(120, 45, (64, 64))
    assert laplacian_variance(hard.astype(np.uint8)) > laplacian_variance(soft.astype(np.uint8))


def test_pool_mean_reduces_by_the_pooling_factor_and_drops_the_remainder():
    frame = np.arange(16, dtype=np.uint8).reshape(4, 4)
    pooled = pool_mean(frame, 2)
    assert pooled.shape == (2, 2)
    # Integer mean, matching the int16 result the alignment search compares in.
    assert pooled[0, 0] == int(frame[:2, :2].mean())


def test_pool_mean_drops_a_ragged_trailing_row():
    frame = np.arange(15, dtype=np.uint8).reshape(5, 3)
    assert pool_mean(frame, 2).shape == (2, 1)


def test_estimate_translation_recovers_a_known_horizontal_shift():
    rng = np.random.default_rng(11)
    first = rng.integers(0, 256, (80, 160), dtype=np.uint8)
    second = np.roll(first, -6, axis=1)
    estimate = estimate_translation(first, second, (6, 0))
    assert estimate.dx_px == 6
    assert estimate.dy_px == 0


def test_estimate_translation_reports_a_low_residual_for_a_pure_translation():
    rng = np.random.default_rng(12)
    first = rng.integers(0, 256, (80, 160), dtype=np.uint8)
    estimate = estimate_translation(first, np.roll(first, -5, axis=1), (5, 0))
    assert estimate.residual_fraction < 0.1
    assert estimate.explained_fraction > 0.9


def test_estimate_translation_stays_within_a_frame_of_a_seed_near_the_edge():
    """A seed past the frame edge must not index outside the overlap.

    Regression: the search used to take the mean of an empty slice, which numpy
    reports as NaN and which made the whole gate die on a 720p capture.
    """
    rng = np.random.default_rng(13)
    first = rng.integers(0, 256, (48, 96), dtype=np.uint8)
    second = np.roll(first, -3, axis=1)
    estimate = estimate_translation(first, second, (90, 40))
    assert abs(estimate.dx_px) <= 95
    assert abs(estimate.dy_px) <= 47
    assert np.isfinite(estimate.residual_fraction)


def test_magnitude_fraction_is_relative_to_frame_width():
    assert make_translation(8, 0, width=TRANSLATION_WIDTH).magnitude_fraction == pytest.approx(0.125)
    assert make_translation(16, 0, width=TRANSLATION_WIDTH * 2).magnitude_fraction == pytest.approx(0.125)


def test_explained_fraction_is_one_when_nothing_changed():
    identical = TranslationEstimate(0, 0, 64, 0.0, 0.0, 0.0, 0.0)
    assert identical.explained_fraction == 1.0


def test_residual_map_marks_the_uncovered_border_as_changed():
    first = np.zeros((20, 20), dtype=np.uint8)
    residual = residual_map(first, first, dx=5, dy=0)
    assert residual.shape == first.shape
    # The 5 columns the shift left uncovered have no counterpart in the second
    # frame, so they are filled with mid-grey and read as a full 128 difference.
    assert residual[0, 0] == 128
    assert residual[0, -1] == 0


def test_residual_fractions_separates_a_localised_change_from_a_global_one():
    localised = np.zeros((48, 48), dtype=np.int16)
    localised[0:24, 0:24] = 100
    pixel_fraction, block_fraction = residual_fractions(localised)
    assert pixel_fraction == pytest.approx(0.25, abs=0.02)
    assert block_fraction < 0.5


def test_histogram_distance_is_zero_for_identical_frames():
    frame = np.full((32, 32), 100, dtype=np.uint8)
    assert histogram_distance(intensity_histogram(frame), intensity_histogram(frame)) == pytest.approx(0.0)


def test_histogram_distance_is_positive_for_disjoint_intensity_ranges():
    dark = np.full((32, 32), 5, dtype=np.uint8)
    bright = np.full((32, 32), 250, dtype=np.uint8)
    assert histogram_distance(intensity_histogram(dark), intensity_histogram(bright)) == pytest.approx(2.0)


def test_is_scene_cut_fires_past_the_limit_only():
    dark = np.full((32, 32), 5, dtype=np.uint8)
    bright = np.full((32, 32), 250, dtype=np.uint8)
    assert is_scene_cut(intensity_histogram(dark), intensity_histogram(dark), 0.15) is False
    assert is_scene_cut(intensity_histogram(dark), intensity_histogram(bright), 0.15) is True


# --------------------------------------------------------------------------
# camera_path
# --------------------------------------------------------------------------


def test_integration_gap_never_exceeds_the_candidate_count():
    assert integration_gap(1, 4) == 1
    assert integration_gap(3, 4) == 2
    assert integration_gap(10, 4) == 4


def test_build_camera_path_accumulates_translations_into_travel():
    candidates = tuple(make_candidate(index, dx=5) for index in range(5))
    path = build_camera_path(candidates, gap=1)
    assert path.total_pixels == pytest.approx(20.0)


def test_build_camera_path_zeroes_a_single_candidate():
    path = build_camera_path((make_candidate(0, dx=5),), gap=1)
    assert path.total_pixels == 0.0


def test_build_camera_path_resets_at_a_scene_cut():
    candidates = (
        make_candidate(0, dx=5),
        make_candidate(1, dx=5),
        make_candidate(2, dx=5, is_cut=True),
        make_candidate(3, dx=5),
    )
    path = build_camera_path(candidates, gap=1)
    assert path.positions[2] == (0.0, 0.0)
    assert path.distances[3] == pytest.approx(5.0)


def test_distance_between_is_absolute_along_the_path():
    candidates = tuple(make_candidate(index, dx=5) for index in range(4))
    path = build_camera_path(candidates, gap=1)
    assert distance_between(path, 0, 3) == pytest.approx(15.0)
    assert distance_between(path, 3, 0) == pytest.approx(15.0)


# --------------------------------------------------------------------------
# sampling_budget
# --------------------------------------------------------------------------


def test_default_budget_sits_inside_the_small_room_hypothesis():
    low, high = hypothesis_range()
    assert low == 100 and high == 200
    assert low <= SamplingBudget().target_frames <= high


def test_budget_hypothesis_note_flags_a_target_outside_the_range():
    note = SamplingBudget(target_frames=400).hypothesis_note(400)
    assert "OUTSIDE" in note
    assert "not as a guarantee" in note


def test_budget_hypothesis_note_is_quiet_inside_the_range():
    note = SamplingBudget(target_frames=150).hypothesis_note(120)
    assert "OUTSIDE" not in note
    assert "starting point, not a guarantee" in note


@pytest.mark.parametrize(
    "override",
    [
        {"target_frames": 0},
        {"max_candidates": -1},
        {"analysis_max_pixels": 0},
        {"max_sample_seconds": 0},
        {"target_shift_fraction": 0.0},
        {"decode_mode": "guess"},
    ],
)
def test_budget_rejects_an_unusable_configuration(override):
    with pytest.raises(BudgetError):
        SamplingBudget().with_overrides(**override)


def test_with_overrides_rejects_an_unknown_field():
    with pytest.raises(BudgetError, match="unknown budget fields"):
        SamplingBudget().with_overrides(nonsense=3)


def test_from_env_applies_a_prefixed_override(monkeypatch):
    monkeypatch.setenv("SPLAT_SAMPLE_TARGET_FRAMES", "42")
    assert from_env().target_frames == 42


def test_from_env_rejects_a_non_numeric_override(monkeypatch):
    monkeypatch.setenv("SPLAT_SAMPLE_TARGET_FRAMES", "many")
    with pytest.raises(BudgetError):
        from_env()


def test_load_json_sets_one_field_and_keeps_the_others(tmp_path):
    path = tmp_path / "budget.json"
    path.write_text('{"target_frames": 60}', encoding="utf-8")
    budget = load_json(path)
    assert budget.target_frames == 60
    assert budget.max_candidates == SamplingBudget().max_candidates


def test_load_json_rejects_an_unknown_key(tmp_path):
    path = tmp_path / "budget.json"
    path.write_text('{"nonsense": 1}', encoding="utf-8")
    with pytest.raises(BudgetError, match="unknown keys"):
        load_json(path)


def test_load_json_rejects_a_non_object_document(tmp_path):
    path = tmp_path / "budget.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(BudgetError, match="JSON object"):
        load_json(path)


def test_load_json_rejects_malformed_json(tmp_path):
    path = tmp_path / "budget.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(BudgetError, match="not valid JSON"):
        load_json(path)


def test_decode_costs_report_both_strategies():
    costs = decode_costs(clip_frames=900, candidate_count=150)
    assert set(costs) == {"stream", "seek"}


def test_stream_decode_wins_on_a_clip_sampled_densely():
    # Streaming decodes 900 frames at ~2 ms each; seeking would pay 140 ms for
    # each of 150 frames. On a densely-sampled clip streaming is far cheaper.
    costs = decode_costs(clip_frames=900, candidate_count=150)
    assert costs["stream"] < costs["seek"]
    mode, reason = choose_decode_mode(SamplingBudget(), clip_frames=900, candidate_count=150)
    assert mode == "stream"
    assert "auto chose stream" in reason


def test_seek_decode_wins_on_a_very_long_clip_sampled_sparsely():
    # The crossover: streaming costs clip_frames * 2 ms, seeking costs
    # candidates * 140 ms, so seeking wins once the clip is ~70x the candidates.
    long_clip = 150 * 100
    costs = decode_costs(clip_frames=long_clip, candidate_count=150)
    assert costs["seek"] < costs["stream"]
    mode, _ = choose_decode_mode(SamplingBudget(), clip_frames=long_clip, candidate_count=150)
    assert mode == "seek"


def test_choose_decode_mode_honours_an_explicit_setting():
    mode, reason = choose_decode_mode(SamplingBudget(decode_mode="stream"), 900, 150)
    assert mode == "stream"
    assert "configured explicitly" in reason


def test_estimated_analysis_bytes_is_one_byte_per_pixel():
    assert estimated_analysis_bytes(10, 1000) == 10_000


# --------------------------------------------------------------------------
# frame_selection
# --------------------------------------------------------------------------


def test_sharpness_reference_is_the_ninety_fifth_of_the_ordered_values():
    candidates = tuple(make_candidate(index, sharpness=float(index)) for index in range(11))
    assert sharpness_reference(candidates) == pytest.approx(9.0)


def test_selection_keeps_a_continuously_translating_walk():
    candidates = tuple(make_candidate(index, dx=6) for index in range(20))
    result = select_frames(candidates, TRANSLATION_WIDTH, target_frames=20, min_sharpness_ratio=0.35,
                           min_shift_fraction=0.005)
    assert result.count == 20
    assert result.exclusions == ()


def test_selection_drops_a_frame_that_moved_less_than_the_minimum():
    candidates = (
        make_candidate(0, dx=6),
        make_candidate(1, dx=6),
        make_candidate(2, dx=0),
        make_candidate(3, dx=6),
    )
    result = select_frames(candidates, TRANSLATION_WIDTH, target_frames=10, min_sharpness_ratio=0.35,
                           min_shift_fraction=0.05)
    assert [exclusion.index for exclusion in result.exclusions] == [2]
    assert result.exclusions[0].reason == REASON_REDUNDANT


def test_selection_excludes_a_frame_beside_a_cut():
    candidates = (
        make_candidate(0, dx=6),
        make_candidate(1, dx=6, is_cut=True),
        make_candidate(2, dx=6),
        make_candidate(3, dx=6),
    )
    result = select_frames(candidates, TRANSLATION_WIDTH, target_frames=10, min_sharpness_ratio=0.35,
                           min_shift_fraction=0.005)
    cut_indices = [exclusion.index for exclusion in result.exclusions if exclusion.reason == REASON_CUT]
    assert 1 in cut_indices
    assert 0 not in result.selected
    assert 1 not in result.selected


def test_selection_drops_a_soft_frame_against_the_clips_own_p90():
    candidates = (
        make_candidate(0, dx=6, sharpness=100.0),
        make_candidate(1, dx=6, sharpness=100.0),
        make_candidate(2, dx=6, sharpness=5.0),
        make_candidate(3, dx=6, sharpness=100.0),
    )
    result = select_frames(candidates, TRANSLATION_WIDTH, target_frames=10, min_sharpness_ratio=0.35,
                           min_shift_fraction=0.005)
    blur = [exclusion.index for exclusion in result.exclusions if exclusion.reason == REASON_BLUR]
    assert blur == [2]


def test_selection_thins_evenly_rather_than_truncating():
    candidates = tuple(make_candidate(index, dx=6) for index in range(40))
    result = select_frames(candidates, TRANSLATION_WIDTH, target_frames=10, min_sharpness_ratio=0.35,
                           min_shift_fraction=0.005)
    assert result.count == 10
    assert result.selected[0] == 0
    assert result.selected[-1] > 30
    over = [exclusion.index for exclusion in result.exclusions if exclusion.reason == REASON_OVER_BUDGET]
    assert len(over) == 30


def test_selection_accounts_for_every_candidate_it_dropped():
    candidates = tuple(make_candidate(index, dx=6 if index % 3 else 0) for index in range(20))
    result = select_frames(candidates, TRANSLATION_WIDTH, target_frames=10, min_sharpness_ratio=0.35,
                           min_shift_fraction=0.05)
    assert result.count + len(result.exclusions) == len(candidates)


# --------------------------------------------------------------------------
# geometry_consistency
# --------------------------------------------------------------------------


def burst_stats(median_residual: float, p90_blocks: float, max_blocks: float = 0.0, pairs: int = 7):
    from candidate_scan import BurstStats

    return BurstStats(
        pairs=pairs,
        windows=3,
        median_residual_fraction=median_residual,
        p90_residual_fraction=median_residual,
        median_hot_block_fraction=p90_blocks,
        p90_hot_block_fraction=p90_blocks,
        max_hot_block_fraction=max_blocks,
        median_shift_fraction=0.01,
    )


def test_consistency_is_consistent_when_one_translation_explains_the_change():
    verdict = classify_consistency(burst_stats(0.03, 0.01))
    assert verdict.classification == CONSISTENT
    assert verdict.rejected is False and verdict.warned is False


def test_consistency_warns_about_a_localised_moving_object():
    verdict = classify_consistency(burst_stats(0.10, 0.12))
    assert verdict.classification == MOVING_CONTENT
    assert verdict.rejected is False
    assert verdict.warned is True


def test_consistency_rejects_a_frame_where_the_whole_frame_changes():
    verdict = classify_consistency(burst_stats(0.73, 1.0, max_blocks=1.0))
    assert verdict.classification == INCOHERENT
    assert verdict.rejected is True


def test_consistency_does_not_claim_to_have_measured_an_empty_probe():
    verdict = classify_consistency(burst_stats(0.0, 0.0, pairs=0))
    assert verdict.classification == UNMEASURED
    assert verdict.rejected is False
    assert "not measured" in verdict.evidence


# --------------------------------------------------------------------------
# matching_plan
# --------------------------------------------------------------------------


def test_exhaustive_pairs_is_the_combination_count():
    assert exhaustive_pairs(5) == 10
    assert exhaustive_pairs(150) == 11175


def test_sequential_pairs_grows_with_the_window():
    # Each frame pairs with up to `window` later neighbours: 9 for a window of 1,
    # 24 for 3 (3+3+3+3+3+3+3+2+1), and the full 45 once the window covers the clip.
    assert sequential_pairs(10, 1) == 9
    assert sequential_pairs(10, 3) == 24
    assert sequential_pairs(10, 100) == 45


def test_sequential_pairs_is_never_more_than_exhaustive():
    for frames in (2, 5, 40, 150):
        for window in (1, 3, 10, 24):
            assert sequential_pairs(frames, window) <= exhaustive_pairs(frames)


def test_retrieval_pairs_counts_non_keyframes_plus_keyframe_pairs():
    # (10-4)*4 + 4*3/2 = 24 + 6
    assert retrieval_pairs(10, 4) == 30


def test_choose_keyframe_count_keeps_a_floor_of_non_keyframes():
    assert choose_keyframe_count(4, 24) == 2
    assert choose_keyframe_count(150, 24) == 24
    assert choose_keyframe_count(2, 24) == 2


def test_plan_is_bounded_and_says_what_it_gives_up():
    plan = build_plan(150)
    assert plan.strategy == STRATEGY_RETRIEVAL
    assert plan.pairs < plan.exhaustive_pairs
    assert plan.reduction_factor > 1
    assert any("revisit" in note for note in plan.unmatched_notes)


def test_plan_for_a_single_frame_says_there_is_no_baseline():
    plan = build_plan(1)
    assert plan.pairs == 0
    assert "no baseline" in " ".join(plan.unmatched_notes)


# --------------------------------------------------------------------------
# view_coverage
# --------------------------------------------------------------------------


def test_coverage_measures_travel_in_frame_widths():
    candidates = tuple(make_candidate(index, dx=4) for index in range(10))
    report = measure_coverage(candidates, tuple(range(10)), TRANSLATION_WIDTH, clip_span_seconds=10.0)
    assert report.path_length_widths == pytest.approx(36 / TRANSLATION_WIDTH)
    assert report.selected_count == 10
    assert report.analysed_count == 10


def test_coverage_of_a_stationary_camera_is_zero_travel_and_no_direction():
    candidates = tuple(make_candidate(index, dx=0) for index in range(10))
    report = measure_coverage(candidates, tuple(range(10)), TRANSLATION_WIDTH, clip_span_seconds=10.0)
    assert report.path_length_widths == pytest.approx(0.0)
    assert report.distinct_directions == 0


def test_viewpoint_efficiency_is_one_when_every_frame_is_a_new_place():
    candidates = tuple(make_candidate(index, dx=64) for index in range(4))
    report = measure_coverage(candidates, (0, 1, 2, 3), TRANSLATION_WIDTH, clip_span_seconds=4.0)
    assert report.viewpoint_efficiency <= 1.0
    assert report.viewpoint_bins >= 1


def test_span_fraction_is_the_share_of_the_clip_the_selection_reaches():
    candidates = tuple(make_candidate(index, dx=4) for index in range(10))
    report = measure_coverage(candidates, (0, 1), TRANSLATION_WIDTH, clip_span_seconds=10.0)
    assert report.span_fraction < 1.0
