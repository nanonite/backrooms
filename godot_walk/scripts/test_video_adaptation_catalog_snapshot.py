"""Tests that historical records bind catalog snapshots, not the live catalog."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from video_adaptation_contracts import verify_versioned_freezes
from video_adaptation_errors import AdaptationValidationError


def _write(root: Path, relative: str, content: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _freeze_fixture(root: Path) -> tuple[Path, Path]:
    catalog = b'{"catalog_id":"fixture-kit","catalog_version":"1.0.0","modules":[]}\n'
    catalog_hash = _write(root, "godot_walk/room_catalog/catalog.json", catalog)
    snapshot_path = "godot_walk/room_catalog/catalog_snapshots/fixture-kit-1.0.0.json"
    _write(root, snapshot_path, catalog)
    v1_files = {}
    for name, relative in {
        "schema": "godot_walk/room_catalog/schema.json",
        "contract": "godot_walk/room_catalog/contract.md",
        "catalog": "godot_walk/room_catalog/catalog.json",
        "material_language": "godot_walk/room_catalog/material.md",
        "accepted_example": "godot_walk/room_catalog/adaptations/accepted.json",
    }.items():
        digest = (
            catalog_hash if name == "catalog" else _write(root, relative, name.encode())
        )
        v1_files[name] = {"path": relative, "sha256": digest}
    v1 = {
        "contract_version": "1.0.0",
        "files": v1_files,
        "catalog_identity": {"catalog_version": "1.0.0"},
    }
    v1_path = root / "godot_walk/room_catalog/contract_freeze_v1.json"
    v1_path.write_text(json.dumps(v1), encoding="utf-8")
    v1_hash = hashlib.sha256(v1_path.read_bytes()).hexdigest()
    _write(
        root,
        "godot_walk/room_catalog/contract_freeze_v1.sha256",
        f"{v1_hash}  freeze\n".encode(),
    )
    return v1_path, root / snapshot_path


def _write_v2_freeze(root: Path, v1_path: Path, snapshot: Path) -> Path:
    snapshot_relative = snapshot.relative_to(root).as_posix()
    files = {}
    for name, relative in {
        "schema_v2": "godot_walk/room_catalog/schema_v2.json",
        "contract_v2": "godot_walk/room_catalog/contract_v2.md",
        "snapshot": snapshot_relative,
        "legacy_freeze": "godot_walk/room_catalog/contract_freeze_v1.json",
        "legacy_sidecar": "godot_walk/room_catalog/contract_freeze_v1.sha256",
    }.items():
        digest = (
            hashlib.sha256((root / relative).read_bytes()).hexdigest()
            if (root / relative).exists()
            else _write(root, relative, name.encode())
        )
        files[name] = {"path": relative, "sha256": digest}
    document = {
        "freeze_version": 2,
        "contract_id": "godot_video_room_completion",
        "contract_version": "2.0.0",
        "issue": 165,
        "files": files,
        "catalog_snapshot": {
            "path": snapshot_relative,
            "sha256": files["snapshot"]["sha256"],
            "catalog_id": "fixture-kit",
            "catalog_version": "1.0.0",
        },
        "compatibility_records": {},
    }
    path = root / "godot_walk/room_catalog/contract_freeze_v2.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _write(
        root,
        "godot_walk/room_catalog/contract_freeze_v2.sha256",
        f"{digest}  freeze\n".encode(),
    )
    v1 = json.loads(v1_path.read_text(encoding="utf-8"))
    v2_sidecar = root / "godot_walk/room_catalog/contract_freeze_v2.sha256"
    v3_files = {name: artifact for name, artifact in files.items()}
    v3_files["v2_manifest"] = {
        "path": "godot_walk/room_catalog/contract_freeze_v2.json",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    v3_files["v2_sidecar"] = {
        "path": "godot_walk/room_catalog/contract_freeze_v2.sha256",
        "sha256": hashlib.sha256(v2_sidecar.read_bytes()).hexdigest(),
    }
    v3 = {
        "freeze_version": 3,
        "contract_id": "godot_video_room_completion",
        "contract_version": "3.0.0",
        "issue": 165,
        "migration_from": {
            "contract_version": "2.0.0",
            "freeze_path": "godot_walk/room_catalog/contract_freeze_v2.json",
        },
        "ancestors": {
            "v1_contract_version": v1["contract_version"],
            "v2_freeze_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        "files": v3_files,
        "catalog_snapshot": document["catalog_snapshot"],
        "compatibility_records": {},
        "compatibility_extensions": {},
        "archived_v2_artifacts": [],
        "calibration_flags": {
            "registration_accepted": False,
            "scale_calibrated": False,
        },
    }
    v3_path = root / "godot_walk/room_catalog/contract_freeze_v3.json"
    v3_path.write_text(json.dumps(v3), encoding="utf-8")
    v3_hash = hashlib.sha256(v3_path.read_bytes()).hexdigest()
    _write(
        root,
        "godot_walk/room_catalog/contract_freeze_v3.sha256",
        f"{v3_hash}  freeze\n".encode(),
    )
    v3_sidecar = root / "godot_walk/room_catalog/contract_freeze_v3.sha256"
    v4_files = dict(v3_files)
    v4_files["v3_manifest"] = {
        "path": "godot_walk/room_catalog/contract_freeze_v3.json",
        "sha256": v3_hash,
    }
    v4_files["v3_sidecar"] = {
        "path": "godot_walk/room_catalog/contract_freeze_v3.sha256",
        "sha256": hashlib.sha256(v3_sidecar.read_bytes()).hexdigest(),
    }
    validator_doc = "godot_walk/room_catalog/video_adaptation_validator_v4.md"
    v4_files["validator_v4_doc"] = {
        "path": validator_doc,
        "sha256": _write(root, validator_doc, b"validator successor fixture\n"),
    }
    for key, relative in {
        "active_contracts_v4": "godot_walk/scripts/video_adaptation_contracts.py",
        "active_resource_graph_v4": "godot_walk/scripts/video_adaptation_resource_graph.py",
    }.items():
        v4_files[key] = {
            "path": relative,
            "sha256": _write(root, relative, f"{key}\n".encode()),
        }
    v4 = {
        "freeze_version": 4,
        "validator_version": "4.0.0",
        "contract_id": v3["contract_id"],
        "contract_version": v3["contract_version"],
        "issue": v3["issue"],
        "migration_from": {
            "validator_version": "3.0.0",
            "freeze_path": "godot_walk/room_catalog/contract_freeze_v3.json",
        },
        "ancestors": {
            "v3_freeze_sha256": v3_hash,
        },
        "files": v4_files,
        "catalog_snapshot": v3["catalog_snapshot"],
        "compatibility_records": v3["compatibility_records"],
        "compatibility_extensions": v3["compatibility_extensions"],
        "archived_v2_artifacts": v3["archived_v2_artifacts"],
        "archived_v3_artifacts": [],
        "calibration_flags": v3["calibration_flags"],
    }
    v4_path = root / "godot_walk/room_catalog/contract_freeze_v4.json"
    v4_path.write_text(json.dumps(v4), encoding="utf-8")
    v4_hash = hashlib.sha256(v4_path.read_bytes()).hexdigest()
    _write(
        root,
        "godot_walk/room_catalog/contract_freeze_v4.sha256",
        f"{v4_hash}  freeze\n".encode(),
    )
    return path


class CatalogSnapshotTests(unittest.TestCase):
    def test_live_catalog_growth_is_ignored_but_snapshot_tampering_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, snapshot = _freeze_fixture(root)
            _write_v2_freeze(
                root, root / "godot_walk/room_catalog/contract_freeze_v1.json", snapshot
            )
            live_catalog = root / "godot_walk/room_catalog/catalog.json"
            live = json.loads(live_catalog.read_text(encoding="utf-8"))
            live["modules"].append({"id": "unrelated-room", "version": 1})
            live_catalog.write_text(json.dumps(live), encoding="utf-8")
            verify_versioned_freezes(root)
            snapshot.write_text('{"tampered":true}', encoding="utf-8")
            with self.assertRaisesRegex(AdaptationValidationError, "hash mismatch"):
                verify_versioned_freezes(root)


if __name__ == "__main__":
    unittest.main()
