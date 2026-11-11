"""T5 source and module lighting/scale overlay checks."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path

import pytest
import lighting_scale_overlay as ls
import template_validate as tv
from deterministic_json import ROOT, sha256_file


def records():
    return [json.loads(path.read_text(encoding="utf-8")) for path in ls.overlay_paths()]


def _copy_overlay_dependencies(record, root: Path) -> None:
    schema_path = root / ls.SCHEMA_PATH
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_bytes((ROOT / ls.SCHEMA_PATH).read_bytes())
    template = root / "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_bytes((ROOT / "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md").read_bytes())
    record["template_ref"] = {
        "version": "generation-template-0.1.0",
        "path": "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md",
        "sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
    }


def _replace_field_evidence(record, reference) -> None:
    evidence = [reference]
    for name in ("colour_temperature_k", "illuminance_lux"):
        record["lighting"][name]["evidence"] = evidence
    for fixture in record["lighting"]["fixture_layout"]:
        fixture["evidence"] = evidence
    if record["scale"]["anchor"] is not None:
        record["scale"]["anchor"]["evidence"] = evidence


def test_exactly_one_source_and_one_module_overlay_validate() -> None:
    overlays = records()
    assert len(overlays) == 2
    assert {record["record_kind"] for record in overlays} == {"source", "module"}
    assert all(ls.validate_overlay(record) == [] for record in overlays)
    assert all(record["scale"]["status"] == "uncalibrated" for record in overlays)
    assert all(record["lighting"]["review_status"] == "pending_operator_review" for record in overlays)
    assert all(record["lighting"]["colour_temperature_k"]["review_status"] == "pending_operator_review" for record in overlays)
    assert all(record["lighting"]["illuminance_lux"]["review_status"] == "pending_operator_review" for record in overlays)
    assert all(record["lighting"]["fixture_layout"][0]["count"] > 0 for record in overlays)
    assert all("Agent-proposed" in record["lighting"]["colour_temperature_k"]["provenance"] for record in overlays)


def test_missing_overlay_has_explicit_uncalibrated_not_reviewed_default() -> None:
    state = ls.lighting_scale_state(None)
    assert state["lighting"]["status"] == "uncalibrated_not_reviewed"
    assert state["lighting"]["review_status"] == "not_reviewed"
    assert state["lighting"]["colour_temperature_k"]["value"] is None
    assert state["lighting"]["illuminance_lux"]["value"] is None
    assert state["lighting"]["fixture_layout"] == []
    assert state["scale"] == {
        "status": "uncalibrated",
        "anchor": None,
        "review_status": "not_reviewed",
    }


def test_default_is_available_for_every_legacy_source_and_module() -> None:
    base_paths = tv.source_manifest_paths() + tv.module_profile_paths()
    assert base_paths
    for path in base_paths:
        state = ls.lighting_scale_state(None)
        assert state["lighting"]["review_status"] == "not_reviewed", path
        assert state["scale"]["status"] == "uncalibrated", path


def test_validator_rejects_estimated_anchor_marked_calibrated() -> None:
    record = copy.deepcopy(records()[0])
    record["scale"]["status"] = "calibrated"
    assert any(
        "anchor marked measured" in error for error in ls.validate_overlay(record)
    )


def test_validator_rejects_measured_anchor_without_committed_measurement() -> None:
    record = copy.deepcopy(records()[0])
    record["scale"]["status"] = "calibrated"
    record["scale"]["anchor"]["status"] = "measured"
    assert any(
        "cited committed measurement" in error
        for error in ls.validate_overlay(record)
    )


@pytest.mark.parametrize("schema_version", [1, 2])
def test_legacy_source_manifests_without_scale_block_accept_uncalibrated_overlay(
    tmp_path, schema_version: int
) -> None:
    record = next(item for item in records() if item["record_kind"] == "source")
    record = copy.deepcopy(record)
    _copy_overlay_dependencies(record, tmp_path)
    base = {"schema_version": schema_version, "source_id": record["record_id"]}
    base_path = tmp_path / "legacy-source.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    reference = {
        "path": "legacy-source.json",
        "sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
    }
    record["base_record"] = reference
    _replace_field_evidence(record, reference)
    assert ls.validate_overlay(record, tmp_path) == []


def test_legacy_source_rejects_measured_anchor_without_measurement(tmp_path) -> None:
    record = next(item for item in records() if item["record_kind"] == "source")
    record = copy.deepcopy(record)
    _copy_overlay_dependencies(record, tmp_path)
    base = {"schema_version": 1, "source_id": record["record_id"]}
    base_path = tmp_path / "legacy-source.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    reference = {
        "path": "legacy-source.json",
        "sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
    }
    record["base_record"] = reference
    _replace_field_evidence(record, reference)
    record["scale"]["anchor"]["status"] = "measured"
    record["scale"]["anchor"]["measurement"] = None

    errors = ls.validate_overlay(record, tmp_path)
    assert any("cited committed measurement" in error for error in errors)
    assert ls.lighting_scale_state(record, tmp_path)["scale"]["anchor"] is None


def test_measured_anchor_rejects_boolean_measurement(tmp_path, monkeypatch) -> None:
    record = next(item for item in records() if item["record_kind"] == "source")
    record = copy.deepcopy(record)
    _copy_overlay_dependencies(record, tmp_path)
    base = {"schema_version": 1, "source_id": record["record_id"]}
    base_path = tmp_path / "legacy-source.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    reference = {
        "path": "legacy-source.json",
        "sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
    }
    record["base_record"] = reference
    _replace_field_evidence(record, reference)
    anchor = record["scale"]["anchor"]
    anchor["status"] = "measured"
    anchor["value_m"] = 1
    measurement_path = tmp_path / "measurement.json"
    measurement_path.write_text(json.dumps({"value_m": True}), encoding="utf-8")
    anchor["measurement"] = {
        "path": "measurement.json",
        "sha256": hashlib.sha256(measurement_path.read_bytes()).hexdigest(),
        "json_pointer": "/value_m",
    }
    monkeypatch.setattr(ls, "_committed_measurement_error", lambda reference, root: None)

    errors = ls.validate_overlay(record, tmp_path)

    assert any("finite numeric value" in error for error in errors)


def test_base_anchor_agreement_checks_kind_as_well_as_measurement(tmp_path) -> None:
    record = next(item for item in records() if item["record_kind"] == "module")
    record = copy.deepcopy(record)
    _copy_overlay_dependencies(record, tmp_path)
    base = json.loads((ROOT / record["base_record"]["path"]).read_text(encoding="utf-8"))
    base["scale"]["anchor"] = {
        "kind": "door_height",
        "value_m": record["scale"]["anchor"]["value_m"],
        "frame_id": None,
    }
    base_path = tmp_path / "module-profile.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    reference = {
        "path": "module-profile.json",
        "sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
    }
    record["base_record"] = reference
    _replace_field_evidence(record, reference)
    assert any(
        "scale anchor conflicts with base record" in error
        for error in ls.validate_overlay(record, tmp_path)
    )


@pytest.mark.parametrize("overlay_frame_id", ["capture-7", "capture-8"])
def test_base_anchor_frame_id_must_match(tmp_path, overlay_frame_id: str) -> None:
    record = next(item for item in records() if item["record_kind"] == "module")
    record = copy.deepcopy(record)
    _copy_overlay_dependencies(record, tmp_path)
    anchor = record["scale"]["anchor"]
    anchor["frame_id"] = overlay_frame_id
    base = json.loads((ROOT / record["base_record"]["path"]).read_text(encoding="utf-8"))
    base["scale"]["anchor"] = {
        "kind": anchor["kind"],
        "value_m": anchor["value_m"],
        "frame_id": "capture-7",
    }
    base_path = tmp_path / "module-profile.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    reference = {
        "path": "module-profile.json",
        "sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
    }
    record["base_record"] = reference
    _replace_field_evidence(record, reference)
    errors = ls.validate_overlay(record, tmp_path)
    if overlay_frame_id == "capture-7":
        assert errors == []
    else:
        assert any("scale anchor conflicts with base record" in error for error in errors)


def test_overlay_discovery_includes_source_derived_module_profiles(tmp_path) -> None:
    schema = tmp_path / ls.SCHEMA_PATH
    schema.parent.mkdir(parents=True)
    schema.write_bytes((ROOT / ls.SCHEMA_PATH).read_bytes())
    source_dir = tmp_path / "godot_walk/source_library/sources/source-id/rooms/room-id"
    source_dir.mkdir(parents=True)
    overlay = source_dir / "module_profile_lighting_scale_v1.json"
    overlay.write_text("{}", encoding="utf-8")
    assert ls.overlay_paths(tmp_path) == [overlay]
    report = tv.validate_repository(tmp_path)
    assert any(
        "module_profile_lighting_scale_v1.json" in error
        and "schema_version" in error
        for error in report.errors
    )


def test_untracked_measurement_with_matching_hash_and_value_is_rejected() -> None:
    record = next(item for item in records() if item["record_kind"] == "source")
    record = copy.deepcopy(record)
    record["scale"]["status"] = "calibrated"
    anchor = record["scale"]["anchor"]
    anchor["status"] = "measured"
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        path = Path(directory) / "measurement.json"
        path.write_text(json.dumps({"value": anchor["value_m"]}), encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        anchor["measurement"] = {
            "path": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "json_pointer": "/value",
        }
        errors = ls.validate_overlay(record)
    assert any("must reference a committed measurement" in error for error in errors)


def test_source_overlay_cannot_mark_null_manifest_anchor_measured() -> None:
    record = next(item for item in records() if item["record_kind"] == "source")
    record = copy.deepcopy(record)
    record["scale"]["anchor"]["status"] = "measured"
    assert any(
        "conflicts with null base anchor" in error
        for error in ls.validate_overlay(record)
    )


def test_reviewed_values_require_cited_evidence() -> None:
    record = copy.deepcopy(records()[0])
    field = record["lighting"]["illuminance_lux"]
    field["review_status"] = "operator_reviewed"
    field["evidence"] = []
    assert any(
        "reviewed values require cited evidence" in error
        for error in ls.validate_overlay(record)
    )


def test_aggregate_reviewed_status_with_pending_fields_is_rejected() -> None:
    record = copy.deepcopy(records()[0])
    record["lighting"]["status"] = "reviewed"
    record["lighting"]["review_status"] = "operator_reviewed"
    assert any(
        "aggregate review status conflicts" in error
        or "aggregate status is unsupported" in error
        for error in ls.validate_overlay(record)
    )


def test_operator_reviewed_fields_without_review_evidence_are_rejected() -> None:
    record = copy.deepcopy(records()[0])
    fields = [record["lighting"][name] for name in ("colour_temperature_k", "illuminance_lux")]
    fields += record["lighting"]["fixture_layout"]
    for field in fields:
        field["review_status"] = "operator_reviewed"
    record["lighting"]["status"] = "reviewed"
    record["lighting"]["review_status"] = "operator_reviewed"
    assert any(
        "who/when/what review evidence" in error for error in ls.validate_overlay(record)
    )


def test_mixed_field_review_statuses_are_rejected() -> None:
    record = copy.deepcopy(records()[0])
    record["lighting"]["illuminance_lux"]["review_status"] = "pending_vision_model_review"
    assert any("mixed review statuses" in error for error in ls.validate_overlay(record))


def test_scale_aggregate_review_status_must_match_anchor() -> None:
    record = copy.deepcopy(records()[0])
    record["scale"]["review_status"] = "operator_reviewed"
    assert any(
        "scale aggregate review status conflicts" in error
        for error in ls.validate_overlay(record)
    )


def test_review_evidence_reviewer_kind_must_match_field_status() -> None:
    record = copy.deepcopy(records()[0])
    field = record["lighting"]["illuminance_lux"]
    field["review_status"] = "operator_reviewed"
    field["review_evidence"] = [{
        "reviewer_kind": "vision_model",
        "reviewer": "vision-reviewer",
        "reviewed_at": "2026-11-11T00:00:00Z",
        "what_was_reviewed": "Illuminance estimate",
        "evidence": [record["base_record"]],
    }]
    assert any(
        "reviewer kind conflicts" in error for error in ls.validate_overlay(record)
    )


def test_review_evidence_requires_iso_date_time() -> None:
    record = copy.deepcopy(records()[0])
    field = record["lighting"]["colour_temperature_k"]
    field["review_status"] = "operator_reviewed"
    field["review_evidence"] = [{
        "reviewer_kind": "operator",
        "reviewer": "operator-1",
        "reviewed_at": "yesterday",
        "what_was_reviewed": "Colour temperature estimate",
        "evidence": [record["base_record"]],
    }]
    assert any(
        "ISO date-time" in error for error in ls.validate_overlay(record)
    )


def test_state_helper_does_not_expose_invalid_aggregate_claims() -> None:
    record = copy.deepcopy(records()[0])
    record["lighting"]["status"] = "reviewed"
    state = ls.lighting_scale_state(record)
    assert state["lighting"]["review_status"] == "not_reviewed"
    assert state["scale"]["status"] == "uncalibrated"


def test_validator_reports_missing_or_unreadable_base_without_raising(tmp_path) -> None:
    record = copy.deepcopy(records()[1])
    record["base_record"] = {"path": "missing.json", "sha256": "0" * 64}
    assert any("missing" in error for error in ls.validate_overlay(record))
    (tmp_path / ls.SCHEMA_PATH).parent.mkdir(parents=True)
    (tmp_path / ls.SCHEMA_PATH).write_bytes((ROOT / ls.SCHEMA_PATH).read_bytes())
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md").write_bytes(
        (ROOT / "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md").read_bytes()
    )
    record["template_ref"] = {
        "version": "generation-template-0.1.0",
        "path": "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md",
        "sha256": sha256_file(tmp_path / "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md"),
    }
    bad_base = tmp_path / "bad.json"
    bad_base.write_text("not json", encoding="utf-8")
    record["base_record"] = {
        "path": "bad.json",
        "sha256": sha256_file(bad_base),
    }
    for name in ("colour_temperature_k", "illuminance_lux"):
        record["lighting"][name]["evidence"] = [record["base_record"]]
    for fixture in record["lighting"]["fixture_layout"]:
        fixture["evidence"] = [record["base_record"]]
    record["scale"]["anchor"]["evidence"] = [record["base_record"]]
    assert any(
        "cannot read referenced record" in error
        for error in ls.validate_overlay(record, tmp_path)
    )


def test_repository_validation_includes_t5_overlays_additively() -> None:
    report = tv.validate_repository(ROOT)
    assert report.valid, report.errors
