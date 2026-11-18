"""Tests for the issue-268 one-tree fixture integrity validator."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from verify_tree_fixture_v1 import FIXTURE_DIR, ROOT, collect_errors


@pytest.fixture()
def fixture_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "fixture"
    shutil.copytree(FIXTURE_DIR, destination)
    return destination


def _replace(directory: Path, name: str, mutate) -> None:
    path = directory / name
    record = json.loads(path.read_text(encoding="utf-8"))
    mutate(record)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def test_real_fixture_has_no_errors() -> None:
    assert collect_errors() == []


def test_source_record_resolves_against_repository() -> None:
    provenance = json.loads(
        (FIXTURE_DIR / "crop_provenance_v1.json").read_text(encoding="utf-8")
    )
    assert (ROOT / provenance["source"]["source_video"]).is_file()
    assert (ROOT / provenance["source"]["frame_manifest"]).is_file()


def test_missing_view_is_reported(fixture_copy: Path) -> None:
    def drop_view(record):
        record["views"] = [v for v in record["views"] if v["id"] != "elevated"]

    _replace(fixture_copy, "views_v1.json", drop_view)
    assert any("elevated" in error for error in collect_errors(fixture_copy))


def test_repeated_card_transform_is_reported(fixture_copy: Path) -> None:
    def flatten(record):
        record["cards"][1]["azimuth_deg"] = record["cards"][0]["azimuth_deg"]

    _replace(fixture_copy, "card_specs_v1.json", flatten)
    assert any("azimuth" in error for error in collect_errors(fixture_copy))


def test_true_flag_is_reported(fixture_copy: Path) -> None:
    def accept(record):
        record["authored_vs_source"]["flags"]["registration_accepted"] = True

    _replace(fixture_copy, "crop_provenance_v1.json", accept)
    assert any(
        "registration_accepted" in error for error in collect_errors(fixture_copy)
    )


def test_wrong_source_hash_is_reported(fixture_copy: Path) -> None:
    def corrupt(record):
        record["source"]["source_video_sha256"] = "0" * 64

    _replace(fixture_copy, "crop_provenance_v1.json", corrupt)
    assert any(
        "Source video hash mismatch" in error for error in collect_errors(fixture_copy)
    )


def test_wrong_crop_hash_is_reported(fixture_copy: Path) -> None:
    def corrupt(record):
        record["crops"][0]["fixture_sha256"] = "0" * 64

    _replace(fixture_copy, "crop_provenance_v1.json", corrupt)
    assert any("fixture_sha256" in error for error in collect_errors(fixture_copy))


def test_missing_bark_assessment_is_reported(fixture_copy: Path) -> None:
    def clear(record):
        record["bark_crop_assessment"] = {}

    _replace(fixture_copy, "crop_provenance_v1.json", clear)
    errors = collect_errors(fixture_copy)
    assert any("Bark crop assessment" in error for error in errors)
