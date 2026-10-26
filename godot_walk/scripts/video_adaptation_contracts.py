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
V3_FREEZE = "godot_walk/room_catalog/contract_freeze_v3.json"
V3_FREEZE_HASH = "godot_walk/room_catalog/contract_freeze_v3.sha256"
V4_FREEZE = "godot_walk/room_catalog/contract_freeze_v4.json"
V4_FREEZE_HASH = "godot_walk/room_catalog/contract_freeze_v4.sha256"
V2_SCHEMA = "godot_walk/room_catalog/video_adaptation.schema.v2.json"
V3_SCHEMA = "godot_walk/room_catalog/video_adaptation.schema.v3.json"
V2_CONTRACT = "godot_walk/room_catalog/video_adaptation_contract_v2.md"
V2_COMPAT_DIR = "godot_walk/room_catalog/adaptations/compatibility_v2"
V3_COMPAT_DIR = "godot_walk/room_catalog/adaptations/compatibility_v3"
V2_ARCHIVE_DIR = "godot_walk/room_catalog/archives/contract_v2"


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
    v2 = _read_manifest(V2_FREEZE, V2_FREEZE_HASH, root)
    v3 = _read_manifest(V3_FREEZE, V3_FREEZE_HASH, root)
    v4 = _read_freeze(V4_FREEZE, V4_FREEZE_HASH, root)
    _verify_v3_lineage(v1, v2, v3, root)
    _verify_v2_artifacts(v2, v3, root)
    _verify_snapshot_identity(v1, v3, root)
    _verify_v4_lineage(v3, v4, root)
    _verify_v3_artifacts(v3, v4, root)
    return v1, v4


def _verify_v4_lineage(v3: dict[str, Any], v4: dict[str, Any], root: Path) -> None:
    if v4.get("freeze_version") != 4 or v4.get("validator_version") != "4.0.0":
        raise AdaptationValidationError("Unsupported v4 validator freeze")
    migration = v4.get("migration_from", {})
    if (
        migration.get("freeze_path") != V3_FREEZE
        or migration.get("validator_version") != "3.0.0"
    ):
        raise AdaptationValidationError(
            "V4 freeze does not identify its v3 predecessor"
        )
    if any(v4.get(key) != v3.get(key) for key in _INHERITED_FREEZE_FIELDS):
        raise AdaptationValidationError("V4 changed frozen v3 contract metadata")
    _verify_v4_predecessor_hash(v4, root)
    _verify_v4_current_tools(v4, root)


_INHERITED_FREEZE_FIELDS = (
    "contract_id",
    "contract_version",
    "issue",
    "catalog_snapshot",
    "compatibility_records",
    "compatibility_extensions",
    "archived_v2_artifacts",
    "calibration_flags",
)


def _verify_v4_predecessor_hash(v4: dict[str, Any], root: Path) -> None:
    predecessor = resolve_repo_path(V3_FREEZE, root, require_file=True)
    digest = sha256_file(predecessor)
    if v4.get("ancestors", {}).get("v3_freeze_sha256") != digest:
        raise AdaptationValidationError(
            "V4 freeze is not bound to the original v3 freeze"
        )
    _require_pinned_file(v4, V3_FREEZE, digest)
    sidecar = resolve_repo_path(V3_FREEZE_HASH, root, require_file=True)
    _require_pinned_file(v4, V3_FREEZE_HASH, sha256_file(sidecar))


def _verify_v4_current_tools(v4: dict[str, Any], root: Path) -> None:
    current_tools = {
        "active_contracts_v4": "godot_walk/scripts/video_adaptation_contracts.py",
        "active_resource_graph_v4": "godot_walk/scripts/video_adaptation_resource_graph.py",
        "validator_v4_doc": "godot_walk/room_catalog/video_adaptation_validator_v4.md",
    }
    for key, path in current_tools.items():
        artifact = v4["files"].get(key)
        if artifact is None or artifact["path"] != path:
            raise AdaptationValidationError(
                f"V4 freeze does not bind current tool {path}"
            )
        _verify_artifact(artifact, root)


def _verify_v3_artifacts(v3: dict[str, Any], v4: dict[str, Any], root: Path) -> None:
    archives = {
        item["original_path"]: item for item in v4.get("archived_v3_artifacts", [])
    }
    seen_archives = set()
    for artifact in v3["files"].values():
        archived = archives.get(artifact["path"])
        if archived is None:
            _require_pinned_file(v4, artifact["path"], artifact["sha256"])
            _verify_artifact(artifact, root)
            continue
        _verify_archived_v3_artifact(artifact, archived, v4, root)
        seen_archives.add(artifact["path"])
    if seen_archives != archives.keys():
        raise AdaptationValidationError("V4 archive map contains unknown v3 artifacts")


def _verify_archived_v3_artifact(
    artifact: dict[str, str],
    archive: dict[str, str],
    v4: dict[str, Any],
    root: Path,
) -> None:
    if archive["sha256"] != artifact["sha256"]:
        raise AdaptationValidationError(
            f"V3 archive binding differs from frozen artifact: {artifact['path']}"
        )
    _require_pinned_file(v4, archive["archive_path"], archive["sha256"])
    _verify_artifact(
        {"path": archive["archive_path"], "sha256": archive["sha256"]}, root
    )


def _require_pinned_file(freeze: dict[str, Any], path: str, digest: str) -> None:
    if not any(
        item["path"] == path and item["sha256"] == digest
        for item in freeze["files"].values()
    ):
        raise AdaptationValidationError(f"Successor freeze does not pin {path}")


def _verify_snapshot_identity(
    v1: dict[str, Any], v3: dict[str, Any], root: Path
) -> None:
    expected_catalog_hash = v1["files"]["catalog"]["sha256"]
    snapshot = v3["catalog_snapshot"]
    snapshot_path = resolve_repo_path(snapshot["path"], root, require_file=True)
    if (
        sha256_file(snapshot_path) != expected_catalog_hash
        or snapshot["sha256"] != expected_catalog_hash
    ):
        raise AdaptationValidationError(
            "Immutable catalog snapshot differs from the original frozen catalog"
        )
    if v3["contract_version"] != "3.0.0" or v3["freeze_version"] != 3:
        raise AdaptationValidationError("Unsupported v3 adaptation freeze")
    snapshot_document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if (
        snapshot_document["catalog_id"] != snapshot["catalog_id"]
        or snapshot_document["catalog_version"] != snapshot["catalog_version"]
        or snapshot["catalog_version"] != v1["catalog_identity"]["catalog_version"]
    ):
        raise AdaptationValidationError(
            "Catalog snapshot identity differs from the frozen catalog identity"
        )


def _verify_v2_artifacts(v2: dict[str, Any], v3: dict[str, Any], root: Path) -> None:
    archives = {
        item["original_path"]: item for item in v3.get("archived_v2_artifacts", [])
    }
    seen_archives = set()
    for artifact in v2["files"].values():
        archived = archives.get(artifact["path"])
        if archived is None:
            _verify_artifact(artifact, root)
            continue
        seen_archives.add(artifact["path"])
        _verify_archived_v2_artifact(artifact, archived, v3, root)
    if seen_archives != archives.keys():
        raise AdaptationValidationError("V3 archive map contains unknown v2 artifacts")


def _verify_archived_v2_artifact(
    artifact: dict[str, str],
    archive: dict[str, str],
    v3: dict[str, Any],
    root: Path,
) -> None:
    if archive["sha256"] != artifact["sha256"]:
        raise AdaptationValidationError(
            f"V2 archive binding differs from frozen artifact: {artifact['path']}"
        )
    pinned = any(
        item["path"] == archive["archive_path"] and item["sha256"] == archive["sha256"]
        for item in v3["files"].values()
    )
    if not pinned:
        raise AdaptationValidationError(
            f"V2 archive is not pinned by v3: {archive['archive_path']}"
        )
    _verify_artifact(
        {"path": archive["archive_path"], "sha256": archive["sha256"]}, root
    )


def _verify_v3_lineage(
    v1: dict[str, Any], v2: dict[str, Any], v3: dict[str, Any], root: Path
) -> None:
    if v3.get("migration_from", {}).get("freeze_path") != V2_FREEZE:
        raise AdaptationValidationError(
            "V3 freeze does not identify its v2 predecessor"
        )
    if v3.get("contract_id") != v2.get("contract_id") or v3.get("issue") != v2.get(
        "issue"
    ):
        raise AdaptationValidationError(
            "V3 freeze changed the predecessor contract identity"
        )
    if v3.get("catalog_snapshot") != v2.get("catalog_snapshot"):
        raise AdaptationValidationError("V3 changed the immutable catalog snapshot")
    if v3.get("ancestors", {}).get("v1_contract_version") != v1.get("contract_version"):
        raise AdaptationValidationError("V3 freeze lost its v1 compatibility lineage")
    if v3.get("compatibility_records") != v2.get("compatibility_records"):
        raise AdaptationValidationError(
            "V3 changed historical v2 compatibility records"
        )
    _verify_v2_predecessor_hash(v2, v3, root)
    _verify_compatibility_extension_links(v2, v3)


def _verify_v2_predecessor_hash(
    v2: dict[str, Any], v3: dict[str, Any], root: Path
) -> None:
    path = resolve_repo_path(V2_FREEZE, root, require_file=True)
    digest = sha256_file(path)
    if v3.get("ancestors", {}).get("v2_freeze_sha256") != digest:
        raise AdaptationValidationError(
            "V3 freeze is not bound to the original v2 freeze"
        )
    if not any(
        item["path"] == V2_FREEZE and item["sha256"] == digest
        for item in v3["files"].values()
    ):
        raise AdaptationValidationError("V3 files do not pin the original v2 freeze")


def _verify_compatibility_extension_links(
    v2: dict[str, Any], v3: dict[str, Any]
) -> None:
    if set(v3.get("compatibility_extensions", {})) != set(v2["compatibility_records"]):
        raise AdaptationValidationError(
            "V3 must preserve one compatibility extension for every frozen record"
        )
    pinned_files = {(item["path"], item["sha256"]) for item in v3["files"].values()}
    for adaptation_id, extension in v3.get("compatibility_extensions", {}).items():
        legacy = v2["compatibility_records"].get(adaptation_id)
        if legacy is None:
            raise AdaptationValidationError(
                f"V3 extension has no v2 compatibility parent: {adaptation_id}"
            )
        if extension["source_record"] != legacy["source_record"] or extension[
            "v2_compatibility"
        ] != {"path": legacy["path"], "sha256": legacy["sha256"]}:
            raise AdaptationValidationError(
                f"V3 extension does not preserve its v2 parent: {adaptation_id}"
            )
        if (extension["path"], extension["sha256"]) not in pinned_files:
            raise AdaptationValidationError(
                f"V3 compatibility extension is not pinned: {adaptation_id}"
            )


def _read_manifest(manifest_path: str, sidecar_path: str, root: Path) -> dict[str, Any]:
    manifest_file = resolve_repo_path(manifest_path, root, require_file=True)
    sidecar_file = resolve_repo_path(sidecar_path, root, require_file=True)
    expected = sidecar_file.read_text(encoding="utf-8").split()[0]
    if sha256_file(manifest_file) != expected:
        raise AdaptationValidationError(
            f"{manifest_path} differs from its hash sidecar"
        )
    return json.loads(manifest_file.read_text(encoding="utf-8"))


def _read_freeze(manifest_path: str, sidecar_path: str, root: Path) -> dict[str, Any]:
    manifest = _read_manifest(manifest_path, sidecar_path, root)
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
