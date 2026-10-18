"""Build the CPU-only authored route, provenance report, and review images."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROTO = HERE.parent
sys.path.insert(0, str(PROTO))
sys.path.insert(0, str(HERE))

import camera_path_diagnostic_inputs as camera_inputs
from collision_meshes import box_mesh, floor_ring_mesh
from glb_writer import build_glb
from route_geometry import (
    make_route_geometry,
)
from route_report import make_report
from route_review_images import write_review_images
from route_source import analyze_source, load_candidate_grid, load_spec

OUTPUT_GLB = HERE / "authored_route_collision.glb"
OUTPUT_REPORT = HERE / "route_report.json"


def build() -> dict:
    """Build deterministic meshes and all review evidence on the CPU."""
    data = _load_scene_inputs()
    data["geometry"] = make_route_geometry(data["source"], data["spec"], data["grid"])
    data.update(_make_meshes(data))
    data["glb"] = build_glb(_named_meshes(data), _asset_extras(data))
    report = make_report(data, data["glb"])
    _write_products(data["glb"], report)
    write_review_images(data["context"], data["source"], data["geometry"], data["grid"])
    return report


def _load_scene_inputs() -> dict:
    """Load the reviewed source records and immutable candidate grid."""
    spec = load_spec()
    context = camera_inputs.load_camera_path()
    return {
        "spec": spec,
        "context": context,
        "source": analyze_source(context, spec),
        "grid": load_candidate_grid(),
    }


def _make_meshes(data: dict) -> dict:
    """Create the floor ring and separate conservative column proxy."""
    grid, spec, source, geometry = (
        data[key] for key in ("grid", "spec", "source", "geometry")
    )
    floor_y = float(np.nanmedian(grid["heights_m"]))
    floor = floor_ring_mesh(
        geometry["center"],
        floor_y,
        geometry["inner"],
        geometry["outer"],
        int(spec["route"]["segments"]),
    )
    column = box_mesh(
        source["lower"],
        source["upper"],
        floor_y,
        float(spec["column_review"]["height_m"]),
    )
    return {"floor_y": floor_y, "floor_mesh": floor, "column_mesh": column}


def _named_meshes(data: dict) -> list[dict]:
    """Name the exported meshes for stable engine-side discovery."""
    return [
        {
            "name": "AuthoredPlanarRouteFloor",
            "vertices": data["floor_mesh"][0],
            "faces": data["floor_mesh"][1],
        },
        {
            "name": "ColumnObstacleProxy",
            "vertices": data["column_mesh"][0],
            "faces": data["column_mesh"][1],
        },
    ]


def _asset_extras(data: dict) -> dict:
    """Mark the GLB's coordinate policy and unresolved scale gates."""
    return {
        "issue": int(data["spec"]["issue"]),
        "asset_status": "experimental_authored_collision_proxy",
        "coordinate_frame": "Godot world coordinates under the chosen #100 convention",
        "transform": "identity; world positions are baked into mesh vertices",
        "floor_height_m": data["floor_y"],
        "metric_scale_accepted": False,
        "hunyuan_registration_accepted": False,
    }


def _write_products(glb: bytes, report: dict) -> None:
    """Write the generated GLB and deterministic JSON measurements."""
    OUTPUT_GLB.write_bytes(glb)
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    result = build()
    print(
        json.dumps(
            {
                "status": result["status"],
                "path_length_m": result["route"]["closed_path_length_m"],
                "candidate_support_fraction": result["route"][
                    "candidate_footprint_proximity"
                ]["candidate_support_fraction"],
                "minimum_column_clearance_m": result["column_obstacle"][
                    "route_centerline_min_clearance_m"
                ],
                "glb_bytes": result["export"]["bytes"],
            },
            indent=2,
        )
    )
