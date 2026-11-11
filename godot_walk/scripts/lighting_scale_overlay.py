"""T5 lighting and scale overlays for immutable source and module records."""

from __future__ import annotations

import json
import hashlib
import math
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from deterministic_json import ROOT

SCHEMA_PATH = Path("godot_walk/room_catalog/lighting_scale_overlay.schema.json")


def lighting_scale_state(
    overlay: dict[str, Any] | None, root: Path = ROOT
) -> dict[str, Any]:
    """Return validated overlay state or a conservative uncalibrated default."""
    if overlay is not None:
        errors = validate_overlay(overlay, root)
        if not errors:
            return {"valid": True, "lighting": overlay["lighting"], "scale": overlay["scale"]}
        return {"valid": False, "errors": errors, **_default_state()}
    return {"valid": True, **_default_state()}


def _default_state() -> dict[str, Any]:
    return {
        "lighting": {
            "status": "uncalibrated_not_reviewed",
            "colour_temperature_k": {"value": None, "provenance": "No T5 overlay exists.", "review_status": "not_reviewed"},
            "illuminance_lux": {"value": None, "provenance": "No T5 overlay exists.", "review_status": "not_reviewed"},
            "fixture_layout": [],
            "review_status": "not_reviewed",
        },
        "scale": {"status": "uncalibrated", "anchor": None, "review_status": "not_reviewed"},
    }


def _json_object(path: Path, label: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, [f"{label}: cannot read referenced record: {error}"]
    if not isinstance(value, dict):
        return None, [f"{label}: referenced record must be a JSON object"]
    return value, []


def _pointer_value(value: Any, pointer: str) -> Any:
    current = value
    if pointer == "":
        return current
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise KeyError(pointer)
    for component in pointer[1:].split("/"):
        key = _decode_pointer_component(component, pointer)
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and _is_array_index(key):
            index = int(key)
            if index >= len(current):
                raise KeyError(pointer)
            current = current[index]
        else:
            raise KeyError(pointer)
    return current


def _decode_pointer_component(component: str, pointer: str) -> str:
    decoded: list[str] = []
    index = 0
    while index < len(component):
        if component[index] != "~":
            decoded.append(component[index])
            index += 1
            continue
        if index + 1 >= len(component) or component[index + 1] not in "01":
            raise KeyError(pointer)
        decoded.append("~" if component[index + 1] == "0" else "/")
        index += 2
    return "".join(decoded)


def _is_array_index(component: str) -> bool:
    return component == "0" or (
        bool(component)
        and component[0] in "123456789"
        and all(character in "0123456789" for character in component)
    )


def validate_overlay(record: Any, root: Path = ROOT) -> list[str]:
    """Validate schema, every supplied reference, status claims and calibration."""
    import template_validate as tv

    try:
        schema = tv.load_schema(SCHEMA_PATH, root)
    except tv.TemplateValidationError as error:
        return [str(error)]
    errors = tv.schema_errors(record, schema)
    if errors:
        return errors
    errors += _all_reference_errors(record, root)
    errors += _finite_number_errors(record)
    lighting = record.get("lighting")
    scale = record.get("scale")
    if not isinstance(lighting, dict) or not isinstance(scale, dict):
        return errors
    errors += _review_evidence_errors(record)
    errors += _aggregate_status_errors(record)
    errors += _anchor_rule_errors(record, root)
    reference = record.get("base_record")
    if not _valid_reference(reference):
        return errors
    base_path = _repository_path(root, reference["path"])
    if base_path is None:
        return errors
    base, read_errors = _json_object(base_path, "base_record")
    if read_errors:
        return errors + read_errors
    if isinstance(record.get("record_kind"), str) and isinstance(record.get("record_id"), str):
        errors += _check_identity(record, base)
    if isinstance(record.get("scale"), dict) and record["scale"].get("status") in {"uncalibrated", "calibrated"}:
        errors += _check_base_scale(record, base)
    return errors


def _all_reference_errors(record: Any, root: Path) -> list[str]:
    """Validate every well-formed reference, even when another field is invalid."""
    import template_validate as tv

    errors: list[str] = []
    if not isinstance(record, dict):
        return errors
    for key in ("base_record", "template_ref"):
        reference = record.get(key)
        if isinstance(reference, dict) and "path" in reference and "sha256" in reference:
            errors += _safe_reference_errors(reference, root, key)
    for label, field in _reviewable_fields_safe(record):
        references = field.get("evidence", [])
        if isinstance(references, list):
            for index, reference in enumerate(references):
                if _valid_reference(reference):
                    errors += _safe_reference_errors(reference, root, f"{label}.evidence[{index}]")
        reviews = field.get("review_evidence", [])
        if not isinstance(reviews, list):
            continue
        for index, review in enumerate(reviews):
            if not isinstance(review, dict):
                continue
            review_references = review.get("evidence", [])
            if not isinstance(review_references, list):
                continue
            for evidence_index, reference in enumerate(review_references):
                if _valid_reference(reference):
                    errors += _safe_reference_errors(
                        reference,
                        root,
                        f"{label}.review_evidence[{index}].evidence[{evidence_index}]",
                    )
    anchor = _anchor_safe(record)
    measurement = anchor.get("measurement") if anchor else None
    if isinstance(measurement, dict) and "path" in measurement and "sha256" in measurement:
        errors += _safe_reference_errors(
            {"path": measurement["path"], "sha256": measurement["sha256"]},
            root, "scale.anchor.measurement",
        )
    return errors


def _safe_reference_errors(reference: dict[str, Any], root: Path, label: str) -> list[str]:
    import template_validate as tv

    try:
        return tv._reference_errors(reference, root, label)
    except (OSError, RuntimeError, ValueError) as error:
        return [f"{label}: invalid or unreadable reference path: {error}"]


def _valid_reference(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str)


def _repository_path(root: Path, relative_path: str) -> Path | None:
    try:
        repository = root.resolve()
        candidate = (root / relative_path).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate if candidate.is_relative_to(repository) else None


def _reviewable_fields_safe(record: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    fields: list[tuple[str, dict[str, Any]]] = []
    lighting = record.get("lighting")
    if isinstance(lighting, dict):
        for name in ("colour_temperature_k", "illuminance_lux"):
            value = lighting.get(name)
            if isinstance(value, dict):
                fields.append((f"lighting.{name}", value))
        fixtures = lighting.get("fixture_layout", [])
        if isinstance(fixtures, list):
            fields.extend((f"lighting.fixture_layout[{i}]", value) for i, value in enumerate(fixtures) if isinstance(value, dict))
        fields.append(("lighting", lighting))
    scale = record.get("scale")
    if isinstance(scale, dict):
        anchor = scale.get("anchor")
        if isinstance(anchor, dict):
            fields.append(("scale.anchor", anchor))
        fields.append(("scale", scale))
    return fields


def _anchor_safe(record: dict[str, Any]) -> dict[str, Any] | None:
    scale = record.get("scale")
    anchor = scale.get("anchor") if isinstance(scale, dict) else None
    return anchor if isinstance(anchor, dict) else None


def _finite_number_errors(value: Any, label: str = "overlay") -> list[str]:
    if isinstance(value, dict):
        errors: list[str] = []
        for key, item in value.items():
            field_label = f"{label}.{key}"
            if key in {"value", "value_m", "tolerance_m", "count"}:
                if isinstance(item, bool):
                    errors.append(f"{field_label}: boolean is not a numeric value")
                elif isinstance(item, (int, float)) and not _is_finite_number(item):
                    errors.append(f"{field_label}: numeric values must be finite")
            errors += _finite_number_errors(item, field_label)
        return errors
    if isinstance(value, list):
        return [error for index, item in enumerate(value) for error in _finite_number_errors(item, f"{label}[{index}]")]
    return []


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _check_identity(record: dict[str, Any], base: dict[str, Any]) -> list[str]:
    if record["record_kind"] == "source":
        if base.get("source_id") != record["record_id"]:
            return ["record_id does not match source manifest"]
    elif base.get("module_id") != record["record_id"]:
        return ["record_id does not match module profile"]
    return []


def _review_evidence_errors(record: dict[str, Any]) -> list[str]:
    errors = []
    for name in ("colour_temperature_k", "illuminance_lux"):
        field = record.get("lighting", {}).get(name, {})
        if not isinstance(field, dict):
            continue
        if _is_reviewed_status(field.get("review_status")) and not field.get("evidence"):
            errors.append(f"lighting.{name}: reviewed values require cited evidence")
    fixtures = record.get("lighting", {}).get("fixture_layout", [])
    if not isinstance(fixtures, list):
        fixtures = []
    for index, fixture in enumerate(fixtures):
        if not isinstance(fixture, dict):
            continue
        if _is_reviewed_status(fixture.get("review_status")) and not fixture.get("evidence"):
            errors.append(f"lighting.fixture_layout[{index}]: reviewed values require cited evidence")
    anchor = record.get("scale", {}).get("anchor")
    if isinstance(anchor, dict) and _is_reviewed_status(anchor.get("review_status")) and not anchor.get("evidence"):
        errors.append("scale.anchor: reviewed values require cited evidence")
    for label, field in _reviewable_fields_safe(record):
        if "review_status" not in field:
            continue
        review_status = field["review_status"]
        review_evidence = field.get("review_evidence", [])
        is_reviewed = _is_reviewed_status(review_status)
        if is_reviewed and not review_evidence:
            errors.append(f"{label}: reviewed status requires who/when/what review evidence")
        if not is_reviewed and review_evidence:
            errors.append(f"{label}: pending or not-reviewed status cannot carry review evidence")
        if not isinstance(review_evidence, list):
            continue
        for index, evidence in enumerate(review_evidence):
            if not isinstance(evidence, dict):
                continue
            expected = "operator" if review_status == "operator_reviewed" else "vision_model"
            if is_reviewed and evidence.get("reviewer_kind") != expected:
                errors.append(f"{label}: review evidence reviewer kind conflicts with status")
            try:
                reviewed_text = evidence.get("reviewed_at")
                if not isinstance(reviewed_text, str):
                    raise ValueError("date-time must be a string")
                reviewed_at = datetime.fromisoformat(reviewed_text.replace("Z", "+00:00"))
                if reviewed_at.utcoffset() is None:
                    raise ValueError("timezone required")
            except (AttributeError, TypeError, ValueError):
                errors.append(
                    f"{label}: review evidence date must be a timezone-aware ISO date-time"
                )
    return errors


def _is_reviewed_status(status: Any) -> bool:
    return isinstance(status, str) and status in {
        "operator_reviewed", "vision_model_reviewed"
    }


def _aggregate_status_errors(record: dict[str, Any]) -> list[str]:
    lighting = record.get("lighting", {})
    if not isinstance(lighting, dict):
        return []
    lighting_fields = [
        field for label, field in _reviewable_fields_safe(record)
        if label.startswith("lighting.") and label != "lighting"
    ]
    errors = []
    lighting_statuses = set()
    for field in lighting_fields:
        status = field.get("review_status")
        if isinstance(status, str):
            lighting_statuses.add(status)
        else:
            errors.append("lighting field review_status must be a string")
    if len(lighting_statuses) != 1:
        errors.append("lighting fields have mixed review statuses")
    else:
        field_status = next(iter(lighting_statuses))
        if lighting.get("review_status") != field_status:
            errors.append("lighting aggregate review status conflicts with its fields")
        expected_status = {
            "not_reviewed": "uncalibrated_not_reviewed",
            "pending_operator_review": "estimated_pending_review",
            "pending_vision_model_review": "estimated_pending_review",
            "operator_reviewed": "reviewed",
            "vision_model_reviewed": "reviewed",
        }.get(field_status)
        if expected_status is not None and lighting.get("status") != expected_status:
            errors.append("lighting aggregate status is unsupported by its fields")
    scale = record.get("scale", {})
    if not isinstance(scale, dict):
        return errors
    anchor = scale.get("anchor")
    anchor_status = anchor.get("review_status", "not_reviewed") if isinstance(anchor, dict) else "not_reviewed"
    if scale.get("review_status") != anchor_status:
        errors.append("scale aggregate review status conflicts with its anchor")
    return errors


def _anchor_rule_errors(record: dict[str, Any], root: Path) -> list[str]:
    """Apply the closed calibration rules on every overlay validation path."""
    scale = record.get("scale", {})
    if not isinstance(scale, dict):
        return []
    anchor = scale.get("anchor")
    status = anchor.get("status") if isinstance(anchor, dict) else "none"
    measurement = anchor.get("measurement") if isinstance(anchor, dict) else None
    has_measurement = measurement is not None
    errors: list[str] = []
    if not isinstance(status, str) or status not in {"none", "estimated", "measured"}:
        errors.append("scale.anchor.status must be none, estimated or measured")
    if isinstance(anchor, dict) and status == "none":
        errors.append("scale.anchor.status none requires anchor to be null; an anchor object describes a dimension")
    if (status == "measured") != has_measurement:
        errors.append("measured anchor requires a cited committed measurement; other anchors cannot cite one")
    measurement_valid = False
    if isinstance(measurement, dict):
        measurement_errors = _measurement_errors(anchor, measurement, root)
        errors += measurement_errors
        measurement_valid = not measurement_errors
    calibrated = scale.get("status") == "calibrated"
    if calibrated != (status == "measured" and measurement_valid):
        errors.append("calibrated status requires an anchor marked measured with valid committed measurement")
    if calibrated and record.get("record_kind") == "source" and _valid_reference(record.get("base_record")):
        base_path = _repository_path(root, record["base_record"]["path"])
        if base_path is None:
            errors.append("base_record escapes the repository")
            return errors
        base, read_errors = _json_object(base_path, "base_record")
        if read_errors:
            errors += read_errors
        elif base.get("scale_calibrated") is not True:
            errors.append("source manifest has not accepted scale calibration")
    return errors


def _measurement_errors(anchor: dict[str, Any], measurement: dict[str, Any], root: Path) -> list[str]:
    import template_validate as tv

    if "path" not in measurement or "sha256" not in measurement:
        return ["scale.anchor.measurement reference is incomplete"]
    reference = {"path": measurement["path"], "sha256": measurement["sha256"]}
    errors = _safe_reference_errors(reference, root, "scale.anchor.measurement")
    if "json_pointer" not in measurement:
        errors.append("scale.anchor.measurement reference is incomplete: json_pointer is required")
    tolerance = measurement.get("tolerance_m", 0)
    if not _is_finite_number(tolerance) or tolerance < 0 or tolerance > 0.1:
        errors.append("scale.anchor.measurement tolerance_m must be finite and between 0 and 0.1")
    if errors or "json_pointer" not in measurement:
        return errors
    commit_error = _committed_measurement_error(reference, root)
    if commit_error:
        return [commit_error]
    source, read_errors = _json_object(root / measurement["path"], "scale.anchor.measurement")
    if read_errors:
        return read_errors
    try:
        measured_value = _pointer_value(source, measurement["json_pointer"])
    except (KeyError, AttributeError, TypeError, ValueError):
        return ["scale.anchor.measurement json_pointer does not resolve"]
    if not _is_finite_number(measured_value) or measured_value <= 0:
        return ["scale.anchor.measurement must resolve to a finite numeric value greater than zero"]
    value_m = anchor.get("value_m")
    if not _is_finite_number(value_m):
        return ["scale.anchor.value_m must be a finite numeric value"]
    if abs(measured_value - value_m) > tolerance:
        return ["scale.anchor value does not match cited committed measurement within tolerance"]
    return []


def _check_base_scale(record: dict[str, Any], base: dict[str, Any]) -> list[str]:
    base_scale = base.get("scale")
    if not isinstance(base_scale, dict):
        if record["record_kind"] == "source" and base.get("schema_version") in (1, 2):
            if record["scale"]["status"] == "uncalibrated":
                return []
            return ["legacy source manifest without a scale block cannot be calibrated"]
        return ["base record has no scale block"]
    overlay_scale = record["scale"]
    errors = []
    if overlay_scale["status"] != base_scale.get("status"):
        errors.append("scale status conflicts with base record")
    if base_scale.get("anchor") is not None:
        anchor = overlay_scale.get("anchor")
        base_anchor = base_scale["anchor"]
        if not isinstance(base_anchor, dict):
            return ["base record scale anchor must be an object or null"]
        if not isinstance(anchor, dict) or any(
            anchor.get(field) != base_anchor.get(field)
            for field in ("kind", "value_m", "frame_id")
            if field in base_anchor
        ):
            errors.append("scale anchor conflicts with base record")
    elif isinstance(overlay_scale.get("anchor"), dict) and overlay_scale["anchor"].get("status") == "measured":
        errors.append("measured scale anchor conflicts with null base anchor")
    return errors


def _committed_measurement_error(
    reference: dict[str, Any], root: Path
) -> str | None:
    """Require the cited bytes to exist in the current Git commit."""
    try:
        committed = subprocess.run(
            ["git", "show", f"HEAD:{reference['path']}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
    except OSError as error:
        return f"scale.anchor.measurement: cannot verify committed measurement: {error}"
    if committed.returncode != 0:
        return "scale.anchor.measurement must reference a committed measurement"
    digest = hashlib.sha256(committed.stdout).hexdigest()
    if digest != reference["sha256"]:
        return "scale.anchor.measurement differs from the committed measurement"
    return None


def overlay_paths(root: Path = ROOT) -> list[Path]:
    paths = set((root / "godot_walk/source_library/sources").glob("*/source_lighting_scale_v1.json"))
    paths.update(root.glob(
        "godot_walk/source_library/sources/*/rooms/*/module_profile_lighting_scale_v1.json"
    ))
    paths.update((root / "godot_walk/room_catalog/module_profiles").glob("*-lighting-scale-v1.json"))
    return sorted(paths)
