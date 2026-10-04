"""
Tests for pipeline_state.py — resumability, hashing, and state recording.

Run with: python3 -m pytest scripts/splat_pipeline/tests/ -v
"""

import json
import sys
from pathlib import Path

import pytest

# conftest.py puts the pipeline directory on sys.path.
import pipeline_state


# ---------------------------------------------------------------------------
# file_hash
# ---------------------------------------------------------------------------


def test_file_hash_returns_sha256(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    hash_value = pipeline_state.file_hash(f)
    assert len(hash_value) == 64
    assert hash_value != ""


def test_file_hash_missing_file_returns_empty(tmp_path):
    assert pipeline_state.file_hash(tmp_path / "nonexistent.txt") == ""


def test_file_hash_detects_changes(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")
    hash1 = pipeline_state.file_hash(f)
    f.write_text("world")
    hash2 = pipeline_state.file_hash(f)
    assert hash1 != hash2


# ---------------------------------------------------------------------------
# compute_hash
# ---------------------------------------------------------------------------


def test_compute_hash_is_deterministic():
    h1 = pipeline_state.compute_hash("a", "b", "c")
    h2 = pipeline_state.compute_hash("a", "b", "c")
    assert h1 == h2


def test_compute_hash_changes_with_input():
    h1 = pipeline_state.compute_hash("a", "b")
    h2 = pipeline_state.compute_hash("a", "c")
    assert h1 != h2


def test_compute_hash_order_matters():
    h1 = pipeline_state.compute_hash("a", "b")
    h2 = pipeline_state.compute_hash("b", "a")
    assert h1 != h2


# ---------------------------------------------------------------------------
# StageRecord
# ---------------------------------------------------------------------------


def test_stage_record_to_dict():
    record = pipeline_state.StageRecord(
        stage="stage_a",
        input_hash="abc123",
        output_hash="def456",
        timestamp="2026-01-01T00:00:00+00:00",
        status="success",
        log_path="logs/stage_a.log",
        detail="test",
    )
    d = record.to_dict()
    assert d["stage"] == "stage_a"
    assert d["input_hash"] == "abc123"
    assert d["output_hash"] == "def456"
    assert d["status"] == "success"
    assert d["log_path"] == "logs/stage_a.log"
    assert d["detail"] == "test"


def test_stage_record_from_dict():
    data = {
        "stage": "stage_b",
        "input_hash": "hash1",
        "output_hash": "hash2",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "status": "failed",
        "log_path": "",
        "detail": "error",
    }
    record = pipeline_state.StageRecord.from_dict(data)
    assert record.stage == "stage_b"
    assert record.status == "failed"


# ---------------------------------------------------------------------------
# load_state / save_state
# ---------------------------------------------------------------------------


def test_load_state_empty_when_no_file(tmp_path):
    assert pipeline_state.load_state(tmp_path) == {}


def test_save_and_load_state(tmp_path):
    record = pipeline_state.StageRecord(
        stage="stage_a",
        input_hash="abc",
        output_hash="def",
        timestamp="2026-01-01T00:00:00+00:00",
        status="success",
    )
    pipeline_state.save_state(tmp_path, {"stage_a": record})

    loaded = pipeline_state.load_state(tmp_path)
    assert "stage_a" in loaded
    assert loaded["stage_a"].input_hash == "abc"
    assert loaded["stage_a"].status == "success"


def test_save_state_overwrites(tmp_path):
    record1 = pipeline_state.StageRecord(
        stage="stage_a", input_hash="old", output_hash="old_out",
        timestamp="2026-01-01T00:00:00+00:00", status="success",
    )
    pipeline_state.save_state(tmp_path, {"stage_a": record1})

    record2 = pipeline_state.StageRecord(
        stage="stage_a", input_hash="new", output_hash="new_out",
        timestamp="2026-01-02T00:00:00+00:00", status="success",
    )
    pipeline_state.save_state(tmp_path, {"stage_a": record2})

    loaded = pipeline_state.load_state(tmp_path)
    assert loaded["stage_a"].input_hash == "new"


def test_load_state_handles_corrupt_file(tmp_path):
    state_file = tmp_path / "pipeline_state.json"
    state_file.write_text("not valid json {{{")
    assert pipeline_state.load_state(tmp_path) == {}


# ---------------------------------------------------------------------------
# should_skip
# ---------------------------------------------------------------------------


def test_should_skip_returns_none_when_no_record(tmp_path):
    result = pipeline_state.should_skip(tmp_path, "stage_a", "hash123")
    assert result is None


def test_should_skip_returns_none_when_status_failed(tmp_path):
    record = pipeline_state.StageRecord(
        stage="stage_a", input_hash="hash123", output_hash="",
        timestamp="2026-01-01T00:00:00+00:00", status="failed",
    )
    pipeline_state.save_state(tmp_path, {"stage_a": record})
    result = pipeline_state.should_skip(tmp_path, "stage_a", "hash123")
    assert result is None


def test_should_skip_returns_none_when_hash_differs(tmp_path):
    record = pipeline_state.StageRecord(
        stage="stage_a", input_hash="old_hash", output_hash="out",
        timestamp="2026-01-01T00:00:00+00:00", status="success",
    )
    pipeline_state.save_state(tmp_path, {"stage_a": record})
    result = pipeline_state.should_skip(tmp_path, "stage_a", "new_hash")
    assert result is None


def test_should_skip_returns_record_when_matching(tmp_path):
    record = pipeline_state.StageRecord(
        stage="stage_a", input_hash="hash123", output_hash="out",
        timestamp="2026-01-01T00:00:00+00:00", status="success",
    )
    pipeline_state.save_state(tmp_path, {"stage_a": record})
    result = pipeline_state.should_skip(tmp_path, "stage_a", "hash123")
    assert result is not None
    assert result.stage == "stage_a"
    assert result.input_hash == "hash123"


# ---------------------------------------------------------------------------
# record_success / record_failure
# ---------------------------------------------------------------------------


def test_record_success_persists(tmp_path):
    record = pipeline_state.record_success(
        tmp_path, "stage_a", "in_hash", "out_hash",
        log_path="logs/stage_a.log", detail="done",
    )
    assert record.status == "success"
    assert record.input_hash == "in_hash"
    assert record.output_hash == "out_hash"

    loaded = pipeline_state.load_state(tmp_path)
    assert loaded["stage_a"].status == "success"


def test_record_failure_persists(tmp_path):
    record = pipeline_state.record_failure(
        tmp_path, "stage_a", "in_hash", detail="error",
    )
    assert record.status == "failed"
    assert record.output_hash == ""

    loaded = pipeline_state.load_state(tmp_path)
    assert loaded["stage_a"].status == "failed"


def test_record_success_overwrites_failure(tmp_path):
    pipeline_state.record_failure(tmp_path, "stage_a", "hash", detail="error")
    pipeline_state.record_success(tmp_path, "stage_a", "hash", "out", detail="fixed")

    loaded = pipeline_state.load_state(tmp_path)
    assert loaded["stage_a"].status == "success"


# ---------------------------------------------------------------------------
# stage_log_path
# ---------------------------------------------------------------------------


def test_stage_log_path(tmp_path):
    path = pipeline_state.stage_log_path(tmp_path, "stage_a")
    assert path == tmp_path / "logs" / "stage_a.log"
