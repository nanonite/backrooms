"""Tests for the #195 template batch ingestion (issue 222)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_source_intake_contact_sheet
import seed_review_sources
import template_batch_ingest as batch
import template_validate as tv
from library_index import load_verified_index
from register_video_sources import register_video
from source_ingestion_runner import _verify_extraction_identity, source_status
from template_manifest_v3 import ManifestUpgradeError
from template_module_contract import module_contract_errors
from video_source_library import (
    manifest_lineage_hashes,
    manifest_video_content,
    validate_index,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_LIBRARY = ROOT / "godot_walk/source_library"
LIBRARY_INDEX = (
    ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
)
SCHEMA_NAMES = (
    "source_manifest.schema.json",
    "source_manifest_v2.schema.json",
    "source_manifest_v3.schema.json",
)
FAKE_METADATA = {
    "width": 1920,
    "height": 1080,
    "fps": 24.0,
    "frame_count": 96,
    "duration_seconds": 4.0,
}


def fake_probe(_path: Path) -> dict[str, object]:
    return dict(FAKE_METADATA)


def _copy_schemas(root: Path) -> None:
    target = root / "godot_walk/source_library"
    (target / "batches").mkdir(parents=True)
    for name in SCHEMA_NAMES:
        shutil.copy(SOURCE_LIBRARY / name, target / name)


def _batch_root(tmp_path: Path) -> tuple[Path, list[str]]:
    root = tmp_path / "repo"
    _copy_schemas(root)
    videos = root / "data/videos"
    videos.mkdir(parents=True)
    source_ids = []
    for index in range(7):
        video = videos / f"sample-{index}.mp4"
        video.write_bytes(f"sample video {index}".encode())
        source_ids.append(register_video(video, root, fake_probe))
    record = {
        "schema_version": 1,
        "batch_id": "issue-195",
        "issue": 195,
        "template_version": "generation-template-0.1.0",
        "sources": [
            {"issue": 174 + index, "source_id": source_id}
            for index, source_id in enumerate(source_ids)
        ],
    }
    (root / batch.BATCH_PATH).write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    return root, source_ids


def _source_dir(root: Path, source_id: str) -> Path:
    return root / "godot_walk/source_library/sources" / source_id


def test_batch_descriptor_is_the_195_sources() -> None:
    record = batch.load_batch(ROOT)
    assert [item["issue"] for item in record["sources"]] == list(range(174, 181))
    assert [item["source_id"] for item in record["sources"]] == [
        "video-d92fc1fa764aa3a2",
        "video-102caf53423018b7",
        "video-2671b32f256a4ee7",
        "video-61b91dbeb9026dc7",
        "video-f657e9bc27813df8",
        "video-ef0ec21cd4ae7b26",
        "video-51abd379f94b8f84",
    ]
    assert batch.batch_record_errors(record) == []


def test_batch_descriptor_rejects_missing_or_duplicate_issues() -> None:
    record = batch.load_batch(ROOT)
    duplicate = json.loads(json.dumps(record))
    duplicate["sources"][1]["issue"] = duplicate["sources"][0]["issue"]
    assert any(
        "exactly once" in error for error in batch.batch_record_errors(duplicate)
    )
    duplicate["sources"][1]["source_id"] = duplicate["sources"][0]["source_id"]
    assert any("unique" in error for error in batch.batch_record_errors(duplicate))


def test_upgrade_writes_a_v2_bridge_then_a_v3_snapshot(tmp_path: Path) -> None:
    root, source_ids = _batch_root(tmp_path)
    originals = {
        source_id: (_source_dir(root, source_id) / "source_manifest.json").read_bytes()
        for source_id in source_ids
    }
    results = batch.upgrade_batch(root)
    assert [result["status"] for result in results] == ["created"] * 7
    entries = {entry["source_id"]: entry for entry in validate_index(root)}
    for source_id in source_ids:
        entry = entries[source_id]
        assert Path(entry["manifest_path"]).name == "source_manifest-v3.json"
        v3 = json.loads((root / entry["manifest_path"]).read_text(encoding="utf-8"))
        v2_path = _source_dir(root, source_id) / "source_manifest-v2.json"
        v2 = json.loads(v2_path.read_text(encoding="utf-8"))
        assert v3["schema_version"] == 3
        assert v3["manifest_version"] == 3
        assert v3["source_kind"] == "video"
        assert v3["registration_accepted"] is False
        assert v3["scale_calibrated"] is False
        assert v3["content"]["video"]["sha256"] == entry["source_sha256"]
        assert v3["content"]["video"]["metadata"]["width"] == 1920
        assert v3["capture"]["camera_model"] is None
        assert v3["scale"]["status"] == "uncalibrated"
        assert v3["lighting"]["status"] == "unknown"
        assert v3["supersedes"] == {
            "path": v2_path.relative_to(root).as_posix(),
            "sha256": batch.sha256_file(v2_path),
        }
        assert v2["schema_version"] == 2
        assert v2["supersedes"]["path"].endswith("source_manifest.json")
        assert (
            originals[source_id]
            == (_source_dir(root, source_id) / "source_manifest.json").read_bytes()
        )
        assert tv.source_manifest_errors(v3, root) == []
        assert len(manifest_lineage_hashes(entry, root)) == 3
        events = batch._read_events(_source_dir(root, source_id) / "events.jsonl")
        assert [event["event_type"] for event in events] == [
            "source_registered",
            batch.UPGRADE_EVENT,
        ]
        assert events[-1]["payload"]["manifest_sha256"] == entry["manifest_sha256"]


def test_upgrade_is_idempotent(tmp_path: Path) -> None:
    root, source_ids = _batch_root(tmp_path)
    batch.upgrade_batch(root)
    hashes = {
        entry["source_id"]: entry["manifest_sha256"] for entry in validate_index(root)
    }
    events = {
        source_id: len(
            batch._read_events(_source_dir(root, source_id) / "events.jsonl")
        )
        for source_id in source_ids
    }
    results = batch.upgrade_batch(root)
    assert [result["status"] for result in results] == ["unchanged"] * 7
    assert [result["event"] for result in results] == ["unchanged"] * 7
    assert hashes == {
        entry["source_id"]: entry["manifest_sha256"] for entry in validate_index(root)
    }
    for source_id in source_ids:
        assert (
            len(batch._read_events(_source_dir(root, source_id) / "events.jsonl"))
            == events[source_id]
        )


def test_upgrade_restores_a_missing_audit_event(tmp_path: Path) -> None:
    root, source_ids = _batch_root(tmp_path)
    batch.upgrade_batch(root)
    events_path = _source_dir(root, source_ids[0]) / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    events_path.write_text(lines[0] + "\n", encoding="utf-8")
    results = batch.upgrade_batch(root)
    assert results[0]["event"] == "appended"
    restored = batch._read_events(events_path)
    assert [event["event_type"] for event in restored] == [
        "source_registered",
        batch.UPGRADE_EVENT,
    ]


def test_upgrade_refuses_a_tampered_v3_successor(tmp_path: Path) -> None:
    root, source_ids = _batch_root(tmp_path)
    batch.upgrade_batch(root)
    entries = validate_index(root)
    entry = next(item for item in entries if item["source_id"] == source_ids[0])
    path = root / entry["manifest_path"]
    record = json.loads(path.read_text(encoding="utf-8"))
    record["content"]["video"]["sha256"] = "0" * 64
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    with pytest.raises((ManifestUpgradeError, batch.BatchError)):
        batch.upgrade_source(source_ids[0], root, entries)


def test_v3_manifest_is_readable_by_the_runner_and_seed_review() -> None:
    record = batch.load_batch(ROOT)
    source_id = record["sources"][0]["source_id"]
    entry = next(
        item for item in validate_index(ROOT) if item["source_id"] == source_id
    )
    assert entry["manifest_path"].endswith("source_manifest-v3.json")
    status = source_status(source_id, ROOT)
    assert status["next_worker_actions"] == ["review-source"]
    seed = seed_review_sources.load_source_record(source_id, ROOT)
    assert seed.video_path == entry["source_path"]
    manifest = json.loads((ROOT / entry["manifest_path"]).read_text(encoding="utf-8"))
    video = manifest_video_content(manifest)
    _verify_extraction_identity(
        {
            "source_video": video["path"],
            "source_video_sha256": video["sha256"],
            "decoder": "ffmpeg select by decoded zero-based frame index",
        },
        manifest,
    )


def test_contact_sheet_reads_v3_videos_and_skips_picture_sets() -> None:
    rows = build_source_intake_contact_sheet._read_sources(ROOT)
    assert rows
    assert all(row["source_id"].startswith("video-") for row in rows)
    assert all("metadata" in row for row in rows)


def test_all_admitted_modules_satisfy_the_template_contract() -> None:
    modules = load_verified_index(LIBRARY_INDEX, ROOT)["modules"]
    assert len(modules) >= 11
    failures = {}
    for entry in modules:
        errors = module_contract_errors(entry, ROOT)
        if errors:
            failures[entry["module_id"]] = errors
    assert failures == {}


def test_module_contract_accepts_admitted_modules_and_reports_missing_parts() -> None:
    modules = load_verified_index(LIBRARY_INDEX, ROOT)["modules"]
    admitted = [entry for entry in modules if entry.get("source_id")]
    assert admitted
    assert all(module_contract_errors(entry, ROOT) == [] for entry in admitted)
    missing = module_contract_errors(
        {
            "module_id": "ghost_v1",
            "version": 1,
            "source_id": "video-102caf53423018b7",
            "room_dir": (
                "godot_walk/source_library/sources/video-102caf53423018b7/"
                "rooms/ghost-v1"
            ),
        },
        ROOT,
    )
    assert any("module profile missing" in error for error in missing)
    assert any("missing ghost_v1@1" in error for error in missing)
    assert any("surface descriptor missing" in error for error in missing)
    assert any("consolidated module metadata missing" in error for error in missing)


def test_batch_check_passes_and_operator_flags_stay_false() -> None:
    assert batch.batch_errors(ROOT) == []
    status = batch.batch_status(ROOT)
    assert status["source_count"] == 7
    modules = {entry["source_id"]: [] for entry in validate_index(ROOT)}
    for source in status["sources"]:
        assert source["manifest_schema_version"] == 3
        entry = next(
            item
            for item in validate_index(ROOT)
            if item["source_id"] == source["source_id"]
        )
        manifest = json.loads(
            (ROOT / entry["manifest_path"]).read_text(encoding="utf-8")
        )
        assert manifest["registration_accepted"] is False
        assert manifest["scale_calibrated"] is False
        assert source["module_contract_errors"] == {}
        modules[source["source_id"]] = source["admitted_module_ids"]
    assert status["admitted_module_count"] == sum(len(ids) for ids in modules.values())


def test_batch_text_records_are_utf8_json_without_binary_payloads() -> None:
    record = batch.load_batch(ROOT)
    paths = [ROOT / batch.BATCH_PATH]
    for source in record["sources"]:
        directory = _source_dir(ROOT, source["source_id"])
        paths.extend(
            [
                directory / "source_manifest-v2.json",
                directory / "source_manifest-v3.json",
            ]
        )
    for path in paths:
        data = path.read_bytes()
        assert b"\0" not in data
        assert path.suffix == ".json"
        json.loads(data.decode("utf-8"))
