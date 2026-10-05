#!/usr/bin/env python3
"""Tests for the VGGT resource policy: metadata filtering, frame cap, OOM backoff.

The failure these guard against is a fallback that crashes on the pipeline's
own metadata or OOMs uncontrollably. Both are cheap to get wrong and expensive
to discover during an unattended run, so the policy is tested as pure
functions: the same input must always produce the same attempt, an OOM must
be classified as the one failure a smaller attempt can fix, and a refusal
must name the budget and the setting that would change it.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_vggt_budget.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vggt_budget import (
    DEFAULT_MAX_FRAMES,
    MIN_FRAMES,
    classify_failure,
    evenly_spaced_indices,
    format_refusal,
    is_image_file,
    plan_attempts,
    select_image_files,
    write_refusal,
)


# ---------------------------------------------------------------------------
# Metadata filtering
# ---------------------------------------------------------------------------


class TestMetadataFiltering:
    def test_image_extensions_are_recognised(self):
        for name in ("frame_0001.jpg", "frame_0002.jpeg", "frame_0003.png"):
            assert is_image_file(Path(name))

    def test_filtering_is_case_insensitive(self):
        assert is_image_file(Path("frame_0001.JPG"))
        assert is_image_file(Path("frame_0002.Jpeg"))

    def test_pipeline_metadata_is_not_an_image(self):
        assert not is_image_file(Path("frames.json"))

    def test_other_non_image_files_are_excluded(self):
        for name in ("frames.json", "notes.txt", "thumb.db", "capture_gate.json"):
            assert not is_image_file(Path(name))

    def test_select_image_files_sorts_by_name(self, tmp_path):
        for name in ("frame_0003.png", "frame_0001.jpg", "frames.json", "frame_0002.jpeg"):
            (tmp_path / name).write_text("x")

        selected = select_image_files(tmp_path.iterdir())

        assert [p.name for p in selected] == ["frame_0001.jpg", "frame_0002.jpeg", "frame_0003.png"]

    def test_select_image_files_on_an_empty_directory(self, tmp_path):
        assert select_image_files(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Frame selection
# ---------------------------------------------------------------------------


class TestFrameSelection:
    def test_fewer_frames_than_cap_keeps_everything(self):
        assert evenly_spaced_indices(5, 24) == [0, 1, 2, 3, 4]

    def test_exact_cap_keeps_everything(self):
        assert evenly_spaced_indices(24, 24) == list(range(24))

    def test_over_cap_selects_an_evenly_spaced_subset(self):
        indices = evenly_spaced_indices(50, 5)

        assert indices == [0, 12, 24, 37, 49]

    def test_selection_includes_both_endpoints(self):
        indices = evenly_spaced_indices(100, 7)

        assert indices[0] == 0
        assert indices[-1] == 99

    def test_selection_is_deterministic(self):
        assert evenly_spaced_indices(50, 10) == evenly_spaced_indices(50, 10)

    def test_selection_count_matches_the_cap(self):
        assert len(evenly_spaced_indices(1000, 24)) == 24

    def test_a_single_frame_is_the_first(self):
        assert evenly_spaced_indices(50, 1) == [0]

    def test_zero_frames_selects_nothing(self):
        assert evenly_spaced_indices(0, 24) == []

    def test_a_cap_below_one_is_refused(self):
        with pytest.raises(ValueError):
            evenly_spaced_indices(10, 0)

    def test_a_negative_count_is_refused(self):
        with pytest.raises(ValueError):
            evenly_spaced_indices(-1, 10)


# ---------------------------------------------------------------------------
# Attempt schedule
# ---------------------------------------------------------------------------


class TestAttemptSchedule:
    def test_schedule_starts_at_the_capped_selection(self):
        assert plan_attempts(50, 24, 4) == [24, 12, 6, 4]

    def test_schedule_never_exceeds_the_input(self):
        assert plan_attempts(10, 24, 4) == [10, 5, 4]

    def test_schedule_ends_at_the_floor(self):
        assert plan_attempts(100, 24, 4)[-1] == 4

    def test_a_small_input_is_a_single_attempt(self):
        assert plan_attempts(3, 24, 4) == [3]

    def test_no_frames_is_no_attempts(self):
        assert plan_attempts(0, 24, 4) == []

    def test_floor_above_cap_is_refused(self):
        with pytest.raises(ValueError):
            plan_attempts(50, 4, 24)

    def test_floor_of_one_allows_a_single_frame_attempt(self):
        assert plan_attempts(50, 24, 1) == [24, 12, 6, 3, 1]

    def test_default_cap_is_at_least_the_floor(self):
        assert MIN_FRAMES <= DEFAULT_MAX_FRAMES


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------


class TestFailureClassification:
    def test_a_cuda_out_of_memory_is_an_oom(self):
        output = "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 270.00 MiB."

        assert classify_failure(output) == "oom"

    def test_oom_matching_is_case_insensitive(self):
        assert classify_failure("CUDNN_STATUS_ALLOC_FAILED") == "oom"

    def test_a_non_oom_failure_is_not_retried_with_fewer_frames(self):
        output = "ValueError: No reconstruction can be built with BA"

        assert classify_failure(output) == "other"

    def test_empty_output_is_not_an_oom(self):
        assert classify_failure("") == "other"


# ---------------------------------------------------------------------------
# Bounded refusal
# ---------------------------------------------------------------------------


class TestBoundedRefusal:
    def test_refusal_names_the_budget(self):
        text = format_refusal("CUDA out of memory at 24 frame(s)", "RTX 4070 Ti 12 GiB", "lower VGGT_MAX_FRAMES")

        assert "RTX 4070 Ti 12 GiB" in text

    def test_refusal_names_the_suggested_setting(self):
        text = format_refusal("reason", "budget", "lower VGGT_MAX_FRAMES (currently 24)")

        assert "VGGT_MAX_FRAMES" in text

    def test_refusal_names_the_reason(self):
        text = format_refusal("CUDA out of memory at 4 frame(s)", "budget", "suggested")

        assert "CUDA out of memory" in text

    def test_write_refusal_creates_the_marker_file(self, tmp_path):
        path = write_refusal(tmp_path, "reason", "budget", "suggested")

        assert path.name == "POSE_REFUSED"
        assert path.is_file()
        assert "POSE_REFUSED" in path.read_text()
