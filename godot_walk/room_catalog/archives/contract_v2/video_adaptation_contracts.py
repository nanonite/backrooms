"""Versioned contract and compatibility bindings for video adaptations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from video_adaptation_errors import AdaptationValidationError
from video_adaptation_paths import ROOT, resolve_repo_path

V1_FREEZE = "godot_walk/room_catalog/contract_freeze_v1.json"
V1_FREEZE_HASH = "godot_walk/room_catalog/contract_freeze_v1.sha256"
V2_FREEZE = "godot_walk/room_catalog/contract_freeze_v2.json"
V2_FREEZE_HASH = "godot_walk/room_catalog/contract_freeze_v2.sha256"
V2_SCHEMA = "godot_walk/room_catalog/video_adaptation.schema.v2.json"
V2_CONTRACT = "godot_walk/room_catalog/video_adaptation_contract_v2.md"
V2_SNAPSHOT = "godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.2.0.json"
V2_COMPAT_DIR = "godot_walk/room_catalog/adaptations/compatibility_v2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def candidate_identity_v2(record: dict[str, Any]) -> str:
    payload = {
        "contract_id": record["contract_id"],
        "contract_version": record.get("contract_version", "2.0.0"),
        "adaptation_id": record["adaptation_id"],
        "catalog_snapshot": record.get("catalog_snapshot"),
        "registration_accepted": record["registration_accepted"],
        "scale_calibrated": record["scale_calibrated"],
        "source_observations": record["source_observations"],
        "reusable_requirements": record["reusable_requirements"],
        "resolved_adaptation": record["resolved_adaptation"],
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def verify_versioned_freezes(
    root: Path = ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    v1 = _read_freeze(V1_FREEZE, V1_FREEZE_HASH, root)
    v2 = _read_freeze(V2_FREEZE, V2_FREEZE_HASH, root)
    _verify_snapshot_identity(v1, v2, root)
    _verify_v2_artifacts(v2, root)
    return v1, v2


def _verify_snapshot_identity(
    v1: dict[str, Any], v2: dict[str, Any], root: Path
) -> None:
    expected_catalog_hash = v1["files"]["catalog"]["sha256"]
    snapshot = v2["catalog_snapshot"]
    snapshot_path = resolve_repo_path(snapshot["path"], root, require_file=True)
    if (
        sha256_file(snapshot_path) != expected_catalog_hash
        or snapshot["sha256"] != expected_catalog_hash
    ):
        raise AdaptationValidationError(
            "Immutable v2 catalog snapshot differs from the original frozen catalog"
        )
    if v2["contract_version"] != "2.0.0" or v2["freeze_version"] != 2:
        raise AdaptationValidationError("Unsupported v2 adaptation freeze")
    snapshot_document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if (
        snapshot_document["catalog_id"] != snapshot["catalog_id"]
        or snapshot_document["catalog_version"] != snapshot["catalog_version"]
        or snapshot["catalog_version"] != v1["catalog_identity"]["catalog_version"]
    ):
        raise AdaptationValidationError(
            "Catalog snapshot identity differs from the frozen catalog identity"
        )


def _verify_v2_artifacts(v2: dict[str, Any], root: Path) -> None:
    for name, artifact in v2["files"].items():
        if name == "v1_live_catalog_reference":
            continue
        _verify_artifact(artifact, root)


def _read_freeze(manifest_path: str, sidecar_path: str, root: Path) -> dict[str, Any]:
    manifest_file = resolve_repo_path(manifest_path, root, require_file=True)
    sidecar_file = resolve_repo_path(sidecar_path, root, require_file=True)
    expected = sidecar_file.read_text(encoding="utf-8").split()[0]
    if sha256_file(manifest_file) != expected:
        raise AdaptationValidationError(
            f"{manifest_path} differs from its hash sidecar"
        )
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    for key, artifact in manifest["files"].items():
        if manifest_path == V1_FREEZE and key == "catalog":
            continue
        if key == "v1_live_catalog_reference":
            continue
        _verify_artifact(artifact, root)
    return manifest


def _verify_artifact(artifact: dict[str, str], root: Path) -> None:
    path = resolve_repo_path(artifact["path"], root, require_file=True)
    if sha256_file(path) != artifact["sha256"]:
        raise AdaptationValidationError(
            f"Frozen artifact hash mismatch: {artifact['path']}"
        )
