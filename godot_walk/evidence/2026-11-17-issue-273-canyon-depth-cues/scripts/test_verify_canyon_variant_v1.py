"""Mutation tests for the issue-273 canyon variant integrity validator."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from verify_canyon_variant_v1 import (
    BASELINE,
    EVIDENCE,
    PINNED,
    PROVENANCE,
    ROOT,
    VARIANT,
    VARIANT_CANDIDATE,
    collect_errors,
)

FOLDERS = (BASELINE, VARIANT, EVIDENCE)


@pytest.fixture()
def repo_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "repo"
    for relative in FOLDERS:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / relative, target)
    supplement = json.loads((ROOT / PINNED).read_text(encoding="utf-8"))
    for relative in supplement["files"]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    events = "godot_walk/source_library/sources/video-22909eb734e4d8e2/events.jsonl"
    target = destination / events
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / events, target)
    return destination


def edit_json(repo: Path, relative: str, mutate) -> None:
    path = repo / relative
    record = json.loads(path.read_text(encoding="utf-8"))
    mutate(record)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def edit_text(repo: Path, relative: str, old: str, new: str) -> None:
    path = repo / relative
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_real_repository_has_no_errors() -> None:
    assert collect_errors() == []


def test_source_records_exist() -> None:
    assert (ROOT / VARIANT_CANDIDATE).is_file()
    assert (ROOT / PROVENANCE).is_file()
    assert (ROOT / PINNED).is_file()


def test_footprint_change_is_reported(repo_copy: Path) -> None:
    def mutate(record):
        record["resolved_adaptation"]["walkable_space"]["footprint"]["vertices_xz"][0][
            0
        ] = -5.0

    edit_json(repo_copy, VARIANT_CANDIDATE, mutate)
    assert any("footprint changed" in error for error in collect_errors(repo_copy))


def test_true_calibration_flag_is_reported(repo_copy: Path) -> None:
    edit_json(
        repo_copy,
        VARIANT_CANDIDATE,
        lambda record: record.update(scale_calibrated=True),
    )
    assert any("calibration flags" in error for error in collect_errors(repo_copy))


def test_stale_identity_is_reported(repo_copy: Path) -> None:
    edit_json(
        repo_copy,
        VARIANT_CANDIDATE,
        lambda record: record.update(candidate_identity="0" * 64),
    )
    assert any("identity is stale" in error for error in collect_errors(repo_copy))


def test_declared_socket_is_reported(repo_copy: Path) -> None:
    def mutate(record):
        record["resolved_adaptation"]["sockets"].append({"id": "escape"})

    edit_json(repo_copy, VARIANT_CANDIDATE, mutate)
    assert any("declares sockets" in error for error in collect_errors(repo_copy))


def test_dependency_hash_change_is_reported(repo_copy: Path) -> None:
    def mutate(record):
        record["resolved_adaptation"]["dependencies"][0]["sha256"] = "0" * 64

    edit_json(repo_copy, VARIANT_CANDIDATE, mutate)
    assert any(
        "dependency hash mismatch" in error for error in collect_errors(repo_copy)
    )


def test_frozen_file_edit_is_reported(repo_copy: Path) -> None:
    path = repo_copy / "godot_walk/scripts/player.gd"
    path.write_text(path.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    assert any(
        "frozen/accepted file changed" in error for error in collect_errors(repo_copy)
    )


def test_relief_collider_is_reported(repo_copy: Path) -> None:
    edit_text(
        repo_copy,
        f"{VARIANT}/room.gd",
        "func _build_visual_relief() -> void:\n",
        'func _build_visual_relief() -> void:\n\t_add_collision_box("Bad", Vector3.ZERO, Vector3.ONE, "AuthoredObstacles")\n',
    )
    assert any(
        "visual relief creates a collider" in error
        for error in collect_errors(repo_copy)
    )


def test_changed_wall_constant_is_reported(repo_copy: Path) -> None:
    edit_text(
        repo_copy,
        f"{VARIANT}/room.gd",
        '["SouthWall", 0.0, 3.5, -10.15',
        '["SouthWall", 0.0, 3.5, -9.15',
    )
    assert any(
        "room constant WALL_SEGMENTS changed" in error
        for error in collect_errors(repo_copy)
    )


def test_missing_negative_control_is_reported(repo_copy: Path) -> None:
    edit_text(
        repo_copy,
        f"{VARIANT}/test_room.gd",
        "escape negative control",
        "renamed control",
    )
    assert any("headless test lacks" in error for error in collect_errors(repo_copy))


def test_divergent_camera_pose_is_reported(repo_copy: Path) -> None:
    def mutate(record):
        record["matched_capture"]["camera_variant"]["fov_degrees"] = 60.0

    edit_json(repo_copy, PROVENANCE, mutate)
    assert any(
        "matched captures differ on camera" in error
        for error in collect_errors(repo_copy)
    )


def test_divergent_view_pose_is_reported(repo_copy: Path) -> None:
    def mutate(record):
        record["matched_capture"]["views_variant"][1]["target"][0] = 9.0

    edit_json(repo_copy, PROVENANCE, mutate)
    assert any(
        "matched captures differ on views" in error
        for error in collect_errors(repo_copy)
    )


def test_dirty_guard_receipt_is_reported(repo_copy: Path) -> None:
    def mutate(record):
        record["variant"]["guard_receipt"]["return_code"] = 2

    edit_json(repo_copy, PROVENANCE, mutate)
    assert any(
        "guard receipt is not clean" in error for error in collect_errors(repo_copy)
    )


def test_capture_flag_is_reported(repo_copy: Path) -> None:
    relative = f"{VARIANT}/captures/capture_manifest.json"

    def mutate(record):
        record["registration_accepted"] = True

    edit_json(repo_copy, relative, mutate)
    assert any("capture manifest flags" in error for error in collect_errors(repo_copy))


def test_hand_written_ledger_event_is_reported(repo_copy: Path) -> None:
    events = (
        repo_copy
        / "godot_walk/source_library/sources/video-22909eb734e4d8e2/events.jsonl"
    )
    events.write_text(
        events.read_text(encoding="utf-8")
        + '{"issue":273,"room":"slot-canyon-courtyard-v2"}\n',
        encoding="utf-8",
    )
    assert any("hand-written" in error for error in collect_errors(repo_copy))


def test_missing_variant_capture_is_reported(repo_copy: Path) -> None:
    (repo_copy / f"{VARIANT}/captures/walk_02_mid.png").unlink()
    assert any(
        "variant capture missing" in error for error in collect_errors(repo_copy)
    )


def test_wrong_room_ids_are_reported(repo_copy: Path) -> None:
    edit_json(
        repo_copy, PROVENANCE, lambda record: record["variant"].update(room_id="wrong")
    )
    assert any("variant room id" in error for error in collect_errors(repo_copy))


def test_negative_control_description_is_reported(repo_copy: Path) -> None:
    def mutate(record):
        record["negative_control"]["description"] = "no control"

    edit_json(repo_copy, PROVENANCE, mutate)
    assert any(
        "negative control description" in error for error in collect_errors(repo_copy)
    )
