"""Validate a serialized #149 layout against the current immutable room catalog."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from issue149_layout_core import ROOT, canonical_json, validate_layout

DEFAULT_LAYOUT = ROOT / "godot_walk/evidence/2026-10-22-issue-149/layout_seed_149.json"


def validate_bundle(layout_path: Path) -> tuple[dict, list[str]]:
    layout_bytes = layout_path.read_bytes()
    layout = json.loads(layout_bytes)
    errors = _validate_layout_digest(layout)
    errors.extend(_validate_layout_file_digest(layout_path, layout_bytes))
    snapshot_path = _snapshot_path(layout)
    if snapshot_path is None:
        return layout, errors + ["layout catalog snapshot path is invalid"]
    if not snapshot_path.is_file():
        return layout, errors + ["catalog snapshot is missing"]
    snapshot_bytes = snapshot_path.read_bytes()
    catalog_hash = hashlib.sha256(snapshot_bytes).hexdigest()
    if layout.get("catalog_sha256") != catalog_hash:
        errors.append("layout catalog hash does not match its immutable snapshot")
    try:
        snapshot = json.loads(snapshot_bytes)
    except json.JSONDecodeError as error:
        return layout, errors + [f"catalog snapshot is invalid: {error}"]
    errors.extend(_validate_runtime_dependencies(snapshot))
    errors.extend(validate_layout(layout, snapshot))
    errors.extend(_validate_shape(layout))
    return layout, errors


def _snapshot_path(layout: dict) -> Path | None:
    resource = layout.get("catalog_snapshot_path", "")
    if not isinstance(resource, str) or not resource.startswith("res://evidence/"):
        return None
    project = ROOT / "godot_walk"
    path = (project / resource.removeprefix("res://")).resolve()
    try:
        path.relative_to(project.resolve())
    except ValueError:
        return None
    return path


def _validate_runtime_dependencies(snapshot: dict) -> list[str]:
    errors = []
    for dependency in snapshot.get("runtime_dependencies", []):
        relative_path = dependency.get("path", "")
        path = (ROOT / relative_path).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError:
            errors.append("runtime dependency path escapes the repository: " + relative_path)
            continue
        if not path.is_file():
            errors.append("runtime dependency is missing: " + relative_path)
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != dependency.get("sha256"):
            errors.append("runtime dependency hash mismatch: " + relative_path)
    return errors


def _validate_layout_digest(layout: dict) -> list[str]:
    expected = layout.get("layout_sha256", "")
    payload = copy.deepcopy(layout)
    payload.pop("layout_sha256", None)
    actual = hashlib.sha256(canonical_json(payload)).hexdigest()
    return [] if actual == expected else ["canonical layout payload hash mismatch"]


def _validate_layout_file_digest(layout_path: Path, content: bytes) -> list[str]:
    sidecar = layout_path.with_suffix(layout_path.suffix + ".sha256")
    if not sidecar.is_file():
        return ["serialized layout SHA-256 sidecar is missing"]
    expected = sidecar.read_text().split()[0]
    actual = hashlib.sha256(content).hexdigest()
    return [] if actual == expected else ["serialized layout file hash mismatch"]


def _validate_shape(layout: dict) -> list[str]:
    required = {
        "schema_version", "layout_id", "generator_version", "catalog_id",
        "catalog_version", "catalog_sha256", "catalog_snapshot_path", "seed",
        "settings", "topology", "placements", "connections", "layout_sha256",
    }
    errors = ["layout is missing required fields: " + ", ".join(sorted(required - layout.keys()))]
    if required.issubset(layout):
        errors.clear()
    if layout.get("operator_status") != "review_pending":
        errors.append("generated candidate must remain pending operator review")
    if layout.get("registration_accepted") or layout.get("scale_calibrated"):
        errors.append("registration and scale flags must remain false")
    if len(layout.get("placements", [])) != layout.get("settings", {}).get("placement_count"):
        errors.append("placement count differs from settings")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    arguments = parser.parse_args()
    layout, errors = validate_bundle(arguments.layout)
    if errors:
        for error in errors:
            print("INVALID: " + error)
        return 1
    print(
        f"validated {layout['layout_id']}: {len(layout['placements'])} modules, "
        f"{len(layout['connections'])} connections, operator_status={layout['operator_status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
