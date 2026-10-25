"""Verify inherited protected inputs and record #156 reference asset hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "godot_walk/evidence/2026-10-23-issue-156"
PROVENANCE = ROOT / "godot_walk/evidence/2026-10-22-issue-160/provenance.json"
SNAPSHOT = EVIDENCE / "catalog_snapshot.json"
REFERENCE_PATHS = (
    "godot_walk/scenes/issue149_generated_walkthrough.tscn",
    "godot_walk/scripts/issue149_generated_walkthrough.gd",
    "godot_walk/evidence/2026-10-22-issue-149/layout_seed_149.json",
    "godot_walk/evidence/2026-10-22-issue-149/layout_seed_149.svg",
    "godot_walk/scenes/issue160_assembled_walkthrough.tscn",
    "godot_walk/scripts/issue160_assembled_walkthrough.gd",
    "godot_walk/scenes/corridor_splat.tscn",
    "godot_walk/assets/corridor_splat/collision/corridor_splat.collision.glb",
    "godot_walk/assets/corridor_splat/alignment_manifest.json",
    "godot_walk/assets/corridor_splat/corridor_clean.ply",
)


def main() -> int:
    protected = _provenance_hashes()
    catalog = _catalog_hashes()
    inherited = _verify_records(protected, "#160-protected-input")
    registered = _verify_records(catalog, "catalog-generation-dependency")
    references = _current_reference_records()
    all_verified = all(record["verified"] for record in inherited + registered)
    output = {
        "issue": 156,
        "baseline_issue": 160,
        "source_manifests": [str(PROVENANCE.relative_to(ROOT)), str(SNAPSHOT.relative_to(ROOT))],
        "inherited_protected_count": len(inherited),
        "catalog_dependency_count": len(registered),
        "all_inherited_and_catalog_hashes_verified": all_verified,
        "protected_inputs": inherited,
        "catalog_dependencies": registered,
        "recorded_reference_assets": references,
        "reference_hash_note": "Reference asset hashes are recorded for this #156 bundle; only #160 provenance and catalog snapshot hashes have prior expected values verified here.",
    }
    (EVIDENCE / "protected_hashes.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        f"#156 integrity: inherited={len(inherited)}, catalog={len(registered)}, "
        f"all_verified={all_verified}, references={len(references)}"
    )
    return 0 if all_verified and all(record["exists"] for record in references) else 1


def _provenance_hashes() -> dict[str, str]:
    provenance = json.loads(PROVENANCE.read_text())
    expected = {item["path"]: item["expected_sha256"] for item in provenance["protected_inputs"]}
    for key in ("additional_references", "new_implementation_files", "candidate_asset_hashes"):
        for record in _hash_records(provenance.get(key, [])):
            prior = expected.setdefault(record["path"], record["sha256"])
            if prior != record["sha256"]:
                raise ValueError(f"Conflicting #160 hashes for {record['path']}")
    return expected


def _catalog_hashes() -> dict[str, str]:
    snapshot = json.loads(SNAPSHOT.read_text())
    return {item["path"]: item["sha256"] for item in snapshot["file_hashes"]}


def _verify_records(expected: dict[str, str], category: str) -> list[dict[str, Any]]:
    records = []
    for relative_path, digest in sorted(expected.items()):
        path = ROOT / relative_path
        actual = _sha256(path) if path.is_file() else "missing"
        records.append({
            "path": relative_path,
            "category": category,
            "expected_sha256": digest,
            "actual_sha256": actual,
            "verified": actual == digest,
        })
    return records


def _current_reference_records() -> list[dict[str, Any]]:
    records = []
    for relative_path in REFERENCE_PATHS:
        path = ROOT / relative_path
        records.append({
            "path": relative_path,
            "exists": path.is_file(),
            "sha256": _sha256(path) if path.is_file() else None,
            "category": "recorded_reference",
        })
    return records


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


if __name__ == "__main__":
    raise SystemExit(main())
