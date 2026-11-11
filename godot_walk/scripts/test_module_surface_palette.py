"""Tests for the additive module surface/palette descriptor (#217)."""

from __future__ import annotations

import copy
import json
import shutil

import module_surface_palette as surfaces
from deterministic_json import ROOT


def first_profile():
    return surfaces.profile_paths()[0]


def test_builds_complete_surface_mappings_for_all_admitted_profiles():
    profiles = surfaces.profile_paths()
    assert len(profiles) == 11
    descriptors = [surfaces.build_descriptor(path) for path in profiles]
    assert all(set(record["surfaces"]) == set(surfaces.SURFACES) for record in descriptors)
    assert all(not surfaces.validate_descriptor(record, path) for record, path in zip(descriptors, profiles))
    profile_schema = json.loads((ROOT / surfaces.PROFILE_SCHEMA_PATH).read_text(encoding="utf-8"))
    import jsonschema

    profile_surface_schema = {
        "$schema": profile_schema["$schema"],
        "$defs": profile_schema["$defs"],
        "type": "object",
        "required": ["surfaces"],
        "properties": {"surfaces": {"$ref": "#/$defs/surfaces"}},
        "additionalProperties": False,
    }
    for descriptor in descriptors:
        jsonschema.validate({"surfaces": descriptor["surfaces"]}, profile_surface_schema)
    report = surfaces.coverage_report(descriptors)
    assert report["module_count"] == 11
    assert report["surface_count"] == 44
    assert report["counts"] == {"resolved": 40, "null": 3, "bespoke": 1, "unresolved": 0}
    assert report["counts"]["unresolved"] == 0
    assert report["operator_review"] == "pending"


def test_validator_rejects_an_unresolved_surface():
    profile_path = first_profile()
    descriptor = copy.deepcopy(surfaces.build_descriptor(profile_path))
    descriptor["surfaces"]["wall"]["palette_id"] = "missing_palette"
    errors = surfaces.validate_descriptor(descriptor, profile_path)
    assert any("unresolved palette_id" in error for error in errors)


def test_bespoke_surface_requires_reason_and_null_palette():
    profile_path = first_profile()
    descriptor = copy.deepcopy(surfaces.build_descriptor(profile_path))
    entry = descriptor["review"]["surfaces"]["trim"]
    entry.update(status="bespoke", bespoke_reason=None)
    errors = surfaces.validate_descriptor(descriptor, profile_path)
    assert any("bespoke surface requires null palette_id and a reason" in error for error in errors)


def test_validator_rejects_missing_surface_and_stale_profile_reference():
    profile_path = first_profile()
    descriptor = copy.deepcopy(surfaces.build_descriptor(profile_path))
    del descriptor["surfaces"]["ceiling"]
    descriptor["profile_ref"]["sha256"] = "0" * 64
    errors = surfaces.validate_descriptor(descriptor, profile_path)
    assert any("ceiling: unresolved surface" in error for error in errors)
    assert "profile_ref.sha256 does not match its profile" in errors


def test_descriptor_basis_records_profile_reference_and_evidence_status():
    profile_path = first_profile()
    descriptor = surfaces.build_descriptor(profile_path)
    for surface in surfaces.SURFACES:
        entry = descriptor["surfaces"][surface]
        review = descriptor["review"]["surfaces"][surface]
        assert descriptor["profile_ref"]["path"] in review["basis"]
        assert entry["provenance"] == review["basis"]
        assert str(ROOT) not in review["basis"]
        assert review["evidence_status"] in {"observed", "proposed"}


def test_per_surface_evidence_status_requires_direct_surface_provenance():
    by_id = {
        json.loads(path.read_text(encoding="utf-8"))["module_id"]: path
        for path in surfaces.profile_paths()
    }
    industrial = surfaces.build_descriptor(by_id["godot_gopro_industrial_hall_frame1097_v1"])
    industrial_review = industrial["review"]["surfaces"]
    assert industrial_review["floor"]["evidence_status"] == "observed"
    assert industrial_review["wall"]["evidence_status"] == "proposed"
    assert industrial_review["ceiling"]["evidence_status"] == "proposed"
    assert industrial_review["trim"]["evidence_status"] == "proposed"

    debris = surfaces.build_descriptor(by_id["video_ccf9722164a0bdc8_debris_window_rock_room_v1"])
    debris_review = debris["review"]["surfaces"]
    assert debris_review["wall"]["evidence_status"] == "observed"
    assert all(
        debris_review[name]["evidence_status"] == "proposed"
        for name in ("floor", "ceiling", "trim")
    )


def test_build_and_check_are_reproducible_from_another_checkout(tmp_path):
    profile_paths = surfaces.profile_paths()
    for profile_path in profile_paths:
        target = tmp_path / profile_path.resolve().relative_to(ROOT.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(profile_path, target)
    for relative in (
        surfaces.ACOUSTICS_PATH,
        surfaces.REGISTRY_PATH,
        surfaces.SCHEMA_PATH,
        surfaces.PROFILE_SCHEMA_PATH,
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)

    assert not surfaces.run(tmp_path, build=True)
    assert not surfaces.run(tmp_path, build=False)
    for profile_path in surfaces.profile_paths(tmp_path):
        descriptor = json.loads(surfaces.descriptor_path(profile_path, tmp_path).read_text(encoding="utf-8"))
        assert str(tmp_path) not in " ".join(
            entry["basis"] for entry in descriptor["review"]["surfaces"].values()
        )


def test_committed_report_and_mapping_table_are_current():
    descriptors = [surfaces.build_descriptor(path) for path in surfaces.profile_paths()]
    report_path = ROOT / surfaces.REPORT_PATH
    table_path = ROOT / surfaces.TABLE_PATH
    assert json.loads(report_path.read_text(encoding="utf-8")) == surfaces.coverage_report(descriptors)
    assert table_path.read_text(encoding="utf-8") == surfaces.mapping_table(descriptors)
    assert not surfaces.run(ROOT, build=False)
