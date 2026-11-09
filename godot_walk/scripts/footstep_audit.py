"""Audit footstep loudness and material separability, and render an audition sheet (#202).

The audit is deliberately deterministic: the same WAVs always produce the same
metrics, matrix and audition bytes. It reads the committed samples under
`godot_walk/audio/footsteps` but never rewrites them.

Usage:
    python3 godot_walk/scripts/footstep_audit.py report
    python3 godot_walk/scripts/footstep_audit.py report --json report.json \
        --markdown matrix.md
    python3 godot_walk/scripts/footstep_audit.py render
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import wave
from datetime import datetime, timezone
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import periodogram

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, repo_relative, write_deterministic

SCRIPT_VERSION = "footstep-audit-0.1.0"
ISSUE_NUMBER = 202
SAMPLE_RATE = 22050
AUDIO_DIR = Path("godot_walk/audio/footsteps")
EVIDENCE_ROOT = Path("godot_walk/evidence")

TAGS = ("carpet", "concrete", "tile", "plaster", "metal", "wood", "debris")
DEFAULT_TAG = "default"
LAND_TAG = "land"
AUDITION_TAGS = (*TAGS, DEFAULT_TAG, LAND_TAG)
DISTANCE_TAGS = AUDITION_TAGS

BAND_NAMES = ("sub_200", "band_200_800", "band_800_3000", "band_above_3000")
BAND_EDGES_HZ = (0.0, 200.0, 800.0, 3000.0, math.inf)

# The pre-0.2.0 generator normalised every sample to peak 0.72 and measured
# -19.89 dBFS RMS across its 32 tag variants (-19.90 including land). The v0.1.0
# file was never committed; it was recovered from the #200 worker session log.
# Round to one decimal for the target.
LOUDNESS_TARGET_DBFS = -19.9
LOUDNESS_TOLERANCE_DB = 1.5

# Chosen so footsteps-0.2.0 fails every-pair separability while a deliberately
# contrasting synthetic set passes. See evidence/2026-11-08-issue-202/REPORT.md.
SEPARABILITY_THRESHOLD = 0.60
BAND_DISTANCE_WEIGHT = 2.0

AUDITION_REPEATS = 3
AUDITION_GAP_SECONDS = 0.6
AUDITION_LEAD_IN_SECONDS = 0.6
BEEP_HZ = 880.0
BEEP_SECONDS = 0.12
BEEP_AMPLITUDE = 0.16
CLIP_FADE_SECONDS = 0.004
PEAK_LIMIT = 0.98

DECAY_FRAME_SECONDS = 0.005
DECAY_RANGE_DB = 20.0
DECAY_MAX_SECONDS = 4.0
SILENCE_FLOOR = 1e-12


def _db(value: float) -> float:
    return 20.0 * math.log10(max(float(value), SILENCE_FLOOR))


def _power_db(value: float) -> float:
    return 10.0 * math.log10(max(float(value), SILENCE_FLOOR))


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        sample_width = stream.getsampwidth()
        sample_rate = stream.getframerate()
        frame_count = stream.getnframes()
        raw = stream.readframes(frame_count)
    if sample_width != 2:
        raise ValueError(f"{path}: expected 16-bit PCM, got {sample_width * 8}-bit")
    if channels < 1:
        raise ValueError(f"{path}: no audio channels")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, sample_rate


def _band_energies(
    samples: np.ndarray, sample_rate: int
) -> tuple[list[float], list[float]]:
    nfft = 1 << max(11, (len(samples) - 1).bit_length())
    frequencies, density = periodogram(
        samples,
        fs=sample_rate,
        window="hann",
        detrend="constant",
        scaling="density",
        nfft=nfft,
    )
    bin_width = sample_rate / nfft
    energies = []
    for lower, upper in pairwise(BAND_EDGES_HZ):
        mask = (frequencies >= lower) & (frequencies < upper)
        energies.append(float(np.sum(density[mask]) * bin_width))
    total = float(np.sum(energies))
    if total <= SILENCE_FLOOR:
        return energies, [0.0 for _ in energies]
    return energies, [energy / total for energy in energies]


def _spectral_centroid(samples: np.ndarray, sample_rate: int) -> float:
    nfft = 1 << max(11, (len(samples) - 1).bit_length())
    frequencies, density = periodogram(
        samples,
        fs=sample_rate,
        window="hann",
        detrend="constant",
        scaling="density",
        nfft=nfft,
    )
    total = float(np.sum(density))
    if total <= SILENCE_FLOOR:
        return 0.0
    return float(np.sum(frequencies * density) / total)


def _decay_seconds(samples: np.ndarray, sample_rate: int) -> float:
    frame_length = max(1, int(sample_rate * DECAY_FRAME_SECONDS))
    frame_count = len(samples) // frame_length
    if frame_count < 3:
        return 0.0
    frames = samples[: frame_count * frame_length].reshape(frame_count, frame_length)
    levels = 10.0 * np.log10(
        np.maximum(np.mean(frames * frames, axis=1), SILENCE_FLOOR)
    )
    peak = int(np.argmax(levels))
    tail = levels[peak:]
    if len(tail) < 3:
        return 0.0
    below = np.flatnonzero(tail <= levels[peak] - DECAY_RANGE_DB)
    stop = int(below[0]) + 1 if below.size else len(tail)
    segment = tail[: max(stop, 3)]
    times = np.arange(len(segment)) * frame_length / sample_rate
    slope, _intercept = np.polyfit(times, segment, 1)
    if slope >= -1e-6:
        return 0.0
    return float(min(60.0 / abs(slope), DECAY_MAX_SECONDS))


def _display_path(path: Path) -> str:
    try:
        return repo_relative(path, ROOT)
    except ValueError:
        return path.as_posix()


def measure_sample(path: Path) -> dict[str, Any]:
    samples, sample_rate = read_wav(path)
    if len(samples) < 3:
        raise ValueError(f"{path}: too short to measure")
    rms = float(np.sqrt(np.mean(samples * samples)))
    peak = float(np.max(np.abs(samples)))
    energies, fractions = _band_energies(samples, sample_rate)
    return {
        "path": path.as_posix(),
        "duration_s": round(len(samples) / sample_rate, 6),
        "rms_dbfs": round(_db(rms), 3),
        "peak_dbfs": round(_db(peak), 3),
        "crest_factor_db": round(_db(peak) - _db(rms), 3),
        "spectral_centroid_hz": round(_spectral_centroid(samples, sample_rate), 3),
        "band_energy_dbfs": {
            name: round(_power_db(energy), 3)
            for name, energy in zip(BAND_NAMES, energies)
        },
        "band_fraction": {
            name: round(fraction, 6) for name, fraction in zip(BAND_NAMES, fractions)
        },
        "t60_s": round(_decay_seconds(samples, sample_rate), 6),
    }


def _mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def aggregate_tag(tag: str, samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ValueError(f"{tag}: no variants to aggregate")
    return {
        "tag": tag,
        "variant_count": len(samples),
        "rms_dbfs": round(_mean([sample["rms_dbfs"] for sample in samples]), 3),
        "peak_dbfs": round(_mean([sample["peak_dbfs"] for sample in samples]), 3),
        "crest_factor_db": round(
            _mean([sample["crest_factor_db"] for sample in samples]), 3
        ),
        "spectral_centroid_hz": round(
            _mean([sample["spectral_centroid_hz"] for sample in samples]), 3
        ),
        "t60_s": round(_mean([sample["t60_s"] for sample in samples]), 6),
        "band_energy_dbfs": {
            name: round(
                _mean([sample["band_energy_dbfs"][name] for sample in samples]), 3
            )
            for name in BAND_NAMES
        },
        "band_fraction": {
            name: round(_mean([sample["band_fraction"][name] for sample in samples]), 6)
            for name in BAND_NAMES
        },
    }


def _distance_features(tag_mean: dict[str, Any]) -> tuple[float, float, np.ndarray]:
    centroid_octaves = math.log2(max(tag_mean["spectral_centroid_hz"], 1.0))
    decay_log = math.log(max(tag_mean["t60_s"], 0.001))
    bands = np.array(
        [tag_mean["band_fraction"][name] for name in BAND_NAMES], dtype=np.float64
    )
    return centroid_octaves, decay_log, bands


def material_distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_centroid, left_decay, left_bands = _distance_features(left)
    right_centroid, right_decay, right_bands = _distance_features(right)
    centroid_term = abs(left_centroid - right_centroid)
    decay_term = abs(left_decay - right_decay)
    band_term = 0.5 * float(np.sum(np.abs(left_bands - right_bands)))
    return round(
        math.sqrt(
            centroid_term**2 + decay_term**2 + (BAND_DISTANCE_WEIGHT * band_term) ** 2
        ),
        6,
    )


def _tag_files(audio_dir: Path, tag: str) -> list[Path]:
    return sorted(
        path for path in audio_dir.glob(f"{tag}/{tag}_*.wav") if path.is_file()
    )


def audit_directory(audio_dir: Path = AUDIO_DIR) -> dict[str, Any]:
    tags: dict[str, Any] = {}
    variants: dict[str, list[dict[str, Any]]] = {}
    for tag in AUDITION_TAGS:
        files = _tag_files(audio_dir, tag)
        if not files:
            raise FileNotFoundError(f"{audio_dir / tag}: no {tag}_*.wav samples")
        samples = [measure_sample(path) for path in files]
        for sample in samples:
            sample["path"] = _display_path(Path(sample["path"]))
        variants[tag] = samples
        tags[tag] = aggregate_tag(tag, samples)

    matrix = {
        left: {
            right: material_distance(tags[left], tags[right]) for right in DISTANCE_TAGS
        }
        for left in DISTANCE_TAGS
    }
    pairs = [
        (left, right, matrix[left][right])
        for index, left in enumerate(DISTANCE_TAGS)
        for right in DISTANCE_TAGS[index + 1 :]
    ]
    minimum = min(pairs, key=lambda pair: pair[2])
    loudness_violations = [
        {
            "tag": tag,
            "variant": sample["path"],
            "rms_dbfs": sample["rms_dbfs"],
            "deviation_db": round(sample["rms_dbfs"] - LOUDNESS_TARGET_DBFS, 3),
        }
        for tag, samples in variants.items()
        for sample in samples
        if abs(sample["rms_dbfs"] - LOUDNESS_TARGET_DBFS) > LOUDNESS_TOLERANCE_DB
    ]
    return {
        "schema_version": 1,
        "generator": "godot_walk/scripts/footstep_audit.py",
        "generator_version": SCRIPT_VERSION,
        "audio_dir": _display_path(audio_dir),
        "loudness": {
            "target_dbfs": LOUDNESS_TARGET_DBFS,
            "tolerance_db": LOUDNESS_TOLERANCE_DB,
            "passes": not loudness_violations,
            "violations": loudness_violations,
        },
        "separability": {
            "threshold": SEPARABILITY_THRESHOLD,
            "passes": minimum[2] >= SEPARABILITY_THRESHOLD,
            "minimum_distance": minimum[2],
            "minimum_pair": [minimum[0], minimum[1]],
        },
        "distance_tags": list(DISTANCE_TAGS),
        "tags": tags,
        "variants": variants,
        "matrix": matrix,
    }


def format_matrix(report: dict[str, Any]) -> str:
    tags = report["distance_tags"]
    lines = [
        "| tag | " + " | ".join(tags) + " |",
        "|" + "---|" * (len(tags) + 1),
    ]
    for left in tags:
        cells = [f"{report['matrix'][left][right]:.2f}" for right in tags]
        lines.append(f"| {left} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def report_bytes(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _fade(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    count = min(len(samples) // 2, max(1, int(sample_rate * CLIP_FADE_SECONDS)))
    if count <= 0:
        return samples
    window = np.ones(len(samples), dtype=np.float64)
    ramp = np.linspace(0.0, 1.0, count, endpoint=False)
    window[:count] = ramp
    window[-count:] = ramp[::-1]
    return samples * window


def _normalise_rms(samples: np.ndarray) -> tuple[np.ndarray, float]:
    rms = float(np.sqrt(np.mean(samples * samples)))
    if rms <= SILENCE_FLOOR:
        raise ValueError("cannot normalise a silent sample")
    target = 10.0 ** (LOUDNESS_TARGET_DBFS / 20.0)
    gain = target / rms
    peak = float(np.max(np.abs(samples)))
    if peak * gain > PEAK_LIMIT:
        gain = PEAK_LIMIT / peak
    return samples * gain, gain


def _beep(sample_rate: int) -> np.ndarray:
    count = int(sample_rate * BEEP_SECONDS)
    time = np.arange(count, dtype=np.float64) / sample_rate
    tone = BEEP_AMPLITUDE * np.sin(2.0 * math.pi * BEEP_HZ * time)
    return _fade(tone, sample_rate)


def _silence(sample_rate: int, seconds: float) -> np.ndarray:
    return np.zeros(int(sample_rate * seconds), dtype=np.float64)


def _audition_segments(
    audio_dir: Path, sample_rate: int
) -> tuple[list[np.ndarray], dict[str, Any]]:
    segments = [_silence(sample_rate, AUDITION_LEAD_IN_SECONDS)]
    gains: dict[str, list[float]] = {}
    for tag in AUDITION_TAGS:
        files = _tag_files(audio_dir, tag)
        if not files:
            raise FileNotFoundError(f"{audio_dir / tag}: no {tag}_*.wav samples")
        gains[tag] = []
        for repeat in range(AUDITION_REPEATS):
            if repeat == 0:
                segments.append(_beep(sample_rate))
                segments.append(_silence(sample_rate, AUDITION_GAP_SECONDS))
            path = files[repeat % len(files)]
            clip, clip_rate = read_wav(path)
            if clip_rate != sample_rate:
                raise ValueError(
                    f"{path}: expected {sample_rate} Hz, got {clip_rate} Hz"
                )
            clip, gain = _normalise_rms(clip)
            gains[tag].append(round(gain, 6))
            segments.append(_fade(clip, sample_rate))
            segments.append(_silence(sample_rate, AUDITION_GAP_SECONDS))
    metadata = {
        "order": list(AUDITION_TAGS),
        "repeats": AUDITION_REPEATS,
        "gap_seconds": AUDITION_GAP_SECONDS,
        "beep_hz": BEEP_HZ,
        "beep_seconds": BEEP_SECONDS,
        "loudness_target_dbfs": LOUDNESS_TARGET_DBFS,
        "gains": gains,
    }
    return segments, metadata


def render_audition(
    audio_dir: Path = AUDIO_DIR, out_path: Path | None = None
) -> dict[str, Any]:
    segments, metadata = _audition_segments(audio_dir, SAMPLE_RATE)
    samples = np.concatenate(segments)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(
            (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        )
    data = buffer.getvalue()
    if out_path is None:
        raise ValueError("out_path is required")
    write_deterministic(out_path, data)
    metadata["path"] = out_path.as_posix()
    metadata["duration_s"] = round(len(samples) / SAMPLE_RATE, 6)
    metadata["bytes"] = len(data)
    return metadata


def default_evidence_dir(issue: int = ISSUE_NUMBER, day: str | None = None) -> Path:
    local_day = datetime.now(timezone.utc).astimezone().date().isoformat()
    return EVIDENCE_ROOT / f"{day or local_day}-issue-{issue}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("report", "audit", "render"))
    parser.add_argument("--audio-dir", type=Path, default=AUDIO_DIR)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--issue", type=int, default=ISSUE_NUMBER)
    parser.add_argument("--date")
    arguments = parser.parse_args(argv)

    audio_dir = (
        arguments.audio_dir
        if arguments.audio_dir.is_absolute()
        else ROOT / arguments.audio_dir
    )
    if arguments.command in ("report", "audit"):
        report = audit_directory(audio_dir)
        data = report_bytes(report)
        if arguments.json:
            write_deterministic(arguments.json, data)
        else:
            print(data.decode("utf-8"), end="")
        if arguments.markdown:
            write_deterministic(
                arguments.markdown, format_matrix(report).encode("utf-8")
            )
        return 0

    out_path = arguments.out or (
        default_evidence_dir(arguments.issue, arguments.date) / "audition.wav"
    )
    metadata = render_audition(audio_dir, out_path)
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
