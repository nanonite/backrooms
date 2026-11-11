"""Issue #219 checks for additive ceiling, exit, role and mood descriptors."""

from __future__ import annotations

import json
import copy
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_profile_t6 as t6
import template_validate as tv
from backfill_module_profiles import expected_profiles
from deterministic_json import ROOT, sha256_file

EXPECTED = {item.module_id: item for item in expected_profiles()}
OVERLAYS = {
    json.loads(path.read_text(encoding="utf-8"))["module_id"]: path
    for path in tv.module_profile_t6_paths()
}


def overlay(module_id: str) -> dict[str, Any]:
    return json.loads(OVERLAYS[module_id].read_text(encoding="utf-8"))


def test_all_eleven_admitted_modules_have_valid_editable_overlays() -> None:
    assert set(OVERLAYS) == set(EXPECTED)
    assert len(OVERLAYS) == 11
    for module_id in EXPECTED:
        assert tv.module_profile_t6_errors(overlay(module_id)) == []


def test_ceiling_and_volume_provenance_is_explicit_per_field() -> None:
    fields = {
        "ceiling_min_m",
        "ceiling_max_m",
        "ceiling_height_m",
        "ceiling_kind",
        "volume_nominal_m3",
        "volume_measured_m3",
    }
    for module_id in EXPECTED:
        descriptors = overlay(module_id)["ceiling_volume"]
        assert set(descriptors) == fields
        assert all(
            {"value", "status", "basis_status", "source"}.issubset(v)
            for v in descriptors.values()
        )
        assert descriptors["ceiling_min_m"]["status"] == "authored"
        assert descriptors["ceiling_max_m"]["status"] == "authored"
        assert descriptors["ceiling_height_m"]["status"] == "measured"
        assert "issue-216" in descriptors["ceiling_height_m"]["source"]
        assert "capped by the profile ceiling hint" in descriptors["ceiling_height_m"]["source"]
        assert descriptors["volume_nominal_m3"]["status"] == "derived"
        assert descriptors["volume_nominal_m3"]["basis_status"] == "authored"
        assert "authored" in descriptors["volume_nominal_m3"]["source"]
        assert descriptors["volume_nominal_m3"]["derivation"]
        assert descriptors["volume_measured_m3"]["status"] == "unmeasured"
        assert descriptors["volume_measured_m3"]["basis_status"] == "unmeasured"
        assert descriptors["volume_measured_m3"]["value"] is None


def test_exits_match_only_recorded_socket_openings() -> None:
    for module_id, item in EXPECTED.items():
        actual = overlay(module_id)
        base = json.loads(item.path.read_text(encoding="utf-8"))
        assert [entry["socket_id"] for entry in actual["exits"]] == [
            entry["socket_id"] for entry in base["exits"]
        ]
    no_socket_modules = {
        module_id for module_id, item in EXPECTED.items()
        if not json.loads(item.path.read_text(encoding="utf-8"))["exits"]
    }
    assert no_socket_modules
    assert all(not overlay(module_id)["exits"] for module_id in no_socket_modules)


def test_role_and_mood_drafts_are_pending_operator_taste_review() -> None:
    for module_id in EXPECTED:
        actual = overlay(module_id)
        assert actual["roles"]["review_status"] == t6.REVIEW_STATUS
        assert actual["mood"]["review_status"] == t6.REVIEW_STATUS
        assert actual["mood"]["evidence"]
        assert all(
            0 <= actual["mood"][axis] <= 1
            for axis in ("tension", "dread", "curiosity", "safety", "anomaly")
        )


def test_overlay_validation_rejects_missing_provenance_and_inferred_exits() -> None:
    module_id = "godot_early_pocket_pass_through_v1"
    missing_provenance = copy.deepcopy(overlay(module_id))
    del missing_provenance["ceiling_volume"]["volume_nominal_m3"]["status"]
    assert tv.module_profile_t6_errors(missing_provenance)

    inferred_exit = copy.deepcopy(overlay(module_id))
    inferred_exit["exits"].append(dict(inferred_exit["exits"][0]))
    assert any(
        "exactly the recorded" in error
        for error in tv.module_profile_t6_errors(inferred_exit)
    )


def test_overlay_validation_rejects_mood_values_outside_design_scale() -> None:
    invalid = copy.deepcopy(overlay("godot_early_pocket_pass_through_v1"))
    invalid["mood"]["dread"] = 1.1
    assert tv.module_profile_t6_errors(invalid)


def test_t6_record_validator_returns_missing_base_reference_errors() -> None:
    invalid = copy.deepcopy(overlay("godot_early_pocket_pass_through_v1"))
    invalid["base_profile"]["path"] = "godot_walk/room_catalog/missing-profile.json"
    assert any(
        "base_profile" in error and "missing" in error
        for error in t6.validate_record(invalid)
    )


def test_overlays_are_additive_and_do_not_change_maps_or_v1_profiles() -> None:
    assert len(tv.module_profile_paths()) == 11
    assert len(tv.generative_map_paths()) >= 1
    for module_id, item in EXPECTED.items():
        record = overlay(module_id)
        assert record["base_profile"] == {
            "path": item.path.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(item.path),
        }
        assert not {"cells", "map_id", "generator"}.intersection(record)
    assert t6.check() == []

