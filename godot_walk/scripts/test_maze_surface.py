"""Tests for palette-compatible surface layers (#238)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maze_mutation as mm
import maze_surface as ms
from deterministic_json import ROOT, sha256_file

MAP_PATH = ROOT / "godot_walk/room_catalog/generative_maps/gmap-279-gmap-0.13.0.json"


@pytest.fixture(scope="module")
def base() -> mm.BaseMap:
    return mm.load_base(MAP_PATH)


@pytest.fixture(scope="module")
def cell() -> dict:
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    return next(entry for entry in document["cells"] if entry["cell_id"] == "c00")


def test_registry_reference_loads_and_palette_lookup(base, cell):
    registry = ms.palette_registry(base.document)
    assert registry["palettes"]
    palette = ms.palette_for_cell(base.document, cell, registry=registry)
    assert palette["palette_id"] == cell["palette"]["palette_id"]
    assert ms.registry_version_for(base.document) == "0.3.0"


def test_registry_hash_mismatch_is_rejected(base):
    document = copy.deepcopy(base.document)
    document["palette_registry"]["sha256"] = "0" * 64
    with pytest.raises(ms.SurfaceError) as error:
        ms.palette_registry(document)
    assert error.value.code == "palette_stale"


def test_unknown_palette_is_rejected(base, cell):
    forged = copy.deepcopy(cell)
    forged["palette"]["palette_id"] = "missing_palette"
    with pytest.raises(ms.SurfaceError) as error:
        ms.palette_for_cell(base.document, forged)
    assert error.value.code == "palette_unknown"


def test_variant_must_exist_in_the_cell_palette(base, cell):
    palette = copy.deepcopy(ms.palette_for_cell(base.document, cell))
    del palette["surfaces"]["floor"]["variants"]["worn"]
    variants = copy.deepcopy(cell["surface_variants"])
    variants["floor"] = "worn"
    with pytest.raises(ms.SurfaceError) as error:
        ms.validate_variants(cell, variants, palette)
    assert error.value.code == "variant_incompatible"


def test_unknown_variant_name_is_rejected(cell):
    with pytest.raises(ms.SurfaceError) as error:
        ms.surface_record({"cell_id": cell["cell_id"], "surface_variants": {"floor": "pristine"}})
    assert error.value.code == "surface_invalid"


def test_variants_move_forward_only_and_cap_at_damaged(base, cell):
    palette = ms.palette_for_cell(base.document, cell)
    assert ms.next_variant("floor", "clean", palette) == "worn"
    assert ms.next_variant("floor", "worn", palette) == "damaged"
    assert ms.next_variant("floor", "damaged", palette) is None
    clean = copy.deepcopy(cell["surface_variants"])
    after = ms.surface_change(cell, "floor", clean, palette)
    assert after is not None
    assert after["floor"] == "worn"
    damaged = {surface: "damaged" for surface in ms.SURFACES}
    assert ms.escalatable_from_variants(damaged, palette) == []
    assert ms.surface_change(cell, "floor", damaged, palette) is None


def test_wear_is_bounded_and_override_is_merged(cell):
    assert ms.wear_record(cell) == 0
    assert ms.effective_wear(cell, {}) == 0
    assert ms.effective_wear(cell, {"wear": 2}) == 2
    with pytest.raises(ms.SurfaceError) as error:
        ms.effective_wear(cell, {"wear": 3})
    assert error.value.code == "override_invalid"
    with pytest.raises(ms.SurfaceError) as error:
        ms.wear_record({"cell_id": cell["cell_id"], "wear": True})
    assert error.value.code == "wear_invalid"


def test_variant_override_merges_one_surface(base, cell):
    variants = ms.effective_variants(
        base.document, cell, {"surface_variant": {"trim": "worn"}}
    )
    assert variants["trim"] == "worn"
    assert variants["floor"] == cell["surface_variants"]["floor"]
    with pytest.raises(ms.SurfaceError) as error:
        ms.effective_variants(
            base.document, cell, {"surface_variant": {"walls": "worn"}}
        )
    assert error.value.code == "override_invalid"


def test_registry_directory_and_text_contract(base):
    reference = base.document["palette_registry"]
    path = ROOT / reference["path"]
    assert sha256_file(path) == reference["sha256"]
    assert path.read_text(encoding="utf-8").strip()
    assert path.suffix == ".json"
