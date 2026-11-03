"""Tests for shape-room specs (issue 183): primitives, margins, containment, determinism, controls."""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

import shape_room as sr
from deterministic_json import ROOT, DeterministicWriteError
from library_index import load_json
from poetics_geometry import is_rectilinear
from shape_room_arms import arm_rects, arm_width_range, primitive_for
from shape_room_checks import ShapeRoomError, check_room, port_issues, require_valid
from shape_room_raster import RasterError, decompose, is_connected, occupied_cells, outline_of
from shape_room_rng import cell_rng
from shape_room_spec import build_spec, lamp_inset_ok

CATALOG = ROOT / "godot_walk/room_catalog"
MAP_DIR = CATALOG / "generative_maps"
SEEDS = (1, 2, 3)


def map_path(seed: int) -> Path:
    return MAP_DIR / f"gmap-{seed}-gmap-0.1.0.json"


def specs_for(seed: int, mode: str = "all_walkable") -> dict[str, dict]:
    files = sr.derive(map_path(seed), mode)
    return {n[:-5]: json.loads(d) for n, d in files.items() if n != "index.json"}


def port(port_id: str, pos: tuple[int, int], normal: tuple[int, int]) -> dict:
    return {"port_id": port_id, "pos_xz": list(pos), "normal": list(normal), "compatibility_type": "level_doorway_2m_v1"}


def spec_of(role: str, size: tuple[int, int], ports: list[dict], stage_max: int = 1) -> dict:
    document = {"seed": 7, "map_id": "gmap-7-gmap-0.1.0", "shape_stage_max": stage_max}
    width, depth = size
    cell = {
        "cell_id": "c00", "role": role, "rarity_tier": 0, "ceiling_range_m": [2.6, 4.8],
        "allowed_primitives": ["box", "l_shape", "rectilinear_polygon"], "required_ports": ports,
        "envelope_xz": [[0, 0], [width, 0], [width, depth], [0, depth]],
    }
    links = {p["port_id"]: (f"c99:{p['port_id']}", "direct") for p in ports}
    return build_spec(document, "0" * 64, cell, "shape_room_pending", links)


# --- primitives -------------------------------------------------------------


@pytest.mark.parametrize(
    ("ports", "expected"),
    [
        ([port("a", (3, 0), (0, -1))], "dead_end"),
        ([port("a", (3, 0), (0, -1)), port("b", (3, 8), (0, 1))], "straight"),
        ([port("a", (3, 0), (0, -1)), port("b", (8, 3), (1, 0))], "l_shape"),
        ([port("a", (3, 0), (0, -1)), port("b", (3, 8), (0, 1)), port("c", (8, 3), (1, 0))], "t_shape"),
        (
            [port("a", (3, 0), (0, -1)), port("b", (3, 8), (0, 1)), port("c", (8, 3), (1, 0)), port("d", (0, 3), (-1, 0))],
            "cross",
        ),
        ([port("a", (2, 0), (0, -1)), port("b", (6, 0), (0, -1))], "u_shape"),
    ],
)
def test_primitive_follows_port_pattern(ports: list[dict], expected: str) -> None:
    assert primitive_for(ports) == expected


@pytest.mark.parametrize(
    ("ports", "expected_class"),
    [
        ([port("a", (5, 0), (0, -1)), port("b", (10, 5), (1, 0))], "l_shape"),
        ([port("a", (5, 0), (0, -1)), port("b", (5, 10), (0, 1)), port("c", (10, 5), (1, 0))], "rectilinear_polygon"),
        (
            [port("a", (5, 0), (0, -1)), port("b", (5, 10), (0, 1)), port("c", (10, 5), (1, 0)), port("d", (0, 5), (-1, 0))],
            "rectilinear_polygon",
        ),
        ([port("a", (2, 0), (0, -1)), port("b", (8, 0), (0, -1))], "rectilinear_polygon"),
    ],
)
def test_threshold_arms_realise_the_pattern(ports: list[dict], expected_class: str) -> None:
    spec = spec_of("threshold", (10, 10), ports)
    assert spec["construction"] == "arms" and spec["arm_width_m"] == 3
    assert spec["primitive_class"] == expected_class
    assert is_rectilinear([tuple(p) for p in spec["outline_xz"]])


def test_straight_with_offset_ports_is_connected_by_a_cross_bar() -> None:
    ports = [port("a", (2, 0), (0, -1)), port("b", (7, 10), (0, 1))]
    spec = spec_of("threshold", (10, 10), ports)
    assert spec["primitive"] == "straight" and spec["primitive_class"] == "rectilinear_polygon"


# --- real maps: invariants --------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_every_walkable_cell_has_a_valid_room(seed: int) -> None:
    document = load_json(map_path(seed))
    specs = specs_for(seed)
    walkable = {c["cell_id"]: c for c in document["cells"] if c["role"] != "void"}
    assert set(specs) == set(walkable)
    for cell_id, spec in specs.items():
        cell = walkable[cell_id]
        envelope = tuple(float(v) for v in (*cell["envelope_xz"][0], *cell["envelope_xz"][2]))
        cells = occupied_cells([tuple(r) for r in spec["rects"]])
        assert all(envelope[0] <= r[0] and envelope[1] <= r[1] and r[2] <= envelope[2] and r[3] <= envelope[3] for r in spec["rects"])
        assert is_connected(cells)
        assert spec["primitive_class"] in cell["allowed_primitives"]
        assert cell["ceiling_range_m"][0] <= spec["ceiling_height_m"] <= cell["ceiling_range_m"][1]
        assert round(spec["ceiling_height_m"] * 10) == pytest.approx(spec["ceiling_height_m"] * 10)
        assert abs(sum((r[2] - r[0]) * (r[3] - r[1]) for r in spec["rects"]) - spec["area_m2"]) < 1e-6
        for required in cell["required_ports"]:
            assert port_issues(cells, envelope, required) == []


@pytest.mark.parametrize("seed", SEEDS)
def test_doorways_follow_edges_and_record_original_status(seed: int) -> None:
    document = load_json(map_path(seed))
    connector = {}
    for edge in document["edges"]:
        connector[edge["from"]] = connector[edge["to"]] = edge["connector"]
    fill = load_json(map_path(seed).with_name(f"{map_path(seed).stem}.fill.json"))
    status = {c["cell_id"]: c["cell_status"] for c in fill["cells"]}
    for spec in specs_for(seed).values():
        assert spec["original_cell_status"] == status[spec["cell_id"]]
        for doorway in spec["doorways"]:
            expected = "open" if connector[doorway["port_id"]] == "direct" else "closed_visible"
            assert doorway["kind"] == expected and doorway["width_m"] == 2.0 and doorway["height_m"] == 2.1
        assert spec["registration_accepted"] is False and spec["scale_calibrated"] is False


@pytest.mark.parametrize("seed", SEEDS)
def test_lamps_sit_inside_the_polygon_with_inset(seed: int) -> None:
    for spec in specs_for(seed).values():
        cells = occupied_cells([tuple(r) for r in spec["rects"]])
        assert spec["lamps_xz"]
        big = max(spec["rects"], key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
        for x, z in spec["lamps_xz"]:
            assert lamp_inset_ok(cells, x, z) or [x, z] == [(big[0] + big[2]) / 2, (big[1] + big[3]) / 2]


def test_pending_mode_selects_only_pending_cells() -> None:
    specs = specs_for(1, "pending")
    assert specs and all(s["original_cell_status"] == "shape_room_pending" for s in specs.values())
    everything = specs_for(1)
    assert all(everything[cell_id] == spec for cell_id, spec in specs.items())


def test_stage_max_zero_gives_boxes_only() -> None:
    document = load_json(map_path(3))
    document["shape_stage_max"] = 0
    links = sr.edge_links(document)
    for cell in document["cells"]:
        if cell["role"] == "void":
            continue
        spec = build_spec(document, "0" * 64, cell, "shape_room_pending", links)
        assert spec["construction"] == "box" and spec["primitive_class"] == "box" and spec["shape_stage"] == 0


def test_all_features_are_symbols() -> None:
    for seed in SEEDS:
        for spec in specs_for(seed).values():
            assert spec["features"] and {f["sign"] for f in spec["features"]} == {"symbol"}


# --- determinism ------------------------------------------------------------


def test_cell_rng_uses_sha256_and_is_stable() -> None:
    digest = hashlib.sha256(b"1:c00:shape-room-0.1.0").digest()
    expected = random.Random(int.from_bytes(digest, "big"))
    assert cell_rng(1, "c00").random() == expected.random()
    assert cell_rng(1, "c00").random() != cell_rng(1, "c01").random()
    assert cell_rng(1, "c00").random() != cell_rng(2, "c00").random()


@pytest.mark.parametrize("seed", SEEDS)
def test_derivation_is_byte_identical_and_matches_committed_files(seed: int) -> None:
    assert sr.derive(map_path(seed), "all_walkable") == sr.derive(map_path(seed), "all_walkable")
    assert sr.validate(map_path(seed), "all_walkable") == []


def test_pending_files_match_committed_files() -> None:
    assert sr.validate(map_path(1), "pending") == []


def test_generate_refuses_to_overwrite_different_content(tmp_path: Path) -> None:
    sr.generate(map_path(1), "all_walkable", out_dir=tmp_path)
    again = sr.generate(map_path(1), "all_walkable", out_dir=tmp_path)
    assert again["created"] == 0
    target = tmp_path / "gmap-1-gmap-0.1.0" / "c00.json"
    target.write_text(target.read_text() + " ")
    with pytest.raises(DeterministicWriteError):
        sr.generate(map_path(1), "all_walkable", out_dir=tmp_path)


def test_validate_reports_stale_and_missing_files(tmp_path: Path) -> None:
    sr.generate(map_path(2), "all_walkable", out_dir=tmp_path)
    folder = tmp_path / "gmap-2-gmap-0.1.0"
    (folder / "c01.json").unlink()
    (folder / "c00.json").write_text("{}\n")
    errors = sr.validate(map_path(2), "all_walkable", out_dir=tmp_path)
    assert "c01.json: missing" in errors and any(e.startswith("c00.json: differs") for e in errors)


# --- schema -----------------------------------------------------------------


def schema() -> dict:
    return load_json(CATALOG / "shape_room.schema.json")


def test_schema_is_valid_and_accepts_fixture_and_generated_specs() -> None:
    Draft202012Validator.check_schema(schema())
    validator = Draft202012Validator(schema())
    assert list(validator.iter_errors(load_json(CATALOG / "schema_fixtures/shape_room.fixture.json"))) == []
    for seed in SEEDS:
        assert sr.schema_errors(ROOT / sr.OUT_DIR / f"gmap-{seed}-gmap-0.1.0", ROOT) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update(registration_accepted=True),
        lambda s: s.update(scale_calibrated=True),
        lambda s: s.update(material_source="inherited"),
        lambda s: s["features"][0].update(sign="index"),
        lambda s: s["doorways"][0].update(kind="locked"),
        lambda s: s.update(generator_version="shape-room-9"),
    ],
)
def test_schema_rejects_bad_specs(mutate) -> None:
    spec = load_json(CATALOG / "schema_fixtures/shape_room.fixture.json")
    mutate(spec)
    assert list(Draft202012Validator(schema()).iter_errors(spec))


# --- negative controls ------------------------------------------------------


ENVELOPE = (0.0, 0.0, 10.0, 10.0)


def room_issues(rects: list[tuple], ports: list[dict]) -> list[str]:
    cells = occupied_cells(rects)
    return check_room(ENVELOPE, ports, rects, cells, outline_of(cells))


def test_valid_arms_pass_all_invariants() -> None:
    ports = [port("a", (5, 0), (0, -1)), port("b", (10, 5), (1, 0))]
    assert room_issues(arm_rects(ENVELOPE, ports, 3), ports) == []


def test_control_port_without_wall_margin_fails() -> None:
    ports = [port("a", (5, 0), (0, -1)), port("b", (10, 5), (1, 0))]
    narrow = arm_rects(ENVELOPE, ports, 2)  # doorway 2 m in a 2 m arm: no solid wall beside it
    issues = room_issues(narrow, ports)
    assert any("wall margin" in issue for issue in issues)


def test_control_doorway_abutting_the_envelope_corner_is_allowed() -> None:
    envelope = (0.0, 0.0, 3.0, 10.0)
    ports = [port("a", (1, 0), (0, -1)), port("b", (3, 6), (1, 0))]
    cells = occupied_cells(arm_rects(envelope, ports, 3))
    assert all(port_issues(cells, envelope, p) == [] for p in ports)


def test_control_arm_outside_envelope_fails() -> None:
    ports = [port("a", (5, 0), (0, -1)), port("b", (10, 5), (1, 0))]
    rects = arm_rects(ENVELOPE, ports, 3) + [(9.0, 4.0, 12.0, 7.0)]
    assert any("leaves the envelope" in issue for issue in room_issues(rects, ports))


def test_control_disconnected_union_fails() -> None:
    cells = occupied_cells([(0.0, 0.0, 4.0, 4.0), (6.0, 6.0, 10.0, 10.0)])
    assert not is_connected(cells)
    with pytest.raises(RasterError):
        outline_of(cells)


def test_control_corner_touching_rectangles_are_rejected() -> None:
    with pytest.raises(RasterError):
        outline_of(occupied_cells([(0.0, 0.0, 2.0, 2.0), (2.0, 2.0, 4.0, 4.0)]))


def test_require_valid_raises_with_the_cell_id() -> None:
    with pytest.raises(ShapeRoomError, match="c07: boom"):
        require_valid("c07", ["boom"])


def test_decompose_covers_the_union_exactly() -> None:
    cells = occupied_cells([(0.0, 0.0, 6.0, 3.0), (0.0, 3.0, 3.0, 9.0)])
    parts = decompose(cells)
    assert occupied_cells(parts) == cells
    assert sum((r[2] - r[0]) * (r[3] - r[1]) for r in parts) == 36.0


def test_arm_width_range_never_exceeds_the_envelope() -> None:
    assert arm_width_range((0, 0, 3, 10)) == (3, 3)
    assert arm_width_range((0, 0, 8, 8)) == (3, 7)


def test_map_sha_is_recorded() -> None:
    spec = specs_for(1)["c00"]
    data = (MAP_DIR / "gmap-1-gmap-0.1.0.json").read_bytes()
    assert spec["map_sha256"] == hashlib.sha256(data).hexdigest()
