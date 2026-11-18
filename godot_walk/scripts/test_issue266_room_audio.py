"""Checks for the #266 versioned footstep and acoustics records.

These tests only read accepted rooms and verify the NEW versioned files. They
never claim the recorded materials sound correct: that is an operator step.
"""

from __future__ import annotations

import json

from deterministic_json import ROOT, sha256_file


def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


EXPECTED_KEYS = {
    "video_22909eb734e4d8e2_slot_canyon_courtyard_v1@1",
    "video_d857abe7a94da9d1_nested_light_corridor_v1@1",
    "video_d92fc1fa764aa3a2_snow_garden_courtyard_v2@1",
    "video_102caf53423018b7_chevron_corridor_v1@1",
    "video_2671b32f256a4ee7_chevron_corridor_v1@1",
    "video_61b91dbeb9026dc7_chevron_cross_corridor_v1@1",
}


def test_generated_records_match_deterministic_projection():
    from issue266_room_audio import check

    assert check() == []


def test_all_six_rooms_have_a_recorded_material_and_rationale():
    footstep = _load("godot_walk/room_catalog/footstep_materials_v0.1.0.json")
    acoustics = _load("godot_walk/room_catalog/module_acoustics_v0.3.0.json")
    assert set(footstep["rooms"]) == EXPECTED_KEYS
    assert set(acoustics["modules"]) == EXPECTED_KEYS
    for key in EXPECTED_KEYS:
        room = footstep["rooms"][key]
        module = acoustics["modules"][key]
        assert room["floor_class"]
        assert room["rationale"]
        assert room["floor_evidence"]["source"].endswith("room.gd")
        assert room["poetics"]["sha256"]
        assert module["rationale"]
        assert module["reverb_character"] in ("open_courtyard", "enclosed_corridor")
        assert all(0.0 <= module["reverb"][field] <= 1.0 for field in ("room_size", "damping", "wet"))


def test_acoustics_are_derived_not_measured_and_listening_is_pending():
    acoustics = _load("godot_walk/room_catalog/module_acoustics_v0.3.0.json")
    assert acoustics["reverb_mapping"]["operator_listening"] == "pending"
    assert acoustics["reverb_mapping"]["inputs"] == "derived_from_shape_metadata"
    assert acoustics["relationship_to_v0.2.0"].startswith("additive overlay")
    for module in acoustics["modules"].values():
        assert module["provenance"] == "derived_from_shape_metadata"
        assert module["absorption"]["status"] == "unknown"


def test_missing_audio_layers_are_listed_and_no_audio_was_authored():
    footstep = _load("godot_walk/room_catalog/footstep_materials_v0.1.0.json")
    missing = {item["material"] for item in footstep["missing_layers"]}
    assert {"snow", "rock_sand"} <= missing
    assert footstep["operator_listening"] == "pending"
    assert footstep["audio_authoring_status"].startswith("none")
    snow = footstep["rooms"]["video_d92fc1fa764aa3a2_snow_garden_courtyard_v2@1"]
    assert snow["footstep_tag"] is None
    assert snow["runtime_fallback"] == "default"
    rock = footstep["rooms"]["video_22909eb734e4d8e2_slot_canyon_courtyard_v1@1"]
    assert rock["footstep_tag"] == "debris"
    assert rock["status"] == "proxy_existing_tag"


def test_shared_acoustics_and_footstep_generator_are_untouched():
    from generate_footstep_audio import check as footstep_check

    # The measured sidecar and its pin are unchanged by this issue.
    path = ROOT / "godot_walk/room_catalog/module_acoustics_v0.2.0.json"
    pin = (ROOT / "godot_walk/room_catalog/module_acoustics_v0.2.0.json.sha256").read_text()
    assert pin == f"{sha256_file(path)}  {path.name}\n"
    # No new audio samples were authored: the deterministic generator is intact.
    assert footstep_check() == []
    manifest = _load("godot_walk/audio/footsteps/provenance.json")
    assert set(manifest["tags"]) == {
        "carpet", "concrete", "tile", "plaster", "metal", "wood", "debris", "default", "land"
    }
    audio_root = ROOT / "godot_walk/audio/footsteps"
    assert not any((audio_root / tag).exists() for tag in ("snow", "rock", "sand"))


def test_gallery_entry_lists_the_new_materials_as_pending():
    gallery = _load(
        "godot_walk/evidence/2026-11-17-issue-266-footsteps-acoustics/"
        "gallery_entry_v0.1.0.json"
    )
    assert gallery["issue"] == 266
    assert gallery["operator_listening"] == "pending"
    assert {entry["module"] for entry in gallery["entries"]} == EXPECTED_KEYS
    assert all(entry["audition_status"] == "pending_operator_listening" for entry in gallery["entries"])
