"""Tests for the derived library index (issue 181, section A)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import library_index as li
from deterministic_json import ROOT, DeterministicWriteError, canonical_bytes, sha256_file

SNAPSHOT = ROOT / "godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.5.0.json"
COMMITTED_INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
ISSUE_168_PAIR = "issue168_industrial_hall_south__debris_rock_north_v1"
BILL_VIOLA = "video_b9161c467ed2d30a_bill_viola_single_room_v1"
SOURCE_A = "video-aaaaaaaaaaaaaaaa"


def socket(socket_id: str) -> dict:
    return {"id": socket_id, "local_floor_center": [0.0, 0.0, 0.0]}


def module(module_id: str, sockets: list[str], scene: str = "res://scenes/x.tscn") -> dict:
    return {
        "id": module_id,
        "version": 1,
        "scene": scene,
        "kind": "authored_room",
        "variant_status": "test",
        "sockets": [socket(name) for name in sockets],
        "source_provenance": [],
    }


def synthetic_catalog() -> dict:
    room_scene = f"res://source_library/sources/{SOURCE_A}/rooms/r1/room.tscn"
    return {
        "catalog_id": "test_kit",
        "catalog_version": "9.9.9",
        "modules": [module("top_a", ["east"]), module("top_dup", [], room_scene)],
        "tested_connector_pairs": [],
        "source_video_adaptations": [
            {
                "rooms": [module("nested_b", ["west"], room_scene), module("top_dup", [])],
                "tested_connector_pair": {
                    "id": "pair_ab",
                    "status": "operator_accepted_exact_pair",
                    "from": ["top_a", "east"],
                    "to": ["nested_b", "west"],
                    "scope": "Only this.",
                    "evidence": ["b.json", "a.json"],
                },
            }
        ],
    }


def build_document(catalog: dict) -> dict:
    return li.build_index_document(catalog, "snap.json", "0" * 64)


def real_document() -> dict:
    return json.loads(COMMITTED_INDEX.read_text(encoding="utf-8"))


def entry_by_id(document: dict, module_id: str) -> dict:
    return next(item for item in document["modules"] if item["module_id"] == module_id)


def test_issue_168_pair_resolves_to_nested_socket_variants() -> None:
    document = real_document()
    pair = next(item for item in document["connector_pairs"] if item["id"] == ISSUE_168_PAIR)
    assert pair["placement_scope"] == "exact_pair_only"
    assert pair["location"].startswith("/source_video_adaptations/0/")
    (south_id, south), (north_id, north) = pair["from"], pair["to"]
    assert south == "south" and north == "north"
    for module_id, socket_id in ((south_id, south), (north_id, north)):
        entry = entry_by_id(document, module_id)
        assert entry["location"].startswith("/source_video_adaptations/0/rooms/")
        assert socket_id in {item["id"] for item in entry["sockets"]}


def test_top_level_pair_is_plain_pair_scope() -> None:
    pairs = {item["id"]: item for item in real_document()["connector_pairs"]}
    assert pairs["column_east__pocket_west_v1"]["placement_scope"] == "pair"
    assert pairs["column_east__pocket_west_v1"]["location"] == "/tested_connector_pairs/0"


def test_bill_viola_top_level_wins_and_nested_is_reference() -> None:
    entry = entry_by_id(real_document(), BILL_VIOLA)
    assert entry["location"].startswith("/modules/")
    assert entry["adaptation_reference"] == "/source_video_adaptations/1/rooms/0"
    assert entry["catalog_layout_eligible"] is False
    assert entry["room_dir"].endswith("rooms/bill-viola-single-room-v1")


def test_real_index_has_eleven_unique_modules() -> None:
    modules = real_document()["modules"]
    keys = [(item["module_id"], item["version"]) for item in modules]
    assert len(modules) == 11 and len(set(keys)) == 11
    assert keys == sorted(keys)


def test_committed_index_matches_fresh_build() -> None:
    catalog = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    fresh = li.build_index_document(
        catalog, "godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.5.0.json",
        sha256_file(SNAPSHOT),
    )
    assert canonical_bytes(fresh) == COMMITTED_INDEX.read_bytes()


def test_synthetic_top_level_wins_over_nested_duplicate() -> None:
    document = build_document(synthetic_catalog())
    entry = entry_by_id(document, "top_dup")
    assert entry["location"] == "/modules/1"
    assert entry["adaptation_reference"] == "/source_video_adaptations/0/rooms/1"
    assert entry["source_id"] == SOURCE_A
    assert entry["room_dir"] == f"godot_walk/source_library/sources/{SOURCE_A}/rooms/r1"


def test_pair_fields_and_sorted_evidence() -> None:
    pair = build_document(synthetic_catalog())["connector_pairs"][0]
    assert pair["placement_scope"] == "exact_pair_only"
    assert pair["evidence"] == ["a.json", "b.json"]
    assert pair["location"] == "/source_video_adaptations/0/tested_connector_pair"


def test_missing_endpoint_module_fails() -> None:
    catalog = synthetic_catalog()
    catalog["source_video_adaptations"][0]["tested_connector_pair"]["to"] = ["ghost", "west"]
    with pytest.raises(li.LibraryIndexError, match="ghost"):
        build_document(catalog)


def test_missing_endpoint_socket_fails() -> None:
    catalog = synthetic_catalog()
    catalog["source_video_adaptations"][0]["tested_connector_pair"]["to"] = ["nested_b", "up"]
    with pytest.raises(li.LibraryIndexError, match="no socket up"):
        build_document(catalog)


def test_non_top_level_duplicate_is_an_error() -> None:
    catalog = synthetic_catalog()
    catalog["source_video_adaptations"][0]["rooms"].append(module("nested_b", ["west"]))
    with pytest.raises(li.LibraryIndexError, match="Duplicate module"):
        build_document(catalog)
    catalog = synthetic_catalog()
    catalog["modules"].append(copy.deepcopy(catalog["modules"][0]))
    with pytest.raises(li.LibraryIndexError, match="Duplicate module"):
        build_document(catalog)


def test_duplicate_pair_id_is_an_error() -> None:
    catalog = synthetic_catalog()
    pair = copy.deepcopy(catalog["source_video_adaptations"][0]["tested_connector_pair"])
    catalog["tested_connector_pairs"] = [pair]
    with pytest.raises(li.LibraryIndexError, match="Duplicate connector pair"):
        build_document(catalog)


def make_workspace(tmp_path: Path) -> Path:
    snapshot = tmp_path / "godot_walk/room_catalog/catalog_snapshots/test_kit-9.9.9.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(json.dumps(synthetic_catalog()), encoding="utf-8")
    return snapshot


def test_rebuild_is_byte_identical(tmp_path: Path) -> None:
    snapshot = make_workspace(tmp_path)
    first = li.build_index(snapshot, root=tmp_path)
    target = tmp_path / first["index"]
    data = target.read_bytes()
    second = li.build_index(snapshot, root=tmp_path)
    assert (first["status"], second["status"]) == ("created", "unchanged")
    assert target.read_bytes() == data
    assert first["index"] == "godot_walk/room_catalog/library_index/test_kit-9.9.9.json"
    assert b"generated" not in data and b"timestamp" not in data


def test_refuses_to_overwrite_different_content(tmp_path: Path) -> None:
    snapshot = make_workspace(tmp_path)
    target = tmp_path / li.build_index(snapshot, root=tmp_path)["index"]
    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(DeterministicWriteError):
        li.build_index(snapshot, root=tmp_path)
    assert target.read_text(encoding="utf-8") == "{}\n"


def test_verified_index_detects_changed_snapshot(tmp_path: Path) -> None:
    snapshot = make_workspace(tmp_path)
    target = tmp_path / li.build_index(snapshot, root=tmp_path)["index"]
    assert li.load_verified_index(target, tmp_path)["catalog_id"] == "test_kit"
    snapshot.write_text(snapshot.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(li.LibraryIndexError, match="hash changed"):
        li.load_verified_index(target, tmp_path)
