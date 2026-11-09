"""Synthesise layered footstep samples deterministically (#203, footsteps-0.3.0).

Each acoustic tag is baked with three layer roles: a short brightness-tuned
transient (two baked tiers), a material-specific modal body, and a granular
texture. The runtime mixes one transient tier, the body and the texture on
pooled players, so this generator only writes mono 22.05 kHz 16-bit WAV stems.
No downloaded audio is used.

Layout:

    godot_walk/audio/footsteps/<tag>/<layer>/<tag>_<layer>_<variant>.wav
    godot_walk/audio/footsteps/<tag>/<layer>/<tag>_<layer>_01.wav   (land)

Run:

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

SCRIPT_VERSION = "footsteps-0.3.0"
SAMPLE_RATE = 22050
VARIANT_COUNT = 4
AUDIO_DIR = Path("godot_walk/audio/footsteps")
MANIFEST_PATH = AUDIO_DIR / "provenance.json"
TAGS = ("carpet", "concrete", "tile", "plaster", "metal", "wood", "debris")
DEFAULT_TAG = "default"
LAND_TAG = "land"
TAG_SET = (*TAGS, DEFAULT_TAG, LAND_TAG)

TRANSIENT_SOFT = "transient_soft"
TRANSIENT_HARD = "transient_hard"
BODY = "body"
TEXTURE = "texture"
LAYERS = (TRANSIENT_SOFT, TRANSIENT_HARD, BODY, TEXTURE)
REQUIRED_LAYERS = (TRANSIENT_SOFT, BODY, TEXTURE)
MIX_LAYERS = (TRANSIENT_SOFT, BODY, TEXTURE)

LOW_PASS_HZ = 6000.0
BODY_NOISE_WEIGHT = 0.75
MAX_STEM_SECONDS = 0.30
LOUDNESS_TARGET_DBFS = -19.9
PEAK_LIMIT = 0.98
MAX_ONSET_MS = 8.0

# Modal banks use (frequency Hz, decay per second, relative gain). Decay is the
# exponential rate of each mode; slower modes give a longer T60 tail.
PROFILES = {
    "carpet": {
        "layer_gain": {"transient": 0.32, "body": 1.00, "texture": 0.30},
        TRANSIENT_SOFT: {
            "duration_s": 0.070,
            "band_hz": [200.0, 1400.0],
            "decay": 85.0,
            "click": 0.06,
        },
        TRANSIENT_HARD: {
            "duration_s": 0.060,
            "band_hz": [900.0, 4800.0],
            "decay": 115.0,
            "click": 0.22,
        },
        BODY: {
            "duration_s": 0.220,
            "modes": [
                [70.0, 58.0, 1.00],
                [105.0, 64.0, 0.65],
                [150.0, 72.0, 0.40],
                [215.0, 85.0, 0.22],
                [300.0, 100.0, 0.12],
            ],
        },
        TEXTURE: {
            "duration_s": 0.220,
            "grain_count": 26,
            "grain_ms": 7.0,
            "band_hz": [180.0, 700.0],
            "grain_decay": 60.0,
            "bed_decay": 58.0,
            "bed_gain": 0.55,
            "decay": 58.0,
        },
    },
    "concrete": {
        "layer_gain": {"transient": 0.42, "body": 1.00, "texture": 0.10},
        TRANSIENT_SOFT: {
            "duration_s": 0.060,
            "band_hz": [450.0, 3000.0],
            "decay": 110.0,
            "click": 0.16,
        },
        TRANSIENT_HARD: {
            "duration_s": 0.055,
            "band_hz": [1800.0, 5800.0],
            "decay": 145.0,
            "click": 0.40,
        },
        BODY: {
            "duration_s": 0.120,
            "modes": [
                [230.0, 92.0, 0.60],
                [420.0, 98.0, 0.80],
                [760.0, 102.0, 1.00],
                [1380.0, 110.0, 0.65],
                [2350.0, 118.0, 0.35],
            ],
        },
        TEXTURE: {
            "duration_s": 0.120,
            "grain_count": 9,
            "grain_ms": 3.0,
            "band_hz": [350.0, 1800.0],
            "grain_decay": 120.0,
            "bed_decay": 92.0,
            "bed_gain": 0.35,
            "decay": 92.0,
        },
    },
    "tile": {
        "layer_gain": {"transient": 0.55, "body": 1.00, "texture": 0.04},
        TRANSIENT_SOFT: {
            "duration_s": 0.055,
            "band_hz": [1000.0, 4800.0],
            "decay": 130.0,
            "click": 0.24,
        },
        TRANSIENT_HARD: {
            "duration_s": 0.050,
            "band_hz": [2600.0, 6000.0],
            "decay": 165.0,
            "click": 0.50,
        },
        BODY: {
            "duration_s": 0.085,
            "modes": [
                [1250.0, 125.0, 0.35],
                [2100.0, 130.0, 0.60],
                [3400.0, 138.0, 1.00],
                [5200.0, 145.0, 0.70],
                [7600.0, 155.0, 0.35],
            ],
        },
        TEXTURE: {
            "duration_s": 0.100,
            "grain_count": 5,
            "grain_ms": 2.5,
            "band_hz": [2500.0, 6000.0],
            "grain_decay": 150.0,
            "bed_decay": 125.0,
            "bed_gain": 0.20,
            "decay": 125.0,
        },
    },
    "plaster": {
        "layer_gain": {"transient": 0.32, "body": 1.00, "texture": 0.12},
        TRANSIENT_SOFT: {
            "duration_s": 0.065,
            "band_hz": [300.0, 2200.0],
            "decay": 115.0,
            "click": 0.10,
        },
        TRANSIENT_HARD: {
            "duration_s": 0.055,
            "band_hz": [1400.0, 5400.0],
            "decay": 150.0,
            "click": 0.30,
        },
        BODY: {
            "duration_s": 0.110,
            "modes": [
                [130.0, 118.0, 0.65],
                [210.0, 124.0, 1.00],
                [340.0, 132.0, 0.55],
                [540.0, 140.0, 0.28],
            ],
        },
        TEXTURE: {
            "duration_s": 0.110,
            "grain_count": 12,
            "grain_ms": 4.0,
            "band_hz": [220.0, 900.0],
            "grain_decay": 110.0,
            "bed_decay": 118.0,
            "bed_gain": 0.40,
            "decay": 118.0,
        },
    },
    "metal": {
        "layer_gain": {"transient": 0.42, "body": 1.00, "texture": 0.03},
        TRANSIENT_SOFT: {
            "duration_s": 0.065,
            "band_hz": [800.0, 4200.0],
            "decay": 100.0,
            "click": 0.26,
        },
        TRANSIENT_HARD: {
            "duration_s": 0.055,
            "band_hz": [2200.0, 6000.0],
            "decay": 135.0,
            "click": 0.55,
        },
        BODY: {
            "duration_s": 0.285,
            "modes": [
                [700.0, 24.0, 0.30],
                [990.0, 25.0, 0.45],
                [1485.0, 26.0, 0.55],
                [2280.0, 27.0, 0.50],
                [3520.0, 28.0, 0.35],
                [5400.0, 30.0, 0.22],
            ],
        },
        TEXTURE: {
            "duration_s": 0.285,
            "grain_count": 6,
            "grain_ms": 3.0,
            "band_hz": [1800.0, 6000.0],
            "grain_decay": 80.0,
            "bed_decay": 24.0,
            "bed_gain": 0.20,
            "decay": 24.0,
        },
    },
    "wood": {
        "layer_gain": {"transient": 0.34, "body": 1.00, "texture": 0.15},
        TRANSIENT_SOFT: {
            "duration_s": 0.065,
            "band_hz": [400.0, 2600.0],
            "decay": 105.0,
            "click": 0.14,
        },
        TRANSIENT_HARD: {
            "duration_s": 0.055,
            "band_hz": [1600.0, 5600.0],
            "decay": 140.0,
            "click": 0.34,
        },
        BODY: {
            "duration_s": 0.220,
            "modes": [
                [220.0, 40.0, 0.70],
                [340.0, 43.0, 1.00],
                [590.0, 46.0, 0.75],
                [980.0, 50.0, 0.50],
                [1620.0, 55.0, 0.30],
            ],
        },
        TEXTURE: {
            "duration_s": 0.220,
            "grain_count": 15,
            "grain_ms": 5.0,
            "band_hz": [300.0, 1300.0],
            "grain_decay": 60.0,
            "bed_decay": 40.0,
            "bed_gain": 0.40,
            "decay": 40.0,
        },
    },
    "debris": {
        "layer_gain": {"transient": 0.40, "body": 0.90, "texture": 0.55},
        TRANSIENT_SOFT: {
            "duration_s": 0.065,
            "band_hz": [600.0, 3400.0],
            "decay": 100.0,
            "click": 0.20,
        },
        TRANSIENT_HARD: {
            "duration_s": 0.055,
            "band_hz": [2000.0, 6000.0],
            "decay": 135.0,
            "click": 0.45,
        },
        BODY: {
            "duration_s": 0.190,
            "modes": [
                [260.0, 58.0, 0.45],
                [430.0, 62.0, 0.60],
                [760.0, 68.0, 0.65],
                [1350.0, 74.0, 0.55],
                [2400.0, 82.0, 0.35],
            ],
        },
        TEXTURE: {
            "duration_s": 0.120,
            "grain_count": 140,
            "grain_ms": 3.0,
            "band_hz": [1000.0, 5000.0],
            "grain_decay": 70.0,
            "bed_decay": 58.0,
            "bed_gain": 0.50,
            "decay": 58.0,
        },
    },
    "default": {
        "layer_gain": {"transient": 0.34, "body": 1.00, "texture": 0.14},
        TRANSIENT_SOFT: {
            "duration_s": 0.065,
            "band_hz": [350.0, 2400.0],
            "decay": 108.0,
            "click": 0.12,
        },
        TRANSIENT_HARD: {
            "duration_s": 0.055,
            "band_hz": [1500.0, 5600.0],
            "decay": 142.0,
            "click": 0.32,
        },
        BODY: {
            "duration_s": 0.200,
            "modes": [
                [150.0, 54.0, 0.55],
                [250.0, 58.0, 1.00],
                [410.0, 62.0, 0.60],
                [680.0, 68.0, 0.35],
                [1100.0, 75.0, 0.18],
            ],
        },
        TEXTURE: {
            "duration_s": 0.200,
            "grain_count": 13,
            "grain_ms": 4.5,
            "band_hz": [280.0, 1100.0],
            "grain_decay": 70.0,
            "bed_decay": 54.0,
            "bed_gain": 0.38,
            "decay": 54.0,
        },
    },
    "land": {
        "layer_gain": {"transient": 0.34, "body": 1.00, "texture": 0.18},
        TRANSIENT_SOFT: {
            "duration_s": 0.075,
            "band_hz": [120.0, 1200.0],
            "decay": 70.0,
            "click": 0.05,
        },
        TRANSIENT_HARD: {
            "duration_s": 0.065,
            "band_hz": [900.0, 5600.0],
            "decay": 95.0,
            "click": 0.35,
        },
        BODY: {
            "duration_s": 0.285,
            "modes": [
                [48.0, 26.0, 1.00],
                [74.0, 28.0, 0.55],
                [112.0, 30.0, 0.30],
                [168.0, 34.0, 0.15],
            ],
        },
        TEXTURE: {
            "duration_s": 0.285,
            "grain_count": 16,
            "grain_ms": 6.0,
            "band_hz": [150.0, 700.0],
            "grain_decay": 45.0,
            "bed_decay": 26.0,
            "bed_gain": 0.45,
            "decay": 26.0,
        },
    },
}


def _seed(tag: str, variant: int, layer: str) -> int:
    text = f"{SCRIPT_VERSION}:{tag}:{variant}:{layer}"
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest(), "big")


def _variant_count(tag: str) -> int:
    return 1 if tag == LAND_TAG else VARIANT_COUNT


def _records() -> list[dict[str, Any]]:
    records = []
    for tag in TAG_SET:
        for variant in range(1, _variant_count(tag) + 1):
            for layer in LAYERS:
                records.append(
                    {
                        "tag": tag,
                        "variant": variant,
                        "layer": layer,
                        "path": (
                            AUDIO_DIR / tag / layer / f"{tag}_{layer}_{variant:02d}.wav"
                        ).as_posix(),
                    }
                )
    return records


def _low_pass(samples: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """Fourth-order Butterworth magnitude response, zero-phase and deterministic."""
    count = len(samples)
    spectrum = np.fft.rfft(samples)
    frequencies = np.fft.rfftfreq(count, 1.0 / SAMPLE_RATE)
    magnitude = 1.0 / np.sqrt(1.0 + (frequencies / cutoff_hz) ** 8.0)
    return np.fft.irfft(spectrum * magnitude, n=count)


def _band_shape(frequencies: np.ndarray, low_hz: float, high_hz: float) -> np.ndarray:
    high_pass = frequencies**2.0 / (frequencies**2.0 + low_hz**2.0)
    low_pass = high_hz**2.0 / (frequencies**2.0 + high_hz**2.0)
    return high_pass * low_pass


def _band_noise(
    rng: np.random.Generator, count: int, low_hz: float, high_hz: float
) -> np.ndarray:
    noise = rng.standard_normal(count)
    spectrum = np.fft.rfft(noise)
    frequencies = np.fft.rfftfreq(count, 1.0 / SAMPLE_RATE)
    shaped = np.fft.irfft(spectrum * _band_shape(frequencies, low_hz, high_hz), n=count)
    peak = max(float(np.max(np.abs(shaped))), 1e-12)
    return shaped / peak


def _fade_tail(samples: np.ndarray, seconds: float = 0.010) -> np.ndarray:
    count = min(len(samples), max(1, int(SAMPLE_RATE * seconds)))
    window = np.ones(len(samples), dtype=np.float64)
    window[-count:] = np.linspace(1.0, 0.0, count, endpoint=True)
    return samples * window


def _unit_rms(samples: np.ndarray) -> np.ndarray:
    rms = float(np.sqrt(np.mean(samples * samples)))
    if rms <= 1e-12:
        raise ValueError("synthesised a silent layer")
    return samples / rms


def _transient(tag: str, variant: int, layer: str) -> np.ndarray:
    profile = PROFILES[tag][layer]
    rng = np.random.default_rng(_seed(tag, variant, layer))
    count = round(SAMPLE_RATE * profile["duration_s"])
    time = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    low_hz, high_hz = profile["band_hz"]
    noise = _band_noise(rng, count, low_hz, high_hz)
    click = np.zeros(count, dtype=np.float64)
    click[0] = rng.uniform(0.5, 1.0)
    click = _low_pass(click, LOW_PASS_HZ)
    click /= max(float(np.max(np.abs(click))), 1e-12)
    attack = 1.0 - np.exp(-time * 900.0)
    envelope = attack * np.exp(-time * profile["decay"])
    mixed = (noise + profile["click"] * click) * envelope
    mixed = _low_pass(mixed, LOW_PASS_HZ)
    return _unit_rms(_fade_tail(mixed))


def _body(tag: str, variant: int) -> np.ndarray:
    profile = PROFILES[tag][BODY]
    rng = np.random.default_rng(_seed(tag, variant, BODY))
    count = round(SAMPLE_RATE * profile["duration_s"])
    time = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    modes = profile["modes"]
    sines = np.zeros(count, dtype=np.float64)
    shape = np.zeros(count // 2 + 1, dtype=np.float64)
    frequencies = np.fft.rfftfreq(count, 1.0 / SAMPLE_RATE)
    for frequency, decay, gain in modes:
        phase = rng.uniform(0.0, 2.0 * math.pi)
        sines += (
            gain
            * np.sin(2.0 * math.pi * frequency * time + phase)
            * np.exp(-time * decay)
        )
        width = max(frequency * 0.05, 10.0)
        shape += gain**2.0 * np.exp(-0.5 * ((frequencies - frequency) / width) ** 2.0)
    # A narrow-band noise bed around the same modes keeps the modal spectrum but
    # avoids the very high crest factor of summed pure sines at this loudness.
    noise = np.fft.irfft(
        np.fft.rfft(rng.standard_normal(count)) * np.sqrt(shape), n=count
    )
    noise *= np.exp(-time * min(decay for _frequency, decay, _gain in modes))
    attack = 1.0 - np.exp(-time * 300.0)
    sines *= attack
    noise *= attack
    sines /= max(float(np.sqrt(np.mean(sines * sines))), 1e-12)
    noise /= max(float(np.sqrt(np.mean(noise * noise))), 1e-12)
    mixed = sines + BODY_NOISE_WEIGHT * noise
    mixed = _low_pass(mixed, LOW_PASS_HZ)
    return _unit_rms(_fade_tail(mixed, 0.015))


def _texture(tag: str, variant: int) -> np.ndarray:
    profile = PROFILES[tag][TEXTURE]
    rng = np.random.default_rng(_seed(tag, variant, TEXTURE))
    count = round(SAMPLE_RATE * profile["duration_s"])
    time = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    low_hz, high_hz = profile["band_hz"]
    grain_count = max(1, int(profile["grain_count"]))
    grain_length = max(2, int(SAMPLE_RATE * profile["grain_ms"] / 1000.0))
    source = _band_noise(rng, count + grain_length, low_hz, high_hz)
    grains = np.zeros(count, dtype=np.float64)
    grain_time = np.arange(grain_length, dtype=np.float64) / SAMPLE_RATE
    grain_envelope = np.exp(-grain_time * profile["grain_decay"])
    for _grain in range(grain_count):
        start = int(rng.integers(0, count - 1))
        length = min(grain_length, count - start)
        amplitude = rng.uniform(0.25, 1.0)
        grains[start : start + length] += (
            amplitude * source[start : start + length] * grain_envelope[:length]
        )
    bed = _band_noise(rng, count, low_hz, high_hz) * np.exp(
        -time * profile["bed_decay"]
    )
    mixed = grains + profile["bed_gain"] * bed
    mixed *= np.exp(-time * profile["decay"])
    mixed *= 1.0 - np.exp(-time * 800.0)
    mixed = _low_pass(mixed, LOW_PASS_HZ)
    return _unit_rms(_fade_tail(mixed))


def _onset_ms(tag: str, variant: int, layer: str) -> float:
    rng = np.random.default_rng(_seed(tag, variant, "onset"))
    transient_ms = rng.uniform(0.0, 1.5)
    body_ms = rng.uniform(2.0, 5.0)
    texture_ms = rng.uniform(4.5, MAX_ONSET_MS)
    if layer in (TRANSIENT_SOFT, TRANSIENT_HARD):
        return transient_ms
    if layer == BODY:
        return body_ms
    return texture_ms


def _delay(samples: np.ndarray, milliseconds: float) -> np.ndarray:
    lead = round(SAMPLE_RATE * milliseconds / 1000.0)
    return np.concatenate((np.zeros(lead, dtype=np.float64), samples))


def _synthesised_layers(tag: str, variant: int) -> dict[str, np.ndarray]:
    gains = PROFILES[tag]["layer_gain"]
    layers = {
        TRANSIENT_SOFT: _transient(tag, variant, TRANSIENT_SOFT),
        TRANSIENT_HARD: _transient(tag, variant, TRANSIENT_HARD),
        BODY: _body(tag, variant),
        TEXTURE: _texture(tag, variant),
    }
    prepared = {}
    for layer, samples in layers.items():
        gain_key = "transient" if layer.startswith("transient") else layer
        prepared[layer] = _delay(
            samples * gains[gain_key], _onset_ms(tag, variant, layer)
        )
    length = max(len(samples) for samples in prepared.values())
    mix = np.zeros(length, dtype=np.float64)
    for layer in MIX_LAYERS:
        mix[: len(prepared[layer])] += prepared[layer]
    mix_rms = float(np.sqrt(np.mean(mix * mix)))
    scale = 10.0 ** (LOUDNESS_TARGET_DBFS / 20.0) / max(mix_rms, 1e-12)
    peak = float(np.max(np.abs(mix))) * scale
    if peak > PEAK_LIMIT:
        scale *= PEAK_LIMIT / peak
    return {layer: samples * scale for layer, samples in prepared.items()}


def _wav_bytes(samples: np.ndarray) -> bytes:
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _mix_metrics(layers: dict[str, np.ndarray]) -> dict[str, Any]:
    length = max(len(samples) for samples in layers.values())
    mix = np.zeros(length, dtype=np.float64)
    for layer in MIX_LAYERS:
        mix[: len(layers[layer])] += layers[layer]
    rms = float(np.sqrt(np.mean(mix * mix)))
    peak = float(np.max(np.abs(mix)))
    return {
        "rms_dbfs": round(20.0 * math.log10(max(rms, 1e-12)), 3),
        "peak_dbfs": round(20.0 * math.log10(max(peak, 1e-12)), 3),
        "duration_s": round(length / SAMPLE_RATE, 6),
    }


def _manifest_bytes() -> bytes:
    records = []
    mixes = []
    for tag in TAG_SET:
        for variant in range(1, _variant_count(tag) + 1):
            layers = _synthesised_layers(tag, variant)
            for layer in LAYERS:
                data = _wav_bytes(layers[layer])
                profile = PROFILES[tag][layer]
                gain_key = "transient" if layer.startswith("transient") else layer
                records.append(
                    {
                        "tag": tag,
                        "variant": variant,
                        "layer": layer,
                        "path": (
                            AUDIO_DIR / tag / layer / f"{tag}_{layer}_{variant:02d}.wav"
                        ).as_posix(),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data),
                        "duration_s": round(len(layers[layer]) / SAMPLE_RATE, 6),
                        "onset_ms": round(_onset_ms(tag, variant, layer), 3),
                        "script_version": SCRIPT_VERSION,
                        "seed_rule": "sha256(script_version:tag:variant:layer)",
                        "layer_gain": PROFILES[tag]["layer_gain"][gain_key],
                        "parameters": profile,
                    }
                )
            mix = _mix_metrics(layers)
            mixes.append(
                {
                    "tag": tag,
                    "variant": variant,
                    "layers": list(MIX_LAYERS),
                    "transient_tier": TRANSIENT_SOFT,
                    **mix,
                }
            )
    document = {
        "schema_version": 2,
        "script_version": SCRIPT_VERSION,
        "generator": "godot_walk/scripts/generate_footstep_audio.py",
        "sample_rate": SAMPLE_RATE,
        "variant_count": VARIANT_COUNT,
        "tags": list(TAG_SET),
        "layers": list(LAYERS),
        "mix_layers": list(MIX_LAYERS),
        "optional_layers": {
            "wet": "omitted: no acoustic tag needs a squelch or splash layer"
        },
        "seed_rule": "sha256(script_version:tag:variant:layer)",
        "loudness": {
            "target_dbfs": LOUDNESS_TARGET_DBFS,
            "audit_transient_tier": TRANSIENT_SOFT,
            "peak_limit": PEAK_LIMIT,
        },
        "low_pass_hz": LOW_PASS_HZ,
        "max_stem_seconds": MAX_STEM_SECONDS,
        "profiles": PROFILES,
        "records": records,
        "mixes": mixes,
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def generate() -> dict[str, Any]:
    created = 0
    for record in _records():
        layers = _synthesised_layers(record["tag"], record["variant"])
        data = _wav_bytes(layers[record["layer"]])
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
        layers = _synthesised_layers(record["tag"], record["variant"])
        if path.read_bytes() != _wav_bytes(layers[record["layer"]]):
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
