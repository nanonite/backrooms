"""T5 source and module lighting/scale overlay checks."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
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
    assert state["valid"] is False


_ANCHOR_STATES = ("none", "estimated", "measured")
_MEASUREMENT_STATES = (
    "absent", "valid", "missing_file", "untracked", "bad_hash", "bad_pointer",
    "bool", "string", "zero", "negative", "nan",
)
_AGGREGATE_STATES = ("uncalibrated", "calibrated")
def _write_fixture_repo(root: Path, measurement_state: str) -> dict:
    record = copy.deepcopy(next(item for item in records() if item["record_kind"] == "module"))
    _copy_overlay_dependencies(record, root)
    base = json.loads((ROOT / record["base_record"]["path"]).read_text(encoding="utf-8"))
    base_path = root / "base.json"
    base_path.parent.mkdir(parents=True, exist_ok=True)
    base_path.write_text(json.dumps(base), encoding="utf-8")
    base_ref = {"path": "base.json", "sha256": hashlib.sha256(base_path.read_bytes()).hexdigest()}
    record["base_record"] = base_ref
    _replace_field_evidence(record, base_ref)
    measurement_values = {
        "valid": 1.75, "bool": True, "string": "1.75", "zero": 0,
        "negative": -1, "nan": float("nan"),
    }
    if measurement_state not in {"absent", "missing_file"}:
        value = measurement_values.get(measurement_state, 1.75)
        measurement_path = root / "measurement.json"
        measurement_path.write_text(json.dumps({"height_m": value}), encoding="utf-8")
        measurement_ref = {
            "path": "measurement.json",
            "sha256": hashlib.sha256(measurement_path.read_bytes()).hexdigest(),
            "json_pointer": "/height_m" if measurement_state != "bad_pointer" else "/wrong",
            "tolerance_m": 0,
        }
        if measurement_state == "bad_hash":
            measurement_ref["sha256"] = "0" * 64
        record["scale"]["anchor"]["measurement"] = measurement_ref
        if measurement_state == "untracked":
            tracked = ["docs", "godot_walk"]
        else:
            tracked = ["docs", "godot_walk", "measurement.json"]
    else:
        record["scale"]["anchor"]["measurement"] = None
        tracked = ["docs", "godot_walk"]
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=root, check=True)
    subprocess.run(["git", "add", *tracked], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixtures"], cwd=root, check=True)
    return record


@pytest.mark.parametrize(
    ("anchor_status", "measurement_state", "aggregate_status"),
    [(anchor, measurement, aggregate) for anchor in _ANCHOR_STATES
     for measurement in _MEASUREMENT_STATES for aggregate in _AGGREGATE_STATES],
)
def test_anchor_status_measurement_and_aggregate_matrix_real_validator(
    tmp_path, anchor_status: str, measurement_state: str, aggregate_status: str,
) -> None:
    root = tmp_path / f"{anchor_status}-{measurement_state}-{aggregate_status}"
    root.mkdir()
    record = _write_fixture_repo(root, measurement_state)
    anchor = record["scale"]["anchor"]
    record["scale"]["status"] = aggregate_status
    if anchor_status == "none":
        if measurement_state == "absent":
            record["scale"]["anchor"] = None
        else:
            anchor["status"] = "none"
            anchor["value_m"] = 1.75
        record["scale"]["review_status"] = "not_reviewed"
    else:
        anchor["status"] = anchor_status
        anchor["value_m"] = 1.75
        if measurement_state == "absent":
            anchor["measurement"] = None
        elif measurement_state == "missing_file":
            anchor["measurement"] = {
                "path": "missing.json", "sha256": "0" * 64,
                "json_pointer": "/height_m", "tolerance_m": 0,
            }
    base_path = root / "base.json"
    base = json.loads(base_path.read_text(encoding="utf-8"))
    base["scale"] = {
        "status": aggregate_status,
        "anchor": None if anchor_status == "none" else {
            "kind": anchor["kind"], "value_m": 1.75, "frame_id": anchor.get("frame_id")
        },
    }
    base_path.write_text(json.dumps(base), encoding="utf-8")
    base_ref = {"path": "base.json", "sha256": hashlib.sha256(base_path.read_bytes()).hexdigest()}
    record["base_record"] = base_ref
    _replace_field_evidence(record, base_ref)
    subprocess.run(["git", "add", "base.json"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base update"], cwd=root, check=True)
    accepted = (
        anchor_status == "measured" and measurement_state == "valid"
        and aggregate_status == "calibrated"
    ) or (
        anchor_status in {"none", "estimated"} and measurement_state == "absent"
        and aggregate_status == "uncalibrated"
    )
    errors = ls.validate_overlay(record, root)
    assert (not errors) is accepted, (anchor_status, measurement_state, aggregate_status, errors)


def _leaf_paths(value, prefix=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaf_paths(item, prefix + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaf_paths(item, prefix + (index,))
    else:
        yield prefix


def _replace_path(value, path, replacement):
    result = copy.deepcopy(value)
    target = result
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = replacement
    return result


@pytest.mark.parametrize("replacement", [None, True, [], {}, "x", -1, 0, 3.5, ["a"], {"a": 1}, "bad\u0000value"])
def test_all_example_paths_are_type_fuzzed_without_raising(replacement) -> None:
    for original in records():
        for path in _leaf_paths(original):
            malformed = _replace_path(original, path, replacement)
            errors = ls.validate_overlay(malformed)
            state = ls.lighting_scale_state(malformed)
            assert isinstance(errors, list), path
            assert isinstance(state, dict), path


@pytest.mark.parametrize("record", [None, True, [], {}, "x", -1, 0, 3.5, ["a"], {"a": 1}, "bad\u0000value"])
def test_non_object_json_records_return_errors_without_raising(record) -> None:
    errors = ls.validate_overlay(record)
    state = ls.lighting_scale_state(record)

    assert isinstance(errors, list)
    assert isinstance(state, dict)


def test_extremely_large_integer_returns_validation_error_without_raising() -> None:
    record = copy.deepcopy(next(item for item in records() if item["record_kind"] == "source"))
    record["lighting"]["colour_temperature_k"]["value"] = 10**400

    errors = ls.validate_overlay(record)
    state = ls.lighting_scale_state(record)

    assert any("numeric values must be finite" in error for error in errors)
    assert state["valid"] is False


@pytest.mark.parametrize(
    ("measurement_value", "pointer", "tolerance", "commit_error", "expected"),
    [
        (1.75, "/height_m", 0, None, None),
        (1.75, "/missing", 0, None, "pointer does not resolve"),
        (True, "/height_m", 0, None, "finite numeric value"),
        ("1.75", "/height_m", 0, None, "finite numeric value"),
        (0, "/height_m", 0, None, "greater than zero"),
        (-1, "/height_m", 0, None, "greater than zero"),
        (float("nan"), "/height_m", 0, None, "finite numeric value"),
        (1.75, "/height_m", 0.100001, None, "tolerance_m"),
        (1.75, "/height_m", 0, "measurement must reference a committed measurement", "committed measurement"),
    ],
)
def test_measurement_reference_is_always_checked(
    tmp_path, monkeypatch, measurement_value, pointer, tolerance,
    commit_error, expected,
) -> None:
    measurement_path = tmp_path / "measurement.json"
    measurement_path.write_text(
        json.dumps({"height_m": measurement_value}), encoding="utf-8"
    )
    measurement = {
        "path": "measurement.json",
        "sha256": hashlib.sha256(measurement_path.read_bytes()).hexdigest(),
        "json_pointer": pointer,
        "tolerance_m": tolerance,
    }
    monkeypatch.setattr(ls, "_committed_measurement_error", lambda *_args: commit_error)
    errors = ls._measurement_errors({"value_m": 1.75}, measurement, tmp_path)
    assert (not errors) is (expected is None), errors
    if expected is not None:
        assert any(expected in error for error in errors)


def test_measurement_reference_rejects_missing_file_and_hash_mismatch(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ls, "_committed_measurement_error", lambda *_args: None)
    measurement = {
        "path": "absent.json", "sha256": "0" * 64,
        "json_pointer": "/height_m",
    }
    assert any(
        "missing" in error
        for error in ls._measurement_errors({"value_m": 1.75}, measurement, tmp_path)
    )
    incomplete = {"path": "still-absent.json", "sha256": "0" * 64}
    incomplete_errors = ls._measurement_errors({"value_m": 1.75}, incomplete, tmp_path)
    assert any("missing" in error for error in incomplete_errors)
    assert any("json_pointer is required" in error for error in incomplete_errors)
    missing = tmp_path / "absent.json"
    missing.write_text('{"height_m":1.75}', encoding="utf-8")
    assert any(
        "sha256" in error
        for error in ls._measurement_errors({"value_m": 1.75}, measurement, tmp_path)
    )


def test_pointer_resolves_array_measurement(tmp_path, monkeypatch) -> None:
    record = next(item for item in records() if item["record_kind"] == "source")
    record = copy.deepcopy(record)
    _copy_overlay_dependencies(record, tmp_path)
    anchor = record["scale"]["anchor"]
    anchor["status"] = "measured"
    anchor["value_m"] = 2.0
    anchor["frame_id"] = None
    measurement_file = tmp_path / "measurement.json"
    measurement_file.write_text('{"measurements":[2.0]}', encoding="utf-8")
    anchor["measurement"] = {
        "path": "measurement.json",
        "sha256": hashlib.sha256(measurement_file.read_bytes()).hexdigest(),
        "json_pointer": "/measurements/0",
    }
    base = {
        "source_id": record["record_id"],
        "scale_calibrated": True,
        "scale": {
            "status": "calibrated",
            "anchor": {"kind": anchor["kind"], "value_m": 2.0, "frame_id": None},
        },
    }
    base_file = tmp_path / "source.json"
    base_file.write_text(json.dumps(base), encoding="utf-8")
    base_reference = {
        "path": "source.json",
        "sha256": hashlib.sha256(base_file.read_bytes()).hexdigest(),
    }
    record["base_record"] = base_reference
    _replace_field_evidence(record, base_reference)
    record["scale"]["status"] = "calibrated"
    monkeypatch.setattr(ls, "_committed_measurement_error", lambda *_args: None)

    assert ls.validate_overlay(record, tmp_path) == []


def test_overlay_returns_errors_for_null_byte_reference_path() -> None:
    record = copy.deepcopy(records()[0])
    record["base_record"]["path"] = "missing\u0000file"

    errors = ls.validate_overlay(record)

    assert errors
    assert any("invalid or unreadable reference path" in error for error in errors)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda record: record["lighting"].update(fixture_layout=None),
        lambda record: record["scale"]["anchor"].update(status=["estimated"]),
        lambda record: record["lighting"]["illuminance_lux"].update(
            review_status=["pending_operator_review"]
        ),
    ],
)
def test_malformed_overlay_values_return_errors_and_invalid_state(mutate) -> None:
    record = copy.deepcopy(records()[0])
    mutate(record)

    errors = ls.validate_overlay(record)
    state = ls.lighting_scale_state(record)

    assert errors
    assert state["valid"] is False


def test_anchor_status_none_rejects_a_present_dimension() -> None:
    record = next(item for item in records() if item["record_kind"] == "source")
    record = copy.deepcopy(record)
    record["scale"]["anchor"]["status"] = "none"

    errors = ls.validate_overlay(record)

    assert any("none requires anchor to be null" in error for error in errors)


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
