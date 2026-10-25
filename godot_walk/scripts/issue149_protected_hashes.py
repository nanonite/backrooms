"""Verify and record the issue #160 inputs protected by #149."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def write_protected_hashes(root: Path, evidence: Path, provenance_path: Path) -> None:
    provenance = json.loads(provenance_path.read_text())
    expected = {item["path"]: item["expected_sha256"] for item in provenance["protected_inputs"]}
    for key in ("additional_references", "new_implementation_files", "candidate_asset_hashes"):
        for item in _hash_records(provenance[key]):
            prior = expected.setdefault(item["path"], item["sha256"])
            if prior != item["sha256"]:
                raise ValueError(f"Conflicting #160 provenance hashes for {item['path']}")
    records = [_record(root, path, checksum) for path, checksum in sorted(expected.items())]
    mismatches = [item["path"] for item in records if not item["verified"]]
    if mismatches:
        raise ValueError("Protected #160 hash mismatch: " + ", ".join(mismatches))
    output = {
        "issue": 149,
        "baseline_issue": 160,
        "source_manifest": str(provenance_path.relative_to(root)),
        "verified_count": len(records),
        "all_verified": True,
        "assets": records,
    }
    (evidence / "protected_hashes.json").write_text(json.dumps(output, indent=2) + "\n")


def _record(root: Path, relative_path: str, expected: str) -> dict[str, Any]:
    path = root / relative_path
    actual = _sha256(path) if path.is_file() else "missing"
    return {"path": relative_path, "expected_sha256": expected, "actual_sha256": actual,
            "verified": actual == expected}


def _hash_records(value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict):
        own = []
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            own.append({"path": value["path"], "sha256": value["sha256"]})
        return own + [record for child in value.values() for record in _hash_records(child)]
    if isinstance(value, list):
        return [record for item in value for record in _hash_records(item)]
    return []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
