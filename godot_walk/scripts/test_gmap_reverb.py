"""Tests for the gmap-0.11.0 per-room wet/dry reverb layer (#204)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generative_map as gm
import gmap_build as build
import shape_room as sr
from deterministic_json import ROOT, canonical_bytes
from gmap_library import Library, load_library
from gmap_reverb import (
    BASE_PROBABILITY,
    DOUBLE_HEIGHT_BONUS,
    MAX_PROBABILITY,
    STREAM,
    assign_reverb,
    keyed_draw,
    metadata,
    reverb_errors,
    reverb_for,
    reverb_summary,
    room_volume_m3,
    strip_reverb,
    wet_probability,
)
from gmap_validate import validate_document
from shape_room_spec import build_spec

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
MAP_DIR = ROOT / "godot_walk/room_catalog/generative_maps"
CATALOG = ROOT / "godot_walk/room_catalog"
SEEDS = (1, 2, 3, 279)
LEGACY_VERSIONS = (
    build.GENERATOR_VERSION,
    build.GENERATOR_VERSION_V2,
    build.GENERATOR_VERSION_V3,
    build.GENERATOR_VERSION_V4,
    build.GENERATOR_VERSION_V5,
    build.GENERATOR_VERSION_V6,
    build.GENERATOR_VERSION_V61,
    build.GENERATOR_VERSION_V7,
    build.GENERATOR_VERSION_V8,
    build.GENERATOR_VERSION_V9,
    build.GENERATOR_VERSION_V10,
)


@pytest.fixture(scope="module")
def library() -> Library:
    return load_library(INDEX)


@pytest.fixture(scope="module")
def samples(library: Library) -> dict[int, dict]:
    return {
        seed: build.build_map(
            seed, library, cells=12, version=build.GENERATOR_VERSION_V11
        )
        for seed in SEEDS
    }


@pytest.fixture(scope="module")
def legacy_samples(library: Library) -> dict[int, dict]:
    return {
        seed: build.build_map(
            seed, library, cells=12, version=build.GENERATOR_VERSION_V10
        )
        for seed in SEEDS
    }


def codes(document: dict) -> set[str]:
    return {error["code"] for error in validate_document(document)}


def walkable(document: dict) -> list[dict]:
    return [cell for cell in document["cells"] if cell["role"] != "void"]


def without_reverb(document: dict) -> dict:
    result = strip_reverb(document)
    for key in ("generator_version", "map_id", "rules"):
        result.pop(key, None)
    return result


def synthetic_cell(cell_id: str, size: float, low: float, high: float) -> dict:
    return {
        "cell_id": cell_id,
        "envelope_xz": [[0, 0], [size, 0], [size, size], [0, size]],
        "ceiling_range_m": [low, high],
        "role": "ground",
        "required_ports": [],
        "allowed_primitives": ["box"],
        "rarity_tier": 0,
    }


def test_v110_maps_are_deterministic_valid_and_carry_the_layer(library):
    for seed in SEEDS:
        first = build.build_map(
            seed, library, cells=12, version=build.GENERATOR_VERSION_V11
        )
        second = build.build_map(
            seed, library, cells=12, version=build.GENERATOR_VERSION_V11
        )
        assert canonical_bytes(first) == canonical_bytes(second)
        assert validate_document(first) == [], seed
        assert first["generator_version"] == "gmap-0.11.0"
        assert first["map_id"] == f"gmap-{seed}-gmap-0.11.0"
        assert first["reverb_layer"] == metadata()
        assert "reverb_layer" in first["rules"]


def test_v110_keeps_every_other_layer_identical_to_v100(samples, legacy_samples):
    for seed in SEEDS:
        assert without_reverb(samples[seed]) == without_reverb(legacy_samples[seed]), (
            seed
        )


def test_v110_shape_specs_keep_the_v100_room_geometry(samples, legacy_samples):
    for seed in SEEDS:
        old, new = legacy_samples[seed], samples[seed]
        old_links = sr.edge_links(old)
        new_links = sr.edge_links(new)
        for old_cell, new_cell in zip(old["cells"], new["cells"], strict=True):
            if old_cell["role"] == "void" or old_cell.get("module"):
                continue
            old_spec = build_spec(
                old, "a" * 64, old_cell, "shape_room_pending", old_links
            )
            new_spec = build_spec(
                new, "a" * 64, new_cell, "shape_room_pending", new_links
            )
            for spec in (old_spec, new_spec):
                spec.pop("map_id", None)
                spec.pop("map_sha256", None)
            assert old_spec == new_spec, (seed, old_cell["cell_id"])


def test_every_walkable_cell_has_one_boolean_flag_and_voids_have_none(samples):
    for document in samples.values():
        for cell in document["cells"]:
            if cell["role"] == "void":
                assert "reverb" not in cell, cell["cell_id"]
            else:
                assert type(cell.get("reverb")) is bool, cell["cell_id"]


def test_spawn_is_always_dry_and_both_states_occur(samples):
    wet = dry = 0
    for document in samples.values():
        spawn = document["cells"][0]["cell_id"]
        assert document["cells"][0]["reverb"] is False
        for cell in walkable(document):
            if cell["cell_id"] == spawn:
                assert cell["reverb"] is False
            wet += int(cell["reverb"])
            dry += int(not cell["reverb"])
    assert wet > 0 and dry > 0


def test_same_seed_same_flags_even_when_one_cell_is_added_or_removed(library):
    document = build.build_map(
        1, library, cells=12, version=build.GENERATOR_VERSION_V11
    )
    flags = {cell["cell_id"]: cell["reverb"] for cell in walkable(document)}
    for removed in ("c01", "c05", "c13"):
        reduced = copy.deepcopy(document)
        reduced["cells"] = [
            cell for cell in reduced["cells"] if cell["cell_id"] != removed
        ]
        assign_reverb(reduced)
        for cell in walkable(reduced):
            assert cell["reverb"] == flags[cell["cell_id"]], (removed, cell["cell_id"])


def test_keyed_draw_depends_on_seed_attempt_and_cell_but_not_order():
    assert keyed_draw(1, 0, "c00") == keyed_draw(1, 0, "c00")
    assert keyed_draw(1, 0, "c00") != keyed_draw(1, 0, "c01")
    assert keyed_draw(1, 0, "c00") != keyed_draw(2, 0, "c00")
    assert keyed_draw(1, 0, "c00") != keyed_draw(1, 1, "c00")
    assert [keyed_draw(1, 0, cell) for cell in ("c00", "c01")] == [
        keyed_draw(1, 0, "c00"),
        keyed_draw(1, 0, "c01"),
    ]


def test_wet_probability_rises_with_volume_and_double_height_and_is_zero_for_spawn():
    small = synthetic_cell("small", 6.0, 2.6, 2.6)
    large = synthetic_cell("large", 16.0, 2.6, 6.0)
    double = synthetic_cell("double", 6.0, 4.8, 4.8)
    standard = synthetic_cell("standard", 6.0, 2.6, 4.8)
    assert room_volume_m3(large) > room_volume_m3(small)
    assert wet_probability(large, "spawn") > wet_probability(small, "spawn")
    assert wet_probability(double, "spawn") > wet_probability(standard, "spawn")
    assert wet_probability(double, "spawn") >= BASE_PROBABILITY + DOUBLE_HEIGHT_BONUS
    assert wet_probability(large, "spawn") <= MAX_PROBABILITY
    assert wet_probability(small, "small") == 0.0
    assert reverb_for(1, 0, small, "small") is False


def test_validator_rejects_non_boolean_and_tampered_flags(samples):
    document = samples[1]
    changed = copy.deepcopy(document)
    changed["cells"][0]["reverb"] = "wet"
    assert codes(changed) == {"schema"}
    assert "reverb_flag_invalid" in {error["code"] for error in reverb_errors(changed)}

    changed = copy.deepcopy(document)
    target = next(
        cell
        for cell in walkable(changed)
        if cell["cell_id"] != changed["cells"][0]["cell_id"]
    )
    target["reverb"] = not target["reverb"]
    assert "reverb_assignment_mismatch" in codes(changed)

    changed = copy.deepcopy(document)
    changed["cells"][0]["reverb"] = True
    assert "reverb_assignment_mismatch" in codes(changed)
    assert "spawn_is_wet" in {error["code"] for error in reverb_errors(changed)}

    void = next(cell for cell in document["cells"] if cell["role"] == "void")
    changed = copy.deepcopy(document)
    next(cell for cell in changed["cells"] if cell["cell_id"] == void["cell_id"])[
        "reverb"
    ] = True
    assert "void_has_reverb" in codes(changed)

    changed = copy.deepcopy(document)
    next(cell for cell in changed["cells"] if cell["role"] != "void").pop("reverb")
    assert codes(changed) == {"schema"}
    assert "reverb_flag_invalid" in {error["code"] for error in reverb_errors(changed)}

    changed = copy.deepcopy(document)
    changed.pop("reverb_layer")
    assert codes(changed) == {"schema"}
    assert "reverb_metadata_missing" in {
        error["code"] for error in reverb_errors(changed)
    }


def test_previous_versions_carry_no_flags_and_report_dry(legacy_samples):
    for document in legacy_samples.values():
        assert all("reverb" not in cell for cell in document["cells"])
        assert validate_document(document) == []
        summary = reverb_summary(document)
        assert summary["layer"] == "absent"
        assert summary["wet"] == 0
        assert summary["dry"] == len(walkable(document))


def test_map_summary_reports_wet_dry_counts_and_ratio(samples):
    for document in samples.values():
        summary = reverb_summary(document)
        rooms = walkable(document)
        assert summary["layer"] == "present"
        assert summary["stream"] == STREAM
        assert summary["wet"] + summary["dry"] == len(rooms)
        assert summary["wet"] == sum(1 for cell in rooms if cell["reverb"])
        assert summary["wet_ratio"] == pytest.approx(
            summary["wet"] / len(rooms), abs=1e-6
        )


def test_cli_validate_includes_the_reverb_summary(tmp_path, capsys, samples):
    path = tmp_path / "map.json"
    path.write_text(json.dumps(samples[1]), encoding="utf-8")
    assert gm.main(["validate", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is True
    assert output["summary"]["reverb"] == reverb_summary(samples[1])


def test_generate_reports_the_reverb_summary(tmp_path):
    result = gm.generate(
        1,
        INDEX,
        svg=True,
        out_dir=tmp_path,
        version=build.GENERATOR_VERSION_V11,
    )
    assert result["summary"]["reverb"]["layer"] == "present"
    assert result["summary"]["reverb"]["wet"] > 0


def test_old_versions_stay_byte_identical(library):
    for seed in (1, 2, 3):
        for version in LEGACY_VERSIONS:
            document = build.build_map(seed, library, cells=12, version=version)
            path = MAP_DIR / f"gmap-{seed}-{version}.json"
            assert canonical_bytes(document) == path.read_bytes(), (seed, version)


@pytest.mark.parametrize("seed", SEEDS)
def test_committed_v110_outputs_are_current_and_valid(seed, tmp_path):
    gm.generate(
        seed,
        INDEX,
        svg=True,
        out_dir=tmp_path,
        version=build.GENERATOR_VERSION_V11,
    )
    stem = f"gmap-{seed}-gmap-0.11.0"
    for suffix in (".json", ".fill.json", ".svg"):
        assert (MAP_DIR / f"{stem}{suffix}").read_bytes() == (
            tmp_path / f"{stem}{suffix}"
        ).read_bytes(), suffix
    assert gm.validate_path(MAP_DIR / f"{stem}.json") == []
    assert sr.validate(MAP_DIR / f"{stem}.json", "all_walkable") == []
    committed = CATALOG / "shape_rooms" / stem
    regenerated = tmp_path / "rooms" / stem
    sr.generate(MAP_DIR / f"{stem}.json", "all_walkable", out_dir=tmp_path / "rooms")
    assert sorted(path.name for path in committed.glob("*.json")) == sorted(
        path.name for path in regenerated.glob("*.json")
    )
    for path in committed.glob("*.json"):
        assert path.read_bytes() == (regenerated / path.name).read_bytes(), path.name
