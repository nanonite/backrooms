"""Regression coverage for spatial declarations and scene dependency manifests."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from video_adaptation_errors import AdaptationValidationError
from video_adaptation_evidence import verify_artifacts
from video_adaptation_polygon import validate_orthogonal_polygon
from video_adaptation_scene_dependencies import validate_required_scene_dependencies
from video_adaptation_semantics import validate_static_spatial_contract
from video_adaptation_validation import ROOT

TRANSFER = ROOT / "godot_walk/room_catalog/adaptations/corridor-corner-v2.json"
REFERENCE = ROOT / "godot_walk/room_catalog/adaptations/room-large-v1.json"


def load_record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class SpatialValidationTests(unittest.TestCase):
    def test_rejects_self_intersection_and_nonorthogonal_edges(self) -> None:
        crossed = [[0, 0], [3, 0], [3, 3], [1, 3], [1, 1], [2, 1], [2, 2], [0, 2]]
        diagonal = [[0, 0], [2, 0], [2, 2], [0.2, 1.8]]
        for polygon in (crossed, diagonal):
            with (
                self.subTest(polygon=polygon),
                self.assertRaises(AdaptationValidationError),
            ):
                validate_orthogonal_polygon(polygon, "fixture")

    def test_rejects_inverted_render_bounds(self) -> None:
        record = load_record(TRANSFER)
        record["resolved_adaptation"]["rendered_placement_envelope"]["bounds_xyz"][
            "max"
        ][0] = -10
        with self.assertRaisesRegex(
            AdaptationValidationError, "inverted or degenerate"
        ):
            validate_static_spatial_contract(record)

    def test_invalid_spawn_and_socket_declarations_fail_static_checks(self) -> None:
        outside_spawn = copy.deepcopy(load_record(TRANSFER))
        outside_spawn["resolved_adaptation"]["walkable_space"]["safe_spawn_xyz"][0] = (
            100
        )
        with self.assertRaisesRegex(AdaptationValidationError, "Safe spawn"):
            validate_static_spatial_contract(outside_spawn)
        bad_socket = load_record(REFERENCE)
        bad_socket["resolved_adaptation"]["sockets"][0]["outward_normal_xyz"] = [
            2,
            0,
            0,
        ]
        with self.assertRaisesRegex(AdaptationValidationError, "normalized horizontal"):
            validate_static_spatial_contract(bad_socket)

    def test_v3_authored_sockets_require_perimeter_edges_and_outward_normals(
        self,
    ) -> None:
        interior = _v3_spatial_record()
        interior["resolved_adaptation"]["sockets"] = [
            _authored_socket([0, 0, 0], [1, 0, 0], EAST_APPROACH)
        ]
        with self.assertRaisesRegex(AdaptationValidationError, "perimeter edge"):
            validate_static_spatial_contract(interior)

        reversed_normal = _v3_spatial_record()
        reversed_normal["resolved_adaptation"]["sockets"] = [
            _authored_socket([3, 0, 0], [-1, 0, 0], EAST_APPROACH)
        ]
        with self.assertRaisesRegex(
            AdaptationValidationError, "does not point outward"
        ):
            validate_static_spatial_contract(reversed_normal)

    def test_v3_socket_opening_must_fit_strictly_inside_one_edge(self) -> None:
        for center, width in (([3, 0, 1.7], 1.2), ([3, 0, 0], 6.2)):
            record = _v3_spatial_record()
            record["resolved_adaptation"]["sockets"] = [
                _authored_socket(center, [1, 0, 0], EAST_APPROACH, width=width)
            ]
            with (
                self.subTest(center=center, width=width),
                self.assertRaisesRegex(AdaptationValidationError, "perimeter corner"),
            ):
                validate_static_spatial_contract(record)

    def test_v3_approach_region_must_stay_inside_concave_footprint(self) -> None:
        concave = [[-3, -2], [3, -2], [3, -1], [0, -1], [0, 2], [-3, 2]]
        record = _v3_spatial_record(concave)
        record["resolved_adaptation"]["walkable_space"]["safe_spawn_xyz"] = [-1, 0.6, 0]
        record["resolved_adaptation"]["rendered_placement_envelope"]["footprint"][
            "vertices_xz"
        ] = concave
        record["resolved_adaptation"]["sockets"] = [
            _authored_socket(
                [3, 0, -1.5],
                [1, 0, 0],
                [[0.5, 0.1], [1.1, 0.1], [1.1, 0.7], [0.5, 0.7]],
                width=0.8,
            )
        ]
        with self.assertRaisesRegex(
            AdaptationValidationError, "leaves its supporting footprint"
        ):
            validate_static_spatial_contract(record)

    def test_v3_room_clearance_must_cover_player_and_socket_height(self) -> None:
        record = _v3_spatial_record()
        record["resolved_adaptation"]["room_clearance"]["ceiling_elevation"] = 1.0
        with self.assertRaisesRegex(AdaptationValidationError, "below capsule height"):
            validate_static_spatial_contract(record)

        record = _v3_spatial_record()
        record["resolved_adaptation"]["sockets"] = [
            _authored_socket([3, 0, 0], [1, 0, 0], EAST_APPROACH, height=3.1)
        ]
        with self.assertRaisesRegex(
            AdaptationValidationError, "exceeds declared room clearance"
        ):
            validate_static_spatial_contract(record)

    def test_observed_opening_cannot_be_promoted_to_a_gameplay_connector(self) -> None:
        record = _v3_spatial_record()
        record["resolved_adaptation"]["sockets"] = [
            {
                "id": "observed-only",
                "kind": "observed_opening",
                "status": "source_observation_only",
                "closure_behavior": "Evidence only.",
                "tested_connection_ref": "layout:doorway",
            }
        ]
        with self.assertRaisesRegex(
            AdaptationValidationError, "cannot declare a gameplay connector"
        ):
            validate_static_spatial_contract(record)

    def test_v3_valid_socket_frames_work_on_all_four_orientations(self) -> None:
        cases = (
            ([3, 0, 0], [1, 0, 0], EAST_APPROACH),
            ([-3, 0, 0], [-1, 0, 0], WEST_APPROACH),
            ([0, 0, 2], [0, 0, 1], NORTH_APPROACH),
            ([0, 0, -2], [0, 0, -1], SOUTH_APPROACH),
        )
        for center, normal, approach in cases:
            record = _v3_spatial_record()
            record["resolved_adaptation"]["sockets"] = [
                _authored_socket(center, normal, approach)
            ]
            with self.subTest(center=center):
                validate_static_spatial_contract(record)


class SceneDependencyTests(unittest.TestCase):
    def test_scene_files_and_external_scene_resources_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = self._scene_fixture(root)
            snapshot = {"modules": []}
            record["resolved_adaptation"]["scene_path"] = "godot_walk/missing.tscn"
            with self.assertRaisesRegex(
                AdaptationValidationError, "Missing repository file"
            ):
                validate_required_scene_dependencies(record, snapshot, root)
            record = self._scene_fixture(root)
            record["resolved_adaptation"]["dependencies"] = [
                item
                for item in record["resolved_adaptation"]["dependencies"]
                if item["path"] != "godot_walk/scripts/room.gd"
            ]
            with self.assertRaisesRegex(AdaptationValidationError, "not fingerprinted"):
                validate_required_scene_dependencies(record, snapshot, root)

    def test_scene_references_reject_absolute_and_traversal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = self._scene_fixture(root)
            for scene in ("/tmp/room.tscn", "godot_walk/../room.tscn"):
                record["resolved_adaptation"]["scene_path"] = scene
                with (
                    self.subTest(scene=scene),
                    self.assertRaises(AdaptationValidationError),
                ):
                    validate_required_scene_dependencies(record, {"modules": []}, root)

    def _scene_fixture(self, root: Path) -> dict:
        resources = {
            "godot_walk/room.tscn": '[ext_resource type="Script" path="res://scripts/room.gd" id="1"]\n',
            "godot_walk/player.tscn": '[ext_resource type="Script" path="res://scripts/player.gd" id="1"]\n',
            "godot_walk/scripts/room.gd": "extends Node3D\n",
            "godot_walk/scripts/player.gd": "extends CharacterBody3D\n",
        }
        for relative, content in resources.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return {
            "resolved_adaptation": {
                "scene_path": "godot_walk/room.tscn",
                "catalog_module_refs": [],
                "dependencies": [{"path": path} for path in resources],
            },
            "reusable_requirements": {
                "player": {"controller_scene": "godot_walk/player.tscn"}
            },
        }


class ArtifactHashTests(unittest.TestCase):
    def test_tampered_referenced_dependency_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dependency = root / "scene.tscn"
            dependency.write_text("original", encoding="utf-8")
            expected = hashlib.sha256(dependency.read_bytes()).hexdigest()
            dependency.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(AdaptationValidationError, "Hash mismatch"):
                verify_artifacts([{"path": "scene.tscn", "sha256": expected}], root)


def _v3_spatial_record(polygon: list[list[int]] | None = None) -> dict:
    vertices = polygon or RECTANGLE
    record = load_record(TRANSFER)
    resolved = record["resolved_adaptation"]
    record["schema_version"] = 3
    resolved["walkable_space"]["footprint"]["vertices_xz"] = vertices
    resolved["walkable_space"]["floor_elevation"] = 0
    resolved["walkable_space"]["safe_spawn_xyz"] = [0, 0.6, 0]
    resolved["rendered_placement_envelope"]["footprint"]["vertices_xz"] = vertices
    minimum_x = min(point[0] for point in vertices)
    maximum_x = max(point[0] for point in vertices)
    minimum_z = min(point[1] for point in vertices)
    maximum_z = max(point[1] for point in vertices)
    resolved["rendered_placement_envelope"]["bounds_xyz"] = {
        "min": [minimum_x - 0.1, -0.1, minimum_z - 0.1],
        "max": [maximum_x + 0.1, 3.1, maximum_z + 0.1],
    }
    resolved["room_clearance"] = {
        "floor_elevation": 0,
        "ceiling_elevation": 3,
        "basis": "authored",
    }
    return record


def _authored_socket(
    center: list[float],
    normal: list[float],
    approach: list[list[float]],
    *,
    width: float = 1.2,
    height: float = 2.4,
) -> dict:
    return {
        "id": "socket-test",
        "kind": "authored_doorway",
        "status": "open_untested",
        "local_floor_center_xyz": center,
        "outward_normal_xyz": normal,
        "clear_size": [width, height],
        "approach_clearance": 0.8,
        "floor_elevation": 0,
        "approach_region_xz": {
            "representation": "simple_orthogonal_polygon_xz",
            "vertices_xz": approach,
        },
        "closure_behavior": "Closed by authored wall panel when unused.",
    }


RECTANGLE = [[-3, -2], [3, -2], [3, 2], [-3, 2]]
EAST_APPROACH = [[2.2, -0.6], [2.7, -0.6], [2.7, 0.6], [2.2, 0.6]]
WEST_APPROACH = [[-2.7, -0.6], [-2.2, -0.6], [-2.2, 0.6], [-2.7, 0.6]]
NORTH_APPROACH = [[-0.6, 1.2], [0.6, 1.2], [0.6, 1.7], [-0.6, 1.7]]
SOUTH_APPROACH = [[-0.6, -1.7], [0.6, -1.7], [0.6, -1.2], [-0.6, -1.2]]


if __name__ == "__main__":
    unittest.main()
