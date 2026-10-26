"""Read-only validation for versioned video-to-PSX adaptation records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "godot_walk/room_catalog/video_adaptation.schema.json"
FREEZE_PATH = ROOT / "godot_walk/room_catalog/contract_freeze_v1.json"
FREEZE_HASH_PATH = FREEZE_PATH.with_suffix(".sha256")


class AdaptationValidationError(ValueError):
    """Raised when a record or its bound artifacts do not match the contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repo_file(relative_path: str) -> Path:
    candidate = (ROOT / relative_path).resolve()
    if not candidate.is_relative_to(ROOT) or not candidate.is_file():
        raise AdaptationValidationError(f"Missing or out-of-repository file: {relative_path}")
    return candidate


def canonical_fingerprint(artifacts: list[dict[str, str]]) -> str:
    ordered = sorted(artifacts, key=lambda item: item["path"])
    payload = json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _verify_artifacts(artifacts: list[dict[str, str]]) -> None:
    for artifact in artifacts:
        path = repo_file(artifact["path"])
        actual = sha256_file(path)
        if actual != artifact["sha256"]:
            raise AdaptationValidationError(f"Hash mismatch: {artifact['path']}")


def _verify_contract_freeze() -> str:
    manifest_hash = sha256_file(FREEZE_PATH)
    sidecar = FREEZE_HASH_PATH.read_text(encoding="utf-8").split()[0]
    if manifest_hash != sidecar:
        raise AdaptationValidationError("Contract freeze manifest hash differs from its sidecar")
    manifest = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    _verify_artifacts(list(manifest["files"].values()))
    catalog = json.loads(repo_file(manifest["files"]["catalog"]["path"]).read_text(encoding="utf-8"))
    if catalog["catalog_version"] != manifest["catalog_identity"]["catalog_version"]:
        raise AdaptationValidationError("Frozen catalog version changed")
    return manifest_hash


def _validate_record_schema(record: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(record),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        field = "/".join(str(part) for part in first.absolute_path) or "record"
        raise AdaptationValidationError(f"Schema error at {field}: {first.message}")


def _verify_frame_artifacts(record: dict[str, Any]) -> None:
    observations = record["source_observations"]
    _verify_artifacts([observations["video"]])
    for frame in observations["frames"]:
        _verify_artifacts([{"path": frame["path"], "sha256": frame["sha256"]}])
        _verify_artifacts(frame.get("crops", []))


def _verify_module_refs(record: dict[str, Any]) -> None:
    catalog = json.loads(repo_file("godot_walk/room_catalog/catalog.json").read_text(encoding="utf-8"))
    modules = {module["id"]: module["version"] for module in catalog["modules"]}
    for module_ref in record["resolved_adaptation"]["catalog_module_refs"]:
        module_id = module_ref["catalog_id"]
        if modules.get(module_id) != module_ref["version"]:
            raise AdaptationValidationError(f"Catalog module reference is missing or changed: {module_id}")


def _verify_record_results(record: dict[str, Any], fingerprint: str) -> None:
    decision = record["operator_decision"]
    if decision["candidate_fingerprint"] not in (None, fingerprint):
        raise AdaptationValidationError("Operator decision is bound to a different candidate version")
    if decision["decision_record_path"] is not None:
        decision_artifact = {
            "path": decision["decision_record_path"],
            "sha256": decision["decision_sha256"],
        }
        _verify_artifacts([decision_artifact])
    for stage in record["validation"]["stages"]:
        if stage["status"] == "passed" and stage["candidate_fingerprint"] != fingerprint:
            raise AdaptationValidationError(f"Passed result is stale: {stage['stage_id']}")
        _verify_artifacts(stage["artifacts"])


def _verify_stage_receipts(bundle_path: Path, adaptation_id: str, fingerprint: str) -> None:
    receipt_dir = bundle_path.parent / "stage_receipts" / adaptation_id
    if not receipt_dir.is_dir():
        return
    for receipt_path in sorted(receipt_dir.glob("*.json")):
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt["candidate_fingerprint"] != fingerprint:
            raise AdaptationValidationError(f"Stage receipt is stale: {receipt_path.name}")
        _verify_artifacts(receipt["artifacts"])


def validate_bundle(bundle_path: Path) -> tuple[dict[str, Any], str]:
    """Validate a bundle without writing or launching a subprocess."""
    resolved = bundle_path.resolve()
    if not resolved.is_relative_to(ROOT) or not resolved.is_file():
        raise AdaptationValidationError("Bundle must be an existing file inside the repository")
    freeze_hash = _verify_contract_freeze()
    record = json.loads(resolved.read_text(encoding="utf-8"))
    _validate_record_schema(record)
    _verify_frame_artifacts(record)
    _verify_artifacts(record["resolved_adaptation"]["dependencies"])
    _verify_module_refs(record)
    fingerprint = canonical_fingerprint(record["resolved_adaptation"]["dependencies"])
    _verify_record_results(record, fingerprint)
    _verify_stage_receipts(resolved, record["adaptation_id"], fingerprint)
    reference = record.get("contract_freeze")
    if reference and (reference["path"] != FREEZE_PATH.relative_to(ROOT).as_posix()
                      or reference["sha256"] != freeze_hash):
        raise AdaptationValidationError("Adaptation references a different frozen contract")
    return record, fingerprint
