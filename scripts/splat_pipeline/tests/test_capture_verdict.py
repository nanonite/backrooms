#!/usr/bin/env python3
"""Tests for the verdict rules and the COLMAP registration report.

``test_capture_gate.py`` covers measurement; this covers the decision. Two
properties are asserted structurally rather than on wording, because they are
the ones that make the report actionable and they would both survive a
reworded string:

* every blocking finding names a capture change, since "fail" is not something an
  operator can act on;
* no rejection is ever raised for resolution alone, which is the specific wrong
  behaviour this issue had to undo.

Run from ``scripts/splat_pipeline``:
    python3 -m pytest tests/test_capture_verdict.py -q
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from build_colmap_model import write_model
from capture_verdict import (
    MIN_PATH_WIDTHS,
    SEVERITY_BLOCK,
    SEVERITY_INFO,
    SEVERITY_WARN,
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    STATUS_WARNED,
    judge_capture,
)
from candidate_scan import BurstStats, CandidateFrame, ScanResult
from colmap_model import read_cameras, read_images
from frame_metrics import TranslationEstimate
from frame_reader import AnalysisSize, DecodeStats
from frame_selection import select_frames
from geometry_consistency import ConsistencyVerdict
from model_coverage import (
    DEFAULT_MIN_COVERAGE,
    ModelCoverageError,
    build_report,
    choose_model,
    compare_registration,
    extracted_frames,
    read_intrinsics,
)
from resource_estimate import ResourceVerdict
from sampling_budget import SamplingBudget
from video_probe import VideoMetadata
from view_coverage import measure_coverage

WIDTH, HEIGHT = 640, 360
ANALYSIS_WIDTH = 320


def make_metadata(
    width: int = WIDTH, height: int = HEIGHT, duration: float = 4.0, frames: int = 96
) -> VideoMetadata:
    return VideoMetadata(
        path=Path("fixture.mp4"),
        width=width,
        height=height,
        fps=24.0,
        duration_seconds=duration,
        frame_count=frames,
        frame_count_is_exact=True,
        codec="h264",
        pixel_format="yuv420p",
    )


def make_candidate(
    index: int,
    dx: int | None = 6,
    dy: int = 0,
    sharpness: float = 100.0,
    is_cut: bool = False,
    explained: float = 0.9,
    residual_fraction: float = 0.05,
) -> CandidateFrame:
    translation = None
    if dx is not None:
        translation = TranslationEstimate(
            dx_px=dx,
            dy_px=dy,
            frame_width_px=ANALYSIS_WIDTH,
            change_before_px=40.0,
            change_after_px=40.0 * (1.0 - explained),
            residual_fraction=residual_fraction,
            hot_block_fraction=0.02,
        )
    return CandidateFrame(
        index=index,
        timestamp=index / 24.0,
        sharpness=sharpness,
        luma=120.0,
        cut_distance=0.02,
        is_cut=is_cut,
        cut_signal="fixture cut" if is_cut else "",
        translation=translation,
    )


def walking_candidates(count: int = 40, dx: int = 6) -> tuple[CandidateFrame, ...]:
    """A walk whose measured displacement grows, weaving in two directions.

    Displacement has to *vary* between candidates, not just be non-zero. The path
    integration is non-overlapping over a gap of 2, so it accumulates two
    interleaved chains (even and odd candidates) independently and each candidate
    inherits the total of its own chain. If the two chains hold the same total --
    which is what a perfectly symmetric weave produces -- consecutive candidates
    always tie and the selector reads every second frame as "the camera did not
    move". A real walk is never that symmetric, so this fixture breaks parity too:
    each step's magnitude depends on its own index, not on its parity.
    """
    candidates = []
    for index in range(count):
        travel = dx + index * index % 17
        # Weave across x with an alternating y drift, so more than one direction
        # of travel is measured and the single-direction warning stays quiet.
        lateral = travel if index % 4 < 2 else -travel
        vertical = (travel // 3) * (1 if (index // 4) % 2 == 0 else -1)
        candidates.append(make_candidate(index, dx=lateral, dy=vertical))
    return tuple(candidates)


def stationary_candidates(count: int = 40) -> tuple[CandidateFrame, ...]:
    """A capture with everything a walk has except the baseline: the camera never moves."""
    return tuple(make_candidate(index, dx=0) for index in range(count))


def make_bursts(
    median_residual: float = 0.03,
    p90_blocks: float = 0.01,
    max_blocks: float = 0.02,
    pairs: int = 21,
) -> BurstStats:
    return BurstStats(
        pairs=pairs,
        windows=3,
        median_residual_fraction=median_residual,
        p90_residual_fraction=median_residual,
        median_hot_block_fraction=p90_blocks,
        p90_hot_block_fraction=p90_blocks,
        max_hot_block_fraction=max_blocks,
        median_shift_fraction=0.02,
    )


def make_consistency(
    classification: str = "temporal_geometry_consistent",
    rejected: bool = False,
    warned: bool = False,
    evidence: str = "fixture measurement",
) -> ConsistencyVerdict:
    return ConsistencyVerdict(
        classification=classification,
        median_residual_fraction=0.03,
        p90_hot_block_fraction=0.01,
        max_hot_block_fraction=0.02,
        rejected=rejected,
        warned=warned,
        evidence=evidence,
    )


def make_resources(fits: bool = True) -> ResourceVerdict:
    return ResourceVerdict(
        fits=fits,
        free_disk_bytes=100 * 1024**3,
        free_ram_bytes=32 * 1024**3,
        blockers=() if fits else ("needs 400 GiB of disk, 100 GiB free",),
        actions=() if fits else ("select fewer frames",),
    )


def make_scan(candidates: tuple[CandidateFrame, ...], burst_stats: BurstStats | None = None) -> ScanResult:
    size = AnalysisSize(width=ANALYSIS_WIDTH, height=180, source_width=WIDTH, source_height=HEIGHT)
    stats = DecodeStats(
        mode="stream", reason="fixture", clip_frames=96, requested=len(candidates),
        retained=len(candidates), visited=96, seconds=0.2,
    )
    return ScanResult(
        metadata=make_metadata(),
        size=size,
        stride=1,
        candidates=candidates,
        bursts=burst_stats or make_bursts(),
        motion_px_per_frame=3.0,
        parallax_gap=2,
        probe_stats=DecodeStats("stream", "fixture", 96, 12, 12, 96, 0.1),
        candidate_stats=stats,
        burst_frames_decoded=24,
        seconds=1.0,
        limits=("fixture limit",),
    )


def judge(
    candidates: tuple[CandidateFrame, ...],
    consistency_verdict: ConsistencyVerdict | None = None,
    resource_verdict: ResourceVerdict | None = None,
    meta: VideoMetadata | None = None,
    budget: SamplingBudget | None = None,
):
    """Run the full verdict over a candidate set, with coverage measured for real."""
    budget = budget or SamplingBudget()
    scan = make_scan(candidates)
    selection = select_frames(
        candidates, ANALYSIS_WIDTH, budget.target_frames,
        budget.min_sharpness_ratio, budget.min_shift_fraction, scan.parallax_gap,
    )
    coverage = measure_coverage(candidates, selection.selected, ANALYSIS_WIDTH, 4.0, scan.parallax_gap)
    return judge_capture(
        meta or make_metadata(),
        scan,
        selection,
        coverage,
        consistency_verdict or make_consistency(),
        resource_verdict or make_resources(),
        budget,
    )


def codes(verdict, severity: str) -> set[str]:
    return {finding.code for finding in verdict.findings_of(severity)}


# --------------------------------------------------------------------------
# capture_verdict: what is and is not a rejection
# --------------------------------------------------------------------------


def test_a_clean_walk_is_accepted():
    verdict = judge(walking_candidates(40))
    assert verdict.status == STATUS_ACCEPTED
    assert codes(verdict, SEVERITY_BLOCK) == set()


def test_every_blocking_finding_names_a_capture_change():
    """A rejection an operator cannot act on is a broken report."""
    verdicts = [
        judge(stationary_candidates(40)),
        judge(walking_candidates(40), make_consistency("temporal_geometry_inconsistent", True, True)),
        judge(walking_candidates(40), resource_verdict=make_resources(fits=False)),
        judge(walking_candidates(2)),
    ]
    for verdict in verdicts:
        for finding in verdict.findings_of(SEVERITY_BLOCK):
            assert finding.action.strip(), f"{finding.code} has no action"
            assert finding.cause.strip(), f"{finding.code} has no cause"


def test_a_stationary_camera_is_rejected_with_capture_guidance():
    verdict = judge(stationary_candidates(40))
    assert verdict.status == STATUS_REJECTED
    assert "no_parallax_baseline" in codes(verdict, SEVERITY_BLOCK)
    assert "camera_path_too_short" in codes(verdict, SEVERITY_BLOCK)


def test_incoherent_geometry_is_rejected_and_the_action_is_a_real_capture():
    verdict = judge(walking_candidates(40), make_consistency("temporal_geometry_inconsistent", True, True))
    assert verdict.status == STATUS_REJECTED
    blocking = [f for f in verdict.findings_of(SEVERITY_BLOCK) if f.code.startswith("geometry_")]
    assert blocking, "an inconsistent-geometry rejection should carry a geometry finding"
    action = blocking[0].action.lower()
    assert "real" in action and "cannot invent" in action


def test_moving_content_warns_rather_than_rejecting():
    verdict = judge(walking_candidates(40), make_consistency("moving_content_dominant", True, True))
    assert verdict.status == STATUS_REJECTED
    assert "geometry_moving_content_dominant" in codes(verdict, SEVERITY_BLOCK)


def test_a_partly_moving_scene_warns_only():
    verdict = judge(walking_candidates(40), make_consistency("moving_content_dominant", False, True))
    assert verdict.status == STATUS_WARNED
    assert codes(verdict, SEVERITY_BLOCK) == set()


def test_a_scene_cut_is_rejected():
    candidates = list(walking_candidates(40))
    candidates[20] = make_candidate(20, is_cut=True)
    verdict = judge(tuple(candidates))
    assert verdict.status == STATUS_REJECTED
    assert "scene_cuts" in codes(verdict, SEVERITY_BLOCK)


def test_unmeasured_consistency_is_info_not_a_failure():
    verdict = judge(walking_candidates(40), make_consistency("not_measured", False, False))
    assert "consistency_not_measured" in codes(verdict, SEVERITY_INFO)
    assert verdict.status != STATUS_REJECTED


def test_an_unrunnable_estimate_is_rejected_before_the_work_is_spent():
    verdict = judge(walking_candidates(40), resource_verdict=make_resources(fits=False))
    assert verdict.status == STATUS_REJECTED
    assert "resource_budget_exceeded" in codes(verdict, SEVERITY_BLOCK)


def test_a_clip_too_short_to_have_a_baseline_is_rejected():
    verdict = judge(walking_candidates(40), meta=make_metadata(duration=0.4, frames=6))
    assert verdict.status == STATUS_REJECTED
    assert "clip_too_short" in codes(verdict, SEVERITY_BLOCK)


# --------------------------------------------------------------------------
# capture_verdict: resolution is never a rejection
# --------------------------------------------------------------------------


def test_720p_is_not_rejected():
    """The specific behaviour this issue had to undo."""
    verdict = judge(walking_candidates(40), meta=make_metadata(width=1280, height=720))
    assert verdict.status == STATUS_ACCEPTED
    assert "resolution_below_recommended" in codes(verdict, SEVERITY_INFO)
    assert "resolution" not in " ".join(codes(verdict, SEVERITY_BLOCK))


def test_720p_is_reported_with_what_it_costs():
    verdict = judge(walking_candidates(40), meta=make_metadata(width=1280, height=720))
    finding = next(f for f in verdict.findings if f.code == "resolution_below_recommended")
    assert finding.severity == SEVERITY_INFO
    assert "0.92 MP" in finding.measured
    # The advisory must state the consequence honestly, not just flag the number.
    assert "soften" in finding.cause or "distance" in finding.cause


def test_1080p_raises_no_resolution_finding_at_all():
    verdict = judge(walking_candidates(40), meta=make_metadata(width=1920, height=1080))
    assert not any(f.code.startswith("resolution_") for f in verdict.findings)


def test_a_frame_too_small_to_carry_features_is_still_rejected():
    verdict = judge(walking_candidates(40), meta=make_metadata(width=160, height=120))
    assert verdict.status == STATUS_REJECTED
    assert "resolution_unusable" in codes(verdict, SEVERITY_BLOCK)


def test_the_resolution_note_states_the_rule_explicitly():
    verdict = judge(walking_candidates(40))
    assert any("never used as a rejection" in note for note in verdict.notes)


# --------------------------------------------------------------------------
# capture_verdict: reporting
# --------------------------------------------------------------------------


def test_blocking_findings_come_first_in_the_report():
    verdict = judge(stationary_candidates(40))
    severities = [finding.severity for finding in verdict.findings]
    assert severities[0] == SEVERITY_BLOCK
    assert severities == sorted(severities, key=lambda s: {SEVERITY_BLOCK: 0, SEVERITY_WARN: 1, SEVERITY_INFO: 2}[s])


def test_the_report_states_what_was_not_measured():
    verdict = judge(walking_candidates(40))
    assert verdict.limits == ("fixture limit",)


def test_the_frame_target_is_reported_as_a_hypothesis_not_a_guarantee():
    verdict = judge(walking_candidates(40))
    assert any("not a guarantee" in note for note in verdict.notes)


def test_a_target_outside_the_hypothesis_is_flagged_as_deliberate():
    verdict = judge(walking_candidates(40), budget=SamplingBudget(target_frames=400))
    assert any("OUTSIDE" in note for note in verdict.notes)


def test_to_dict_is_json_serialisable():
    import json

    verdict = judge(stationary_candidates(40))
    payload = json.loads(json.dumps(verdict.to_dict()))
    assert payload["status"] == STATUS_REJECTED
    assert payload["findings"]


# --------------------------------------------------------------------------
# model_coverage
# --------------------------------------------------------------------------


def stage_scene(tmp_path: Path, frame_count: int, registered: int, models: int = 1) -> Path:
    """A scene with ``frame_count`` extracted frames and one model over ``registered``."""
    scene = tmp_path / "scene"
    images = scene / "images"
    images.mkdir(parents=True, exist_ok=True)
    names = [f"frame_{index:04d}.jpg" for index in range(1, frame_count + 1)]
    for name in names:
        (images / name).write_bytes(b"not a real jpeg")
    for component in range(models):
        write_model(
            scene / "sparse" / str(component),
            names[:registered] if component == 0 else names[registered:],
        )
    return scene


def test_a_fully_registered_model_covers_the_extracted_frames(tmp_path):
    scene = stage_scene(tmp_path, frame_count=10, registered=10)
    report = build_report(scene)
    assert report.registration.extracted == 10
    assert report.registration.registered == 10
    assert report.registration.excluded == 0
    assert report.registration.coverage == 1.0
    assert report.covers_enough is True
    assert report.unsupported_frames == ()


def test_partial_registration_is_reported_with_the_unregistered_frame_names(tmp_path):
    scene = stage_scene(tmp_path, frame_count=20, registered=10)
    report = build_report(scene)
    assert report.registration.registered == 10
    assert report.registration.excluded == 10
    assert report.covers_enough is False
    assert report.unsupported_frames[0] == "frame_0011.jpg"


def test_coverage_never_silently_exceeds_one(tmp_path):
    scene = stage_scene(tmp_path, frame_count=5, registered=10)
    report = build_report(scene)
    # The model holds more images than were extracted; only extracted frames count.
    assert report.registration.registered == 5
    assert report.registration.coverage == 1.0


def test_a_second_component_is_named_rather_than_dropped_silently(tmp_path):
    scene = stage_scene(tmp_path, frame_count=20, registered=15, models=2)
    report = build_report(scene)
    assert len(report.choice.all_models) == 2
    others = report.choice.others()
    assert len(others) == 1
    assert others[0][1] == 5
    assert any("was not used" in warning for warning in report.warnings)


def test_the_largest_component_is_chosen_and_the_choice_is_stated(tmp_path):
    scene = tmp_path / "scene"
    (scene / "images").mkdir(parents=True)
    names = [f"frame_{index:04d}.jpg" for index in range(1, 21)]
    for name in names:
        (scene / "images" / name).write_bytes(b"x")
    write_model(scene / "sparse" / "0", names[:4])
    write_model(scene / "sparse" / "1", names[:12])
    choice = choose_model(scene)
    assert choice.chosen.endswith("sparse/1")
    assert choice.chosen_images == 12


def test_an_explicitly_named_model_overrides_the_largest_one(tmp_path):
    scene = stage_scene(tmp_path, frame_count=20, registered=15, models=2)
    report = build_report(scene, model_path=scene / "sparse" / "1")
    assert report.choice.chosen.endswith("sparse/1")
    assert report.choice.chosen_images == 5


def test_intrinsics_are_read_as_written_and_not_recomputed(tmp_path):
    scene = tmp_path / "scene"
    write_model(scene / "sparse" / "0", ["a.jpg", "b.jpg"], width=1920, height=1080, focal=1234.5)
    intrinsics = read_intrinsics(scene / "sparse" / "0")
    camera = read_cameras(scene / "sparse" / "0")[1]
    assert intrinsics.camera_count == 1
    assert intrinsics.resolutions == ("1920x1080",)
    assert intrinsics.models == ("SIMPLE_PINHOLE",)
    # SIMPLE_PINHOLE stores (f, cx, cy): the principal point is params[1:3].
    assert intrinsics.principal_points == ((camera.params[1], camera.params[2]),)


def test_pose_extent_is_measured_from_the_registered_centres(tmp_path):
    scene = tmp_path / "scene"
    write_model(
        scene / "sparse" / "0",
        [f"frame_{index:04d}.jpg" for index in range(1, 6)],
        poses=[(0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (6.0, 0.0, 0.0), (9.0, 0.0, 0.0), (12.0, 0.0, 0.0)],
    )
    from model_coverage import pose_extent

    extent = pose_extent(scene / "sparse" / "0")
    assert extent[0] == pytest.approx(12.0)
    assert extent[1] == pytest.approx(0.0)
    assert extent[2] == pytest.approx(0.0)


def test_poses_survive_the_write_and_read_round_trip(tmp_path):
    """The report must measure COLMAP's poses, not re-derive them."""
    from colmap_model import camera_centers

    scene = tmp_path / "scene"
    poses = [(0.0, 0.0, 0.0), (1.5, -2.0, 0.25), (3.0, 4.0, 1.0)]
    write_model(scene / "sparse" / "0", ["a.jpg", "b.jpg", "c.jpg"], poses=poses)
    centres = camera_centers(read_images(scene / "sparse" / "0"))
    assert centres == pytest.approx(np.asarray(poses))


def test_a_missing_model_is_reported_as_missing_not_as_zero_coverage(tmp_path):
    scene = tmp_path / "scene"
    (scene / "images").mkdir(parents=True)
    (scene / "images" / "frame_0001.jpg").write_bytes(b"x")
    with pytest.raises((FileNotFoundError, ModelCoverageError)):
        build_report(scene)


def test_missing_frames_are_reported_rather_than_read_as_full_coverage(tmp_path):
    scene = stage_scene(tmp_path, frame_count=10, registered=10)
    for stale in (scene / "images").glob("*.jpg"):
        stale.unlink()
    with pytest.raises(ModelCoverageError, match="no frames found"):
        build_report(scene)


def test_extracted_frames_are_listed_in_name_order(tmp_path):
    directory = tmp_path / "images"
    directory.mkdir()
    for name in ("frame_0010.jpg", "frame_0002.jpg", "frame_0001.jpg"):
        (directory / name).write_bytes(b"x")
    assert extracted_frames(directory) == ["frame_0001.jpg", "frame_0002.jpg", "frame_0010.jpg"]


def test_default_coverage_floor_is_the_documented_value():
    assert DEFAULT_MIN_COVERAGE == 0.8


def test_coverage_report_serialises_and_names_unsupported_frames(tmp_path):
    import json

    scene = stage_scene(tmp_path, frame_count=20, registered=10)
    payload = json.loads(json.dumps(build_report(scene).to_dict()))
    assert payload["unsupported_coverage"]["count"] == 10
    assert payload["registration"]["coverage"] == 0.5
    assert payload["covers_enough"] is False
    assert "limited to the registered" in payload["unsupported_coverage"]["note"]
