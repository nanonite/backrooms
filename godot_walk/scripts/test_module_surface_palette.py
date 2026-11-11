"""Tests for the additive module surface/palette descriptor (#217)."""

from __future__ import annotations

import copy
import json

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
    entry = descriptor["surfaces"]["trim"]
    entry.update(status="bespoke", palette_id=None, bespoke_reason=None)
    errors = surfaces.validate_descriptor(descriptor, profile_path)
    assert any("bespoke surface requires null palette_id and a reason" in error for error in errors)


def test_committed_report_and_mapping_table_are_current():
    descriptors = [surfaces.build_descriptor(path) for path in surfaces.profile_paths()]
    report_path = ROOT / surfaces.REPORT_PATH
    table_path = ROOT / surfaces.TABLE_PATH
    assert json.loads(report_path.read_text(encoding="utf-8")) == surfaces.coverage_report(descriptors)
    assert table_path.read_text(encoding="utf-8") == surfaces.mapping_table(descriptors)
