"""Template consumer and layer stability checks for gmap-0.13.0 (#220)."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gmap_build
from deterministic_json import ROOT
from gmap_library import load_library
from gmap_validate import validate_document

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
MAPS = ROOT / "godot_walk/room_catalog/generative_maps"
SEEDS = (1, 2, 3, 32, 279)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v13_consumes_metadata_and_commits_redrawable_maps() -> None:
    library = load_library(INDEX)
    for seed in SEEDS:
        previous = _load(MAPS / f"gmap-{seed}-gmap-0.12.0.json")
        current = _load(MAPS / f"gmap-{seed}-gmap-0.13.0.json")
        assert validate_document(previous) == []
        assert validate_document(current) == []
        assert current["registration_accepted"] is False
        assert current["scale_calibrated"] is False
        assert current["elevation"] == previous["elevation"]
        assert current.get("elevation_loops") == previous.get("elevation_loops")
        assert current.get("floor_regions") == previous.get("floor_regions")
        old_edges = {(edge["from"], edge["to"]): edge for edge in previous["edges"]}
        for edge in current["edges"]:
            old_edge = old_edges[(edge["from"], edge["to"])]
            for layer in ("vertical", "ramp", "drop", "kind"):
                assert edge.get(layer) == old_edge.get(layer), (seed, edge, layer)
        for cell in current["cells"]:
            old_cell = next(
                item for item in previous["cells"] if item["cell_id"] == cell["cell_id"]
            )
            for layer in (
                "floor_y",
                "reverb",
                "palette",
                "light",
                "wear",
                "surface_variants",
            ):
                assert cell.get(layer) == old_cell.get(layer), (
                    seed,
                    cell["cell_id"],
                    layer,
                )
            assert cell["volume"]["nominal_m3"] is not None
            assert cell["absorption"]["source"] == "#213"
            assert cell["mutation"]["eligible"] is False
            if cell.get("module"):
                assert cell["module_profile"] in [
                    {"path": pin["path"], "sha256": pin["sha256"]}
                    for pin in current["module_metadata"]
                ]
        assert current["template"]["version"] == "generation-template-0.1.0"
        assert current["module_metadata"] == sorted(
            current["module_metadata"], key=lambda item: item["module_id"]
        )
        assert all(
            not door["reroll"]["eligible"]
            for cell in current["cells"]
            for door in cell["doors"]
        )
        assert all(
            edge["door_id"] in (edge["from"], edge["to"]) for edge in current["edges"]
        )
        room_index = (
            ROOT
            / "godot_walk/room_catalog/shape_rooms"
            / current["map_id"]
            / "index.json"
        )
        assert room_index.is_file()
        assert (
            gmap_build.build_map(
                seed, library, version=gmap_build.GENERATOR_VERSION_V13
            )
            == current
        )


def test_v13_rejects_missing_or_incorrect_metadata_pins() -> None:
    document = _load(MAPS / "gmap-1-gmap-0.13.0.json")
    missing_pin = deepcopy(document)
    missing_pin["module_metadata"] = []
    assert validate_document(missing_pin)
    missing_profile = deepcopy(document)
    module_cell = next(cell for cell in missing_profile["cells"] if cell.get("module"))
    del module_cell["module_profile"]
    assert validate_document(missing_profile)
    wrong_pin = deepcopy(document)
    wrong_pin["module_metadata"][0]["sha256"] = "0" * 64
    assert validate_document(wrong_pin)
