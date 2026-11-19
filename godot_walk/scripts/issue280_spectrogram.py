"""Issue #280 — deterministic ffmpeg spectrogram/waveform renders for #276 captures.

New file only. The #276 capture already writes a 48 kHz mono WAV plus a
measurement JSON. This module adds a *picture* of the same sound so an agent can
inspect transients, decay tails, band content and clipping visually in addition
to reading numbers. It never claims a sound is acceptable, correct, or
identifiable as a material or room; the operator still listens.

Every render uses fixed, documented parameters so two captures are comparable
and the same WAV yields byte-identical PNGs. PNGs are written under the
already git-ignored evidence tree (``godot_walk/evidence/**/*.png``).

Usage:
    python3 godot_walk/scripts/issue280_spectrogram.py render --input WAV --output PNG [--waveform PNG]
    python3 godot_walk/scripts/issue280_spectrogram.py selftest
    python3 godot_walk/scripts/issue280_spectrogram.py determinism --input WAV
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The exact #276 440 Hz tone + full-scale clip + silence fixture.
from issue276_analyze_audio import _synthetic_wav

# Fixed render parameters. Do not change without updating the #280 REPORT.md:
# two captures are comparable only because these values are identical.
SPECTROGRAM_SIZE = "1600x900"
SPECTROGRAM_MODE = "combined"
SPECTROGRAM_SCALE = "log"       # amplitude (dB) colour scale
SPECTROGRAM_FSCALE = "log"      # logarithmic frequency axis
SPECTROGRAM_START_HZ = 20
SPECTROGRAM_STOP_HZ = 24000     # 48 kHz Nyquist: shows the #276 clip near 24 kHz
SPECTROGRAM_DRANGE_DB = 80      # fixed dB window, 0 .. -80 dBFS
SPECTROGRAM_LIMIT_DBFS = 0
SPECTROGRAM_COLOR = "intensity"
SPECTROGRAM_LEGEND = True       # production PNGs carry readable axis labels
CHECK_LEGEND = False            # machine-checked PNGs omit the grid/legend
WIN_FUNC = "hann"               # showspectrumpic default FFT window
WAVEFORM_SIZE = "1600x220"
WAVEFORM_SCALE = "lin"

# Mechanical-check constants for the #276 synthetic fixture (3.0 s).
SILENCE_MAX_COLUMN = 0.01       # normalised mean brightness of a silent column
TONE_X = (450, 900)             # 0.75-1.75 s tone, with time-smear margin
CLIP_X = (980, 1180)            # 1.75-2.25 s clipped segment
SILENCE_X = ((50, 350), (1250, 1550))
TONE_PEAK_ROW_TOLERANCE = 8     # rows; calibration render defines the 440 Hz row
CLIP_BROADBAND_MIN_ROWS = 40    # rows >15/255 in the clip region
CLIP_TOP_MAX_ROW = 60           # clip energy peaks near the top (high frequency)

SPECTROGRAM_PARAMETERS = {
    "filter": "showspectrumpic",
    "size": SPECTROGRAM_SIZE,
    "mode": SPECTROGRAM_MODE,
    "scale": SPECTROGRAM_SCALE,
    "fscale": SPECTROGRAM_FSCALE,
    "start_hz": SPECTROGRAM_START_HZ,
    "stop_hz": SPECTROGRAM_STOP_HZ,
    "drange_db": SPECTROGRAM_DRANGE_DB,
    "limit_dbfs": SPECTROGRAM_LIMIT_DBFS,
    "color": SPECTROGRAM_COLOR,
    "legend": SPECTROGRAM_LEGEND,
    "window": WIN_FUNC,
    "waveform_filter": "showwavespic",
    "waveform_size": WAVEFORM_SIZE,
    "waveform_scale": WAVEFORM_SCALE,
}


def require_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise RuntimeError("ffmpeg not found; enter the audioAnalysis nix devShell")
    return executable


def spectrogram_filter(legend: bool = SPECTROGRAM_LEGEND) -> str:
    """Build the fixed showspectrumpic filter string."""
    return (
        f"showspectrumpic=s={SPECTROGRAM_SIZE}:mode={SPECTROGRAM_MODE}"
        f":scale={SPECTROGRAM_SCALE}:fscale={SPECTROGRAM_FSCALE}"
        f":start={SPECTROGRAM_START_HZ}:stop={SPECTROGRAM_STOP_HZ}"
        f":drange={SPECTROGRAM_DRANGE_DB}:limit={SPECTROGRAM_LIMIT_DBFS}"
        f":color={SPECTROGRAM_COLOR}:legend={str(legend).lower()}"
        f":win_func={WIN_FUNC}"
    )


def render_spectrogram(wav: Path, output: Path, *, legend: bool = SPECTROGRAM_LEGEND) -> Path:
    """Render one spectrogram PNG from a WAV; refuse to overwrite via ffmpeg -n."""
    if not Path(wav).is_file():
        raise SystemExit(f"input WAV does not exist: {wav}")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        require_ffmpeg(), "-nostdin", "-v", "error", "-n", "-i", str(wav),
        "-filter_complex", spectrogram_filter(legend), "-frames:v", "1", str(output),
    ]
    subprocess.run(command, check=True)
    return output


def render_waveform(wav: Path, output: Path) -> Path:
    """Render the optional waveform PNG from a WAV."""
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        require_ffmpeg(), "-nostdin", "-v", "error", "-n", "-i", str(wav),
        "-filter_complex",
        f"showwavespic=s={WAVEFORM_SIZE}:scale={WAVEFORM_SCALE}:split_channels=false",
        "-frames:v", "1", str(output),
    ]
    subprocess.run(command, check=True)
    return output


def decode_gray(png: Path, width: int, height: int) -> np.ndarray:
    """Decode a PNG to an (height, width) uint8 grayscale array via ffmpeg."""
    raw = subprocess.run(
        [require_ffmpeg(), "-nostdin", "-v", "error", "-i", str(png),
         "-vf", "format=gray", "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    ).stdout
    expected = width * height
    if len(raw) != expected:
        raise ValueError(f"{png}: expected {expected} gray bytes, got {len(raw)}")
    return np.frombuffer(raw, dtype=np.uint8).reshape(height, width).astype(np.float64)


def png_dimensions(png: Path) -> tuple[int, int]:
    """Return the actual (width, height) of a PNG via ffprobe.

    The legend adds margins, so a legend render is 1884x1028 even though the
    configured filter size is 1600x900. Legend-free check renders are exactly
    1600x900.
    """
    executable = shutil.which("ffprobe")
    if executable is None:
        raise RuntimeError("ffprobe not found; enter the audioAnalysis nix devShell")
    result = subprocess.run(
        [executable, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(png)],
        capture_output=True, text=True, check=True,
    )
    width, height = (int(value) for value in result.stdout.strip().split(",")[:2])
    return width, height


def image_size(png: Path) -> tuple[int, int]:
    """Dimensions expected of a legend-free mechanical-check render."""
    width, height = png_dimensions(png)
    if f"{width}x{height}" != SPECTROGRAM_SIZE:
        raise ValueError(f"{png}: expected a {SPECTROGRAM_SIZE} legend-free render")
    return width, height


def peak_row(image: np.ndarray, x_range: tuple[int, int]) -> int:
    """Row (0 = top) carrying the most mean energy across an x range."""
    return int(np.argmax(image[:, x_range[0]:x_range[1]].mean(axis=1)))


def broadband_rows(image: np.ndarray, x_range: tuple[int, int], threshold: float) -> int:
    """Count rows whose mean brightness exceeds a threshold in an x range."""
    rows = image[:, x_range[0]:x_range[1]].mean(axis=1)
    return int(np.count_nonzero(rows > threshold))


def column_energy(image: np.ndarray, x_range: tuple[int, int]) -> float:
    """Normalised mean brightness of a column range (0.0 = fully black)."""
    return float(image[:, x_range[0]:x_range[1]].mean() / 255.0)


def pure_tone_wav(path: Path, frequency: float = 440.0, duration: float = 1.0) -> None:
    """Write a pure tone for the frequency-to-row calibration render."""
    rate = 48000
    count = int(rate * duration)
    samples = np.sin(2.0 * np.pi * frequency * np.arange(count) / rate) * 0.5
    pcm = np.clip(np.rint(samples * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def mechanical_check(image_path: Path, calibration_path: Path) -> dict[str, Any]:
    """Check the #276 tone/clip/silence layout in a legend-free spectrogram."""
    width, height = image_size(image_path)
    image = decode_gray(image_path, width, height)
    calibration = decode_gray(calibration_path, width, height)
    tone_row = peak_row(image, TONE_X)
    reference_row = peak_row(calibration, (width // 3, 2 * width // 3))
    clip_row = peak_row(image, CLIP_X)
    clip_rows = broadband_rows(image, CLIP_X, 15.0)
    silence = [column_energy(image, span) for span in SILENCE_X]
    checks = {
        "silence_gaps_near_zero": all(value <= SILENCE_MAX_COLUMN for value in silence),
        "tone_at_440hz_row": abs(tone_row - reference_row) <= TONE_PEAK_ROW_TOLERANCE,
        "clip_broadband": clip_rows >= CLIP_BROADBAND_MIN_ROWS,
        "clip_near_nyquist": clip_row <= CLIP_TOP_MAX_ROW,
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "tone_peak_row": tone_row,
        "calibration_440hz_row": reference_row,
        "clip_peak_row": clip_row,
        "clip_broadband_rows": clip_rows,
        "silence_column_energy": [round(value, 6) for value in silence],
        "image_size": f"{width}x{height}",
        "check_legend": CHECK_LEGEND,
        "parameters": SPECTROGRAM_PARAMETERS,  # production parameters (legend=true)
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_render(arguments: argparse.Namespace) -> int:
    wav = Path(arguments.input)
    output = render_spectrogram(wav, Path(arguments.output))
    width, height = png_dimensions(output)
    print(f"ISSUE280_SPECTROGRAM {output} sha256={_sha256(output)} "
          f"size={width}x{height} filter_size={SPECTROGRAM_SIZE} legend=true")
    if arguments.waveform:
        waveform = render_waveform(wav, Path(arguments.waveform))
        print(f"ISSUE280_WAVEFORM {waveform} sha256={_sha256(waveform)} size={WAVEFORM_SIZE}")
    return 0


def command_selftest(arguments: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="issue280-selftest-") as temporary:
        directory = Path(temporary)
        wav, calibration_wav = directory / "synthetic.wav", directory / "440hz.wav"
        _synthetic_wav(wav)
        pure_tone_wav(calibration_wav)
        image = render_spectrogram(wav, directory / "spectrogram.png", legend=CHECK_LEGEND)
        calibration = render_spectrogram(calibration_wav, directory / "calibration.png", legend=CHECK_LEGEND)
        render_waveform(wav, directory / "waveform.png")
        result = mechanical_check(image, calibration)
        result["selftest_signal"] = "issue276 440 Hz tone + full-scale clip + silence gaps"
        if arguments.output:
            from deterministic_json import canonical_bytes, write_deterministic

            write_deterministic(Path(arguments.output), canonical_bytes(result))
            print(f"ISSUE280_SELFTEST_JSON {arguments.output}")
    status = "PASS" if result["pass"] else "FAIL"
    print(f"ISSUE280_SELFTEST {status} tone_row={result['tone_peak_row']} "
          f"clip_row={result['clip_peak_row']} silence={result['silence_column_energy']}")
    return 0 if result["pass"] else 1


def command_determinism(arguments: argparse.Namespace) -> int:
    wav = Path(arguments.input)
    if not wav.is_file():
        raise SystemExit(f"input WAV does not exist: {wav}")
    with tempfile.TemporaryDirectory(prefix="issue280-determinism-") as temporary:
        directory = Path(temporary)
        first = render_spectrogram(wav, directory / "first.png")
        second = render_spectrogram(wav, directory / "second.png")
        digest = _sha256(first)
        identical = digest == _sha256(second)
        width, height = png_dimensions(first)
    print(f"ISSUE280_DETERMINISM {'PASS' if identical else 'FAIL'} "
          f"identical={identical} sha256={digest} size={width}x{height}")
    return 0 if identical else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    render_parser = subcommands.add_parser("render")
    render_parser.add_argument("--input", required=True)
    render_parser.add_argument("--output", required=True)
    render_parser.add_argument("--waveform")
    render_parser.set_defaults(handler=command_render)
    selftest_parser = subcommands.add_parser("selftest")
    selftest_parser.add_argument("--output")
    selftest_parser.set_defaults(handler=command_selftest)
    determinism_parser = subcommands.add_parser("determinism")
    determinism_parser.add_argument("--input", required=True)
    determinism_parser.set_defaults(handler=command_determinism)
    arguments = parser.parse_args(argv)
    return arguments.handler(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
