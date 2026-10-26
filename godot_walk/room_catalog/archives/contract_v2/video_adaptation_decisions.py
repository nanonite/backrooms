"""Candidate-bound operator decisions and stage receipt verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from video_adaptation_contracts import sha256_file
from video_adaptation_errors import AdaptationValidationError
from video_adaptation_paths import ROOT, receipt_files, resolve_repo_path


def verify_v1_decision_binding(
    record: dict[str, Any], decision: dict[str, Any], fingerprint: str
) -> None:
    if record["status"] == "accepted_reference":
        _require_accepted_decision(decision, fingerprint)
        _verify_decision_artifact(decision)
    elif decision.get("status") == "accepted":
        raise AdaptationValidationError(
            "Pending or rejected v1 records cannot validate as accepted"
        )
    elif decision.get("decision_record_path"):
        _verify_decision_artifact(decision)


def verify_v2_decision(
    record: dict[str, Any], candidate_identity: str, *, root: Path = ROOT
) -> None:
    decision = record["operator_decision"]
    _require_accepted_decision(decision, candidate_identity)
    path = resolve_repo_path(decision["decision_record_path"], root, require_file=True)
    if sha256_file(path) != decision["decision_sha256"]:
        raise AdaptationValidationError("Decision artifact hash mismatch")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    _verify_artifact_identity(artifact, record["adaptation_id"], candidate_identity)


def verify_stage_receipts(
    bundle_path: Path,
    adaptation_id: str,
    fingerprint: str,
    *,
    candidate_identity: str | None = None,
    root: Path = ROOT,
) -> None:
    for path in receipt_files(bundle_path, adaptation_id, root):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        _verify_receipt_identity(
            receipt, adaptation_id, fingerprint, candidate_identity, path.name
        )
        _verify_receipt_artifacts(receipt.get("artifacts", []), root)


def _require_accepted_decision(decision: dict[str, Any], fingerprint: str) -> None:
    if (
        decision.get("status") != "accepted"
        or decision.get("candidate_fingerprint") != fingerprint
    ):
        raise AdaptationValidationError(
            "Accepted decision needs the current candidate fingerprint"
        )
    if not decision.get("decision_record_path") or not decision.get("decision_sha256"):
        raise AdaptationValidationError(
            "Accepted decision requires a verified decision artifact"
        )


def _verify_decision_artifact(decision: dict[str, Any]) -> None:
    path = resolve_repo_path(decision["decision_record_path"], ROOT, require_file=True)
    if sha256_file(path) != decision["decision_sha256"]:
        raise AdaptationValidationError("Decision artifact hash mismatch")


def _verify_artifact_identity(
    artifact: dict[str, Any], adaptation_id: str, candidate_identity: str
) -> None:
    expected = {
        "adaptation_id": adaptation_id,
        "candidate_identity": candidate_identity,
        "decision": "accepted",
    }
    if any(artifact.get(key) != value for key, value in expected.items()):
        raise AdaptationValidationError(
            "Decision artifact identity or decision does not match this candidate"
        )


def _verify_receipt_identity(
    receipt: dict[str, Any],
    adaptation_id: str,
    fingerprint: str,
    candidate_identity: str | None,
    receipt_name: str,
) -> None:
    if receipt.get("adaptation_id") != adaptation_id:
        raise AdaptationValidationError(
            f"Stage receipt belongs to a different adaptation: {receipt_name}"
        )
    is_v2_receipt = receipt.get("schema_version") == 2
    actual = (
        receipt.get("candidate_identity")
        if is_v2_receipt
        else receipt.get("candidate_fingerprint")
    )
    expected = candidate_identity if is_v2_receipt else fingerprint
    if actual != expected:
        raise AdaptationValidationError(f"Stage receipt is stale: {receipt_name}")


def _verify_receipt_artifacts(artifacts: list[dict[str, str]], root: Path) -> None:
    for artifact in artifacts:
        path = resolve_repo_path(artifact["path"], root, require_file=True)
        if sha256_file(path) != artifact["sha256"]:
            raise AdaptationValidationError(
                f"Stage receipt artifact hash mismatch: {artifact['path']}"
            )
