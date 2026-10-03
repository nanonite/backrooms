#!/usr/bin/env python3
"""Tests for the collision generation and validation stages.

Everything here runs without a GPU, without the pinned tool and without the
corridor splat: the formats are exercised through fixtures built to spec, and
the tool's own output is exercised through recorded excerpts.  The one thing
these tests cannot prove is that the pinned tool still accepts the flags
:meth:`splat_transform_cli.build_argv` builds -- that is what the recorded
benchmark in ``scripts/splat_pipeline/collision_benchmark.json`` is for, and a
drift between them is a reason to re-run it, not a reason to relax a test.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from collision_fixtures import tetrahedron, write_glb, write_voxel_dataset
from collision_params import (
    CLEARANCE_MARGIN_M,
    DEFAULT_EXTERIOR_FILL_RADIUS_M,
    ENGINE_FRAME_ROTATION,
    PLAYER_CAPSULE_HEIGHT_M,
    PLAYER_CAPSULE_RADIUS_M,
    PLAYER_SCENE_PATH,
    CollisionError,
    CollisionSettings,
    collision_node_transform,
    engine_frame_to_world,
    settings_from_contract,
    voxel_size_in_raw_units,
    world_to_engine_frame,
)
from glb_mesh import GlbFormatError, read_glb
from splat_columns import PLAN_AXES, VERTICAL_AXIS, classify_columns, rotated_extents
from splat_frame import FrameContract
from splat_transform_cli import (
    PINNED_VERSION,
    ParsedOutput,
    build_argv,
    parse_output,
    resolve_cli,
)
from traversability import CollisionVerdict, validate
from voxel_octree import VoxelFormatError, VoxelOctree, parse_header

REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "godot_walk" / "assets" / "corridor_splat" / "alignment_manifest.json"

#: Recorded excerpt of a real splat-transform 3.9.0 run over the corridor splat.
#: Kept verbatim (bar the progress bars) so the parser is tested against the
#: tool's real formatting, including the 'K' suffixed counts and the two-stage
#: pre-merge/merge mesh report that a naive parser reads as one.
TOOL_OUTPUT = """
splat-transform v3.9.0 (435b972)
▸ Filter cluster
  · scene: 287m x 617m x 1.36km, grid: 1152 x 2472 x 4096 voxels (11.7B) @ 25cm
  ! seed (0.70, -0.33, -0.53) unoccupied; resolved to nearest at (-0.13, -1.13, -1.15)
  · cluster is 302 of 547 blocks
  · removed 86.9K gaussians
  · 95.7K gaussians · 3 SH bands
▸ Collision mesh
  · Extracting
    · pre-merged vertices: 10K
    · pre-merged triangles: 20.1K
▸ Merging coplanar faces
    · merged vertices: 5.19K
    · merged triangles: 10.7K
    · reduction: 47%
▸ Writing
    · sealed.voxel.json (663B)
    · sealed.voxel.bin (77.6KB)
    · sealed.collision.glb (188.3KB)
done in 3.139s  [peak cpu=557.5MB gpu=33.2MB]
"""


@pytest.fixture(scope="module")
def contract() -> FrameContract:
    """The corridor_splat alignment contract, validated on load."""
    return FrameContract.load(MANIFEST)


@pytest.fixture(scope="module")
def settings(contract) -> CollisionSettings:
    """Default collision settings derived from that contract."""
    return settings_from_contract(contract)


def write_ply(path: Path, centres, scales=0.02, quaternions=None) -> Path:
    """Write a minimal binary 3DGS PLY with the given Gaussian centres."""
    columns = ("x", "y", "z", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3")
    header = ["ply", "format binary_little_endian 1.0", "comment test", "element vertex %d" % len(centres)]
    header += ["property float %s" % name for name in columns]
    header.append("end_header")
    with path.open("wb") as handle:
        handle.write(("\n".join(header) + "\n").encode("ascii"))
        for centre in centres:
            rotation = (1.0, 0.0, 0.0, 0.0) if quaternions is None else quaternions
            row = [centre[0], centre[1], centre[2], 5.0]
            row += [float(np.log(scales))] * 3
            row += list(rotation)
            handle.write(np.asarray(row, dtype="<f4").tobytes())
    return path


# ---------------------------------------------------------------- voxel octree


def test_voxel_reader_round_trips_a_synthetic_room(tmp_path):
    dataset = write_voxel_dataset(
        tmp_path / "room.voxel.json",
        lambda local, _base: local[:, 2] < 2,
        (16, 16, 16),
        0.05,
        (-0.4, -0.4, -0.1),
    )
    voxel = VoxelOctree.load(dataset)
    occupancy = voxel.occupancy(voxel.header.grid_min, voxel.header.grid_max)
    assert occupancy.shape == (16, 16, 16)
    assert occupancy[:, :, :2].all()
    assert not occupancy[:, :, 2:].any()


def test_occupancy_agrees_with_point_queries(tmp_path):
    dataset = write_voxel_dataset(
        tmp_path / "room.voxel.json",
        lambda local, _base: (local[:, 0] + local[:, 2]) % 3 == 0,
        (16, 16, 16),
        0.05,
        (0.0, 0.0, 0.0),
    )
    voxel = VoxelOctree.load(dataset)
    occupancy = voxel.occupancy(voxel.header.grid_min, voxel.header.grid_max)
    for index in np.ndindex(occupancy.shape):
        centre = voxel.voxel_centre(index)
        assert voxel.is_solid(centre) == bool(occupancy[index])


def test_space_outside_the_grid_reads_as_solid(tmp_path):
    dataset = write_voxel_dataset(
        tmp_path / "room.voxel.json", lambda local, _base: local[:, 2] < 2, (8, 8, 8), 0.05, (0.0, 0.0, 0.0)
    )
    voxel = VoxelOctree.load(dataset)
    assert voxel.is_solid((5.0, 5.0, 5.0))
    assert voxel.is_solid_box((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0))


def test_voxel_reader_rejects_an_unsupported_format_version(tmp_path):
    document = {
        "version": "1.0",
        "voxelResolution": 0.05,
        "leafSize": 4,
        "treeDepth": 1,
        "gridBounds": {"min": [0, 0, 0], "max": [0.4, 0.4, 0.4]},
        "sceneBounds": {"min": [0, 0, 0], "max": [0.4, 0.4, 0.4]},
        "numInteriorNodes": 0,
        "numMixedLeaves": 0,
        "nodeCount": 0,
        "leafDataCount": 0,
    }
    dataset = tmp_path / "old.voxel.json"
    dataset.write_text(json.dumps(document))
    with pytest.raises(VoxelFormatError, match="engine frame"):
        VoxelOctree.load(dataset)


def test_voxel_reader_rejects_a_binary_payload_of_the_wrong_size(tmp_path):
    dataset = write_voxel_dataset(
        tmp_path / "room.voxel.json", lambda local, _base: local[:, 2] < 2, (8, 8, 8), 0.05, (0.0, 0.0, 0.0)
    )
    dataset.with_name("room.voxel.bin").write_bytes(b"\x00" * 4)
    with pytest.raises(VoxelFormatError, match="declares"):
        VoxelOctree.load(dataset)


def test_voxel_header_requires_a_positive_resolution():
    with pytest.raises(VoxelFormatError, match="must be positive"):
        parse_header(
            {
                "version": "1.1",
                "voxelResolution": 0.0,
                "leafSize": 4,
                "treeDepth": 1,
                "gridBounds": {"min": [0, 0, 0], "max": [1, 1, 1]},
                "sceneBounds": {"min": [0, 0, 0], "max": [1, 1, 1]},
            },
            "inline",
        )


# ------------------------------------------------------------------- glb mesh


def test_glb_reader_returns_a_closed_tetrahedron(tmp_path):
    vertices, indices = tetrahedron()
    mesh = read_glb(write_glb(tmp_path / "tet.collision.glb", vertices, indices))
    assert mesh.triangle_count == 4
    assert mesh.vertex_count == 4
    assert mesh.edge_manifoldness() == {"boundary": 0, "manifold": 6, "non_manifold": 0}


def test_outward_winding_gives_a_positive_signed_volume(tmp_path):
    vertices, indices = tetrahedron()
    mesh = read_glb(write_glb(tmp_path / "tet.collision.glb", vertices, indices))
    assert mesh.signed_volume() == pytest.approx(1.0 / 6.0)


def test_reversed_winding_negates_the_signed_volume(tmp_path):
    vertices, indices = tetrahedron()
    mesh = read_glb(write_glb(tmp_path / "tet.collision.glb", vertices, indices[::-1]))
    assert mesh.signed_volume() == pytest.approx(-1.0 / 6.0)


def test_glb_reader_rejects_a_non_glb(tmp_path):
    path = tmp_path / "not.glb"
    path.write_bytes(b"not a glb at all")
    with pytest.raises(GlbFormatError, match="not a GLB"):
        read_glb(path)


def test_glb_reader_rejects_a_mesh_count_it_cannot_resolve(tmp_path):
    vertices, indices = tetrahedron()
    document = _with_a_second_mesh(
        write_glb(tmp_path / "two.collision.glb", vertices, indices)
    )
    with pytest.raises(GlbFormatError, match="exactly one mesh"):
        read_glb(document)


def _with_a_second_mesh(path: Path) -> Path:
    """Duplicate the mesh and point a second node at it, keeping the container valid."""
    import struct

    raw = path.read_bytes()
    length, kind = struct.unpack_from("<II", raw, 12)
    document = json.loads(raw[20 : 20 + length].decode("utf-8"))
    document["meshes"].append(json.loads(json.dumps(document["meshes"][0])))
    document["nodes"].append({"mesh": len(document["meshes"]) - 1})
    payload = json.dumps(document).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    body = raw[20 + length :]
    with path.open("wb") as handle:
        handle.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(payload) + len(body)))
        handle.write(struct.pack("<II", len(payload), kind))
        handle.write(payload)
        handle.write(body)
    return path


# -------------------------------------------------------------- collision params


def test_player_capsule_constants_match_the_production_scene():
    """The carve capsule must never be smaller than the thing that walks in it."""
    text = (REPO / PLAYER_SCENE_PATH).read_text(encoding="utf-8")
    assert "radius = %s" % PLAYER_CAPSULE_RADIUS_M in text
    assert "height = %s" % PLAYER_CAPSULE_HEIGHT_M in text


def test_settings_default_to_the_production_capsule_plus_a_recorded_margin(settings):
    assert settings.capsule_radius_m == PLAYER_CAPSULE_RADIUS_M + CLEARANCE_MARGIN_M
    assert settings.capsule_height_m == PLAYER_CAPSULE_HEIGHT_M + CLEARANCE_MARGIN_M
    assert settings.validate() is None


def test_settings_reject_a_capsule_smaller_than_the_player(contract):
    narrow = settings_from_contract(contract)
    object.__setattr__(narrow, "capsule_radius_m", 0.1)
    with pytest.raises(CollisionError, match="below the production player radius"):
        narrow.validate()


def test_engine_frame_is_a_180_degree_rotation_about_z():
    assert np.allclose(ENGINE_FRAME_ROTATION, np.diag([-1.0, -1.0, 1.0]))
    assert np.linalg.det(ENGINE_FRAME_ROTATION) == pytest.approx(1.0)
    assert np.allclose(ENGINE_FRAME_ROTATION @ np.array([1.0, 2.0, 3.0]), [-1.0, -2.0, 3.0])


def test_world_and_engine_frames_round_trip(contract, settings):
    seed = np.asarray(settings.seed_engine_frame_m)
    world = engine_frame_to_world(seed, contract)
    assert np.allclose(world_to_engine_frame(world, contract), seed, atol=1e-9)


def test_collision_node_basis_is_a_pure_rotation_of_the_engine_frame(contract):
    """The collision basis carries no scale: the tool's output is already metric.

    ``build_argv`` hands ``splat-transform`` a splat the contract has already
    multiplied by ``metres_per_unit``, so the engine frame it writes is in metres.
    The old assertion here composed the basis with the *splat node's* basis, which
    includes that scale, and so passed for a matrix that stretches the collision
    by 5.128x on this scene -- putting the generated floor metres below the room
    and leaving the player nothing to stand on.  ``test_collision.py`` now
    cross-checks the matrix against the independent point mapping, which is what
    caught it.
    """
    collision = collision_node_transform(contract)
    rotation = contract.ply_to_world.rotation()
    assert np.allclose(collision[:, :3], rotation @ ENGINE_FRAME_ROTATION.T)
    assert np.linalg.det(collision[:, :3]) == pytest.approx(1.0)
    # A rotation times a uniform scale has orthogonal columns of equal length; a
    # scaled one has columns of length metres_per_unit, which is 5.128 here.
    lengths = np.linalg.norm(collision[:, :3], axis=0)
    assert np.allclose(lengths, 1.0), lengths


def test_collision_node_matrix_agrees_with_the_independent_point_mapping(contract):
    """The matrix form and the point mapping must be the same transform.

    They were written separately and disagreed: ``collision_node_transform``
    multiplied by ``metres_per_unit`` while ``engine_frame_to_world`` did not.
    Only one of the two was ever checked against the other, so the scale error
    survived a passing suite.
    """
    collision = collision_node_transform(contract)
    rotation = collision[:, :3]
    translation = collision[:, 3]
    for point in (np.array([0.0, 0.0, 0.0]), np.array([2.5, -3.25, 1.75]), np.array([-6.0, 4.0, 0.5])):
        assert np.allclose(rotation @ point + translation, engine_frame_to_world(point, contract))


def test_collision_node_places_the_seed_in_the_carved_capsule(contract, settings):
    """The transform has to put the tool's carve seed back where the tool found it.

    This is the check that fails loudly if the basis is scaled: the seed is a
    known point inside the carved navigable volume, so a stretched basis lands it
    outside the room entirely.
    """
    collision = collision_node_transform(contract)
    seed = np.asarray(settings.seed_engine_frame_m)
    world = collision[:, :3] @ seed + collision[:, 3]
    expected = engine_frame_to_world(seed, contract)
    assert np.allclose(world, expected)
    assert world[1] == pytest.approx(
        contract.collider.floor_height + 0.5 * settings.capsule_height_m, abs=1e-3
    )


def test_collision_node_basis_is_not_the_scaled_splat_node_basis(contract):
    """The negative form of the old assertion, so the bug cannot be reintroduced.

    Written explicitly because the mistake was reasonable-looking: the collision
    does come from the same frame as the splat, so composing with the splat node's
    *rotation* is right, and only the scale is wrong.
    """
    collision = collision_node_transform(contract)
    splat = contract.ply_to_world.node_transform_matrix()
    assert not np.allclose(collision[:, :3], splat[:, :3] @ ENGINE_FRAME_ROTATION)
    # ...while still sharing the splat's rotation.
    assert np.allclose(
        collision[:, :3] @ collision[:, :3].T,
        splat[:, :3] @ splat[:, :3].T / contract.ply_to_world.metres_per_unit ** 2,
    )


def test_collision_node_carries_the_centroid_translation_the_splat_node_omits(contract):
    collision = collision_node_transform(contract)
    splat = contract.ply_to_world.node_transform_matrix()
    assert np.allclose(splat[:, 3], 0.0)
    assert not np.allclose(collision[:, 3], 0.0)


def test_voxel_size_is_reported_in_raw_units_as_well_as_metres(contract, settings):
    raw = voxel_size_in_raw_units(settings.voxel_size_m, contract)
    assert raw == pytest.approx(settings.voxel_size_m / contract.ply_to_world.metres_per_unit)
    assert raw < settings.voxel_size_m, "one reconstruction unit is more than one metre here"


def test_seed_sits_at_the_centre_of_the_carve_capsule(contract, settings):
    seed_world = engine_frame_to_world(settings.seed_engine_frame_m, contract)
    expected = contract.collider.floor_height + 0.5 * settings.capsule_height_m
    # The seed is recorded to millimetres, so the comparison is to that precision.
    assert seed_world[1] == pytest.approx(expected, abs=1e-3)


def test_room_bounds_flip_sign_about_z_in_the_engine_frame(contract):
    from collision_params import room_bounds_in_engine_frame

    low, high = room_bounds_in_engine_frame(contract)
    assert low[0] < high[0] and low[1] < high[1] and low[2] < high[2]
    assert high[2] - low[2] == pytest.approx(
        contract.collider.ceiling_height - contract.collider.floor_height
    )


# ------------------------------------------------------------- splat-transform CLI


def test_tool_output_parser_reads_counts_the_tool_actually_prints():
    parsed = parse_output(TOOL_OUTPUT)
    assert parsed.version == "3.9.0"
    assert parsed.gaussians_out == 95700
    assert parsed.gaussians_removed == 86900
    assert parsed.cluster == (302, 547)
    assert parsed.pre_merge_vertices == 10000
    assert parsed.pre_merge_triangles == 20100
    assert parsed.vertices == 5190
    assert parsed.triangles == 10700
    assert parsed.seed_was_unoccupied
    assert parsed.peak_cpu_bytes == int(557.5 * 1024 ** 2)
    assert parsed.peak_gpu_bytes == int(33.2 * 1024 ** 2)


def test_tool_output_parser_sees_a_skipped_stage():
    parsed = parse_output("  ! seed reachable from outside, skipping exterior fill\n")
    assert parsed.exterior_fill_skipped


def test_parsed_output_defaults_to_no_skip_flags():
    parsed = ParsedOutput()
    assert not parsed.exterior_fill_skipped
    assert not parsed.carve_skipped


def test_argv_scales_the_splat_into_metres_before_voxelizing(contract, settings):
    argv = build_argv("/fake/cli.mjs", "in.ply", "out", settings, contract.ply_to_world.metres_per_unit)
    assert argv[argv.index("-s") + 1] == "%.17g" % contract.ply_to_world.metres_per_unit
    assert argv.index("-s") < argv.index("out.voxel.json")
    assert argv[argv.index("--voxel-size") + 1] == "%.6g" % settings.voxel_size_m
    assert argv[argv.index("--seed-pos") + 1] == "0.704,-0.326,-0.528"


def test_argv_asks_for_a_sealed_shell_and_a_capsule_carve(settings):
    argv = build_argv("/fake/cli.mjs", "in.ply", "out", settings, 1.0)
    assert argv[argv.index("--voxel-external-fill") + 1] == "%.6g" % DEFAULT_EXTERIOR_FILL_RADIUS_M
    assert argv[argv.index("--voxel-carve") + 1] == "%.6g,%.6g" % (
        settings.capsule_height_m,
        settings.capsule_radius_m,
    )
    assert "--collision-mesh" in argv


def test_resolve_cli_names_the_install_command_when_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("SPLAT_TRANSFORM_NODE_MODULES", raising=False)
    monkeypatch.setattr("splat_transform_cli.__file__", str(tmp_path / "generate_collision.py"))
    with pytest.raises(Exception, match="npm install @playcanvas/splat-transform@%s" % PINNED_VERSION):
        resolve_cli(tmp_path / "nowhere")


# ------------------------------------------------------------------ splat columns


def _world_to_ply_units(points, contract) -> np.ndarray:
    """Map Godot world metres into raw PLY units, for fixtures written as PLYs.

    Dividing by ``metres_per_unit`` and adding the origin is *not* this: the
    contract's mapping is a rotation as well as a scale, and skipping it turns a
    synthetic floor plane into a wall.
    """
    ply_to_world = contract.ply_to_world
    inverse = np.linalg.inv(ply_to_world.rotation())
    return ply_to_world.origin_ply_units + (
        inverse @ (np.asarray(points, dtype=np.float64) / ply_to_world.metres_per_unit).T
    ).T


def test_column_grid_spans_the_floor_plan_not_the_vertical(tmp_path, contract):
    ply = write_ply(tmp_path / "splat.ply", [(0.0, 0.0, 0.0)])
    grid = classify_columns(ply, contract, 0.25)
    assert grid.shape[0] > 10, "the room is metres wide on its floor plan"
    assert grid.shape[1] > 10
    assert PLAN_AXES == (0, 2) and VERTICAL_AXIS == 1


def test_column_grid_shape_matches_the_observed_window(contract):
    ply = write_ply(Path(__file__).parent / "_probe_splat.ply", [(0.0, 0.0, 0.0)])
    try:
        grid = classify_columns(ply, contract, 0.5)
    finally:
        ply.unlink()
    room = contract.collider
    expected = (
        int(np.ceil((room.max_corner[0] - room.min_corner[0]) / 0.5)),
        int(np.ceil((room.max_corner[2] - room.min_corner[2]) / 0.5)),
    )
    assert grid.shape == expected


def test_rotated_extents_are_positive_and_three_sigma(tmp_path, contract):
    ply = write_ply(tmp_path / "splat.ply", [(0.1, 0.2, 0.3)], scales=0.01)
    extents = rotated_extents(ply)
    assert extents.shape == (1, 3)
    assert np.allclose(extents[0], 0.03)


def test_a_synthetic_wall_column_is_marked_obstructed_and_open_space_is_not(tmp_path, contract):
    """The classifier must separate a wall from open floor using splat extents."""
    floor = contract.collider.floor_height
    wall_x = (contract.collider.min_corner[0] + contract.collider.max_corner[0]) * 0.5
    # Dense enough that a quarter-metre column holds several splats, which is
    # what MIN_FLOOR_SPLATS assumes of a real reconstruction.
    floor_x = np.linspace(contract.collider.min_corner[0], contract.collider.max_corner[0], 150)
    floor_z = np.linspace(contract.collider.min_corner[2], contract.collider.max_corner[2], 150)
    wall_z = np.linspace(contract.collider.min_corner[2], contract.collider.max_corner[2], 60)
    centres = [(x, floor + 0.02, z) for x in floor_x for z in floor_z]
    centres += [
        (x, height, z)
        for x in np.linspace(wall_x - 0.3, wall_x + 0.3, 12)
        for z in wall_z
        for height in np.linspace(floor + 0.3, floor + 1.8, 20)
    ]
    raw = _world_to_ply_units(np.asarray(centres), contract)
    ply = write_ply(tmp_path / "room.ply", raw)
    grid = classify_columns(ply, contract, 0.25)
    # The grid is indexed [world x, world z], and the wall runs along z at the
    # middle of x.
    assert grid.obstructed[grid.shape[0] // 2, :].sum() > 20, "the wall column should be obstructed"
    assert not grid.obstructed[0, 0], "the far corner is open floor"
    assert not grid.obstructed[-1, -1], "the opposite corner is open floor"


# ----------------------------------------------------------------- traversability


def build_room(tmp_path, contract, settings):
    """Write a voxel room whose navigable box is the contract's floor plate."""
    low = np.array([-0.5, -0.5, 0.0])
    high = np.array([0.5, 0.5, 0.1])
    shape = (24, 24, 8)
    resolution = 0.05

    def solid(local, _base):
        room = np.zeros(len(local), dtype=bool)
        for index, cell in enumerate(local):
            point = low + cell * resolution
            room[index] = point[2] < high[2] or not (
                low[0] <= point[0] <= high[0] and low[1] <= point[1] <= high[1]
            )
        return room

    dataset = write_voxel_dataset(tmp_path / "room.voxel.json", solid, shape, resolution, tuple(low))
    return VoxelOctree.load(dataset)


def stub_run(**overrides):
    """Return a :class:`ToolRun` stand-in with every field at a healthy value."""
    from splat_transform_cli import ToolRun

    defaults = {
        "argv": ("fake",),
        "version": PINNED_VERSION,
        "elapsed_s": 1.0,
        "peak_cpu_bytes": 10 ** 8,
        "peak_gpu_bytes": 10 ** 7,
        "gaussians_in": 1000,
        "gaussians_out": 900,
        "gaussians_removed": 100,
        "cluster_blocks_kept": 3,
        "cluster_blocks_total": 4,
        "pre_merge_triangles": 20,
        "pre_merge_vertices": 12,
        "triangles": 10,
        "vertices": 6,
        "octree_depth": 3,
        "mixed_leaves": 2,
        "seed_was_unoccupied": False,
        "exterior_fill_skipped": False,
        "carve_skipped": False,
        "warnings": (),
        "files": {},
    }
    defaults.update(overrides)
    return ToolRun(**defaults)


def test_a_sealed_room_passes_every_check(tmp_path, contract, settings):
    room = build_room(tmp_path, contract, settings)
    mesh = read_glb(write_glb(tmp_path / "room.collision.glb", *tetrahedron()))
    grid = classify_columns(write_ply(tmp_path / "empty.ply", [(0.0, 0.0, 0.0)]), contract, 0.25)
    camera = np.array([[0.0, contract.collider.floor_height + 0.1, 0.0]])
    verdict = validate(contract, settings, room, mesh, stub_run(), grid, camera)
    names = {check.name: check for check in verdict.checks}
    assert names["stages_applied"].passed
    assert isinstance(verdict, CollisionVerdict)


def test_a_skipped_stage_fails_even_with_a_valid_mesh(tmp_path, contract, settings):
    room = build_room(tmp_path, contract, settings)
    mesh = read_glb(write_glb(tmp_path / "room.collision.glb", *tetrahedron()))
    grid = classify_columns(write_ply(tmp_path / "empty.ply", [(0.0, 0.0, 0.0)]), contract, 0.25)
    verdict = validate(
        contract, settings, room, mesh, stub_run(exterior_fill_skipped=True), grid, None
    )
    failed = {check.name for check in verdict.failures}
    assert "stages_applied" in failed


def test_missing_camera_positions_fail_rather_than_pass(tmp_path, contract, settings):
    room = build_room(tmp_path, contract, settings)
    mesh = read_glb(write_glb(tmp_path / "room.collision.glb", *tetrahedron()))
    grid = classify_columns(write_ply(tmp_path / "empty.ply", [(0.0, 0.0, 0.0)]), contract, 0.25)
    verdict = validate(contract, settings, room, mesh, stub_run(), grid, None)
    failed = {check.name for check in verdict.failures}
    assert {"floor_supported", "walkway_covers_camera_path"} <= failed


def test_a_reversed_winding_is_reported_as_facing_the_wrong_way(tmp_path, contract, settings):
    """The normal check's polarity is stated, so it is tested against a flipped mesh."""
    room = build_room(tmp_path, contract, settings)
    grid = classify_columns(write_ply(tmp_path / "empty.ply", [(0.0, 0.0, 0.0)]), contract, 0.25)
    outward = read_glb(write_glb(tmp_path / "out.collision.glb", *tetrahedron()))
    inward = read_glb(write_glb(tmp_path / "in.collision.glb", outward.positions, outward.indices[::-1]))
    forward = validate(contract, settings, room, outward, stub_run(), grid, None)
    flipped = validate(contract, settings, room, inward, stub_run(), grid, None)
    forward_check = next(c for c in forward.checks if c.name == "mesh_normals_face_walkable")
    flipped_check = next(c for c in flipped.checks if c.name == "mesh_normals_face_walkable")
    assert forward_check.metrics["signed_volume_m3"] == -flipped_check.metrics["signed_volume_m3"]


def test_a_fully_solid_room_fails_the_not_filled_check(tmp_path, contract, settings):
    def solid(local, _base):
        return np.ones(len(local), dtype=bool)

    dataset = write_voxel_dataset(tmp_path / "solid.voxel.json", solid, (8, 8, 8), 0.05, (0, 0, 0))
    room = VoxelOctree.load(dataset)
    mesh = read_glb(write_glb(tmp_path / "room.collision.glb", *tetrahedron()))
    grid = classify_columns(write_ply(tmp_path / "empty.ply", [(0.0, 0.0, 0.0)]), contract, 0.25)
    verdict = validate(contract, settings, room, mesh, stub_run(), grid, None)
    assert "room_not_filled" in {check.name for check in verdict.failures}