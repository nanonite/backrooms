"""T5 lighting and scale overlays for immutable source and module records."""

from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path
from typing import Any

from deterministic_json import ROOT

SCHEMA_PATH = Path("godot_walk/room_catalog/lighting_scale_overlay.schema.json")
def lighting_scale_state(overlay: dict[str, Any] | None) -> dict[str, Any]:
    """Return overlay fields or the explicit uncalibrated/unreviewed default."""
    if overlay is not None:
        return {"lighting": overlay["lighting"], "scale": overlay["scale"]}
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
    for component in pointer.lstrip("/").split("/"):
        key = component.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or key not in current:
            raise KeyError(pointer)
        current = current[key]
    return current


def validate_overlay(record: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Validate schema, references, base agreement and calibration evidence."""
    import template_validate as tv

    try:
        schema = tv.load_schema(SCHEMA_PATH, root)
    except tv.TemplateValidationError as error:
        return [str(error)]
    errors = tv.schema_errors(record, schema)
    if errors:
        return errors
    reference = record["base_record"]
    errors += tv._reference_errors(reference, root, "base_record")
    errors += tv._reference_errors(record["template_ref"], root, "template_ref")
    errors += _field_evidence_errors(record, root)
    errors += _review_evidence_errors(record)
    if errors:
        return errors
    base, read_errors = _json_object(root / reference["path"], "base_record")
    if read_errors:
        return read_errors
    errors += _check_identity(record, base)
    errors += _check_base_scale(record, base)
    errors += _check_calibration(record, root)
    return errors


def _check_identity(record: dict[str, Any], base: dict[str, Any]) -> list[str]:
    if record["record_kind"] == "source":
        if base.get("source_id") != record["record_id"]:
            return ["record_id does not match source manifest"]
    elif base.get("module_id") != record["record_id"]:
        return ["record_id does not match module profile"]
    return []


def _field_evidence_errors(record: dict[str, Any], root: Path) -> list[str]:
    import template_validate as tv

    errors = []
    for name in ("colour_temperature_k", "illuminance_lux"):
        for index, evidence in enumerate(record["lighting"][name]["evidence"]):
            errors += tv._reference_errors(evidence, root, f"lighting.{name}.evidence[{index}]")
    for index, fixture in enumerate(record["lighting"]["fixture_layout"]):
        for evidence_index, evidence in enumerate(fixture["evidence"]):
            errors += tv._reference_errors(evidence, root, f"lighting.fixture_layout[{index}].evidence[{evidence_index}]")
    anchor = record["scale"].get("anchor")
    if isinstance(anchor, dict):
        for index, evidence in enumerate(anchor["evidence"]):
            errors += tv._reference_errors(evidence, root, f"scale.anchor.evidence[{index}]")
    return errors


def _review_evidence_errors(record: dict[str, Any]) -> list[str]:
    reviewed = {"operator_reviewed", "vision_model_reviewed"}
    errors = []
    for name in ("colour_temperature_k", "illuminance_lux"):
        field = record["lighting"][name]
        if field["review_status"] in reviewed and not field["evidence"]:
            errors.append(f"lighting.{name}: reviewed values require cited evidence")
    for index, fixture in enumerate(record["lighting"]["fixture_layout"]):
        if fixture["review_status"] in reviewed and not fixture["evidence"]:
            errors.append(f"lighting.fixture_layout[{index}]: reviewed values require cited evidence")
    anchor = record["scale"].get("anchor")
    if isinstance(anchor, dict) and anchor["review_status"] in reviewed and not anchor["evidence"]:
        errors.append("scale.anchor: reviewed values require cited evidence")
    return errors


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
        if not isinstance(anchor, dict) or any(
            anchor.get(field) != base_anchor.get(field)
            for field in ("kind", "value_m", "frame_id")
            if field in base_anchor
        ):
            errors.append("scale anchor conflicts with base record")
    elif isinstance(overlay_scale.get("anchor"), dict) and overlay_scale["anchor"].get("status") == "measured":
        errors.append("measured scale anchor conflicts with null base anchor")
    return errors


def _check_calibration(record: dict[str, Any], root: Path) -> list[str]:
    scale = record["scale"]
    anchor = scale.get("anchor")
    if scale["status"] != "calibrated":
        return []
    if not isinstance(anchor, dict) or anchor.get("status") != "measured":
        return ["calibrated scale requires an anchor marked measured"]
    measurement = anchor.get("measurement")
    if not isinstance(measurement, dict):
        return ["calibrated scale requires a cited committed measurement"]
    import template_validate as tv

    errors = tv._reference_errors(measurement, root, "scale.anchor.measurement")
    if errors:
        return errors
    commit_error = _committed_measurement_error(measurement, root)
    if commit_error:
        return [commit_error]
    source, read_errors = _json_object(root / measurement["path"], "scale.anchor.measurement")
    if read_errors:
        return read_errors
    try:
        measured_value = _pointer_value(source, measurement["json_pointer"])
    except KeyError:
        return ["scale.anchor.measurement json_pointer does not resolve"]
    if measured_value != anchor["value_m"]:
        return ["scale.anchor value does not match cited committed measurement"]
    if record["record_kind"] == "source":
        base, read_errors = _json_object(root / record["base_record"]["path"], "base_record")
        if read_errors:
            return read_errors
        if base.get("scale_calibrated") is not True:
            return ["source manifest has not accepted scale calibration"]
    return []


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
