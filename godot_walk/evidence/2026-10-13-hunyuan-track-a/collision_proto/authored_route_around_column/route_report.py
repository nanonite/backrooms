"""Human-readable measurements and provenance for the authored route mesh."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from route_geometry import corridor_coverage
from route_source import GRID_PATH, camera_inputs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
GLB_PATH = HERE / "authored_route_collision.glb"


def make_report(data: dict, glb: bytes) -> dict:
    """Assemble the small report while keeping evidence separate from fill."""
    return {
        "schema_version": 1,
        "issue": 139,
        "status": "experimental_authored_route_prototype",
        "gpu_used": False,
        "inference_run": False,
        "metric_scale_accepted": False,
        "hunyuan_registration_accepted": False,
        "plane": _plane_record(data["floor_y"]),
        "route": _route_record(data),
        "column_obstacle": _column_record(data),
        "edge_boundaries": _edge_boundary_record(data),
        "export": _export_record(data, glb),
        "inputs": _input_record(data),
        "limits": _limits(),
    }


def _plane_record(floor_y: float) -> dict:
    """State the chosen plane and which terrain claims it cannot support."""
    return {
        "height_m": floor_y,
        "basis": "#100 chosen floor plane; not measured terrain",
        "slope_and_step_validation": "not applicable to this planar authored mesh",
    }


def _route_record(data: dict) -> dict:
    """Record route coordinates, candidate overlap, and authored fill."""
    return _route_design_record(data) | _route_evidence_record(data)


def _route_design_record(data: dict) -> dict:
    """Record chosen route location, dimensions, and closed-path length."""
    spec, source, geometry = (data[key] for key in ("spec", "source", "geometry"))
    return {
        "kind": spec["route"]["kind"],
        "center_xz_m": geometry["center"].tolist(),
        "center_offset_from_camera_orbit_xz_m": spec["route"][
            "center_offset_from_camera_orbit_xz_m"
        ],
        "camera_orbit_fit_radius_m": source["orbit_radius"],
        "camera_orbit_abs_residual_q50_q90_max_m": np.quantile(
            np.abs(source["residuals"]), [0.5, 0.9, 1.0]
        ).tolist(),
        "radius_m": geometry["radius"],
        "width_m": geometry["width"],
        "inner_radius_m": geometry["inner"],
        "outer_radius_m": geometry["outer"],
        "start_xz_m": geometry["centerline"][0].tolist(),
        "end_xz_m": geometry["centerline"][0].tolist(),
        "closed_path_length_m": _closed_path_length(geometry["centerline"]),
        "centerline_samples": len(geometry["centerline"]),
    }


def _route_evidence_record(data: dict) -> dict:
    """Record candidate overlap separately from authored support geometry."""
    geometry, grid = (data[key] for key in ("geometry", "grid"))
    band = corridor_coverage(
        grid, geometry["center"], geometry["inner"], geometry["outer"]
    )
    return {
        "candidate_footprint_proximity": geometry["support"],
        "candidate_footprint_corridor_comparison": band,
        "offline_capsule_geometry_check": geometry["capsule_check"],
        "explicit_authored_fill": _authored_fill_record(),
    }


def _closed_path_length(centerline: np.ndarray) -> float:
    """Measure the loop through the final segment back to its start."""
    closed = np.vstack((centerline, centerline[0]))
    return float(np.linalg.norm(np.diff(closed, axis=0), axis=1).sum())


def _authored_fill_record() -> dict:
    """Keep the unreviewed candidate grid distinct from the authored GLB."""
    return {
        "mesh_covers_full_loop": True,
        "candidate_support_is_not_ground_truth": True,
        "unknown_cells_in_candidate_grid_remain_unmodified": True,
    }


def _column_record(data: dict) -> dict:
    """Record reviewed frames, conservative bounds, and path clearance."""
    spec, source, geometry = (data[key] for key in ("spec", "source", "geometry"))
    images = {
        frame["image"]: _sha256(
            ROOT / "data/scenes/corridor_travel/images" / frame["image"]
        )
        for frame in spec["column_review"]["frames"]
    }
    return {
        "review_method": spec["column_review"]["method"],
        "frames": source["column_records"],
        "source_image_sha256": images,
        "footprint_lower_xz_m": source["lower"].tolist(),
        "footprint_upper_xz_m": source["upper"].tolist(),
        "horizontal_margin_m": float(spec["column_review"]["horizontal_margin_m"]),
        "height_m": float(spec["column_review"]["height_m"]),
        "height_basis": spec["column_review"]["height_basis"],
        "route_centerline_min_clearance_m": float(geometry["clearances"].min()),
        "capsule_radius_m": float(spec["capsule"]["radius_m"]),
        "capsule_residual_clearance_m": geometry["capsule_check"][
            "centerline_obstacle_clearance_after_capsule_m"
        ],
    }


def _edge_boundary_record(data: dict) -> dict:
    """Document the authored boundary geometry and its assumed plane placement."""
    spec = data["spec"]["edge_boundaries"]
    check = data["geometry"]["edge_boundary_check"]
    column_to_inner_wall = check["column_to_inner_wall_m"]
    return {
        **check,
        "floor_y_m": data["floor_y"],
        "floor_y_basis": spec["assumed_floor_y_source"],
        "column_intersects_inner_boundary": column_to_inner_wall <= 0.0,
        "omitted_segments_because_column_blocks": 0,
        "both_open_edges_fully_bounded": True,
        "mesh_names": [
            "authored_edge_boundary_inner",
            "authored_edge_boundary_outer",
        ],
        "transforms": "identity nodes; world-space vertices match Godot source scene",
    }
def _export_record(data: dict, glb: bytes) -> dict:
    """Record triangle counts, content hash, and baked-world transform policy."""
    floor_mesh, column_mesh = data["floor_mesh"], data["column_mesh"]
    inner_wall, outer_wall = (
        data["inner_edge_boundary_mesh"],
        data["outer_edge_boundary_mesh"],
    )
    return {
        "path": GLB_PATH.name,
        "format": "glTF 2.0 binary (GLB)",
        "sha256": hashlib.sha256(glb).hexdigest(),
        "bytes": len(glb),
        "mesh_names": [
            "AuthoredPlanarRouteFloor",
            "ColumnObstacleProxy",
            "authored_edge_boundary_inner",
            "authored_edge_boundary_outer",
        ],
        "floor_vertices": len(floor_mesh[0]),
        "floor_triangles": len(floor_mesh[1]),
        "column_vertices": len(column_mesh[0]),
        "column_triangles": len(column_mesh[1]),
        "edge_boundary_vertices": len(inner_wall[0]) + len(outer_wall[0]),
        "edge_boundary_triangles": len(inner_wall[1]) + len(outer_wall[1]),
        "inner_edge_boundary_triangles": len(inner_wall[1]),
        "outer_edge_boundary_triangles": len(outer_wall[1]),
        "node_transform": "identity; vertices already use #100 Godot world coordinates",
        "grid_spacing_m": float(data["grid"]["spacing_m"]),
    }


def _input_record(data: dict) -> dict:
    """Hash every input that controls route geometry or the review decision."""
    context = data["context"]
    frame_paths = [
        ROOT / "data/scenes/corridor_travel/images" / image.name
        for image in context.images
        if image.name
        in {frame["image"] for frame in data["spec"]["column_review"]["frames"]}
    ]
    return {
        "alignment_and_registered_pose_hashes": camera_inputs.input_hashes(),
        "candidate_grid_sha256": _sha256(GRID_PATH),
        "route_spec_sha256": _sha256(HERE / "route_spec.json"),
        "registered_images": {path.name: _sha256(path) for path in frame_paths},
    }


def _sha256(path: Path) -> str:
    """Hash one input file in bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _limits() -> list[str]:
    """List the unresolved evidence and engineering gates without ambiguity."""
    return [
        "The #100 scale is a chosen synthetic convention, not surveyed metric scale.",
        "The floor is an explicitly authored horizontal mesh imported into Godot, not reconstructed terrain.",
        "The column footprint uses manually selected image pixels and an assumed floor plane.",
        "The fourth base corner is derived by parallelogram closure; the obstacle is a conservative AABB proxy.",
        "No engine physics traversal, slope, step, or headroom validation is claimed; #141 owns controller testing.",
        "Hunyuan #134 registration remains unaccepted; this route is independent authored support.",
    ]
