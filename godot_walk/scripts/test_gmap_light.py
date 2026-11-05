"""Map-driven generated-room lighting for gmap-0.8.0 (#198)."""

from __future__ import annotations

import copy
import json
import os
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, sha256_file
from gmap_build import GENERATOR_VERSION_V7, GENERATOR_VERSION_V8, build_map
from gmap_library import load_library
from gmap_light import light_errors
from gmap_validate import validate_document
from shape_room import edge_links
from shape_room_spec import build_spec

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"


@pytest.fixture(scope="module")
def library():
    return load_library(INDEX)


def _without_light(document: dict) -> dict:
    result = copy.deepcopy(document)
    result.pop("dark_wing", None)
    for cell in result["cells"]:
        cell.pop("light", None)
    return result


def test_v80_preserves_v70_map_geometry_and_other_map_data(library):
    for seed, size in ((1, 12), (2, 12), (3, 12), (69, 12), (64, 20)):
        old = build_map(seed, library, cells=size, version=GENERATOR_VERSION_V7)
        new = build_map(seed, library, cells=size, version=GENERATOR_VERSION_V8)
        old_base, new_base = _without_light(old), _without_light(new)
        for document in (old_base, new_base):
            document.pop("generator_version", None)
            document.pop("map_id", None)
            document.pop("rules", None)
        assert old_base == new_base


def test_v80_shape_specs_preserve_v70_geometry(library):
    old = build_map(69, library, cells=12, version=GENERATOR_VERSION_V7)
    new = build_map(69, library, cells=12, version=GENERATOR_VERSION_V8)
    old_links, new_links = edge_links(old), edge_links(new)
    for old_cell, new_cell in zip(old["cells"], new["cells"], strict=True):
        if old_cell["role"] == "void" or old_cell.get("module"):
            continue
        old_spec = build_spec(old, "a" * 64, old_cell, "shape_room_pending", old_links)
        new_spec = build_spec(new, "a" * 64, new_cell, "shape_room_pending", new_links)
        for spec in (old_spec, new_spec):
            spec.pop("generator_version", None)
            spec.pop("map_id", None)
            spec.pop("map_sha256", None)
            spec.pop("light", None)
        assert old_spec == new_spec


def test_light_assignment_tolerates_invalid_candidate_widths(library):
    document = build_map(163, library, cells=12, version=GENERATOR_VERSION_V8)
    assert validate_document(document) == []
    links = edge_links(document)
    specs = [
        build_spec(document, "a" * 64, cell, "shape_room_pending", links)
        for cell in document["cells"]
        if cell["role"] != "void" and not cell.get("module")
    ]
    assert len(specs) > 0


def test_v80_light_assignment_is_seeded_and_valid(library):
    first = build_map(1, library, cells=12, version=GENERATOR_VERSION_V8)
    second = build_map(1, library, cells=12, version=GENERATOR_VERSION_V8)
    assert first["dark_wing"] == second["dark_wing"]
    assert [cell.get("light") for cell in first["cells"]] == [
        cell.get("light") for cell in second["cells"]
    ]
    assert validate_document(first) == []


def test_light_layer_covers_each_generated_lamp_and_keeps_landmarks_lit(library):
    document = build_map(69, library, cells=12, version=GENERATOR_VERSION_V8)
    assert validate_document(document) == []
    for cell in document["cells"]:
        if cell["role"] == "void":
            assert "light" not in cell
            continue
        light = cell["light"]
        assert [lamp["lamp_index"] for lamp in light["lamps"]] == list(
            range(len(light["lamps"]))
        )
        assert 3800 <= light["color_temp_k"] <= 5200
        if cell.get("landmark"):
            assert light["tier"] == "bright"
            assert [lamp["state"] for lamp in light["lamps"]] == ["on"]


def test_light_validator_rejects_state_and_wing_tampering(library):
    document = build_map(1, library, cells=12, version=GENERATOR_VERSION_V8)
    changed = copy.deepcopy(document)
    cell = next(item for item in changed["cells"] if item["light"]["lamps"])
    cell["light"]["lamps"][0]["state"] = "dead"
    assert any(
        error["code"] == "light_assignment_mismatch"
        for error in light_errors(changed, library)
    )
    changed = copy.deepcopy(document)
    changed["dark_wing"]["cell_ids"] = [changed["cells"][0]["cell_id"]]
    assert light_errors(changed, library)


def test_light_validator_reports_unknown_dark_wing_cell(library):
    document = build_map(1, library, cells=12, version=GENERATOR_VERSION_V8)
    changed = copy.deepcopy(document)
    changed["dark_wing"] = {
        "status": "placed",
        "cell_ids": ["nonexistent", changed["cells"][1]["cell_id"]],
    }
    errors = light_errors(changed, library)
    unknown = [error for error in errors if error["code"] == "dark_wing_unknown_cell"]
    assert unknown
    assert "nonexistent" in unknown[0]["message"]
    assert "dark_wing_unknown_cell" in {
        error["code"] for error in validate_document(changed)
    }


def test_v80_validator_reports_missing_library_index(library):
    document = build_map(1, library, cells=12, version=GENERATOR_VERSION_V8)
    document["library_index"]["path"] = (
        "godot_walk/room_catalog/library_index/missing-index.json"
    )
    codes = {error["code"] for error in validate_document(document)}
    assert {"stale_index_hash", "library_index_unavailable"} <= codes


def test_v80_validator_reports_unloadable_library_index(library, tmp_path):
    document = build_map(1, library, cells=12, version=GENERATOR_VERSION_V8)
    broken = tmp_path / "broken-index.json"
    broken.write_text("{not valid json", encoding="utf-8")
    document["library_index"].update(
        {"path": str(broken), "sha256": sha256_file(broken)}
    )
    codes = {error["code"] for error in validate_document(document)}
    assert "library_index_unavailable" in codes


@pytest.mark.parametrize(
    "modules",
    [[None], [{}], ["not-a-module"]],
    ids=["null-entry", "empty-entry", "string-entry"],
)
def test_v80_validator_reports_malformed_library_index(library, tmp_path, modules):
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    index["modules"] = modules
    malformed = tmp_path / "malformed-index.json"
    malformed.write_text(json.dumps(index), encoding="utf-8")
    document = build_map(1, library, cells=12, version=GENERATOR_VERSION_V8)
    document["library_index"].update(
        {"path": str(malformed), "sha256": sha256_file(malformed)}
    )
    codes = {error["code"] for error in validate_document(document)}
    assert "library_index_unavailable" in codes


def _sweep(library, cell_count: int) -> dict:
    states: Counter[str] = Counter()
    tiers: Counter[str] = Counter()
    wings: Counter[str] = Counter()
    invalid: list[tuple[int, list[dict]]] = []
    for seed in range(1, 301):
        document = build_map(
            seed, library, cells=cell_count, version=GENERATOR_VERSION_V8
        )
        errors = validate_document(document)
        if errors:
            invalid.append((seed, errors[:2]))
        wings[document["dark_wing"]["status"]] += 1
        for cell in document["cells"]:
            if cell["role"] == "void":
                continue
            tiers[cell["light"]["tier"]] += 1
            states.update(lamp["state"] for lamp in cell["light"]["lamps"])
    return {"states": states, "tiers": tiers, "wings": wings, "invalid": invalid}


@pytest.mark.skipif(
    os.environ.get("GMAP_LIGHT_SWEEP") != "1",
    reason="600-map light sweep; run with GMAP_LIGHT_SWEEP=1",
)
def test_v80_seed_sweep_12_and_20_cells(library):
    twelve, twenty = _sweep(library, 12), _sweep(library, 20)
    print(f"gmap-0.8.0 cells=12 {twelve}")
    print(f"gmap-0.8.0 cells=20 {twenty}")
    assert not twelve["invalid"] and not twenty["invalid"]
    for result in (twelve, twenty):
        assert sum(result["wings"].values()) == 300
        assert result["wings"]["placed"] > 0
        assert result["states"]["on"] > result["states"]["flicker"]
        assert result["states"]["on"] > result["states"]["dead"]
