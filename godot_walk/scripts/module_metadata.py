"""Build and validate consolidated module metadata snapshots (issue 229)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from deterministic_json import ROOT, canonical_bytes, sha256_file

sys.path.insert(0, str(Path(__file__).resolve().parent))
import operator_approval_receipts as receipts

CATALOG = Path("godot_walk/room_catalog")
OUTPUT = CATALOG / "module_metadata"
SCHEMA = CATALOG / "module_metadata.schema.json"
ACOUSTICS = CATALOG / "module_acoustics_v0.2.0.json"
ACOUSTIC_FIELDS = (
    "mean_distance_m", "max_distance_m", "ceiling_height_m", "openness",
    "room_size", "damping", "wet", "predelay_msec",
)
MEASURED_FIELDS = frozenset(ACOUSTIC_FIELDS[:4])
CEILING_LIMITATION = "The up-ray ceiling estimate is capped by the profile ceiling hint; it is not an uncapped ceiling measurement."


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _reference(path: Path, root: Path) -> dict[str, str]:
    return {"path": _relative(path, root), "sha256": sha256_file(path)}


def _is_authored(item: dict[str, Any], root: Path) -> bool:
    if "origin" in item:
        return item["origin"] == "authored_kit"
    return item["profile"].resolve().is_relative_to((root / CATALOG / "module_profiles").resolve())


def _output_path(item: dict[str, Any], root: Path) -> Path:
    if _is_authored(item, root):
        return root / OUTPUT / f"{item['module_id']}-v1.json"
    try:
        relative_profile = item["profile"].resolve().relative_to(root.resolve())
    except ValueError:
        relative_profile = item["profile"].resolve().relative_to(ROOT.resolve())
    return (root / relative_profile).parent / "module_metadata.json"


def record_paths(root: Path = ROOT) -> list[Path]:
    authored = (root / OUTPUT).glob("*-v1.json")
    sources = root.glob("godot_walk/source_library/sources/*/rooms/*/module_metadata.json")
    return sorted([*authored, *sources])


def _record_coverage_errors(paths: list[Path], expected: dict[str, Path], root: Path) -> list[str]:
    errors: list[str] = []
    seen: dict[str, Path] = {}
    for path in paths:
        try:
            record = _load(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append(f"{path}: cannot read module id: {error}")
            continue
        module_id = record.get("module_id") if isinstance(record, dict) else None
        if not isinstance(module_id, str):
            errors.append(f"{path}: module_id must be a string")
            continue
        if module_id in seen:
            errors.append(f"{path}: duplicate module record for {module_id}; also at {seen[module_id]}")
        seen[module_id] = path
        expected_path = expected.get(module_id)
        if expected_path is None:
            errors.append(f"{path}: module_id {module_id} is not admitted")
        elif path.resolve() != expected_path.resolve():
            errors.append(f"{path}: record for {module_id} must be at {expected_path.relative_to(root)}")
    for module_id, expected_path in expected.items():
        if module_id not in seen:
            errors.append(f"{expected_path.relative_to(root)}: missing record for admitted module {module_id}")
    return errors


def _module_inputs(root: Path) -> list[dict[str, Any]]:
    profiles = list((root / CATALOG / "module_profiles").glob("*.json"))
    profiles = [p for p in profiles if "-t6-" not in p.name and "-lighting-scale-" not in p.name]
    profiles.extend(root.glob("godot_walk/source_library/sources/*/rooms/*/module_profile_v1.json"))
    descriptors = list((root / CATALOG / "module_surface_palettes").glob("*.json"))
    descriptors.extend(root.glob("godot_walk/source_library/sources/*/rooms/*/module_surface_palette_v1.json"))
    t6_files = list((root / CATALOG / "module_profiles").glob("*-t6-v1.json"))
    t6_files.extend(root.glob("godot_walk/source_library/sources/*/rooms/*/module_profile_t6_v1.json"))
    by_id = lambda paths: {_load(path)["module_id"]: path for path in paths}
    descriptor_by_id, t6_by_id = by_id(descriptors), by_id(t6_files)
    acoustic_index = _load(root / ACOUSTICS)["modules"]
    result = []
    for profile_path in sorted(profiles):
        profile = _load(profile_path)
        module_id = profile["module_id"]
        acoustic_key = f"{module_id}@1"
        if acoustic_key not in acoustic_index:
            continue
        descriptor_path = descriptor_by_id.get(module_id)
        if descriptor_path is None or module_id not in t6_by_id:
            continue
        base = profile_path.parent
        poetics = acoustic_index[acoustic_key]["poetics"]["path"]
        overlay = base / f"{module_id}-v1-lighting-scale-v1.json"
        if not overlay.exists():
            source_root = base.parents[1] if base.name != "module_profiles" else base
            overlay = source_root / "source_lighting_scale_v1.json"
        if not overlay.exists():
            overlay = None
        result.append({"module_id": module_id, "profile": profile_path, "descriptor": descriptor_path,
                       "t6": t6_by_id[module_id], "poetics": root / poetics, "overlay": overlay,
                       "acoustic_key": acoustic_key,
                       "origin": "authored_kit" if profile_path.parent == root / CATALOG / "module_profiles" else "source_room"})
    return result


def _mapping_table_ref(root: Path) -> dict[str, str]:
    return _reference(root / receipts.MAPPING_TABLE_PATH, root)


def _pointer(document: Any, pointer: str) -> Any:
    value = document
    for part in pointer.strip("/").split("/"):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _approval(path: str, field: str, root: Path) -> dict[str, Any] | None:
    return receipts.operator_approval_for_field(path, field, root)


def _mapping_material_approval(path: str, root: Path) -> dict[str, Any] | None:
    receipt_path = root / receipts.RECEIPT_DIR / "issue-217.json"
    table_path = root / receipts.MAPPING_TABLE_PATH
    try:
        receipt = _load(receipt_path)
        table = next((scope for scope in receipt["scope"]
                      if scope["path"] == receipts.MAPPING_TABLE_PATH), None)
        if (receipt.get("issue_id") != 217 or table is None
                or "/table/Material ID" not in table["fields"]
                or sha256_file(table_path) != table["sha256"]):
            return None
        derived = table.get("derived_from", {})
        if any(item.get("path") == path for item in derived.get("files", [])):
            return receipt
    except (OSError, KeyError, TypeError, ValueError):
        return None
    return None


def _lock(locks: dict[str, Any], record_field: str, source_path: str,
          source_field: str, source: Any, root: Path,
          record_value_path: str | None = None) -> None:
    approval = (_mapping_material_approval(source_path, root)
                if source_field.endswith("/material_id")
                else _approval(source_path, source_field, root))
    if approval is None:
        return
    receipt_path = root / receipts.RECEIPT_DIR / f"issue-{approval['issue_id']}.json"
    locks[record_field] = {"receipt": _reference(receipt_path, root), "source_path": source_path,
                           "source_field": source_field,
                           "record_value_path": record_value_path or record_field,
                           "value": _pointer(source, source_field)}


def _build(item: dict[str, Any], root: Path) -> dict[str, Any]:
    paths = {key: item[key] for key in ("profile", "descriptor", "t6", "poetics")}
    paths["acoustics"] = root / ACOUSTICS
    if item["overlay"] is not None:
        paths["lighting_scale"] = item["overlay"]
    source_layers = {key: _reference(path, root) for key, path in paths.items()}
    profile, surfaces, t6 = (_load(item[key]) for key in ("profile", "descriptor", "t6"))
    acoustic_record = _load(root / ACOUSTICS)["modules"][item["acoustic_key"]]
    probe = acoustic_record["probe"]
    poetics_ref = _reference(item["poetics"], root)
    approval_refs: dict[str, Any] = {}
    locks: dict[str, Any] = {}
    for surface, fields in surfaces["surfaces"].items():
        for field in ("material_id", "acoustic"):
            source_field = f"/surfaces/{surface}/{field}"
            lock_name = f"surfaces.surfaces.{surface}.{field}"
            _lock(locks, lock_name, source_layers["descriptor"]["path"], source_field, surfaces, root)
    for section, names in (("roles", tuple(t6["roles"])), ("mood", tuple(t6["mood"]))):
        for name in names:
            source_field = f"/{section}/{name}"
            lock_name = f"t6.{section}.{name}"
            _lock(locks, lock_name, source_layers["t6"]["path"], source_field, t6, root)
    for name in ("acoustic", "absorption", "probe"):
        values = acoustic_record[name]
        if name == "probe":
            for field in ACOUSTIC_FIELDS:
                source_field = f"/modules/{item['acoustic_key']}/probe/{field}"
                lock = _approval_lock(
                    locks, source_layers["acoustics"]["path"], source_field,
                    _load(root / ACOUSTICS), root,
                    f"acoustics.fields.{field}.value")
                if lock is not None:
                    locks[f"acoustics.fields.{field}"] = lock
        else:
            source_field = f"/modules/{item['acoustic_key']}/{name}"
            record_path = f"acoustics.committed_block.{name}"
            _lock(locks, f"acoustics.{name}", source_layers["acoustics"]["path"],
                  source_field, _load(root / ACOUSTICS), root, record_path)
    if item["overlay"] is not None:
        overlay = _load(item["overlay"])
        overlay_path = source_layers["lighting_scale"]["path"]
        source_level_overlay = item["overlay"].name == "source_lighting_scale_v1.json"
        if source_level_overlay:
            approval = next(((field, candidate) for field in ("/scale/anchor/value_m", "/lighting/illuminance_lux/value")
                             if (candidate := _approval(overlay_path, field, root)) is not None), None)
            if approval is not None:
                source_field, receipt = approval
                receipt_path = root / receipts.RECEIPT_DIR / f"issue-{receipt['issue_id']}.json"
                locks["lighting_scale.source_overlay"] = {
                    "receipt": _reference(receipt_path, root),
                    "source_path": overlay_path,
                    "source_field": source_field,
                    "record_value_path": "lighting_scale.overlay_ref.sha256",
                    "value": source_layers["lighting_scale"]["sha256"],
                    "source_value": _pointer(overlay, source_field),
                }
        else:
            for section in ("lighting", "scale"):
                for name in overlay.get(section, {}):
                    source_field = f"/{section}/{name}"
                    approval = _approval(overlay_path, source_field, root)
                    if approval is not None:
                        receipt_path = root / receipts.RECEIPT_DIR / f"issue-{approval['issue_id']}.json"
                        approval_refs[f"lighting_scale.{section}.{name}"] = _reference(receipt_path, root)
                        lock_name = f"lighting_scale.{section}.{name}"
                        record_path = f"lighting_scale.overlay.{section}.{name}"
                        _lock(locks, lock_name, overlay_path,
                              source_field, overlay, root, record_path)
        lighting_scale = ({"state": "source_overlay", "overlay_ref": source_layers["lighting_scale"]}
                          if source_level_overlay else {"state": "overlay", "overlay": overlay})
    else:
        lighting_scale = {"state": "not_reviewed_uncalibrated", "overlay": None,
                          "registration_accepted": False, "scale_calibrated": False}
    for name, lock in locks.items():
        approval_refs[name] = lock["receipt"]
    inputs = {**source_layers, "approval_refs": approval_refs}
    if any(lock["receipt"]["path"].endswith("issue-217.json") for lock in locks.values()):
        inputs["mapping_table"] = _mapping_table_ref(root)
    fields = {}
    for name in ACOUSTIC_FIELDS:
        state = "measured" if name in MEASURED_FIELDS else "derived"
        provenance = {"kind": state, "source": f"{source_layers['acoustics']['path']}#/modules/{item['acoustic_key']}/probe/{name}"}
        if name == "ceiling_height_m":
            provenance["limitation"] = CEILING_LIMITATION
        if state == "derived":
            provenance["basis"] = (["mean_distance_m"] if name == "predelay_msec" else
                                    ["mean_distance_m", "ceiling_height_m"] if name == "room_size" else
                                    ["mean_distance_m", "ceiling_height_m", "openness"])
            provenance["method"] = {
                "room_size": "clamp(0.10 + 0.78 * clamp(mean_distance_m / 10.0, 0, 1) + 0.12 * clamp((ceiling_height_m - 2.2) / (6.0 - 2.2), 0, 1), 0, 1)",
                "damping": "clamp(0.22 + 0.48 * wall_size + 0.18 * height_size + 0.12 * openness, 0, 1)",
                "wet": "clamp((0.18 + 0.48 * wall_size + 0.14 * height_size) * (1.0 - 0.35 * openness), 0, 0.75)",
                "predelay_msec": "clamp(mean_distance_m / 343.0 * 1000.0, 1.0, 50.0)",
            }[name]
            if name in {"damping", "wet"}:
                provenance["intermediate_definitions"] = {
                    "wall_size": "clamp(mean_distance_m / 10.0, 0, 1)",
                    "height_size": "clamp((ceiling_height_m - 2.2) / (6.0 - 2.2), 0, 1)",
                }
            provenance["mapping_source"] = "godot_walk/scripts/room_acoustic_probe.gd#map_metrics"
        fields[name] = {"value": probe[name], "provenance": provenance,
                        "committed_block_label": probe["provenance"]}
    return {"metadata_version": "module-metadata-1.0.0", "module_id": item["module_id"],
            "origin": item["origin"] if "origin" in item else "authored_kit" if _is_authored(item, root) else "source_room",
            "space_kind": "enclosed", "registration_accepted": False, "scale_calibrated": False,
            "poetics_ref": poetics_ref, "source_layers": source_layers,
            "inputs": inputs, "approval_refs": approval_refs, "locks": locks,
            "profile": profile, "surfaces": surfaces, "lighting_scale": lighting_scale,
            "t6": t6, "acoustics": {"committed_block": acoustic_record, "fields": fields}}


def _approval_lock(locks: dict[str, Any], path: str, field: str,
                   source: Any, root: Path,
                   record_value_path: str) -> dict[str, Any] | None:
    approval = _approval(path, field, root)
    if approval is None:
        return None
    receipt = root / receipts.RECEIPT_DIR / f"issue-{approval['issue_id']}.json"
    return {"receipt": _reference(receipt, root), "source_path": path,
            "source_field": field, "record_value_path": record_value_path,
            "value": _pointer(source, field)}


def _record_path_for_lock(name: str, lock: dict[str, Any]) -> str:
    if lock.get("record_value_path"):
        return lock["record_value_path"]
    if name.startswith("acoustics.fields."):
        return f"{name}.value"
    if name in {"acoustics.acoustic", "acoustics.absorption"}:
        return f"acoustics.committed_block.{name.removeprefix('acoustics.')}"
    if name.startswith("lighting_scale."):
        return f"lighting_scale.overlay.{name.removeprefix('lighting_scale.')}"
    return name


def _dotted_value(document: Any, path: str) -> Any:
    missing = object()
    value = document
    for segment in path.split("."):
        if not isinstance(value, dict) or segment not in value:
            return missing
        value = value[segment]
    return value


def _locked_value_errors(existing: dict[str, Any], current: dict[str, Any], target: Path) -> list[str]:
    errors = []
    for name, saved_lock in existing.get("locks", {}).items():
        current_lock = current.get("locks", {}).get(name)
        if current_lock is None:
            errors.append(f"{target}: locked input changed or lost approval for {name}")
            continue
        saved_path = _record_path_for_lock(name, saved_lock)
        if _dotted_value(existing, saved_path) != saved_lock.get("value"):
            errors.append(f"{target}: saved locked record value was edited for {name}")
        if current_lock.get("record_value_path", saved_path) != saved_path:
            errors.append(f"{target}: locked record field changed for {name}")
        for field in ("receipt", "source_path", "source_field", "value"):
            if saved_lock.get(field) != current_lock.get(field):
                errors.append(f"{target}: locked input changed underneath {name}")
                break
    return errors


def generate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    candidates = []
    try:
        module_inputs = _module_inputs(root)
    except Exception as error:
        return [f"cannot determine admitted module set: {error}"]
    if len(module_inputs) != 11:
        return [f"module_metadata generation requires 11 admitted modules, found {len(module_inputs)}"]
    module_ids = [item["module_id"] for item in module_inputs]
    if len(set(module_ids)) != len(module_ids):
        return ["module_metadata generation found duplicate admitted module IDs"]
    for item in module_inputs:
        record = _build(item, root)
        target = _output_path(item, root)
        if target.exists():
            try:
                existing = _load(target)
                errors.extend(_locked_value_errors(existing, record, target))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                errors.append(f"{target}: cannot read existing record: {error}")
        candidates.append((target, canonical_bytes(record)))
    if errors:
        return errors
    for target, data in candidates:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        (target.with_suffix(target.suffix + ".sha256")).write_text(
            __import__("hashlib").sha256(data).hexdigest() + "\n", encoding="ascii")
    return []


def validate_record(record: dict[str, Any], root: Path = ROOT, path: Path | None = None) -> list[str]:
    try:
        return _validate_record(record, root, path)
    except Exception as error:
        return [f"cannot validate module metadata record: {error}"]


def _validate_record(record: Any, root: Path, path: Path | None) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["module metadata record must be an object"]
    source_layers = record.get("source_layers")
    inputs = record.get("inputs")
    approvals = record.get("approval_refs")
    if not isinstance(source_layers, dict):
        errors.append("source_layers must be an object")
        source_layers = {}
    if not isinstance(inputs, dict):
        errors.append("inputs must be an object containing every source reference")
        inputs = {}
    if not isinstance(approvals, dict):
        errors.append("approval_refs must be an object")
        approvals = {}
    for name, reference in source_layers.items():
        if inputs.get(name) != reference:
            errors.append(f"inputs omits or differs from source_layers.{name}")
    if inputs.get("poetics") != record.get("poetics_ref"):
        errors.append("inputs omits or differs from poetics_ref")
    if inputs.get("approval_refs") != approvals:
        errors.append("inputs omits or differs from approval_refs")
    references = [value for key, value in inputs.items() if key != "approval_refs"]
    references.extend(inputs.get("approval_refs", {}).values()
                      if isinstance(inputs.get("approval_refs"), dict) else [])
    for reference in references:
        if not isinstance(reference, dict):
            errors.append("input reference must be an object")
            continue
        try:
            input_path = root / reference.get("path", "")
            if sha256_file(input_path) != reference.get("sha256"):
                errors.append(f"stale input hash: {reference.get('path')}")
        except (OSError, ValueError, TypeError):
            errors.append(f"missing or unreadable input: {reference.get('path')}")
    errors.extend(_section_source_errors(record, root))
    if path is not None:
        pin = path.with_suffix(path.suffix + ".sha256")
        try:
            expected = pin.read_text(encoding="ascii").strip()
            if expected != sha256_file(path):
                errors.append("detached sha256 pin does not match record")
        except (OSError, UnicodeDecodeError, ValueError, TypeError):
            errors.append("detached sha256 pin is missing or unreadable")
    return errors


def _palette_errors(record: dict[str, Any], root: Path) -> list[str]:
    try:
        registry = _load(root / CATALOG / "material_palettes/palettes-0.3.0.json")
        known = {palette["palette_id"] for palette in registry["palettes"]}
    except (OSError, KeyError, TypeError, ValueError) as error:
        return [f"cannot load palette registry: {error}"]
    errors = []
    surfaces = record.get("surfaces", {}).get("surfaces", {})
    if not isinstance(surfaces, dict):
        return ["surfaces.surfaces must be an object"]
    for surface, entry in surfaces.items():
        if not isinstance(entry, dict):
            continue
        palette_id = entry.get("palette_id")
        if palette_id is not None and (not isinstance(palette_id, str) or palette_id not in known):
            errors.append(f"surfaces.surfaces.{surface}.palette_id is not in palettes-0.3.0.json: {palette_id}")
    return errors


def _section_source_errors(record: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    layers = record.get("source_layers", {})
    try:
        documents = {name: _load(root / reference["path"])
                     for name, reference in layers.items()}
        acoustic_root = documents["acoustics"]
        module_key = f"{record['module_id']}@1"
        acoustic = acoustic_root["modules"][module_key]
        expected_sections = {
            "profile": documents["profile"],
            "surfaces": documents["descriptor"],
            "t6": documents["t6"],
        }
        for section, expected in expected_sections.items():
            if record.get(section) != expected:
                errors.append(f"{section} differs from its source layer")
        for section in ("profile", "surfaces", "t6"):
            if expected_sections[section].get("module_id") != record.get("module_id"):
                errors.append(f"{section} module_id differs from the metadata record")
        errors.extend(_source_layer_schema_errors(documents, root))
        if record.get("poetics_ref") != acoustic.get("poetics"):
            errors.append("poetics_ref differs from the acoustics layer reference")
        if record.get("acoustics", {}).get("committed_block") != acoustic:
            errors.append("acoustics.committed_block differs from the committed acoustics layer")
        errors.extend(_acoustic_field_errors(record, acoustic))
        errors.extend(_lighting_source_errors(record, layers, documents, root))
        errors.extend(_locked_source_errors(record, root))
        errors.extend(_expected_lock_errors(record, root))
        if any(lock.get("receipt", {}).get("path", "").endswith("issue-217.json")
               for lock in record.get("locks", {}).values()):
            if record.get("inputs", {}).get("mapping_table") != _mapping_table_ref(root):
                errors.append("inputs omits or has a stale issue-217 material mapping table reference")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        errors.append(f"cannot compare metadata sections with source layers: {error}")
    return errors


def _acoustic_field_errors(record: dict[str, Any], acoustic: dict[str, Any]) -> list[str]:
    errors = []
    probe = acoustic.get("probe", {})
    fields = record.get("acoustics", {}).get("fields", {})
    if not isinstance(fields, dict) or set(fields) != set(ACOUSTIC_FIELDS):
        return ["acoustics.fields must contain every measured and derived probe field"]
    for name in ACOUSTIC_FIELDS:
        field = fields.get(name)
        expected_kind = "measured" if name in MEASURED_FIELDS else "derived"
        if not isinstance(field, dict) or field.get("value") != probe.get(name):
            errors.append(f"acoustics.fields.{name}.value differs from the committed probe value")
            continue
        provenance = field.get("provenance")
        if not isinstance(provenance, dict) or provenance.get("kind") != expected_kind:
            errors.append(f"acoustics.fields.{name}.provenance.kind must be {expected_kind}")
        expected_source = (
            f"{record.get('source_layers', {}).get('acoustics', {}).get('path')}"
            f"#/modules/{record.get('module_id')}@1/probe/{name}"
        )
        if not isinstance(provenance, dict) or provenance.get("source") != expected_source:
            errors.append(f"acoustics.fields.{name}.provenance.source is incorrect")
        if expected_kind == "derived":
            expected_basis = {
                "room_size": ["mean_distance_m", "ceiling_height_m"],
                "predelay_msec": ["mean_distance_m"],
            }.get(name, ["mean_distance_m", "ceiling_height_m", "openness"])
            if (not provenance.get("method") or not provenance.get("mapping_source")
                    or provenance.get("basis") != expected_basis):
                errors.append(f"acoustics.fields.{name} is missing its basis or derivation method")
        if name == "ceiling_height_m" and "capped" not in provenance.get("limitation", ""):
            errors.append("acoustics.fields.ceiling_height_m is missing the capped up-ray limitation")
        if field.get("committed_block_label") != probe.get("provenance"):
            errors.append(f"acoustics.fields.{name} lost the literal committed block label")
    return errors


def _source_layer_schema_errors(documents: dict[str, Any], root: Path) -> list[str]:
    from jsonschema import Draft202012Validator

    errors = []
    schema_paths = {
        "profile": CATALOG / "module_profile.schema.json",
        "t6": CATALOG / "module_profile_t6.schema.json",
    }
    if "lighting_scale" in documents:
        schema_paths["lighting_scale"] = CATALOG / "lighting_scale_overlay.schema.json"
    for section, schema_path in schema_paths.items():
        try:
            schema = _load(root / schema_path)
            validator = Draft202012Validator(schema)
            for error in validator.iter_errors(documents[section]):
                pointer = "/".join(str(part) for part in error.absolute_path) or "<root>"
                errors.append(f"source {section} schema {pointer}: {error.message}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            errors.append(f"cannot validate source {section} schema: {error}")
    return errors


def _lighting_source_errors(record: dict[str, Any], layers: dict[str, Any],
                            documents: dict[str, Any], root: Path) -> list[str]:
    section = record.get("lighting_scale")
    if not isinstance(section, dict):
        return ["lighting_scale must be an object"]
    reference = layers.get("lighting_scale")
    if reference is None:
        expected = {"state": "not_reviewed_uncalibrated", "overlay": None,
                    "registration_accepted": False, "scale_calibrated": False}
        return [] if section == expected else ["lighting_scale default differs from the unreviewed default"]
    path = reference["path"]
    if Path(path).name == "source_lighting_scale_v1.json":
        expected = {"state": "source_overlay", "overlay_ref": reference}
        return [] if section == expected else ["source-level lighting/scale overlay must remain a hash reference"]
    if section != {"state": "overlay", "overlay": documents["lighting_scale"]}:
        return ["lighting_scale overlay differs from its source overlay"]
    return []


def _locked_source_errors(record: dict[str, Any], root: Path) -> list[str]:
    errors = []
    inputs = record.get("inputs", {})
    approved_receipts = inputs.get("approval_refs", {}) if isinstance(inputs, dict) else {}
    for name, lock in record.get("locks", {}).items():
        if not isinstance(lock, dict):
            errors.append(f"locks.{name} must be an object")
            continue
        receipt = lock.get("receipt")
        if not isinstance(receipt, dict) or receipt not in approved_receipts.values():
            errors.append(f"locks.{name} receipt is not listed in approval_refs input hashes")
        try:
            source_path = lock["source_path"]
            source = _load(root / source_path)
            source_value = _pointer(source, lock["source_field"])
            expected_source = lock.get("source_value", lock.get("value"))
            if source_value != expected_source:
                errors.append(f"locks.{name} approved source value differs from its input")
            actual_value = _dotted_value(record, lock["record_value_path"])
            if actual_value != lock.get("value"):
                errors.append(f"locks.{name} record value differs from its approved value")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            errors.append(f"locks.{name} cannot be checked against its source: {error}")
    return errors


def _expected_lock_errors(record: dict[str, Any], root: Path) -> list[str]:
    module = next((item for item in _module_inputs(root)
                   if item["module_id"] == record.get("module_id")), None)
    if module is None:
        return [f"no admitted source layers for module {record.get('module_id')}"]
    try:
        expected_locks = _build(module, root)["locks"]
    except Exception as error:
        return [f"cannot derive approved locks for {record.get('module_id')}: {error}"]
    actual_locks = record.get("locks")
    if not isinstance(actual_locks, dict):
        return ["locks must be an object"]
    errors = []
    for name, expected in expected_locks.items():
        if actual_locks.get(name) != expected:
            errors.append(f"locks.{name} is missing or differs from its current approval")
    for name in actual_locks.keys() - expected_locks.keys():
        errors.append(f"locks.{name} has no current operator approval")
    return errors


def validate_repository(root: Path = ROOT) -> list[str]:
    try:
        schema = _load(root / SCHEMA)
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)
    except Exception as error:
        return [f"module_metadata schema cannot be loaded: {error}"]
    errors: list[str] = []
    try:
        paths = record_paths(root)
    except OSError as error:
        return [f"{OUTPUT}: cannot list records: {error}"]
    try:
        module_inputs = _module_inputs(root)
    except Exception as error:
        return [f"cannot determine admitted module set: {error}"]
    expected: dict[str, Path] = {}
    for item in module_inputs:
        if item["module_id"] in expected:
            errors.append(f"duplicate admitted module ID: {item['module_id']}")
            continue
        expected[item["module_id"]] = _output_path(item, root)
    if len(module_inputs) != 11 or len(expected) != 11:
        errors.append(f"expected 11 distinct admitted modules, found {len(expected)}")
    if len(paths) != 11:
        errors.append(f"{OUTPUT}: expected 11 records, found {len(paths)}")
    errors.extend(_record_coverage_errors(paths, expected, root))
    for path in paths:
        try:
            record = _load(path)
            errors.extend(f"{path.relative_to(root)}: {error}" for error in
                          Draft202012Validator(schema).iter_errors(record))
            errors.extend(f"{path.relative_to(root)}: {error}" for error in validate_record(record, root, path))
            errors.extend(f"{path.relative_to(root)}: {error}" for error in _palette_errors(record, root))
        except Exception as error:
            errors.append(f"{path}: cannot read module metadata: {error}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    errors = validate_repository(args.root.resolve()) if args.check else generate(args.root.resolve())
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
