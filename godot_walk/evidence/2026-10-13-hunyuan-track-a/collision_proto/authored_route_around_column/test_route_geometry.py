"""Focused CPU tests for the authored route geometry and GLB container."""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from collision_meshes import floor_ring_mesh
from glb_writer import build_glb
from route_geometry import (
    capsule_route_check,
    distance_to_bounds,
    make_route_geometry,
)
from route_source import fit_camera_circle


def test_circle_fit_recovers_center_and_radius() -> None:
    angles = np.linspace(0.0, 2.0 * np.pi, 64, endpoint=False)
    center = np.array([-0.7, 0.75])
    points = center + 4.7 * np.column_stack((np.cos(angles), np.sin(angles)))

    fitted_center, radius, residuals = fit_camera_circle(points)

    assert np.allclose(fitted_center, center)
    assert radius == pytest.approx(4.7)
    assert np.max(np.abs(residuals)) < 1e-12


def test_circle_fit_rejects_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="at least three"):
        fit_camera_circle(np.zeros((2, 2)))
    with pytest.raises(ValueError, match="at least three"):
        fit_camera_circle(np.zeros((3, 3)))


def test_floor_ring_has_continuous_upward_faces() -> None:
    vertices, faces = floor_ring_mesh(np.array([1.0, -2.0]), -1.27, 1.95, 2.75, 64)
    assert vertices.shape == (256, 3)
    assert faces.shape == (128, 3)
    assert np.isfinite(vertices).all()
    assert np.allclose(vertices[:, 1], -1.27)
    normals_y = []
    for face in faces:
        a, b, c = vertices[face]
        normals_y.append(np.cross(b - a, c - a)[1])
    assert min(normals_y) > 0.0


def test_box_clearance_reports_distance_outside_rectangle() -> None:
    points = np.array([[2.0, 0.0], [0.5, 0.5], [0.0, 2.0]])
    distance = distance_to_bounds(points, np.array([-1.0, -1.0]), np.array([1.0, 1.0]))
    assert distance.tolist() == pytest.approx([1.0, 0.0, 1.0])


def test_authored_loop_encloses_column_and_fits_capsule() -> None:
    source = {
        "center": np.array([-0.700118, 0.750685]),
        "lower": np.array([-1.256857, -0.741561]),
        "upper": np.array([0.361927, 1.388522]),
    }
    result = capsule_route_check(
        source,
        2.35,
        0.8,
        1.95,
        2.75,
        np.array([0.5184, 0.6]),
        0.3,
    )

    assert result["pass"]
    assert result["lateral_margin_each_side_m"] == pytest.approx(0.1)
    assert result["centerline_obstacle_clearance_after_capsule_m"] > 0.2


def test_glb_has_scene_nodes_and_well_formed_chunks() -> None:
    floor_vertices, floor_faces = floor_ring_mesh(np.zeros(2), -1.0, 1.0, 2.0, 8)
    glb = build_glb(
        [
            {
                "name": "AuthoredPlanarRouteFloor",
                "vertices": floor_vertices,
                "faces": floor_faces,
            }
        ],
        {"metric_scale_accepted": False},
    )
    magic, version, total_length = struct.unpack_from("<4sII", glb, 0)
    json_length = struct.unpack_from("<I", glb, 12)[0]
    document = json.loads(glb[20 : 20 + json_length])

    assert magic == b"glTF"
    assert version == 2
    assert total_length == len(glb)
    assert document["nodes"][0]["name"] == "AuthoredPlanarRouteFloor"
    assert document["asset"]["extras"]["metric_scale_accepted"] is False


def test_authored_route_glb_preserves_world_space_engine_contract() -> None:
    import build_route

    data = build_route._load_scene_inputs()
    data["geometry"] = make_route_geometry(data["source"], data["spec"], data["grid"])
    data.update(build_route._make_meshes(data))
    glb = build_glb(build_route._named_meshes(data), build_route._asset_extras(data))
    json_length = struct.unpack_from("<I", glb, 12)[0]
    document = json.loads(glb[20 : 20 + json_length])

    assert [node["name"] for node in document["nodes"]] == [
        "AuthoredPlanarRouteFloor",
        "ColumnObstacleProxy",
    ]
    assert all(set(node) == {"name", "mesh"} for node in document["nodes"])
    assert document["asset"]["extras"]["transform"].startswith("identity;")
    assert document["asset"]["extras"]["metric_scale_accepted"] is False
    assert document["asset"]["extras"]["hunyuan_registration_accepted"] is False

    floor_accessor_id = document["meshes"][0]["primitives"][0]["attributes"]["POSITION"]
    floor_bounds = document["accessors"][floor_accessor_id]
    assert floor_bounds["min"][1] == pytest.approx(data["floor_y"])
    assert floor_bounds["max"][1] == pytest.approx(data["floor_y"])
    assert floor_bounds["min"][0] < floor_bounds["max"][0]
    assert floor_bounds["min"][2] < floor_bounds["max"][2]
    route_center = data["geometry"]["center"]
    outer_radius = data["geometry"]["outer"]
    assert (floor_bounds["min"][0] + floor_bounds["max"][0]) / 2 == pytest.approx(
        route_center[0]
    )
    assert (floor_bounds["min"][2] + floor_bounds["max"][2]) / 2 == pytest.approx(
        route_center[1]
    )
    assert floor_bounds["max"][0] == pytest.approx(route_center[0] + outer_radius)
    assert floor_bounds["max"][2] == pytest.approx(route_center[1] + outer_radius)
