#!/usr/bin/env python3
"""Tests for the #107 coverage-clip spec and its overwrite guard.

These exercise the pure payload/settings logic without a network call or an API
key, so the submitted settings and the coverage cues in the prompt are checked
in CI rather than trusted to a comment.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TESTS_DIR.parent
SCRIPTS_DIR = PIPELINE_DIR.parent
for _path in (PIPELINE_DIR, SCRIPTS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import coverage_clip  # noqa: E402
import generate_coverage_clip  # noqa: E402

IMAGE_URI = "data:image/jpeg;base64,AAAA"


def test_payload_carries_the_requested_settings():
    settings = coverage_clip.GenerationSettings()
    payload = coverage_clip.build_payload(coverage_clip.COVERAGE_PROMPT, settings, IMAGE_URI)

    assert payload["model"] == "google/veo-3.1-lite"
    assert payload["duration"] == 8
    assert payload["resolution"] == "1080p"
    assert payload["aspect_ratio"] == "16:9"
    assert payload["generate_audio"] is False
    assert payload["prompt"] == coverage_clip.COVERAGE_PROMPT


def test_payload_seeds_the_first_frame_from_the_style_image():
    settings = coverage_clip.GenerationSettings()
    payload = coverage_clip.build_payload("prompt", settings, IMAGE_URI)

    assert len(payload["frame_images"]) == 1
    frame = payload["frame_images"][0]
    assert frame["frame_type"] == "first_frame"
    assert frame["image_url"]["url"] == IMAGE_URI


def test_prompt_requires_translation_and_two_travel_directions():
    prompt = coverage_clip.COVERAGE_PROMPT.lower()
    assert "walks forward" in prompt
    assert "sideways" in prompt
    assert "two different directions" in prompt


def test_prompt_requires_the_missing_wall_and_its_joins():
    prompt = coverage_clip.COVERAGE_PROMPT.lower()
    assert "far wall" in prompt
    assert "wall meets the carpeted floor" in prompt
    assert "wall meets the drop ceiling" in prompt


def test_prompt_rejects_cuts_and_pan_only_coverage():
    prompt = coverage_clip.COVERAGE_PROMPT.lower()
    assert "no cuts" in prompt
    assert "unbroken" in prompt
    assert "no people" in prompt


def test_settings_report_retains_prompt_and_model():
    reported = coverage_clip.GenerationSettings().to_dict()
    assert reported["prompt"] == coverage_clip.COVERAGE_PROMPT
    assert reported["model_id"] == "google/veo-3.1-lite"
    assert reported["resolution"] == "1080p"


def test_paths_live_in_the_scene_directory():
    scene = Path("/tmp/scene")
    assert coverage_clip.video_path(scene) == scene / "video.mp4"
    assert coverage_clip.report_path(scene) == scene / "generation.json"


def test_cli_refuses_to_overwrite_a_historical_clip(tmp_path):
    scene = tmp_path / "scene"
    scene.mkdir()
    (scene / "video.mp4").write_bytes(b"existing")

    with pytest.raises(SystemExit) as exit_info:
        generate_coverage_clip.main(["--scene-dir", str(scene)])

    assert "refusing to overwrite" in str(exit_info.value)
