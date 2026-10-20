"""Build the authored #147 bounded route collision asset on the CPU."""

from __future__ import annotations

import hashlib
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ISSUE_DIR = Path(__file__).resolve().parent
ROOT = ISSUE_DIR.parents[2]
REFERENCE_GEOMETRY = (
    ROOT
    / "godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column"
)
sys.path.insert(0, str(REFERENCE_GEOMETRY))

from collision_meshes import box_mesh, edge_boundary_mesh, floor_ring_mesh  # noqa: E402
from glb_writer import build_glb  # noqa: E402

OUTPUT_GLB = ISSUE_DIR / "authored_route_collision_v2.glb"
OUTPUT_REPORT = ISSUE_DIR / "route_report_v2.json"
FLOOR_Y_M = -1.2709904909133911
ROUTE_CENTER_XZ_M = (-0.45011800276157465, 1.4506849140103122)
ROUTE_RADIUS_M = 3.3
ROUTE_WIDTH_M = 0.8
ROUTE_SEGMENTS = 256
COLUMN_LOWER_XZ_M = (-1.2568561533613571, -0.7415601043662503)
COLUMN_UPPER_XZ_M = (0.36192645011758046, 1.3885216998149807)
COLUMN_HEIGHT_M = 2.4
BOUNDARY_HEIGHT_M = 1.4
BOUNDARY_THICKNESS_M = 0.08


def make_meshes() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    center = np.asarray(ROUTE_CENTER_XZ_M, dtype=np.float32)
    inner = ROUTE_RADIUS_M - ROUTE_WIDTH_M / 2.0
    outer = ROUTE_RADIUS_M + ROUTE_WIDTH_M / 2.0
    return {
        "floor": floor_ring_mesh(center, FLOOR_Y_M, inner, outer, ROUTE_SEGMENTS),
        "column": box_mesh(
            np.asarray(COLUMN_LOWER_XZ_M),
            np.asarray(COLUMN_UPPER_XZ_M),
            FLOOR_Y_M,
            COLUMN_HEIGHT_M,
        ),
        "inner": edge_boundary_mesh(
            center,
            inner,
            outer,
            FLOOR_Y_M,
            BOUNDARY_HEIGHT_M,
            BOUNDARY_THICKNESS_M,
            ROUTE_SEGMENTS,
            "inner",
        ),
        "outer": edge_boundary_mesh(
            center,
            inner,
            outer,
            FLOOR_Y_M,
            BOUNDARY_HEIGHT_M,
            BOUNDARY_THICKNESS_M,
            ROUTE_SEGMENTS,
            "outer",
        ),
    }


def named_meshes(meshes: dict[str, tuple[np.ndarray, np.ndarray]]) -> list[dict]:
    names = {
        "floor": "AuthoredPlanarRouteFloor",
        "column": "ColumnObstacleProxy",
        "inner": "authored_edge_boundary_inner",
        "outer": "authored_edge_boundary_outer",
    }
    return [
        {"name": names[key], "vertices": value[0], "faces": value[1]}
        for key, value in meshes.items()
    ]


def triangle_count(meshes: dict[str, tuple[np.ndarray, np.ndarray]], name: str) -> int:
    return len(meshes[name][1]) if name in meshes else 0


def build_report(
    meshes: dict[str, tuple[np.ndarray, np.ndarray]], glb: bytes, output_path: Path, control: str
) -> dict:
    return {
        "schema_version": 1,
        "issue": 147,
        "status": "negative_control" if control else "authored_bounded_candidate_not_admitted",
        "negative_control": control or None,
        "gpu_used": False,
        "metric_scale_accepted": False,
        "hunyuan_registration_accepted": False,
        "plane": {"height_m": FLOOR_Y_M, "basis": "#100 chosen floor convention; not surveyed"},
        "route": {
            "kind": "authored_expanded_loop_around_observed_column_candidate",
            "center_xz_m": list(ROUTE_CENTER_XZ_M),
            "radius_m": ROUTE_RADIUS_M,
            "width_m": ROUTE_WIDTH_M,
            "inner_radius_m": ROUTE_RADIUS_M - ROUTE_WIDTH_M / 2.0,
            "outer_radius_m": ROUTE_RADIUS_M + ROUTE_WIDTH_M / 2.0,
            "closed_path_length_m": 2.0 * np.pi * ROUTE_RADIUS_M,
            "centerline_samples": ROUTE_SEGMENTS * 6,
            "geometry_origin": "authored; a bounded playable candidate, not a recovered room extent",
        },
        "column_obstacle": {
            "footprint_lower_xz_m": list(COLUMN_LOWER_XZ_M),
            "footprint_upper_xz_m": list(COLUMN_UPPER_XZ_M),
            "height_m": COLUMN_HEIGHT_M,
            "basis": "reused conservative authored proxy from #135 frames 0137 and 0141",
            "metric_scale_accepted": False,
        },
        "edge_boundaries": {
            "height_m": BOUNDARY_HEIGHT_M,
            "thickness_m": BOUNDARY_THICKNESS_M,
            "origin": "authored, not reconstructed",
            "inner_and_outer_rings_closed": True,
        },
        "export": {
            "path": output_path.name,
            "sha256": hashlib.sha256(glb).hexdigest(),
            "bytes": len(glb),
            "floor_triangles": triangle_count(meshes, "floor"),
            "column_triangles": triangle_count(meshes, "column"),
            "inner_edge_boundary_triangles": triangle_count(meshes, "inner"),
            "outer_edge_boundary_triangles": triangle_count(meshes, "outer"),
            "mesh_names": [mesh["name"] for mesh in named_meshes(meshes)],
            "node_transform": "identity; authored vertices use the uncalibrated #100 convention",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--negative-control",
        choices=("missing_floor", "missing_column", "missing_boundaries"),
    )
    control = parser.parse_args().negative_control or ""
    output_directory = ISSUE_DIR / "negative_controls" if control else ISSUE_DIR
    output_glb = output_directory / (f"{control}.glb" if control else OUTPUT_GLB.name)
    output_report = output_directory / (f"{control}_route_report.json" if control else OUTPUT_REPORT.name)
    output_directory.mkdir(parents=True, exist_ok=True)
    if output_glb.exists() or output_report.exists():
        raise FileExistsError("refusing to overwrite an existing #147 collision output")
    meshes = make_meshes()
    omitted = {
        "missing_floor": ("floor",),
        "missing_column": ("column",),
        "missing_boundaries": ("inner", "outer"),
    }.get(control, ())
    for name in omitted:
        meshes.pop(name)
    glb = build_glb(
        named_meshes(meshes),
        {
            "issue": 147,
            "asset_status": "negative_control" if control else "authored_collision_candidate",
            "metric_scale_accepted": False,
            "hunyuan_registration_accepted": False,
            "boundaries_origin": "authored_not_reconstructed",
            "negative_control": control or None,
        },
    )
    report = build_report(meshes, glb, output_glb, control)
    output_glb.write_bytes(glb)
    output_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["export"], indent=2))


if __name__ == "__main__":
    main()
