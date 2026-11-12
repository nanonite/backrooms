"""Tests for generated module metadata v1 records (issue 229)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_metadata as metadata
from deterministic_json import ROOT, canonical_bytes, sha256_file


def _eleven_test_inputs(item: dict) -> list[dict]:
    return [item] + [
        {**item, "module_id": f"test_module_{index}"} for index in range(10)
    ]


def test_committed_records_are_deterministic_and_validate() -> None:
    paths = metadata.record_paths(ROOT)
    before = {path: path.read_bytes() for path in paths}
    assert len(paths) == 11
    assert metadata.generate(ROOT) == []
    assert {path: path.read_bytes() for path in paths} == before
    assert metadata.validate_repository(ROOT) == []


def test_generation_refuses_to_change_a_locked_value(
    tmp_path: Path, monkeypatch
) -> None:
    item = metadata._module_inputs(ROOT)[0]
    record = metadata._build(item, ROOT)
    lock_name = "descriptor:/surfaces/floor/material_id"
    assert lock_name in record["locks"]
    target = metadata._output_path(item, tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(canonical_bytes(record))
    changed = copy.deepcopy(record)
    changed["surfaces"]["surfaces"]["floor"]["material_id"] = "edited-under-lock"
    target.write_bytes(canonical_bytes(changed))
    monkeypatch.setattr(
        metadata, "_module_inputs", lambda _root: _eleven_test_inputs(item)
    )
    monkeypatch.setattr(metadata, "_build", lambda _item, _root: record)
    errors = metadata.generate(tmp_path)
    assert any("saved locked record value was edited" in error for error in errors)
    assert target.read_bytes() == canonical_bytes(changed)


def test_generation_refuses_removed_lock_with_changed_value(
    tmp_path: Path, monkeypatch
) -> None:
    item = metadata._module_inputs(ROOT)[0]
    record = metadata._build(item, ROOT)
    target = metadata._output_path(item, tmp_path)
    target.parent.mkdir(parents=True)
    saved = copy.deepcopy(record)
    name = "descriptor:/surfaces/floor/material_id"
    del saved["locks"][name]
    saved["surfaces"]["surfaces"]["floor"]["material_id"] = "edited-with-lock-removed"
    target.write_bytes(canonical_bytes(saved))
    monkeypatch.setattr(
        metadata, "_module_inputs", lambda _root: _eleven_test_inputs(item)
    )
    monkeypatch.setattr(metadata, "_build", lambda _item, _root: record)
    errors = metadata.generate(tmp_path)
    assert any(
        f"saved record is missing approved lock {name}" in error for error in errors
    )
    assert target.read_bytes() == canonical_bytes(saved)


def test_generation_protects_both_acoustic_value_copies(
    tmp_path: Path, monkeypatch
) -> None:
    item = metadata._module_inputs(ROOT)[0]
    record = metadata._build(item, ROOT)
    name = f"acoustics:/modules/{item['acoustic_key']}/probe/mean_distance_m"
    assert record["locks"][name]["record_value_paths"] == [
        "acoustics.fields.mean_distance_m.value",
        "acoustics.committed_block.probe.mean_distance_m",
    ]
    target = metadata._output_path(item, tmp_path)
    target.parent.mkdir(parents=True)
    saved = copy.deepcopy(record)
    saved["acoustics"]["committed_block"]["probe"]["mean_distance_m"] += 1
    target.write_bytes(canonical_bytes(saved))
    monkeypatch.setattr(
        metadata, "_module_inputs", lambda _root: _eleven_test_inputs(item)
    )
    monkeypatch.setattr(metadata, "_build", lambda _item, _root: record)
    errors = metadata.generate(tmp_path)
    assert any("committed_block.probe.mean_distance_m" in error for error in errors)
    assert target.read_bytes() == canonical_bytes(saved)


def test_palette_only_layer_change_does_not_lose_material_locks(monkeypatch) -> None:
    item = metadata._module_inputs(ROOT)[0]
    descriptor_path = item["descriptor"]
    original_load = metadata._load

    def load_with_palette_change(path):
        document = original_load(path)
        if Path(path) == descriptor_path:
            document = copy.deepcopy(document)
            document["surfaces"]["floor"]["palette_id"] = None
        return document

    monkeypatch.setattr(metadata, "_load", load_with_palette_change)
    generated = metadata._build(item, ROOT)
    assert generated["surfaces"]["surfaces"]["floor"]["palette_id"] is None
    assert "descriptor:/surfaces/floor/material_id" in generated["locks"]
    assert not any(
        lock["source_field"].endswith("/palette_id")
        for lock in generated["locks"].values()
    )


def test_record_and_candidate_input_edits_are_rejected_in_each_locked_section() -> None:
    record = metadata._build(metadata._module_inputs(ROOT)[0], ROOT)
    for section in ("descriptor", "t6", "acoustics", "lighting_scale"):
        name = next(key for key in record["locks"] if key.startswith(f"{section}:"))
        saved_lock = record["locks"][name]
        paths = saved_lock.get("record_value_paths", [saved_lock["record_value_path"]])
        edited_record = copy.deepcopy(record)
        _set_path(edited_record, paths[0], "edited-record-value")
        errors = metadata._locked_value_errors(
            edited_record, record, Path("module.json")
        )
        assert any(
            "saved locked record value was edited" in error and name in error
            for error in errors
        )

        changed_input = copy.deepcopy(record)
        changed_input["locks"][name]["value"] = "changed-layer-input"
        for record_path in paths:
            _set_path(changed_input, record_path, "changed-layer-input")
        errors = metadata._locked_value_errors(
            record, changed_input, Path("module.json")
        )
        assert any(
            "locked input changed underneath" in error and name in error
            for error in errors
        )


def test_generation_rejects_edited_layer_files_for_each_locked_section(
    tmp_path: Path, monkeypatch
) -> None:
    item = metadata._module_inputs(ROOT)[0]
    saved = metadata._build(item, ROOT)
    target = metadata._output_path(item, tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(canonical_bytes(saved))
    monkeypatch.setattr(
        metadata, "_module_inputs", lambda _root: _eleven_test_inputs(item)
    )

    for section in ("descriptor", "t6", "acoustics", "lighting_scale"):
        name = next(key for key in saved["locks"] if key.startswith(f"{section}:"))
        lock = saved["locks"][name]
        source_path = lock["source_path"]
        layer_copy = tmp_path / source_path
        layer_copy.parent.mkdir(parents=True, exist_ok=True)
        layer_copy.write_bytes((ROOT / source_path).read_bytes())
        source_document = json.loads(layer_copy.read_text(encoding="utf-8"))
        old_value = metadata._pointer(source_document, lock["source_field"])
        new_value = (
            old_value + 1
            if isinstance(old_value, (int, float))
            else f"{old_value}-changed"
        )
        _set_path(source_document, lock["source_field"], new_value)
        layer_copy.write_text(json.dumps(source_document), encoding="utf-8")

        candidate = copy.deepcopy(saved)
        candidate_lock = candidate["locks"][name]
        candidate_lock["value"] = new_value
        for record_path in candidate_lock.get(
            "record_value_paths", [candidate_lock["record_value_path"]]
        ):
            _set_path(candidate, record_path, new_value)
        reference_name = section
        candidate["source_layers"][reference_name]["sha256"] = sha256_file(layer_copy)
        candidate["inputs"][reference_name]["sha256"] = sha256_file(layer_copy)
        monkeypatch.setattr(
            metadata, "_build", lambda _item, _root, value=candidate: value
        )
        errors = metadata.generate(tmp_path)
        assert any(
            "locked input changed underneath" in error and name in error
            for error in errors
        )
        assert target.read_bytes() == canonical_bytes(saved)


def _set_path(document: dict, path: str, value: object) -> None:
    parts = path.strip("/").replace("/", ".").split(".")
    target = document
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if isinstance(target, list):
        target[int(parts[-1])] = value
    else:
        target[parts[-1]] = value


def test_invalidated_acoustics_approval_fails_as_a_locked_input(
    tmp_path: Path, monkeypatch
) -> None:
    item = metadata._module_inputs(ROOT)[0]
    record = metadata._build(item, ROOT)
    target = metadata._output_path(item, tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(canonical_bytes(record))
    monkeypatch.setattr(metadata, "_approval", lambda *_args: None)
    candidate = metadata._build(item, ROOT)
    monkeypatch.setattr(
        metadata, "_module_inputs", lambda _root: _eleven_test_inputs(item)
    )
    monkeypatch.setattr(metadata, "_build", lambda _item, _root: candidate)
    errors = metadata.generate(tmp_path)
    assert any("locked input changed or lost approval" in error for error in errors)


def test_material_approval_comes_from_shared_receipt_lookup() -> None:
    item = metadata._module_inputs(ROOT)[0]
    path = item["descriptor"].relative_to(ROOT).as_posix()
    approval = metadata.receipts.operator_approval_for_field(
        path, "/surfaces/floor/material_id", ROOT
    )
    assert approval is not None and approval["issue_id"] == 217
    record = metadata._build(item, ROOT)
    assert not any(
        lock["source_field"].endswith("/palette_id")
        for lock in record["locks"].values()
    )
    material_lock = record["locks"]["descriptor:/surfaces/floor/material_id"]
    assert material_lock["receipt"] == metadata._reference(
        ROOT / metadata.receipts.RECEIPT_DIR / "issue-217.json", ROOT
    )


def test_validator_reports_stale_input_hash_without_raising(tmp_path: Path) -> None:
    input_path = tmp_path / "layer.json"
    input_path.write_text("{}\n", encoding="utf-8")
    record_path = tmp_path / "module.json"
    reference = {"path": "layer.json", "sha256": sha256_file(input_path)}
    record = {
        "source_layers": {
            name: reference
            for name in ("profile", "descriptor", "t6", "poetics", "acoustics")
        },
        "inputs": {
            name: reference
            for name in ("profile", "descriptor", "t6", "poetics", "acoustics")
        },
        "approval_refs": {},
        "poetics_ref": reference,
    }
    record["inputs"]["approval_refs"] = {}
    data = canonical_bytes(record)
    record_path.write_bytes(data)
    record_path.with_suffix(".json.sha256").write_text(
        __import__("hashlib").sha256(data).hexdigest() + "\n", encoding="ascii"
    )
    input_path.write_text('{"changed": true}\n', encoding="utf-8")
    assert any(
        "stale input hash: layer.json" in error
        for error in metadata.validate_record(record, tmp_path, record_path)
    )


def test_validator_requires_all_source_references_and_never_raises_on_bad_inputs() -> (
    None
):
    record = json.loads(metadata.record_paths(ROOT)[0].read_text(encoding="utf-8"))
    record["inputs"].pop("descriptor")
    errors = metadata.validate_record(record, ROOT)
    assert any(
        "inputs omits or differs from source_layers.descriptor" in error
        for error in errors
    )
    assert metadata.validate_record({"inputs": None}, ROOT)


def test_repository_coverage_detects_duplicate_and_missing_module_ids(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps({"module_id": "module_a"}), encoding="utf-8")
    second.write_text(json.dumps({"module_id": "module_a"}), encoding="utf-8")
    expected = {"module_a": first, "module_b": second}
    errors = metadata._record_coverage_errors([first, second], expected, tmp_path)
    assert any("duplicate module record for module_a" in error for error in errors)
    assert any(
        "missing record for admitted module module_b" in error for error in errors
    )


def test_section_and_locked_values_are_checked_against_sources() -> None:
    path = metadata.record_paths(ROOT)[0]
    record = json.loads(path.read_text(encoding="utf-8"))
    record["profile"]["shape"]["area_m2"] = -1
    record["surfaces"]["surfaces"]["floor"]["material_id"] = "edited-material"
    errors = metadata.validate_record(record, ROOT)
    assert any("profile differs from its source layer" in error for error in errors)
    assert any(
        "locks." in error and "record value differs" in error for error in errors
    )


def test_mapping_table_hash_is_an_input_for_material_locks() -> None:
    record = json.loads(metadata.record_paths(ROOT)[0].read_text(encoding="utf-8"))
    assert record["inputs"]["mapping_table"] == metadata._mapping_table_ref(ROOT)
    assert metadata._validate_record(record, ROOT, None) == []


def test_source_level_overlay_is_referenced_without_embedding() -> None:
    item = metadata._module_inputs(ROOT)[-1].copy()
    item["overlay"] = (
        ROOT
        / "godot_walk/source_library/sources/picture-set-d160eaa3cc847d5c/source_lighting_scale_v1.json"
    )
    record = metadata._build(item, ROOT)
    assert record["lighting_scale"]["state"] == "source_overlay"
    assert "overlay" not in record["lighting_scale"]
    assert (
        record["lighting_scale"]["overlay_ref"]
        == record["source_layers"]["lighting_scale"]
    )
    assert "lighting_scale:/scale/anchor/value_m" in record["locks"]


def test_palette_validation_accepts_null_and_rejects_unknown_palette() -> None:
    record = json.loads(metadata.record_paths(ROOT)[0].read_text(encoding="utf-8"))
    record["surfaces"]["surfaces"]["floor"]["palette_id"] = None
    assert metadata._palette_errors(record, ROOT) == []
    record["surfaces"]["surfaces"]["floor"]["palette_id"] = "missing_palette"
    assert any(
        "not in palettes-0.3.0.json" in error
        for error in metadata._palette_errors(record, ROOT)
    )


def test_records_carry_layer_values_verbatim_and_acoustic_provenance_per_field() -> (
    None
):
    for path in metadata.record_paths(ROOT):
        record = json.loads(path.read_text(encoding="utf-8"))
        layers = record["source_layers"]
        profile = json.loads(
            (ROOT / layers["profile"]["path"]).read_text(encoding="utf-8")
        )
        descriptor = json.loads(
            (ROOT / layers["descriptor"]["path"]).read_text(encoding="utf-8")
        )
        t6 = json.loads((ROOT / layers["t6"]["path"]).read_text(encoding="utf-8"))
        assert record["profile"] == profile
        assert record["surfaces"] == descriptor
        assert record["t6"] == t6
        assert record["space_kind"] == "enclosed"
        assert record["registration_accepted"] is False
        assert record["scale_calibrated"] is False
        assert (
            record["acoustics"]["committed_block"]["probe"]["provenance"] == "measured"
        )
        for name, field in record["acoustics"]["fields"].items():
            expected = "measured" if name in metadata.MEASURED_FIELDS else "derived"
            assert field["provenance"]["kind"] == expected
            assert field["committed_block_label"] == "measured"
        assert (
            metadata.CEILING_LIMITATION
            in record["acoustics"]["fields"]["ceiling_height_m"]["provenance"][
                "limitation"
            ]
        )


def test_record_detached_pins_match_exact_record_bytes() -> None:
    for path in metadata.record_paths(ROOT):
        pin = path.with_suffix(path.suffix + ".sha256")
        import hashlib

        assert (
            pin.read_text(encoding="ascii").strip()
            == hashlib.sha256(path.read_bytes()).hexdigest()
        )


def test_every_record_locks_exactly_its_receipt_approved_layer_leaves() -> None:
    def leaves(value, prefix=""):
        if isinstance(value, dict):
            return [
                path
                for key, child in value.items()
                for path in leaves(child, f"{prefix}/{key}")
            ]
        if isinstance(value, list):
            return [
                path
                for index, child in enumerate(value)
                for path in leaves(child, f"{prefix}/{index}")
            ]
        return [prefix or "/"]

    receipt_cache = metadata.receipts.valid_receipts(ROOT)
    for path in metadata.record_paths(ROOT):
        record = json.loads(path.read_text(encoding="utf-8"))
        expected = set()
        for layer in ("profile", "descriptor", "t6", "lighting_scale"):
            reference = record["source_layers"].get(layer)
            if reference is None:
                continue
            source = json.loads((ROOT / reference["path"]).read_text(encoding="utf-8"))
            for field in leaves(source):
                if layer == "descriptor" and field.endswith("/palette_id"):
                    continue
                approved = metadata.receipts.operator_approval_for_field(
                    reference["path"], field, ROOT, receipt_cache
                )
                if approved:
                    expected.add((reference["path"], field))
        acoustic_reference = record["source_layers"]["acoustics"]
        acoustic_document = json.loads(
            (ROOT / acoustic_reference["path"]).read_text(encoding="utf-8")
        )
        module = acoustic_document["modules"][f"{record['module_id']}@1"]
        prefix = f"/modules/{record['module_id']}@1"
        for field in leaves(module, prefix):
            if metadata.receipts.operator_approval_for_field(
                acoustic_reference["path"], field, ROOT, receipt_cache
            ):
                expected.add((acoustic_reference["path"], field))
        actual = {
            (lock["source_path"], lock["source_field"])
            for lock in record["locks"].values()
        }
        assert actual == expected
        for field in (
            "/lighting/colour_temperature_k/value",
            "/lighting/illuminance_lux/value",
            "/scale/anchor/value_m",
            "/lighting/fixture_layout/0/arrangement",
        ):
            if (
                record["source_layers"]
                .get("lighting_scale", {})
                .get("path", "")
                .endswith("-lighting-scale-v1.json")
            ):
                assert (
                    record["source_layers"]["lighting_scale"]["path"],
                    field,
                ) in actual
        for field in (
            "/probe/provenance",
            "/probe/mean_distance_m",
            "/probe/ceiling_height_m",
        ):
            source_field = prefix + field
            if metadata.receipts.operator_approval_for_field(
                acoustic_reference["path"], source_field, ROOT, receipt_cache
            ):
                assert (acoustic_reference["path"], source_field) in actual
