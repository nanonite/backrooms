#!/usr/bin/env python3
"""Build the capture fixtures the gate is tested and documented against.

The fixtures are synthetic clips with *known* properties, because the point of
an accepted/rejected pair is that the verdict is reproducible on any machine
without shipping megabytes of footage:

``accepted_walkthrough``
    A camera translating across a static textured scene. One rigid scene, real
    baseline, no cuts, no moving content -- what a real walk-through looks like
    to these metrics.
``accepted_720p``
    The same walk at 1280x720. Included because "reject 720p" is the wrong
    rule, and a fixture is the only way to keep that honest across releases.
``stationary_camera``
    The same scene with a camera that never moves. Everything else is identical,
    so the only thing that changes is the baseline.
``cut_sequence``
    Three unrelated scenes joined by hard cuts.
``moving_content``
    The accepted walk with an object crossing the frame: still reconstructible,
    so the expected verdict is a warning rather than a refusal.
``incoherent_geometry``
    The accepted camera move over detail that is regenerated every frame -- the
    signature measured footage has when no single scene persists.
``long_walkthrough``
    900 frames, used for the bounded-work case: a clip far longer than the frame
    budget, to show that sampling cost does not grow with clip length.

Frames are generated at the fixture's own resolution and never rescaled,
because sharpness and residual thresholds are stated at the analysis
resolution: a fixture that had been upscaled would measure in a different
regime from a real capture.

Usage:
    python3 scripts/splat_pipeline/fixtures/make_capture_fixtures.py [output_dir]
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FIXTURE_FPS = 24

#: Native analysis-resolution size. Matches the gate's default 640x360 analysis
#: frames, so measured sharpness is in the same regime as a 1080p capture
#: downscaled for analysis.
ANALYSIS_SIZE = (640, 360)

#: 720p, the size the gate is explicitly not allowed to refuse.
PHONE_720P_SIZE = (1280, 720)

#: Short clips: 4 seconds, matching the shipped data/videos captures so the
#: gate sees the same clip length in tests as in use.
SHORT_CLIP_FRAMES = 96

#: Long clip: 37.5 seconds -- 9x the short clips and well past any frame
#: target, which is what makes it the bounded-work case.
LONG_CLIP_FRAMES = 900

#: How far the camera window travels across the scene canvas, per axis.
TRAVEL_X = 700
TRAVEL_Y = 120

#: Encoding: CRF 16 keeps fixtures visually close to lossless, so re-encoding
#: artefacts are not mistaken for temporal instability by the burst probe.
CRF = "16"
X264_PRESET = "veryfast"

ACCEPT = "accepted"
WARN = "accepted_with_warnings"
REJECT = "rejected"


class FixtureError(RuntimeError):
    """A fixture could not be built."""


@dataclass(frozen=True)
class Fixture:
    """One generated clip and the property it is meant to exercise."""

    name: str
    frames: int
    size: tuple[int, int]
    expected: str
    property: str

    @property
    def filename(self) -> str:
        return f"{self.name}.mp4"

    @property
    def width(self) -> int:
        return self.size[0]

    @property
    def height(self) -> int:
        return self.size[1]


def bilinear_noise(height: int, width: int, cell: int, rng: np.random.Generator) -> np.ndarray:
    """Smooth value noise in [0, 1): soft gradients without speckle."""
    grid_h = int(np.ceil(height / cell)) + 2
    grid_w = int(np.ceil(width / cell)) + 2
    grid = rng.random((grid_h, grid_w))
    row = np.arange(height) / cell
    column = np.arange(width) / cell
    row0 = np.clip(row.astype(int), 0, grid_h - 2)
    column0 = np.clip(column.astype(int), 0, grid_w - 2)
    smooth_row = (row - row0) * (-(row - row0) + 2)
    smooth_column = (column - column0) * (-(column - column0) + 2)
    top = grid[row0][:, column0] * (1 - smooth_column) + grid[row0][:, column0 + 1] * smooth_column
    bottom = grid[row0 + 1][:, column0] * (1 - smooth_column) + grid[row0 + 1][:, column0 + 1] * smooth_column
    return (top * (1 - smooth_row[:, None]) + bottom * smooth_row[:, None]).astype(np.float64)


def scene_texture(height: int, width: int, seed: int) -> np.ndarray:
    """A static textured scene: shading, hard trim edges, periodic seams.

    Built from the parts a real room provides -- soft shading, sharp edges at
    trim and outlets, repeating wallpaper -- because a feature matcher needs all
    three and a pure gradient would match nothing.
    """
    rng = np.random.default_rng(seed)
    image = 40 + 150 * (0.65 * bilinear_noise(height, width, 14, rng) + 0.35 * bilinear_noise(height, width, 4, rng))
    for _ in range(20):
        top = int(rng.integers(0, height - 30))
        left = int(rng.integers(0, width - 30))
        image[top : top + int(rng.integers(4, 26)), left : left + int(rng.integers(4, 26))] += float(
            rng.integers(-80, 80)
        )
    columns = np.arange(width)[None, :]
    for period in range(26, 61, 7):
        image += 18 * np.sin(columns * (2 * np.pi / period))
    return np.clip(image, 0, 255)


def scene_for(fixture: Fixture) -> np.ndarray:
    """The canvas the camera window travels across, sized for this fixture."""
    scale = fixture.width / ANALYSIS_SIZE[0]
    return scene_texture(
        fixture.height + int(TRAVEL_Y * scale) + 40,
        fixture.width + int(TRAVEL_X * scale) + 40,
        seed=7,
    )


def sweep_path(fixture: Fixture) -> list[tuple[int, int]]:
    """Camera window positions: a lateral sweep with forward drift, turning once."""
    scale = fixture.width / ANALYSIS_SIZE[0]
    progress = np.arange(fixture.frames) / max(1, fixture.frames - 1)
    horizontal = TRAVEL_X * scale * (0.5 - 0.5 * np.cos(2 * np.pi * 0.75 * progress))
    vertical = TRAVEL_Y * scale * progress
    return [(int(x), int(y)) for x, y in zip(horizontal, vertical)]


def window(scene: np.ndarray, fixture: Fixture, left: int, top: int) -> np.ndarray:
    """The camera's view: a window of the scene at the camera's position."""
    return scene[top : top + fixture.height, left : left + fixture.width]


def encode_video(frames: list[np.ndarray], path: Path, fps: int = FIXTURE_FPS) -> None:
    """Encode greyscale frames to H.264 with ffmpeg."""
    height, width = frames[0].shape
    payload = np.clip(np.stack(frames), 0, 255).astype(np.uint8).tobytes()
    command = [
        "ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray",
        "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-crf", CRF, "-preset", X264_PRESET, "-pix_fmt", "yuv420p", str(path),
    ]
    try:
        result = subprocess.run(command, input=payload, capture_output=True)
    except FileNotFoundError as exc:
        raise FixtureError("ffmpeg is not on PATH; fixtures cannot be encoded") from exc
    if result.returncode != 0:
        raise FixtureError(f"ffmpeg failed to encode {path}: {result.stderr.decode('utf-8', 'replace').strip()}")


def translated_walk(fixture: Fixture, scene: np.ndarray) -> list[np.ndarray]:
    """Frames from a camera translating across a static scene."""
    return [window(scene, fixture, left, top).copy() for left, top in sweep_path(fixture)]


def stationary(fixture: Fixture, scene: np.ndarray) -> list[np.ndarray]:
    """Frames from a camera that never moves."""
    still = window(scene, fixture, int(0.2 * fixture.width), int(0.1 * fixture.height))
    return [still.copy() for _ in range(fixture.frames)]


def cut_sequence(fixture: Fixture) -> list[np.ndarray]:
    """Three unrelated scenes joined by hard cuts, each one static.

    Each scene canvas has to be wider than the camera window *and* offset from
    it, or the window runs off the canvas and the clip comes out narrower than
    the fixture claims -- a fixture whose resolution drifts is one the measured
    thresholds are no longer stated against.
    """
    per_scene = fixture.frames // 3
    offset_x, offset_y = int(0.2 * fixture.width), int(0.1 * fixture.height)
    canvas = (fixture.height + offset_y + 40, fixture.width + offset_x + 40)
    frames: list[np.ndarray] = []
    for index in range(3):
        scene = scene_texture(*canvas, seed=20 + index)
        still = window(scene, fixture, offset_x, offset_y).copy()
        assert still.shape == (fixture.height, fixture.width), (
            f"cut scene {index} window is {still.shape}, expected "
            f"{(fixture.height, fixture.width)}"
        )
        frames += [still.copy() for _ in range(per_scene)]
    frames += [frames[-1].copy() for _ in range(fixture.frames - len(frames))]
    return frames


def with_moving_object(fixture: Fixture, frames: list[np.ndarray]) -> list[np.ndarray]:
    """The accepted walk with a dark object crossing the frame."""
    moving = []
    for index, frame in enumerate(frames):
        annotated = frame.astype(np.float64).copy()
        left = 60 + (index * 15) % (fixture.width - 120)
        top = 100 + (index * 7) % (fixture.height - 220)
        annotated[top : top + 200, left : left + 100] *= 0.35
        moving.append(annotated)
    return moving


def incoherent_geometry(fixture: Fixture, scene: np.ndarray) -> list[np.ndarray]:
    """The accepted camera move over texture that is regenerated every frame."""
    rng = np.random.default_rng(3)
    frames = []
    for left, top in sweep_path(fixture):
        base = window(scene, fixture, left, top)
        noise = bilinear_noise(fixture.height, fixture.width, max(2, fixture.width // 180), rng)
        frames.append(0.45 * base + 0.55 * (10 + 190 * noise))
    return frames


FIXTURES = (
    Fixture("accepted_walkthrough", SHORT_CLIP_FRAMES, ANALYSIS_SIZE, ACCEPT, "static scene, real translation, no cuts"),
    Fixture("accepted_720p", 48, PHONE_720P_SIZE, ACCEPT, "720p: enough to match features, never a refusal"),
    Fixture("stationary_camera", SHORT_CLIP_FRAMES, ANALYSIS_SIZE, REJECT, "no baseline: the camera never moves"),
    Fixture("cut_sequence", SHORT_CLIP_FRAMES, ANALYSIS_SIZE, REJECT, "hard cuts between unrelated scenes"),
    Fixture("moving_content", SHORT_CLIP_FRAMES, ANALYSIS_SIZE, WARN, "an object crosses the frame during the take"),
    Fixture("incoherent_geometry", SHORT_CLIP_FRAMES, ANALYSIS_SIZE, REJECT, "geometry does not persist between frames"),
    Fixture("long_walkthrough", LONG_CLIP_FRAMES, ANALYSIS_SIZE, ACCEPT, "900 frames: bounded work over a long clip"),
)


def build_fixture(fixture: Fixture, output_dir: Path) -> Path:
    """Build one fixture and return the path written."""
    scene = scene_for(fixture)
    if fixture.name in ("accepted_walkthrough", "accepted_720p", "long_walkthrough"):
        frames = translated_walk(fixture, scene)
    elif fixture.name == "stationary_camera":
        frames = stationary(fixture, scene)
    elif fixture.name == "cut_sequence":
        frames = cut_sequence(fixture)
    elif fixture.name == "moving_content":
        frames = with_moving_object(fixture, translated_walk(fixture, scene))
    else:
        frames = incoherent_geometry(fixture, scene)
    _assert_frame_count(fixture, frames)
    path = output_dir / fixture.filename
    encode_video(frames, path)
    return path


def _assert_frame_count(fixture: Fixture, frames: list[np.ndarray]) -> None:
    """Fail loudly when a fixture no longer matches its own declared shape.

    Every threshold in the gate is stated against a fixture's resolution, so a
    clip that silently came out a different size would test the wrong regime and
    still pass. The canvas maths in each builder can produce a short window when
    it is wrong, which is exactly the case this catches.
    """
    if len(frames) != fixture.frames:
        raise FixtureError(
            f"{fixture.name} produced {len(frames)} frames, declared {fixture.frames}"
        )
    for position, frame in enumerate((frames[0], frames[-1])):
        if frame.shape != (fixture.height, fixture.width):
            raise FixtureError(
                f"{fixture.name} frame {position} is {frame.shape[1]}x{frame.shape[0]}, "
                f"declared {fixture.width}x{fixture.height}"
            )


def build_all(output_dir: Path, only: tuple[str, ...] = ()) -> list[tuple[Fixture, Path]]:
    """Build every fixture into ``output_dir``, optionally filtered by name."""
    output_dir.mkdir(parents=True, exist_ok=True)
    chosen = [fixture for fixture in FIXTURES if not only or fixture.name in only]
    return [(fixture, build_fixture(fixture, output_dir)) for fixture in chosen]


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    output_dir = Path(arguments[0]).expanduser() if arguments else Path(__file__).resolve().parent / "clips"
    try:
        built = build_all(output_dir)
    except FixtureError as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return 2
    for fixture, path in built:
        size = path.stat().st_size / 1024
        print(f"{fixture.filename:26s} {size:8.0f} KiB  expect {fixture.expected}: {fixture.property}")
    return 0


if __name__ == "__main__":
    sys.exit(main())