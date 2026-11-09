"""Tests for the footstep audition harness and separability metrics (#202)."""

from __future__ import annotations

import io
import json
import math
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT
from footstep_audit import (
    AUDIO_DIR,
    AUDITION_GAP_SECONDS,
    AUDITION_REPEATS,
    AUDITION_TAGS,
    DISTANCE_TAGS,
    LOUDNESS_TARGET_DBFS,
    SEPARABILITY_THRESHOLD,
    audit_directory,
    measure_sample,
    read_wav,
    render_audition,
    report_bytes,
)

SYNTHETIC_SPECS = {
    "land": (45.0, 3.5),
    "carpet": (79.0, 9.0),
    "concrete": (138.0, 13.0),
    "default": (241.0, 16.0),
    "plaster": (422.0, 20.0),
    "wood": (738.0, 24.0),
    "tile": (1292.0, 55.0),
    "debris": (2261.0, 6.0),
    "metal": (3956.0, 2.2),
}
SYNTHETIC_SAMPLE_RATE = 22050
SYNTHETIC_DURATION_SECONDS = 0.28
SYNTHETIC_VARIANTS = 3


def _low_pass(samples: np.ndarray, cutoff_hz: float, sample_rate: int) -> np.ndarray:
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff_hz / sample_rate)
    output = np.empty_like(samples)
    previous = 0.0
    for index, value in enumerate(samples):
        previous += alpha * (value - previous)
        output[index] = previous
    return output


def _synthetic_clip(frequency_hz: float, decay: float, variant: int) -> np.ndarray:
    rng = np.random.default_rng(1000 + int(frequency_hz) + variant)
    count = int(SYNTHETIC_SAMPLE_RATE * SYNTHETIC_DURATION_SECONDS)
    time = np.arange(count, dtype=np.float64) / SYNTHETIC_SAMPLE_RATE
    envelope = np.exp(-time * decay) * (1.0 - np.exp(-time * 400.0))
    noise = _low_pass(rng.standard_normal(count), 7000.0, SYNTHETIC_SAMPLE_RATE)
    noise /= max(float(np.max(np.abs(noise))), 1e-9)
    mixed = (0.9 * np.sin(2.0 * math.pi * frequency_hz * time) + 0.1 * noise) * envelope
    rms = float(np.sqrt(np.mean(mixed * mixed)))
    target = 10.0 ** (LOUDNESS_TARGET_DBFS / 20.0)
    return mixed * (target / rms)


def _write_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SYNTHETIC_SAMPLE_RATE)
        stream.writeframes(pcm.tobytes())
    path.write_bytes(buffer.getvalue())


def _write_synthetic_set(directory: Path) -> None:
    for tag, (frequency_hz, decay) in SYNTHETIC_SPECS.items():
        for variant in range(1, SYNTHETIC_VARIANTS + 1):
            clip = _synthetic_clip(frequency_hz, decay, variant)
            _write_wav(directory / tag / f"{tag}_{variant:02d}.wav", clip)


def _samples_version() -> str:
    manifest = json.loads((ROOT / AUDIO_DIR / "provenance.json").read_text())
    return str(manifest.get("script_version", ""))


def test_metrics_are_deterministic():
    path = ROOT / AUDIO_DIR / "metal" / "body" / "metal_body_01.wav"
    assert measure_sample(path) == measure_sample(path)
    first = audit_directory(ROOT / AUDIO_DIR)
    second = audit_directory(ROOT / AUDIO_DIR)
    assert report_bytes(first) == report_bytes(second)
    for left in DISTANCE_TAGS:
        assert first["matrix"][left][left] == 0.0
        for right in DISTANCE_TAGS:
            assert first["matrix"][left][right] == first["matrix"][right][left]


def test_v020_fails_loudness_and_separability():
    if _samples_version() != "footsteps-0.2.0":
        pytest.skip("baseline assertion applies to the v0.2.0 placeholder samples")
    report = audit_directory(ROOT / AUDIO_DIR)
    assert report["loudness"]["passes"] is False
    assert report["loudness"]["violations"]
    assert report["separability"]["passes"] is False
    assert report["separability"]["minimum_distance"] < SEPARABILITY_THRESHOLD


def test_v030_passes_loudness_and_separability():
    if _samples_version() != "footsteps-0.3.0":
        pytest.skip("layered assertion applies to the footstep stems 0.3.0")
    report = audit_directory(ROOT / AUDIO_DIR)
    assert report["loudness"]["passes"] is True
    assert report["separability"]["passes"] is True
    assert report["separability"]["minimum_distance"] >= SEPARABILITY_THRESHOLD
    for tag in AUDITION_TAGS:
        assert report["tags"][tag]["variant_count"] == (1 if tag == "land" else 4)


def test_synthetic_contrasting_set_passes(tmp_path: Path):
    _write_synthetic_set(tmp_path)
    report = audit_directory(tmp_path)
    assert report["loudness"]["passes"] is True
    assert report["separability"]["passes"] is True
    assert report["separability"]["minimum_distance"] >= SEPARABILITY_THRESHOLD
    for left in DISTANCE_TAGS:
        for right in DISTANCE_TAGS:
            if left == right:
                assert report["matrix"][left][right] == 0.0
            else:
                assert report["matrix"][left][right] >= SEPARABILITY_THRESHOLD


def test_audition_sheet_is_deterministic_and_complete(tmp_path: Path):
    first_path = tmp_path / "first.wav"
    second_path = tmp_path / "second.wav"
    first = render_audition(ROOT / AUDIO_DIR, first_path)
    render_audition(ROOT / AUDIO_DIR, second_path)
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first["order"] == list(AUDITION_TAGS)
    assert first["repeats"] == AUDITION_REPEATS
    assert first["gap_seconds"] == AUDITION_GAP_SECONDS
    assert set(first["gains"]) == set(AUDITION_TAGS)
    assert all(len(gains) == AUDITION_REPEATS for gains in first["gains"].values())
    samples, sample_rate = read_wav(first_path)
    assert sample_rate == SYNTHETIC_SAMPLE_RATE
    assert np.max(np.abs(samples)) <= 0.99
    with wave.open(str(first_path), "rb") as stream:
        assert stream.getnchannels() == 1
        assert stream.getsampwidth() == 2
        assert stream.getframerate() == SYNTHETIC_SAMPLE_RATE
        duration = stream.getnframes() / stream.getframerate()
    assert first["duration_s"] == pytest.approx(duration)
    assert duration > 20.0
