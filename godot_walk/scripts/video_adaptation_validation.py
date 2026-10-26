"""Read-only validation for versioned video-to-PSX adaptation records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from video_adaptation_compatibility import (
    read_compatibility_extension,
    read_compatibility_record,
    verify_legacy_source_record,
)
from video_adaptation_contracts import (
    V1_FREEZE,
    V2_FREEZE,
    V3_FREEZE,
    candidate_identity_v2,
    sha256_file,  # noqa: F401 - public compatibility export for workflow scripts
    verify_versioned_freezes,
)
from video_adaptation_decisions import verify_stage_receipts as _verify_stage_receipts
from video_adaptation_errors import AdaptationValidationError
from video_adaptation_evidence import (
    validate_record_schema as _validate_record_schema,
)
from video_adaptation_evidence import (
    verify_catalog_snapshot_binding as _verify_catalog_snapshot_binding,
)
from video_adaptation_evidence import (
    verify_dependency_manifest as _verify_dependency_manifest,
)
from video_adaptation_evidence import (
    verify_frame_artifacts as _verify_frame_artifacts,
)
from video_adaptation_evidence import (
    verify_record_results as _verify_record_results,
)
from video_adaptation_paths import ROOT, resolve_repo_path, validate_adaptation_id
from video_adaptation_scene_dependencies import validate_required_scene_dependencies
from video_adaptation_semantics import (
    validate_static_spatial_contract,
)


def repo_file(relative_path: str) -> Path:
    return resolve_repo_path(relative_path, ROOT, require_file=True)


def canonical_fingerprint(artifacts: list[dict[str, str]]) -> str:
    ordered = sorted(artifacts, key=lambda item: item["path"])
    payload = json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_bundle(bundle_path: Path) -> tuple[dict[str, Any], str]:
    """Validate a bundle without writing or launching a subprocess."""
    resolved, record, version = _read_bundle(bundle_path)
    _, v3_freeze = verify_versioned_freezes()
    fingerprint = _validate_bundle_content(record, resolved, version, v3_freeze)
    _verify_stage_receipts(
        resolved,
        record["adaptation_id"],
        fingerprint,
        candidate_identity=candidate_identity_v2(record),
    )
    return record, fingerprint


def _read_bundle(bundle_path: Path) -> tuple[Path, dict[str, Any], int]:
    resolved = bundle_path.resolve(strict=True)
    if not resolved.is_relative_to(ROOT.resolve()) or not resolved.is_file():
        raise AdaptationValidationError(
            "Bundle must be an existing file inside the repository"
        )
    record = json.loads(resolved.read_text(encoding="utf-8"))
    validate_adaptation_id(record.get("adaptation_id"))
    version = _contract_version(record)
    _validate_record_schema(record, version)
    return resolved, record, version


def _validate_bundle_content(
    record: dict[str, Any], resolved: Path, version: int, v3_freeze: dict[str, Any]
) -> str:
    _verify_frozen_contract_reference(record, version)
    _verify_frame_artifacts(record)
    dependencies = record["resolved_adaptation"]["dependencies"]
    _verify_candidate_catalog_dependency(record, dependencies, version)
    compatibility = (
        read_compatibility_record(resolved, v3_freeze) if version == 1 else {}
    )
    extension = (
        read_compatibility_extension(resolved, record, compatibility, v3_freeze)
        if version == 1
        else {}
    )
    snapshot_reference = (
        compatibility["catalog_snapshot"]
        if version == 1
        else record["catalog_snapshot"]
    )
    _verify_catalog_snapshot_binding(snapshot_reference, v3_freeze)
    _verify_dependency_manifest(dependencies, compatibility, v3_freeze, extension)
    validate_static_spatial_contract(record)
    dynamic_declarations = (
        extension.get("dynamic_resource_declarations", [])
        if version == 1
        else record["resolved_adaptation"].get("dynamic_resource_declarations", [])
    )
    validate_required_scene_dependencies(
        record,
        _load_snapshot(snapshot_reference),
        dynamic_declarations=dynamic_declarations,
        supplemental_dependencies=extension.get("supplemental_dependencies", []),
    )
    return _validate_fingerprints(record, resolved, version, compatibility)


def _verify_candidate_catalog_dependency(
    record: dict[str, Any], dependencies: list[dict[str, str]], version: int
) -> None:
    if version == 1:
        return
    snapshot = record["catalog_snapshot"]
    by_path = {item["path"]: item for item in dependencies}
    if "godot_walk/room_catalog/catalog.json" in by_path:
        raise AdaptationValidationError(
            "Versioned candidates must depend on the frozen catalog snapshot, not the live catalog"
        )
    artifact = by_path.get(snapshot["path"])
    if artifact is None or artifact["sha256"] != snapshot["sha256"]:
        raise AdaptationValidationError(
            "Versioned candidate dependency manifest must include its exact catalog snapshot"
        )


def _validate_fingerprints(
    record: dict[str, Any], resolved: Path, version: int, compatibility: dict[str, Any]
) -> str:
    dependency_fingerprint = canonical_fingerprint(
        record["resolved_adaptation"]["dependencies"]
    )
    if version == 1:
        verify_legacy_source_record(record, resolved, compatibility)
        fingerprint = dependency_fingerprint
    else:
        fingerprint = candidate_identity_v2(record)
        if record["candidate_identity"] != fingerprint:
            raise AdaptationValidationError("Candidate identity is stale")
    _verify_record_results(record, fingerprint, version, canonical_fingerprint)
    return fingerprint


def _contract_version(record: dict[str, Any]) -> int:
    if record.get("contract_id") != "godot_video_room_completion":
        raise AdaptationValidationError("Unknown video-adaptation contract ID")
    if record.get("contract_version") == "1.0.0" and record.get("schema_version") == 1:
        return 1
    if record.get("contract_version") == "2.0.0" and record.get("schema_version") == 2:
        return 2
    if record.get("contract_version") == "3.0.0" and record.get("schema_version") == 3:
        return 3
    raise AdaptationValidationError("Unsupported video-adaptation contract version")


def _verify_frozen_contract_reference(record: dict[str, Any], version: int) -> None:
    reference = record.get("contract_freeze")
    if reference is None:
        if version >= 2:
            raise AdaptationValidationError(
                "Versioned adaptation records must reference their frozen contract manifest"
            )
        return
    expected_path = {1: V1_FREEZE, 2: V2_FREEZE, 3: V3_FREEZE}[version]
    expected = repo_file(expected_path)
    if reference["path"] != expected_path:
        raise AdaptationValidationError(
            "Adaptation references an unknown frozen contract"
        )
    if reference["sha256"] != hashlib.sha256(expected.read_bytes()).hexdigest():
        raise AdaptationValidationError(
            "Adaptation references a different contract freeze"
        )


def _load_snapshot(reference: dict[str, Any]) -> dict[str, Any]:
    path = repo_file(reference["path"])
    return json.loads(path.read_text(encoding="utf-8"))
