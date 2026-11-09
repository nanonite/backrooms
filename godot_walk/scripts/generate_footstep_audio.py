"""Synthesise the walkthrough footstep samples deterministically (#200).

The samples are mono 22.05 kHz WAVs built from soft filtered-noise heel and sole
impacts, with only a small material-defining tick. No downloaded audio is used. Run:

    python3 godot_walk/scripts/generate_footstep_audio.py generate
    python3 godot_walk/scripts/generate_footstep_audio.py check
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
import wave
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, plan_write, write_new

SCRIPT_VERSION = "footsteps-0.2.0"
PEAK_GAIN = 0.50
SAMPLE_RATE = 22050
VARIANT_COUNT = 4
AUDIO_DIR = Path("godot_walk/audio/footsteps")
MANIFEST_PATH = AUDIO_DIR / "provenance.json"
TAGS = ("carpet", "concrete", "tile", "plaster", "metal", "wood", "debris")
DEFAULT_TAG = "default"

# Soft heel and sole impacts: heel cutoff, sole cutoff, duration, heel decay,
# sole decay, tick weight. Differences are deliberately subtle.
PROFILES = {
    "carpet": {
        "heel_cutoff": 140.0,
        "sole_cutoff": 500.0,
        "duration": 0.22,
        "heel_decay": 40.0,
        "sole_decay": 12.0,
        "tick": 0.010,
    },
    "concrete": {
        "heel_cutoff": 180.0,
        "sole_cutoff": 800.0,
        "duration": 0.20,
        "heel_decay": 48.0,
        "sole_decay": 15.0,
        "tick": 0.025,
    },
    "tile": {
        "heel_cutoff": 195.0,
        "sole_cutoff": 950.0,
        "duration": 0.19,
        "heel_decay": 52.0,
        "sole_decay": 16.0,
        "tick": 0.030,
    },
    "plaster": {
        "heel_cutoff": 165.0,
        "sole_cutoff": 650.0,
        "duration": 0.21,
        "heel_decay": 43.0,
        "sole_decay": 13.0,
        "tick": 0.018,
    },
    "metal": {
        "heel_cutoff": 205.0,
        "sole_cutoff": 1050.0,
        "duration": 0.23,
        "heel_decay": 45.0,
        "sole_decay": 14.0,
        "tick": 0.028,
    },
    "wood": {
        "heel_cutoff": 175.0,
        "sole_cutoff": 750.0,
        "duration": 0.21,
        "heel_decay": 44.0,
        "sole_decay": 14.0,
        "tick": 0.020,
    },
    "debris": {
        "heel_cutoff": 150.0,
        "sole_cutoff": 620.0,
        "duration": 0.24,
        "heel_decay": 39.0,
        "sole_decay": 12.0,
        "tick": 0.018,
    },
    "default": {
        "heel_cutoff": 160.0,
        "sole_cutoff": 650.0,
        "duration": 0.21,
        "heel_decay": 42.0,
        "sole_decay": 13.0,
        "tick": 0.018,
    },
    "land": {
        "heel_cutoff": 125.0,
        "sole_cutoff": 420.0,
        "duration": 0.27,
        "heel_decay": 28.0,
        "sole_decay": 9.0,
        "tick": 0.005,
    },
}


def _seed(tag: str, variant: int) -> int:
    text = f"{SCRIPT_VERSION}:{tag}:{variant}"
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest(), "big")


def _low_pass(samples: np.ndarray, cutoff_hz: float) -> np.ndarray:
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff_hz / SAMPLE_RATE)
    output = np.empty_like(samples)
    previous = 0.0
    for index, value in enumerate(samples):
        previous += alpha * (value - previous)
        output[index] = previous
    return output


def _filtered_noise(
    rng: np.random.Generator, count: int, cutoff_hz: float, passes: int = 3
) -> np.ndarray:
    noise = rng.standard_normal(count)
    for _pass in range(passes):
        noise = _low_pass(noise, cutoff_hz)
    return noise / max(float(np.max(np.abs(noise))), 1e-9)


def _synthesise(tag: str, variant: int) -> bytes:
    profile = PROFILES[tag]
    rng = np.random.default_rng(_seed(tag, variant))
    count = int(SAMPLE_RATE * profile["duration"])
    time = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    attack = 1.0 - np.exp(-time * 260.0)
    heel = _filtered_noise(rng, count, profile["heel_cutoff"]) * np.exp(
        -time * profile["heel_decay"]
    )
    sole = _filtered_noise(rng, count, profile["sole_cutoff"]) * np.exp(
        -time * profile["sole_decay"]
    )
    tick = _filtered_noise(rng, count, 1800.0, 4) * np.exp(-time * 95.0)
    mixed = (0.60 * heel + 0.55 * sole + profile["tick"] * tick) * attack
    mixed -= np.mean(mixed)
    for _pass in range(2):
        mixed = _low_pass(mixed, 2000.0)
    mixed *= np.exp(-time * 1.5)
    peak = max(float(np.max(np.abs(mixed))), 1e-9)
    pcm = np.clip(mixed / peak * PEAK_GAIN, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _records() -> list[dict[str, Any]]:
    records = []
    for tag in (*TAGS, DEFAULT_TAG):
        for variant in range(1, VARIANT_COUNT + 1):
            records.append(
                {
                    "tag": tag,
                    "variant": variant,
                    "path": (AUDIO_DIR / tag / f"{tag}_{variant:02d}.wav").as_posix(),
                }
            )
    records.append(
        {
            "tag": "land",
            "variant": 1,
            "path": (AUDIO_DIR / "land" / "land_01.wav").as_posix(),
        }
    )
    return records


def _manifest_bytes() -> bytes:
    records = []
    for record in _records():
        data = _synthesise(record["tag"], record["variant"])
        records.append(
            {
                **record,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    document = {
        "schema_version": 1,
        "script_version": SCRIPT_VERSION,
        "generator": "godot_walk/scripts/generate_footstep_audio.py",
        "sample_rate": SAMPLE_RATE,
        "variant_count": VARIANT_COUNT,
        "tags": [*TAGS, DEFAULT_TAG, "land"],
        "seed_rule": "sha256(script_version:tag:variant)",
        "profiles": PROFILES,
        "peak_gain": PEAK_GAIN,
        "records": records,
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def generate() -> dict[str, Any]:
    created = 0
    for record in _records():
        data = _synthesise(record["tag"], record["variant"])
        path = ROOT / record["path"]
        status = plan_write(path, data)
        if status == "create":
            write_new(path, data)
            created += 1
    manifest = ROOT / MANIFEST_PATH
    data = _manifest_bytes()
    status = plan_write(manifest, data)
    if status == "create":
        write_new(manifest, data)
        created += 1
    return {
        "directory": AUDIO_DIR.as_posix(),
        "files": len(_records()),
        "manifest": MANIFEST_PATH.as_posix(),
        "created": created,
    }


def check() -> list[str]:
    errors = []
    for record in _records():
        path = ROOT / record["path"]
        if not path.is_file():
            errors.append(f"{record['path']}: missing")
            continue
        if path.read_bytes() != _synthesise(record["tag"], record["variant"]):
            errors.append(f"{record['path']}: differs from deterministic audio")
    if errors:
        return errors
    manifest = ROOT / MANIFEST_PATH
    if not manifest.is_file():
        return [f"{MANIFEST_PATH.as_posix()}: missing"]
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except ValueError as error:
        return [f"{MANIFEST_PATH.as_posix()}: {error}"]
    expected = json.loads(_manifest_bytes().decode("utf-8"))
    if document != expected:
        errors.append(
            f"{MANIFEST_PATH.as_posix()}: differs from deterministic manifest"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "check"))
    arguments = parser.parse_args(argv)
    if arguments.command == "generate":
        print(json.dumps(generate(), sort_keys=True))
        return 0
    errors = check()
    print(json.dumps({"valid": not errors, "errors": errors}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
