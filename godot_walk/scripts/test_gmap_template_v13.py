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
from gmap_elevation import (
    assign_elevation,
    directed_edges,
    strip_elevation,
    strongly_connected,
    walkable_ids,
)
from gmap_light import assign_light
from gmap_palette import palette_assignment
from gmap_palette_registry import load_registry_v3
from gmap_reverb import (
    STREAM as REVERB_STREAM,
    assign_reverb,
    reverb_for,
    strip_reverb,
    wet_probability,
)
from gmap_surface import assign_surface
from gmap_template import add_template_fields
from gmap_validate import validate_document

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
MAPS = ROOT / "godot_walk/room_catalog/generative_maps"
SEEDS = (1, 2, 3, 32, 279)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cells_by_id(document: dict) -> dict[str, dict]:
    return {cell["cell_id"]: cell for cell in document["cells"]}


def _has_image_field(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            any(token in str(key).lower() for token in ("image", "screenshot", "base64"))
            or _has_image_field(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_has_image_field(item) for item in value)
    return False


def test_v13_redraws_every_layer_from_its_per_cell_stream() -> None:
    library = load_library(INDEX)
    registry = load_registry_v3()
    for seed in SEEDS:
        stored = _load(MAPS / f"gmap-{seed}-gmap-0.13.0.json")

        light_redraw = deepcopy(stored)
        for cell in light_redraw["cells"]:
            cell.pop("light", None)
        light_redraw.pop("dark_wing", None)
        assign_light(light_redraw, library)
        stored_cells = _cells_by_id(stored)
        redrawn_cells = _cells_by_id(light_redraw)
        assert light_redraw["dark_wing"] == stored["dark_wing"], seed
        for cell_id, cell in stored_cells.items():
            assert redrawn_cells[cell_id].get("light") == cell.get("light"), (seed, cell_id, "light")

        surface_redraw = deepcopy(stored)
        for cell in surface_redraw["cells"]:
            cell.pop("wear", None)
            cell.pop("surface_variants", None)
        assign_surface(surface_redraw, registry)
        redrawn_cells = _cells_by_id(surface_redraw)
        for cell_id, cell in stored_cells.items():
            assert redrawn_cells[cell_id].get("wear") == cell.get("wear"), (seed, cell_id, "wear")
            assert redrawn_cells[cell_id].get("surface_variants") == cell.get("surface_variants"), (seed, cell_id, "surface_variants")

        palette_redraw = strip_elevation(deepcopy(stored))
        for cell in palette_redraw["cells"]:
            if not cell.get("module"):
                cell.pop("palette", None)
        palettes, regions = palette_assignment(palette_redraw, library, registry)
        for cell_id, expected in palettes.items():
            assert stored_cells[cell_id].get("palette") == expected, (seed, cell_id, "palette")
        assert stored.get("floor_regions") == regions, (seed, "floor_regions")

        elevation_redraw = strip_elevation(deepcopy(stored))
        assign_elevation(elevation_redraw)
        redrawn_cells = _cells_by_id(elevation_redraw)
        for cell_id, cell in stored_cells.items():
            for field in ("floor_y", "ceiling_range_m"):
                assert redrawn_cells[cell_id].get(field) == cell.get(field), (seed, cell_id, field)
        redrawn_edges = {(edge["from"], edge["to"]): edge for edge in elevation_redraw["edges"]}
        for edge in stored["edges"]:
            redrawn = redrawn_edges[(edge["from"], edge["to"])]
            for field in ("vertical", "ramp", "drop", "kind"):
                assert redrawn.get(field) == edge.get(field), (seed, edge["from"], field)
        assert elevation_redraw.get("elevation") == stored.get("elevation"), (seed, "elevation")
        assert elevation_redraw.get("elevation_loops") == stored.get("elevation_loops"), (seed, "elevation_loops")

        reverb_redraw = strip_reverb(deepcopy(stored))
        assign_reverb(reverb_redraw)
        redrawn_cells = _cells_by_id(reverb_redraw)
        for cell_id, cell in stored_cells.items():
            assert redrawn_cells[cell_id].get("reverb") == cell.get("reverb"), (seed, cell_id, "reverb")
        assert reverb_redraw["reverb_layer"] == stored["reverb_layer"], (seed, "reverb_layer")

        template_redraw = deepcopy(stored)
        template_redraw.pop("template", None)
        template_redraw.pop("module_metadata", None)
        for cell in template_redraw["cells"]:
            for field in ("module_profile", "mood", "absorption", "volume", "doors", "mutation"):
                cell.pop(field, None)
        for edge in template_redraw["edges"]:
            edge.pop("door_id", None)
        add_template_fields(template_redraw)
        assert template_redraw["template"] == stored["template"], (seed, "template")
        assert template_redraw["module_metadata"] == stored["module_metadata"], (seed, "module_metadata")
        redrawn_cells = _cells_by_id(template_redraw)
        for cell_id, cell in stored_cells.items():
            for field in ("module_profile", "mood", "absorption", "volume", "doors", "mutation"):
                assert redrawn_cells[cell_id].get(field) == cell.get(field), (seed, cell_id, field)
        for edge, redrawn in zip(stored["edges"], template_redraw["edges"], strict=True):
            assert redrawn.get("door_id") == edge.get("door_id"), (seed, edge["from"], "door_id")


def test_v13_consumes_metadata_and_commits_redrawable_maps() -> None:
    library = load_library(INDEX)
    for seed in SEEDS:
        previous = _load(MAPS / f"gmap-{seed}-gmap-0.12.0.json")
        current = _load(MAPS / f"gmap-{seed}-gmap-0.13.0.json")
        assert validate_document(previous) == []
        assert validate_document(current) == []
        previous_cells = {cell["cell_id"]: cell for cell in previous["cells"]}
        current_cells = {cell["cell_id"]: cell for cell in current["cells"]}
        assert previous_cells.keys() == current_cells.keys()
        assert previous["reverb_layer"] == current["reverb_layer"]
        old_spawn = previous["cells"][0]["cell_id"]
        new_spawn = current["cells"][0]["cell_id"]
        for cell_id in previous_cells:
            old, new = previous_cells[cell_id], current_cells[cell_id]
            for field in ("envelope_xz", "role", "module"):
                assert old.get(field) == new.get(field), (seed, cell_id, field)
            old_ports = [port for port in old["required_ports"] if ":p" in port["port_id"]]
            new_ports = [port for port in new["required_ports"] if ":p" in port["port_id"]]
            assert old_ports == new_ports, (seed, cell_id, "base ports")
            if old["role"] != "void":
                old_probability = wet_probability(old, old_spawn)
                new_probability = wet_probability(new, new_spawn)
                if old_probability == new_probability:
                    assert new["reverb"] == old["reverb"], (seed, cell_id, "unchanged reverb inputs")
                else:
                    assert new["reverb"] == reverb_for(
                        seed, current["attempt"], new, new_spawn, REVERB_STREAM
                    ), (seed, cell_id, "changed reverb inputs")
        if seed != 279:
            assert current["floor_regions"] == previous["floor_regions"]
        else:
            assert current["floor_regions"] != previous["floor_regions"]
        assert current["registration_accepted"] is False
        assert current["scale_calibrated"] is False
        assert strongly_connected(walkable_ids(current), directed_edges(current))
        degree = {cell_id: 0 for cell_id in walkable_ids(current)}
        for left, right in directed_edges(current):
            degree[left] += 1
        assert any(value == 1 for value in degree.values())
        for cell in current["cells"]:
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
        stale_stream = deepcopy(current)
        old_cells = previous_cells
        for cell in stale_stream["cells"]:
            old = old_cells[cell["cell_id"]]
            for layer in ("light", "wear", "surface_variants", "floor_y", "reverb", "palette"):
                if layer in old:
                    cell[layer] = old[layer]
        assert validate_document(stale_stream)


def test_v13_rejects_missing_or_incorrect_metadata_pins() -> None:
    document = _load(MAPS / "gmap-1-gmap-0.13.0.json")
    missing_pin = deepcopy(document)
    missing_pin["module_metadata"] = []
    assert validate_document(missing_pin)
    missing_profile = deepcopy(document)
    module_cell = next(cell for cell in missing_profile["cells"] if cell.get("module"))
    del module_cell["module_profile"]
    assert validate_document(missing_profile)
    for seed in SEEDS:
        wrong_pin = _load(MAPS / f"gmap-{seed}-gmap-0.13.0.json")
        assert wrong_pin["module_metadata"]
        wrong_pin["module_metadata"][0]["sha256"] = "0" * 64
        assert validate_document(wrong_pin)


def test_v13_validator_rederives_all_metadata_template_values() -> None:
    document = _load(MAPS / "gmap-1-gmap-0.13.0.json")
    module_cell_id = next(cell["cell_id"] for cell in document["cells"] if cell.get("module"))
    generated_cell_id = next(cell["cell_id"] for cell in document["cells"] if not cell.get("module") and cell["role"] != "void")
    mutations = {
        "module_profile": lambda cell: cell["module_profile"].update(sha256="0" * 64),
        "mood": lambda cell: cell["mood"].update(tension=1.0),
        "absorption": lambda cell: cell["absorption"].update(confidence=1.0),
        "module volume": lambda cell: cell["volume"].update(nominal_m3=999999.0),
        "generated cell volume": lambda cell: cell["volume"].update(nominal_m3=999999.0),
        "doors": lambda cell: cell["doors"][0].update(state="locked"),
        "mutation": lambda cell: cell["mutation"].update(eligible=True),
    }
    for field, mutate in mutations.items():
        changed = deepcopy(document)
        cell_id = generated_cell_id if field == "generated cell volume" else module_cell_id
        mutate(next(cell for cell in changed["cells"] if cell["cell_id"] == cell_id))
        assert any(
            error["code"] == "template_cell_value_mismatch"
            for error in validate_document(changed)
        ), field

    changed_template = deepcopy(document)
    changed_template["template"]["version"] = "other-template"
    assert validate_document(changed_template)
    changed_edge = deepcopy(document)
    edge = next(edge for edge in changed_edge["edges"] if edge["from"] != edge["to"])
    edge["door_id"] = edge["to"]
    assert any(error["code"] == "template_edge_value_mismatch" for error in validate_document(changed_edge))


def test_v13_metadata_and_layer_artifacts_remain_text_only() -> None:
    paths: set[Path] = set()
    for seed in SEEDS:
        document = _load(MAPS / f"gmap-{seed}-gmap-0.13.0.json")
        paths.update(
            {
                MAPS / f"gmap-{seed}-gmap-0.13.0.json",
                MAPS / f"gmap-{seed}-gmap-0.13.0.fill.json",
                MAPS / f"gmap-{seed}-gmap-0.13.0.svg",
            }
        )
        room_dir = ROOT / "godot_walk/room_catalog/shape_rooms" / document["map_id"]
        paths.update(room_dir.glob("*.json"))
        paths.update(ROOT / pin["path"] for pin in document["module_metadata"])
    for path in paths:
        content = path.read_bytes()
        assert b"\0" not in content, path
        decoded = content.decode("utf-8")
        if path.suffix == ".json":
            assert not _has_image_field(json.loads(decoded)), path
