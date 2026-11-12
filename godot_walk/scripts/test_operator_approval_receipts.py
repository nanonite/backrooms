"""Tests for committed operator approval receipts (issue 228)."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import operator_approval_receipts as receipts
import template_validate as tv
from deterministic_json import ROOT

RECEIPT_PATH = ROOT / "godot_walk/room_catalog/operator_approval_receipts/issue-216.json"
MAPPING_RECEIPT_PATH = ROOT / "godot_walk/room_catalog/operator_approval_receipts/issue-217.json"
LAYER_PATH = ROOT / "godot_walk/room_catalog/module_acoustics_v0.2.0.json"
MAPPING_PATH = ROOT / "godot_walk/room_catalog/module_surface_palette_mapping_v0.1.0.md"


def _test_repository(tmp_path: Path) -> tuple[Path, Path]:
    schema_path = tmp_path / receipts.RECEIPT_SCHEMA
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / receipts.RECEIPT_SCHEMA, schema_path)
    layer_path = tmp_path / LAYER_PATH.relative_to(ROOT)
    layer_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(LAYER_PATH, layer_path)
    receipt_path = tmp_path / receipts.RECEIPT_DIR / "issue-216.json"
    receipt_path.parent.mkdir(parents=True)
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    receipt["scope"] = [receipt["scope"][0]]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt_path, layer_path


def _refresh_hash(receipt_path: Path, layer_path: Path) -> dict[str, Any]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["scope"][0]["sha256"] = hashlib.sha256(layer_path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt


def _markdown_test_repository(tmp_path: Path) -> tuple[Path, Path]:
    schema_path = tmp_path / receipts.RECEIPT_SCHEMA
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / receipts.RECEIPT_SCHEMA, schema_path)
    mapping_path = tmp_path / MAPPING_PATH.relative_to(ROOT)
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(MAPPING_PATH, mapping_path)
    receipt_path = tmp_path / receipts.RECEIPT_DIR / "issue-217.json"
    receipt_path.parent.mkdir(parents=True)
    receipt = json.loads(MAPPING_RECEIPT_PATH.read_text(encoding="utf-8"))
    receipt["scope"] = [next(item for item in receipt["scope"] if item["path"].endswith(".md"))]
    for record in receipt["scope"][0]["derived_from"]["files"]:
        source = ROOT / record["path"]
        target = tmp_path / record["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt_path, mapping_path


def test_committed_receipts_validate_and_are_wired_into_template_validation() -> None:
    assert receipts.validate_receipts() == []
    assert receipts.operator_approval_for_field(
        LAYER_PATH.relative_to(ROOT).as_posix(),
        "/modules/godot_early_pocket_pass_through_v1@1/acoustic",
    ) is not None
    report = tv.validate_repository(ROOT)
    assert not any("operator_approval_receipts" in error for error in report.errors)


def test_issue_217_receipt_is_limited_to_approved_mapping_table() -> None:
    receipt = json.loads(MAPPING_RECEIPT_PATH.read_text(encoding="utf-8"))
    assert [item["path"] for item in receipt["scope"]] == [
        MAPPING_PATH.relative_to(ROOT).as_posix()
    ]
    approval = receipts.operator_approval_for_field(
        "godot_walk/room_catalog/module_surface_palettes/godot_early_pocket_pass_through_v1-v1_surface_palette_v1.json",
        "/surfaces/wall/material_id",
    )
    assert approval is not None
    assert approval["approval_via"] == "approved mapping table"


def test_issue_217_derivation_approves_descriptor_material_and_palette_fields() -> None:
    descriptor = next(
        record["path"]
        for record in json.loads(MAPPING_RECEIPT_PATH.read_text(encoding="utf-8"))["scope"][0]["derived_from"]["files"]
        if "godot_early_pocket_pass_through" in record["path"]
    )
    for field in ("/surfaces/wall/material_id", "/surfaces/floor/palette_id"):
        approval = receipts.operator_approval_for_field(descriptor, field)
        assert approval is not None
        assert approval["approval_via"] == "approved mapping table"


def test_derived_mapping_rejects_descriptor_hash_drift(tmp_path: Path) -> None:
    receipt_path, _ = _markdown_test_repository(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    descriptor_path = tmp_path / receipt["scope"][0]["derived_from"]["files"][0]["path"]
    descriptor_path.write_text(descriptor_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    errors = receipts.validate_receipt(receipt_path, tmp_path)
    assert any("derived file hash mismatch" in error for error in errors)


def test_valid_receipt_resolves_file_hash_and_scoped_fields(tmp_path: Path) -> None:
    receipt_path, _ = _test_repository(tmp_path)
    assert receipts.validate_receipt(receipt_path, tmp_path) == []


def test_hash_drift_is_rejected(tmp_path: Path) -> None:
    receipt_path, layer_path = _test_repository(tmp_path)
    layer_path.write_text(layer_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    errors = receipts.validate_receipt(receipt_path, tmp_path)
    assert any("sha256 mismatch" in error for error in errors)


def test_missing_scope_field_is_rejected(tmp_path: Path) -> None:
    receipt_path, _ = _test_repository(tmp_path)
    receipt = _refresh_hash(receipt_path, tmp_path / LAYER_PATH.relative_to(ROOT))
    receipt["scope"][0]["fields"] = ["/modules/*/not_a_field"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    errors = receipts.validate_receipt(receipt_path, tmp_path)
    assert any("scoped field does not exist" in error for error in errors)


def test_wildcard_scope_requires_field_in_every_matched_branch(tmp_path: Path) -> None:
    receipt_path, layer_path = _test_repository(tmp_path)
    layer = json.loads(layer_path.read_text(encoding="utf-8"))
    first_module = next(iter(layer["modules"].values()))
    del first_module["acoustic"]
    layer_path.write_text(json.dumps(layer), encoding="utf-8")
    receipt = _refresh_hash(receipt_path, layer_path)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    errors = receipts.validate_receipt(receipt_path, tmp_path)
    assert any("scoped field does not exist: /modules/*/acoustic" in error for error in errors)


def test_markdown_hash_drift_is_rejected(tmp_path: Path) -> None:
    receipt_path, mapping_path = _markdown_test_repository(tmp_path)
    relative_mapping_path = MAPPING_PATH.relative_to(ROOT).as_posix()
    assert receipts.operator_approval_for_field(
        relative_mapping_path, "/table/Material ID", root=tmp_path
    ) is not None
    mapping_path.write_text(mapping_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    errors = receipts.validate_receipt(receipt_path, tmp_path)
    assert any("sha256 mismatch" in error for error in errors)
    assert receipts.operator_approval_for_field(
        relative_mapping_path, "/table/Material ID", root=tmp_path
    ) is None


def test_consumer_lookup_rejects_nonexistent_concrete_fields() -> None:
    file_path = LAYER_PATH.relative_to(ROOT).as_posix()
    assert receipts.operator_approval_for_field(
        file_path, "/modules/nonexistent/acoustic"
    ) is None
    assert receipts.operator_approval_for_field(
        file_path, "/modules/godot_early_pocket_pass_through_v1@1/nonexistent"
    ) is None


def test_consumer_lookup_handles_descendants_ancestors_siblings_and_wildcards() -> None:
    overlay_path = "godot_walk/room_catalog/module_profiles/godot_early_pocket_pass_through_v1-v1-lighting-scale-v1.json"
    assert receipts.operator_approval_for_field(
        overlay_path, "/lighting/fixture_layout/0/kind"
    ) is not None
    assert receipts.operator_approval_for_field(
        overlay_path, "/lighting/fixture_layout/0/count"
    ) is not None
    assert receipts.operator_approval_for_field(overlay_path, "/lighting") is None
    assert receipts.operator_approval_for_field(
        overlay_path, "/lighting/colour_temperature_k"
    ) is None
    assert receipts.operator_approval_for_field(
        overlay_path, "/lighting/colour_temperature_k/review_status"
    ) is None
    assert receipts.operator_approval_for_field(
        overlay_path, "/lighting/fixture_layout/0/unsupported"
    ) is None
    assert receipts.operator_approval_for_field(
        overlay_path, "/lighting/fixture_layout/*/kind"
    ) is None
    acoustics_path = LAYER_PATH.relative_to(ROOT).as_posix()
    assert receipts.operator_approval_for_field(
        acoustics_path, "/modules/godot_early_pocket_pass_through_v1@1/acoustic"
    ) is not None


def test_unknown_issue_is_rejected(tmp_path: Path) -> None:
    receipt_path, _ = _test_repository(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["issue_id"] = 999
    receipt["source"]["issue_id"] = 999
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert receipts.validate_receipt(receipt_path, tmp_path)


def test_lighting_scale_receipt_does_not_approve_or_calibrate_status_fields() -> None:
    receipt = json.loads(
        (ROOT / receipts.RECEIPT_DIR / "issue-218.json").read_text(encoding="utf-8")
    )
    scoped_fields = [field for item in receipt["scope"] for field in item["fields"]]
    assert all("status" not in field for field in scoped_fields)
    assert receipts.operator_approval_for_field(
        "godot_walk/room_catalog/module_profiles/godot_early_pocket_pass_through_v1-v1-lighting-scale-v1.json",
        "/scale/status",
    ) is None
    example_paths = [item["path"] for item in receipt["scope"]]
    for relative_path in example_paths:
        overlay = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
        assert overlay["scale"]["status"] == "uncalibrated"
        assert overlay["scale"]["anchor"]["status"] == "estimated"
        assert overlay["scale"]["anchor"]["measurement"] is None
