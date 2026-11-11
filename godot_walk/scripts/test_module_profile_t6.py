"""Issue #219 checks for additive ceiling, exit, role and mood descriptors."""

from __future__ import annotations

import json
import copy
import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_profile_t6 as t6
import template_validate as tv
from backfill_module_profiles import expected_profiles
from deterministic_json import ROOT, canonical_bytes, sha256_file

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


def test_t6_record_validator_returns_unreadable_reference_errors(monkeypatch) -> None:
    invalid = copy.deepcopy(overlay("godot_early_pocket_pass_through_v1"))
    base_path = (ROOT / invalid["base_profile"]["path"]).resolve()
    original = tv.sha256_file

    def unreadable(path: Path) -> str:
        if path.resolve() == base_path:
            raise PermissionError("test unreadable reference")
        return original(path)

    monkeypatch.setattr(tv, "sha256_file", unreadable)
    errors = t6.validate_record(invalid)
    assert any("cannot read" in error and "base_profile" in error for error in errors)


@pytest.mark.parametrize("reference_kind", ["base_profile", "metric_citation"])
def test_t6_record_validator_returns_invalid_utf8_reference_errors(
    monkeypatch, reference_kind: str
) -> None:
    invalid = copy.deepcopy(overlay("godot_early_pocket_pass_through_v1"))
    if reference_kind == "base_profile":
        unreadable_path = (ROOT / invalid["base_profile"]["path"]).resolve()
        expected = "base_profile: cannot read"
    else:
        unreadable_path = (ROOT / t6.PROBE_RESULTS).resolve()
        expected = "cannot read cited reference"
    original = Path.read_text

    def invalid_utf8(path: Path, *args, **kwargs):
        if path.resolve() == unreadable_path:
            raise UnicodeDecodeError("utf-8", b"\\xff", 0, 1, "invalid byte")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", invalid_utf8)
    assert any(expected in error for error in t6.validate_record(invalid))


@pytest.mark.parametrize(
    ("field", "mutate", "expected"),
    [
        ("ceiling_height_m", lambda metric: metric.update(value=None), "null values"),
        ("ceiling_height_m", lambda metric: metric.update(basis_status="authored"), "measured basis"),
        ("ceiling_height_m", lambda metric: metric.update(value=9.0), "beyond tolerance"),
        ("volume_nominal_m3", lambda metric: metric.pop("derivation"), "require a derivation"),
        ("ceiling_min_m", lambda metric: metric.update(source="authored without a field pointer"), "must cite their source"),
        ("ceiling_min_m", lambda metric: metric.update(source=metric["source"].replace("/shape/ceiling_min_m", "/shape/missing")), "citation field does not exist"),
        ("ceiling_min_m", lambda metric: metric.update(source="godot_walk/evidence/2026-11-11-issue-216/module_acoustics_probe_results.json#/modules/godot_early_pocket_pass_through_v1@1/metrics/ceiling_height_m"), "authored values must cite authored inputs"),
    ],
)
def test_t6_validator_rejects_contradictory_or_unresolvable_provenance(
    field, mutate, expected: str
) -> None:
    invalid = copy.deepcopy(overlay("godot_early_pocket_pass_through_v1"))
    mutate(invalid["ceiling_volume"][field])
    assert any(expected in error for error in tv.module_profile_t6_errors(invalid))


def test_measured_height_rejects_authored_probe_hint_citation() -> None:
    invalid = copy.deepcopy(overlay("godot_early_pocket_pass_through_v1"))
    metric = invalid["ceiling_volume"]["ceiling_height_m"]
    metric["source"] = metric["source"].replace(
        "/metrics/ceiling_height_m", "/ceiling_hint_m"
    )
    assert any(
        "measured probe field" in error
        for error in tv.module_profile_t6_errors(invalid)
    )


def test_derived_volume_basis_must_match_authored_geometry_citations() -> None:
    invalid = copy.deepcopy(overlay("godot_early_pocket_pass_through_v1"))
    invalid["ceiling_volume"]["volume_nominal_m3"]["basis_status"] = "measured"
    assert any(
        "basis_status does not match" in error
        for error in tv.module_profile_t6_errors(invalid)
    )


def test_measured_value_and_tolerance_cannot_expand_to_hide_a_mismatch() -> None:
    invalid = copy.deepcopy(overlay("godot_early_pocket_pass_through_v1"))
    metric = invalid["ceiling_volume"]["ceiling_height_m"]
    metric["value"] = 999
    metric["tolerance"] = 1000
    assert any(
        "maximum" in error or "tolerance" in error
        for error in tv.module_profile_t6_errors(invalid)
    )


def test_gmap_consumer_output_matches_the_pre_t6_committed_map() -> None:
    import gmap_build
    import gmap_library

    index_path = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
    committed_path = ROOT / "godot_walk/room_catalog/generative_maps/gmap-1-gmap-0.12.0.json"
    library = gmap_library.load_library(index_path)
    output = gmap_build.build_map(
        1, library, cells=12, version=gmap_build.GENERATOR_VERSION_V12
    )
    committed = json.loads(committed_path.read_text(encoding="utf-8"))
    assert output == committed
    assert hashlib.sha256(canonical_bytes(committed)).hexdigest() == (
        "5c6f61548844b8afee308e6ea7e204dd6c1ffc832d78f3deba33d37dadd41dce"
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

