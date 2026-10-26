"""Strict migration bindings for accepted contract-v1 adaptation records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from video_adaptation_contracts import candidate_identity_v2, sha256_file
from video_adaptation_errors import AdaptationValidationError
from video_adaptation_paths import ROOT, resolve_repo_path


def read_compatibility_record(
    adaptation_path: Path, v2: dict[str, Any], root: Path = ROOT
) -> dict[str, Any]:
    relative = adaptation_path.relative_to(root.resolve()).as_posix()
    matches = [
        item
        for item in v2["compatibility_records"].values()
        if item["source_record"]["path"] == relative
    ]
    if len(matches) != 1:
        raise AdaptationValidationError(
            f"No unique v2 compatibility record is frozen for {relative}"
        )
    compatibility = matches[0]
    compat_path = resolve_repo_path(compatibility["path"], root, require_file=True)
    if sha256_file(compat_path) != compatibility["sha256"]:
        raise AdaptationValidationError(
            f"Compatibility record hash mismatch: {compatibility['path']}"
        )
    return json.loads(compat_path.read_text(encoding="utf-8"))


def verify_legacy_source_record(
    record: dict[str, Any],
    record_path: Path,
    compatibility: dict[str, Any],
    root: Path = ROOT,
) -> None:
    if sha256_file(record_path) != compatibility["source_record_sha256"]:
        raise AdaptationValidationError(
            "Historical source record differs from its v2 compatibility binding"
        )
    if record["adaptation_id"] != compatibility["adaptation_id"]:
        raise AdaptationValidationError(
            "Compatibility binding belongs to a different adaptation ID"
        )
    if candidate_identity_v2(record) != compatibility["candidate_identity_v2"]:
        raise AdaptationValidationError(
            "Decision-relevant candidate metadata changed after v2 migration"
        )
    _verify_frozen_decision_reference(record, compatibility, root)


def _verify_frozen_decision_reference(
    record: dict[str, Any], compatibility: dict[str, Any], root: Path
) -> None:
    artifact = compatibility["decision_artifact"]
    decision = record["operator_decision"]
    if (
        decision.get("decision_record_path") != artifact["path"]
        or decision.get("decision_sha256") != artifact["sha256"]
    ):
        raise AdaptationValidationError(
            "Historical record does not reference its frozen decision artifact"
        )
    path = resolve_repo_path(artifact["path"], root, require_file=True)
    if sha256_file(path) != artifact["sha256"]:
        raise AdaptationValidationError(
            "Historical decision artifact hash differs from its v2 binding"
        )
    _verify_legacy_decision(record, compatibility, path)


def _verify_legacy_decision(
    record: dict[str, Any], compatibility: dict[str, Any], artifact_path: Path
) -> None:
    decision = record["operator_decision"]
    if record["status"] != "accepted_reference" or decision.get("status") != "accepted":
        raise AdaptationValidationError(
            "Historical compatibility bindings only accept explicitly approved records"
        )
    fingerprint = compatibility["legacy_dependency_fingerprint"]
    if decision.get("candidate_fingerprint") != fingerprint:
        raise AdaptationValidationError(
            "Historical approval is not bound to the current legacy dependency fingerprint"
        )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    contract = compatibility["decision_contract"]
    if not _decision_matches(artifact, record, contract, fingerprint):
        raise AdaptationValidationError(
            "Historical decision artifact does not affirm this candidate"
        )


def _decision_matches(
    artifact: dict[str, Any],
    record: dict[str, Any],
    contract: dict[str, Any],
    fingerprint: str,
) -> bool:
    decision = artifact.get("decision")
    if decision not in contract["accepted_decisions"]:
        return False
    if contract["format"] == "version_fingerprint_decision":
        return _matches_version_fingerprint(artifact, contract, fingerprint)
    if contract["format"] == "accepted_layout_decision":
        return _matches_accepted_layout(artifact, record, contract)
    if contract["format"] == "candidate_id_decision":
        return artifact.get("candidate_id") == contract["candidate_id"]
    raise AdaptationValidationError("Unsupported frozen historical decision format")


def _matches_version_fingerprint(
    artifact: dict[str, Any], contract: dict[str, Any], fingerprint: str
) -> bool:
    return (
        artifact.get("candidate_version") == contract["candidate_version"]
        and artifact.get("candidate_fingerprint") == fingerprint
    )


def _matches_accepted_layout(
    artifact: dict[str, Any], record: dict[str, Any], contract: dict[str, Any]
) -> bool:
    layout_ids = {
        socket.get("tested_connection_ref", "").split(":", 1)[0]
        for socket in record["resolved_adaptation"]["sockets"]
        if socket.get("tested_connection_ref")
    }
    return (
        artifact.get("issue") == contract["issue"]
        and artifact.get("reviewer") == contract["reviewer"]
        and artifact.get("reviewed_layout_id") == contract["layout_id"]
        and artifact.get("reviewed_connection_id") == contract["connection_id"]
        and contract["layout_id"] in layout_ids
    )
