"""Verify the template artifacts required for one admitted library module.

Checks named by the #195/#222 contract: a source manifest v3 (checked by the
batch layer), one module profile, one acoustics record and one surface/palette
descriptor. The consolidated ``module_metadata`` record is checked as well
because it is the single module record introduced by #229.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import template_validate as tv
from backfill_module_profiles import profile_path
from deterministic_json import ROOT, repo_relative, sha256_file
from jsonschema import Draft202012Validator
from module_metadata import SCHEMA as MODULE_METADATA_SCHEMA
from module_metadata import validate_record as validate_module_metadata
from module_surface_palette import descriptor_path, validate_descriptor

MODULE_ACOUSTICS = Path("godot_walk/room_catalog/module_acoustics_v0.2.0.json")
MODULE_METADATA_DIR = Path("godot_walk/room_catalog/module_metadata")
PROBE_FIELDS = (
    "probe_version",
    "mean_distance_m",
    "max_distance_m",
    "ceiling_height_m",
    "openness",
    "room_size",
    "damping",
    "wet",
    "predelay_msec",
    "sample_points",
    "evidence",
)
SURFACES = ("wall", "floor", "ceiling", "trim")


class ModuleContractError(ValueError):
    """A module record set cannot satisfy the generation-template contract."""


def _load(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ModuleContractError(f"Cannot read {path}: {error}") from error
    if not isinstance(record, dict):
        raise ModuleContractError(f"Record is not a JSON object: {path}")
    return record


def _reference(path: Path, root: Path) -> dict[str, str]:
    return {
        "path": repo_relative(path, root),
        "sha256": sha256_file(path),
    }


@lru_cache(maxsize=8)
def _acoustics_document(path_text: str, mtime_ns: int, size: int) -> dict[str, Any]:
    del mtime_ns, size
    return _load(Path(path_text))


@lru_cache(maxsize=8)
def _metadata_validator(
    path_text: str, mtime_ns: int, size: int
) -> Draft202012Validator:
    del mtime_ns, size
    schema = json.loads(Path(path_text).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _module_key(entry: dict[str, Any]) -> str:
    module_id, version = entry.get("module_id"), entry.get("version")
    if not isinstance(module_id, str) or not isinstance(version, int):
        raise ModuleContractError("Admitted module entry has no module_id/version")
    return f"{module_id}@{version}"


def _metadata_path(entry: dict[str, Any], profile: Path, root: Path) -> Path:
    if entry.get("room_dir"):
        return profile.parent / "module_metadata.json"
    return root / MODULE_METADATA_DIR / f"{entry['module_id']}-v{entry['version']}.json"


def _profile_errors(entry: dict[str, Any], profile: Path, root: Path) -> list[str]:
    label = repo_relative(profile, root)
    try:
        record = _load(profile)
    except ModuleContractError as error:
        return [str(error)]
    errors = [f"{label}: {error}" for error in tv.module_profile_errors(record, root)]
    if record.get("module_id") != entry["module_id"]:
        errors.append(f"{label}: module_id does not match the library index")
    if record.get("version") != entry["version"]:
        errors.append(f"{label}: version does not match the library index")
    if record.get("source_id") != entry.get("source_id"):
        errors.append(f"{label}: source_id does not match the library index")
    for surface in SURFACES:
        block = record.get("surfaces", {}).get(surface)
        if not isinstance(block, dict):
            errors.append(f"{label}: missing {surface} surface descriptor")
    return errors


def _acoustics_errors(
    entry: dict[str, Any],
    profile: Path,
    profile_exists: bool,
    root: Path,
) -> list[str]:
    label = repo_relative(root / MODULE_ACOUSTICS, root)
    path = root / MODULE_ACOUSTICS
    try:
        stat = path.stat()
        modules = _acoustics_document(
            str(path.resolve()), stat.st_mtime_ns, stat.st_size
        ).get("modules", {})
    except (ModuleContractError, OSError) as error:
        return [str(error)]
    record = modules.get(_module_key(entry))
    if not isinstance(record, dict):
        return [f"{label}: missing {_module_key(entry)}"]
    errors = []
    for field in ("acoustic", "evidence", "probe", "absorption"):
        if field not in record:
            errors.append(f"{label}: {_module_key(entry)} lacks {field}")
    probe = record.get("probe")
    if isinstance(probe, dict):
        errors.extend(
            f"{label}: {_module_key(entry)} probe lacks {field}"
            for field in PROBE_FIELDS
            if field not in probe
        )
    if profile_exists:
        expected = _reference(profile, root)
        if record.get("profile") != expected:
            errors.append(f"{label}: {_module_key(entry)} profile reference is stale")
    return errors


def _surface_errors(
    entry: dict[str, Any], profile: Path, profile_exists: bool, root: Path
) -> list[str]:
    descriptor_file = descriptor_path(profile, root)
    if not descriptor_file.is_file():
        return [f"{repo_relative(descriptor_file, root)}: surface descriptor missing"]
    if not profile_exists:
        return []
    try:
        descriptor = _load(descriptor_file)
    except ModuleContractError as error:
        return [str(error)]
    errors = [
        f"{repo_relative(descriptor_file, root)}: {error}"
        for error in validate_descriptor(descriptor, profile, root)
    ]
    if descriptor.get("module_id") != entry["module_id"]:
        errors.append(
            f"{repo_relative(descriptor_file, root)}: module_id does not match the index"
        )
    return errors


def _metadata_errors(
    entry: dict[str, Any], profile: Path, profile_exists: bool, root: Path
) -> list[str]:
    metadata = _metadata_path(entry, profile, root)
    if not metadata.is_file():
        return [
            f"{repo_relative(metadata, root)}: consolidated module metadata missing"
        ]
    if not profile_exists:
        return []
    schema_path = root / MODULE_METADATA_SCHEMA
    try:
        record = _load(metadata)
        schema_stat = schema_path.stat()
        validator = _metadata_validator(
            str(schema_path.resolve()), schema_stat.st_mtime_ns, schema_stat.st_size
        )
    except (ModuleContractError, OSError, json.JSONDecodeError) as error:
        return [str(error)]
    label = repo_relative(metadata, root)
    errors = [
        f"{label}: schema: {error.message}" for error in validator.iter_errors(record)
    ]
    errors.extend(
        f"{label}: {error}"
        for error in validate_module_metadata(record, root, metadata)
    )
    return errors


def module_contract_errors(entry: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Return every missing or stale template artifact for one module entry."""
    try:
        _module_key(entry)
        profile = profile_path(entry, root)
    except (ModuleContractError, KeyError, ValueError) as error:
        return [str(error)]
    profile_exists = profile.is_file()
    errors = (
        []
        if profile_exists
        else [f"{repo_relative(profile, root)}: module profile missing"]
    )
    if profile_exists:
        errors += _profile_errors(entry, profile, root)
    errors += _acoustics_errors(entry, profile, profile_exists, root)
    errors += _surface_errors(entry, profile, profile_exists, root)
    errors += _metadata_errors(entry, profile, profile_exists, root)
    return errors
