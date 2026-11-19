"""Tests for the issue #280 spectrogram rendering step (CPU-only, no Godot)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import issue280_spectrogram as spectrogram
from issue276_analyze_audio import _synthetic_wav


def _synthetic_wav_file(directory: Path) -> Path:
    path = directory / "synthetic.wav"
    _synthetic_wav(path)
    return path


def test_render_is_byte_identical_for_same_wav(tmp_path: Path) -> None:
    wav = _synthetic_wav_file(tmp_path)
    first = spectrogram.render_spectrogram(wav, tmp_path / "first.png")
    second = spectrogram.render_spectrogram(wav, tmp_path / "second.png")
    assert first.read_bytes() == second.read_bytes()


def test_render_uses_documented_fixed_parameters() -> None:
    filt = spectrogram.spectrogram_filter()
    for expected in ("s=1600x900", "scale=log", "fscale=log", "start=20",
                     "stop=24000", "drange=80", "limit=0", "win_func=hann"):
        assert expected in filt
    assert spectrogram.SPECTROGRAM_PARAMETERS["stop_hz"] == 24000
    assert spectrogram.SPECTROGRAM_PARAMETERS["drange_db"] == 80


def test_decode_gray_shape(tmp_path: Path) -> None:
    wav = _synthetic_wav_file(tmp_path)
    image = spectrogram.render_spectrogram(wav, tmp_path / "gray.png", legend=False)
    width, height = spectrogram.image_size(image)
    assert spectrogram.decode_gray(image, width, height).shape == (height, width)


def test_mechanical_check_recovers_tone_clip_and_silence(tmp_path: Path) -> None:
    wav = _synthetic_wav_file(tmp_path)
    image = spectrogram.render_spectrogram(wav, tmp_path / "image.png", legend=False)
    calibration_wav = tmp_path / "440.wav"
    spectrogram.pure_tone_wav(calibration_wav)
    calibration = spectrogram.render_spectrogram(
        calibration_wav, tmp_path / "calibration.png", legend=False
    )
    result = spectrogram.mechanical_check(image, calibration)
    assert result["pass"] is True
    assert all(result["checks"].values())
    assert abs(result["tone_peak_row"] - result["calibration_440hz_row"]) <= 8
    assert result["clip_broadband_rows"] >= 40
    assert all(value <= 0.01 for value in result["silence_column_energy"])


def test_mechanical_check_rejects_blank_image(tmp_path: Path) -> None:
    calibration_wav = tmp_path / "440.wav"
    spectrogram.pure_tone_wav(calibration_wav)
    calibration = spectrogram.render_spectrogram(
        calibration_wav, tmp_path / "calibration.png", legend=False
    )
    blank = tmp_path / "blank.png"
    import subprocess

    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-n", "-f", "lavfi", "-i",
         "color=c=black:s=1600x900:d=0.04", "-frames:v", "1", str(blank)],
        check=True,
    )
    result = spectrogram.mechanical_check(blank, calibration)
    assert result["pass"] is False
    assert result["checks"]["tone_at_440hz_row"] is False


def test_selftest_command_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert spectrogram.main(["selftest"]) == 0
    assert "ISSUE280_SELFTEST PASS" in capsys.readouterr().out


def test_determinism_command_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    wav = _synthetic_wav_file(tmp_path)
    assert spectrogram.main(["determinism", "--input", str(wav)]) == 0
    assert "ISSUE280_DETERMINISM PASS identical=True" in capsys.readouterr().out


def test_render_command_writes_waveform(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    wav = _synthetic_wav_file(tmp_path)
    output, waveform = tmp_path / "spec.png", tmp_path / "wave.png"
    assert spectrogram.main([
        "render", "--input", str(wav), "--output", str(output), "--waveform", str(waveform)
    ]) == 0
    assert output.is_file() and waveform.is_file()
    out = capsys.readouterr().out
    assert "ISSUE280_SPECTROGRAM" in out and "ISSUE280_WAVEFORM" in out
