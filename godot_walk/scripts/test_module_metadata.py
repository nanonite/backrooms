"""Tests for generated module metadata v1 records (issue 229)."""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_metadata as metadata
from deterministic_json import ROOT, canonical_bytes, sha256_file


def _eleven_test_inputs(item: dict) -> list[dict]:
    return [item] + [{**item, "module_id": f"test_module_{index}"} for index in range(10)]


def test_committed_records_are_deterministic_and_validate() -> None:
    paths = metadata.record_paths(ROOT)
    before = {path: path.read_bytes() for path in paths}
    assert len(paths) == 11
    assert metadata.generate(ROOT) == []
    assert {path: path.read_bytes() for path in paths} == before
    assert metadata.validate_repository(ROOT) == []


def test_generation_refuses_to_change_a_locked_value(tmp_path: Path, monkeypatch) -> None:
    item = metadata._module_inputs(ROOT)[0]
    record = metadata._build(item, ROOT)
    lock_name = "surfaces.surfaces.floor.material_id"
    assert lock_name in record["locks"]
    target = metadata._output_path(item, tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(canonical_bytes(record))
    changed = copy.deepcopy(record)
    changed["surfaces"]["surfaces"]["floor"]["material_id"] = "edited-under-lock"
    target.write_bytes(canonical_bytes(changed))
    monkeypatch.setattr(metadata, "_module_inputs", lambda _root: _eleven_test_inputs(item))
    monkeypatch.setattr(metadata, "_build", lambda _item, _root: record)
    errors = metadata.generate(tmp_path)
    assert any("saved locked record value was edited" in error for error in errors)
    assert target.read_bytes() == canonical_bytes(changed)


def test_invalidated_acoustics_approval_fails_as_a_locked_input(tmp_path: Path, monkeypatch) -> None:
    item = metadata._module_inputs(ROOT)[0]
    record = metadata._build(item, ROOT)
    target = metadata._output_path(item, tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(canonical_bytes(record))
    monkeypatch.setattr(metadata, "_approval", lambda *_args: None)
    candidate = metadata._build(item, ROOT)
    monkeypatch.setattr(metadata, "_module_inputs", lambda _root: _eleven_test_inputs(item))
    monkeypatch.setattr(metadata, "_build", lambda _item, _root: candidate)
    errors = metadata.generate(tmp_path)
    assert any("locked input changed or lost approval" in error for error in errors)


def test_palette_change_does_not_remove_material_lock_approval(tmp_path: Path) -> None:
    item = metadata._module_inputs(ROOT)[0]
    descriptor_relative = item["descriptor"].relative_to(ROOT)
    descriptor_target = tmp_path / descriptor_relative
    descriptor_target.parent.mkdir(parents=True)
    shutil.copyfile(item["descriptor"], descriptor_target)
    for relative in (metadata.CATALOG / "module_surface_palette_mapping_v0.1.0.md",
                     metadata.receipts.RECEIPT_DIR / "issue-217.json"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    descriptor = json.loads(descriptor_target.read_text(encoding="utf-8"))
    descriptor["surfaces"]["floor"]["palette_id"] = None
    descriptor_target.write_text(json.dumps(descriptor), encoding="utf-8")
    assert metadata._mapping_material_approval(
        descriptor_relative.as_posix(), tmp_path
    ) is not None


def test_validator_reports_stale_input_hash_without_raising(tmp_path: Path) -> None:
    input_path = tmp_path / "layer.json"
    input_path.write_text("{}\n", encoding="utf-8")
    record_path = tmp_path / "module.json"
    reference = {"path": "layer.json", "sha256": sha256_file(input_path)}
    record = {
        "source_layers": {name: reference for name in ("profile", "descriptor", "t6", "poetics", "acoustics")},
        "inputs": {name: reference for name in ("profile", "descriptor", "t6", "poetics", "acoustics")},
        "approval_refs": {},
        "poetics_ref": reference,
    }
    record["inputs"]["approval_refs"] = {}
    data = canonical_bytes(record)
    record_path.write_bytes(data)
    record_path.with_suffix(".json.sha256").write_text(
        __import__("hashlib").sha256(data).hexdigest() + "\n", encoding="ascii")
    input_path.write_text("{\"changed\": true}\n", encoding="utf-8")
    assert any("stale input hash: layer.json" in error
               for error in metadata.validate_record(record, tmp_path, record_path))


def test_validator_requires_all_source_references_and_never_raises_on_bad_inputs() -> None:
    record = json.loads(metadata.record_paths(ROOT)[0].read_text(encoding="utf-8"))
    record["inputs"].pop("descriptor")
    errors = metadata.validate_record(record, ROOT)
    assert any("inputs omits or differs from source_layers.descriptor" in error for error in errors)
    assert metadata.validate_record({"inputs": None}, ROOT)


def test_repository_coverage_detects_duplicate_and_missing_module_ids(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps({"module_id": "module_a"}), encoding="utf-8")
    second.write_text(json.dumps({"module_id": "module_a"}), encoding="utf-8")
    expected = {"module_a": first, "module_b": second}
    errors = metadata._record_coverage_errors([first, second], expected, tmp_path)
    assert any("duplicate module record for module_a" in error for error in errors)
    assert any("missing record for admitted module module_b" in error for error in errors)


def test_section_and_locked_values_are_checked_against_sources() -> None:
    path = metadata.record_paths(ROOT)[0]
    record = json.loads(path.read_text(encoding="utf-8"))
    record["profile"]["shape"]["area_m2"] = -1
    record["surfaces"]["surfaces"]["floor"]["material_id"] = "edited-material"
    errors = metadata.validate_record(record, ROOT)
    assert any("profile differs from its source layer" in error for error in errors)
    assert any("locks." in error and "record value differs" in error for error in errors)


def test_mapping_table_hash_is_an_input_for_material_locks() -> None:
    record = json.loads(metadata.record_paths(ROOT)[0].read_text(encoding="utf-8"))
    assert record["inputs"]["mapping_table"] == metadata._mapping_table_ref(ROOT)
    assert metadata._validate_record(record, ROOT, None) == []


def test_source_level_overlay_is_referenced_without_embedding() -> None:
    item = metadata._module_inputs(ROOT)[-1].copy()
    item["overlay"] = ROOT / "godot_walk/source_library/sources/picture-set-d160eaa3cc847d5c/source_lighting_scale_v1.json"
    record = metadata._build(item, ROOT)
    assert record["lighting_scale"]["state"] == "source_overlay"
    assert "overlay" not in record["lighting_scale"]
    assert record["lighting_scale"]["overlay_ref"] == record["source_layers"]["lighting_scale"]
    assert "lighting_scale.source_overlay" in record["locks"]


def test_palette_validation_accepts_null_and_rejects_unknown_palette() -> None:
    record = json.loads(metadata.record_paths(ROOT)[0].read_text(encoding="utf-8"))
    record["surfaces"]["surfaces"]["floor"]["palette_id"] = None
    assert metadata._palette_errors(record, ROOT) == []
    record["surfaces"]["surfaces"]["floor"]["palette_id"] = "missing_palette"
    assert any("not in palettes-0.3.0.json" in error
               for error in metadata._palette_errors(record, ROOT))


def test_records_carry_layer_values_verbatim_and_acoustic_provenance_per_field() -> None:
    for path in metadata.record_paths(ROOT):
        record = json.loads(path.read_text(encoding="utf-8"))
        layers = record["source_layers"]
        profile = json.loads((ROOT / layers["profile"]["path"]).read_text(encoding="utf-8"))
        descriptor = json.loads((ROOT / layers["descriptor"]["path"]).read_text(encoding="utf-8"))
        t6 = json.loads((ROOT / layers["t6"]["path"]).read_text(encoding="utf-8"))
        assert record["profile"] == profile
        assert record["surfaces"] == descriptor
        assert record["t6"] == t6
        assert record["space_kind"] == "enclosed"
        assert record["registration_accepted"] is False
        assert record["scale_calibrated"] is False
        assert record["acoustics"]["committed_block"]["probe"]["provenance"] == "measured"
        for name, field in record["acoustics"]["fields"].items():
            expected = "measured" if name in metadata.MEASURED_FIELDS else "derived"
            assert field["provenance"]["kind"] == expected
            assert field["committed_block_label"] == "measured"
        assert metadata.CEILING_LIMITATION in record["acoustics"]["fields"]["ceiling_height_m"]["provenance"]["limitation"]


def test_record_detached_pins_match_exact_record_bytes() -> None:
    for path in metadata.record_paths(ROOT):
        pin = path.with_suffix(path.suffix + ".sha256")
        import hashlib

        assert pin.read_text(encoding="ascii").strip() == hashlib.sha256(path.read_bytes()).hexdigest()

