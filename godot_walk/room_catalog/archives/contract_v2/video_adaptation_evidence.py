"""Artifact, decision, and receipt checks shared by the v1/v2 validators."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jsonschema
from video_adaptation_contracts import (
    V2_SCHEMA,
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
    v2_freeze: dict[str, Any],
) -> None:
    migrations = {
        item["record_dependency_path"]: item
        for item in compatibility.get("migrated_tool_dependencies", [])
    }
    frozen_v2 = {item["path"]: item["sha256"] for item in v2_freeze["files"].values()}
    seen: set[str] = set()
    for artifact in artifacts:
        path_text = artifact["path"]
        if path_text in seen:
            raise AdaptationValidationError(
                f"Duplicate artifact manifest path: {path_text}"
            )
        seen.add(path_text)
        migration = migrations.get(path_text)
        if migration is None:
            verify_artifacts([artifact])
            continue
        _verify_migrated_tool(artifact, migration, frozen_v2)


def validate_record_schema(record: dict[str, Any], version: int) -> None:
    schema_path = SCHEMA_V2_PATH if version == 2 else SCHEMA_V1_PATH
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
    reference: dict[str, Any], freeze: dict[str, Any]
) -> None:
    if reference != freeze["catalog_snapshot"]:
        raise AdaptationValidationError(
            "Adaptation is not bound to the frozen versioned catalog snapshot"
        )
    snapshot_path = resolve_repo_path(reference["path"], ROOT, require_file=True)
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
        if version == 2
        else fingerprint_function(record["resolved_adaptation"]["dependencies"])
    )
    for stage in record["validation"]["stages"]:
        _verify_stage_result(stage, expected)


def _verify_stage_result(stage: dict[str, Any], expected: str) -> None:
    if stage["status"] == "passed" and stage["candidate_fingerprint"] != expected:
        raise AdaptationValidationError(f"Passed result is stale: {stage['stage_id']}")
    verify_artifacts(stage["artifacts"])


def _verify_migrated_tool(
    artifact: dict[str, str], migration: dict[str, str], frozen_v2: dict[str, str]
) -> None:
    path_text = artifact["path"]
    if (
        path_text not in MIGRATABLE_TOOL_PATHS
        or artifact["sha256"] != migration["legacy_sha256"]
    ):
        raise AdaptationValidationError(
            f"Invalid legacy tooling migration for {path_text}"
        )
    _verify_migration_hashes(artifact, migration, frozen_v2)


def _verify_migration_hashes(
    artifact: dict[str, str], migration: dict[str, str], frozen_v2: dict[str, str]
) -> None:
    archived = resolve_repo_path(
        migration["archived_source_path"], ROOT, require_file=True
    )
    active = resolve_repo_path(migration["active_tool_path"], ROOT, require_file=True)
    if sha256_file(archived) != artifact["sha256"]:
        raise AdaptationValidationError(
            f"Archived v1 tool no longer matches its old fingerprint: {artifact['path']}"
        )
    if sha256_file(active) != migration["active_tool_sha256"]:
        raise AdaptationValidationError(
            f"Hardened v2 tool changed after migration: {artifact['path']}"
        )
    if frozen_v2.get(migration["active_tool_path"]) != migration["active_tool_sha256"]:
        raise AdaptationValidationError(
            f"Hardened tool is absent from the v2 freeze: {artifact['path']}"
        )
