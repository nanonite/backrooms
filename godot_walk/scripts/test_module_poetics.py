"""Tests for module_poetics derivation, schemas and drafts (issue 181, sections B-D)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

import library_index as li
import module_poetics as mp
import poetics_geometry as geometry
import poetics_signs as signs
from deterministic_json import ROOT, DeterministicWriteError

CATALOG_DIR = ROOT / "godot_walk/room_catalog"
FRAME = "godot_walk/source_library/sources/video-aaaaaaaaaaaaaaaa/frames/seed/frame_0001.png"
SCENE = "res://source_library/sources/video-aaaaaaaaaaaaaaaa/rooms/r1/room.tscn"
RECT = [[0, 0], [6, 0], [6, 4], [0, 4]]


def schema(name: str) -> dict:
    return json.loads((CATALOG_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def fixture(name: str) -> dict:
    path = CATALOG_DIR / "schema_fixtures" / f"{name}.fixture.json"
    return json.loads(path.read_text(encoding="utf-8"))


def errors(name: str, record: dict) -> list[str]:
    return [e.message for e in Draft202012Validator(schema(name)).iter_errors(record)]


# --- geometry -------------------------------------------------------------


def shape(points: list[list[float]]) -> dict:
    return geometry.analyze_shape(points)


def test_rectangle_is_box_d2_stage_zero() -> None:
    result = shape(RECT)
    assert (result["primitive"], result["shape_stage"], result["symmetry"]) == ("box", 0, "D2")
    assert result["area_m2"] == 24.0 and result["aspect"] == 1.5 and result["convexity"] == 1.0
    assert result["bbox_xz"] == {"min": [0.0, 0.0], "max": [6.0, 4.0]}


def test_square_is_d4_and_closing_vertex_is_ignored() -> None:
    result = shape([[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]])
    assert (result["vertex_count"], result["symmetry"], result["aspect"]) == (4, "D4", 1.0)


def test_l_shape_is_stage_one_with_low_symmetry() -> None:
    result = shape([[0, 0], [8, 0], [8, 4], [4, 4], [4, 8], [0, 8]])
    assert (result["primitive"], result["shape_stage"]) == ("l_shape", 1)
    assert result["symmetry"] in {"C1", "D1"}
    assert result["convexity"] == 0.857143 and result["rectilinear"] is True


def test_mirror_symmetric_rectilinear_polygon_is_d1() -> None:
    hall = [[-6, -5], [6, -5], [6, -1.5], [13, -1.5], [13, 1.5], [6, 1.5], [6, 5], [-6, 5]]
    result = shape(hall)
    assert (result["primitive"], result["symmetry"]) == ("rectilinear_polygon", "D1")


def test_chamfered_octagon_is_stage_two() -> None:
    octagon = [[2, 0], [6, 0], [8, 2], [8, 6], [6, 8], [2, 8], [0, 6], [0, 2]]
    result = shape(octagon)
    assert (result["primitive"], result["shape_stage"]) == ("chamfered_polygon", 2)
    assert result["rectilinear"] is False and result["symmetry"] == "D4"


def test_generic_polygon_has_no_stage() -> None:
    result = shape([[0, 0], [4, 0], [3.5, 2.4], [0, 3]])
    assert (result["primitive"], result["shape_stage"]) == ("polygon", None)


def test_degenerate_footprint_is_rejected() -> None:
    with pytest.raises(ValueError):
        shape([[0, 0], [1, 0], [2, 0]])


def socket_at(x: float, z: float) -> dict:
    return {"id": "s", "local_floor_center": [x, 0.0, z]}


def test_port_slots_exclude_edges_hosting_sockets() -> None:
    slots = geometry.port_slots(RECT, [socket_at(6.0, 2.0)])
    assert [slot["edge_index"] for slot in slots] == [0, 2, 3]
    assert all(slot["length_m"] >= 2.4 for slot in slots)


def test_port_slots_have_outward_normals_for_either_winding() -> None:
    for footprint in (RECT, RECT[::-1]):
        slots = {tuple(s["midpoint_xz"]): s for s in geometry.port_slots(footprint, [])}
        assert slots[(3.0, 0.0)]["outward_normal_xz"] == [0.0, -1.0]
        assert slots[(3.0, 4.0)]["outward_normal_xz"] == [0.0, 1.0]
        assert slots[(0.0, 2.0)]["outward_normal_xz"] == [-1.0, 0.0]
        assert slots[(6.0, 2.0)]["outward_normal_xz"] == [1.0, 0.0]


def test_short_edges_are_not_port_slots() -> None:
    slots = geometry.port_slots([[0, 0], [2.3, 0], [2.3, 5], [0, 5]], [])
    assert {slot["length_m"] for slot in slots} == {5.0}


# --- sign tagging ----------------------------------------------------------


def test_obstacle_with_frame_citation_is_symbol_motivated_by_index() -> None:
    feature = signs.obstacle_feature(
        {"id": "post", "provenance": f"Authored from {FRAME} and godot_walk/notes.md."}
    )
    assert (feature["kind"], feature["sign"]) == ("obstacle", "symbol")
    assert feature["citations"] == ["godot_walk/notes.md", FRAME]
    assert feature["motivated_by_index"] is True


def test_obstacle_without_paths_is_not_motivated_by_index() -> None:
    feature = signs.obstacle_feature({"id": "post", "provenance": "Authored from frame 0013."})
    assert feature["citations"] == [] and feature["motivated_by_index"] is False
    named = signs.obstacle_feature("AuthoredObstacles/Stone_000Collision")
    assert named["feature_id"] == "obstacle:Stone_000Collision" and named["sign"] == "symbol"


def test_textures_and_panoramas_are_icons_other_assets_are_not() -> None:
    assets = [
        "godot_walk/rooms/r1/textures/wall.png",
        "godot_walk/x/hunyuan/attempt-1/panorama/panorama.png",
        "godot_walk/x/hunyuan_panorama_room/panorama_v2.png",
        "godot_walk/rooms/r1/room.tscn",
        "godot_walk/rooms/r1/captures/view.png",
    ]
    tagged = signs.surface_features(assets)
    assert [f["citations"][0] for f in tagged] == assets[:3]
    assert {f["sign"] for f in tagged} == {"icon"}


def test_observed_opening_is_index_and_untested_one_becomes_void() -> None:
    module = {
        "id": "m",
        "observed_openings": [
            {"id": "gap", "source_frame": FRAME, "description": "dark", "tested_connector": False},
            {"id": "door", "source_frame": FRAME, "description": "ok", "tested_connector": True},
        ],
    }
    features = {f["feature_id"]: f for f in signs.build_features(module)}
    assert features["observed_opening:gap"]["sign"] == "index"
    assert features["observed_opening:gap"]["citations"] == [FRAME]
    assert features["collision"]["sign"] == "symbol"
    assert signs.build_voids(module) == [
        {"void_id": "gap", "source_frame": FRAME, "description": "dark", "traversable": False}
    ]


def test_translation_chain_orders_stages_and_skips_kit_modules() -> None:
    paths = [FRAME, "godot_walk/s/hunyuan/a1/panorama/panorama.png"]
    chain = signs.translation_chain("video-aaaaaaaaaaaaaaaa", SCENE, paths)
    assert [stage["stage"] for stage in chain] == ["direct_frame", "hunyuan_panorama", "godot_room"]
    assert signs.translation_chain(None, "res://scenes/a.tscn", paths) == []


# --- schemas and fixtures ---------------------------------------------------


@pytest.mark.parametrize("name", ["module_poetics", "generative_map", "integration_proposal"])
def test_schema_is_valid_and_accepts_its_fixture(name: str) -> None:
    Draft202012Validator.check_schema(schema(name))
    assert errors(name, fixture(name)) == []


def test_generative_map_rejects_registration_and_bad_normals() -> None:
    record = fixture("generative_map")
    record["registration_accepted"] = True
    assert errors("generative_map", record)
    record = fixture("generative_map")
    record["cells"][0]["required_ports"][0]["normal"] = [0.6, 0.8]
    assert errors("generative_map", record)
    record = fixture("generative_map")
    record["cells"][0]["rarity_tier"] = 4
    assert errors("generative_map", record)


def test_integration_proposal_propose_needs_exactly_one_connection_kind() -> None:
    record = fixture("integration_proposal")
    record["sockets_used"] = [
        {"from": {"module_id": "a", "version": 1, "socket_id": "e"},
         "to": {"module_id": "b", "version": 1, "socket_id": "w"}}
    ]
    assert errors("integration_proposal", record)
    record["adapter_required"] = None
    assert errors("integration_proposal", record) == []
    abstain = fixture("integration_proposal")
    abstain.update(outcome="abstain", adapter_required=None, placement=None, confidence=0.0)
    assert errors("integration_proposal", abstain) == []


def test_module_poetics_schema_rejects_eligible_draft() -> None:
    record = fixture("module_poetics")
    record["metadata_status"] = "draft_mechanical"
    assert errors("module_poetics", record)
    record["eligibility"]["layout_eligible_derived"] = False
    assert errors("module_poetics", record) == []


def test_module_poetics_schema_rejects_wrong_sign() -> None:
    record = fixture("module_poetics")
    record["features"][0]["sign"] = "index"
    assert errors("module_poetics", record)


# --- derived drafts against the real 0.5.0 snapshot -------------------------


def real_records() -> list[tuple[Path, dict]]:
    return mp.derive_all_records(ROOT / mp.DEFAULT_INDEX)


def test_real_snapshot_yields_eleven_valid_drafts() -> None:
    records = real_records()
    assert len(records) == 11
    for path, record in records:
        assert errors("module_poetics", record) == [], path
        assert record["metadata_status"] == "draft_mechanical"
        assert record["eligibility"]["layout_eligible_derived"] is False


def test_real_drafts_leave_poetics_empty() -> None:
    for _, record in real_records():
        poetics = record["poetics"]
        assert poetics["poetics_status"] == "operator_pending"
        assert [poetics[k] for k in ("form_role", "rarity_tier", "apollonian", "dionysian", "surface_salience")] == [None] * 5
        assert poetics["style_tags"] == [] and poetics["unique_details"] == []


def test_real_draft_paths_follow_the_design() -> None:
    paths = {record["module_id"]: path.relative_to(ROOT).as_posix() for path, record in real_records()}
    assert paths["godot_gopro_industrial_hall_frame1097_v1"].endswith(
        "rooms/industrial-hall-panorama-v3/module_poetics_v1.json"
    )
    assert paths["godot_early_pocket_single_west_v1"] == (
        "godot_walk/room_catalog/module_poetics/godot_early_pocket_single_west_v1-v1.json"
    )
    assert len(set(paths.values())) == 11


def test_real_issue_168_pair_marks_tested_sockets_exact_pair_only() -> None:
    by_id = {record["module_id"]: record for _, record in real_records()}
    south = by_id["godot_gopro_industrial_hall_south_socket_v1"]["ports"]["tested_sockets"]
    assert south == [
        {"socket_id": "south", "pairs": [
            {"pair_id": "issue168_industrial_hall_south__debris_rock_north_v1",
             "placement_scope": "exact_pair_only"}]}
    ]
    assert by_id["godot_gopro_industrial_hall_frame1097_v1"]["ports"]["tested_sockets"] == []


def test_real_far_right_gap_is_a_void_and_an_index_feature() -> None:
    record = {r["module_id"]: r for _, r in real_records()}["godot_gopro_industrial_hall_frame1097_v1"]
    assert [v["void_id"] for v in record["voids"]] == ["source_frame_1097_far_right_gap"]
    kinds = {f["feature_id"]: f["sign"] for f in record["features"]}
    assert kinds["observed_opening:source_frame_1097_far_right_gap"] == "index"
    assert kinds["obstacle:support_post_00"] == "symbol"


def test_committed_drafts_validate() -> None:
    result = mp.validate_drafts(ROOT / mp.DEFAULT_INDEX)
    assert result == {"valid": True, "draft_count": 11, "errors": []}


# --- derive-all / validate behaviour in a scratch workspace ------------------


def scratch_module(module_id: str, scene: str, sockets: list[dict]) -> dict:
    return {
        "id": module_id, "version": 1, "scene": scene, "kind": "authored_room",
        "variant_status": "test", "sockets": sockets,
        "source_provenance": [FRAME], "visual_assets": [],
        "collision_provenance": "Authored.", "placement_footprint_xz": RECT,
        "collision_footprint_xz": RECT, "floor_elevation_m": 0.0, "ceiling_elevation_m": 3.0,
        "observed_openings": [], "obstacles": [],
    }


def scratch_workspace(tmp_path: Path) -> Path:
    east = {"id": "east", "local_floor_center": [6.0, 0.0, 2.0]}
    catalog = {
        "catalog_id": "test_kit", "catalog_version": "9.9.9",
        "modules": [
            scratch_module("kit_room_v1", "res://scenes/k.tscn", [east]),
            scratch_module("src_room_v1", SCENE, [dict(east, id="west")]),
        ],
        "tested_connector_pairs": [{
            "id": "pair", "status": "operator_accepted_first_pass_pair",
            "from": ["kit_room_v1", "east"], "to": ["src_room_v1", "west"],
            "scope": "This pair only.", "evidence": [],
        }],
        "source_video_adaptations": [],
    }
    snapshot = tmp_path / "godot_walk/room_catalog/catalog_snapshots/test_kit-9.9.9.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(json.dumps(catalog), encoding="utf-8")
    shutil.copy(CATALOG_DIR / "module_poetics.schema.json", tmp_path / mp.SCHEMA_PATH)
    return tmp_path / li.build_index(snapshot, root=tmp_path)["index"]


def test_scratch_derive_all_is_idempotent_and_validates(tmp_path: Path) -> None:
    index = scratch_workspace(tmp_path)
    first = mp.derive_all(index, tmp_path)
    second = mp.derive_all(index, tmp_path)
    assert sorted(item["status"] for item in first) == ["created", "created"]
    assert sorted(item["status"] for item in second) == ["unchanged", "unchanged"]
    assert (tmp_path / "godot_walk/source_library/sources/video-aaaaaaaaaaaaaaaa/rooms/r1/module_poetics_v1.json").is_file()
    assert (tmp_path / "godot_walk/room_catalog/module_poetics/kit_room_v1-v1.json").is_file()
    assert mp.validate_drafts(index, tmp_path)["valid"] is True


def test_scratch_derive_all_refuses_overwrite_and_writes_nothing_new(tmp_path: Path) -> None:
    index = scratch_workspace(tmp_path)
    kit_draft = tmp_path / "godot_walk/room_catalog/module_poetics/kit_room_v1-v1.json"
    kit_draft.parent.mkdir(parents=True)
    kit_draft.write_text("{}\n", encoding="utf-8")
    with pytest.raises(DeterministicWriteError):
        mp.derive_all(index, tmp_path)
    assert kit_draft.read_text(encoding="utf-8") == "{}\n"
    assert not list((tmp_path / "godot_walk/source_library").rglob("module_poetics_v1.json"))


def test_scratch_validate_reports_missing_and_stale_drafts(tmp_path: Path) -> None:
    index = scratch_workspace(tmp_path)
    mp.derive_all(index, tmp_path)
    kit_draft = tmp_path / "godot_walk/room_catalog/module_poetics/kit_room_v1-v1.json"
    record = json.loads(kit_draft.read_text(encoding="utf-8"))
    record["catalog_snapshot_sha256"] = "1" * 64
    kit_draft.write_text(json.dumps(record), encoding="utf-8")
    stale = mp.validate_drafts(index, tmp_path)
    assert not stale["valid"] and "catalog_snapshot_sha256" in stale["errors"][0]
    kit_draft.unlink()
    missing = mp.validate_drafts(index, tmp_path)
    assert not missing["valid"] and "missing draft" in missing["errors"][0]


def test_scratch_record_marks_tested_socket_but_stays_ineligible(tmp_path: Path) -> None:
    index = scratch_workspace(tmp_path)
    records = {r["module_id"]: r for _, r in mp.derive_all_records(index, tmp_path)}
    kit = records["kit_room_v1"]
    assert [s["socket_id"] for s in kit["ports"]["tested_sockets"]] == ["east"]
    assert kit["ports"]["untested_sockets"] == []
    assert kit["eligibility"] == {"layout_eligible_derived": False, "catalog_layout_eligible": None}
    assert records["src_room_v1"]["translation_chain"][0]["stage"] == "direct_frame"
    assert kit["shape"]["ceiling_height_m"] == 3.0
