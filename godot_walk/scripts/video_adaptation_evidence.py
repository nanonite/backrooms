"""Artifact, decision, and receipt checks shared by versioned validators."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jsonschema
from video_adaptation_contracts import (
    V2_SCHEMA,
    V3_SCHEMA,
    sha256_file,
)
from video_adaptation_decisions import verify_v1_decision_binding, verify_v2_decision
from video_adaptation_errors import AdaptationValidationError
from video_adaptation_paths import ROOT, resolve_repo_path

SCHEMA_V1_PATH = ROOT / "godot_walk/room_catalog/video_adaptation.schema.json"
SCHEMA_V2_PATH = ROOT / V2_SCHEMA
MIGRATABLE_TOOL_PATHS = {
    "godot_walk/scripts/video_adaptation_runner.py",
    "godot_walk/scripts/video_adaptation_sources.py",
    "godot_walk/scripts/video_adaptation_validation.py",
}


def verify_artifacts(artifacts: list[dict[str, str]], root: Path = ROOT) -> None:
    seen: set[str] = set()
    for artifact in artifacts:
        path_text = artifact["path"]
        if path_text in seen:
            raise AdaptationValidationError(
                f"Duplicate artifact manifest path: {path_text}"
            )
        seen.add(path_text)
        path = resolve_repo_path(path_text, root, require_file=True)
        if sha256_file(path) != artifact["sha256"]:
            raise AdaptationValidationError(f"Hash mismatch: {path_text}")


def verify_dependency_manifest(
    artifacts: list[dict[str, str]],
    compatibility: dict[str, Any],
    v3_freeze: dict[str, Any],
    compatibility_extension: dict[str, Any] | None = None,
    root: Path = ROOT,
) -> None:
    migrations = {
        item["record_dependency_path"]: item
        for item in compatibility.get("migrated_tool_dependencies", [])
    }
    catalog_migrations = {
        item["record_dependency_path"]: item
        for item in (compatibility_extension or {}).get(
            "catalog_dependency_bindings", []
        )
    }
    if len(catalog_migrations) != len(
        (compatibility_extension or {}).get("catalog_dependency_bindings", [])
    ):
        raise AdaptationValidationError(
            "Duplicate historical catalog dependency binding"
        )
    supplemental = (compatibility_extension or {}).get("supplemental_dependencies", [])
    supplemental_paths = [item["path"] for item in supplemental]
    if len(supplemental_paths) != len(set(supplemental_paths)):
        raise AdaptationValidationError("Duplicate supplemental dependency path")
    if set(supplemental_paths) & {item["path"] for item in artifacts}:
        raise AdaptationValidationError(
            "Supplemental dependency duplicates a historical dependency"
        )
    verify_artifacts(supplemental, root)
    expected_supplemental = (compatibility_extension or {}).get(
        "supplemental_dependency_fingerprint"
    )
    if supplemental and expected_supplemental is None:
        raise AdaptationValidationError(
            "Supplemental dependencies require their own fingerprint"
        )
    if (
        expected_supplemental is not None
        and _artifact_fingerprint(supplemental) != expected_supplemental
    ):
        raise AdaptationValidationError(
            "Supplemental dependency fingerprint does not match its manifest"
        )
    seen: set[str] = set()
    for artifact in artifacts:
        path_text = artifact["path"]
        if path_text in seen:
            raise AdaptationValidationError(
                f"Duplicate artifact manifest path: {path_text}"
            )
        seen.add(path_text)
        migration = migrations.get(path_text)
        catalog_migration = catalog_migrations.get(path_text)
        if migration is not None:
            _verify_migrated_tool(artifact, migration, v3_freeze)
            continue
        if catalog_migration is not None:
            _verify_archived_catalog(artifact, catalog_migration, v3_freeze, root)
            continue
        verify_artifacts([artifact], root)
    if set(catalog_migrations) - seen:
        raise AdaptationValidationError(
            "Historical catalog binding is absent from the dependency manifest"
        )


def validate_record_schema(record: dict[str, Any], version: int) -> None:
    schema_path = (
        ROOT / V3_SCHEMA
        if version == 3
        else SCHEMA_V2_PATH
        if version == 2
        else SCHEMA_V1_PATH
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(record),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        field = "/".join(str(part) for part in first.absolute_path) or "record"
        raise AdaptationValidationError(f"Schema error at {field}: {first.message}")


def verify_frame_artifacts(record: dict[str, Any]) -> None:
    observations = record["source_observations"]
    verify_artifacts([observations["video"]])
    for frame in observations["frames"]:
        verify_artifacts([{"path": frame["path"], "sha256": frame["sha256"]}])
        verify_artifacts(frame.get("crops", []))


def verify_catalog_snapshot_binding(
    reference: dict[str, Any], freeze: dict[str, Any], root: Path = ROOT
) -> None:
    if reference != freeze["catalog_snapshot"]:
        raise AdaptationValidationError(
            "Adaptation is not bound to the frozen versioned catalog snapshot"
        )
    snapshot_path = resolve_repo_path(reference["path"], root, require_file=True)
    if sha256_file(snapshot_path) != reference["sha256"]:
        raise AdaptationValidationError("Referenced catalog snapshot hash mismatch")


def verify_record_results(
    record: dict[str, Any],
    fingerprint: str,
    version: int,
    fingerprint_function: Callable[[list[dict[str, str]]], str],
) -> None:
    _verify_decision_state(record, fingerprint, version)
    _verify_validation_stages(record, fingerprint, version, fingerprint_function)


def _verify_decision_state(
    record: dict[str, Any], fingerprint: str, version: int
) -> None:
    decision = record["operator_decision"]
    if version == 1:
        verify_v1_decision_binding(record, decision, fingerprint)
    elif record["status"] == "accepted_reference":
        verify_v2_decision(record, fingerprint)
    elif decision.get("status") == "accepted":
        raise AdaptationValidationError(
            "Pending records cannot carry an accepted decision"
        )


def _verify_validation_stages(
    record: dict[str, Any],
    fingerprint: str,
    version: int,
    fingerprint_function: Callable[[list[dict[str, str]]], str],
) -> None:
    expected = (
        fingerprint
        if version >= 2
        else fingerprint_function(record["resolved_adaptation"]["dependencies"])
    )
    for stage in record["validation"]["stages"]:
        _verify_stage_result(stage, expected)


def _verify_stage_result(stage: dict[str, Any], expected: str) -> None:
    if stage["status"] == "passed" and stage["candidate_fingerprint"] != expected:
        raise AdaptationValidationError(f"Passed result is stale: {stage['stage_id']}")
    verify_artifacts(stage["artifacts"])


def _verify_migrated_tool(
    artifact: dict[str, str], migration: dict[str, str], freeze: dict[str, Any]
) -> None:
    path_text = artifact["path"]
    if (
        path_text not in MIGRATABLE_TOOL_PATHS
        or artifact["sha256"] != migration["legacy_sha256"]
    ):
        raise AdaptationValidationError(
            f"Invalid legacy tooling migration for {path_text}"
        )
    _verify_migration_hashes(artifact, migration, freeze)


def _verify_migration_hashes(
    artifact: dict[str, str], migration: dict[str, str], freeze: dict[str, Any]
) -> None:
    archived = resolve_repo_path(
        migration["archived_source_path"], ROOT, require_file=True
    )
    if sha256_file(archived) != artifact["sha256"]:
        raise AdaptationValidationError(
            f"Archived v1 tool no longer matches its old fingerprint: {artifact['path']}"
        )
    v2_archives = {
        item["original_path"]: item for item in freeze.get("archived_v2_artifacts", [])
    }
    archived_v2 = v2_archives.get(migration["active_tool_path"])
    if archived_v2 is None or archived_v2["sha256"] != migration["active_tool_sha256"]:
        raise AdaptationValidationError(
            f"V2 migration tool is absent from its immutable archive: {artifact['path']}"
        )
    archived_tool = resolve_repo_path(
        archived_v2["archive_path"], ROOT, require_file=True
    )
    if sha256_file(archived_tool) != migration["active_tool_sha256"]:
        raise AdaptationValidationError(
            f"Archived v2 tool differs from the migration binding: {artifact['path']}"
        )


def _verify_archived_catalog(
    artifact: dict[str, str],
    binding: dict[str, str],
    freeze: dict[str, Any],
    root: Path = ROOT,
) -> None:
    snapshot = freeze["catalog_snapshot"]
    if (
        binding["record_dependency_path"] != "godot_walk/room_catalog/catalog.json"
        or artifact["path"] != binding["record_dependency_path"]
        or artifact["sha256"] != binding["legacy_sha256"]
    ):
        raise AdaptationValidationError(
            "Historical live-catalog dependency differs from its frozen fingerprint"
        )
    if (
        binding["snapshot_path"] != snapshot["path"]
        or binding["snapshot_sha256"] != snapshot["sha256"]
    ):
        raise AdaptationValidationError(
            "Historical catalog dependency is not bound to the exact frozen snapshot"
        )
    path = resolve_repo_path(snapshot["path"], root, require_file=True)
    if sha256_file(path) != artifact["sha256"]:
        raise AdaptationValidationError(
            "Frozen catalog snapshot bytes differ from the historical dependency hash"
        )


def _artifact_fingerprint(artifacts: list[dict[str, str]]) -> str:
    ordered = sorted(artifacts, key=lambda item: item["path"])
    payload = json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()
