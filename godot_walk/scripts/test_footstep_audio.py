"""Determinism, coverage and loudness tests for the #203 footstep stems."""

from __future__ import annotations

import hashlib
import json
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT
from footstep_audit import LOUDNESS_TARGET_DBFS as AUDIT_LOUDNESS_TARGET_DBFS
from generate_footstep_audio import (
    DEFAULT_TAG,
    LAND_TAG,
    LAYERS,
    LOUDNESS_TARGET_DBFS,
    MANIFEST_PATH,
    MAX_STEM_SECONDS,
    SAMPLE_RATE,
    SCRIPT_VERSION,
    TAGS,
    VARIANT_COUNT,
    check,
)

AUDIT_TOLERANCE_DB = 1.5


def _manifest() -> dict:
    return json.loads((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))


def _expected_variants(tag: str) -> int:
    return 1 if tag == LAND_TAG else VARIANT_COUNT


def test_footstep_audio_is_deterministic_and_complete():
    assert check() == []
    manifest = _manifest()
    assert manifest["script_version"] == SCRIPT_VERSION
    assert manifest["sample_rate"] == SAMPLE_RATE
    assert manifest["layers"] == list(LAYERS)
    assert manifest["seed_rule"] == "sha256(script_version:tag:variant:layer)"
    records = manifest["records"]
    for tag in (*TAGS, DEFAULT_TAG, LAND_TAG):
        expected_variants = _expected_variants(tag)
        tag_records = [record for record in records if record["tag"] == tag]
        assert len(tag_records) == expected_variants * len(LAYERS), tag
        for variant in range(1, expected_variants + 1):
            for layer in LAYERS:
                matches = [
                    record
                    for record in tag_records
                    if record["variant"] == variant and record["layer"] == layer
                ]
                assert len(matches) == 1, f"{tag}/{layer}/{variant}"
                record = matches[0]
                path = ROOT / record["path"]
                assert path.is_file(), record["path"]
                with wave.open(str(path), "rb") as stream:
                    assert stream.getnchannels() == 1
                    assert stream.getsampwidth() == 2
                    assert stream.getframerate() == SAMPLE_RATE
                    duration = stream.getnframes() / stream.getframerate()
                assert 0.02 <= duration <= MAX_STEM_SECONDS
                assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
                assert 0.0 <= record["onset_ms"] <= 8.0
                assert record["parameters"]


def test_loudness_target_matches_the_202_audit():
    assert LOUDNESS_TARGET_DBFS == AUDIT_LOUDNESS_TARGET_DBFS


def test_every_mix_hits_the_202_loudness_target():
    manifest = _manifest()
    mixes = manifest["mixes"]
    assert len(mixes) == (len(TAGS) + 1) * VARIANT_COUNT + 1
    for mix in mixes:
        assert mix["layers"] == ["transient_soft", "body", "texture"]
        assert mix["duration_s"] <= MAX_STEM_SECONDS
        assert mix["peak_dbfs"] <= 0.0
        assert abs(mix["rms_dbfs"] - LOUDNESS_TARGET_DBFS) <= AUDIT_TOLERANCE_DB, mix
