"""Tests for the seeded structural map generator (issue 182): determinism, rules, controls."""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generative_map as gm
import gmap_build as build
import gmap_library as library
from deterministic_json import ROOT, DeterministicWriteError
from gmap_assign import add_voids
from gmap_geometry import contact_port, flush_rects, overlaps
from gmap_grow import Cell, Draft, GenerationError, connect
from gmap_validate import validate_document

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
MAP_DIR = ROOT / "godot_walk/room_catalog/generative_maps"


@pytest.fixture(scope="module")
def lib() -> library.Library:
    return library.load_library(INDEX)


def codes(document: dict) -> set[str]:
    return {error["code"] for error in validate_document(document)}


def generated(lib, seed: int = 1) -> dict:
    return build.build_map(seed, lib)


def from_draft(lib, draft: Draft) -> dict:
    """A document built from a hand-made draft, on the real index/snapshot refs."""
    document = build.build_map(1, lib)
    document["cells"] = [build.cell_json(c, ["box"]) for c in draft.cells.values()]
    document["edges"] = [{"from": a, "to": b, "connector": k} for a, b, k in draft.edges]
    return document


def grid(lib, rects: dict[str, tuple], links: list[tuple[str, str]], roles: dict[str, str] | None = None) -> dict:
    """Hand-made cells joined by `links`, plus one void west of c00."""
    draft = Draft()
    for cell_id, rect in rects.items():
        draft.cells[cell_id] = Cell(cell_id, rect)
    for a, b in links:
        connect(draft, draft.cells[a], draft.cells[b], "direct")
    void = Cell("c09", (-3, 0, 0, 3), role="void")
    draft.cells["c09"] = void
    connect(draft, draft.cells["c00"], void, "closed_visible")
    for cell_id, role in (roles or {}).items():
        draft.cells[cell_id].role = role
    return from_draft(lib, draft)


BLOCK = {"c00": (0, 0, 6, 6), "c01": (6, 0, 12, 6), "c02": (0, 6, 6, 12), "c03": (6, 6, 12, 12)}
ROW = {"c00": (0, 0, 6, 6), "c01": (6, 0, 12, 6), "c02": (12, 0, 18, 6), "c03": (6, 6, 12, 12)}


# --- determinism and generation -------------------------------------------------


def test_same_seed_is_byte_identical_and_reruns_are_unchanged(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    gm.generate(7, INDEX, svg=True, out_dir=first)
    result = gm.generate(7, INDEX, svg=True, out_dir=second)
    assert {f["status"] for f in result["files"]} == {"created"}
    names = sorted(p.name for p in first.iterdir())
    assert names == ["gmap-7-gmap-0.1.0.fill.json", "gmap-7-gmap-0.1.0.json", "gmap-7-gmap-0.1.0.svg"]
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    again = gm.generate(7, INDEX, svg=True, out_dir=first)
    assert {f["status"] for f in again["files"]} == {"unchanged"}


def test_refuses_to_overwrite_different_content_and_writes_nothing(tmp_path):
    gm.generate(7, INDEX, out_dir=tmp_path)
    fill = tmp_path / "gmap-7-gmap-0.1.0.fill.json"
    fill.write_text("{}\n", encoding="utf-8")
    other = tmp_path / "gmap-7-gmap-0.1.0.svg"
    with pytest.raises(DeterministicWriteError):
        gm.generate(7, INDEX, svg=True, out_dir=tmp_path)
    assert not other.exists()
    assert fill.read_text(encoding="utf-8") == "{}\n"


def test_seeds_1_to_20_validate_and_differ(lib):
    documents = {seed: generated(lib, seed) for seed in range(1, 21)}
    for seed, document in documents.items():
        assert validate_document(document) == [], seed
    assert len({json.dumps(d["cells"], sort_keys=True) for d in documents.values()}) == 20


def test_generated_structure_matches_the_design(lib):
    for seed in range(1, 21):
        document = generated(lib, seed)
        walkable = [c for c in document["cells"] if c["role"] != "void"]
        voids = [c for c in document["cells"] if c["role"] == "void"]
        assert len(walkable) == 12 and 1 <= len(voids) <= 3
        assert len([e for e in document["edges"] if e["connector"] == "direct"]) == 11
        void_ids = {v["cell_id"] for v in voids}
        void_edges = [e for e in document["edges"] if e["to"].split(":")[0] in void_ids]
        assert len(void_edges) == len(voids)
        assert all(e["connector"] == "closed_visible" for e in void_edges)
        assert document["registration_accepted"] is False and document["scale_calibrated"] is False
        assert document["rules"] == sorted(build.RULE_IDS)


def test_stage_zero_only_allows_boxes(lib):
    document = build.build_map(3, lib, stage_max=0)
    assert {tuple(c["allowed_primitives"]) for c in document["cells"]} == {("box",)}
    assert validate_document(document) == []


def test_cell_count_range_and_stage_are_enforced(lib):
    for bad in (5, 21):
        with pytest.raises(GenerationError):
            build.build_map(1, lib, cells=bad)
    with pytest.raises(GenerationError):
        build.build_map(1, lib, stage_max=2)


def test_branch_retry_records_attempt(lib):
    document = build.build_map(1, lib, cells=6)
    assert document["attempt"] >= 1
    assert validate_document(document) == []
    assert build.build_map(1, lib, cells=6) == document


def test_tier_distribution_over_300_seeds(lib):
    tiers = Counter()
    for seed in range(1, 301):
        tiers.update(c["rarity_tier"] for c in generated(lib, seed)["cells"] if c["role"] != "void")
    assert tiers[0] == max(tiers.values())
    assert tiers[3] == min(tiers[t] for t in range(4)) and tiers[3] > 0


def test_figure_cells_use_figure_size_classes(lib):
    classes = library.figure_classes(lib)
    assert classes == [(8, 8), (12, 10), (16, 13)]
    allowed = {tuple(sorted(c)) for c in classes}
    for seed in range(1, 40):
        for cell in generated(lib, seed)["cells"]:
            if cell["role"] == "figure":
                (x0, z0), (x1, z1) = cell["envelope_xz"][0], cell["envelope_xz"][2]
                assert tuple(sorted((x1 - x0, z1 - z0))) in allowed
                assert cell["rarity_tier"] >= 2 and cell["ceiling_range_m"] == [3.0, 6.0]


def test_void_placement_failure_asks_for_another_attempt(monkeypatch):
    import random

    import gmap_assign
    from gmap_grow import RetryAttempt

    draft = Draft()
    draft.cells["c00"] = Cell("c00", (0, 0, 6, 6))
    monkeypatch.setattr(gmap_assign, "placements", lambda *args: [])
    with pytest.raises(RetryAttempt):
        add_voids(random.Random(1), draft)


def test_geometry_helpers_snap_ports_to_the_lattice():
    parent = (0, 0, 6, 6)
    for rect in flush_rects(parent, (1, 0), 8, 8):
        assert not overlaps(parent, rect)
        pos, normal = contact_port(parent, rect)
        assert normal == (1, 0) and pos[0] == 6 and pos[1] == int(pos[1])
    assert contact_port((0, 0, 6, 6), (6, 5, 12, 11)) is None  # 1 m overlap


# --- negative controls ------------------------------------------------------------


def test_control_overlap(lib):
    document = generated(lib)
    document["cells"][1]["envelope_xz"] = copy.deepcopy(document["cells"][0]["envelope_xz"])
    assert "envelope_overlap" in codes(document)


def test_control_misaligned_port(lib):
    document = generated(lib)
    port = document["cells"][0]["required_ports"][0]
    port["pos_xz"] = [port["pos_xz"][0] + 1, port["pos_xz"][1] + 1]
    assert {"port_misaligned"} <= codes(document)


def test_control_loop(lib):
    ring = [("c00", "c01"), ("c01", "c03"), ("c03", "c02"), ("c02", "c00")]
    assert "tree_loop" in codes(grid(lib, BLOCK, ring))
    tree = codes(grid(lib, BLOCK, ring[:3]))
    assert "tree_loop" not in tree and "tree_disconnected" not in tree


def test_control_disconnected(lib):
    assert "tree_disconnected" in codes(grid(lib, ROW, [("c00", "c01"), ("c01", "c03")]))


def test_control_no_branch(lib):
    chain = [("c00", "c01"), ("c01", "c02"), ("c01", "c03")]
    assert "no_branch" not in codes(grid(lib, ROW, chain))
    assert "no_branch" in codes(grid(lib, BLOCK, [("c00", "c01"), ("c01", "c03"), ("c03", "c02")]))


def test_control_adjacent_figures(lib):
    links = [("c00", "c01"), ("c01", "c02"), ("c01", "c03")]
    assert "figure_adjacent" in codes(grid(lib, ROW, links, {"c00": "figure", "c01": "figure"}))
    assert "figure_adjacent" not in codes(grid(lib, ROW, links, {"c00": "figure", "c02": "figure"}))


def test_control_traversable_void(lib):
    document = generated(lib)
    void_ids = {c["cell_id"] for c in document["cells"] if c["role"] == "void"}
    edge = next(e for e in document["edges"] if e["to"].split(":")[0] in void_ids)
    edge["connector"] = "direct"
    assert "void_traversable" in codes(document)


def test_control_stale_index_hash(lib):
    document = generated(lib)
    document["library_index"]["sha256"] = "0" * 64
    assert "stale_index_hash" in codes(document)
    document = generated(lib)
    document["catalog_snapshot"]["sha256"] = "1" * 64
    assert "stale_snapshot_hash" in codes(document)


def test_control_off_lattice_normals_and_budget(lib):
    document = generated(lib)
    document["cells"][0]["required_ports"][0]["pos_xz"][0] += 0.5
    assert "off_lattice" in codes(document)
    document = generated(lib)
    first = next(e for e in document["edges"] if e["connector"] == "direct")
    ports = {p["port_id"]: p for c in document["cells"] for p in c["required_ports"]}
    ports[first["to"]]["normal"] = list(ports[first["from"]]["normal"])
    assert "normals_not_opposite" in codes(document)
    document = generated(lib)
    document["void_budget"] = {"min": 0, "max": 0}
    assert "void_budget" in codes(document)


def test_control_schema_and_rule_list(lib):
    document = generated(lib)
    document["surprise"] = True
    assert codes(document) == {"schema"}
    document = generated(lib)
    document["rules"] = ["tree_no_loops"]
    assert "rules_incomplete" in codes(document)


# --- CLI and committed outputs ----------------------------------------------------


def test_cli_validate_reports_json_errors_and_exit_code(tmp_path, capsys, lib):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(generated(lib)), encoding="utf-8")
    assert gm.main(["validate", str(good)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
    bad_doc = generated(lib)
    bad_doc["library_index"]["sha256"] = "0" * 64
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(bad_doc), encoding="utf-8")
    assert gm.main(["validate", str(bad)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is False and output["errors"][0]["code"] == "stale_index_hash"


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_committed_seed_outputs_are_current(seed, tmp_path):
    gm.generate(seed, INDEX, svg=True, out_dir=tmp_path)
    stem = f"gmap-{seed}-gmap-0.1.0"
    for suffix in (".json", ".fill.json", ".svg"):
        committed = MAP_DIR / f"{stem}{suffix}"
        assert committed.read_bytes() == (tmp_path / f"{stem}{suffix}").read_bytes(), suffix
    assert gm.validate_path(MAP_DIR / f"{stem}.json") == []
