"""Tests for the issue #276 WAV-to-measurement step (CPU-only, no Godot)."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import issue276_analyze_audio as analyser
from deterministic_json import canonical_bytes

EXPECT = {
    "tone_hz": 440.0,
    "tone_tolerance_hz": 120.0,
    "min_peak": 0.99,
    "max_peak": 1.0,
    "min_clipped_samples": 20000,
    "require_clipping": True,
    "require_silence": True,
    "min_duration_seconds": 2.9,
    "max_duration_seconds": 3.1,
}


def _synthetic_measurement() -> dict:
    import tempfile

    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "tone.wav"
        analyser._synthetic_wav(path)
        samples, rate = analyser.read_wav(path)
    return analyser.measure(samples, rate)


def test_synthetic_tone_clip_and_silence_are_recovered() -> None:
    result = _synthetic_measurement()
    assert analyser.verify(result, EXPECT) == []
    assert result["spectral_centroid_hz"] == pytest.approx(440.0, abs=120.0)
    assert result["clipping"]["sample_count"] >= 20000
    assert len(result["silence_intervals"]) >= 2


def test_wrong_tone_fails_verification() -> None:
    result = _synthetic_measurement()
    failures = analyser.verify(result, {"tone_hz": 1000.0, "tone_tolerance_hz": 10.0})
    assert any("spectral_centroid" in failure for failure in failures)


def test_clip_is_excluded_from_spectral_estimate() -> None:
    result = _synthetic_measurement()
    assert result["clipping"]["run_count"] == 1
    assert result["bands"]["low_mid_250_1000"]["energy_fraction"] > 0.9


def test_decay_estimate_is_never_an_rt60_claim() -> None:
    result = _synthetic_measurement()
    assert "uncalibrated" in result["decay_estimate"]["basis"] or "never dropped" in result["decay_estimate"]["basis"]
    assert result["measurement_only"] is True
    assert "required" in result["operator_listening"]


def test_measurement_json_is_canonical_and_repeatable() -> None:
    first = _synthetic_measurement()
    second = _synthetic_measurement()
    assert canonical_bytes(first) == canonical_bytes(second)
    assert json.loads(canonical_bytes(first)) == first


def test_compare_command_passes_identical_and_fails_different(tmp_path: Path) -> None:
    measurement = _synthetic_measurement()
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    first.write_bytes(canonical_bytes(measurement))
    second.write_bytes(canonical_bytes(measurement))
    assert analyser.main(["compare", "--a", str(first), "--b", str(second)]) == 0
    altered = dict(measurement)
    altered["peak_linear"] = measurement["peak_linear"] + 0.1
    second.write_bytes(canonical_bytes(altered))
    assert analyser.main(["compare", "--a", str(first), "--b", str(second)]) == 1


def test_selftest_command_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert analyser.main(["selftest"]) == 0
    assert "ISSUE276_SELFTEST PASS" in capsys.readouterr().out


def test_unsupported_wav_layout_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.wav"
    path.write_bytes(b"not a wav")
    with pytest.raises((ValueError, wave.Error)):
        analyser.read_wav(path)
