"""Determinism and coverage tests for the #200 footstep samples."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT
from generate_footstep_audio import (
    DEFAULT_TAG,
    MANIFEST_PATH,
    SAMPLE_RATE,
    TAGS,
    VARIANT_COUNT,
    check,
)


def test_footstep_audio_is_deterministic_and_complete():
    assert check() == []
    manifest = json.loads((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    assert manifest["sample_rate"] == SAMPLE_RATE
    records = manifest["records"]
    for tag in (*TAGS, DEFAULT_TAG):
        files = [record for record in records if record["tag"] == tag]
        assert len(files) == VARIANT_COUNT, tag
        for record in files:
            path = ROOT / record["path"]
            assert path.is_file()
            with wave.open(str(path), "rb") as stream:
                assert stream.getnchannels() == 1
                assert stream.getsampwidth() == 2
                assert stream.getframerate() == SAMPLE_RATE
                duration = stream.getnframes() / stream.getframerate()
                assert 0.15 <= duration <= 0.30
    land = [record for record in records if record["tag"] == "land"]
    assert len(land) == 1
    assert (ROOT / land[0]["path"]).is_file()
