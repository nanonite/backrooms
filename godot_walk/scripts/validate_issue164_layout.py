"""Validate #164 layout, snapshot, catalog dependencies, and serialized hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from issue149_layout_core import ROOT, canonical_json
from issue164_layout import LAYOUT_ID, validate_chain_layout
from jsonschema import Draft202012Validator

EVIDENCE = ROOT / "godot_walk/evidence/2026-10-24-issue-164"
LAYOUT_PATH = EVIDENCE / "layout_three_room.json"
SCHEMA_PATH = ROOT / "godot_walk/design_rounds/issue164_layout.schema.json"


def validate_bundle(layout_path: Path = LAYOUT_PATH) -> list[str]:
    try:
        layout_bytes = layout_path.read_bytes()
        layout = json.loads(layout_bytes)
    except (OSError, json.JSONDecodeError) as error:
        return [f"Cannot read layout: {error}"]
    errors = _validate_layout_schema(layout)
    errors.extend(_validate_layout_hash(layout, layout_bytes, layout_path))
    snapshot_path = _snapshot_path(layout)
    if snapshot_path is None:
        return errors + ["Catalog snapshot path is invalid"]
    try:
        snapshot_bytes = snapshot_path.read_bytes()
        snapshot = json.loads(snapshot_bytes)
    except (OSError, json.JSONDecodeError) as error:
        return errors + [f"Cannot read catalog snapshot: {error}"]
    if hashlib.sha256(snapshot_bytes).hexdigest() != layout.get("catalog_sha256"):
        errors.append("Catalog snapshot SHA-256 differs from layout")
    errors.extend(_validate_snapshot_files(snapshot))
    errors.extend(validate_chain_layout(layout, snapshot))
    if layout.get("layout_id") != LAYOUT_ID:
        errors.append("Unexpected layout ID")
    if {item["module_id"] for item in layout.get("placements", [])} != {
        "godot_later_bay_column_bounded_v1",
        "godot_early_pocket_pass_through_v1",
        "godot_source_textured_large_room_hall_end_v1",
    }:
        errors.append("Layout must contain all three distinct room designs")
    return errors


def _validate_layout_schema(layout: dict[str, Any]) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return [error.message for error in Draft202012Validator(schema).iter_errors(layout)]


def _validate_layout_hash(
    layout: dict[str, Any], content: bytes, layout_path: Path
) -> list[str]:
    payload = dict(layout)
    payload.pop("layout_sha256", None)
    if hashlib.sha256(canonical_json(payload)).hexdigest() != layout.get(
        "layout_sha256"
    ):
        return ["Canonical layout hash does not match"]
    sidecar = _validate_sidecar(content, layout_path)
    return sidecar


def _validate_sidecar(content: bytes, layout_path: Path) -> list[str]:
    path = layout_path.with_suffix(layout_path.suffix + ".sha256")
    if not path.is_file():
        return ["Serialized layout hash sidecar is missing"]
    if (
        path.read_text(encoding="utf-8").split()[0]
        != hashlib.sha256(content).hexdigest()
    ):
        return ["Serialized layout hash sidecar does not match"]
    return []


def _snapshot_path(layout: dict[str, Any]) -> Path | None:
    resource = layout.get("catalog_snapshot_path")
    if not isinstance(resource, str) or not resource.startswith("res://evidence/"):
        return None
    project = ROOT / "godot_walk"
    path = (project / resource.removeprefix("res://")).resolve()
    try:
        path.relative_to(project.resolve())
        return path
    except ValueError:
        return None


def _validate_snapshot_files(snapshot: dict[str, Any]) -> list[str]:
    errors = []
    for dependency in snapshot.get("file_hashes", []):
        path = (ROOT / dependency["path"]).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError:
            errors.append("Catalog file path escapes repository: " + dependency["path"])
            continue
        if not path.is_file():
            errors.append("Catalog dependency is missing: " + dependency["path"])
        elif _sha256(path) != dependency["sha256"]:
            errors.append("Catalog dependency hash mismatch: " + dependency["path"])
    return errors


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", type=Path, default=LAYOUT_PATH)
    args = parser.parse_args()
    errors = validate_bundle(args.layout)
    if errors:
        for error in errors:
            print("INVALID: " + error)
        return 1
    print(
        "ISSUE164_LAYOUT_BUNDLE_VALID: 3 distinct modules, 2 connections, review_pending"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
