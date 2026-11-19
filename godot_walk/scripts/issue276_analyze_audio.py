"""Issue #276 — convert a Godot Movie Maker recording into agent-readable measurements.

New file only. Reads any container ffmpeg can decode (.avi with PCM, or the
sibling .wav of a .png movie), normalises to 48 kHz mono PCM WAV and emits a
deterministic measurement JSON: duration, peak, RMS per frame, clipping count,
silence intervals, per-band energy, spectral centroid and a *documented,
uncalibrated* decay-time estimate.

Numeric measurements do not replace operator listening. This tool never claims
that a sound is acceptable, correct, or identifiable as a material or room.

Usage:
    python3 godot_walk/scripts/issue276_analyze_audio.py measure --input F --output J [--wav W]
    python3 godot_walk/scripts/issue276_analyze_audio.py verify --measurement J --expect E
    python3 godot_walk/scripts/issue276_analyze_audio.py compare --a J1 --b J2 [--output J]
    python3 godot_walk/scripts/issue276_analyze_audio.py selftest [--output J]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import canonical_bytes, write_deterministic

TARGET_RATE_HZ = 48000
TARGET_CHANNELS = 1
DEFAULT_FRAME_MS = 100
DEFAULT_HOP_MS = 50
SILENCE_THRESHOLD_DBFS = -60.0
MIN_SILENCE_SECONDS = 0.2
CLIPPING_THRESHOLD = 0.999
DECAY_DROP_DB = 20.0
BANDS_HZ: tuple[tuple[str, float, float], ...] = (
    ("sub_bass_20_60", 20.0, 60.0),
    ("bass_60_250", 60.0, 250.0),
    ("low_mid_250_1000", 250.0, 1000.0),
    ("mid_1000_4000", 1000.0, 4000.0),
    ("presence_4000_8000", 4000.0, 8000.0),
    ("brilliance_8000_16000", 8000.0, 16000.0),
    ("air_16000_24000", 16000.0, 24000.0),
)


def require_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise RuntimeError("ffmpeg not found; enter the audioAnalysis nix devShell")
    return executable


def decode_to_wav(source: Path, destination: Path, rate: int = TARGET_RATE_HZ) -> None:
    """Normalise any decodable input to 48 kHz mono 16-bit PCM WAV via ffmpeg."""
    executable = require_ffmpeg()
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        executable, "-nostdin", "-v", "error", "-y", "-i", str(source), "-vn",
        "-ac", str(TARGET_CHANNELS), "-ar", str(rate), "-c:a", "pcm_s16le",
        str(destination),
    ]
    subprocess.run(command, check=True)


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Return float64 mono samples in [-1, 1] and the sample rate."""
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if rate <= 0 or channels <= 0 or width not in (1, 2, 3, 4):
        raise ValueError(f"unsupported WAV layout: rate={rate} channels={channels} width={width}")
    samples = _unpack_pcm(frames, width)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def _unpack_pcm(frames: bytes, width: int) -> np.ndarray:
    if width == 1:
        return (np.frombuffer(frames, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    if width == 2:
        return np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    if width == 3:
        values = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3).astype(np.int64)
        packed = values[:, 0] | (values[:, 1] << 8) | (values[:, 2] << 16)
        packed = np.where(packed >= 1 << 23, packed - (1 << 24), packed)
        return packed.astype(np.float64) / float(1 << 23)
    return np.frombuffer(frames, dtype="<i4").astype(np.float64) / 2147483648.0


def _dbfs(amplitude: float) -> float | None:
    if amplitude <= 0.0:
        return None
    return round(float(20.0 * np.log10(amplitude)), 4)


def _window(samples: np.ndarray, rate: int, frame_ms: int, hop_ms: int) -> list[tuple[int, int]]:
    frame = max(1, int(rate * frame_ms / 1000.0))
    hop = max(1, int(rate * hop_ms / 1000.0))
    if samples.size < frame:
        return [(0, samples.size)]
    return [(start, min(start + frame, samples.size)) for start in range(0, samples.size, hop)]


def _frame_metrics(
    samples: np.ndarray, rate: int, frame_ms: int, hop_ms: int
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for start, end in _window(samples, rate, frame_ms, hop_ms):
        block = samples[start:end]
        if block.size == 0:
            continue
        rms = float(np.sqrt(np.mean(np.square(block))))
        clipped = int(np.count_nonzero(np.abs(block) >= CLIPPING_THRESHOLD))
        records.append({
            "start_s": round(start / rate, 6),
            "end_s": round(end / rate, 6),
            "rms_dbfs": _dbfs(rms),
            "peak_dbfs": _dbfs(float(np.max(np.abs(block)))),
            "clipped_samples": clipped,
        })
    return records


def _clipping(samples: np.ndarray, rate: int) -> dict[str, Any]:
    mask = np.abs(samples) >= CLIPPING_THRESHOLD
    count = int(np.count_nonzero(mask))
    indices = np.flatnonzero(np.diff(np.concatenate(([0], mask.view(np.int8), [0]))))
    runs = [(int(indices[i]), int(indices[i + 1])) for i in range(0, indices.size, 2)]
    intervals = [
        {"start_s": round(begin / rate, 6), "end_s": round(end / rate, 6)}
        for begin, end in runs
    ]
    return {
        "threshold_linear": CLIPPING_THRESHOLD,
        "sample_count": count,
        "run_count": len(runs),
        "longest_run_samples": max((end - begin for begin, end in runs), default=0),
        "intervals": intervals,
    }


def _silence(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    quiet = [
        frame for frame in frames
        if frame["rms_dbfs"] is None or frame["rms_dbfs"] <= SILENCE_THRESHOLD_DBFS
    ]
    intervals: list[dict[str, Any]] = []
    for frame in quiet:
        if intervals and frame["start_s"] <= intervals[-1]["end_s"] + 0.001:
            intervals[-1]["end_s"] = max(intervals[-1]["end_s"], frame["end_s"])
        else:
            intervals.append({"start_s": frame["start_s"], "end_s": frame["end_s"]})
    return [
        interval for interval in intervals
        if interval["end_s"] - interval["start_s"] >= MIN_SILENCE_SECONDS
    ]


def _spectrum(samples: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    window_samples = min(samples.size, 4096)
    if window_samples < 2:
        return np.array([0.0]), np.zeros(1)
    window = np.hanning(window_samples)
    power = np.zeros(window_samples // 2 + 1, dtype=np.float64)
    starts = range(0, max(1, samples.size - window_samples + 1), window_samples // 2)
    for start in starts:
        block = samples[start:start + window_samples] * window
        power += np.square(np.abs(np.fft.rfft(block)))
    return np.fft.rfftfreq(window_samples, 1.0 / rate), power / max(1, len(starts))


def _band_energies(frequencies: np.ndarray, power: np.ndarray) -> dict[str, dict[str, float]]:
    total = float(np.sum(power))
    result: dict[str, dict[str, float]] = {}
    for name, low, high in BANDS_HZ:
        selected = power[(frequencies >= low) & (frequencies < high)]
        energy = float(np.sum(selected))
        result[name] = {
            "low_hz": low,
            "high_hz": high,
            "energy_db": round(float(10.0 * np.log10(energy + 1e-20)), 4),
            "energy_fraction": round(energy / total, 8) if total > 0.0 else 0.0,
        }
    return result


def _centroid(frequencies: np.ndarray, power: np.ndarray) -> float | None:
    total = float(np.sum(power))
    if total <= 0.0:
        return None
    return round(float(np.sum(frequencies * power) / total), 4)


def _decay(frames: list[dict[str, Any]]) -> dict[str, Any]:
    levels = [(frame["start_s"], frame["rms_dbfs"]) for frame in frames]
    levels = [(time, level) for time, level in levels if level is not None]
    if len(levels) < 2:
        return {"t20_seconds": None, "t60_extrapolated_seconds": None, "basis": "no signal"}
    peak = max(level for _, level in levels)
    target = peak - DECAY_DROP_DB
    for (time_a, level_a), (time_b, level_b) in pairwise(levels):
        if level_a >= target >= level_b and level_a > level_b:
            fraction = (level_a - target) / (level_a - level_b)
            t20 = time_a + fraction * (time_b - time_a)
            return {
                "t20_seconds": round(t20, 6),
                "t60_extrapolated_seconds": round(t20 * 3.0, 6),
                "basis": "linear interpolation of frame RMS; uncalibrated, not an RT60 claim",
            }
    return {
        "t20_seconds": None,
        "t60_extrapolated_seconds": None,
        "basis": f"level never dropped {DECAY_DROP_DB:.0f} dB within the capture",
    }


def measure(
    samples: np.ndarray,
    rate: int,
    *,
    frame_ms: int = DEFAULT_FRAME_MS,
    hop_ms: int = DEFAULT_HOP_MS,
) -> dict[str, Any]:
    frames = _frame_metrics(samples, rate, frame_ms, hop_ms)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
    # Near-full-scale samples (e.g. a deliberately clipped segment) inject
    # broadband energy into an FFT. Exclude them from spectral estimates only;
    # peak, RMS and clipping counts always use the untouched samples.
    spectral_samples = samples.copy()
    spectral_samples[np.abs(spectral_samples) >= CLIPPING_THRESHOLD] = 0.0
    frequencies, power = _spectrum(spectral_samples, rate)
    return {
        "schema_version": 1,
        "generator": "godot_walk/scripts/issue276_analyze_audio.py",
        "measurement_only": True,
        "operator_listening": "required; no sound is declared acceptable by an agent",
        "sample_rate_hz": rate,
        "channels": 1,
        "duration_seconds": round(samples.size / rate, 6),
        "peak_linear": round(peak, 8),
        "peak_dbfs": _dbfs(peak),
        "rms_linear": round(rms, 8),
        "rms_dbfs": _dbfs(rms),
        "clipping": _clipping(samples, rate),
        "silence_threshold_dbfs": SILENCE_THRESHOLD_DBFS,
        "min_silence_seconds": MIN_SILENCE_SECONDS,
        "silence_intervals": _silence(frames),
        "frame_ms": frame_ms,
        "hop_ms": hop_ms,
        "frames": frames,
        "bands": _band_energies(frequencies, power),
        "spectral_centroid_hz": _centroid(frequencies, power),
        "decay_estimate": _decay(frames),
        "fft_window": "Hann, 4096 samples, 50% overlap, averaged power; clipped samples excluded",
    }


def verify(measurement: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    """Return a list of failures; empty list means all expectations were met."""
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str) -> None:
        if not condition:
            failures.append(f"{label}: {detail}")

    tolerance_hz = float(expect.get("tone_tolerance_hz", 120.0))
    if "tone_hz" in expect:
        centroid = measurement.get("spectral_centroid_hz")
        target = float(expect["tone_hz"])
        check(
            "spectral_centroid",
            centroid is not None and abs(float(centroid) - target) <= tolerance_hz,
            f"expected {target:.1f} +/- {tolerance_hz:.1f} Hz, got {centroid}",
        )
    if "min_peak" in expect:
        peak = float(measurement.get("peak_linear", 0.0))
        check("peak", peak >= float(expect["min_peak"]), f"expected >= {expect['min_peak']}, got {peak}")
    if "max_peak" in expect:
        peak = float(measurement.get("peak_linear", 0.0))
        check("peak", peak <= float(expect["max_peak"]), f"expected <= {expect['max_peak']}, got {peak}")
    for key in ("min_duration_seconds", "max_duration_seconds"):
        if key in expect:
            duration = float(measurement.get("duration_seconds", 0.0))
            limit = float(expect[key])
            ok = duration >= limit if key.startswith("min") else duration <= limit
            check(key, ok, f"expected {key}={limit}, got {duration}")
    if expect.get("require_clipping"):
        count = int(measurement.get("clipping", {}).get("sample_count", 0))
        check("clipping", count > 0, "no near-full-scale samples found")
    if "min_clipped_samples" in expect:
        count = int(measurement.get("clipping", {}).get("sample_count", 0))
        check("clipped_samples", count >= int(expect["min_clipped_samples"]), f"got {count}")
    if "max_clipped_samples" in expect:
        count = int(measurement.get("clipping", {}).get("sample_count", 0))
        check("clipped_samples", count <= int(expect["max_clipped_samples"]), f"got {count}")
    if "min_nonquiet_frames" in expect:
        frames = measurement.get("frames", [])
        loud = sum(1 for frame in frames if (frame.get("rms_dbfs") or -999.0) > -60.0)
        check("nonquiet_frames", loud >= int(expect["min_nonquiet_frames"]), f"got {loud}")
    if expect.get("require_silence"):
        count = len(measurement.get("silence_intervals", []))
        check("silence", count > 0, "no qualifying silence interval found")
    return failures


def command_measure(arguments: argparse.Namespace) -> int:
    source = Path(arguments.input)
    if not source.is_file():
        raise SystemExit(f"input does not exist: {source}")
    with tempfile.TemporaryDirectory(prefix="issue276-") as temporary:
        normalised = Path(temporary) / "audio_48k_mono.wav"
        decode_to_wav(source, normalised)
        samples, rate = read_wav(normalised)
        result = measure(samples, rate, frame_ms=arguments.frame_ms, hop_ms=arguments.hop_ms)
    if arguments.wav:
        decode_to_wav(source, Path(arguments.wav))
    status = write_deterministic(Path(arguments.output), canonical_bytes(result))
    print(f"ISSUE276_MEASURE source={source.name} duration={result['duration_seconds']}s "
          f"peak={result['peak_dbfs']}dBFS centroid={result['spectral_centroid_hz']}Hz write={status}")
    print(f"ISSUE276_MEASURE_JSON {arguments.output}")
    return 0


def command_compare(arguments: argparse.Namespace) -> int:
    first = json.loads(Path(arguments.a).read_text(encoding="utf-8"))
    second = json.loads(Path(arguments.b).read_text(encoding="utf-8"))
    frame_a = [(f["start_s"], f["rms_dbfs"], f["peak_dbfs"], f["clipped_samples"]) for f in first["frames"]]
    frame_b = [(f["start_s"], f["rms_dbfs"], f["peak_dbfs"], f["clipped_samples"]) for f in second["frames"]]
    result = {
        "json_identical": first == second,
        "frames_identical": frame_a == frame_b,
        "duration_delta_s": round(abs(first["duration_seconds"] - second["duration_seconds"]), 9),
        "peak_delta_linear": round(abs(first["peak_linear"] - second["peak_linear"]), 9),
        "rms_delta_linear": round(abs(first["rms_linear"] - second["rms_linear"]), 9),
        "centroid_delta_hz": round(abs(first["spectral_centroid_hz"] - second["spectral_centroid_hz"]), 9),
        "clipping_delta_samples": abs(first["clipping"]["sample_count"] - second["clipping"]["sample_count"]),
        "tolerances": {
            "duration_delta_s": 1e-6,
            "peak_delta_linear": 1e-6,
            "rms_delta_linear": 1e-6,
            "centroid_delta_hz": 1e-3,
            "clipping_delta_samples": 0,
        },
    }
    tolerances = result["tolerances"]
    result["pass"] = (
        result["frames_identical"]
        and result["duration_delta_s"] <= tolerances["duration_delta_s"]
        and result["peak_delta_linear"] <= tolerances["peak_delta_linear"]
        and result["rms_delta_linear"] <= tolerances["rms_delta_linear"]
        and result["centroid_delta_hz"] <= tolerances["centroid_delta_hz"]
        and result["clipping_delta_samples"] <= tolerances["clipping_delta_samples"]
    )
    if arguments.output:
        write_deterministic(Path(arguments.output), canonical_bytes(result))
    print(f"ISSUE276_DETERMINISM {'PASS' if result['pass'] else 'FAIL'} "
          f"json_identical={result['json_identical']} frames_identical={result['frames_identical']} "
          f"peak_delta={result['peak_delta_linear']} rms_delta={result['rms_delta_linear']} "
          f"centroid_delta={result['centroid_delta_hz']}")
    return 0 if result["pass"] else 1


def command_verify(arguments: argparse.Namespace) -> int:
    measurement = json.loads(Path(arguments.measurement).read_text(encoding="utf-8"))
    expect = json.loads(Path(arguments.expect).read_text(encoding="utf-8"))
    failures = verify(measurement, expect)
    for failure in failures:
        print(f"ISSUE276_VERIFY FAIL {failure}")
    if not failures:
        print(f"ISSUE276_VERIFY PASS checks={len(expect)} measurement={arguments.measurement}")
    return 1 if failures else 0


def _synthetic_wav(path: Path) -> None:
    """Locally synthesised silence + 440 Hz tone + full-scale clip + silence."""
    rate = TARGET_RATE_HZ
    pieces = [
        np.zeros(int(rate * 0.75)),
        (np.sin(2.0 * np.pi * 440.0 * np.arange(rate) / rate) * 0.25),
        np.where(np.arange(rate // 2) % 2 == 0, 1.0, -1.0),
        np.zeros(int(rate * 0.75)),
    ]
    samples = np.concatenate(pieces)
    pcm = np.clip(np.rint(samples * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def command_selftest(arguments: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="issue276-selftest-") as temporary:
        wav_path = Path(temporary) / "synthetic.wav"
        _synthetic_wav(wav_path)
        samples, rate = read_wav(wav_path)
        result = measure(samples, rate)
    expect = {
        "tone_hz": 440.0,
        "tone_tolerance_hz": 120.0,
        "min_peak": 0.99,
        "max_peak": 1.0,
        "require_clipping": True,
        "min_clipped_samples": 20000,
        "require_silence": True,
        "min_duration_seconds": 2.9,
        "max_duration_seconds": 3.1,
    }
    failures = verify(result, expect)
    for failure in failures:
        print(f"ISSUE276_SELFTEST FAIL {failure}")
    if not failures:
        print("ISSUE276_SELFTEST PASS tone=440Hz clipping=detected silence=detected")
    if arguments.output:
        write_deterministic(Path(arguments.output), canonical_bytes(result))
        print(f"ISSUE276_SELFTEST_JSON {arguments.output}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    measure_parser = subcommands.add_parser("measure")
    measure_parser.add_argument("--input", required=True)
    measure_parser.add_argument("--output", required=True)
    measure_parser.add_argument("--wav")
    measure_parser.add_argument("--frame-ms", type=int, default=DEFAULT_FRAME_MS)
    measure_parser.add_argument("--hop-ms", type=int, default=DEFAULT_HOP_MS)
    measure_parser.set_defaults(handler=command_measure)
    verify_parser = subcommands.add_parser("verify")
    verify_parser.add_argument("--measurement", required=True)
    verify_parser.add_argument("--expect", required=True)
    verify_parser.set_defaults(handler=command_verify)
    compare_parser = subcommands.add_parser("compare")
    compare_parser.add_argument("--a", required=True)
    compare_parser.add_argument("--b", required=True)
    compare_parser.add_argument("--output")
    compare_parser.set_defaults(handler=command_compare)
    selftest_parser = subcommands.add_parser("selftest")
    selftest_parser.add_argument("--output")
    selftest_parser.set_defaults(handler=command_selftest)
    arguments = parser.parse_args(argv)
    return arguments.handler(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
