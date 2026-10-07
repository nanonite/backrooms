#!/usr/bin/env python3
"""Spec for the #107 coverage-complete source clip.

Pure configuration and payload construction: no network, no ffmpeg, no
credentials. The CLI in ``scripts/generate_coverage_clip.py`` submits these
settings to OpenRouter; the tests here exercise the spec without a key.

The prompt is the lever the gate cannot pull for us. The capture gate measures
translation, direction spread and temporal consistency, but it cannot see
whether a wall, a wall/floor join or a wall/ceiling join was ever framed. That
requirement is encoded in the prompt and checked by a human against the sampled
frames, so the prompt text is a first-class artifact, not a comment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Same cost-effective image-to-video model as the historical clips, so the new
#: clip is directly comparable to the ones the gate has already judged.
MODEL_ID = "google/veo-3.1-lite"
BASE_URL = "https://openrouter.ai/api/v1"

#: The model's typical single-take maximum. Longer than the 4 s historical clips
#: because coverage needs time to translate across the room in two directions.
DURATION_SECONDS = 8
RESOLUTION = "1080p"
ASPECT_RATIO = "16:9"

#: Seed image locks the recognizable Backrooms look; the prompt drives motion.
SEED_IMAGE_NAME = "Backrooms_model.jpg"

#: Delivered under data/ (git-ignored, like every other source clip) so no
#: historical asset is touched. The name is versioned for future clips.
DEFAULT_SCENE_DIR = "data/scenes/backrooms_coverage_v1"
VIDEO_NAME = "video.mp4"
REPORT_NAME = "generation.json"

#: The prompt. Every clause maps to a #107 acceptance requirement:
#:   - "one unbroken take ... no cuts"          -> reject cuts
#:   - "walks forward ... then turns and walks  -> meaningful translation,
#:      sideways"                                  >= 2 travel directions
#:   - "faces the far wall ... wall meets floor  -> deliberate views of the
#:      ... wall meets ceiling"                    previously missing wall and
#:                                                 floor/ceiling joins
#:   - "within arm's reach ... parallax"        -> near-field parallax
#:   - "rigid ... stable lighting ... no people" -> temporal consistency
COVERAGE_PROMPT = (
    "Continuous single-take first-person walk through one bounded backrooms room, "
    "eight seconds, one unbroken shot, no cuts, no teleports. The camera body "
    "physically walks forward at a steady pace across the open carpet floor, then "
    "turns smoothly and keeps walking sideways across the room to the opposite "
    "side, so the camera travels in two different directions. While walking it "
    "deliberately faces the far wall of the room and holds it in frame, showing "
    "the whole wall surface including the clean horizontal join where the wall "
    "meets the carpeted floor and the join where the wall meets the drop ceiling. "
    "The camera passes within arm's reach of the side walls and a structural "
    "column, so nearby textured surfaces fill the frame and shift with parallax. "
    "Yellow patterned wallpaper, moist carpet tiles, drop ceiling with recessed "
    "fluorescent light panels. One rigid consistent room, fixed geometry, stable "
    "lighting, sharp focus, no motion blur, no flicker, no people, no windows, "
    "fixed camera lens, photorealistic, liminal backrooms."
)


@dataclass(frozen=True)
class GenerationSettings:
    """Every setting that shaped one generated clip, so it can be reproduced."""

    model_id: str = MODEL_ID
    duration_seconds: int = DURATION_SECONDS
    resolution: str = RESOLUTION
    aspect_ratio: str = ASPECT_RATIO
    generate_audio: bool = False
    seed_image: str = SEED_IMAGE_NAME

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "duration_seconds": self.duration_seconds,
            "resolution": self.resolution,
            "aspect_ratio": self.aspect_ratio,
            "generate_audio": self.generate_audio,
            "seed_image": self.seed_image,
            "prompt": COVERAGE_PROMPT,
        }


def build_payload(prompt: str, settings: GenerationSettings, image_uri: str) -> dict:
    """The exact OpenRouter ``POST /videos`` body for one clip.

    Kept pure so a test can assert the submitted settings without a network
    call, and so a future reader can see precisely what was requested.
    """
    return {
        "model": settings.model_id,
        "prompt": prompt,
        "duration": settings.duration_seconds,
        "resolution": settings.resolution,
        "aspect_ratio": settings.aspect_ratio,
        "generate_audio": settings.generate_audio,
        "frame_images": [
            {
                "type": "image_url",
                "image_url": {"url": image_uri},
                "frame_type": "first_frame",
            }
        ],
    }


def video_path(scene_dir: Path) -> Path:
    return Path(scene_dir) / VIDEO_NAME


def report_path(scene_dir: Path) -> Path:
    return Path(scene_dir) / REPORT_NAME
